"""Layout path shapes + deterministic runId (FEAT-001 step 4 / plan item 2)."""

from __future__ import annotations

from datetime import date

from azure_sim.exporter.layout import (
    PeriodWindow,
    build_run_prefix,
    compute_run_id,
    manifest_blob_name,
    part_blob_name,
)

_WINDOW = PeriodWindow(start=date(2026, 2, 1), end=date(2026, 2, 14))


def test_window_folder_segment() -> None:
    assert _WINDOW.folder_segment() == "20260201-20260214"


def _run_id(
    *,
    seed: int = 42,
    profile: str = "small",
    currency: str = "USD",
    schedule: str = "daily",
    run_index: int = 0,
) -> str:
    return compute_run_id(
        seed=seed,
        profile=profile,
        currency=currency,
        schedule=schedule,
        period=_WINDOW,
        run_index=run_index,
    )


def test_run_id_is_deterministic() -> None:
    first = _run_id()
    second = _run_id()
    assert first == second
    assert len(first) == 16
    assert all(c in "0123456789abcdef" for c in first)


def test_run_id_varies_with_inputs() -> None:
    assert _run_id() != _run_id(run_index=1)
    assert _run_id() != _run_id(seed=43)
    assert _run_id() != _run_id(schedule="monthly")


def test_mca_run_prefix_shape() -> None:
    prefix = build_run_prefix(
        root_directory="cost-exports",
        export_name="focus-cost",
        agreement="mca",
        period=_WINDOW,
        run_id="abc123",
    )
    assert prefix == "cost-exports/focus-cost/20260201-20260214/abc123"


def test_ea_run_prefix_shape() -> None:
    # TODO-verificar §11.1: EA currently shares the MCA shape until the EA root
    # segment is confirmed; the branch is isolated in layout._export_root.
    prefix = build_run_prefix(
        root_directory="cost-exports",
        export_name="focus-cost",
        agreement="ea",
        period=_WINDOW,
        run_id="abc123",
    )
    assert prefix.endswith("/focus-cost/20260201-20260214/abc123")


def test_part_and_manifest_blob_names() -> None:
    prefix = "cost-exports/focus-cost/20260201-20260214/abc123"
    assert part_blob_name(prefix, "part_focus_0001.csv.gz") == f"{prefix}/part_focus_0001.csv.gz"
    assert manifest_blob_name(prefix) == f"{prefix}/manifest.json"
