"""Policy Insights router: policyStates / policyEvents (design §5.1).

Emits NATIVE policy states/events only (compliance states Azure Policy reports),
derived from inventory + findings. FinOps computes any policy VERDICT from
these inputs (P1); this never emits a FinOps compliance verdict.

A resource with an open finding is projected as a ``NonCompliant`` native policy
state; all other inventoried resources are ``Compliant``. This is the raw
compliance-state input, not a scored verdict.

TODO-verificar §11.8: the exact Policy Insights ``value[]`` envelope keys, the
``complianceState`` vocabulary, and api-version strings are NOT offline-
verifiable; emitted official-shaped and flagged.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from azure_sim.api.common import get_estate, require_api_version, value_page

router = APIRouter()

# TODO-verificar §11.8: official Policy Insights api-version strings.
_API_VERSIONS: frozenset[str] = frozenset({"2019-10-01", "2024-10-01"})

# TODO-verificar §11.8: official complianceState vocabulary.
_STATE_NON_COMPLIANT = "NonCompliant"
_STATE_COMPLIANT = "Compliant"


def _policy_states(estate: Any) -> list[dict[str, Any]]:
    """Project per-resource native compliance states (NonCompliant if a finding)."""
    flagged = {finding.resource_uuid for finding in estate.findings}
    rows: list[dict[str, Any]] = []
    for asset in estate.inventory:
        state = _STATE_NON_COMPLIANT if asset.resource_uuid in flagged else _STATE_COMPLIANT
        rows.append(
            {
                "resourceId": asset.resource_uuid,
                "resourceType": asset.asset_type,
                "complianceState": state,
            }
        )
    return sorted(rows, key=lambda row: str(row["resourceId"]))


def _policy_events(estate: Any) -> list[dict[str, Any]]:
    """Project native policy events — one per non-compliant resource."""
    return [row for row in _policy_states(estate) if row["complianceState"] == _STATE_NON_COMPLIANT]


@router.post("/{scope:path}/providers/Microsoft.PolicyInsights/policyStates/{state_name}/queryResults")
async def policy_states(request: Request, state_name: str, scope: str = "") -> dict[str, Any]:
    """Return native policy compliance states (NOT a FinOps verdict)."""
    require_api_version(request, _API_VERSIONS)
    return value_page(request, _policy_states(get_estate(request)))


@router.post("/{scope:path}/providers/Microsoft.PolicyInsights/policyEvents/{event_name}/queryResults")
async def policy_events(request: Request, event_name: str, scope: str = "") -> dict[str, Any]:
    """Return native policy events for non-compliant resources."""
    require_api_version(request, _API_VERSIONS)
    return value_page(request, _policy_events(get_estate(request)))
