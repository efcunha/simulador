"""pytest fixtures for the gcp-sim service tests.

Builds a real fixtures directory by running the ``gcp_rest_fixtures`` renderer
against a tiny estate, then yields a FastAPI ``TestClient`` wired to it. The
service package is ``gcp_sim`` (this dir on sys.path); the renderer lives in the
repo-root ``tools.synthetic_clouds`` tree, so both roots are added to sys.path.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# gcp-sim package root (this file: tests/conftest.py -> gcp-sim).
_SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_SERVICE_ROOT))

# Repo root = parents[4]: tests -> gcp-sim -> synthetic-clouds -> deploy -> root.
_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


@pytest.fixture(scope="session")
def fixtures_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Render REST fixtures from a tiny estate into a temp dir."""
    from tools.synthetic_clouds.generate.estate_builder import build_estate
    from tools.synthetic_clouds.render.gcp_rest_fixtures import GcpRestFixturesRenderer
    from tools.synthetic_clouds.scenarios.emit import apply_all

    estate = apply_all(build_estate(seed=123, profile="small", currency="USD"))
    out = tmp_path_factory.mktemp("fixtures_root")
    GcpRestFixturesRenderer().render(estate, out)
    return out / "gcp_rest_fixtures"


@pytest.fixture()
def client(fixtures_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """Yield a TestClient for the gcp-sim app wired to the rendered fixtures."""
    monkeypatch.setenv("GCP_SIM_FIXTURES_DIR", str(fixtures_dir))
    from gcp_sim.app import create_app

    with TestClient(create_app()) as test_client:
        yield test_client
