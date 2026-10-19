"""Runner schedules + deterministic runId + export_time derivation (FEAT-001 step 6).

The blob writer is faked: it records every ``write_run`` call so the test asserts
manifest/part behavior without touching Azurite.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from azure_sim.config import Settings, load_settings
from azure_sim.estate import build_simulated_estate
from azure_sim.exporter.focus_export import LaidOutPart
from azure_sim.exporter.runner import derive_export_time, plan_runs, run_export


@dataclass
class FakeWriter:
    """Records each run write for assertions (manifest-last never touches Azurite)."""

    calls: list[dict[str, Any]] = field(default_factory=list)

    def write_run(
        self, *, container: str, run_prefix: str, parts: list[LaidOutPart], manifest: dict[str, Any]
    ) -> None:
        self.calls.append(
            {"container": container, "run_prefix": run_prefix, "parts": parts, "manifest": manifest}
        )


def _settings(**overrides: Any) -> Settings:
    return load_settings(env={}, **overrides)


def _estate():
    return build_simulated_estate(seed=42, profile="small", currency="USD")


def test_one_time_covers_all_windows() -> None:
    estate = _estate()
    plans = plan_runs(estate, _settings(schedule="one-time"))
    months = {
        (line.billing_period_start.year, line.billing_period_start.month)
        for line in estate.billing_lines
    }
    assert len(plans) == len(months)


def test_monthly_is_single_prior_window() -> None:
    plans = plan_runs(_estate(), _settings(schedule="monthly"))
    assert len(plans) == 1


def test_daily_is_month_to_date_bounded_by_sim_now() -> None:
    estate = _estate()
    plans = plan_runs(estate, _settings(schedule="daily"))
    assert len(plans) == 1
    window = plans[0].period
    assert window.end == estate.sim_now
    assert window.start.day == 1


def test_run_id_is_deterministic_across_calls() -> None:
    estate = _estate()
    settings = _settings(schedule="one-time")
    first = [p.run_id for p in plan_runs(estate, settings)]
    second = [p.run_id for p in plan_runs(estate, settings)]
    assert first == second


def test_export_time_is_max_plus_latency() -> None:
    estate = _estate()
    plans = plan_runs(estate, _settings(schedule="one-time"))
    plan = next(p for p in plans if p.lines)
    latency = 4
    expected = max(line.export_time for line in plan.lines) + timedelta(hours=latency)
    assert derive_export_time(plan.lines, latency) == expected


def test_empty_slice_export_time_is_none() -> None:
    assert derive_export_time([], 4) is None


def test_run_export_writes_manifest_last_shape() -> None:
    estate = _estate()
    settings = _settings(schedule="monthly", format="csv")
    writer = FakeWriter()
    prefixes = run_export(estate, settings, writer)
    assert prefixes  # at least one run written
    assert len(writer.calls) == len(prefixes)
    for call in writer.calls:
        assert call["container"] == settings.blob_container
        assert call["manifest"]["synthetic"] is True
        # manifest blob list count matches the laid-out parts
        assert len(call["manifest"]["blobs"]) == len(call["parts"])


def test_run_export_both_formats_doubles_runs() -> None:
    estate = _estate()
    writer = FakeWriter()
    run_export(estate, _settings(schedule="monthly", format="csv,parquet"), writer)
    formats = {call["manifest"]["format"] for call in writer.calls}
    assert formats == {"csv", "parquet"}
