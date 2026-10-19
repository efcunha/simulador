"""FOCUS export <-> real parser fidelity (FEAT-001 step 7 / plan item 4).

THE Phase-4 ingestion contract, proven in Phase 2: lay out a FOCUS export via
``focus_export.py`` (both ``.csv.gz`` and ``.parquet``, partitioned into >=2
parts), read every laid-out part back through the UNCHANGED real parser, and
assert:

  * every part detects dialect ``focus`` (no ``CurParseError``),
  * measure conservation across parts equals the single-file total
    (``aggregate_cost_rows`` merge), to float tolerance, and
  * tags decode to ``dict[str, str]`` via
    ``parse_cur_cost_dataframe_with_resources``.

Mirrors ``tools/synthetic_clouds/tests/test_focus_parser_roundtrip.py`` but
against the laid-out / gzip / partitioned files, not the raw renderer bytes.
"""

from __future__ import annotations

from decimal import Decimal
from types import ModuleType

import pytest

from azure_sim.estate import build_simulated_estate
from azure_sim.exporter.focus_export import lay_out_focus_parts

# Conservation tolerance: the parser sums float64 then converts to Decimal, so
# summation order across parts vs a single file differs by sub-nanocent amounts.
_TOLERANCE = Decimal("0.000001")

# A whole-file layout uses a very large row cap so there is exactly one part.
_WHOLE = 10**9


def _estate():
    return build_simulated_estate(seed=42, profile="small", currency="USD")


def _part_count_for_two_plus(total_rows: int) -> int:
    """Return a max-rows-per-part that guarantees >= 2 parts for ``total_rows``."""
    return max(1, total_rows // 3)


def _frames(parser: ModuleType, parts: list) -> list:
    return [parser.parse_cur_bytes(part.data, part.file_name) for part in parts]


def _total_billed(rows: list) -> Decimal:
    return sum((r.billed_cost for r in rows), Decimal(0))


@pytest.mark.parametrize("export_format", ["csv", "parquet"])
def test_partitioned_focus_parses_and_conserves(real_parser: ModuleType, export_format: str) -> None:
    estate = _estate()
    total_rows = len(estate.billing_lines)
    max_rows = _part_count_for_two_plus(total_rows)

    parts = lay_out_focus_parts(estate, export_format=export_format, max_rows_per_part=max_rows)
    assert len(parts) >= 2, "fidelity contract requires a partitioned export (>= 2 parts)"

    # Every part detects dialect focus, no CurParseError.
    frames = _frames(real_parser, parts)
    for frame in frames:
        assert real_parser._detect_dialect(set(frame.columns))[0] == "focus"
        assert real_parser.parse_cur_dataframe(frame) is not None

    # Measure conservation: merged parts == single-file total (to float tolerance).
    merged = real_parser.aggregate_cost_rows(frames)
    whole_parts = lay_out_focus_parts(estate, export_format=export_format, max_rows_per_part=_WHOLE)
    assert len(whole_parts) == 1
    whole_rows = real_parser.aggregate_cost_rows(_frames(real_parser, whole_parts))

    assert abs(_total_billed(merged) - _total_billed(whole_rows)) <= _TOLERANCE
    # Row-group identity is exact even when float sums drift.
    assert len(merged) == len(whole_rows)


@pytest.mark.parametrize("export_format", ["csv", "parquet"])
def test_tags_decode_to_str_dict(real_parser: ModuleType, export_format: str) -> None:
    estate = _estate()
    parts = lay_out_focus_parts(estate, export_format=export_format, max_rows_per_part=_WHOLE)
    df = real_parser.parse_cur_bytes(parts[0].data, parts[0].file_name)
    rows = real_parser.parse_cur_cost_dataframe_with_resources(df)
    tagged = [r for r in rows if r.tags]
    assert tagged, "expected at least one resource-grain row carrying tags"
    sample = tagged[0].tags
    assert isinstance(sample, dict)
    assert all(isinstance(k, str) and isinstance(v, str) for k, v in sample.items())


def test_tags_match_a_known_resource(real_parser: ModuleType) -> None:
    """A specific estate resource's tags survive the laid-out CSV roundtrip."""
    estate = _estate()
    parts = lay_out_focus_parts(estate, export_format="csv", max_rows_per_part=_WHOLE)
    df = real_parser.parse_cur_bytes(parts[0].data, parts[0].file_name)
    rows = real_parser.parse_cur_cost_dataframe_with_resources(df)
    tagged_resource = next(r for r in estate.resources if r.tags)
    expected = {k: v for k, v in tagged_resource.tags}
    assert any(r.tags == expected for r in rows), f"no row carried the expected tags {expected}"
