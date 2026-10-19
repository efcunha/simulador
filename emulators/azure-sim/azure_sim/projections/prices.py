"""Retail Prices + Price Sheet projections (design §5).

Projects ``estate.list_prices`` into Azure Retail Prices OData items and
``estate.contracted_prices`` into a Cost Management Price Sheet. Both are native
inputs (the published/negotiated unit prices Azure returns); FinOps computes
any rate-optimization output from these (P1).

TODO-verificar §11.11: the exact Retail Prices OData item envelope
(``retailPrice``/``unitOfMeasure``/``armSkuName``/``meterId`` keys) and the Price
Sheet row keys/casing are NOT offline-verifiable. Items are emitted
official-shaped and flagged.
"""

from __future__ import annotations

from tools.synthetic_clouds.model.billing import ContractedPrice, ListPrice
from tools.synthetic_clouds.model.estate import CanonicalEstate


def _retail_item(price: ListPrice) -> dict[str, object]:
    """Project one list price into a Retail Prices OData item."""
    # TODO-verificar §11.11: official Retail Prices OData key names/casing.
    return {
        "skuId": price.sku_id,
        "retailPrice": float(price.unit_price),
        "unitOfMeasure": price.unit,
        "currencyCode": price.currency,
    }


def project_retail_prices(estate: CanonicalEstate) -> list[dict[str, object]]:
    """Return Retail Prices OData items, deterministically ordered by sku+unit."""
    items = [_retail_item(price) for price in estate.list_prices]
    return sorted(items, key=lambda item: (str(item["skuId"]), str(item["unitOfMeasure"])))


def filter_retail_prices(
    items: list[dict[str, object]], *, sku_id: str | None, currency: str | None
) -> list[dict[str, object]]:
    """Apply the OData ``$filter`` subset the sim supports (sku/currency equality).

    The real Retail Prices API supports a broad OData grammar; the sim implements
    the equality predicates FinOps clients use. Unsupported predicates are
    ignored (the sim is permissive on the filter grammar, strict on the shape).
    """
    result = items
    if sku_id is not None:
        result = [item for item in result if item["skuId"] == sku_id]
    if currency is not None:
        result = [item for item in result if item["currencyCode"] == currency]
    return result


def _price_sheet_row(price: ContractedPrice) -> dict[str, object]:
    """Project one contracted price into a Price Sheet row."""
    # TODO-verificar §11.11: official Price Sheet row key names/casing.
    return {
        "skuId": price.sku_id,
        "unitPrice": float(price.unit_price),
        "unitOfMeasure": price.unit,
        "currencyCode": price.currency,
        "commitmentId": price.commitment_id,
    }


def project_price_sheet(estate: CanonicalEstate) -> list[dict[str, object]]:
    """Return Price Sheet rows from contracted prices, deterministically ordered."""
    rows = [_price_sheet_row(price) for price in estate.contracted_prices]
    return sorted(rows, key=lambda row: (str(row["skuId"]), str(row["unitOfMeasure"])))
