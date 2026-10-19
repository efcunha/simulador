"""pytest fixtures and import wiring for the synthetic_clouds test suite.

Two import concerns are handled here:

1. The package is imported as ``tools.synthetic_clouds.*`` — the repo root
   (``D:\\synthetic-clouds``) must be on ``sys.path`` so that namespace resolves
   when pytest runs from the package directory.
2. The FOCUS fidelity tests (AC-11) feed renderer output to the REAL
   ``parser.py (modulo do consumidor)``. That module depends only on
   ``pandas`` + ``structlog`` (verified) and does NOT import ``app`` package
   state, so it is loaded standalone via ``importlib`` to avoid triggering the
   heavy ``app`` package ``__init__`` (DB/config). ``real_parser`` exposes it.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

# Repo root = parents[3] of this file:
#   tests/conftest.py -> synthetic_clouds -> tools -> <repo root>
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

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
