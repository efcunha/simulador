"""Compute Engine instance routes (Phase 6).

``GET /compute/v1/projects/{project}/aggregated/instances`` (``instances.aggregatedList``)
and ``GET /compute/v1/projects/{project}/zones/{zone}/instances`` (``instances.list``) --
one row per ``compute_instance`` resource of the estate. FinOps GCP inventory reads
the aggregated form (``resources.py (modulo do consumidor)``) and builds each row's
``resource_id`` from the zone and the instance name, so both routes here come from one row
factory and cannot disagree about an instance.

**The zone is derived, and that is the point.** The estate records a region and nothing
finer, so the zone is the resource's own ``region_id`` plus a letter chosen
deterministically from its uuid -- the derivation ``emulators/aws-sim/aws_sim/projections/ec2.py``
already uses for an availability zone. Two properties matter and both are tested: the
letter is stable across calls (a random one would make two calls about one instance
disagree, and FinOps correlates those answers across a scan), and it stays inside the
region (``us-central1-a`` starts with ``us-central1``), which is exactly the prefix
comparison that inventory client filters on.

``machineType`` is the SKU the estate bills the instance under, in the path form the same
client splits on (``zones/<zone>/machineTypes/<type>``). The map is closed: the SKU
catalog is the generator's, so an unmapped SKU is a code change upstream and the
``KeyError`` names it rather than serving a blank machine type.

``status`` is ``RUNNING`` -- the estate is a billing baseline, so a resource it bills for
exists and runs. That is the same claim the AWS sim makes for a billed instance, not a
value read off the estate.

Nothing else is emitted, and each omission is the estate's silence: no ``id`` (the estate
mints a uuid, not GCP's numeric id), no ``creationTimestamp`` (the estate asserts no
creation time, and the sim's clock would be a fabricated one), no ``networkInterfaces``,
``disks`` or ``serviceAccounts`` (the estate models no network, attachment or identity
relation, so any of those would be an invented relation, not a missing field).

The aggregated map carries one entry per zone an instance actually sits in, keyed
``zones/<zone>`` -- the key shape ``compute_v1``'s aggregated-list iterator yields. A zone
the estate places nothing in is **not** listed: ``{"instances": []}`` under it would assert
that the project has that zone and nothing running in it, which the estate never says.

A zone or project this estate does not carry selects nothing (empty ``items``) rather than
404, matching the sibling sims: the emulator answers about what it owns instead of
inventing a row for something it does not.
"""

from __future__ import annotations

import hashlib
from typing import Any

from fastapi import APIRouter, Query, Request
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.resource import Resource

from gcp_sim import scope
from gcp_sim.deps import clamp_page_size, require_bearer
from gcp_sim.routers import estate

router = APIRouter(tags=["compute"])

INSTANCE = "compute_instance"

#: ``sku_id`` -> the machine type it names. A closed map: the SKU catalog is the
#: generator's, so an unmapped SKU is a code change upstream and a KeyError names it.
MACHINE_TYPES_BY_SKU: dict[str, str] = {
    "gcp-ce-e2-standard-2": "e2-standard-2",
}

#: Zone letters appended to the region. GCP names zones ``<region>-<letter>``, so a
#: derived zone stays inside its region -- which is what the inventory client filters on.
ZONE_LETTERS: tuple[str, ...] = ("a", "b", "c")

#: Compute's own state vocabulary, restricted to the member a billed resource is in.
INSTANCE_STATE_RUNNING = "RUNNING"


def _zone(resource: Resource) -> str:
    """The zone the instance sits in: its region plus a letter derived from its uuid.

    Stable for a given resource and inside its region; see the module docstring for why
    both properties are load-bearing.
    """
    digest = hashlib.sha256(f"{resource.identity.uuid}:zone".encode()).hexdigest()
    return f"{resource.region_id}-{ZONE_LETTERS[int(digest[:8], 16) % len(ZONE_LETTERS)]}"


def _instance(resource: Resource) -> dict[str, Any]:
    """One ``instances`` entry for an estate instance. Fresh each call, so no aliasing."""
    zone = _zone(resource)
    return {
        "name": resource.resource_name,
        "zone": zone,
        "machineType": f"zones/{zone}/machineTypes/{MACHINE_TYPES_BY_SKU[resource.sku_id]}",
        "status": INSTANCE_STATE_RUNNING,
        "labels": dict(resource.tags),
    }


def _instances(estate_: CanonicalEstate, project_id: str) -> tuple[dict[str, Any], ...]:
    """This project's instance rows, ordered by name."""
    return tuple(
        _instance(resource) for resource in scope.resources_of_type(estate_, INSTANCE, project_id=project_id)
    )


@router.get("/compute/v1/projects/{project}/aggregated/instances")
async def aggregated_list_instances(
    project: str,
    request: Request,
    maxResults: int | None = Query(default=None),  # noqa: N803 - GCP query param casing
) -> dict[str, Any]:
    """Compute Engine ``instances.aggregatedList`` for one project (regional grouping)."""
    require_bearer(request)
    clamp_page_size(maxResults)
    items: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for row in _instances(estate(request), project):
        items.setdefault(f"zones/{row['zone']}", {"instances": []})["instances"].append(row)
    return {"items": dict(sorted(items.items())), "nextPageToken": ""}


@router.get("/compute/v1/projects/{project}/zones/{zone}/instances")
async def list_instances(
    project: str,
    zone: str,
    request: Request,
    maxResults: int | None = Query(default=None),  # noqa: N803 - GCP query param casing
) -> dict[str, Any]:
    """Compute Engine ``instances.list`` for one zone of one project."""
    require_bearer(request)
    clamp_page_size(maxResults)
    return {
        "items": [row for row in _instances(estate(request), project) if row["zone"] == zone],
        "nextPageToken": "",
    }
