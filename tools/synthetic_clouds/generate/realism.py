"""Realism injectors: untagged, off-standard names, duplicate lines, null line.

FR-D2 ~15% untagged; FR-D3 off-standard names; FR-D4 benign duplicate export
lines; FR-D5 one billing-only null-resource line (``resource_uuid=None``, empty
FOCUS ``ResourceId``). Per F2 the null-resource line has NO backing consumption,
inventory, finding, recommendation, metric, or IaC — it is a pure billing
construct (tax/marketplace/fee).

All functions are deterministic given the passed RNG stream (NFR-1).
"""

from __future__ import annotations

import random
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from tools.synthetic_clouds.clock import export_time_for
from tools.synthetic_clouds.model.billing import BillingLine
from tools.synthetic_clouds.model.identity import IdentityFactory
from tools.synthetic_clouds.model.resource import Resource
from tools.synthetic_clouds.render.markers import source_fingerprint

_UNTAGGED_FRACTION = 0.15
_DUPLICATE_FRACTION = 0.02
_OFF_STANDARD_FRACTION = 0.20
_MIDDAY = time(12, 0, 0)

# A few off-standard name templates (FR-D3): names that break the convention.
_OFF_STANDARD_TEMPLATES = (
    "{base}_FINAL_v2",
    "TEMP-{base}",
    "{base} (do not delete)",
    "prod{base}COPY",
)


def off_standard_name(base_name: str, rng: random.Random) -> str:
    """Return ``base_name`` or, for ~20% (seeded), an off-standard variant (FR-D3)."""
    if rng.random() >= _OFF_STANDARD_FRACTION:
        return base_name
    template = rng.choice(_OFF_STANDARD_TEMPLATES)
    return template.format(base=base_name)


def apply_untagged(resources: list[Resource], rng: random.Random) -> list[Resource]:
    """Return ``resources`` with ~15% (seeded) stripped of all tags (FR-D2).

    Selection is a deterministic sample of indices from the provided RNG stream;
    the input order is preserved so downstream identity threading is unaffected.
    """
    count = int(round(len(resources) * _UNTAGGED_FRACTION))
    if count == 0:
        return list(resources)
    untagged_idx = set(rng.sample(range(len(resources)), count))
    return [replace(r, tags=()) if i in untagged_idx else r for i, r in enumerate(resources)]


def duplicate_billing_lines(billing: list[BillingLine], rng: random.Random) -> list[BillingLine]:
    """Append benign duplicate copies of ~2% (seeded) of billing lines (FR-D4).

    The copy carries ``is_duplicate=True`` and a distinct ``line_id`` (``:dup``
    suffix). The parser's groupby sums duplicates; the flag exists only so a test
    can find them.
    """
    count = int(round(len(billing) * _DUPLICATE_FRACTION))
    if count == 0:
        return list(billing)
    dup_idx = sorted(rng.sample(range(len(billing)), count))
    result = list(billing)
    for i in dup_idx:
        original = billing[i]
        result.append(
            replace(
                original,
                line_id=f"{original.line_id}:dup",
                is_duplicate=True,
                source_fingerprint=source_fingerprint(f"{original.line_id}:dup"),
            )
        )
    return result


def make_null_resource_line(
    *,
    identity: IdentityFactory,
    billing_account_id: str,
    sub_account_id: str,
    day: date,
    currency: str,
    provider_name: str,
) -> BillingLine:
    """Return the single FR-D5 null-resource billing line (billing-only construct).

    ``resource_uuid=None`` -> the renderer emits an empty FOCUS ``ResourceId`` and
    ingestion owns the unallocated sentinel (OA-4). Per F2 this line has NO backing
    consumption/inventory/finding/recommendation/metric/IaC, and the gate asserts
    it is the ONLY ``None``-resource billing row. Modeled as a ``Tax`` charge.
    """
    line_id = identity.uuid_for(f"line/null-resource/{day.isoformat()}/Tax")
    charge_start = datetime.combine(day, _MIDDAY, tzinfo=UTC)
    amount = Decimal("12.500000")
    return BillingLine(
        line_id=line_id,
        resource_uuid=None,
        billing_account_id=billing_account_id,
        sub_account_id=sub_account_id,
        invoice_id=None,
        service_name="Tax",
        service_category="Other",
        charge_category="Tax",
        charge_period_start=charge_start,
        charge_period_end=charge_start + timedelta(days=1),
        billing_period_start=day.replace(day=1),
        billing_period_end=_month_end(day),
        export_time=export_time_for(day),
        is_restatement=False,
        restates_date=None,
        billed_cost=amount,
        effective_cost=amount,
        list_cost=amount,
        contracted_cost=amount,
        pricing_quantity=Decimal("1.000000"),
        pricing_unit="Charge",
        pricing_category="Standard",
        # A real tax/fee export line still carries a region (often "global"); only the
        # ResourceId is empty (FR-D5 / OA-4). An empty CSV region decodes as NaN and
        # breaks the parser's per-account unallocated sentinel, so emit "global".
        region_id="global",
        region_name="Global",
        tags=(),
        commitment_discount_id=None,
        commitment_discount_status=None,
        currency=currency,
        service_provider_name=provider_name,
        is_duplicate=False,
        source_fingerprint=source_fingerprint(line_id),
    )


def _month_end(day: date) -> date:
    if day.month == 12:
        return date(day.year + 1, 1, 1)
    return date(day.year, day.month + 1, 1)
