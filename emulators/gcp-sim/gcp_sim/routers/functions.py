"""Cloud Functions routes (Phase 6).

``GET /v1/projects/{project}/locations/{location}/functions`` (``list_functions``) -- one
row per ``cloud_function`` resource of the estate, the resource type FinOps GCP
inventory collects under its ``FUNCTIONS`` token
(``resources.py (modulo do consumidor)``). That collector asks for the parent
``projects/<p>/locations/-`` to cover the whole project and
``projects/<p>/locations/<region>`` when a region filter is set, so this route serves both
call shapes -- ``-`` covers every location, a concrete location narrows to that region --
and a region-filtered scan sees the same functions a full scan does, only fewer of them.

``name`` is the full resource name GCP reports (the collector takes its last segment as the
function name and parses the location out of the middle), built from the project, the
estate's ``region_id`` and the resource name. ``status`` is the v1 Function's own state
member -- ``ACTIVE`` -- because the estate bills the function, so it is deployed and
serving: the baseline claim the AWS sim makes for a billed resource, not a value read off
the estate. ``labels`` are the resource's own tags.

Version note, because it decides what a caller can do with this route: this is the **v1**
shape (``google.cloud.functions_v1``, whose state member is ``status``). FinOps
collector speaks **v2** (``client.py (modulo do consumidor)`` builds a
``functions_v2.FunctionServiceClient``, whose ``Function`` carries ``state`` and
``build_config``), so closing the FUNCTIONS gap end to end also needs the v2 route; this
module serves the version this slice was asked for (``/v1``), in its own correct wire shape
rather than a mix of the two.

``runtime`` is deliberately **absent**. No estate field states a runtime, and the SKU this
type is billed under (``gcp-cf-gb-second``) names a billing unit (GB-Seconds), not a runtime
identifier. A runtime picked from a catalog here would be fabricated configuration -- a
caller stores it and reports a language the estate never recorded -- so the field is left
out and a client reads it as empty.

A project or location this estate does not carry selects nothing (empty ``functions``),
matching the sibling sims (``emulators/aws-sim/aws_sim/projections/elbv2.py``).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.resource import Resource

from gcp_sim import scope
from gcp_sim.deps import clamp_page_size, require_bearer
from gcp_sim.routers import estate

router = APIRouter(tags=["functions"])

FUNCTION = "cloud_function"

#: ``locations/-`` in a parent means "every location" (GCP's own wildcard).
ALL_LOCATIONS = "-"

#: Cloud Functions v1's state vocabulary (its member is ``status``), restricted to the
#: member a billed function is in.
FUNCTION_STATUS_ACTIVE = "ACTIVE"


def _function(resource: Resource) -> dict[str, Any]:
    """One ``functions`` entry for an estate cloud function."""
    return {
        "name": (
            f"projects/{resource.parent_scope_id}/locations/{resource.region_id}"
            f"/functions/{resource.resource_name}"
        ),
        "status": FUNCTION_STATUS_ACTIVE,
        "labels": dict(resource.tags),
    }


def _functions(estate_: CanonicalEstate, project_id: str, location: str) -> tuple[dict[str, Any], ...]:
    """This project's function rows, narrowed to ``location`` unless it is the wildcard."""
    return tuple(
        _function(resource)
        for resource in scope.resources_of_type(estate_, FUNCTION, project_id=project_id)
        if location == ALL_LOCATIONS or resource.region_id == location
    )


@router.get("/v1/projects/{project}/locations/{location}/functions")
async def list_functions(
    project: str,
    location: str,
    request: Request,
    pageSize: int | None = Query(default=None),  # noqa: N803 - GCP query param casing
) -> dict[str, Any]:
    """Cloud Functions ``list_functions`` for one project (``-`` = every location)."""
    require_bearer(request)
    clamp_page_size(pageSize)
    return {"functions": list(_functions(estate(request), project, location)), "nextPageToken": ""}
