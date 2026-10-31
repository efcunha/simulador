"""Drift views projected from the canonical estate (C11, consumer side).

The generator emits the drift INPUTS, not a FinOps verdict: an inventory asset that is
absent from the IaC snapshot is unmanaged, and a ``declared_config`` that disagrees with
the inventory is a modified resource. Those are cloud/provider facts. The modelled
attribute is the tag/label map (the estate has real values for it); the C11 catalogue's
firewall-specific case is NOT modelled here and remains a separate scenario. This module turns
them into the two provider-native API representations the cloud publishes:

* GCP Infrastructure Manager ``ResourceDrift`` (``propertyDrifts``);
* Azure Deployment Stacks ``deploymentStacksWhatIfResults`` (``resourceChanges``).

WHY A PROJECTION AND NOT A NEW ESTATE FIELD
-------------------------------------------
``CanonicalEstate`` is the single source of truth for *inputs* (inventory, IaC snapshots,
resources, instance profiles). Adding a derived drift tuple would duplicate state and make
the C11 input/output separation ambiguous. Both the renderer and the two emulators call
:func:`project_drift_views` on the same frozen estate, so the JSON artifact and the HTTP
response cannot disagree.

WHAT IS DERIVED, AND FROM WHERE
-------------------------------
* a resource's actual tags are ``Resource.tags`` (the same tuple FOCUS publishes);
* its declared tags are ``IacResourceState.declared_config["tags"]`` (the snapshot now
  carries them; see ``generate/estate_builder._build_iac``);
* a resource is managed when ``InventoryAsset.managed_by_iac`` is true; the snapshot has
  one ``IacResourceState`` per managed resource (the C11 catalogue's firewall case is not
  modelled: the estate has no ``InventoryAsset`` for an NSG, so its rules are not compared);
* a VM's size is ``InstanceProfile.instance_type`` (derived from the SKU catalogue), never
  a literal in this module.

Only resources with a real tag difference become a modified drift. A managed resource
whose declared tags equal the actual tags is NOT emitted -- an empty drift would be a
fabricated finding. An unmanaged Azure VM becomes a ``detach`` change, which is the
provider's own vocabulary for "exists in Azure, no longer managed by the stack".

IDENTIFIERS
-----------
GCP resource drift names use the official ``projects/{p}/locations/{l}/previews/{pv}/
resourceDrifts/{id}`` shape; ``{id}`` is the resource's stable UUIDv5, so the name is
deterministic. Azure ARM IDs use the subscription GUID the estate already mints
(``azure_subscription_guid``) and the resource group the network projection already uses
(``synthetic-rg-<scope[:8]>``) -- the same pair the ARM rows publish, so a caller can
resolve one from the other.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from tools.synthetic_clouds.model.identity import azure_subscription_guid

if TYPE_CHECKING:
    from tools.synthetic_clouds.model.estate import CanonicalEstate
    from tools.synthetic_clouds.model.resource import Resource

_GCP = "gcp"
_AZURE = "azure"
_COMPUTE_INSTANCE = "compute_instance"
_VIRTUAL_MACHINE = "virtual_machine"

#: Nome do preview/resultado: nao e um id de ninguem; e o nome que o operador escolhe.
_PREVIEW = "synthetic-drift"
_WHAT_IF_NAME = "synthetic-drift-what-if"

#: O provider Terraform que o Infrastructure Manager usa para `google_compute_instance`.
_GCP_TF_PROVIDER = "registry.terraform.io/hashicorp/google"
_GCP_TF_TYPE = "google_compute_instance"

_LABEL_RE = re.compile(r"[^a-z0-9_]+")


@dataclass(slots=True, frozen=True)
class GcpTerraformInfo:
    """``ResourceDriftTerraformInfo`` (todos os campos são output-only no GCP)."""

    address: str
    type: str
    resource_name: str
    provider: str


@dataclass(slots=True, frozen=True)
class GcpPropertyDrift:
    """``PropertyDrift``: um caminho do state com os valores antes/depois."""

    path: str
    before: str | None
    after: str | None
    before_sensitive_paths: tuple[str, ...] = ()
    after_sensitive_paths: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class GcpResourceDrift:
    """``ResourceDrift`` de um ``preview`` do Infrastructure Manager."""

    name: str
    terraform_info: GcpTerraformInfo
    property_drifts: tuple[GcpPropertyDrift, ...]


@dataclass(slots=True, frozen=True)
class AzurePropertyChange:
    """``DeploymentStacksWhatIfPropertyChange``."""

    path: str
    before: Any
    after: Any
    change_type: str
    children: tuple[Any, ...] = ()


@dataclass(slots=True, frozen=True)
class AzureResourceChange:
    """``DeploymentStacksWhatIfResourceChange``."""

    id: str
    type: str
    change_type: str
    change_certainty: str
    management_before: str | None
    management_after: str | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    delta: tuple[AzurePropertyChange, ...]


@dataclass(slots=True, frozen=True)
class AzureWhatIfResult:
    """``DeploymentStacksWhatIfResult`` de um resource group."""

    id: str
    name: str
    type: str
    location: str
    resource_changes: tuple[AzureResourceChange, ...]


@dataclass(slots=True, frozen=True)
class DriftViews:
    """As duas projeções, já ordenadas para entrega determinística."""

    gcp_resource_drifts: tuple[GcpResourceDrift, ...]
    azure_what_if_results: tuple[AzureWhatIfResult, ...]


def _declared_by_uuid(estate: CanonicalEstate) -> dict[str, dict[str, Any]]:
    """``resource_uuid -> declared_config`` de todos os snapshots de IaC."""
    declared: dict[str, dict[str, Any]] = {}
    for snapshot in estate.iac_snapshots:
        for state in snapshot.resource_states:
            declared[state.resource_uuid] = state.declared_config
    return declared


def _inventory_by_uuid(estate: CanonicalEstate) -> dict[str, Any]:
    return {asset.resource_uuid: asset for asset in estate.inventory}


def _actual_tags(resource: Resource) -> dict[str, str]:
    return dict(resource.tags)


def _tag_diffs(actual: dict[str, str], declared: dict[str, Any]) -> list[tuple[str, str | None, str | None]]:
    """Diferenças de tag no formato ``(chave, before, after)``.

    ``before`` é o valor ATUAL e ``after`` o declarado. No Terraform plan e no ARM
    what-if o lado "before" é o estado atual; a direção fica explícita aqui para que
    nenhum consumidor precise adivinhá-la.
    """
    chaves = sorted(set(actual) | set(declared))
    diffs: list[tuple[str, str | None, str | None]] = []
    for chave in chaves:
        antes = actual.get(chave)
        depois = declared.get(chave)
        if antes != depois:
            diffs.append((chave, antes, depois if isinstance(depois, str) else None))
    return diffs


def _gcp_label(resource: Resource) -> str:
    """Rótulo HCL determinístico, derivado do nome do recurso (nunca inventado)."""
    base = _LABEL_RE.sub("_", resource.resource_name.lower()).strip("_")
    if not base:
        base = f"resource_{resource.identity.uuid[:8]}"
    if base[0].isdigit():
        base = f"r_{base}"
    return base


def _gcp_projection(
    estate: CanonicalEstate,
    declared: dict[str, dict[str, Any]],
    inventory: dict[str, Any],
) -> tuple[GcpResourceDrift, ...]:
    profiles = {profile.resource_uuid: profile for profile in estate.instance_profiles}
    rows: list[GcpResourceDrift] = []
    for resource in sorted(estate.resources, key=lambda item: item.identity.uuid):
        if resource.identity.provider != _GCP or resource.resource_type != _COMPUTE_INSTANCE:
            continue
        asset = inventory.get(resource.identity.uuid)
        if asset is None or not asset.managed_by_iac:
            continue
        config = declared.get(resource.identity.uuid)
        if not config or "tags" not in config:
            continue
        actual = _actual_tags(resource)
        declaradas = config.get("tags") or {}
        diffs = _tag_diffs(actual, declaradas)
        if not diffs:
            continue
        label = _gcp_label(resource)
        project = resource.parent_scope_id
        location = resource.region_id
        profile = profiles.get(resource.identity.uuid)
        # O preview é nosso; o location é a região do recurso (Infra Manager só
        # aceita locations válidas, e a região do próprio recurso é uma).
        _ = profile
        rows.append(
            GcpResourceDrift(
                name=(
                    f"projects/{project}/locations/{location}/previews/{_PREVIEW}"
                    f"/resourceDrifts/{resource.identity.uuid}"
                ),
                terraform_info=GcpTerraformInfo(
                    address=f"{_GCP_TF_TYPE}.{label}",
                    type=_GCP_TF_TYPE,
                    resource_name=label,
                    provider=_GCP_TF_PROVIDER,
                ),
                property_drifts=tuple(
                    GcpPropertyDrift(path=f"labels.{chave}", before=antes, after=depois)
                    for chave, antes, depois in diffs
                ),
            )
        )
    return tuple(rows)


def _azure_vm_id(estate: CanonicalEstate, resource: Resource) -> str:
    scope = resource.parent_scope_id
    subscription = azure_subscription_guid(estate.seed, scope)
    resource_group = f"synthetic-rg-{scope[:8]}"
    return (
        f"/subscriptions/{subscription}/resourceGroups/{resource_group}"
        f"/providers/Microsoft.Compute/virtualMachines/{resource.resource_name}"
    )


def _azure_config(resource: Resource, tags: dict[str, str], vm_size: str | None) -> dict[str, Any]:
    """Configuração que o ARM publica para uma VM: o que o estado realmente sabe."""
    properties: dict[str, Any] = {}
    if vm_size:
        properties["hardwareProfile"] = {"vmSize": vm_size}
    return {
        "location": resource.region_id,
        "tags": tags,
        "properties": properties,
    }


def _azure_projection(
    estate: CanonicalEstate,
    declared: dict[str, dict[str, Any]],
    inventory: dict[str, Any],
) -> tuple[AzureWhatIfResult, ...]:
    profiles = {profile.resource_uuid: profile for profile in estate.instance_profiles}
    por_escopo: dict[tuple[str, str, str], list[AzureResourceChange]] = {}
    for resource in sorted(estate.resources, key=lambda item: item.identity.uuid):
        if resource.identity.provider != _AZURE or resource.resource_type != _VIRTUAL_MACHINE:
            continue
        asset = inventory.get(resource.identity.uuid)
        if asset is None:
            continue
        profile = profiles.get(resource.identity.uuid)
        vm_size = profile.instance_type if profile is not None else None
        resource_id = _azure_vm_id(estate, resource)
        actual = _actual_tags(resource)
        if not asset.managed_by_iac:
            # Existe na Azure e não está no snapshot de IaC: `detach` é o
            # vocabulário que a Deployment Stack publica para esse caso.
            change = AzureResourceChange(
                id=resource_id,
                type="Microsoft.Compute/virtualMachines",
                change_type="detach",
                change_certainty="definite",
                management_before="managed",
                management_after="unmanaged",
                before=_azure_config(resource, actual, vm_size),
                after=None,
                delta=(),
            )
        else:
            config = declared.get(resource.identity.uuid)
            if not config or "tags" not in config:
                continue
            declaradas = config.get("tags") or {}
            diffs = _tag_diffs(actual, declaradas)
            if not diffs:
                continue
            delta = tuple(
                AzurePropertyChange(
                    path=f"tags.{chave}",
                    before=antes,
                    after=depois,
                    change_type="delete" if depois is None else "modify",
                )
                for chave, antes, depois in diffs
            )
            change = AzureResourceChange(
                id=resource_id,
                type="Microsoft.Compute/virtualMachines",
                change_type="modify",
                change_certainty="definite",
                management_before="managed",
                management_after="managed",
                before=_azure_config(resource, actual, vm_size),
                after=_azure_config(resource, {k: v for k, v in declaradas.items() if isinstance(v, str)}, vm_size),
                delta=delta,
            )
        subscription = azure_subscription_guid(estate.seed, resource.parent_scope_id)
        resource_group = f"synthetic-rg-{resource.parent_scope_id[:8]}"
        chave = (subscription, resource_group, resource.region_id)
        por_escopo.setdefault(chave, []).append(change)

    resultados: list[AzureWhatIfResult] = []
    for (subscription, resource_group, location), changes in sorted(por_escopo.items()):
        # `modify` primeiro: o teste de fidelidade lê a primeira linha do artefato
        # para o conjunto de caminhos, e o `detach` não tem delta.
        ordenadas = tuple(
            sorted(changes, key=lambda item: (item.change_type != "modify", item.id))
        )
        resultado_id = (
            f"/subscriptions/{subscription}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.Resources/deploymentStacksWhatIfResults/{_WHAT_IF_NAME}"
        )
        resultados.append(
            AzureWhatIfResult(
                id=resultado_id,
                name=_WHAT_IF_NAME,
                type="Microsoft.Resources/deploymentStacksWhatIfResults",
                location=location,
                resource_changes=ordenadas,
            )
        )
    return tuple(resultados)


def project_drift_views(estate: CanonicalEstate) -> DriftViews:
    """Projeta os dois contratos nativos a partir de UM estado canônico congelado."""
    declared = _declared_by_uuid(estate)
    inventory = _inventory_by_uuid(estate)
    return DriftViews(
        gcp_resource_drifts=_gcp_projection(estate, declared, inventory),
        azure_what_if_results=_azure_projection(estate, declared, inventory),
    )


# ── Serialização para os contratos publicados ────────────────────────────────


def gcp_resource_drift_document(drift: GcpResourceDrift) -> dict[str, Any]:
    """Corpo de UM ``ResourceDrift`` (o item de ``resourceDrifts[]``)."""
    return {
        "name": drift.name,
        "terraformInfo": {
            "address": drift.terraform_info.address,
            "type": drift.terraform_info.type,
            "resourceName": drift.terraform_info.resource_name,
            "provider": drift.terraform_info.provider,
        },
        "propertyDrifts": [
            {
                "path": item.path,
                "beforeSensitivePaths": list(item.before_sensitive_paths),
                "before": item.before,
                "afterSensitivePaths": list(item.after_sensitive_paths),
                "after": item.after,
            }
            for item in drift.property_drifts
        ],
    }


def azure_what_if_document(result: AzureWhatIfResult) -> dict[str, Any]:
    """Corpo de UM ``DeploymentStacksWhatIfResult``."""
    return {
        "id": result.id,
        "type": result.type,
        "name": result.name,
        "location": result.location,
        "properties": {
            "changes": {
                "resourceChanges": [
                    {
                        "id": change.id,
                        "type": change.type,
                        "changeType": change.change_type,
                        "changeCertainty": change.change_certainty,
                        "managementStatusChange": {
                            "before": change.management_before,
                            "after": change.management_after,
                        },
                        "resourceConfigurationChanges": {
                            "before": change.before,
                            "after": change.after,
                            "delta": [
                                {
                                    "path": item.path,
                                    "before": item.before,
                                    "after": item.after,
                                    "changeType": item.change_type,
                                    "children": list(item.children),
                                }
                                for item in change.delta
                            ],
                        },
                    }
                    for change in result.resource_changes
                ]
            }
        },
    }


def gcp_flat_rows(drifts: tuple[GcpResourceDrift, ...]) -> list[dict[str, Any]]:
    """Uma linha plana por ``propertyDrift``, com os nomes documentados."""
    rows: list[dict[str, Any]] = []
    for drift in drifts:
        for item in drift.property_drifts:
            rows.append(
                {
                    "name": drift.name,
                    "terraformInfo.address": drift.terraform_info.address,
                    "terraformInfo.type": drift.terraform_info.type,
                    "terraformInfo.resourceName": drift.terraform_info.resource_name,
                    "terraformInfo.provider": drift.terraform_info.provider,
                    "propertyDrifts[].path": item.path,
                    "propertyDrifts[].beforeSensitivePaths[]": list(item.before_sensitive_paths),
                    "propertyDrifts[].before": item.before,
                    "propertyDrifts[].afterSensitivePaths[]": list(item.after_sensitive_paths),
                    "propertyDrifts[].after": item.after,
                }
            )
    return rows


def azure_flat_rows(results: tuple[AzureWhatIfResult, ...]) -> list[dict[str, Any]]:
    """Uma linha plana por ``delta`` (ou por ``detach`` sem delta)."""
    rows: list[dict[str, Any]] = []
    for result in results:
        for change in result.resource_changes:
            deltas = change.delta or (None,)
            for item in deltas:
                rows.append(
                    {
                        "id": result.id,
                        "type": result.type,
                        "name": result.name,
                        "location": result.location,
                        "properties.changes.resourceChanges[].id": change.id,
                        "properties.changes.resourceChanges[].type": change.type,
                        "properties.changes.resourceChanges[].changeType": change.change_type,
                        "properties.changes.resourceChanges[].changeCertainty": change.change_certainty,
                        "properties.changes.resourceChanges[].managementStatusChange.before": change.management_before,
                        "properties.changes.resourceChanges[].managementStatusChange.after": change.management_after,
                        "properties.changes.resourceChanges[].resourceConfigurationChanges.before": change.before,
                        "properties.changes.resourceChanges[].resourceConfigurationChanges.after": change.after,
                        "properties.changes.resourceChanges[].resourceConfigurationChanges.delta[].path": (
                            item.path if item else None
                        ),
                        "properties.changes.resourceChanges[].resourceConfigurationChanges.delta[].before": (
                            item.before if item else None
                        ),
                        "properties.changes.resourceChanges[].resourceConfigurationChanges.delta[].after": (
                            item.after if item else None
                        ),
                        "properties.changes.resourceChanges[].resourceConfigurationChanges.delta[].changeType": (
                            item.change_type if item else None
                        ),
                        "properties.changes.resourceChanges[].resourceConfigurationChanges.delta[].children[]": (
                            list(item.children) if item else []
                        ),
                    }
                )
    return rows
