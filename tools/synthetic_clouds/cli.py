"""CLI entry point: build -> emit scenarios -> gate -> store -> render -> gabarito.

The flow validates (gate, fail-closed) BEFORE any artifact or scenarios.json is
written (design sec. 12). The ``--out`` guard is tighter than "inside the repo":
the resolved path must be UNDER ``tools/synthetic_clouds/`` and the only other
permitted write target is the fixed ``docs/synthetic-clouds/scenarios.json`` path
(NFR-5, AC-1).
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from tools.synthetic_clouds.generate.estate_builder import CANONICAL_EPOCH, build_estate
from tools.synthetic_clouds.render.base import get_renderer, registered_names
from tools.synthetic_clouds.scenarios.emit import apply_all
from tools.synthetic_clouds.scenarios.gabarito import write_gabarito
from tools.synthetic_clouds.serialize import store
from tools.synthetic_clouds.validate import gate


class GeneratorError(Exception):
    """Raised for fatal CLI/generation errors (surfaced to a non-zero exit)."""


# Repo root = parents[2] of this file: cli.py -> synthetic_clouds -> tools -> root.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_PACKAGE_ROOT = _REPO_ROOT / "tools" / "synthetic_clouds"
_DEFAULT_OUT = _PACKAGE_ROOT / "out"
_SCENARIOS_OUT = _REPO_ROOT / "docs" / "synthetic-clouds" / "scenarios.json"


def _iso_day(raw: str) -> date:
    """Parse a ``YYYY-MM-DD`` argument, failing at argparse time rather than mid-build."""
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"expected YYYY-MM-DD, got {raw!r}") from exc


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m tools.synthetic_clouds")
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--profile", choices=("small", "medium", "large"), required=True)
    parser.add_argument("--currency", choices=("USD", "BRL"), default="USD")
    # The simulated window is a parameter of the generator, not a pinned constant: leaving both
    # unset keeps the canonical epoch and the profile's window, so every existing caller stays
    # byte-identical, while a demo can ask for the window it means to show (`--sim-start` +
    # `--window-days 282` covers the epoch through today).
    parser.add_argument(
        "--sim-start",
        type=_iso_day,
        default=None,
        help=f"first day of the simulated window, YYYY-MM-DD (default: {CANONICAL_EPOCH})",
    )
    parser.add_argument(
        "--window-days",
        type=int,
        default=None,
        help="length of the simulated window in days (default: the profile's window)",
    )
    parser.add_argument(
        "--emit",
        default=",".join(registered_names()),
        help="comma-separated renderer names: " + ", ".join(registered_names()),
    )
    parser.add_argument("--out", type=Path, default=_DEFAULT_OUT)
    parser.add_argument("--scenarios-out", type=Path, default=_SCENARIOS_OUT)
    return parser.parse_args(argv)


def _guard_out(out: Path) -> Path:
    """Reject any --out that does not resolve under tools/synthetic_clouds/ (NFR-5)."""
    resolved = out.resolve()
    package_resolved = _PACKAGE_ROOT.resolve()
    if package_resolved not in resolved.parents and resolved != package_resolved:
        raise GeneratorError(f"--out {resolved} must be under {package_resolved} (NFR-5 write boundary)")
    return resolved


def _guard_scenarios_out(path: Path) -> Path:
    """Only the fixed docs/synthetic-clouds/scenarios.json path is permitted (NFR-5)."""
    resolved = path.resolve()
    if resolved != _SCENARIOS_OUT.resolve():
        raise GeneratorError(f"--scenarios-out must be {_SCENARIOS_OUT.resolve()} (NFR-5 write boundary)")
    return resolved


def _emit_names(raw: str) -> list[str]:
    names = [token.strip() for token in raw.split(",") if token.strip()]
    valid = set(registered_names())
    for name in names:
        if name not in valid:
            raise GeneratorError(f"unknown renderer {name!r}; valid: {', '.join(sorted(valid))}")
    return names


def main(argv: list[str] | None = None) -> int:
    """Run the generator pipeline; return a process exit code."""
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    try:
        out = _guard_out(args.out)
        scenarios_out = _guard_scenarios_out(args.scenarios_out)
        emit_names = _emit_names(args.emit)

        estate = apply_all(
            build_estate(
                args.seed,
                args.profile,
                args.currency,
                sim_start=args.sim_start,
                window_days=args.window_days,
            )
        )
        gate.run(estate)  # fail-closed BEFORE any write

        canonical = store.write(estate, out)
        run_dir = canonical.parent
        for name in emit_names:
            get_renderer(name).render(estate, run_dir / "render")

        write_gabarito(estate.seed, estate.profile, estate.sim_start, estate.sim_now, scenarios_out)
    except GeneratorError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"ok: wrote canonical+render under {out} and gabarito {scenarios_out}")
    return 0
