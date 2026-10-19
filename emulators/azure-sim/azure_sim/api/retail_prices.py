"""Retail Prices router: OData retail prices (design §5.1).

``GET .../api/retail/prices`` with OData ``$filter``/``$top`` and ``NextPageLink``
paging. Projected from ``projections/prices.py`` (native list prices). This is the
public Retail Prices API: it is NOT scoped by subscription and does NOT require an
``api-version`` query param in the same way the ARM control plane does — it uses
an optional ``api-version`` path/arg. The sim accepts the known versions and
defaults permissively.

TODO-verificar §11.11: the exact Retail Prices OData item keys, the ``Items`` vs
``value`` envelope key, and the ``NextPageLink`` field are NOT offline-verifiable;
emitted official-shaped and flagged.
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Request

from azure_sim.api.common import get_estate, get_settings
from azure_sim.api.paging import page_rows_and_link
from azure_sim.projections.prices import filter_retail_prices, project_retail_prices

router = APIRouter()

_NEXT_LINK_FIELD = "NextPageLink"

# Equality predicates the sim supports from the OData $filter grammar.
_SKU_EQ = re.compile(r"skuId\s+eq\s+'([^']*)'", re.IGNORECASE)
_CURRENCY_EQ = re.compile(r"currencyCode\s+eq\s+'([^']*)'", re.IGNORECASE)


def _parse_filter(odata_filter: str | None) -> tuple[str | None, str | None]:
    """Extract the ``skuId``/``currencyCode`` equality predicates from ``$filter``.

    The real Retail Prices API supports a broad OData grammar; the sim implements
    the equality predicates FinOps clients use and ignores the rest.
    """
    if not odata_filter:
        return None, None
    sku_match = _SKU_EQ.search(odata_filter)
    currency_match = _CURRENCY_EQ.search(odata_filter)
    sku = sku_match.group(1) if sku_match else None
    currency = currency_match.group(1) if currency_match else None
    return sku, currency


@router.get("/api/retail/prices")
async def retail_prices(request: Request) -> dict[str, Any]:
    """Return Retail Prices OData items with ``$filter``/``NextPageLink`` paging."""
    estate = get_estate(request)
    settings = get_settings(request)
    sku_id, currency = _parse_filter(request.query_params.get("$filter"))
    items = filter_retail_prices(project_retail_prices(estate), sku_id=sku_id, currency=currency)
    page_rows, next_link = page_rows_and_link(
        list(items),
        page_size=settings.api_page_size,
        request_url=str(request.url),
        token_field=_NEXT_LINK_FIELD,
    )
    envelope: dict[str, Any] = {"Items": page_rows}
    if next_link is not None:
        envelope["NextPageLink"] = next_link
    return envelope
