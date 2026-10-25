"""Cost Management Query projection: ``properties.columns``/``properties.rows`` (design §5, DISCOVERY §2.3).

Projects ``estate.billing_lines`` into the tabular ``QueryResult`` shape the real
``CostManagementClient.query.usage(...)`` returns (DISCOVERY §2.3): a
``QueryDefinition`` carries an ``aggregation`` (user-chosen alias -> measure)
and a ``grouping`` list of dimensions, and the response echoes **the requested
aliases and dimensions as columns**, in the order the request asked for them.
That is why this module no longer hard-codes ``PreTaxCost``: the column name is
whatever alias the caller sent (CloudPilot asks for
``CostInBillingCurrency``), and the dimension columns are the requested
dimensions — not a fixed four.

This is a NATIVE input (the as-charged cost rows Azure itself returns); it is
never a FinOps-computed output. The money measure is the line's
``billed_cost`` (ActualCost semantics), summed per grouping bucket per period.

Dimension values are projections of the canonical estate, using the same
identity functions the FOCUS renderer uses, so the two surfaces cannot disagree:
``SubscriptionId`` is ``azure_subscription_guid`` of the line's scope label and
the billing/subscription names are the estate's own (unmarked). A dimension the
estate does not carry projects the empty string — absence is absence.

Billing-period dimension values
-------------------------------
For ``granularity=DAILY`` the estate's unit IS the usage day, so
``BillingPeriodStartDate``/``BillingPeriodEndDate`` project that day. This is
deliberate: CloudPilot's Azure mapper derives ``ChargePeriodStart`` from the row
date and falls back to the billing-period start, and its natural key includes
both — projecting a month-long billing period onto a one-day row would collapse
every day of the month onto the same key. ``granularity=MONTHLY`` projects the
line's real billing period.

TODO-verificar §11.6: the exact ``type`` strings are offline-unverifiable
(``"Number"`` vs ``"Numeric"``, ``"DateTime"`` vs ``"Datetime"``); the metadata
is emitted official-shaped and flagged.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any

from tools.synthetic_clouds.generate.constants import PROVIDER_AZURE
from tools.synthetic_clouds.model.billing import BillingLine
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.identity import azure_subscription_guid
from tools.synthetic_clouds.render.markers import unmarked_name

_SIX = Decimal("0.000001")

# Grouping dimensions the previous fixed projection emitted. Kept as the
# default so callers that do not send a grouping (unit tests, smoke checks)
# still get the historical four-dimension shape.
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

# Dimensions a daily/monthly row can carry, derived from the estate. Any other
# requested dimension projects the empty string rather than an invented value.
_DATE_DIMENSIONS: frozenset[str] = frozenset(
    {"BillingPeriodStartDate", "BillingPeriodEndDate"}
)


@dataclass(slots=True, frozen=True)
class _Lookups:
    """Estate-wide names the billing line cannot resolve by itself."""

    seed: int
    subscription_name: dict[str, str]
    billing_account_name: dict[str, str]


def _build_lookups(estate: CanonicalEstate) -> _Lookups:
    return _Lookups(
        seed=estate.seed,
        subscription_name={
            subscription.subscription_id: unmarked_name(subscription.name)
            for group in estate.azure_mgmt_groups
            for subscription in group.subscriptions
        },
        billing_account_name={
            account.billing_account_id: unmarked_name(account.name)
            for account in estate.billing_accounts
        },
    )


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


def _dimension_value(name: str, line: BillingLine, lookups: _Lookups, granularity: str) -> str:
    """Return one dimension's value from the line (empty when not modelled)."""
    if name == "ServiceName":
        return line.service_name
    if name == "MeterCategory":
        # Azure's MeterCategory is the service classification (e.g. "Virtual
        # Machines"), which is exactly what the estate carries as service_name.
        return line.service_name
    if name == "ResourceGroupName":
        return _resource_group_name(line)
    if name == "ResourceLocation":
        return line.region_name
    if name == "ResourceId":
        return _resource_id(line)
    if name == "SubscriptionId":
        return azure_subscription_guid(lookups.seed, line.sub_account_id)
    if name == "SubscriptionName":
        # The hierarchy keys its subscriptions by the same scope label the
        # billing line carries (``sub-01``); the GUID is derived for the id.
        return lookups.subscription_name.get(line.sub_account_id, "")
    if name == "ChargeType":
        return line.charge_category
    if name == "UnitOfMeasure":
        return line.pricing_unit
    if name == "BillingCurrency":
        return line.currency
    if name == "PricingCurrency":
        return line.currency
    if name == "BillingAccountId":
        return line.billing_account_id
    if name == "BillingAccountName":
        return lookups.billing_account_name.get(line.billing_account_id, "")
    if name == "InvoiceId":
        return line.invoice_id or ""
    if name == "BenefitId":
        return line.commitment_discount_id or ""
    if name == "BillingPeriodStartDate":
        return (
            line.billing_period_start
            if granularity == "monthly"
            else line.charge_period_start.date()
        ).isoformat()
    if name == "BillingPeriodEndDate":
        return (
            line.billing_period_end
            if granularity == "monthly"
            else line.charge_period_start.date()
        ).isoformat()
    # Dimensions the estate does not model (PublisherName, ProductName,
    # PricingModel, BillingProfileId, ReservationId, ...) stay empty: a value
    # invented here would be indistinguishable from a real one downstream.
    return ""


def _dimension_values(
    line: BillingLine,
    lookups: _Lookups,
    *,
    dimensions: Sequence[str],
    granularity: str,
) -> tuple[str, ...]:
    """Return the grouping bucket key: one value per requested dimension."""
    return tuple(
        _dimension_value(name, line, lookups, granularity) for name in dimensions
    )


def _column_type(name: str) -> str:
    return _COLUMN_TYPE_DATETIME if name in _DATE_DIMENSIONS else _COLUMN_TYPE_STRING


def build_columns(
    *,
    aggregations: Mapping[str, str] | None = None,
    dimensions: Sequence[str] | None = None,
) -> list[dict[str, str]]:
    """Return ``properties.columns`` in request order (aliases, date, dims, currency)."""
    aliases = list(aggregations if aggregations is not None else {"PreTaxCost": "Cost"})
    dims = list(dimensions if dimensions is not None else GROUPING_DIMENSIONS)
    columns: list[dict[str, str]] = [
        {"name": alias, "type": _COLUMN_TYPE_NUMBER} for alias in aliases
    ]
    columns.append({"name": "UsageDate", "type": _COLUMN_TYPE_DATETIME})
    columns.extend({"name": name, "type": _column_type(name)} for name in dims)
    columns.append({"name": "Currency", "type": _COLUMN_TYPE_STRING})
    return columns


def _measure_value(line: BillingLine, measure: str) -> Decimal:
    """Return the value of one aggregation's source measure for a line."""
    if measure in {"UsageQuantity", "Quantity", "Usage"}:
        return line.pricing_quantity
    # "Cost" is the only measure the estate carries as money; an alias asking
    # for anything else still sums the same as-charged cost, never a zero.
    return line.billed_cost


def build_rows(
    lines: Sequence[BillingLine],
    *,
    granularity: str,
    currency: str,
    aggregations: Mapping[str, str] | None = None,
    dimensions: Sequence[str] | None = None,
    lookups: _Lookups | None = None,
) -> list[list[object]]:
    """Return ``properties.rows`` — one row per (period, requested grouping).

    Each row is ``[<aggregation alias values...>, UsageDate, <dimensions...>,
    Currency]`` matching :func:`build_columns`. Rows are summed per measure and
    deterministically ordered.
    """
    agg = dict(aggregations if aggregations is not None else {"PreTaxCost": "Cost"})
    dims = list(dimensions if dimensions is not None else GROUPING_DIMENSIONS)
    if lookups is None:
        raise ValueError("lookups are required to project dimension values")
    buckets: dict[tuple[str, ...], list[Decimal]] = {}
    for line in lines:
        period = _period_key(line, granularity)
        key = (period.isoformat(), *_dimension_values(line, lookups, dimensions=dims, granularity=granularity))
        sums = buckets.get(key)
        if sums is None:
            sums = [Decimal("0") for _ in agg]
            buckets[key] = sums
        for index, measure in enumerate(agg.values()):
            sums[index] += _measure_value(line, measure)
    ordered = sorted(buckets.items(), key=lambda item: item[0])
    rows: list[list[object]] = []
    for key, sums in ordered:
        period_iso, dimension_values = key[0], list(key[1:])
        rows.append(
            [
                *[float(_money(value)) for value in sums],
                period_iso,
                *dimension_values,
                currency,
            ]
        )
    return rows


def project_cost_query(
    estate: CanonicalEstate,
    *,
    granularity: str = "daily",
    aggregations: Mapping[str, str] | None = None,
    dimensions: Sequence[str] | None = None,
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
    lookups = _build_lookups(estate)
    return {
        "columns": build_columns(aggregations=aggregations, dimensions=dimensions),
        "rows": build_rows(
            azure_lines,
            granularity=granularity,
            currency=estate.currency,
            aggregations=aggregations,
            dimensions=dimensions,
            lookups=lookups,
        ),
    }
