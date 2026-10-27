"""Kubernetes Engine cluster routes (container v1).

``GET /container/v1/projects/{project}/locations/{location}/clusters``
(``projects.locations.clusters.list``) -- one row per ``gke_cluster`` resource of the
estate, in the ``ListClustersResponse`` the method publishes: the ``clusters`` array and
the ``missingZones`` array.

The response carries **exactly** those two members. The envelope is the API's, and a
third member would be a member the provider does not publish. The cluster rows come
from ``gcp_sim/projections/container.py``, which is where the members the estate can
answer for -- and the ones it cannot -- are decided.

``missingZones`` is published empty, and that is the estate's silence rather than a
default: the field says "the list of clusters returned may be missing those zones", and
the estate models no zone the emulator failed to answer. A non-empty list would claim
a gap in the answer that the estate never had.

A project or a location the estate does not carry selects nothing (an empty
``clusters``) rather than 404: the emulator answers about what it owns instead of
inventing a row for something it does not -- the same rule the sibling routers take.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from gcp_sim.deps import require_bearer
from gcp_sim.projections import container
from gcp_sim.routers import estate

router = APIRouter(tags=["container"])


@router.get("/container/v1/projects/{project}/locations/{location}/clusters")
async def list_clusters(project: str, location: str, request: Request) -> dict[str, Any]:
    """Kubernetes Engine ``projects.locations.clusters.list`` for one project and location.

    ``location`` is the zone or region the clusters reside in; "-" matches every zone
    and every region, which is what the list method publishes.
    """
    require_bearer(request)
    return {
        "clusters": list(container.clusters(estate(request), project, location)),
        "missingZones": [],
    }
