"""Gabarito serializer: ScenarioSpec -> docs/synthetic-clouds/scenarios.json.

Validated by a Pydantic v2 model before writing (design sec. 10.2). The JSON is
written deterministically (fixed key order, sorted keys, trailing newline) so the
gabarito is byte-stable for a given ``(seed, profile)`` (NFR-1/2).

Windows are resolved against the estate's ``sim_start``/``sim_now`` so the emitted
``window`` dates are concrete ISO dates in the gabarito.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from pydantic import BaseModel, Field

from tools.synthetic_clouds.render.markers import RECOMMENDATION_MODEL
from tools.synthetic_clouds.scenarios.catalog import CATALOG, ScenarioSpec

GABARITO_VERSION = RECOMMENDATION_MODEL  # "synthetic.seed.v1"


class _WindowModel(BaseModel):
    start: date
    end: date


class _TargetModel(BaseModel):
    provider: str | None
    service: str | None
    scope_hint: str | None


class _ExpectedEngineOutputModel(BaseModel):
    engine: str | None
    assertion: str


class _EvidenceModel(BaseModel):
    screen: str | None
    report: str | None
    engine: str | None


class _ScenarioModel(BaseModel):
    id: str
    title: str
    window: _WindowModel
    target: _TargetModel
    emitted_inputs: list[str]
    expected_effect: str
    expected_engine_output: _ExpectedEngineOutputModel
    evidence: _EvidenceModel


class GabaritoModel(BaseModel):
    """The validated ``scenarios.json`` document (design sec. 10.2)."""

    version: str
    seed: int
    profile: str
    scenarios: list[_ScenarioModel] = Field(min_length=28, max_length=28)


def _resolve_window(spec: ScenarioSpec, sim_start: date, sim_now: date) -> _WindowModel:
    start = sim_now if spec.window.start_offset == -1 else sim_start + timedelta(days=spec.window.start_offset)
    end = sim_now if spec.window.end_offset == -1 else sim_start + timedelta(days=spec.window.end_offset)
    # Clamp to the simulated range so the gabarito never points past SIM_NOW.
    end = min(end, sim_now)
    start = min(start, end)
    return _WindowModel(start=start, end=end)


def build_gabarito(seed: int, profile: str, sim_start: date, sim_now: date) -> GabaritoModel:
    """Build and validate the gabarito model from the catalog."""
    scenarios = [
        _ScenarioModel(
            id=spec.id,
            title=spec.title,
            window=_resolve_window(spec, sim_start, sim_now),
            target=_TargetModel(
                provider=spec.target.provider,
                service=spec.target.service,
                scope_hint=spec.target.scope_hint,
            ),
            emitted_inputs=list(spec.emitted_inputs),
            expected_effect=spec.expected_effect,
            expected_engine_output=_ExpectedEngineOutputModel(
                engine=spec.expected_engine_output.engine,
                assertion=spec.expected_engine_output.assertion,
            ),
            evidence=_EvidenceModel(
                screen=spec.evidence.screen,
                report=spec.evidence.report,
                engine=spec.evidence.engine,
            ),
        )
        for spec in CATALOG
    ]
    return GabaritoModel(version=GABARITO_VERSION, seed=seed, profile=profile, scenarios=scenarios)


def write_gabarito(seed: int, profile: str, sim_start: date, sim_now: date, out_path: Path) -> Path:
    """Validate and write ``scenarios.json`` to ``out_path`` deterministically."""
    model = build_gabarito(seed, profile, sim_start, sim_now)
    payload = model.model_dump(mode="json")
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")
    return out_path
