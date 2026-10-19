"""Cost Management Query projection: ``properties.columns``/``properties.rows`` (design §5, DISCOVERY §2.3).

Projects ``estate.billing_lines`` into the tabular ``QueryResult`` shape the real
``CostManagementClient.query.usage(...)`` returns (DISCOVERY §2.3):
``QueryDefinition(type="ActualCost", granularity=DAILY|MONTHLY,
aggregation={"totalCost": Sum of "Cost"}, grouping=[Dimension:
ServiceName|ResourceGroupName|ResourceLocation|ResourceId])``.

This is a NATIVE input (the as-charged cost rows Azure itself returns); it is
never a FinOps-computed output. The money measure is the line's
``billed_cost`` (ActualCost semantics), summed per grouping bucket per period.

TODO-verificar §11.6: the exact dimension name spellings Azure returns in the
``columns`` metadata (``ServiceName`` vs ``MeterCategory`` etc.), the column
``type`` strings, and whether the currency/period columns carry Azure-specific
casing are NOT offline-verifiable. The grouping literals here come straight from
DISCOVERY §2.3; the column metadata is emitted official-shaped and flagged.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any

from tools.synthetic_clouds.generate.constants import PROVIDER_AZURE
from tools.synthetic_clouds.model.billing import BillingLine
from tools.synthetic_clouds.model.estate import CanonicalEstate

_SIX = Decimal("0.000001")

# Grouping dimensions, verbatim from DISCOVERY §2.3. TODO-verificar §11.6: exact
# Azure QueryResult column-name spellings for each dimension.
GROUPING_DIMENSIONS: tuple[str, ...] = (
    "ServiceName",
    "ResourceGroupName",
    "ResourceLocation",
    "ResourceId",
)

# Column metadata types. TODO-verificar §11.6: Azure's exact ``type`` strings
# (e.g. "Number" vs "Numeric", "DateTime" vs "Datetime").
_COLUMN_TYPE_NUMBER = "Number"
_COLUMN_TYPE_STRING = "String"
_COLUMN_TYPE_DATETIME = "DateTime"

_GRANULARITIES: frozenset[str] = frozenset({"daily", "monthly"})


def _money(value: Decimal) -> Decimal:
    return value.quantize(_SIX, ROUND_HALF_EVEN)


def _resource_group_name(line: BillingLine) -> str:
    """Derive a ResourceGroupName dimension value from the resource identity.

    The FR-D5 null-resource line has no resource group (empty, mirroring the
    FOCUS renderer's empty ResourceId for that line).
    """
    if line.resource_uuid is None:
        return ""
    # Native rows group by the subscription scope's resource group; the estate
    # does not model a separate RG string, so the sub-account scopes the bucket.
    return line.sub_account_id


def _resource_id(line: BillingLine) -> str:
    return "" if line.resource_uuid is None else line.resource_uuid


def _period_key(line: BillingLine, granularity: str) -> date:
    """Return the period bucket key for the granularity."""
    if granularity == "monthly":
        return line.billing_period_start
    return line.charge_period_start.date()


def _dimension_values(line: BillingLine, granularity: str) -> tuple[str, str, str, str, date]:
    """Return the (service, rg, location, resource_id, period) bucket key."""
    return (
        line.service_name,
        _resource_group_name(line),
        line.region_name,
        _resource_id(line),
        _period_key(line, granularity),
    )


def build_columns() -> list[dict[str, str]]:
    """Return the ``properties.columns`` metadata list (official-shaped, §11.6)."""
    columns: list[dict[str, str]] = [
        {"name": "PreTaxCost", "type": _COLUMN_TYPE_NUMBER},
        {"name": "UsageDate", "type": _COLUMN_TYPE_DATETIME},
    ]
    columns.extend({"name": dim, "type": _COLUMN_TYPE_STRING} for dim in GROUPING_DIMENSIONS)
    columns.append({"name": "Currency", "type": _COLUMN_TYPE_STRING})
    return columns


def _row_order_key(bucket: tuple[str, str, str, str, date]) -> tuple[str, str, str, str, str]:
    """Deterministic row sort key (period first, then dimensions), all as str."""
    service, rg, location, resource_id, period = bucket
    return (period.isoformat(), service, rg, location, resource_id)


def build_rows(
    lines: Sequence[BillingLine], *, granularity: str, currency: str
) -> list[list[object]]:
    """Return ``properties.rows`` — one row per (period, grouping) bucket.

    ``granularity`` is ``daily`` or ``monthly``. Each row is
    ``[PreTaxCost, UsageDate, ServiceName, ResourceGroupName, ResourceLocation,
    ResourceId, Currency]`` matching :func:`build_columns`. Rows are summed over
    ``billed_cost`` (ActualCost) and deterministically ordered.
    """
    buckets: dict[tuple[str, str, str, str, date], Decimal] = {}
    for line in lines:
        key = _dimension_values(line, granularity)
        buckets[key] = buckets.get(key, Decimal("0")) + line.billed_cost
    ordered = sorted(buckets.items(), key=lambda item: _row_order_key(item[0]))
    rows: list[list[object]] = []
    for (service, rg, location, resource_id, period), total in ordered:
        rows.append(
            [
                float(_money(total)),
                period.isoformat(),
                service,
                rg,
                location,
                resource_id,
                currency,
            ]
        )
    return rows


def project_cost_query(
    estate: CanonicalEstate, *, granularity: str = "daily"
) -> dict[str, Any]:
    """Return ``{columns, rows}`` for the Query API (native ActualCost shape).

    ``granularity`` defaults to ``daily``; ``monthly`` buckets by billing period.
    Raises :class:`ValueError` on an unknown granularity (routers map it to a 400
    Azure envelope).

    Only this tenant's own lines are projected. The canonical estate carries every
    provider's billing lines, and the export renderer has always filtered to
    ``Microsoft Azure`` (``render/focus_azure.py``); this projection did not, so the
    Cost Management Query API answered with AWS and GCP services mixed in (observed:
    ``AWS Lambda``, region ``South America (Sao Paulo)``). That is not cosmetic: this
    endpoint is the reference FinOps ingestion compares its Azure-only promoted
    total against, so the mixture guaranteed a permanent parity mismatch.
    """
    if granularity not in _GRANULARITIES:
        raise ValueError(f"granularity must be one of {sorted(_GRANULARITIES)}, got {granularity!r}")
    azure_lines = [
        line for line in estate.billing_lines if line.service_provider_name == PROVIDER_AZURE
    ]
    return {
        "columns": build_columns(),
        "rows": build_rows(azure_lines, granularity=granularity, currency=estate.currency),
    }
