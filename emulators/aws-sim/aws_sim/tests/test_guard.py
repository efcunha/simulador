"""The refusal guard: it must refuse real material, and never echo a value."""

from __future__ import annotations

from pathlib import Path

import pytest

from aws_sim.guard import SafetyRefusalError, assert_no_real_credentials

#: Synthetic-by-construction: the guard matches on SHAPE, and this is a shape.
_ACCESS_KEY_SHAPE = "AKIAIOSFODNN7EXAMPLE"


def test_clean_environment_passes() -> None:
    assert_no_real_credentials({"SEED": "42", "AWS_DEFAULT_REGION": "us-east-1"})


def test_refuses_a_long_lived_access_key_id_shape() -> None:
    with pytest.raises(SafetyRefusalError, match="SAFETY REFUSAL"):
        assert_no_real_credentials({"AWS_ACCESS_KEY_ID": _ACCESS_KEY_SHAPE})


def test_refuses_a_temporary_access_key_id_shape() -> None:
    with pytest.raises(SafetyRefusalError, match="SAFETY REFUSAL"):
        assert_no_real_credentials({"AWS_ACCESS_KEY_ID": "ASIAIOSFODNN7EXAMPLE"})


def test_refusal_names_the_variable_and_never_the_value() -> None:
    """A message that echoes a credential into a log is the leak this guard prevents."""
    with pytest.raises(SafetyRefusalError) as caught:
        assert_no_real_credentials({"AWS_ACCESS_KEY_ID": _ACCESS_KEY_SHAPE})

    message = str(caught.value)
    assert "AWS_ACCESS_KEY_ID" in message
    assert _ACCESS_KEY_SHAPE not in message


def test_ignores_a_value_that_only_looks_like_a_key() -> None:
    """Too short, wrong charset, or no prefix: not an access key id shape."""
    for value in ("AKIA", "AKIAIOSFODNN7EXAMPL", "akiaiosfodnn7example", "synthetic-key"):
        assert_no_real_credentials({"AWS_ACCESS_KEY_ID": value})


def test_refuses_a_profile_that_exists_in_the_shared_config(tmp_path: Path) -> None:
    config = tmp_path / "config"
    config.write_text("[profile prod]\nregion = us-east-1\n", encoding="utf-8")
    with pytest.raises(SafetyRefusalError, match="prod"):
        assert_no_real_credentials({"AWS_PROFILE": "prod", "AWS_CONFIG_FILE": str(config)})


def test_allows_a_profile_that_is_not_configured(tmp_path: Path) -> None:
    config = tmp_path / "config"
    config.write_text("[profile prod]\nregion = us-east-1\n", encoding="utf-8")
    assert_no_real_credentials({"AWS_PROFILE": "synthetic", "AWS_CONFIG_FILE": str(config)})


def test_unreadable_shared_config_is_not_a_refusal(tmp_path: Path) -> None:
    """The guard blocks on evidence; a config it cannot read is not evidence."""
    assert_no_real_credentials({"AWS_PROFILE": "prod", "AWS_CONFIG_FILE": str(tmp_path / "absent")})
