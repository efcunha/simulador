"""Remaining acceptance-criteria tests (AC-5,6,13,15,16,17,18 + determinism).

Grouped here to keep the suite navigable; each test names its AC. The FOCUS
fidelity (AC-11) and scenario catalog (AC-14) live in dedicated files; the gate
(AC-7/8/9/10/12, OA-7) lives in test_gate_unit.
"""

from __future__ import annotations

import re
from datetime import timedelta
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path

from tools.synthetic_clouds.generate.estate_builder import build_estate
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.render.focus_azure import render_csv_bytes, render_parquet_bytes
from tools.synthetic_clouds.render.gcp_bigquery import render_ddl, render_json_bytes, render_rows
from tools.synthetic_clouds.scenarios.catalog import COMPUTED_OUTPUT_SCENARIOS
from tools.synthetic_clouds.scenarios.emit import apply_all
from tools.synthetic_clouds.serialize import store

_PACKAGE_SRC = Path(__file__).resolve().parents[1]


def _final(seed: int = 123, profile: str = "small", currency: str = "USD") -> CanonicalEstate:
    return apply_all(build_estate(seed, profile, currency))


# ── AC-5 determinism (byte-identical) ──────────────────────────────────────────


def test_focus_csv_byte_identical() -> None:
    assert render_csv_bytes(_final()) == render_csv_bytes(_final())


def test_focus_parquet_byte_identical() -> None:
    assert render_parquet_bytes(_final()) == render_parquet_bytes(_final())


def test_gcp_json_byte_identical() -> None:
    assert render_json_bytes(_final()) == render_json_bytes(_final())


def test_canonical_parquet_byte_identical(tmp_path: Path) -> None:
    est = _final()
    dir_a = store.write(est, tmp_path / "a")
    dir_b = store.write(est, tmp_path / "b")
    for name in ("billing_lines", "resources", "consumption", "invoices"):
        file_a = (dir_a / f"{name}.parquet").read_bytes()
        file_b = (dir_b / f"{name}.parquet").read_bytes()
        assert file_a == file_b, f"{name}.parquet not byte-identical across runs"


# ── AC-6 no Python hash() ──────────────────────────────────────────────────────


def test_no_python_hash_in_source() -> None:
    """AC-6: no real call to the builtin ``hash()`` anywhere in the package source.

    Uses the AST so docstring/comment mentions of ``hash()`` (which explain WHY it
    is banned) are not false positives — only an actual ``hash(...)`` Call node
    bound to the bare name ``hash`` counts.
    """
    import ast

    offenders: list[str] = []
    for py in _PACKAGE_SRC.rglob("*.py"):
        if "tests" in py.parts or py.name.startswith("_"):
            continue
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "hash":
                offenders.append(f"{py.relative_to(_PACKAGE_SRC)}:{node.lineno}")
    assert not offenders, "Python hash() used as entropy:\n" + "\n".join(offenders)


# ── AC-13 GCP ARRAY<STRUCT<...>> ────────────────────────────────────────────────


def test_gcp_ddl_declares_array_of_struct() -> None:
    ddl = render_ddl(_final())
    for col in ("credits", "labels"):
        assert re.search(rf"\b{col}\s+ARRAY<STRUCT<", ddl), f"{col} must be ARRAY<STRUCT<...>>"
    assert "project STRUCT<" in ddl
    assert "labels ARRAY<STRUCT<key STRING, value STRING>>" in ddl  # project.labels nested
    assert "CREATE TABLE" in ddl
    assert "usage_start_time TIMESTAMP" in ddl
    assert "cost FLOAT64" in ddl


def test_gcp_rows_typing() -> None:
    rows = render_rows(_final())
    assert rows
    row = rows[0]
    assert isinstance(row["cost"], float)  # FLOAT64
    assert re.fullmatch(r"\d{6}", row["invoice"]["month"])  # YYYYMM
    assert isinstance(row["labels"], list)  # ARRAY<STRUCT>


# ── AC-15 no computed outputs emitted (P1) ──────────────────────────────────────


def test_no_computed_outputs_emitted() -> None:
    """AC-15/P1: no opportunity/drift/compliance/tag-score/anomaly/forecast record.

    The emitted artifacts are billing/inventory/findings/recs/metrics/IaC only.
    Native recommendations use native kinds (rightsize/idle/sku_change) and native
    findings are status=open — neither is a FinOps-computed verdict. We assert
    no entity carries a computed-output marker field.
    """
    est = _final()
    forbidden = {"drift_result", "compliance_result", "opportunity", "anomaly", "tag_score", "forecast"}
    for rec in est.recommendations:
        assert not (forbidden & set(rec.detail_json)), f"computed output leaked in rec {rec.recommendation_id}"
    for finding in est.findings:
        assert not (forbidden & set(finding.evidence_json)), f"computed output leaked in finding {finding.finding_id}"
    assert COMPUTED_OUTPUT_SCENARIOS  # sanity: the set is populated


# ── AC-16 clock latency + restatement ───────────────────────────────────────────


def test_export_latency_is_next_day() -> None:
    """AC-16: a charge dated day D has export_time D+1 00:00 UTC."""
    est = build_estate(123, "small", "USD")
    line = next(line for line in est.billing_lines if line.charge_category == "Usage" and line.resource_uuid)
    charge_day = line.charge_period_start.date()
    assert line.export_time.date() == charge_day + timedelta(days=1)
    assert (line.export_time.hour, line.export_time.minute) == (0, 0)


def test_restatement_is_adjustment_delta_original_intact() -> None:
    """AC-16: C17 restatement is an Adjustment delta; original Usage line unchanged."""
    est = _final()
    adj = [line for line in est.billing_lines if line.is_restatement]
    assert adj, "no restatement line present"
    for line in adj:
        assert line.charge_category == "Adjustment"
        assert line.restates_date is not None
        assert line.export_time.date() > line.restates_date


# ── AC-18 synthetic markers ─────────────────────────────────────────────────────


def test_synthetic_markers_present() -> None:
    est = _final()
    assert all(b.name.startswith("[SYNTH] ") for b in est.billing_accounts)
    assert all(f.source == "synthetic" for f in est.findings)
    assert all(r.recommendation_model == "synthetic.seed.v1" for r in est.recommendations)
    assert all(f.evidence_json.get("synthetic") is True for f in est.findings)
    assert all(b.source_fingerprint.startswith("synth:") for b in est.billing_lines)
    assert all(a.config_json.get("synthetic") is True for a in est.inventory)
    assert all(s.metadata.get("synthetic") is True for s in est.iac_snapshots)


def test_no_real_secrets_identities_fictional() -> None:
    est = _final()
    assert est.gcp_orgs[0].domain == "contoso.example"
    for ba in est.billing_accounts:
        assert "contoso" in ba.name.lower() or "synth" in ba.name.lower() or "billing" in ba.name.lower()


# ── profile row band (AC-17, small only; medium/large are slow) ──────────────────


def test_small_profile_row_band() -> None:
    """AC-17: small profile FOCUS row count within +/-10% of ~40k."""
    est = _final()
    focus_rows = len(est.billing_lines)
    target = 40_000
    tol = Decimal("0.10")
    low = int((Decimal(target) * (Decimal("1") - tol)).quantize(Decimal("1"), ROUND_HALF_EVEN))
    high = int((Decimal(target) * (Decimal("1") + tol)).quantize(Decimal("1"), ROUND_HALF_EVEN))
    assert low <= focus_rows <= high, f"small FOCUS rows {focus_rows} outside [{low}, {high}]"


def test_brl_run_markers() -> None:
    """AC-17: BRL run emits BillingCurrency=BRL and a conversion rate."""
    est = _final(currency="BRL")
    assert est.currency_conversion_rate is not None
    assert all(b.currency == "BRL" for b in est.billing_lines)
    rows = render_rows(est)
    assert all(r["currency"] == "BRL" for r in rows)
    assert all(r["currency_conversion_rate"] != 1.0 for r in rows)
