"""AC-11 / P3: FOCUS renderer output parses VERBATIM by the real parser.py.

Two axes (design sec. 8.2 / Finding 1):
  * Dialect + aggregation: CSV and Parquet feed parse_cur_bytes /
    parse_cur_dataframe / parse_cur_cost_dataframe -> dialect ``focus``, no
    ``CurParseError``. These three functions IGNORE Tags.
  * Tag fidelity (N1/N2): CSV (JSON-string list-of-pairs) and Parquet (native
    list-of-pairs) feed parse_cur_cost_dataframe_with_resources DIRECTLY (the only
    function that reads Tags) -> both decode to the expected dict[str, str]. No
    CUR_RESOURCE_LEVEL_ENABLED flag manipulation: the function is pure and ungated
    (N1), and AC-11's literal function list covers only the dialect+aggregation
    axis (N2).
"""

from __future__ import annotations

import io
from types import ModuleType

import pandas as pd

from tools.synthetic_clouds.generate.estate_builder import build_estate
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.render.focus_azure import render_csv_bytes, render_parquet_bytes
from tools.synthetic_clouds.scenarios.emit import apply_all


def _estate() -> CanonicalEstate:
    return apply_all(build_estate(seed=123, profile="small", currency="USD"))


def test_csv_detects_focus_and_aggregates(real_parser: ModuleType) -> None:
    estate = _estate()
    raw = render_csv_bytes(estate)
    df = real_parser.parse_cur_bytes(raw, "focus.csv")
    assert real_parser._detect_dialect(set(df.columns))[0] == "focus"
    invoice_rows = real_parser.parse_cur_dataframe(df)
    cost_rows = real_parser.parse_cur_cost_dataframe(df)
    assert invoice_rows  # non-empty, no CurParseError raised
    assert cost_rows


def test_parquet_detects_focus_and_aggregates(real_parser: ModuleType) -> None:
    estate = _estate()
    raw = render_parquet_bytes(estate)
    df = real_parser.parse_cur_bytes(raw, "focus.parquet")
    assert real_parser._detect_dialect(set(df.columns))[0] == "focus"
    assert real_parser.parse_cur_dataframe(df)
    assert real_parser.parse_cur_cost_dataframe(df)


def test_tags_roundtrip_resource_grain_csv(real_parser: ModuleType) -> None:
    """N1/N2: CSV Tags (JSON-string list-of-pairs) decode via the resource-grain fn."""
    estate = _estate()
    df = real_parser.parse_cur_bytes(render_csv_bytes(estate), "focus.csv")
    rows = real_parser.parse_cur_cost_dataframe_with_resources(df)
    tagged = next(r for r in estate.resources if r.tags)
    expected = {k: v for k, v in tagged.tags}
    matching = [r for r in rows if r.tags == expected]
    assert matching, f"no resource-grain row carried the expected tags {expected}"


def test_tags_roundtrip_resource_grain_parquet(real_parser: ModuleType) -> None:
    """N1/N2: Parquet Tags (JSON-string list-of-pairs) decode via the resource-grain fn.

    Parquet uses the JSON-string encoding (not a native arrow list) because
    ``pd.read_parquet`` materializes arrow lists as numpy ndarrays, which the
    parser's native-list branch never matches — see ``render_parquet_bytes`` note.
    """
    estate = _estate()
    df = real_parser.parse_cur_bytes(render_parquet_bytes(estate), "focus.parquet")
    rows = real_parser.parse_cur_cost_dataframe_with_resources(df)
    tagged = next(r for r in estate.resources if r.tags)
    expected = {k: v for k, v in tagged.tags}
    matching = [r for r in rows if r.tags == expected]
    assert matching, f"no resource-grain row carried the expected tags {expected}"


def test_csv_is_valid_focus_frame_shape(real_parser: ModuleType) -> None:
    """Sanity: the CSV has the mandatory focus-detection columns."""
    raw = render_csv_bytes(_estate())
    df = pd.read_csv(io.BytesIO(raw), low_memory=False)
    assert "BilledCost" in df.columns
    assert "BillingPeriodStart" in df.columns
