"""The ARM envelope every resource-plane projection in this package answers in (Phase 6).

Seven Azure services are emulated as ARM resource managers — compute, containerservice,
network, sql, storage, subscription and web. ``docs/synthetic-clouds/COVERAGE.json`` lists
the operation each one stands in for and the FinOps call site it replaces. Two rules
are shared by all seven, and both live here because both are silent when they are wrong:

**Identity.** An ARM row's ``id`` is not decoration — callers parse it. ``service_discovery.py (modulo do consumidor):413`` reads the resource group straight back out
of it (``rg_name = server.id.split("/")[4]``) and hands that string to the next call, and
``resources.py (modulo do consumidor):50`` filters VMs on ``vm.location``.
So every id is built in the one shape
``/subscriptions/<sub>/resourceGroups/<rg>/providers/<ns>/<type>/<name>``, and the
**subscription segment is a GUID**, not the estate's scope label: ``parent_scope_id`` is
the generator's internal key (``sub-01``), while the subscription FinOps is configured
with and keys cost rows on is the GUID the FOCUS export publishes as ``SubAccountId``
(``tools/synthetic_clouds/render/focus_azure.py:117`` mints it with the very same
``identity.azure_subscription_guid`` used below, as ``model/hierarchy.py:33`` describes the
field). Serving the label would give a resource row and the bill for that resource two
different subscriptions.

The **resource group is the scope label**: the estate models no resource-group level, and
the two existing projections that must name one (``inventory._asset_row``'s
``resourceGroup``, ``alerts._rule_id``'s ``/resourceGroups/`` segment) already read it that
way, so this module keeps that reading rather than inventing a third convention. The
consequence is a real one and worth stating: two scopes that reuse a resource name produce
rows whose only difference is the subscription segment, which is exactly why the id — and not
the name — is what identifies a row, and why :func:`resource_id_for` is the one function the
rest of the package asks for it.

**Provider boundary.** Every row comes from :mod:`azure_sim.projections.scope`, so a
``Microsoft.*`` endpoint cannot answer with an AWS or GCP row.
"""

from __future__ import annotations

from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.identity import azure_subscription_guid
from tools.synthetic_clouds.model.resource import Resource

from azure_sim.projections import scope

#: What ARM reports for a resource that exists. The estate bills a resource only while it
#: is owned, so "present in the estate" IS "provisioned"; the estate models no
#: intermediate provisioning state, and emitting nothing here would be read by a caller as
#: an unknown state rather than as a resource with none. Same reading as
#: ``aws_sim/projections/ec2.py:100`` gives ``available``/``running``.
PROVISIONING_SUCCEEDED = "Succeeded"

#: The ARM types this package serves, and the ONE table they come from.
#:
#: Every resource-plane projection reads its own ``type`` here rather than spelling it out,
#: and ``resource_id_for`` builds a resource's ARM id from the same table. That is what makes
#: the identity a resource answers agree across the package by construction: the row
#: ``virtualMachines.list_all`` publishes, the ``resourceId`` a Monitor metric row carries, the
#: ``id`` the Resource Graph inventory reports and the ``scopes`` of a metric-alert rule are
#: all built from these strings, so a caller holding one can resolve the others.
VIRTUAL_MACHINE_TYPE = "Microsoft.Compute/virtualMachines"
DISK_TYPE = "Microsoft.Compute/disks"
MANAGED_CLUSTER_TYPE = "Microsoft.ContainerService/managedClusters"
SQL_SERVER_TYPE = "Microsoft.Sql/servers"
SQL_DATABASE_TYPE = "Microsoft.Sql/servers/databases"
STORAGE_ACCOUNT_TYPE = "Microsoft.Storage/storageAccounts"
NETWORK_SECURITY_GROUP_TYPE = "Microsoft.Network/networkSecurityGroups"
SITE_TYPE = "Microsoft.Web/sites"

#: estate ``resource_type`` -> the ARM type its resource-plane projection serves it under.
#: The estate's types are the generator's catalog (``generate/constants.py:49``), so a pair
#: with no entry is a type this package serves no ARM path for (``public_ip``,
#: ``log_analytics``, ``openai``): ``resource_id_for`` answers ``None`` for those rather than
#: inventing a path no projection publishes.
ARM_TYPES: dict[str, str] = {
    "virtual_machine": VIRTUAL_MACHINE_TYPE,
    "managed_disk": DISK_TYPE,
    "aks_cluster": MANAGED_CLUSTER_TYPE,
    "sql_database": SQL_DATABASE_TYPE,
    "storage_account": STORAGE_ACCOUNT_TYPE,
    "network_security_group": NETWORK_SECURITY_GROUP_TYPE,
    "app_service": SITE_TYPE,
}

#: ``resource_type`` -> the segments a CHILD resource appends after its provider namespace.
#: ``sql_database`` is the only one, and it is genuinely nested: ARM reaches a database as
#: ``.../providers/Microsoft.Sql/servers/<server>/databases/<database>``, and ``sql.py``
#: derives one server per database, named after it — so both ``{name}`` slots are the same
#: resource's own name.
_CHILD_SEGMENTS: dict[str, str] = {
    "sql_database": "servers/{name}/databases/{name}",
}


def subscription_id(estate: CanonicalEstate, scope_id: str) -> str:
    """The ARM subscription id for one of the estate's scope labels.

    ``azure_subscription_guid`` is the estate's own mint (see the module docstring), so
    the id is deterministic for a seed and, for a given scope, is the same value the FOCUS
    export and every other served row uses.
    """
    return azure_subscription_guid(estate.seed, scope_id)


def subscription_in_scope(scope: str) -> str | None:
    """The subscription id a request scope names, or ``None`` when it names none.

    A caller builds the scope out of the ids it was previously served, so it arrives as a
    path string (``/subscriptions/<sub>/resourceGroups/<rg>``) that has to be read back
    out. It is split on ``/`` rather than matched against a fixed prefix because the shapes
    that reach this function differ: FastAPI's ``:path`` converter hands over
    ``subscriptions/sub-01`` **without** the leading slash, while a scope copied out of a
    served ARM id keeps it. Empty segments are dropped, so a doubled or trailing slash
    cannot shift the answer.

    ``None`` means the request was not subscription-scoped, which is the only case where a
    row's own scope may not be narrowed on. The comparison is case-insensitive because ARM
    paths are.
    """
    segments = [segment for segment in scope.split("/") if segment]
    for index, segment in enumerate(segments):
        if segment.lower() == "subscriptions" and index + 1 < len(segments):
            return segments[index + 1]
    return None


def provider_path(estate: CanonicalEstate, resource: Resource, *, arm_type: str) -> str:
    """The provider path of ``resource``: ``.../providers/<arm_type>``, without a name.

    The name is deliberately left off, because a child resource needs its parent's
    provider path as a prefix (a SQL database is reached as ``<server>/databases/<db>``),
    and the caller is the only one that knows which name goes on the end.
    """
    # The resource group mirrors ``inventory.py:36`` / ``alerts.py:77`` (see module doc).
    return (
        f"/subscriptions/{subscription_id(estate, resource.parent_scope_id)}"
        f"/resourceGroups/{resource.parent_scope_id}/providers/{arm_type}"
    )


def resource_id(
    estate: CanonicalEstate,
    resource: Resource,
    *,
    arm_type: str,
    name: str | None = None,
) -> str:
    """The ARM id of ``resource``, or of the child ``name`` names under it."""
    return f"{provider_path(estate, resource, arm_type=arm_type)}/{name or resource.resource_name}"


def resource_id_for(estate: CanonicalEstate, resource: Resource) -> str | None:
    """The ARM id of ``resource``, by its own ``resource_type`` — or ``None``.

    This is the identity a resource is keyed by across the package: the same string
    :func:`arm_row` publishes as a row's ``id``, and the one the Monitor projections
    (``metrics.py``, ``alerts.py``) and the Resource Graph inventory report for it. It is
    built from the resource's own name **and** its scope — the subscription GUID and the
    resource group — so two resources that share a ``resource_name`` in two subscriptions
    resolve to two DIFFERENT ids. That is the whole reason a name cannot be the key: the
    estate reuses names across scopes, and a telemetry row keyed by one would be a row two
    resources claim.

    ``None`` means this package serves no ARM path for the type: the caller keeps the
    estate's own ``ResourceIdentity.uuid``, which is unique but not ARM-shaped, rather than
    have this module invent a path no projection publishes.
    """
    arm_type = ARM_TYPES.get(resource.resource_type)
    if arm_type is None:
        return None
    child = _CHILD_SEGMENTS.get(resource.resource_type)
    if child is not None:
        # The provider namespace only (``Microsoft.Sql``): the child segment carries the
        # parent type and both names itself.
        return (
            f"{provider_path(estate, resource, arm_type=arm_type.split('/')[0])}"
            f"/{child.format(name=resource.resource_name)}"
        )
    return resource_id(estate, resource, arm_type=arm_type)


def resource_id_of_uuid(estate: CanonicalEstate, resource_uuid: str) -> str | None:
    """The ARM id of the resource a native record points at, or ``None`` when unknown.

    Native records — a metric series, a Defender finding, an Advisor recommendation —
    reference their resource by the canonical model's own ``resource_uuid`` (P2), which is
    an internal key. This resolves it to the id every served row uses, so a consumer that
    read a resource row can match a finding or a metric to it. ``None`` means the uuid names
    no resource of this provider, which a caller answers by leaving the field out.
    """
    resource = scope.resource_index(estate).get(resource_uuid)
    if resource is None:
        return None
    return resource_id_for(estate, resource)


def arm_row(
    estate: CanonicalEstate,
    resource: Resource,
    *,
    arm_type: str,
    properties: dict[str, object],
    name: str | None = None,
    top_level: dict[str, object] | None = None,
) -> dict[str, object]:
    """One ARM resource row: ``id``/``name``/``type``/``location``/``tags``/``properties``.

    ``top_level`` carries the blocks ARM models BESIDE ``properties`` — a storage
    account's or a disk's ``sku``. They are merged at the top level rather than nested
    inside ``properties`` because that is where the SDK's own ``_attribute_map`` reads
    them (checked against the installed ``azure-mgmt-storage`` 24.0.1 and
    ``azure-mgmt-sql`` 4.0.0b24 models), and a row that nests them deserializes with
    ``sku = None`` while still looking correct on the wire.
    """
    row: dict[str, object] = {
        "id": resource_id(estate, resource, arm_type=arm_type, name=name),
        "name": name or resource.resource_name,
        "type": arm_type,
        "location": resource.region_id,
        "tags": dict(resource.tags),
        "properties": properties,
    }
    if top_level:
        row.update(top_level)
    return row
