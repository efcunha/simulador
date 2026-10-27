"""Deployment Stacks what-if results (``management.azure.com``).

Official path: ``GET /subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/
providers/Microsoft.Resources/deploymentStacksWhatIfResults/{deploymentStacksWhatIfResultName}
?api-version=2025-07-01``.

The result is projected by
:func:`tools.synthetic_clouds.model.drift.project_drift_views` from the frozen estate: the
C11 inputs (declared tags in the IaC snapshot vs. the inventory, plus ``managed_by_iac``)
are the only source. ``modify`` carries a ``delta[]`` per tag; ``detach`` is the provider
vocabulary for an Azure resource that exists but is no longer managed by the stack.

A list endpoint is served too because a consumer that only knows the resource group needs
to discover the result name; both routes share one projection and one api-version gate.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from azure_sim.api.common import (
    CODE_NOT_FOUND,
    AzureApiError,
    get_estate,
    require_api_version,
    value_page,
)
from tools.synthetic_clouds.model.drift import azure_what_if_document, project_drift_views

router = APIRouter()

#: The version the REST reference for deploymentStacksWhatIfResults publishes.
_WHAT_IF_VERSIONS: frozenset[str] = frozenset({"2025-07-01"})


def _results(request: Request) -> list[dict[str, Any]]:
    return [
        azure_what_if_document(item)
        for item in project_drift_views(get_estate(request)).azure_what_if_results
    ]


@router.get(
    "/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
    "/providers/Microsoft.Resources/deploymentStacksWhatIfResults"
)
async def list_what_if_results(
    subscription_id: str, resource_group: str, request: Request
) -> dict[str, Any]:
    """List the what-if results of one resource group."""
    require_api_version(request, _WHAT_IF_VERSIONS)
    prefix = (
        f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
        "/providers/Microsoft.Resources/deploymentStacksWhatIfResults/"
    )
    rows = [row for row in _results(request) if str(row["id"]).startswith(prefix)]
    return value_page(request, rows)


@router.get(
    "/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
    "/providers/Microsoft.Resources/deploymentStacksWhatIfResults/{name}"
)
async def get_what_if_result(
    subscription_id: str, resource_group: str, name: str, request: Request
) -> dict[str, Any]:
    """Get one what-if result by the name in its ARM id."""
    require_api_version(request, _WHAT_IF_VERSIONS)
    expected = (
        f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
        f"/providers/Microsoft.Resources/deploymentStacksWhatIfResults/{name}"
    )
    for row in _results(request):
        if row["id"] == expected:
            return row
    raise AzureApiError(
        404,
        code=CODE_NOT_FOUND,
        message=f"deploymentStacksWhatIfResults not found: {expected}",
    )
