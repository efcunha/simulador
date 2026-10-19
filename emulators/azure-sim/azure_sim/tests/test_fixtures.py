"""Versioned fixture tests (FEAT-003, plan item 11).

Every JSON fixture under ``azure_sim/fixtures`` must load as valid JSON and carry
a version marker (``version`` or ``api-version``). These fixtures document the
official-shaped schemas the sim projects against; the version field is what lets
Phase 4 (and any schema-drift audit) pin which API/dataset shape each skeleton
targets.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# azure_sim/tests/ -> parents[1] = azure_sim -> fixtures/
_FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"

_VERSION_KEYS = ("version", "api-version")


def _fixture_files() -> list[Path]:
    return sorted(_FIXTURES_DIR.glob("*.json"))


def test_fixtures_dir_is_populated() -> None:
    files = _fixture_files()
    assert files, f"no fixture JSON files found under {_FIXTURES_DIR}"
    # The plan enumerates the schema skeletons the sim shapes against.
    assert len(files) >= 7, f"expected at least 7 fixtures, found {len(files)}"


@pytest.mark.parametrize("fixture_path", _fixture_files(), ids=lambda p: p.name)
def test_fixture_loads_and_has_version(fixture_path: Path) -> None:
    data = json.loads(fixture_path.read_text(encoding="utf-8"))
    assert isinstance(data, dict), f"{fixture_path.name} must be a JSON object"
    present = [key for key in _VERSION_KEYS if key in data and str(data[key]).strip()]
    assert present, (
        f"{fixture_path.name} must carry a non-empty version marker "
        f"(one of {_VERSION_KEYS})"
    )


@pytest.mark.parametrize("fixture_path", _fixture_files(), ids=lambda p: p.name)
def test_fixture_carries_todo_verificar_note(fixture_path: Path) -> None:
    # Each skeleton documents where its shape is unconfirmed (design §11).
    data = json.loads(fixture_path.read_text(encoding="utf-8"))
    note = data.get("_todo_verificar", "")
    assert "TODO-verificar" in note or "§11" in note or "verificar" in note.lower(), (
        f"{fixture_path.name} must carry a _todo_verificar note referencing §11"
    )
