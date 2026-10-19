"""Cloud Billing Catalog routes (design sec. 5.1).

``GET /v1/services`` and ``GET /v1/services/{id}/skus`` -- pricing catalog derived
from the GCP side of the estate. TODO-verificar #7: official response envelope.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request

from gcp_sim.deps import clamp_page_size, require_bearer
from gcp_sim.routers import store

router = APIRouter(tags=["catalog"])


@router.get("/v1/services")
async def list_services(request: Request, pageSize: int | None = Query(default=None)) -> dict[str, Any]:  # noqa: N803 - GCP query param casing
    """Cloud Billing Catalog services list (TODO-verificar #7)."""
    require_bearer(request)
    clamp_page_size(pageSize)
    return store(request).get("catalog_services.json")


@router.get("/v1/services/{service_id}/skus")
async def list_skus(service_id: str, request: Request, pageSize: int | None = Query(default=None)) -> dict[str, Any]:  # noqa: N803 - GCP query param casing
    """Cloud Billing Catalog SKUs list for a service (TODO-verificar #7)."""
    require_bearer(request)
    clamp_page_size(pageSize)
    return store(request).get("catalog_skus.json")
