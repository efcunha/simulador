"""The Cost Explorer projection: cost and usage CALCULATED from the estate's AWS lines.

CE is not a fixture — it is the same canonical billing lines the CUR promoter consumes,
aggregated on demand. That is what makes it coherent (FR-8): ``UnblendedCost`` is the
line's ``billed_cost``, so the CE total for a period equals the CUR total for the same
period by construction, and a divergence can only come from a scenario that asks for one.

The operations covered are the ones FinOps actually calls (audit ``DISCOVERY.md:719``):
``GetCostAndUsage`` and ``GetDimensionValues``. Grouping honors the request's
``Granularity``, ``GroupBy`` and ``TimePeriod``; an absent group yields the ``Total``.

No fabricated zeros: a period with no lines yields no result entry, never a ``0.0`` row
(NFR "absence is absence").
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from tools.synthetic_clouds.model.billing import BillingLine
from tools.synthetic_clouds.model.estate import CanonicalEstate

GRANULARITY_DAILY = "DAILY"
GRANULARITY_MONTHLY = "MONTHLY"

_AWS_PROVIDER = "Amazon Web Services"

#: CE metric name -> the canonical line field it reads. Coherent with CUR (FR-8).
_METRIC_FIELD: dict[str, str] = {
    "UnblendedCost": "billed_cost",
    "AmortizedCost": "effective_cost",
    "BlendedCost": "list_cost",
}

#: CE dimension key -> the line field that carries it.
_DIMENSION_FIELD: dict[str, str] = {
    "SERVICE": "service_name",
    "LINKED_ACCOUNT": "sub_account_id",
    "REGION": "region_id",
}

_DEFAULT_METRIC = "UnblendedCost"


def _aws_lines(estate: CanonicalEstate) -> list[BillingLine]:
    return [line for line in estate.billing_lines if line.service_provider_name == _AWS_PROVIDER]


def parse_day(value: Any) -> date:
    """Parse a CE ``TimePeriod`` bound, which the client sends as ``YYYY-MM-DD``."""
    return date.fromisoformat(str(value)[:10])


def _filter_lines(estate: CanonicalEstate, start: date, end: date) -> list[BillingLine]:
    """AWS lines whose charge day falls in ``[start, end)`` — CE's exclusive end."""
    return [line for line in _aws_lines(estate) if start <= line.charge_period_start.date() < end]


def _bucket_start(day: date, granularity: str) -> date:
    if granularity == GRANULARITY_MONTHLY:
        return day.replace(day=1)
    return day


def _bucket_end(start: date, granularity: str) -> date:
    if granularity == GRANULARITY_MONTHLY:
        if start.month == 12:
            return date(start.year + 1, 1, 1)
        return date(start.year, start.month + 1, 1)
    return start + timedelta(days=1)


def _group_keys(line: BillingLine, group_by: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
    if not group_by:
        return ()
    field = _DIMENSION_FIELD.get(str(group_by[0].get("Key", "")).upper())
    if field is None:
        return ()
    value = getattr(line, field, None)
    return (str(value),) if value else ()


def _amount(value: Decimal) -> str:
    """Format a cost amount the way CE does: a high-precision decimal string."""
    return f"{value:.10f}"


def get_cost_and_usage(
    estate: CanonicalEstate,
    *,
    time_period: Mapping[str, Any],
    granularity: str,
    metrics: Sequence[str] | None,
    group_by: Sequence[Mapping[str, Any]] | None,
) -> dict[str, Any]:
    """The ``GetCostAndUsage`` result, bucketed and grouped as requested."""
    start = parse_day(time_period.get("Start"))
    end = parse_day(time_period.get("End"))
    names = [name for name in (metrics or [_DEFAULT_METRIC]) if name in _METRIC_FIELD] or [_DEFAULT_METRIC]

    # bucket -> group keys -> metric -> summed amount
    buckets: dict[date, dict[tuple[str, ...], dict[str, Decimal]]] = {}
    units: dict[str, str] = {}
    for line in _filter_lines(estate, start, end):
        bucket = _bucket_start(line.charge_period_start.date(), granularity)
        keys = _group_keys(line, group_by or [])
        sums = buckets.setdefault(bucket, {}).setdefault(keys, dict.fromkeys(names, Decimal("0")))
        for name in names:
            sums[name] += getattr(line, _METRIC_FIELD[name])
            units[name] = line.currency

    results: list[dict[str, Any]] = []
    for bucket in sorted(buckets):
        total: dict[str, Any] = {}
        groups: list[dict[str, Any]] = []
        for keys, sums in sorted(buckets[bucket].items()):
            rendered = {name: {"Amount": _amount(value), "Unit": units[name]} for name, value in sums.items()}
            if keys:
                groups.append({"Keys": list(keys), "Metrics": rendered})
            else:
                total = rendered
        results.append(
            {
                "TimePeriod": {"Start": bucket.isoformat(), "End": _bucket_end(bucket, granularity).isoformat()},
                "Total": total,
                "Groups": groups,
                "Estimated": False,
            },
        )

    group_definitions = [
        {"Type": str(group_by[0].get("Type", "DIMENSION")), "Key": str(group_by[0].get("Key", "")).upper()}
        for _ in [0]
    ] if group_by else []
    return {
        "GroupDefinitions": group_definitions,
        "ResultsByTime": results,
        "DimensionValueAttributes": [],
    }


def get_dimension_values(
    estate: CanonicalEstate,
    *,
    time_period: Mapping[str, Any],
    dimension: str,
    search_string: str = "",
) -> dict[str, Any]:
    """The ``GetDimensionValues`` result: the distinct values of one dimension."""
    start = parse_day(time_period.get("Start"))
    end = parse_day(time_period.get("End"))
    field = _DIMENSION_FIELD.get((dimension or "").upper())
    values: set[str] = set()
    if field is not None:
        for line in _filter_lines(estate, start, end):
            value = getattr(line, field, None)
            if value:
                values.add(str(value))
    if search_string:
        needle = search_string.lower()
        values = {value for value in values if needle in value.lower()}
    rows = [{"Value": value, "Attributes": {}} for value in sorted(values)]
    return {"DimensionValues": rows, "ReturnSize": len(rows), "TotalSize": len(rows)}
