"""The one estate every Phase 6 runtime projection reads.

The five API families this phase adds -- cloudresourcemanager, compute, functions,
servicehealth, storage -- describe resources no rendered fixture carries in its own shape.
``fixtures.py`` lists all eleven fixture files, and the CAI snapshot among them holds one
generic asset row per GCP resource (a project id, a location, labels): that is not an
instance, a function or a bucket, and it cannot be turned into one -- an instance row needs
a zone, a machine type and a status, a bucket row a storage class, and inventing them from
an asset row is exactly what this phase must not do. So these routers project the canonical
estate directly, as ``emulators/aws-sim/aws_sim/estate.py`` and its Azure sibling do. The
pipeline is ``build_estate`` -> ``apply_all`` -> ``gate.run`` and the gate is fail-closed, so
a projection can never read a half-valid estate.

``SEED`` / ``PROFILE`` / ``CURRENCY`` are the env names aws-sim and azure-sim already
use, and the defaults are this plane's own: ``scripts/synthetic-clouds/gcp-up.ps1``
renders the fixtures at ``GCP_SEED=123`` / ``GCP_PROFILE=small`` / ``USD``. With the
defaults the fixtures the service loads and the estate these projections walk are the
**same** estate, which is what the design's cross-plane join rests on -- a
``resource_uuid`` in an SCC finding and the instance the Compute route serves are one
row of one generation.

The estate is cached per ``(seed, profile, currency)``. It is frozen and deterministic,
so two callers with one configuration describe one estate and pay for one build;
``create_app`` runs per app instance (and per test), and rebuilding a few hundred resources
for each of them would be pure cost. A caller that asks for another profile still gets
its own estate, because the settings are part of the cache key.

Boot is the boundary, not a request: a bad env value or a gate violation raises here and
the service fails to start, which is the same fail-closed behavior the fixture loader
already has (``fixtures.py`` raises ``FixtureError`` -> non-zero exit).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from functools import lru_cache

from tools.synthetic_clouds.generate.estate_builder import build_estate
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.scenarios.emit import apply_all
from tools.synthetic_clouds.validate import gate

#: Defaults matching this plane's render step (scripts/synthetic-clouds/gcp-up.ps1).
DEFAULT_SEED = 123
DEFAULT_PROFILE = "small"
DEFAULT_CURRENCY = "USD"

PROFILES: frozenset[str] = frozenset({"small", "medium", "large"})
CURRENCIES: frozenset[str] = frozenset({"USD", "BRL"})


class EstateConfigError(ValueError):
    """Raised on an invalid estate env value -- fatal at boot, fail-closed."""


def _require_int(env: Mapping[str, str], key: str, default: int) -> int:
    """Return ``key`` from ``env`` as an int, or ``default`` when absent/unset."""
    raw = env.get(key, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise EstateConfigError(f"{key} must be an integer, got {raw!r}") from exc


def _require_enum(env: Mapping[str, str], key: str, default: str, allowed: frozenset[str]) -> str:
    """Return ``key`` from ``env`` when it is one of ``allowed``, else ``default``."""
    raw = env.get(key, "").strip() or default
    if raw not in allowed:
        raise EstateConfigError(f"{key} must be one of {sorted(allowed)}, got {raw!r}")
    return raw


@lru_cache(maxsize=8)
def _build(seed: int, profile: str, currency: str) -> CanonicalEstate:
    """Build, scenario-apply and gate the estate for one configuration."""
    estate = apply_all(build_estate(seed=seed, profile=profile, currency=currency))
    gate.run(estate)
    return estate


def load_estate(env: Mapping[str, str] | None = None) -> CanonicalEstate:
    """Return the frozen estate configured by ``env`` (``os.environ`` by default).

    Raises :class:`EstateConfigError` on an invalid value and whatever the gate raises on
    an invalid estate; the caller (app startup) never receives a partial estate.
    """
    base: Mapping[str, str] = os.environ if env is None else env
    seed = _require_int(base, "SEED", DEFAULT_SEED)
    profile = _require_enum(base, "PROFILE", DEFAULT_PROFILE, PROFILES)
    currency = _require_enum(base, "CURRENCY", DEFAULT_CURRENCY, CURRENCIES)
    return _build(seed, profile, currency)
