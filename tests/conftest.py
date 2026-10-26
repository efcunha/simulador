"""pytest wiring for the repository-root ``tests`` directory.

The suites under test live in sibling trees (the azure-sim package under
``emulators/azure-sim``, the generator under ``tools``), so both roots go on
``sys.path`` -- the same wiring the per-package ``conftest.py`` files do.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# tests -> repo root.
_REPO_ROOT = Path(__file__).resolve().parents[1]
# The importable ``azure_sim`` package parent.
_AZURE_SIM_ROOT = _REPO_ROOT / "emulators" / "azure-sim"

for _entry in (str(_AZURE_SIM_ROOT), str(_REPO_ROOT)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)


@pytest.fixture(scope="session")
def azure_api_client() -> Iterator[TestClient]:
    """A TestClient bound to the azure-sim API app (the gated estate)."""
    from azure_sim.api.app import create_app
    from azure_sim.config import load_settings

    app = create_app(load_settings(env={}, API_PAGE_SIZE=10000))
    with TestClient(app) as client:
        yield client
