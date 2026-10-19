"""Resource Graph inventory projection (design §5, §8 C11).

Projects ``estate.inventory`` into Resource Graph ``resources`` rows and
``estate.iac_snapshots`` deltas into ``resourcechanges`` rows. All native inputs:
inventory assets and IaC-managed flags are what Azure Resource Graph returns.
FinOps computes drift from these inputs; this projection never emits a drift
verdict (P1).

**The row ``id`` is the resource's ARM id** (``arm.resource_id_for``), which is what Resource
Graph returns and what every other Azure surface in this package names the resource by: the
resource-plane projections publish it as the row ``id``, Monitor returns it as a metric's
``resourceId``, and the alert rules scope to it. The estate's ``ResourceIdentity.uuid`` is the
canonical model's own key (P2) and stays where it belongs — inside this package, joining an
asset to its resource — while the id served on the wire is the provider's. A resource type
this package serves no ARM path for keeps the uuid, because no rival value is published for
it and inventing a path would be the fabrication this module avoids everywhere else.

TODO-verificar §11.8: the exact Resource Graph row envelope (``id``/``name``/
``type``/``location``/``resourceGroup``/``subscriptionId``/``properties`` keys and
their casing) and the ``resourcechanges`` ``changeType`` vocabulary are NOT
offline-verifiable. Rows are emitted official-shaped and flagged.
"""

from __future__ import annotations

from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.iac import InventoryAsset
from tools.synthetic_clouds.model.resource import Resource

from azure_sim.projections import arm, scope


def _asset_id(estate: CanonicalEstate, asset: InventoryAsset, resource: Resource | None) -> str:
    """The id an asset row is addressed by: its resource's ARM id, or the estate's uuid."""
    if resource is None:
        return str(asset.resource_uuid)
    resource_id: str | None = arm.resource_id_for(estate, resource)
    return resource_id or str(asset.resource_uuid)


def _asset_row(estate: CanonicalEstate, asset: InventoryAsset, resource: Resource | None) -> dict[str, object]:
    """Project one inventory asset into a Resource Graph ``resources`` row.

    ``properties`` is EMPTY: ``InventoryAsset.config_json`` is a FinOps-side marker
    bag (``synthetic`` + ``region``, ``generate/estate_builder.py:444``) whose keys the
    Resource Graph row does not define, so spreading it wrote a ``synthetic`` key into
    every row. Resource Graph returns the ASSESSED RESOURCE's own properties there (the
    ``Microsoft.*`` payload ``projections/arm.py`` projects for the resource plane); the
    estate's inventory carries none, and absence is absence. The asset's ``region`` is
    already published on its own real field, ``location``, below.
    """
    # TODO-verificar §11.8: official Resource Graph row key names/casing.
    row: dict[str, object] = {
        "id": _asset_id(estate, asset, resource),
        "type": asset.asset_type,
        "managedByIac": asset.managed_by_iac,
        "properties": {},
    }
    if resource is not None:
        row["name"] = resource.resource_name
        row["location"] = resource.region_id
        row["resourceGroup"] = resource.parent_scope_id
        row["subscriptionId"] = resource.parent_scope_id
        row["tags"] = dict(resource.tags)
    return row


def project_resources(estate: CanonicalEstate) -> list[dict[str, object]]:
    """Return Resource Graph ``resources`` rows for THIS provider, ordered by id."""
    rows = [_asset_row(estate, asset, resource) for asset, resource in scope.inventory(estate)]
    return sorted(rows, key=lambda row: str(row["id"]))


def project_resource_changes(estate: CanonicalEstate) -> list[dict[str, object]]:
    """Return ``resourcechanges`` rows from inventory vs IaC-declared state (C11).

    An inventory asset absent from the IaC snapshot's declared states is the
    drift INPUT: it is reported as a native change row (``changeType`` =
    ``Create`` — present in cloud, not declared). FinOps computes drift from
    these; this emits only the native change record (P1).

    The comparison is on the estate's own uuids, but the id a row PUBLISHES is the
    resource's ARM id — the target a caller then asks the resource plane about.
    """
    declared: set[str] = set()
    for snapshot in estate.iac_snapshots:
        declared.update(state.resource_uuid for state in snapshot.resource_states)
    rows: list[dict[str, object]] = []
    for asset, resource in scope.inventory(estate):
        if asset.managed_by_iac and asset.resource_uuid not in declared:
            # TODO-verificar §11.8: official changeType vocabulary.
            rows.append(
                {
                    "targetResourceId": _asset_id(estate, asset, resource),
                    "targetResourceType": asset.asset_type,
                    "changeType": "Create",
                }
            )
    return sorted(rows, key=lambda row: str(row["targetResourceId"]))


def project_security_resources(estate: CanonicalEstate) -> list[dict[str, object]]:
    """Return ``securityresources`` rows (Resource Graph security table).

    Native inventory joined with the per-resource finding count — the shape the
    ``securityresources`` table exposes. FinOps computes posture scores from
    these; this emits only native counts (P1).
    """
    finding_counts: dict[str, int] = {}
    for finding in scope.findings(estate):
        finding_counts[finding.resource_uuid] = finding_counts.get(finding.resource_uuid, 0) + 1
    rows: list[dict[str, object]] = []
    for asset, resource in scope.inventory(estate):
        rows.append(
            {
                "id": _asset_id(estate, asset, resource),
                "type": asset.asset_type,
                "name": resource.resource_name if resource is not None else "",
                "findingCount": finding_counts.get(asset.resource_uuid, 0),
            }
        )
    return sorted(rows, key=lambda row: str(row["id"]))
