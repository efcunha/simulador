"""Schedule driver for Cost Management export runs (design §4.3, §4.7).

Drives three schedule modes over the frozen, gated estate:

  * ``daily``    — month-to-date slice of the current period, written to a NEW
                   ``<runId>`` folder (prior runs retained).
  * ``monthly``  — the prior full month, written once.
  * ``one-time`` — every simulated period window present in the estate (backfill).

Determinism (§4.3): the ``runId`` folder name derives from
``(seed, profile, currency, schedule, period, run_index)`` and the manifest
``export_time`` derives from the slice —
``max(line.export_time for line in slice) + timedelta(hours=LATENCY_HOURS)`` —
never from the container clock. The month-to-date slice is bounded by
``estate.sim_now``.

Fail-closed (§4.7): the estate is already gated by ``estate.py`` before any run;
this driver performs no write of its own — it builds the parts + manifest and
hands them to the injected :class:`BlobWriter`, which commits the manifest LAST.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from tools.synthetic_clouds.model.billing import BillingLine
from tools.synthetic_clouds.model.estate import CanonicalEstate

from azure_sim.config import Settings
from azure_sim.exporter.blob_writer import BlobWriter
from azure_sim.exporter.focus_export import (
    FOCUS_COLUMNS,
    FOCUS_DATASET_VERSION,
    lay_out_focus_parts,
    part_refs,
)
from azure_sim.exporter.layout import PeriodWindow, build_run_prefix, compute_run_id
from azure_sim.exporter.manifest import build_manifest
from azure_sim.projections import scope

_EXPORT_NAME = "focus-cost"


@dataclass(slots=True, frozen=True)
class RunPlan:
    """One planned export run: its window, slice, and deterministic run id."""

    period: PeriodWindow
    lines: tuple[BillingLine, ...]
    run_id: str
    run_index: int


def _month_start(day: date) -> date:
    return day.replace(day=1)


def _month_end(day: date) -> date:
    """Return the last day of ``day``'s month."""
    if day.month == 12:
        return date(day.year, 12, 31)
    return date(day.year, day.month + 1, 1) - timedelta(days=1)


def _prior_month_window(day: date) -> PeriodWindow:
    first_of_this = _month_start(day)
    last_of_prior = first_of_this - timedelta(days=1)
    return PeriodWindow(start=_month_start(last_of_prior), end=last_of_prior)


def _lines_in_window(estate: CanonicalEstate, window: PeriodWindow) -> list[BillingLine]:
    """Return THIS provider's billing lines whose period start falls in ``window``.

    Scoped through ``projections/scope.py``: the estate carries all three clouds and an
    Azure FOCUS export containing AWS and GCP line items is the leak
    ``render/focus_azure.py:120`` filters out on the renderer side.
    """
    selected = [
        line
        for line in scope.billing_lines(estate)
        if window.start <= line.billing_period_start <= window.end
    ]
    return sorted(selected, key=lambda line: line.line_id)


def _distinct_windows(estate: CanonicalEstate) -> list[PeriodWindow]:
    """Return the distinct month windows present in this provider's lines."""
    months = {
        (line.billing_period_start.year, line.billing_period_start.month)
        for line in scope.billing_lines(estate)
    }
    windows = [PeriodWindow(start=date(y, m, 1), end=_month_end(date(y, m, 1))) for y, m in months]
    return sorted(windows, key=lambda w: w.start)


def _slice_estate(estate: CanonicalEstate, lines: tuple[BillingLine, ...]) -> CanonicalEstate:
    """Return the estate with billing lines narrowed to ``lines`` (for rendering)."""
    return dataclasses.replace(estate, billing_lines=lines)


def plan_runs(estate: CanonicalEstate, settings: Settings) -> list[RunPlan]:
    """Return the ordered list of runs for the configured schedule (§4.3)."""
    schedule = settings.schedule
    if schedule == "daily":
        # Month-to-date slice of the current month, bounded by sim_now.
        windows = [PeriodWindow(start=_month_start(estate.sim_now), end=estate.sim_now)]
    elif schedule == "monthly":
        windows = [_prior_month_window(estate.sim_now)]
    else:  # one-time: every simulated window
        windows = _distinct_windows(estate)

    plans: list[RunPlan] = []
    for run_index, window in enumerate(windows):
        lines = _lines_in_window(estate, window)
        run_id = compute_run_id(
            seed=settings.seed,
            profile=settings.profile,
            currency=settings.currency,
            schedule=schedule,
            period=window,
            run_index=run_index,
        )
        plans.append(RunPlan(period=window, lines=tuple(lines), run_id=run_id, run_index=run_index))
    return plans


def derive_export_time(lines: Sequence[BillingLine], latency_hours: int) -> datetime | None:
    """Return ``max(export_time) + latency`` for the slice, or ``None`` if empty (§4.3)."""
    if not lines:
        return None
    return max(line.export_time for line in lines) + timedelta(hours=latency_hours)


def _manifest_export_time(plan: RunPlan, latency_hours: int) -> datetime:
    """Return the slice's derived export time, or a deterministic empty-slice stamp."""
    derived = derive_export_time(plan.lines, latency_hours)
    if derived is not None:
        return derived
    # Empty slice: stamp the window end at UTC midnight (deterministic, no clock).
    end = plan.period.end
    return datetime(end.year, end.month, end.day)


def run_export(estate: CanonicalEstate, settings: Settings, writer: BlobWriter) -> list[str]:
    """Execute all planned FOCUS runs, writing each via ``writer``.

    Returns the list of run prefixes written (one per (plan, format)). An empty
    slice still writes a manifest with ``blobs: []`` so Phase 4 sees a completed,
    empty window (§4.4/§4.7).
    """
    written: list[str] = []
    for plan in plan_runs(estate, settings):
        export_time = _manifest_export_time(plan, settings.latency_hours)
        slice_estate = _slice_estate(estate, plan.lines)
        for export_format in settings.formats:
            run_prefix = build_run_prefix(
                root_directory=settings.root_directory,
                export_name=_EXPORT_NAME,
                agreement=settings.agreement,
                period=plan.period,
                run_id=plan.run_id,
            )
            parts = lay_out_focus_parts(
                slice_estate,
                export_format=export_format,
                max_rows_per_part=settings.max_rows_per_part,
            )
            refs = part_refs(
                parts,
                max_rows_per_part=settings.max_rows_per_part,
                total_rows=len(plan.lines),
            )
            manifest = build_manifest(
                export_name=_EXPORT_NAME,
                export_type="focus",
                export_format=export_format,
                agreement=settings.agreement,
                period=plan.period,
                columns=FOCUS_COLUMNS,
                parts=refs,
                run_id=plan.run_id,
                export_time=export_time,
                dataset_version=FOCUS_DATASET_VERSION,
                seed=settings.seed,
                profile=settings.profile,
                currency=settings.currency,
            )
            writer.write_run(
                container=settings.blob_container,
                run_prefix=run_prefix,
                parts=parts,
                manifest=manifest,
            )
            written.append(run_prefix)
    return written
