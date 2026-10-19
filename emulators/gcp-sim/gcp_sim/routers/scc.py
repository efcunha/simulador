"""Security Command Center routes (design sec. 5.1, sec. 5.2).

``GET /v1/organizations/*/sources`` and
``GET /v1/{parent=organizations/*/sources/*}/findings`` -- native findings
(status open, UPPERCASE severity) from the estate. SCC is gRPC-by-default; the sim
serves REST, and Phase 4 forces ``transport="rest"`` on the client (no production
code touched here). TODO-verificar #7: official REST shape + transport support.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request

from gcp_sim.deps import clamp_page_size, require_bearer, validate_prefix
from gcp_sim.routers import store

router = APIRouter(tags=["scc"])


@router.get("/v1/organizations/{org}/sources")
async def list_sources(org: str, request: Request, pageSize: int | None = Query(default=None)) -> dict[str, Any]:  # noqa: N803 - GCP query param casing
    """SCC sources list (TODO-verificar #7)."""
    require_bearer(request)
    validate_prefix(f"organizations/{org}", ("organizations/",), "parent")
    clamp_page_size(pageSize)
    return store(request).get("scc_sources.json")


@router.get("/v1/{parent:path}/findings")
async def list_findings(parent: str, request: Request, pageSize: int | None = Query(default=None)) -> dict[str, Any]:  # noqa: N803 - GCP query param casing
    """SCC findings list under ``organizations/*/sources/*`` (TODO-verificar #7)."""
    require_bearer(request)
    validate_prefix(parent, ("organizations/",), "parent")
    clamp_page_size(pageSize)
    return store(request).get("scc_findings.json")
