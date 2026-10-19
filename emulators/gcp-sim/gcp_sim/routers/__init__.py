"""gcp-sim routers package: one module per GCP API family (design sec. 5.1)."""

from __future__ import annotations

from fastapi import Request
from tools.synthetic_clouds.model.estate import CanonicalEstate

from gcp_sim.fixtures import FixtureStore


def store(request: Request) -> FixtureStore:
    """Return the ``FixtureStore`` held on ``app.state`` (typed accessor)."""
    fixtures = request.app.state.fixtures
    if not isinstance(fixtures, FixtureStore):  # pragma: no cover - defensive
        raise RuntimeError("fixtures not initialized on app.state")
    return fixtures


def estate(request: Request) -> CanonicalEstate:
    """Return the frozen estate held on ``app.state`` (typed accessor).

    The Phase 6 families (cloudresourcemanager, compute, functions, servicehealth,
    storage) project the estate directly, because no rendered fixture carries their
    resources; ``gcp_sim.estate.load_estate`` builds it once at boot.
    """
    loaded = request.app.state.estate
    if not isinstance(loaded, CanonicalEstate):  # pragma: no cover - defensive
        raise RuntimeError("estate not initialized on app.state")
    return loaded
