"""Invoice-side conformance for the GCP BigQuery export (FOCUS/GCP Phase 2).

The export ships usage tables *and* an invoice pair. These tests pin the
invoice side: the tables exist, a line item reconciles to the usage row it
came from, and an invoice total equals the sum of its line items. Without
those the simulator could reproduce spend but had no invoice for an app to
reconcile against -- which is the property this phase exists to establish.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from tools.synthetic_clouds.generate.estate_builder import build_estate
from tools.synthetic_clouds.render.gcp_bigquery_topology import (
    GcpBigQueryTopologyRenderer,
)
from tools.synthetic_clouds.scenarios.emit import apply_all

_TOPOLOGY = pytest.mark.topology
pytestmark = _TOPOLOGY


def _payload() -> tuple[Any, dict[str, str], dict[str, int]]:
    estate = apply_all(build_estate(seed=123, profile="small", currency="USD"))
    return GcpBigQueryTopologyRenderer().build_scripts(estate)


def _rows(files: dict[str, str], name: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = json.loads(files[name])
    return rows


@_TOPOLOGY
def test_invoice_tables_are_provisioned() -> None:
    names, files, counts = _payload()
    ddl = files["02_tables.sql"]
    assert f"CREATE TABLE `{names.invoice_table}`" in ddl
    assert f"CREATE TABLE `{names.invoice_line_item_table}`" in ddl
    assert counts[names.invoice_table] > 0
    assert counts[names.invoice_line_item_table] > 0


@_TOPOLOGY
def test_invoice_line_item_carries_the_official_discriminator() -> None:
    """``item_type`` is what lets a consumer roll up without re-deriving."""
    _names, files, _counts = _payload()
    items = _rows(files, "11_rows_invoice_line_item.json")
    assert items
    assert {i["item_type"] for i in items} <= {"SKU", "Tax", "Adjustment", "Rounding"}
    for item in items:
        # A line item is only reconcilable if it names its invoice.
        assert item["invoice_id"]
        assert item["invoice_month"]
        assert item["billing_account_id"]


@_TOPOLOGY
def test_invoice_total_equals_the_sum_of_its_line_items() -> None:
    """The reconciliation identity, on generated data.

    ``invoice.total_amount == sum(invoice_line_item.amount + tax_amount)``
    for the same ``invoice_id``. This is the property an app's parity gate
    depends on; if it drifts the whole invoice side is decorative.
    """
    _names, files, _counts = _payload()
    items = _rows(files, "11_rows_invoice_line_item.json")
    invoices = _rows(files, "10_rows_invoice.json")

    by_invoice: dict[str, float] = {}
    for item in items:
        by_invoice[item["invoice_id"]] = by_invoice.get(item["invoice_id"], 0.0) + (
            item["amount"] + item["tax_amount"]
        )

    assert len(invoices) == len(by_invoice), "one invoice per distinct invoice_id"
    for invoice in invoices:
        expected = by_invoice[invoice["invoice_id"]]
        assert invoice["total_amount"] == pytest.approx(expected, abs=0.01)
        assert invoice["cost"]["amount"] == pytest.approx(expected, abs=0.01)
        assert invoice["status"] == "Posted"


@_TOPOLOGY
def test_invoice_totals_reconcile_with_the_usage_table() -> None:
    """Invoices must account for the same money as the usage rows.

    The invoice is derived from the standard rows rather than recomputed, so
    this guards the derivation itself against a future edit that drops or
    double-counts a charge.
    """
    _names, files, _counts = _payload()
    usage = _rows(files, "08_rows_standard.json")
    invoices = _rows(files, "10_rows_invoice.json")
    usage_total = sum(r["cost"] for r in usage)
    invoice_total = sum(r["total_amount"] for r in invoices)
    assert invoice_total == pytest.approx(usage_total, abs=0.01)


@_TOPOLOGY
def test_render_is_deterministic() -> None:
    """Two renders of the same estate must be byte-identical."""
    estate = apply_all(build_estate(seed=123, profile="small", currency="USD"))
    first = GcpBigQueryTopologyRenderer().build_scripts(estate)[1]
    second = GcpBigQueryTopologyRenderer().build_scripts(estate)[1]
    assert first == second