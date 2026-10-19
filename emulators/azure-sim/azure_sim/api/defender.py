"""Defender for Cloud router: assessments / secureScores / alerts (design §5.1, §8 C09).

Projected from ``projections/findings.py`` (native findings; UPPERCASE severity
preserved). List endpoints page via ``nextLink``.

TODO-verificar §11.9: the exact Defender ``value[]`` envelope keys and api-version
strings are NOT offline-verifiable; emitted official-shaped and flagged.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from azure_sim.api.common import get_estate, require_api_version, value_page
from azure_sim.projections.findings import (
    project_alerts,
    project_assessments,
    project_secure_scores,
)

router = APIRouter()

# TODO-verificar §11.9: official Defender api-version strings.
_API_VERSIONS: frozenset[str] = frozenset({"2021-06-01", "2023-01-01"})


@router.get("/{scope:path}/providers/Microsoft.Security/assessments")
async def assessments(request: Request, scope: str = "") -> dict[str, Any]:
    """Return Defender ``assessments`` (native findings, UPPERCASE severity)."""
    require_api_version(request, _API_VERSIONS)
    return value_page(request, project_assessments(get_estate(request)))


@router.get("/{scope:path}/providers/Microsoft.Security/secureScores")
async def secure_scores(request: Request, scope: str = "") -> dict[str, Any]:
    """Return native ``secureScores`` (finding counts, not a FinOps score)."""
    require_api_version(request, _API_VERSIONS)
    return value_page(request, project_secure_scores(get_estate(request)))


@router.get("/{scope:path}/providers/Microsoft.Security/alerts")
async def alerts(request: Request, scope: str = "") -> dict[str, Any]:
    """Return Defender ``alerts`` (CRITICAL/HIGH finding subset)."""
    require_api_version(request, _API_VERSIONS)
    return value_page(request, project_alerts(get_estate(request)))
