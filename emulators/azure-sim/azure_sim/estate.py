"""Thin wrapper that builds the frozen, gated canonical estate (design §7).

azure-sim is a PURE CONSUMER of the Phase 1 generator: it never reinvents estate
construction. The pipeline is exactly the one the Phase 1 package exposes —
``build_estate(seed, profile, currency)`` -> ``apply_all(estate)`` ->
``gate.run(estate)`` — and the gate is fail-closed (``gate.run`` returns ``None``
and raises on the first violation). Both the exporter and the HTTP API project
from the single ``CanonicalEstate`` this returns, so cost totals are mutually
consistent by construction.
"""

from __future__ import annotations

from tools.synthetic_clouds.generate.estate_builder import build_estate
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.scenarios.emit import apply_all
from tools.synthetic_clouds.validate import gate


def build_simulated_estate(
    seed: int, profile: str, currency: str, window_days: int | None = None
) -> CanonicalEstate:
    """Build, scenario-apply, and gate a ``CanonicalEstate``.

    ``window_days`` overrides the profile's own window length; ``None`` keeps it, so an unset
    ``WINDOW_DAYS`` behaves exactly as before.

    Raises whatever the Phase 1 gate raises on an invalid estate (fail-closed);
    the caller (exporter/API) never sees a half-built estate.
    """
    estate = apply_all(
        build_estate(seed=seed, profile=profile, currency=currency, window_days=window_days)
    )
    gate.run(estate)
    return estate
