"""Gate unit: a valid post-scenario estate passes; broken estates raise.

Covers AC-7 (no-orphans incl. F2 sub-assertions), AC-8 (scoping), AC-9 (invoice
balance + C07), AC-10 (credits bound), AC-12 (category/provider domain), OA-7 (k8s).
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from tools.synthetic_clouds.generate.estate_builder import build_estate
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.scenarios.emit import apply_all
from tools.synthetic_clouds.validate import gate
from tools.synthetic_clouds.validate.integrity import IntegrityError, check_no_orphans
from tools.synthetic_clouds.validate.quality import QualityError, check_credits_bound


def _final_estate() -> CanonicalEstate:
    return apply_all(build_estate(seed=123, profile="small", currency="USD"))


def test_valid_estate_passes_gate() -> None:
    gate.run(_final_estate())  # must not raise


def test_null_resource_line_is_only_none_billing_and_exempt() -> None:
    estate = _final_estate()
    none_lines = [b for b in estate.billing_lines if b.resource_uuid is None]
    # FR-D5 null line + C05 commitment Purchase lines are the sanctioned billing-only
    # None-resource lines; all carry Tax or Purchase category (never Usage).
    assert none_lines
    assert all(b.charge_category in ("Tax", "Purchase") for b in none_lines)
    # No-orphan check must pass despite the None lines (F2 exemption).
    check_no_orphans(estate)


def test_orphan_finding_raises() -> None:
    estate = _final_estate()
    bad_finding = replace(estate.findings[0], resource_uuid="not-a-real-uuid")
    broken = replace(estate, findings=(bad_finding, *estate.findings[1:]))
    with pytest.raises(IntegrityError):
        check_no_orphans(broken)


def test_credit_over_applicable_raises() -> None:
    estate = _final_estate()
    bad_credit = replace(estate.credits[0], amount=Decimal("99999.000000"), applicable_cost=Decimal("1.000000"))
    broken = replace(estate, credits=(bad_credit, *estate.credits[1:]))
    with pytest.raises(QualityError):
        check_credits_bound(broken)


def test_c07_invoices_present_and_balanced() -> None:
    estate = _final_estate()
    c07 = [inv for inv in estate.invoices if inv.is_c07_divergence]
    # One Azure + one GCP C07 divergence invoice.
    assert len(c07) == 2
    gate.run(estate)  # invoice balance (incl. C07 recompute) passes
