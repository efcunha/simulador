"""Partition row-slicing + part naming + empty-slice rule (FEAT-001 step 6)."""

from __future__ import annotations

from azure_sim.exporter.partition import part_file_name, row_slices


def test_empty_input_yields_no_slices() -> None:
    assert row_slices(0, 100) == []


def test_single_slice_when_under_threshold() -> None:
    assert row_slices(50, 100) == [(0, 50)]


def test_splits_into_multiple_parts() -> None:
    assert row_slices(250, 100) == [(0, 100), (100, 200), (200, 250)]


def test_exact_multiple_has_no_trailing_empty() -> None:
    assert row_slices(200, 100) == [(0, 100), (100, 200)]


def test_slices_cover_every_row_once() -> None:
    slices = row_slices(1000, 137)
    covered = [i for start, end in slices for i in range(start, end)]
    assert covered == list(range(1000))


def test_part_file_name_zero_padded() -> None:
    assert part_file_name("focus", ".csv.gz", 1) == "part_focus_0001.csv.gz"
    assert part_file_name("focus", ".parquet", 42) == "part_focus_0042.parquet"


def test_defensive_zero_max_rows_is_single_slice() -> None:
    # config.py guarantees >= 1, but the helper is defensive.
    assert row_slices(10, 0) == [(0, 10)]
