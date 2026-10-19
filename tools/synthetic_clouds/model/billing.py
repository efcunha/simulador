"""Consumption, prices, and billing lines (design sec. 4.4-4.5).

The ``BillingLine`` is the fact table the renderers project from.

F2 (design-review must-fix): ``DailyConsumption.resource_uuid`` is NON-nullable
``str`` — every consumption row references a real resource identity. The FR-D5
null-resource ``BillingLine`` is a billing-only construct (tax/marketplace/fee)
with ``resource_uuid=None`` and NO backing consumption/inventory/finding/
recommendation/metric/IaC. The no-orphan gate inspects only non-None
``resource_uuid`` and asserts the FR-D5 line is the only ``None``-resource
billing row.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(slots=True, frozen=True)
class DailyConsumption:
    """One day of usage for a resource (FR-D1, FR-B2 latency).

    ``resource_uuid`` is non-nullable (F2): consumption is never generated for the
    FR-D5 null-resource billing line.
    """

    resource_uuid: str  # FK -> ResourceIdentity.uuid (NON-nullable, F2)
    usage_date: date  # the charge/usage day D
    export_time: datetime  # availability: D+1 00:00 UTC (FR-B2 latency)
    quantity: Decimal
    unit: str
    is_restatement: bool  # FR-B3: later export_time, original row intact
    restates_date: date | None  # the usage_date this row restates (if any)


@dataclass(slots=True, frozen=True)
class ListPrice:
    """A SKU list unit price."""

    sku_id: str
    unit: str
    unit_price: Decimal
    currency: str


@dataclass(slots=True, frozen=True)
class ContractedPrice:
    """A negotiated/contracted unit price (<= list)."""

    sku_id: str
    unit: str
    unit_price: Decimal  # <= corresponding ListPrice.unit_price
    currency: str
    commitment_id: str | None  # FK -> Commitment when discount comes from one


@dataclass(slots=True, frozen=True)
class BillingLine:
    """A FOCUS/BQ projection source row (design sec. 4.5).

    One line per ``(resource_uuid, usage_date, charge_category, export_time)`` plus
    deliberate duplicates (FR-D4) and the null-resource line (FR-D5).
    ``resource_uuid is None`` marks the sanctioned FR-D5 null-resource line and is
    exempt from the no-orphan check (design sec. 9).
    """

    line_id: str  # deterministic natural key (UUIDv5)
    resource_uuid: str | None  # None => sanctioned FR-D5 null line; exempt from no-orphan
    billing_account_id: str  # FK -> BillingAccount
    sub_account_id: str  # Azure subscription_id / GCP project_id
    invoice_id: str | None  # None until invoice issued (Estimated vs Issued)
    service_name: str
    service_category: str
    charge_category: str  # Usage|Purchase|Tax|Credit|Adjustment (FR-G1a)
    charge_period_start: datetime
    charge_period_end: datetime
    billing_period_start: date
    billing_period_end: date
    export_time: datetime  # D+1; restatements carry a later export_time
    is_restatement: bool  # FR-B3: this line restates an earlier usage_date
    restates_date: date | None  # the usage_date restated (None unless is_restatement)
    billed_cost: Decimal
    effective_cost: Decimal
    list_cost: Decimal
    contracted_cost: Decimal
    pricing_quantity: Decimal
    pricing_unit: str
    pricing_category: str  # "Standard" | "Committed" (changes mid-period, C16)
    region_id: str
    region_name: str
    tags: tuple[tuple[str, str], ...]
    commitment_discount_id: str | None
    commitment_discount_status: str | None  # Used | Unused (C05)
    currency: str
    service_provider_name: str  # "Microsoft Azure" | "Google Cloud" (FR-G1b)
    is_duplicate: bool  # FR-D4 benign duplicate marker (for tests)
    source_fingerprint: str  # "synth:..." prefix (NFR-3)
    k8s_namespace: str | None = None  # C15: set only on AKS/GKE namespace-share lines
