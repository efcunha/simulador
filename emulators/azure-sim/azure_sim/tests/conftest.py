"""pytest fixtures and import wiring for the azure-sim test suite.

Mirrors ``tools/synthetic_clouds/tests/conftest.py`` (design §3, FEAT-001 step 3).
Three import concerns are handled here:

1. The Phase 1 generator is imported as ``tools.synthetic_clouds.*`` — the
   worktree root must be on ``sys.path`` so that namespace resolves when pytest
   runs from the package directory.
2. azure-sim itself is imported as the top-level ``azure_sim`` package, so the
   package parent dir (``emulators/azure-sim``) must also be on ``sys.path``.
3. The FOCUS fidelity test (FEAT-001 step 7) feeds laid-out export bytes to the
   REAL ``parser.py (modulo do consumidor)``. That module depends
   only on ``pandas`` + ``structlog`` (verified) and does NOT import the ``app``
   package, so it is loaded standalone via ``importlib`` to avoid triggering the
   heavy ``app`` package ``__init__`` (DB/config). ``real_parser`` exposes it.

Depth note: this file is
``emulators/azure-sim/azure_sim/tests/conftest.py``, so
  parents[0] = tests
  parents[1] = azure_sim        (the importable package)
  parents[2] = azure-sim        (the package parent -> on sys.path for ``import azure_sim``)
  parents[3] = services
  parents[4] = <worktree root>  (-> on sys.path for ``import tools.synthetic_clouds``)
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

_PKG_PARENT = Path(__file__).resolve().parents[2]  # emulators/azure-sim
_REPO_ROOT = Path(__file__).resolve().parents[4]  # worktree root

for _entry in (str(_PKG_PARENT), str(_REPO_ROOT)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

_PARSER_PATH = _REPO_ROOT / "consumidor" / "services" / "cur_ingestion" / "parser.py"


def _load_real_parser() -> ModuleType:
    """Load the real CUR parser as a standalone module (no ``app`` package init)."""
    spec = importlib.util.spec_from_file_location("cur_parser", _PARSER_PATH)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise RuntimeError(f"cannot load parser from {_PARSER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["cur_parser"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def real_parser() -> ModuleType:
    """Session-scoped handle to the real cur_ingestion parser module."""
    if not _PARSER_PATH.exists():  # pragma: no cover - environment guard
        pytest.skip(f"real parser not found at {_PARSER_PATH}")
    return _load_real_parser()


class FakeExportWriter:
    """Records each run write so tests assert Exports execute without Azurite."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def write_run(self, *, container, run_prefix, parts, manifest) -> None:
        self.calls.append({"run_prefix": run_prefix, "manifest": manifest, "parts": parts})


@pytest.fixture(scope="session")
def api_client():
    """A TestClient bound to the FastAPI app with a small page size.

    Uses ``API_PAGE_SIZE=5`` so paging tests exercise multiple pages against the
    estate. The export writer is faked so ``Exports .../run`` never touches
    Azurite. Yields ``(client, app)``.
    """
    from fastapi.testclient import TestClient

    from azure_sim.api.app import create_app
    from azure_sim.config import load_settings

    # A page size that still forces multi-page paging over the small-estate
    # cost-query rows (~28k) without issuing thousands of HTTP round-trips.
    app = create_app(load_settings(env={}, API_PAGE_SIZE=10000))
    app.state.export_writer = FakeExportWriter()
    with TestClient(app) as client:
        yield client, app
