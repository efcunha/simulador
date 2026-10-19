"""Golden fidelity: the Azure security, network and instance artifacts carry EXACTLY the documented columns.

The specification is the source of truth (``specs/README.md``) and its normative reader is
``fidelity.spec.load_spec``. These tests RENDER the artifacts to a temporary directory and
compare the DELIVERED FILES with that specification through
``fidelity.checker.check_artifact`` -- never an in-memory column list, which would only prove
that two copies of the same mistake agree.

LEVEL UNDER TEST: THE DOCUMENTED PATH
-------------------------------------
The Azure specs spell a nested member as a PATH (``records[].properties.Version``,
``properties.storageProfile.osDisk.caching``), because that is the level at which the official
page names the field. The fidelity core reads the field set of a FILE and a cloud document is
nested, so each nested surface is delivered with a ``field_projection/`` sibling: the flatten
of the document that was actually written. ``check_artifact`` runs on that projection, and
every nested surface has a test proving the projection IS the delivered document flattened by
an INDEPENDENT walker -- so the audit is anchored to the artifact's bytes, not to the
renderer's intent.

THE THREE RESIDUALS THE SPECS THEMSELVES CREATE
-----------------------------------------------
These tests never accept an arbitrary finding. Each artifact's findings must be EXACTLY the
spec's own gaps, computed from the spec (never hardcoded) so that a spec edit moves both sides
at once:

1. ``invented`` == ZERO. The DELIVERED field projection carries exactly the spec's names: a
   container path that hosts a documented path without being listed as a column of its own
   (``properties``, ``...networkInterfaces[].properties``) is a STRUCTURAL CONTAINER of the
   document, never a field of the artifact. The tests assert that the synthesized containers
   are EXACTLY the minimal prefix closure (read from the document's own paths, so a container
   can never smuggle an undocumented column into the delivery) -- the same convention
   ``tests/test_gcp_billing_spec_fidelity.py`` established for the BigQuery records.
2. ``missing`` == the columns the spec marks ``required`` while refusing to generate them (no
   published type). Such a set is UNSATISFIABLE by construction: emitting the name is
   ``unverified_emitted``, omitting it is ``missing``. The renderer omits it and the test pins
   that residual, with a falsification test proving the emitted alternative is denounced.
3. Sets with zero emittable columns (the vnet blob sets, the Resource Graph
   ``SecurityResources/*`` sets, the attack-path set). The correct artifact for a set whose
   every column is ``example-only`` is NO FIELD AT ALL: the test asserts the empty field set
   against the spec and that no delivered file carries a name from those sets.

WHAT IS ALSO ASSERTED, AND WHY
------------------------------
* Every POPULATED column of every artifact is one the spec authorizes to receive a value
  (``is_generatable``): a column that belongs to the format while being declared always-empty
  is caught by ``check_artifact``'s value half, and with no ``null-empty`` column in these five
  specs the assertion is expressed as ``populated <= generatable``.
* The model-sourced VALUES are pinned where the canonical model carries them (``vmSize`` =
  ``sku_id``, ``SystemAlertId`` = the finding id, the window hour, ...), so an artifact that
  lost its values while keeping its column set cannot pass.
* The delivery FORMAT is pinned too: the two flow-log surfaces land on their documented blob
  partitions, the Defender surface writes no Storage container (Azure Storage is not a
  documented destination), and the Resource Graph/ARM artifacts are the documented result
  formats (``ObjectArray`` / a per-VM response body).
* Byte-determinism: rendering the same estate twice produces identical bytes.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from typing import Any

import pytest

from tools.synthetic_clouds.fidelity.artifacts import columns_of, populated_of
from tools.synthetic_clouds.fidelity.checker import (
    KIND_INVENTED,
    KIND_MISSING,
    KIND_POPULATED_EMPTY,
    KIND_UNVERIFIED,
    Finding,
    ScopeError,
    check,
    check_artifact,
    is_faithful,
)
from tools.synthetic_clouds.fidelity.spec import DEFAULT_SPECS_ROOT, Column, SurfaceSpec, load_spec
from tools.synthetic_clouds.generate.estate_builder import build_estate
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.identity import azure_subscription_guid
from tools.synthetic_clouds.model.native import NativeFinding
from tools.synthetic_clouds.model.network import NetworkFlow, NetworkInterface, NetworkSegment
from tools.synthetic_clouds.model.resource import Resource
from tools.synthetic_clouds.render.azure_arm_instances import AzureArmInstancesRenderer
from tools.synthetic_clouds.render.azure_defender import AzureDefenderRenderer
from tools.synthetic_clouds.render.azure_nsg_flow_logs import AzureNsgFlowLogsRenderer
from tools.synthetic_clouds.render.azure_resource_graph import AzureResourceGraphRenderer
from tools.synthetic_clouds.render.azure_vnet_flow_logs import AzureVnetFlowLogsRenderer
from tools.synthetic_clouds.scenarios.emit import apply_all

_SPEC_DIR = DEFAULT_SPECS_ROOT / "azure"

_ARM = "arm-resource-representation.schema.json"
_RG = "azure-resource-graph-virtual-machines.schema.json"
_DEFENDER = "defender-for-cloud-continuous-export.schema.json"
_NSG = "nsg-flow-logs-v2.schema.json"
_VNET = "vnet-flow-logs.schema.json"

#: O escopo obrigatório de ``check_artifact`` em cada superfície de vários conjuntos.
_RG_VM_SCOPE = "Resources/microsoft.compute/virtualmachines"
_NSG_RECORD_SCOPE = "record"
_VNET_ANALYTICS_SCOPE = "NTANetAnalytics"
_VNET_IP_DETAILS_SCOPE = "NTAIpDetails"

#: Contagens da documentação citada, por superfície: (colunas, colunas geráveis). Uma edição da
#: spec que mude qualquer uma delas é exatamente o evento que este ficheiro existe para mostrar.
_DOCUMENTED_COUNTS = {_DEFENDER: (114, 93), _NSG: (39, 13), _VNET: (127, 7), _RG: (148, 32), _ARM: (327, 301)}

#: Colunas que a spec do ARM descreve por EXEMPLO e proíbe gerar: o corpo de resposta entregue
#: não pode carregar nenhuma delas -- nem ``tags``, que o modelo TEM, nem ``vmId``.
_ARM_EXAMPLE_ONLY = (
    "id",
    "type",
    "tags",
    "identity.principalId",
    "identity.tenantId",
    "resources",
    "properties.provisioningState",
    "properties.timeCreated",
    "properties.vmId",
    "properties.storageProfile.imageReference.exactVersion",
)

#: Conjuntos cujo conjunto de campos correto é VAZIO (todas as colunas ``example-only``/sem tipo).
_EMPTY_SCOPES = {
    _NSG: ("flowTuples-position",),
    _VNET: ("blob", "blob-envelope", "flowTuples-position"),
    _DEFENDER: ("securityresources/microsoft.security/attackpaths",),
    _RG: (
        "Resources",
        "SecurityResources/microsoft.security/locations/alerts",
        "SecurityResources/microsoft.security/iotalerts",
        "SecurityResources/microsoft.security/insights/classification",
        "SecurityResources/microsoft.security/assessments",
        "SecurityResources/microsoft.security/assessments/subassessments",
        "SecurityResources/microsoft.security/securescores",
        "SecurityResources/microsoft.security/securescores/securescorecontrols",
        "SecurityResources/microsoft.security/regulatorycompliancestandards",
        "SecurityResources/microsoft.security/regulatorycompliancestandards/regulatorycompliancecontrols/regulatorycomplianceassessments",
        "SecurityResources/microsoft.security/attackpaths",
    ),
}


# -- fixtures ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def estate() -> CanonicalEstate:
    """O estado canônico determinístico que todas as superfícies projetam."""
    return apply_all(build_estate(seed=123, profile="small", currency="USD"))


def _rendered(renderer: Any, estate: CanonicalEstate, factory: pytest.TempPathFactory) -> Path:
    """A árvore ENTREGUE por ``renderer`` (cada renderer escreve ``out_dir/<name>``)."""
    out = factory.mktemp(renderer.name)
    renderer.render(estate, out)
    target: Path = out / renderer.name
    return target


@pytest.fixture(scope="module")
def arm_dir(estate: CanonicalEstate, tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _rendered(AzureArmInstancesRenderer(), estate, tmp_path_factory)


@pytest.fixture(scope="module")
def rg_dir(estate: CanonicalEstate, tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _rendered(AzureResourceGraphRenderer(), estate, tmp_path_factory)


@pytest.fixture(scope="module")
def defender_dir(estate: CanonicalEstate, tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _rendered(AzureDefenderRenderer(), estate, tmp_path_factory)


@pytest.fixture(scope="module")
def nsg_dir(estate: CanonicalEstate, tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _rendered(AzureNsgFlowLogsRenderer(), estate, tmp_path_factory)


@pytest.fixture(scope="module")
def vnet_dir(estate: CanonicalEstate, tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _rendered(AzureVnetFlowLogsRenderer(), estate, tmp_path_factory)


# -- spec helpers (the expectation comes from the spec, never from a literal) -----------


def _spec(filename: str) -> SurfaceSpec:
    return load_spec(_SPEC_DIR / filename)


def _scope_columns(spec: SurfaceSpec, scope: str | None) -> tuple[Column, ...]:
    return spec.columns if scope is None else spec.columns_for(scope)


def _emittable(spec: SurfaceSpec, scope: str | None) -> set[str]:
    """Nomes que PERTENCEM ao formato no escopo (inclui uma coluna sempre vazia)."""
    return {column.name for column in _scope_columns(spec, scope) if column.belongs_to_schema}


def _generatable(spec: SurfaceSpec, scope: str | None) -> set[str]:
    """Nomes que podem RECEBER VALOR no escopo."""
    return {column.name for column in _scope_columns(spec, scope) if column.is_generatable}


def _non_emittable(spec: SurfaceSpec, scope: str | None) -> set[str]:
    """Nomes que o escopo descreve sem autorizar a existir no artefato."""
    return {column.name for column in _scope_columns(spec, scope) if not column.belongs_to_schema}


def _prefix_closure(spec: SurfaceSpec, scope: str | None) -> set[str]:
    """Contêineres que a spec não lista e que hospedam um caminho documentado.

    É o ÚNICO nome extra que uma projeção pode carregar: ``properties`` na tabela ``Resources``
    do Resource Graph, ``...networkInterfaces[].properties`` no ARM. O caminho de uma lista
    (``a.b[]``) é emitido pela chave do pai (``a.b``), então o prefixo é normalizado antes de
    ser comparado -- sem isso o próprio contêiner documentado apareceria como lacuna.
    """
    documented = _emittable(spec, scope)
    closure: set[str] = set()
    for path in documented:
        segments = path.split(".")
        for cut in range(1, len(segments)):
            prefix = ".".join(segments[:cut])
            emitted = prefix[:-2] if prefix.endswith("[]") else prefix
            if emitted not in documented:
                closure.add(emitted)
    return closure


def _required_not_emittable(spec: SurfaceSpec, scope: str | None) -> set[str]:
    """Colunas que a spec chama obrigatórias e ao mesmo tempo recusa gerar: residual irredutível."""
    return {column.name for column in _scope_columns(spec, scope) if column.required} - _emittable(spec, scope)


def _documented_containers(spec: SurfaceSpec, scope: str | None) -> set[str]:
    """Colunas DOCUMENTADAS que hospedam outra coluna documentada.

    O valor de um contêiner na projeção é a sua subárvore, então ele conta como "preenchido"
    mesmo quando todos os filhos saem vazios. Separar os contêineres dos campos FOLHA é o que
    permite afirmar com precisão "nenhum campo folha carrega valor".
    """
    names = _emittable(spec, scope)
    containers: set[str] = set()
    for path in names:
        segments = path.split(".")
        for cut in range(1, len(segments)):
            prefix = ".".join(segments[:cut])
            emitted = prefix[:-2] if prefix.endswith("[]") else prefix
            if emitted in names:
                containers.add(emitted)
    return containers


def _surface_emittable(spec: SurfaceSpec) -> set[str]:
    """A união dos nomes que ALGUM conjunto da superfície autoriza a existir no artefato."""
    return {column.name for column in spec.columns if column.belongs_to_schema}


def _kinds(findings: tuple[Finding, ...]) -> Counter[str]:
    return Counter(finding.kind for finding in findings)


def _of(findings: tuple[Finding, ...], kind: str) -> set[str]:
    return {finding.column for finding in findings if finding.kind == kind}


def _assert_only_the_specs_own_gaps(findings: tuple[Finding, ...], spec: SurfaceSpec, scope: str | None) -> None:
    """Uma divergência aceitável é a que a PRÓPRIA spec cria -- e só ela."""
    assert _of(findings, KIND_INVENTED) == set(), "\n".join(map(str, findings))
    assert _of(findings, KIND_MISSING) == _required_not_emittable(spec, scope), "\n".join(map(str, findings))
    assert _of(findings, KIND_UNVERIFIED) == set(), "\n".join(map(str, findings))
    assert _kinds(findings)[KIND_POPULATED_EMPTY] == 0, "\n".join(map(str, findings))


def _assert_document_is_the_spec_plus_its_containers(
    document: Path, spec: SurfaceSpec, scope: str | None
) -> None:
    """O DOCUMENTO entregue tem os caminhos da spec, e além deles só os contêineres mínimos.

    É a metade estrutural da auditoria: a projeção entregue não publica contêiner nenhum (o
    contrato não define esse nome), e é AQUI que se prova que nenhum contêiner a mais -- e
    nenhum campo inventado -- entrou no documento.
    """
    paths = _document_paths(_read(document))

    assert _emittable(spec, scope) <= paths
    assert paths - _emittable(spec, scope) == _prefix_closure(spec, scope)


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _flatten(payload: Any) -> list[dict[str, Any]]:
    """Achata um documento JSON (leitor INDEPENDENTE do renderer, mesma convenção de caminho)."""
    rows = payload if isinstance(payload, list) else [payload]
    flat: list[dict[str, Any]] = []
    for row in rows:
        fields: dict[str, Any] = {}
        _flatten_into(row, "", fields)
        flat.append(fields)
    return flat


def _flatten_into(node: Any, prefix: str, fields: dict[str, Any]) -> None:
    if not isinstance(node, dict):
        return
    for key, value in node.items():
        path = f"{prefix}{key}"
        fields[path] = value
        if isinstance(value, list):
            for item in value:
                _flatten_into(item, f"{path}[].", fields)
        else:
            _flatten_into(value, f"{path}.", fields)


def _relative(path: Path, root: Path) -> str:
    """O caminho relativo com separador POSIX (os templates documentados usam ``/``)."""
    return path.relative_to(root).as_posix()


def _document_paths(payload: Any) -> set[str]:
    """Todo caminho presente num documento (contêineres incluídos): a ESTRUTURA entregue."""
    return {name for row in _flatten(payload) for name in row}


def _projected(payload: Any, allowed: set[str]) -> list[dict[str, Any]]:
    """A projeção do documento restrita aos nomes que a spec enumera (o que o renderer entrega)."""
    return [{name: value for name, value in row.items() if name in allowed} for row in _flatten(payload)]


def _azure_vms(estate: CanonicalEstate) -> list[Resource]:
    return sorted(
        (
            resource
            for resource in estate.resources
            if resource.identity.provider == "azure" and resource.resource_type == "virtual_machine"
        ),
        key=lambda resource: (resource.parent_scope_id, resource.resource_name),
    )


def _window_hour(estate: CanonicalEstate) -> datetime:
    """A última hora da janela simulada (a hora que os dois flow logs entregam)."""
    return datetime.combine(estate.sim_now, time(23, 0), tzinfo=UTC)


# -- o modelo de rede, lido pelo teste (nunca pelo ajudante do renderer) ----------------


def _azure_flows(estate: CanonicalEstate) -> list[NetworkFlow]:
    """Os fluxos dos segmentos Azure -- a matéria-prima das duas superfícies de flow log."""
    segments = {segment.segment_uuid for segment in estate.network_segments if segment.provider == "azure"}
    return [flow for flow in estate.network_flows if flow.segment_uuid in segments]


def _azure_interfaces(estate: CanonicalEstate) -> int:
    """Quantas NICs Azure o estado carrega: é o número de blobs que cada flow log entrega."""
    segments = {segment.segment_uuid for segment in estate.network_segments if segment.provider == "azure"}
    return len([interface for interface in estate.network_interfaces if interface.segment_uuid in segments])


def _azure_segments(estate: CanonicalEstate) -> list[NetworkSegment]:
    """As VNets Azure do estado, em ordem determinística."""
    return sorted(
        (segment for segment in estate.network_segments if segment.provider == "azure"),
        key=lambda segment: segment.segment_uuid,
    )


def _azure_segment_and_interface(estate: CanonicalEstate) -> tuple[NetworkSegment, NetworkInterface]:
    """Um par (VNet, NIC) Azure determinístico, para montar um caminho esperado."""
    segments = {
        segment.segment_uuid: segment for segment in estate.network_segments if segment.provider == "azure"
    }
    interface = sorted(
        (item for item in estate.network_interfaces if item.segment_uuid in segments),
        key=lambda item: item.interface_uuid,
    )[0]
    return segments[interface.segment_uuid], interface


def _mac_wire(mac: str) -> str:
    """O MAC na forma do exemplo oficial: 12 dígitos hex em maiúsculas, sem separadores."""
    return mac.replace(":", "").replace("-", "").upper()


def _arm_token(arm_id: str, key: str) -> str:
    """O token que segue ``key`` num ARM resource id, lido pelo teste."""
    parts = [part for part in arm_id.split("/") if part]
    return parts[[part.lower() for part in parts].index(key.lower()) + 1]


def _arm_name(arm_id: str) -> str:
    return arm_id.rstrip("/").rsplit("/", 1)[-1]


def _mac_of_blob(blob: Path) -> str:
    """O MAC que a partição ``macAddress=`` do blob carrega."""
    return next(part.split("=", 1)[1] for part in blob.parts if part.startswith("macAddress="))


def _segment_of_blob(blob: Path, segments: Mapping[str, NetworkSegment]) -> NetworkSegment:
    """A VNet/NSG do blob, pelo nome da NSG que o caminho carrega."""
    name = blob.parts[blob.parts.index("NETWORKSECURITYGROUPS") + 1]
    for segment in segments.values():
        arm_id = segment.network_security_group_id or segment.segment_id
        if _arm_name(arm_id) == name:
            return segment
    raise AssertionError(f"nenhum segmento do estado responde pela NSG {name!r}")


def _parse_seven_digit_utc(text: str) -> datetime:
    """Lê a forma documentada ``...T23:00:00.0000000Z`` (7 dígitos fracionários + ``Z``)."""
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%S.%f0Z").replace(tzinfo=UTC)


def _flows_touching(estate: CanonicalEstate, interface_uuid: str) -> list[NetworkFlow]:
    """Os fluxos Azure que tocam a interface (por qualquer das pontas)."""
    return [
        flow
        for flow in _azure_flows(estate)
        if interface_uuid in (flow.src_interface_uuid, flow.dst_interface_uuid)
    ]


def _find_flow(candidates: Sequence[NetworkFlow], start: datetime, positions: Sequence[str]) -> NetworkFlow:
    """O fluxo do modelo que a tupla descreve, pela janela e pela 5-tupla.

    A busca exige UM candidato só: se dois fluxos do modelo coubessem na mesma tupla, o
    artefato não estaria descrevendo um fluxo -- e o teste falha em vez de escolher um.
    """
    found = [
        flow
        for flow in candidates
        if flow.window_start == start
        and flow.src_ip == positions[1]
        and flow.dst_ip == positions[2]
        and str(flow.src_port) == positions[3]
        and str(flow.dst_port) == positions[4]
    ]
    assert len(found) == 1, f"a tupla {positions} casa com {len(found)} fluxos do modelo"
    return found[0]


def _observer_uuid(flow: NetworkFlow) -> str | None:
    """A NIC que coletou o fluxo: origem em egress, destino em ingress (a derivação do renderer)."""
    return flow.src_interface_uuid if flow.direction == "egress" else flow.dst_interface_uuid


def _nsg_projection_name(blob: Path) -> str:
    """O nome do arquivo de projeção irmão de um blob (os quatro eixos do caminho, sem barras)."""
    subscription = blob.parts[blob.parts.index("SUBSCRIPTIONS") + 1]
    nsg = blob.parts[blob.parts.index("NETWORKSECURITYGROUPS") + 1]
    year = next(part.split("=", 1)[1] for part in blob.parts if part.startswith("y="))
    month = next(part.split("=", 1)[1] for part in blob.parts if part.startswith("m=") and part != "m=00")
    day = next(part.split("=", 1)[1] for part in blob.parts if part.startswith("d="))
    hour = next(part.split("=", 1)[1] for part in blob.parts if part.startswith("h="))
    return f"{subscription}_{nsg}_{_mac_of_blob(blob)}_{year}{month}{day}T{hour}.json"


def _vnet_projection_name(blob: Path) -> str:
    """O nome do arquivo de projeção irmão de um blob de VNet flow log."""
    subscription = blob.parts[blob.parts.index("flowLogResourceID=") + 1].replace("_NETWORKWATCHERRG", "")
    return f"blob_{subscription}_{_mac_of_blob(blob)}.json"


def _arm_document(arm_dir: Path, estate: CanonicalEstate, resource: Resource) -> Path:
    subscription = azure_subscription_guid(estate.seed, resource.parent_scope_id)
    return (
        arm_dir
        / "subscriptions"
        / subscription
        / "resourceGroups"
        / "{resourceGroupName}"
        / "providers"
        / "Microsoft.Compute"
        / "virtualMachines"
        / f"{resource.resource_name}.json"
    )


def _arm_projection(arm_dir: Path, estate: CanonicalEstate, resource: Resource) -> Path:
    subscription = azure_subscription_guid(estate.seed, resource.parent_scope_id)
    return arm_dir / "field_projection" / f"{subscription}__{resource.resource_name}.json"


# -- the specs themselves ---------------------------------------------------------------


@pytest.mark.parametrize("filename", sorted(_DOCUMENTED_COUNTS))
def test_the_five_specs_have_the_documented_size(filename: str) -> None:
    """As contagens citadas (114/93, 39/13, 127/7, 148/32, 327/301) são o contrato auditado."""
    spec = _spec(filename)
    columns, generatable = _DOCUMENTED_COUNTS[filename]

    assert len(spec.columns) == columns, filename
    assert spec.generatable_count == generatable, filename


@pytest.mark.parametrize("filename", [_DEFENDER, _NSG, _VNET, _RG])
def test_a_multi_set_surface_refuses_an_unqualified_comparison(filename: str) -> None:
    """Sem ``scope``, comparar contra a união de contratos disjuntos acusaria ausência falsa."""
    spec = _spec(filename)

    assert len(spec.set_names) > 1
    with pytest.raises(ScopeError, match="conjuntos"):
        check(spec, [])
    # O ARM é o único de conjunto anônimo: o escopo não existe e não pode ser exigido.
    assert _spec(_ARM).set_names == ()


def test_every_set_without_a_published_shape_has_an_empty_field_set() -> None:
    """Os escopos cujo artefato correto é vazio não autorizam NENHUM nome."""
    for filename, scopes in _EMPTY_SCOPES.items():
        spec = _spec(filename)
        for scope in scopes:
            findings = check(spec, [], scope=scope)
            assert _emittable(spec, scope) == set(), (filename, scope)
            assert _of(findings, KIND_INVENTED) == set(), (filename, scope)
            assert _of(findings, KIND_UNVERIFIED) == set(), (filename, scope)
            assert _of(findings, KIND_MISSING) == _required_not_emittable(spec, scope), (filename, scope)


# =======================================================================================
# ARM resource representation (instances)
# =======================================================================================


def test_arm_delivers_one_response_body_per_azure_vm(arm_dir: Path, estate: CanonicalEstate) -> None:
    documents = sorted(arm_dir.glob("subscriptions/*/resourceGroups/{resourceGroupName}/providers/Microsoft.Compute/virtualMachines/*.json"))

    assert len(documents) == len(_azure_vms(estate))
    assert {document.name for document in documents} == {f"{resource.resource_name}.json" for resource in _azure_vms(estate)}


def test_arm_response_path_is_the_documented_get_endpoint(arm_dir: Path, estate: CanonicalEstate) -> None:
    """O caminho entregue é o do ENDPOINT documentado, com o token do template no que falta."""
    resource = _azure_vms(estate)[0]
    subscription = azure_subscription_guid(estate.seed, resource.parent_scope_id)
    expected = (
        f"azure_arm_instances/subscriptions/{subscription}"
        f"/resourceGroups/{{resourceGroupName}}/providers/Microsoft.Compute"
        f"/virtualMachines/{resource.resource_name}.json"
    )

    assert _relative(_arm_document(arm_dir, estate, resource), arm_dir.parent) == expected


def test_arm_document_carries_exactly_the_documented_properties(arm_dir: Path, estate: CanonicalEstate) -> None:
    """301 colunas geráveis no documento e na projeção: nem uma a menos, nem um contêiner a mais."""
    spec = _spec(_ARM)
    resource = _azure_vms(estate)[0]
    projection = _arm_projection(arm_dir, estate, resource)

    _assert_only_the_specs_own_gaps(check_artifact(spec, projection), spec, None)
    assert len(_emittable(spec, None)) == 301

    assert set(columns_of(projection)) == _emittable(spec, None)
    assert set(populated_of(projection)) <= _generatable(spec, None)
    _assert_document_is_the_spec_plus_its_containers(_arm_document(arm_dir, estate, resource), spec, None)


def test_arm_required_column_is_present(arm_dir: Path, estate: CanonicalEstate) -> None:
    """``createOption`` é a única coluna obrigatória da spec, e o residual obrigatório é vazio."""
    projection = _arm_projection(arm_dir, estate, _azure_vms(estate)[0])

    assert "properties.storageProfile.dataDisks[].createOption" in set(columns_of(projection))
    assert _required_not_emittable(_spec(_ARM), None) == set()


def test_arm_example_only_columns_are_never_emitted(arm_dir: Path, estate: CanonicalEstate) -> None:
    """O que a spec descreve por exemplo não entra: sem id, sem tags, sem vmId, sem estado."""
    spec = _spec(_ARM)
    forbidden = _non_emittable(spec, None)
    projection = _arm_projection(arm_dir, estate, _azure_vms(estate)[0])

    assert set(_ARM_EXAMPLE_ONLY) <= forbidden
    assert set(columns_of(projection)) & forbidden == set()
    assert set(populated_of(projection)) & forbidden == set()


def test_arm_model_values_are_projected(arm_dir: Path, estate: CanonicalEstate) -> None:
    """Nome, região, tamanho e NIC da VM saem do modelo -- e o resto sai VAZIO, nunca plausível."""
    resource = _azure_vms(estate)[0]
    row = _read(_arm_projection(arm_dir, estate, resource))[0]
    interface = next(item for item in estate.network_interfaces if item.resource_uuid == resource.identity.uuid)

    assert row["name"] == resource.resource_name
    assert row["location"] == resource.region_id
    assert row["properties.hardwareProfile.vmSize"] == resource.sku_id
    # A NIC da VM: o modelo de rede liga interface e recurso, então a lista não sai vazia.
    assert row["properties.networkProfile.networkInterfaces[].id"] == interface.interface_id
    assert row["properties.storageProfile.osDisk.osType"] is None
    assert row["properties.osProfile.adminUsername"] is None
    # ``tags`` existe no modelo, mas a spec só o descreve por exemplo: não pode ser emitido.
    assert "tags" not in row


def test_arm_projection_is_the_delivered_document_flattened(arm_dir: Path, estate: CanonicalEstate) -> None:
    spec = _spec(_ARM)
    resource = _azure_vms(estate)[0]

    assert _read(_arm_projection(arm_dir, estate, resource)) == _projected(
        _read(_arm_document(arm_dir, estate, resource)), _emittable(spec, None)
    )


# =======================================================================================
# Azure Resource Graph (query response)
# =======================================================================================


def test_resource_graph_response_is_the_object_array_result(rg_dir: Path, estate: CanonicalEstate) -> None:
    """O formato entregue é ``ObjectArray``: um array de linhas, uma por VM, sem envelope."""
    rows = _read(rg_dir / "virtualmachines_objectarray.json")

    assert isinstance(rows, list)
    assert len(rows) == len(_azure_vms(estate))
    # Um envelope (``count``/``totalRecords``/``skipToken``) é campo de NENHUM conjunto da spec.
    assert {key for row in rows for key in row} == {"properties"}


def test_resource_graph_vm_scope_carries_exactly_the_documented_paths(rg_dir: Path) -> None:
    spec = _spec(_RG)
    projection = rg_dir / "field_projection" / "virtualmachines.json"

    _assert_only_the_specs_own_gaps(check_artifact(spec, projection, scope=_RG_VM_SCOPE), spec, _RG_VM_SCOPE)
    assert len(_emittable(spec, _RG_VM_SCOPE)) == 32

    assert set(columns_of(projection)) == _emittable(spec, _RG_VM_SCOPE)
    assert set(populated_of(projection)) <= _generatable(spec, _RG_VM_SCOPE)
    _assert_document_is_the_spec_plus_its_containers(
        rg_dir / "virtualmachines_objectarray.json", spec, _RG_VM_SCOPE
    )


def test_resource_graph_vm_identity_survives_as_the_documented_vm_id(rg_dir: Path, estate: CanonicalEstate) -> None:
    """``properties.vmId`` é o único campo de identidade que a spec autoriza -- a chave de junção."""
    rows = _read(rg_dir / "field_projection" / "virtualmachines.json")
    vms = _azure_vms(estate)
    interfaces = {item.resource_uuid: item for item in estate.network_interfaces}
    segments = {segment.segment_uuid: segment for segment in estate.network_segments}

    assert [row["properties.vmId"] for row in rows] == [resource.identity.uuid for resource in vms]
    assert [row["properties.hardwareProfile.vmSize"] for row in rows] == [resource.sku_id for resource in vms]
    # A NIC e o resource group dela vêm do modelo de rede: a linha nomeia a interface da VM.
    # Um recurso acrescentado por CENÁRIO não está no inventário de rede (a rede é construída
    # dentro do build, antes da emissão dos cenários), então a lista sai vazia para ele --
    # ausência é ausência, nunca um id inventado, e o relatório de proveniência registra a lacuna.
    with_interface = 0
    for row, resource in zip(rows, vms, strict=True):
        interface = interfaces.get(resource.identity.uuid)
        if interface is None:
            assert row["properties.networkProfile.networkInterfaces[].id"] is None
            continue
        assert row["properties.networkProfile.networkInterfaces[].id"] == interface.interface_id
        assert (
            row["properties.networkProfile.networkInterfaces[].resourceGroup"]
            == segments[interface.segment_uuid].resource_group
        )
        with_interface += 1
    vms_with_nic = len(
        [item for item in estate.network_interfaces if item.resource_uuid in {r.identity.uuid for r in vms}]
    )
    assert with_interface == vms_with_nic, "toda VM que TEM NIC a projeta no artefato"
    # O estado não modela estado de provisionamento: a coluna sai vazia, não "Succeeded".
    assert all(row["properties.provisioningState"] is None for row in rows)


def test_resource_graph_projection_is_the_delivered_response_flattened(rg_dir: Path) -> None:
    spec = _spec(_RG)

    assert _read(rg_dir / "field_projection" / "virtualmachines.json") == _projected(
        _read(rg_dir / "virtualmachines_objectarray.json"), _emittable(spec, _RG_VM_SCOPE)
    )


@pytest.mark.parametrize("scope", _EMPTY_SCOPES[_RG])
def test_resource_graph_sets_without_a_published_shape_are_not_emitted(rg_dir: Path, scope: str) -> None:
    """Um conjunto ``example-only`` não gera artefato: nenhum nome dele sai na projeção."""
    spec = _spec(_RG)
    emitted = {name for path in rg_dir.glob("field_projection/*.json") for name in columns_of(path)}

    assert _emittable(spec, scope) == set()
    assert emitted == _emittable(spec, _RG_VM_SCOPE)
    assert emitted <= _surface_emittable(spec)


# =======================================================================================
# Defender for Cloud continuous export (security)
# =======================================================================================


def test_defender_alert_table_is_faithful(defender_dir: Path) -> None:
    """``SecurityAlert``: 35 colunas documentadas, nenhuma ausente, nenhuma inventada."""
    spec = _spec(_DEFENDER)
    path = defender_dir / "SecurityAlert.json"
    findings = check_artifact(spec, path, scope="SecurityAlert")

    assert is_faithful(findings), "\n".join(map(str, findings))
    assert set(columns_of(path)) == {column.name for column in spec.columns_for("SecurityAlert")}
    assert set(populated_of(path)) <= {column.name for column in spec.columns_for("SecurityAlert") if column.is_generatable}


def test_defender_recommendation_table_is_faithful(defender_dir: Path) -> None:
    """``SecurityRecommendation``: 23 colunas documentadas, nenhuma ausente, nenhuma inventada."""
    spec = _spec(_DEFENDER)
    path = defender_dir / "SecurityRecommendation.json"

    assert is_faithful(check_artifact(spec, path, scope="SecurityRecommendation"))
    assert set(columns_of(path)) == {column.name for column in spec.columns_for("SecurityRecommendation")}


def test_defender_alert_values_come_from_the_azure_findings(defender_dir: Path, estate: CanonicalEstate) -> None:
    """Um registo por achado Azure; identidade, nome, descrição, procedência e instante vêm do modelo."""
    records = _read(defender_dir / "SecurityAlert.json")
    findings = sorted(
        (finding for finding in estate.findings if finding.provider == "azure"),
        key=lambda finding: finding.finding_id,
    )

    assert [record["SystemAlertId"] for record in records] == [finding.finding_id for finding in findings]
    assert all(record["Type"] == "SecurityAlert" for record in records)
    assert all(record["ProductName"] == "Azure Security Center" for record in records)
    # Nome, descrição e procedência: campos NEUTROS que o modelo passou a carregar.
    assert [record["AlertName"] for record in records] == [finding.title for finding in findings]
    assert [record["DisplayName"] for record in records] == [finding.title for finding in findings]
    assert [record["Description"] for record in records] == [finding.description for finding in findings]
    assert [record["VendorName"] for record in records] == [finding.company_name for finding in findings]
    # ``TimeGenerated`` é o instante OBSERVADO (com fuso), não a meia-noite do dia: o valor
    # entregue é o mesmo que o gate valida no modelo.
    assert [record["TimeGenerated"] for record in records] == [
        _observation_instant_for(finding) for finding in findings
    ]
    assert all(record["TimeGenerated"].endswith("Z") for record in records)
    # A gravidade é normalizada para os literais documentados; CRITICAL não tem correspondente
    # publicado e fica VAZIO -- nenhum literal é inventado para ele.
    assert {record["AlertSeverity"] for record in records} <= {"High", "Medium", "Low", None}
    assert all(record["AlertSeverity"] != "CRITICAL" for record in records)
    # O que o modelo TEM e a Microsoft NÃO publica fica vazio: nada é preenchido por analogia
    # com o ASFF (``types``, ``confidence``), e ``ProviderName`` é documentado como unused.
    for record in records:
        assert record["AlertType"] is None
        assert record["ConfidenceScore"] is None
        assert record["ConfidenceLevel"] is None
        assert record["ProviderName"] is None
    # A chave de junção da tabela é um ARM resource id, que o modelo não carrega: sai vazia.
    assert all(record["ResourceId"] is None for record in records)
    # Os sacos de marcadores FinOps (``synthetic``/``rule``/``kind``) não são colunas do
    # Defender: não são espalhados em campo nenhum.
    assert all("synthetic" not in json.dumps(record) for record in records)


def test_defender_recommendation_values_come_from_the_azure_recommendations(
    defender_dir: Path, estate: CanonicalEstate
) -> None:
    records = _read(defender_dir / "SecurityRecommendation.json")
    recommendations = sorted(
        (item for item in estate.recommendations if item.provider == "azure"),
        key=lambda item: item.recommendation_id,
    )

    assert [record["RecommendationId"] for record in records] == [item.recommendation_id for item in recommendations]
    assert all(record["Type"] == "SecurityRecommendation" for record in records)
    assert all(record["TimeGenerated"] == f"{estate.sim_now.isoformat()}T00:00:00Z" for record in records)
    # O vocabulário do modelo (``rightsize``/``idle``/``sku_change``) não é um display name
    # publicado, e a recomendação não carrega estado: ambos saem VAZIOS.
    assert all(record["RecommendationDisplayName"] is None for record in records)
    assert all(record["RecommendationState"] is None for record in records)


def test_defender_automation_resource_has_the_documented_shape_and_no_value(defender_dir: Path) -> None:
    """A configuração da exportação existe na forma documentada; nenhum valor é modelado."""
    spec = _spec(_DEFENDER)
    scope = "Microsoft.Security/automations"
    projection = defender_dir / "field_projection" / "Microsoft.Security_automations.json"

    _assert_only_the_specs_own_gaps(check_artifact(spec, projection, scope=scope), spec, scope)
    assert set(columns_of(projection)) == _emittable(spec, scope)
    # Nenhum CAMPO FOLHA carrega valor: os únicos nomes "preenchidos" são contêineres, cujo valor
    # na projeção é a própria subárvore. Preencher ``actionType`` afirmaria uma configuração que
    # ninguém modelou.
    assert set(populated_of(projection)) <= _documented_containers(spec, scope)
    _assert_document_is_the_spec_plus_its_containers(
        defender_dir / "Microsoft.Security_automations.json", spec, scope
    )


def test_defender_projection_is_the_delivered_document_flattened(defender_dir: Path) -> None:
    spec = _spec(_DEFENDER)
    scope = "Microsoft.Security/automations"

    assert _read(defender_dir / "field_projection" / "Microsoft.Security_automations.json") == _projected(
        _read(defender_dir / "Microsoft.Security_automations.json"), _emittable(spec, scope)
    )


def test_defender_attack_paths_set_has_no_artifact(defender_dir: Path) -> None:
    """O conjunto de attack path é ``author-classification`` em todas as colunas: nada é emitido."""
    spec = _spec(_DEFENDER)
    scope = "securityresources/microsoft.security/attackpaths"
    projections = {name for path in defender_dir.glob("field_projection/*.json") for name in columns_of(path)}
    tables = {
        name
        for path in (defender_dir / "SecurityAlert.json", defender_dir / "SecurityRecommendation.json")
        for name in columns_of(path)
    }

    assert is_faithful(check(spec, [], scope=scope))
    assert _emittable(spec, scope) == set()
    # Nada na rede sai da união dos nomes que ALGUM conjunto desta superfície autoriza -- e o
    # conjunto de attack path não autoriza nenhum.
    assert projections | tables <= _surface_emittable(spec)


def test_defender_writes_no_storage_container(defender_dir: Path) -> None:
    """Azure Storage NÃO é destino documentado: a entrega é o registo JSON, não um blob."""
    directories = {path.name for path in defender_dir.iterdir() if path.is_dir()}
    files = sorted(path.name for path in defender_dir.iterdir() if path.is_file())

    assert directories == {"field_projection"}
    assert files == [
        "Microsoft.Security_automations.json",
        "SecurityAlert.json",
        "SecurityRecommendation.json",
        "_provenance.json",
    ]
    assert not any("insights-logs" in part for path in defender_dir.rglob("*") for part in path.parts)


# =======================================================================================
# NSG flow logs v2 (network) — a real blob on the documented partition
# =======================================================================================


def test_nsg_blob_lands_on_the_documented_partition(nsg_dir: Path, estate: CanonicalEstate) -> None:
    """Cada segmento do caminho é o do template oficial E tem o valor do modelo de rede."""
    segment, interface = _azure_segment_and_interface(estate)
    nsg_id = segment.network_security_group_id or segment.segment_id
    moment = _window_hour(estate)
    expected = "/".join(
        [
            "azure_nsg_flow_logs",
            "insights-logs-networksecuritygroupflowevent",
            "resourceId=",
            "SUBSCRIPTIONS",
            _arm_token(nsg_id, "subscriptions"),
            "RESOURCEGROUPS",
            segment.resource_group or "",
            "PROVIDERS",
            "MICROSOFT.NETWORK",
            "NETWORKSECURITYGROUPS",
            _arm_name(nsg_id),
            f"y={moment.year}",
            f"m={moment.month:02d}",
            f"d={moment.day:02d}",
            f"h={moment.hour:02d}",
            "m=00",
            f"macAddress={_mac_wire(interface.mac_address)}",
            "PT1H.json",
        ]
    )
    blobs = sorted(nsg_dir.rglob("PT1H.json"))

    assert len(blobs) == _azure_interfaces(estate), "um blob por NIC Azure que coletou fluxo"
    assert expected in {_relative(blob, nsg_dir.parent) for blob in blobs}
    # Nenhum segmento do caminho ficou com o token do template: o modelo tem todos os valores.
    assert not any("{" in part for blob in blobs for part in blob.parts)


def test_nsg_record_scope_carries_exactly_the_documented_members(nsg_dir: Path) -> None:
    """Os 13 membros JSON do registo: os nomes de posição do CSV são irredutivelmente ausentes."""
    spec = _spec(_NSG)
    projection = sorted(nsg_dir.glob("field_projection/*.json"))[0]
    findings = check_artifact(spec, projection, scope=_NSG_RECORD_SCOPE)

    _assert_only_the_specs_own_gaps(findings, spec, _NSG_RECORD_SCOPE)
    assert _of(findings, KIND_MISSING) == _required_not_emittable(spec, _NSG_RECORD_SCOPE)
    assert len(_of(findings, KIND_MISSING)) == 9
    assert set(columns_of(projection)) == _emittable(spec, _NSG_RECORD_SCOPE)


def test_nsg_system_id_is_the_nsg_guid_and_not_the_subscription(
    nsg_dir: Path, estate: CanonicalEstate
) -> None:
    """``systemId`` é o GUID da NSG: projetar a assinatura ali seria mentir (e o modelo tem os dois)."""
    segments = {segment.segment_uuid: segment for segment in estate.network_segments}
    checked = 0
    for blob in sorted(nsg_dir.rglob("PT1H.json")):
        records = _read(blob)["records"]
        assert records, blob
        for record in records:
            segment = _segment_of_blob(blob, segments)
            assert record["systemId"] == segment.network_security_group_uuid
            assert record["systemId"] != segment.scope_id
            assert record["resourceId"] == segment.network_security_group_id
            checked += 1

    assert checked == len(list(nsg_dir.rglob("PT1H.json"))) * 12


def test_nsg_flow_tuples_come_from_the_modelled_flows(nsg_dir: Path, estate: CanonicalEstate) -> None:
    """Cada tupla entregue é o fluxo do modelo, posição a posição, na ordem que a spec fixa.

    Este é o golden que o modelo de rede torna possível: o artefato deixou de ser formato vazio
    e passou a carregar as 13 posições do CSV. A comparação é feita POSIÇÃO A POSIÇÃO contra o
    fluxo do estado -- não contra o ajudante do renderer --, então um erro de conversão
    (protocolo, direção, decisão, unidade do epoch, contador do estado ``B``) falha aqui.
    """
    interfaces_by_mac = {_mac_wire(item.mac_address): item for item in estate.network_interfaces}
    touching = {
        mac: _flows_touching(estate, interface.interface_uuid) for mac, interface in interfaces_by_mac.items()
    }
    tuples_checked = 0
    empty_counters = 0
    for blob in sorted(nsg_dir.rglob("PT1H.json")):
        mac = _mac_of_blob(blob)
        interface = interfaces_by_mac[mac]
        for record in _read(blob)["records"]:
            start = _parse_seven_digit_utc(record["time"])
            group = record["properties"]["flows"][0]["flows"][0]
            assert group["mac"] == mac
            for raw in group["flowTuples"]:
                positions = raw.split(",")
                assert len(positions) == 13, raw
                flow = _find_flow(touching[mac], start, positions)
                # A atribuição do MAC é a do renderer, e o teste a CONFERE: a NIC do grupo é a
                # ponta local que a direção do fluxo implica (origem em egress, destino em ingress).
                assert _observer_uuid(flow) == interface.interface_uuid
                assert positions[0] == str(int(flow.window_start.timestamp())), "epoch em SEGUNDOS"
                assert positions[1] == flow.src_ip
                assert positions[2] == flow.dst_ip
                assert positions[3] == str(flow.src_port)
                assert positions[4] == str(flow.dst_port)
                assert positions[5] == {6: "T", 17: "U"}.get(flow.protocol_number, "")
                assert positions[6] == {"ingress": "I", "egress": "O"}[flow.direction]
                assert positions[7] == {"allowed": "A", "denied": "D"}[flow.decision]
                assert positions[8] == flow.flow_state
                if flow.flow_state == "B":
                    # "Statistics aren't provided" no estado Begin: as quatro posições saem vazias.
                    assert positions[9:] == ["", "", "", ""]
                    empty_counters += 1
                else:
                    assert positions[9:] == [
                        str(flow.packets),
                        str(flow.bytes),
                        str(flow.packets_reverse),
                        str(flow.bytes_reverse),
                    ]
                tuples_checked += 1

    assert tuples_checked == len(_azure_flows(estate)), "um tuplo por fluxo Azure"
    assert empty_counters > 0, "o estado B tem de aparecer: e ele que zera os contadores"


def test_nsg_rule_stays_empty_because_the_model_has_no_rule_identity(nsg_dir: Path) -> None:
    """O modelo não carrega identidade de regra: o campo existe e sai VAZIO, nunca derivado."""
    spec = _spec(_NSG)
    records = [
        record for blob in nsg_dir.rglob("PT1H.json") for record in _read(blob)["records"]
    ]

    assert "records[].properties.flows[].rule" in _emittable(spec, _NSG_RECORD_SCOPE)
    assert all(record["properties"]["flows"][0]["rule"] is None for record in records)


def test_nsg_csv_positions_are_never_emitted_as_fields(nsg_dir: Path) -> None:
    """As 13 posições do CSV ``flowTuples`` não são campos do ficheiro -- elas vivem na string."""
    spec = _spec(_NSG)
    scope = "flowTuples-position"
    emitted = {name for path in nsg_dir.rglob("*.json") for name in columns_of(path)}

    assert emitted & {column.name for column in spec.columns_for(scope)} == set()
    assert _required_not_emittable(spec, scope) == _of(check(spec, [], scope=scope), KIND_MISSING)


def test_nsg_blob_has_one_record_per_flow_window(nsg_dir: Path, estate: CanonicalEstate) -> None:
    """O grão do documento: um registo por janela de fluxo da NIC, com o seu próprio instante."""
    windows = sorted({flow.window_start for flow in _azure_flows(estate)})
    for blob in sorted(nsg_dir.rglob("PT1H.json")):
        records = _read(blob)["records"]

        assert len(records) == len(windows)
        assert [_parse_seven_digit_utc(record["time"]) for record in records] == windows
        assert all(record["properties"]["Version"] == 2 for record in records)
        assert all(record["category"] == "NetworkSecurityGroupFlowEvent" for record in records)
        assert all(record["operationName"] == "NetworkSecurityGroupFlowEvents" for record in records)


def test_nsg_projection_is_the_delivered_blob_flattened(nsg_dir: Path) -> None:
    spec = _spec(_NSG)
    blobs = sorted(nsg_dir.rglob("PT1H.json"))
    projections = sorted(nsg_dir.glob("field_projection/*.json"))

    assert len(projections) == len(blobs)
    for blob in blobs:
        projection = nsg_dir / "field_projection" / _nsg_projection_name(blob)
        assert _read(projection) == _projected(_read(blob), _emittable(spec, _NSG_RECORD_SCOPE))
        _assert_document_is_the_spec_plus_its_containers(blob, spec, _NSG_RECORD_SCOPE)


# =======================================================================================
# Virtual network flow logs (network) — a blob AND two Log Analytics tables
# =======================================================================================


def test_vnet_blob_lands_on_the_documented_partition(vnet_dir: Path, estate: CanonicalEstate) -> None:
    """O caminho tem os valores que o modelo carrega; só o nome do ``FlowLog`` fica por derivar."""
    segment, interface = _azure_segment_and_interface(estate)
    moment = _window_hour(estate)
    expected = "/".join(
        [
            "azure_vnet_flow_logs",
            "insights-logs-flowlogflowevent",
            "flowLogResourceID=",
            f"{_arm_token(segment.segment_id, 'subscriptions')}_NETWORKWATCHERRG",
            # O terceiro segmento é o nome do recurso ``FlowLog``; a spec registra a derivação
            # dele como UNVERIFIED e nenhuma entidade do estado o modela -- então ele mantém o
            # token do template em vez de ser preenchido pela metade.
            "NETWORKWATCHER_{Region}_{ResourceName}-{ResourceGroupName}-FLOWLOGS",
            f"y={moment.year}",
            f"m={moment.month:02d}",
            f"d={moment.day:02d}",
            f"h={moment.hour:02d}",
            "m=00",
            f"macAddress={_mac_wire(interface.mac_address)}",
            "PT1H.json",
        ]
    )
    blobs = sorted(vnet_dir.rglob("PT1H.json"))

    assert len(blobs) == _azure_interfaces(estate), "um blob por NIC Azure do estado"
    assert expected in {_relative(blob, vnet_dir.parent) for blob in blobs}
    assert all(_mac_of_blob(blob) in {_mac_wire(item.mac_address) for item in estate.network_interfaces} for blob in blobs)


def test_vnet_blob_carries_no_field_because_no_set_publishes_one(vnet_dir: Path) -> None:
    """Nenhuma coluna dos conjuntos do blob pertence ao formato: o documento entregue é vazio."""
    spec = _spec(_VNET)
    blob = sorted(vnet_dir.rglob("PT1H.json"))[0]
    projection = sorted(vnet_dir.glob("field_projection/blob_*.json"))[0]
    findings = check_artifact(spec, projection, scope="blob-envelope")

    assert _read(blob) == {}
    _assert_only_the_specs_own_gaps(findings, spec, "blob-envelope")
    assert len(_of(findings, KIND_MISSING)) == 15
    assert columns_of(projection) == ()


def test_vnet_analytics_table_carries_exactly_the_documented_columns(vnet_dir: Path, estate: CanonicalEstate) -> None:
    """``NTANetAnalytics``: 5 nomes geráveis; as 57 colunas de fluxo não têm contrato.

    As duas colunas que significam "primeira/última ocorrência do fluxo no intervalo" passaram a
    ter valor quando o modelo de rede passou a ter fluxo -- e o valor é o do modelo, não um
    palpite: o mínimo dos inícios e o máximo dos fins das janelas daquela VNet.
    """
    spec = _spec(_VNET)
    path = vnet_dir / "NTANetAnalytics.json"
    start = _window_hour(estate)
    end = start + timedelta(hours=1)
    findings = check_artifact(spec, path, scope=_VNET_ANALYTICS_SCOPE)
    flows = _azure_flows(estate)

    _assert_only_the_specs_own_gaps(findings, spec, _VNET_ANALYTICS_SCOPE)
    assert len(_of(findings, KIND_MISSING)) == 57
    assert set(columns_of(path)) == _emittable(spec, _VNET_ANALYTICS_SCOPE)
    assert set(populated_of(path)) == _generatable(spec, _VNET_ANALYTICS_SCOPE), "as 5, e só as 5"

    rows = _read(path)
    assert len(rows) == len(_azure_segments(estate)), "uma linha agregada por VNet"
    assert {row["FlowIntervalStartTime"] for row in rows} == {start.strftime("%Y-%m-%dT%H:%M:%SZ")}
    assert {row["FlowIntervalEndTime"] for row in rows} == {end.strftime("%Y-%m-%dT%H:%M:%SZ")}
    assert {row["TimeProcessed"] for row in rows} == {end.strftime("%Y-%m-%dT%H:%M:%SZ")}
    assert {row["FlowStartTime"] for row in rows} == {
        min(flow.window_start for flow in flows).strftime("%Y-%m-%dT%H:%M:%SZ")
    }
    assert {row["FlowEndTime"] for row in rows} == {
        max(flow.window_end for flow in flows).strftime("%Y-%m-%dT%H:%M:%SZ")
    }


def test_vnet_column_cap_is_the_specs_and_not_the_models(vnet_dir: Path, estate: CanonicalEstate) -> None:
    """O teto de colunas do VNet é da SPEC: com 612 fluxos no modelo, nenhuma coluna de fluxo entra.

    A distinção importa e é o que este teste fixa: ``example-only`` (sem tipo publicado) não vira
    coluna gerável só porque o dado passou a existir. O modelo de rede mudou o que pode ser
    PREENCHIDO dentro das 5+2 colunas geráveis -- e mais nada.
    """
    spec = _spec(_VNET)
    flows = _azure_flows(estate)
    analytics = {name for row in _read(vnet_dir / "NTANetAnalytics.json") for name in row}

    assert len(flows) > 0, "o modelo de rede precisa ter fluxo para o teste nao ser vazio"
    assert len(flows) == _azure_interfaces(estate) * 12
    # 62 - 5 = 57 colunas da tabela agregada que o contrato recusa, mesmo com fluxo de sobra.
    assert len(_non_emittable(spec, _VNET_ANALYTICS_SCOPE)) == 57
    assert len(_non_emittable(spec, _VNET_IP_DETAILS_SCOPE)) == 12
    assert len(_emittable(spec, "blob")) == 0
    assert analytics == _emittable(spec, _VNET_ANALYTICS_SCOPE)
    # Nenhuma coluna de FLUXO (IP, porta, protocolo, direção, decisão, contador) saiu preenchida.
    assert not {"SrcIp", "DestIp", "DestPort", "L4Protocol", "FlowDirection", "FlowStatus"} & analytics
    assert "aggregated_flows" in _read(vnet_dir / "_provenance.json")["counts"]


def test_vnet_ip_details_table_carries_exactly_the_documented_columns(vnet_dir: Path) -> None:
    spec = _spec(_VNET)
    path = vnet_dir / "NTAIpDetails.json"

    _assert_only_the_specs_own_gaps(check_artifact(spec, path, scope=_VNET_IP_DETAILS_SCOPE), spec, _VNET_IP_DETAILS_SCOPE)
    assert set(columns_of(path)) == _emittable(spec, _VNET_IP_DETAILS_SCOPE)
    assert populated_of(path) == ("FlowIntervalStartTime", "FlowIntervalEndTime")


def test_vnet_flow_tuple_positions_are_never_emitted_as_fields(vnet_dir: Path) -> None:
    spec = _spec(_VNET)
    scope = "flowTuples-position"
    emitted = {name for path in vnet_dir.rglob("*.json") for name in columns_of(path)}

    assert emitted & {column.name for column in spec.columns_for(scope)} == set()
    assert _required_not_emittable(spec, scope) == _of(check(spec, [], scope=scope), KIND_MISSING)


def test_vnet_storage_blob_and_analytics_table_are_two_distinct_schemas(vnet_dir: Path) -> None:
    """A documentação avisa que o blob e a tabela agregada são esquemas DIFERENTES.

    O artefato tem de mostrar essa distinção: o blob não carrega nome nenhum (mesmo com fluxo no
    modelo) e a tabela do Log Analytics carrega os cinco nomes que a documentação tipifica.
    Confundir os dois -- o blob com os nomes da tabela, ou a tabela com o envelope do blob -- é o
    defeito que este teste torna impossível.
    """
    blob = _read(sorted(vnet_dir.rglob("PT1H.json"))[0])
    rows = _read(vnet_dir / "NTANetAnalytics.json")

    assert blob == {}
    assert set(rows[0]) == {
        "TimeProcessed",
        "FlowIntervalStartTime",
        "FlowIntervalEndTime",
        "FlowStartTime",
        "FlowEndTime",
    }
    assert "FlowIntervalStartTime" not in blob


def test_vnet_projection_is_the_delivered_blob_flattened(vnet_dir: Path) -> None:
    spec = _spec(_VNET)
    blobs = sorted(vnet_dir.rglob("PT1H.json"))
    projections = sorted(vnet_dir.glob("field_projection/blob_*.json"))

    assert len(projections) == len(blobs)
    for blob in blobs:
        projection = vnet_dir / "field_projection" / _vnet_projection_name(blob)
        assert _read(projection) == _projected(_read(blob), _emittable(spec, "blob-envelope"))


# =======================================================================================
# o relatório de proveniência: arquivo IRMÃO, nunca dentro do artefato
# =======================================================================================

#: Chaves que só existem no relatório. ``kind`` fica de fora DE PROPÓSITO: é uma coluna
#: documentada de ``Microsoft.Security/automations``, e acusá-la aqui seria falso positivo.
_PROVENANCE_KEYS = frozenset({"surface", "spec", "mechanism", "columns", "counts", "not_generated", "model_gaps"})

#: Superfície -> escopos cujas colunas recusadas o relatório tem de cobrir, uma a uma.
_PROVENANCE_SCOPES: dict[str, tuple[str | None, ...]] = {
    _ARM: (None,),
    _RG: (_RG_VM_SCOPE,),
    _DEFENDER: ("Microsoft.Security/automations", "securityresources/microsoft.security/attackpaths"),
    _NSG: (_NSG_RECORD_SCOPE, "flowTuples-position"),
    _VNET: ("blob", "blob-envelope", "flowTuples-position", _VNET_ANALYTICS_SCOPE, _VNET_IP_DETAILS_SCOPE),
}


def _observation_instant_for(finding: NativeFinding) -> str:
    """O instante que o alerta deve carregar: o valor observado, com fuso, sem perder a fração."""
    assert finding.first_observed_at is not None, finding.finding_id
    return finding.first_observed_at.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _assert_provenance(directory: Path, filename: str) -> dict[str, Any]:
    """O relatório tem de citar a spec REAL, cobrir as colunas recusadas e dizer o mecanismo."""
    spec = _spec(filename)
    path = directory / "_provenance.json"

    assert path.is_file(), f"{directory.name}: sem _provenance.json"
    report: dict[str, Any] = _read(path)
    assert report["kind"] == "provenance"
    assert report["surface"] == spec.surface
    # A citação é comparada com o CAMINHO REAL da spec carregada, não com uma constante do teste.
    assert spec.path is not None
    assert report["spec"] == spec.path.relative_to(DEFAULT_SPECS_ROOT.parent).as_posix()
    assert report["mechanism"], "o relatorio tem de dizer o mecanismo documentado"
    assert report["counts"], "o relatorio tem de trazer as contagens"
    assert report["columns"]["documented"] == len(spec.columns)

    refused = {entry["column"] for entry in report["not_generated"]}
    expected = set().union(*(_non_emittable(spec, scope) for scope in _PROVENANCE_SCOPES[filename]))
    assert refused == expected, f"{directory.name}: colunas recusadas divergem da spec"
    assert all(entry["reason"] for entry in report["not_generated"]), "toda coluna recusada tem motivo"
    assert all(entry.get("item") or entry.get("reason") for entry in report["model_gaps"])
    return report


@pytest.mark.parametrize(
    ("directory", "filename"),
    [
        ("arm_dir", _ARM),
        ("rg_dir", _RG),
        ("defender_dir", _DEFENDER),
        ("nsg_dir", _NSG),
        ("vnet_dir", _VNET),
    ],
    ids=["arm", "resource_graph", "defender", "nsg_flow_logs", "vnet_flow_logs"],
)
def test_provenance_report_is_a_sibling_of_the_artifact(
    request: pytest.FixtureRequest, directory: str, filename: str
) -> None:
    """Cada superfície escreve ``_provenance.json`` irmão: a spec, o mecanismo, as contagens e as lacunas."""
    _assert_provenance(request.getfixturevalue(directory), filename)


@pytest.mark.parametrize(
    "directory",
    ["arm_dir", "rg_dir", "defender_dir", "nsg_dir", "vnet_dir"],
    ids=["arm", "resource_graph", "defender", "nsg_flow_logs", "vnet_flow_logs"],
)
def test_no_artifact_mixes_in_provenance(request: pytest.FixtureRequest, directory: str) -> None:
    """O artefato carrega só campos de nuvem: nenhuma chave do relatório aparece dentro dele."""
    root: Path = request.getfixturevalue(directory)
    artifacts = [
        path
        for path in root.rglob("*")
        if path.is_file() and path.name != "_provenance.json" and path.suffix in {".json", ".jsonl"}
    ]

    assert artifacts, f"{root.name}: nenhum artefato para conferir"
    for path in artifacts:
        assert not (set(columns_of(path)) & _PROVENANCE_KEYS), f"{path.name}: proveniencia dentro do artefato"


def test_nsg_provenance_counts_the_records_it_delivered(nsg_dir: Path, estate: CanonicalEstate) -> None:
    """As contagens do relatório são as do artefato: 51 blobs, 612 registos, 612 tuplos."""
    report = _assert_provenance(nsg_dir, _NSG)
    blobs = sorted(nsg_dir.rglob("PT1H.json"))
    records = sum(len(_read(blob)["records"]) for blob in blobs)
    tuples = sum(
        len(group["flowTuples"])
        for blob in blobs
        for record in _read(blob)["records"]
        for group in record["properties"]["flows"][0]["flows"]
    )

    assert report["counts"]["blobs"] == len(blobs) == _azure_interfaces(estate)
    assert report["counts"]["records"] == records
    assert report["counts"]["flow_tuples"] == tuples == len(_azure_flows(estate))
    assert report["counts"]["flow_windows"] == len({flow.window_start for flow in estate.network_flows})
    # A lacuna que o leitor precisa de conhecer: ICMP não tem literal publicado em posição de protocolo.
    assert report["counts"]["protocol_without_documented_literal"] > 0


def test_arm_provenance_shows_the_filled_leaves_and_the_scenario_gap(arm_dir: Path, estate: CanonicalEstate) -> None:
    """Quatro campos folha com valor (nome, região, tamanho, NIC); o recurso de cenário tem três."""
    report = _assert_provenance(arm_dir, _ARM)
    distribution = report["columns"]["fields_with_value_per_document"]

    assert report["columns"]["with_value"] == 4
    assert sum(distribution.values()) == len(_azure_vms(estate))
    # A distribuição é o retrato da lacuna: UMA resposta tem um campo menos, e é a do recurso
    # que um cenário acrescentou depois de o inventário de rede ter sido construído.
    assert sorted(distribution) == ["3", "4"]
    assert distribution["3"] == len([r for r in _azure_vms(estate) if r.resource_name.startswith("c18")])


def test_vnet_provenance_records_the_spec_cap(vnet_dir: Path, estate: CanonicalEstate) -> None:
    """O relatório do VNet diz, com números, que o teto de colunas é da spec e não do modelo."""
    report = _assert_provenance(vnet_dir, _VNET)

    assert "SPEC" in report["columns"]["cap_note"]
    assert report["columns"]["per_set"]["blob"] == {"documented": 23, "emittable": 0}
    assert report["columns"]["per_set"][_VNET_ANALYTICS_SCOPE] == {"documented": 62, "emittable": 5}
    assert report["columns"]["per_set"][_VNET_IP_DETAILS_SCOPE] == {"documented": 14, "emittable": 2}
    assert report["columns"]["generated"] == 7
    assert report["counts"]["aggregated_flows"] == len(_azure_flows(estate))
    assert report["counts"]["blobs"] == _azure_interfaces(estate)
    assert {entry["item"] for entry in report["model_gaps"]} >= {"recurso FlowLog / Network Watcher"}


# =======================================================================================
# falsification: every audit above must be able to FAIL
# =======================================================================================


def test_a_fabricated_column_is_denounced(rg_dir: Path, tmp_path: Path) -> None:
    """Anti-vacuidade: uma coluna que a documentação não define não pode passar na auditoria."""
    spec = _spec(_RG)
    rows = _read(rg_dir / "field_projection" / "virtualmachines.json")
    rows[0]["properties.invented"] = "x"
    mutated = tmp_path / "mutated.json"
    mutated.write_text(json.dumps(rows), encoding="utf-8")

    findings = check_artifact(spec, mutated, scope=_RG_VM_SCOPE)

    assert KIND_INVENTED in _kinds(findings)
    assert "properties.invented" in _of(findings, KIND_INVENTED)


def test_a_container_smuggled_into_the_document_is_denounced(
    arm_dir: Path, estate: CanonicalEstate, tmp_path: Path
) -> None:
    """Anti-vacuidade da ESTRUTURA: um contêiner a mais no documento não pode passar.

    A projeção entregue publica só os nomes que a spec enumera, então um contêiner inventado
    não apareceria nela. É a comparação do DOCUMENTO com o fecho de prefixo mínimo que o
    denuncia -- e é isso que impede a projeção de esconder uma chave a mais.
    """
    spec = _spec(_ARM)
    document = _read(_arm_document(arm_dir, estate, _azure_vms(estate)[0]))
    document["properties"]["storageProfile"]["invented"] = {"x": 1}
    mutated = tmp_path / "mutated.json"
    mutated.write_text(json.dumps(document), encoding="utf-8")

    extra = _document_paths(_read(mutated)) - _emittable(spec, None)

    assert extra != _prefix_closure(spec, None)
    assert "properties.storageProfile.invented" in extra


def test_a_missing_required_column_is_denounced(arm_dir: Path, estate: CanonicalEstate, tmp_path: Path) -> None:
    """Anti-vacuidade: tirar a única coluna obrigatória da spec não pode passar."""
    spec = _spec(_ARM)
    rows = _read(_arm_projection(arm_dir, estate, _azure_vms(estate)[0]))
    rows[0].pop("properties.storageProfile.dataDisks[].createOption")
    mutated = tmp_path / "mutated.json"
    mutated.write_text(json.dumps(rows), encoding="utf-8")

    findings = check_artifact(spec, mutated)

    assert KIND_MISSING in _kinds(findings)
    assert "properties.storageProfile.dataDisks[].createOption" in _of(findings, KIND_MISSING)


def test_a_required_but_not_generatable_name_cannot_be_satisfied_either_way(
    nsg_dir: Path, tmp_path: Path
) -> None:
    """O residual do NSG é uma contradição da spec: emitir é infração, omitir é ausência.

    Este teste é o que transforma ``missing == 9 posições do CSV`` numa afirmação verificável em
    vez de uma desculpa: o nome que falta é EXATAMENTE o nome que a spec recusa gerar.
    """
    spec = _spec(_NSG)
    position = "records[].properties.flows[].flows[].flowTuples[0]"
    rows = _read(sorted(nsg_dir.glob("field_projection/*.json"))[0])
    rows[0][position] = "1542110402"
    mutated = tmp_path / "mutated.json"
    mutated.write_text(json.dumps(rows), encoding="utf-8")

    findings = check_artifact(spec, mutated, scope=_NSG_RECORD_SCOPE)

    assert position in _required_not_emittable(spec, _NSG_RECORD_SCOPE)
    assert _of(findings, KIND_UNVERIFIED) == {position}
    assert position not in _of(findings, KIND_MISSING)


def test_a_value_in_a_column_the_contract_refuses_is_denounced(vnet_dir: Path, tmp_path: Path) -> None:
    """Anti-vacuidade do eixo de VALORES: preencher uma coluna recusada não pode passar."""
    spec = _spec(_VNET)
    rows = _read(vnet_dir / "NTANetAnalytics.json")
    rows[0]["SrcIp"] = "10.0.0.4"  # example-only: nome descrito, sem contrato para gerar
    mutated = tmp_path / "mutated.json"
    mutated.write_text(json.dumps(rows), encoding="utf-8")

    findings = check_artifact(spec, mutated, scope=_VNET_ANALYTICS_SCOPE)

    assert "SrcIp" in _of(findings, KIND_UNVERIFIED)


# =======================================================================================
# protocol and determinism
# =======================================================================================


@pytest.mark.parametrize(
    "renderer",
    [
        AzureArmInstancesRenderer(),
        AzureResourceGraphRenderer(),
        AzureDefenderRenderer(),
        AzureNsgFlowLogsRenderer(),
        AzureVnetFlowLogsRenderer(),
    ],
    ids=["azure_arm_instances", "azure_resource_graph", "azure_defender", "azure_nsg_flow_logs", "azure_vnet_flow_logs"],
)
def test_renderer_follows_the_protocol_and_is_byte_deterministic(
    renderer: Any, estate: CanonicalEstate, tmp_path: Path
) -> None:
    """``name`` + ``render(estate, out_dir) -> list[Path]``, e o mesmo estado dá os mesmos bytes."""
    first = tmp_path / "first"
    second = tmp_path / "second"
    written = renderer.render(estate, first)
    renderer.render(estate, second)

    assert renderer.name
    assert written and all(path.is_file() for path in written)
    assert {path.relative_to(first) for path in written} == {
        path.relative_to(second) for path in second.rglob("*") if path.is_file()
    }
    for path in written:
        assert path.read_bytes() == (second / path.relative_to(first)).read_bytes(), path.name
