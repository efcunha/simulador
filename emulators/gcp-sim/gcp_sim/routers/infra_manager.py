"""Infrastructure Manager resource drifts (``config.googleapis.com``).

The official method is
``GET https://config.googleapis.com/v1/{parent=projects/*/locations/*/previews/*}/resourceDrifts``
(``projects.locations.previews.resourceDrifts.list``). This router serves the same path
shape, the same ``{resourceDrifts[], nextPageToken, unreachable[]}`` envelope and the same
``ResourceDrift`` item the renderer delivers.

The records are projected by
:func:`tools.synthetic_clouds.model.drift.project_drift_views` from the frozen estate: the
C11 inputs (declared tags in the IaC snapshot vs. the inventory) are the only source. There
is no scenario-specific branch here.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request

from gcp_sim.deps import clamp_page_size, require_bearer
from gcp_sim.errors import GcpError
from gcp_sim.routers import estate
from tools.synthetic_clouds.model.drift import gcp_resource_drift_document, project_drift_views

router = APIRouter(tags=["infra-manager"])


def _parent(project: str, location: str, preview: str) -> str:
    return f"projects/{project}/locations/{location}/previews/{preview}"


@router.get("/v1/projects/{project}/locations/{location}/previews/{preview}/resourceDrifts")
async def list_resource_drifts(
    project: str,
    location: str,
    preview: str,
    request: Request,
    pageSize: int | None = Query(default=None),  # noqa: N803 - GCP query param casing
    pageToken: str = Query(default=""),  # noqa: N803 - GCP query param casing
) -> dict[str, Any]:
    """``resourceDrifts.list`` for one preview."""
    require_bearer(request)
    parent = _parent(project, location, preview)
    rows = [
        gcp_resource_drift_document(item)
        for item in project_drift_views(estate(request)).gcp_resource_drifts
        if item.name.startswith(f"{parent}/resourceDrifts/")
    ]
    # The page token is opaque and this emulator returns the full list; an offset
    # token is still honoured so a caller that paginates does not receive a loop.
    start = 0
    if pageToken:
        try:
            start = max(0, int(pageToken))
        except ValueError:
            start = 0
    page = rows[start : start + clamp_page_size(pageSize)]
    next_token = str(start + len(page)) if start + len(page) < len(rows) else ""
    return {"resourceDrifts": page, "nextPageToken": next_token, "unreachable": []}


@router.get(
    "/v1/projects/{project}/locations/{location}/previews/{preview}/resourceDrifts/{resource_drift}"
)
async def get_resource_drift(
    project: str,
    location: str,
    preview: str,
    resource_drift: str,
    request: Request,
) -> dict[str, Any]:
    """``resourceDrifts.get`` for one drift name."""
    require_bearer(request)
    name = f"{_parent(project, location, preview)}/resourceDrifts/{resource_drift}"
    for item in project_drift_views(estate(request)).gcp_resource_drifts:
        if item.name == name:
            return gcp_resource_drift_document(item)
    raise GcpError(404, f"resource drift not found: {name}")
