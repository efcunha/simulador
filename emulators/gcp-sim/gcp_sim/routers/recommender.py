"""Recommender routes (design sec. 5.1, sec. 5.2).

``GET /v1/{parent}/recommenders/{id}/recommendations`` and ``.../insights`` --
native recommendations/insights from the estate. Recommender is gRPC-by-default;
the sim serves REST and Phase 4 forces ``transport="rest"`` (no production code
touched here). TODO-verificar #7: official REST shape + transport support.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request

from gcp_sim.deps import clamp_page_size, require_bearer, validate_prefix
from gcp_sim.routers import store

router = APIRouter(tags=["recommender"])

_PARENT_PREFIXES = ("projects/", "organizations/", "folders/", "billingAccounts/")


@router.get("/v1/{parent:path}/recommenders/{recommender_id}/recommendations")
async def list_recommendations(
    parent: str,
    recommender_id: str,
    request: Request,
    pageSize: int | None = Query(default=None),  # noqa: N803 - GCP query param casing
) -> dict[str, Any]:
    """Recommender recommendations list (TODO-verificar #7)."""
    require_bearer(request)
    validate_prefix(parent, _PARENT_PREFIXES, "parent")
    clamp_page_size(pageSize)
    return store(request).get("recommender_recommendations.json")


@router.get("/v1/{parent:path}/insightTypes/{insight_type}/insights")
async def list_insights(
    parent: str,
    insight_type: str,
    request: Request,
    pageSize: int | None = Query(default=None),  # noqa: N803 - GCP query param casing
) -> dict[str, Any]:
    """Recommender insights list (TODO-verificar #7)."""
    require_bearer(request)
    validate_prefix(parent, _PARENT_PREFIXES, "parent")
    clamp_page_size(pageSize)
    return store(request).get("recommender_insights.json")
