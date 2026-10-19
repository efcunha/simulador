"""The provider boundary for every aws-sim projection.

Same discipline as ``emulators/azure-sim/azure_sim/projections/scope.py``, for the same
reason: the canonical estate is multi-cloud, and an AWS endpoint that answers with an
Azure or GCP resource is the owner's fidelity requirement inverted.

The provider does not live in the same place on every model, so each filter is written
against the field that actually carries it:

* resources and AWS accounts carry the operational provider key (lowercase ``aws``);
* findings and recommendations carry their own ``provider`` string;
* inventory assets and IaC snapshots carry **no** provider — an asset belongs to
  whichever provider owns its ``resource_uuid``, and a snapshot to whichever owns its
  ``scope_id``, so both are scoped through the resource index.

It also carries the one derived index every service projection needs and none of them
should rebuild: the earliest day the estate billed each resource (:func:`first_charge`),
which is what the AWS APIs report as an object's creation time.
"""

from __future__ import annotations

from datetime import datetime

from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.iac import IacStateSnapshot, InventoryAsset
from tools.synthetic_clouds.model.resource import Resource

#: The operational provider key (``ResourceIdentity.provider``), lowercase.
PROVIDER = "aws"


def resources(estate: CanonicalEstate) -> tuple[Resource, ...]:
    """This provider's resources, in estate order."""
    return tuple(r for r in estate.resources if r.identity.provider == PROVIDER)


def resource_index(estate: CanonicalEstate) -> dict[str, Resource]:
    """Map this provider's resource uuid -> Resource."""
    return {r.identity.uuid: r for r in resources(estate)}


def resource_uuids(estate: CanonicalEstate) -> frozenset[str]:
    """The uuid set every provider-scoped projection filters against."""
    return frozenset(resource_index(estate))


def scope_ids(estate: CanonicalEstate) -> frozenset[str]:
    """The AWS account ids that own this provider's resources."""
    return frozenset(r.parent_scope_id for r in resources(estate))


def inventory(estate: CanonicalEstate) -> tuple[tuple[InventoryAsset, Resource | None], ...]:
    """This provider's inventory assets paired with their resource."""
    index = resource_index(estate)
    return tuple(
        (asset, index.get(asset.resource_uuid)) for asset in estate.inventory if asset.resource_uuid in index
    )


def first_charge(estate: CanonicalEstate) -> dict[str, datetime]:
    """Map ``resource_uuid`` -> the earliest charge period start billed for it.

    The canonical model carries **no creation date** for a resource, so the earliest day
    the estate charged it is the only timestamp it asserts about the resource existing —
    which is exactly what an AWS projection needs for ``CreatedTime`` / ``CreatedAt``.
    A resource with no line maps to nothing, and the caller omits the field rather than
    substituting the sim's clock: absence is absence.

    No provider filter is needed. A ``resource_uuid`` belongs to one provider, so a line
    referencing it is this provider's line by construction.
    """
    first: dict[str, datetime] = {}
    for line in estate.billing_lines:
        if line.resource_uuid is None:
            continue
        current = first.get(line.resource_uuid)
        if current is None or line.charge_period_start < current:
            first[line.resource_uuid] = line.charge_period_start
    return first


def iac_snapshots(estate: CanonicalEstate) -> tuple[IacStateSnapshot, ...]:
    """This provider's IaC snapshots.

    A snapshot has a ``scope_id`` (an AWS account id here) and no provider, so it is
    scoped through the accounts this provider's resources actually belong to.
    """
    owned = scope_ids(estate)
    return tuple(s for s in estate.iac_snapshots if s.scope_id in owned)
