"""Actual / Amortized Cost Management column projections (design §4.1, §4.5).

Unlike the FOCUS export (which is the Phase 1 renderer bytes UNCHANGED), the
classic Actual/Amortized Cost Management exports are projected here from
``BillingLine``. Both are pure projections over the frozen estate; no clock, no
FinOps-computed output.

Actual cost: the as-charged cost (``billed_cost``). Amortized cost: the
commitment-amortized measure (``effective_cost``), which spreads committed
purchase cost across usage per FOCUS semantics.

TODO-verificar §11.3: the exact Azure column HEADER names for Actual and
Amortized exports, and the MCA vs EA differences in those headers, are NOT
offline-verifiable. The two header maps below are emitted as official-SHAPED
best effort and flagged; only the measure chosen per column (billed vs
effective) is pinned.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import ROUND_HALF_EVEN, Decimal

from tools.synthetic_clouds.model.billing import BillingLine

_SIX = Decimal("0.000001")

# Shared logical column set (same keys for Actual and Amortized; only the cost
# column's source measure differs). TODO-verificar §11.3: official header names.
_MCA_HEADERS: dict[str, str] = {
    "billing_account_id": "BillingAccountId",
    "sub_account_id": "SubscriptionId",
    "service_name": "ServiceName",
    "region": "ResourceLocation",
    "resource_id": "ResourceId",
    "charge_period_start": "Date",
    "cost": "CostInBillingCurrency",
    "currency": "BillingCurrency",
    "charge_category": "ChargeType",
}

# EA headers differ from MCA (design §4.5). TODO-verificar §11.3: exact spellings.
_EA_HEADERS: dict[str, str] = {
    "billing_account_id": "BillingAccountId",
    "sub_account_id": "SubscriptionGuid",
    "service_name": "MeterCategory",
    "region": "ResourceLocation",
    "resource_id": "InstanceId",
    "charge_period_start": "Date",
    "cost": "Cost",
    "currency": "Currency",
    "charge_category": "ChargeType",
}

# Dataset version tags used in the manifest fingerprint (§4.2) per export type.
ACTUAL_DATASET_VERSION = "actualcost-v1"
AMORTIZED_DATASET_VERSION = "amortizedcost-v1"


def headers_for(agreement: str) -> dict[str, str]:
    """Return the logical->official header map for the agreement (§4.5)."""
    return _EA_HEADERS if agreement == "ea" else _MCA_HEADERS


def _money(value: Decimal) -> str:
    return str(value.quantize(_SIX, ROUND_HALF_EVEN))


def _cost_measure(line: BillingLine, export_type: str) -> Decimal:
    """Return the cost measure for the export type.

    ``actual`` -> as-charged ``billed_cost``; ``amortized`` -> commitment-amortized
    ``effective_cost`` (design §4.1). This measure choice is PINNED; only the
    header name it lands under is §11.3-unverified.
    """
    return line.effective_cost if export_type == "amortized" else line.billed_cost


def _resource_id(line: BillingLine) -> str:
    """Empty for the FR-D5 null-resource line (mirrors the FOCUS renderer, OA-4)."""
    return "" if line.resource_uuid is None else line.resource_uuid


def project_row(line: BillingLine, *, export_type: str, agreement: str) -> dict[str, str]:
    """Project one ``BillingLine`` into an Actual/Amortized export row (official headers)."""
    headers = headers_for(agreement)
    return {
        headers["billing_account_id"]: line.billing_account_id,
        headers["sub_account_id"]: line.sub_account_id,
        headers["service_name"]: line.service_name,
        headers["region"]: line.region_name,
        headers["resource_id"]: _resource_id(line),
        headers["charge_period_start"]: line.charge_period_start.isoformat(),
        headers["cost"]: _money(_cost_measure(line, export_type)),
        headers["currency"]: line.currency,
        headers["charge_category"]: line.charge_category,
    }


def column_order(agreement: str) -> list[str]:
    """Return the official column header order for the agreement."""
    headers = headers_for(agreement)
    return [
        headers["billing_account_id"],
        headers["sub_account_id"],
        headers["service_name"],
        headers["region"],
        headers["resource_id"],
        headers["charge_period_start"],
        headers["cost"],
        headers["currency"],
        headers["charge_category"],
    ]


def project_rows(
    lines: Sequence[BillingLine], *, export_type: str, agreement: str
) -> list[dict[str, str]]:
    """Project an ordered sequence of billing lines (caller controls the sort)."""
    return [project_row(line, export_type=export_type, agreement=agreement) for line in lines]
