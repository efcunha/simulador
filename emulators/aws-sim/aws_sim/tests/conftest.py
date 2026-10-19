"""pytest fixtures and import wiring for the aws-sim test suite.

Mirrors ``emulators/azure-sim/azure_sim/tests/conftest.py``. Two import concerns:

1. The Phase 1 generator is imported as ``tools.synthetic_clouds.*``, so the worktree
   root must be on ``sys.path``.
2. aws-sim itself is imported as the top-level ``aws_sim`` package, so the package
   parent dir (``emulators/aws-sim``) must also be on ``sys.path``.

Depth note: this file is ``emulators/aws-sim/aws_sim/tests/conftest.py``, so
  parents[0] = tests
  parents[1] = aws_sim            (the importable package)
  parents[2] = aws-sim            (the package parent -> on sys.path)
  parents[3] = services
  parents[4] = <worktree root>    (-> on sys.path for ``import tools.synthetic_clouds``)
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PKG_PARENT = Path(__file__).resolve().parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[4]

for _entry in (str(_PKG_PARENT), str(_REPO_ROOT)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)


@pytest.fixture(scope="session")
def api_client():
    """A TestClient bound to the aws-sim app. Yields ``(client, app)``."""
    from fastapi.testclient import TestClient

    from aws_sim.api.app import create_app
    from aws_sim.config import load_settings

    app = create_app(load_settings(env={}, SEED="42", PROFILE="small", CURRENCY="USD"))
    with TestClient(app) as client:
        yield client, app
