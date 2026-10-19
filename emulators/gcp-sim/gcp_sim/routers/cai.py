"""Cloud Asset Inventory routes (design sec. 5.1).

``POST /v1/{scope}:searchAllResources`` / ``:searchAllIamPolicies`` /
``:analyzeIamPolicy`` -- native inputs from the estate's inventory. The ``{scope}``
path param must be ``organizations/*|projects/*|billingAccounts/*`` (400 on
mismatch); a bearer is required (401 on missing). TODO-verificar #7: official
verb+route + response envelope.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from gcp_sim.deps import require_bearer, validate_prefix
from gcp_sim.routers import store

router = APIRouter(tags=["cai"])

_SCOPE_PREFIXES = ("organizations/", "projects/", "folders/", "billingAccounts/")


@router.post("/v1/{scope:path}:searchAllResources")
async def search_all_resources(scope: str, request: Request) -> dict[str, Any]:
    """CAI searchAllResources (TODO-verificar #7)."""
    require_bearer(request)
    validate_prefix(scope, _SCOPE_PREFIXES, "scope")
    return store(request).get("cai_search_all_resources.json")


@router.post("/v1/{scope:path}:searchAllIamPolicies")
async def search_all_iam_policies(scope: str, request: Request) -> dict[str, Any]:
    """CAI searchAllIamPolicies (TODO-verificar #7)."""
    require_bearer(request)
    validate_prefix(scope, _SCOPE_PREFIXES, "scope")
    return store(request).get("cai_search_all_iam_policies.json")


@router.post("/v1/{scope:path}:analyzeIamPolicy")
async def analyze_iam_policy(scope: str, request: Request) -> dict[str, Any]:
    """CAI analyzeIamPolicy (TODO-verificar #7)."""
    require_bearer(request)
    validate_prefix(scope, _SCOPE_PREFIXES, "scope")
    return store(request).get("cai_analyze_iam_policy.json")
