"""Cloud Monitoring routes (design sec. 5.1).

``GET /v3/{name=projects/*}/timeSeries`` -- metric series for GCP resources from
the estate. TODO-verificar #7: official response envelope.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request

from gcp_sim.deps import clamp_page_size, require_bearer, validate_prefix
from gcp_sim.routers import store

router = APIRouter(tags=["monitoring"])


@router.get("/v3/{name:path}/timeSeries")
async def list_time_series(
    name: str,
    request: Request,
    pageSize: int | None = Query(default=None),  # noqa: N803 - GCP query param casing
) -> dict[str, Any]:
    """Cloud Monitoring timeSeries list under ``projects/*`` (TODO-verificar #7)."""
    require_bearer(request)
    validate_prefix(name, ("projects/",), "name")
    clamp_page_size(pageSize)
    return store(request).get("monitoring_time_series.json")
