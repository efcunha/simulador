"""CLI: ``python -m tools.synthetic_clouds.daily`` (FR-22).

One day or a range, always from an explicit date argument. Examples:

    python -m tools.synthetic_clouds.daily --seed 123 --profile small --day 2026-03-18
    python -m tools.synthetic_clouds.daily --seed 123 --profile small --from 2026-03-01 --to 2026-03-31

The ``--out`` guard mirrors ``cli.py``'s: the resolved path must be under
``tools/synthetic_clouds/``, so a daily run cannot be pointed at the repository or at
a container bind mount (NFR-4, NFR-7).
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from tools.synthetic_clouds.daily.emit import DEFAULT_OUT, run_days
from tools.synthetic_clouds.daily.window import days_in_range
from tools.synthetic_clouds.render.base import registered_names

# repo_root = parents[3]: __main__.py -> daily -> synthetic_clouds -> tools -> root.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_PACKAGE_ROOT = _REPO_ROOT / "tools" / "synthetic_clouds"


class DailyError(Exception):
    """Raised for fatal CLI errors, surfaced as a non-zero exit."""


def _iso_day(raw: str) -> date:
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"--from/--to/--day expect YYYY-MM-DD, got {raw!r}") from exc


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m tools.synthetic_clouds.daily")
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--profile", choices=("small", "medium", "large"), required=True)
    parser.add_argument("--currency", choices=("USD", "BRL"), default="USD")
    parser.add_argument("--day", type=_iso_day, help="emit this single simulated day")
    parser.add_argument("--from", dest="start", type=_iso_day, help="first day of a range")
    parser.add_argument("--to", dest="end", type=_iso_day, help="last day of a range (default: --from)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--emit",
        default=",".join(registered_names()),
        help="comma-separated renderer names: " + ", ".join(registered_names()),
    )
    return parser.parse_args(argv)


def _resolve_days(args: argparse.Namespace) -> tuple[date, ...]:
    """Work out the days to generate, rejecting an under-specified request."""
    if args.day is not None and args.start is not None:
        raise DailyError("--day and --from are mutually exclusive")
    if args.day is not None:
        return (args.day,)
    if args.start is not None:
        return days_in_range(args.start, args.end or args.start)
    raise DailyError("one of --day or --from is required")


def _guard_out(out: Path) -> Path:
    resolved = out.resolve()
    package_resolved = _PACKAGE_ROOT.resolve()
    if package_resolved not in resolved.parents and resolved != package_resolved:
        raise DailyError(f"--out {resolved} must be under {package_resolved} (NFR-4 write boundary)")
    return resolved


def _emit_names(raw: str) -> tuple[str, ...]:
    names = [token.strip() for token in raw.split(",") if token.strip()]
    valid = set(registered_names())
    for name in names:
        if name not in valid:
            raise DailyError(f"unknown renderer {name!r}; valid: {', '.join(sorted(valid))}")
    return tuple(names)


def main(argv: list[str] | None = None) -> int:
    """Generate the requested days; return a process exit code."""
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    try:
        days = _resolve_days(args)
        out = _guard_out(args.out)
        names = _emit_names(args.emit)
        written = run_days(args.seed, args.profile, args.currency, days, out, names)
    except DailyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    first, last = days[0], days[-1]
    span = f"{first.isoformat()}" if first == last else f"{first.isoformat()}..{last.isoformat()}"
    print(f"ok: wrote {len(written)} artifacts for {len(days)} day(s) ({span}) under {out}")
    return 0


__all__ = ["DailyError", "main"]


if __name__ == "__main__":
    sys.exit(main())
