"""Resource Graph router: resources / resourcechanges / securityresources (design §5.1, §8 C11).

POSTs the Resource Graph query envelope; results are projected from
``projections/inventory.py`` (native inventory + IaC-delta change rows). Paging
uses ``$skipToken`` per the Resource Graph continuation convention.

TODO-verificar §11.8: the exact Resource Graph request/response envelope keys and
the ``$skipToken`` placement are NOT offline-verifiable; emitted official-shaped
and flagged.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from azure_sim.api.common import get_estate, get_settings, require_api_version
from azure_sim.api.paging import page_rows_and_link
from azure_sim.projections.inventory import (
    project_resource_changes,
    project_resources,
    project_security_resources,
)

router = APIRouter()

# TODO-verificar §11.8: official Resource Graph api-version strings.
_API_VERSIONS: frozenset[str] = frozenset({"2021-03-01", "2022-10-01", "2024-04-01"})
_TOKEN_FIELD = "$skipToken"  # noqa: S105 - a paging field name, not a credential


def _page(request: Request, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Return the Resource Graph ``{count,data,$skipToken}`` envelope for a page."""
    settings = get_settings(request)
    page_rows, next_link = page_rows_and_link(
        list(rows),
        page_size=settings.api_page_size,
        request_url=str(request.url),
        token_field=_TOKEN_FIELD,
    )
    envelope: dict[str, Any] = {"count": len(page_rows), "data": page_rows}
    if next_link is not None:
        envelope["$skipToken"] = next_link
    return envelope


@router.post("/providers/Microsoft.ResourceGraph/resources")
async def resources(request: Request) -> dict[str, Any]:
    """Return Resource Graph ``resources`` rows (native inventory)."""
    require_api_version(request, _API_VERSIONS)
    return _page(request, project_resources(get_estate(request)))


@router.post("/providers/Microsoft.ResourceGraph/resourcechanges")
async def resource_changes(request: Request) -> dict[str, Any]:
    """Return ``resourcechanges`` rows (drift INPUT: cloud-present, not declared)."""
    require_api_version(request, _API_VERSIONS)
    return _page(request, project_resource_changes(get_estate(request)))


@router.post("/providers/Microsoft.ResourceGraph/securityresources")
async def security_resources(request: Request) -> dict[str, Any]:
    """Return ``securityresources`` rows (native inventory + finding counts)."""
    require_api_version(request, _API_VERSIONS)
    return _page(request, project_security_resources(get_estate(request)))
