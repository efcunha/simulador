"""Fixture store: load the rendered REST snapshots at startup (design sec. 5.3).

Reads ``GCP_SIM_FIXTURES_DIR`` (default ``/fixtures``) once at import/boot and
holds the per-endpoint JSON bodies in memory, served read-only. If the dir is
missing or empty the process exits non-zero at boot (design sec. 12 fatal row).

The snapshots are produced by the ``gcp_rest_fixtures`` renderer; the filenames
here match that renderer's output.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# Fixture filenames the gcp_rest_fixtures renderer emits (design sec. 5.3).
_FIXTURE_FILES = (
    "cai_search_all_resources.json",
    "cai_search_all_iam_policies.json",
    "cai_analyze_iam_policy.json",
    "scc_sources.json",
    "scc_findings.json",
    "recommender_recommendations.json",
    "recommender_insights.json",
    "catalog_services.json",
    "catalog_skus.json",
    "monitoring_time_series.json",
    "monitoring_metric_descriptors.json",
    "monitoring_alert_policies.json",
    "budgets.json",
)


class FixtureError(RuntimeError):
    """Raised when the fixtures directory is missing or empty (fatal at boot)."""


class FixtureStore:
    """In-memory holder of the rendered REST fixture bodies."""

    def __init__(self, bodies: dict[str, Any]) -> None:
        self._bodies = bodies

    def get(self, name: str) -> dict[str, Any]:
        """Return the fixture body for ``name`` (empty default if absent)."""
        body: dict[str, Any] = self._bodies.get(name, {})
        return body

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._bodies))


def fixtures_dir() -> Path:
    """Return the configured fixtures directory (``GCP_SIM_FIXTURES_DIR``)."""
    return Path(os.environ.get("GCP_SIM_FIXTURES_DIR", "/fixtures"))


def load_fixtures(directory: Path | None = None) -> FixtureStore:
    """Load all fixture bodies from ``directory``; raise ``FixtureError`` if empty.

    At least one known fixture file must be present and parse as JSON; otherwise
    the service has no data to serve and must fail at boot.
    """
    target = directory or fixtures_dir()
    if not target.is_dir():
        raise FixtureError(f"fixtures dir not found: {target}")
    bodies: dict[str, Any] = {}
    for name in _FIXTURE_FILES:
        path = target / name
        if path.is_file():
            bodies[name] = json.loads(path.read_text(encoding="utf-8"))
    if not bodies:
        raise FixtureError(f"no fixtures found under {target} (expected one of {', '.join(_FIXTURE_FILES)})")
    return FixtureStore(bodies)
