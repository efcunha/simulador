"""Config validation + estate smoke (FEAT-001 step 1 / plan item 1).

Asserts enum/charset/numeric validation fails closed on bad input and that the
thin estate wrapper returns a gated ``CanonicalEstate`` for (42, small, USD).
"""

from __future__ import annotations

import pytest

from azure_sim.config import ConfigError, load_settings
from azure_sim.estate import build_simulated_estate


def test_defaults_load_clean() -> None:
    s = load_settings(env={})
    assert s.seed == 42
    assert s.profile == "small"
    assert s.currency == "USD"
    assert s.agreement == "mca"
    assert s.exports == ("focus",)
    assert set(s.formats) == {"csv", "parquet"}
    assert s.schedule == "one-time"
    assert s.latency_hours >= 0
    assert s.max_rows_per_part >= 1
    assert s.api_page_size >= 1


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("PROFILE", "huge"),
        ("CURRENCY", "EUR"),
        ("AGREEMENT", "aws"),
        ("SCHEDULE", "hourly"),
        ("SEED", "not-an-int"),
    ],
)
def test_bad_enum_or_int_fails_closed(key: str, value: str) -> None:
    with pytest.raises(ConfigError):
        load_settings(env={key: value})


def test_empty_exports_rejected() -> None:
    with pytest.raises(ConfigError):
        load_settings(env={"EXPORTS": " , "})


def test_bad_format_rejected() -> None:
    with pytest.raises(ConfigError):
        load_settings(env={"FORMAT": "csv,avro"})


def test_negative_latency_rejected() -> None:
    with pytest.raises(ConfigError):
        load_settings(env={"LATENCY_HOURS": "-1"})


def test_zero_max_rows_rejected() -> None:
    with pytest.raises(ConfigError):
        load_settings(env={"MAX_ROWS_PER_PART": "0"})


@pytest.mark.parametrize("bad_path", ["has space", "has;semicolon", "..\\escape"])
def test_bad_blob_path_charset_rejected(bad_path: str) -> None:
    with pytest.raises(ConfigError):
        load_settings(env={"BLOB_CONTAINER": bad_path})


def test_overrides_win_over_env() -> None:
    s = load_settings(env={"PROFILE": "small"}, profile="medium", seed=7)
    assert s.profile == "medium"
    assert s.seed == 7


def test_none_override_falls_through() -> None:
    s = load_settings(env={"PROFILE": "large"}, profile=None)
    assert s.profile == "large"


def test_exports_dedup_preserves_order() -> None:
    s = load_settings(env={"EXPORTS": "focus,actual,focus"})
    assert s.exports == ("focus", "actual")


def test_estate_wrapper_returns_gated_estate() -> None:
    estate = build_simulated_estate(seed=42, profile="small", currency="USD")
    assert estate.seed == 42
    assert estate.profile == "small"
    assert estate.currency == "USD"
    assert estate.billing_lines  # non-empty, gate.run did not raise
    assert estate.sim_now is not None
