"""Advisor router: recommendations (design §5.1).

Projected from ``projections/recommendations.py`` (native recommendations). Pages
via ``nextLink``.

TODO-verificar §11.10: the exact Advisor ``value[]`` envelope keys and api-version
strings are NOT offline-verifiable; emitted official-shaped and flagged.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from azure_sim.api.common import get_estate, require_api_version, value_page
from azure_sim.projections.recommendations import project_recommendations

router = APIRouter()

# TODO-verificar §11.10: official Advisor api-version strings.
_API_VERSIONS: frozenset[str] = frozenset({"2020-01-01", "2023-01-01"})


@router.get("/{scope:path}/providers/Microsoft.Advisor/recommendations")
async def recommendations(request: Request, scope: str = "") -> dict[str, Any]:
    """Return Advisor ``recommendations`` (native recommendations)."""
    require_api_version(request, _API_VERSIONS)
    return value_page(request, project_recommendations(get_estate(request)))
