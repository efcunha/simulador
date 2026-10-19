"""AC-14: scenarios.json has all 28 entries (C01..C18, A01..A10) with required fields.

Also exercises ``apply_all`` and the gabarito writer end-to-end on a tiny estate.
"""

from __future__ import annotations

import json
from datetime import date

from tools.synthetic_clouds.generate.estate_builder import build_estate
from tools.synthetic_clouds.scenarios.catalog import CATALOG, catalog_ids
from tools.synthetic_clouds.scenarios.emit import apply_all
from tools.synthetic_clouds.scenarios.gabarito import build_gabarito, write_gabarito

_EXPECTED_IDS = tuple(f"C{i:02d}" for i in range(1, 19)) + tuple(f"A{i:02d}" for i in range(1, 11))
_EXPECTED_COUNT = 28


def test_catalog_has_stable_ids() -> None:
    assert catalog_ids() == _EXPECTED_IDS
    assert len(CATALOG) == _EXPECTED_COUNT


def test_each_scenario_has_required_fields() -> None:
    for spec in CATALOG:
        assert spec.id
        assert spec.title
        assert spec.emitted_inputs  # non-empty
        assert spec.expected_effect
        assert spec.expected_engine_output.assertion
        # window offsets resolvable
        assert spec.window.start_offset is not None
        assert spec.window.end_offset is not None


def test_apply_all_sets_scenario_ids_and_preserves_identity() -> None:
    base = build_estate(seed=123, profile="small", currency="USD")
    final = apply_all(base)
    assert final.scenario_ids == _EXPECTED_IDS
    # C18 adds one resource; identity set grows by exactly 1.
    assert len(final.resources) == len(base.resources) + 1


def test_gabarito_model_validates_all() -> None:
    model = build_gabarito(seed=123, profile="small", sim_start=date(2026, 1, 1), sim_now=date(2026, 2, 14))
    assert len(model.scenarios) == _EXPECTED_COUNT
    assert model.version == "synthetic.seed.v1"
    assert {s.id for s in model.scenarios} == set(_EXPECTED_IDS)


def test_gabarito_writes_deterministic_json(tmp_path) -> None:  # type: ignore[no-untyped-def]
    out = tmp_path / "scenarios.json"
    write_gabarito(123, "small", date(2026, 1, 1), date(2026, 2, 14), out)
    first = out.read_text(encoding="utf-8")
    write_gabarito(123, "small", date(2026, 1, 1), date(2026, 2, 14), out)
    assert out.read_text(encoding="utf-8") == first
    doc = json.loads(first)
    assert len(doc["scenarios"]) == _EXPECTED_COUNT
    assert doc["seed"] == 123
