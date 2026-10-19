"""Thin wrapper that builds the frozen, gated canonical estate (mirrors azure-sim).

aws-sim is a PURE CONSUMER of the Phase 1 generator: the pipeline is exactly
``build_estate`` -> ``apply_all`` -> ``gate.run``, and the gate is fail-closed. Every
router projects from the single ``CanonicalEstate`` this returns, so the drift input and
the infrastructure inventory are mutually consistent by construction.
"""

from __future__ import annotations

from tools.synthetic_clouds.generate.estate_builder import build_estate
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.scenarios.emit import apply_all
from tools.synthetic_clouds.validate import gate


def build_simulated_estate(seed: int, profile: str, currency: str) -> CanonicalEstate:
    """Build, scenario-apply, and gate a ``CanonicalEstate``.

    Raises whatever the Phase 1 gate raises on an invalid estate (fail-closed); the
    caller never sees a half-built estate.
    """
    estate = apply_all(build_estate(seed=seed, profile=profile, currency=currency))
    gate.run(estate)
    return estate
