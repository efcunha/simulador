"""Billing Budgets routes (design sec. 5.1).

``GET /v1/billingAccounts/*/budgets`` -- native budget DEFINITIONS (NOT FinOps
budget evaluations; P1). TODO-verificar #7: official response envelope.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request

from gcp_sim.deps import clamp_page_size, require_bearer, validate_prefix
from gcp_sim.routers import store

router = APIRouter(tags=["budgets"])


@router.get("/v1/billingAccounts/{billing_account}/budgets")
async def list_budgets(
    billing_account: str,
    request: Request,
    pageSize: int | None = Query(default=None),  # noqa: N803 - GCP query param casing
) -> dict[str, Any]:
    """Billing Budgets list (native definitions only; TODO-verificar #7)."""
    require_bearer(request)
    validate_prefix(f"billingAccounts/{billing_account}", ("billingAccounts/",), "parent")
    clamp_page_size(pageSize)
    return store(request).get("budgets.json")
