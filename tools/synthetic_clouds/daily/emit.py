"""Emit one simulated day through the renderers that already exist (FR-22.4).

A second *emitter*, never a third artifact format. Each day lands in its own
directory and is written by the same ``store.write`` and the same registered
renderers the one-shot generator uses, so the daily output is byte-comparable with
the one-shot output for an overlapping window and the ingestion path sees one shape
rather than two.

That is also why there is no "daily artifact" class anywhere in this package: if the
daily surface needed a schema the one-shot surface does not produce, the ingestion
path would have to learn it, and FR-22.4 forbids exactly that.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from tools.synthetic_clouds.daily.engine import build_day
from tools.synthetic_clouds.daily.window import DailyWindow, days_in_range
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.render.base import get_renderer, registered_names
from tools.synthetic_clouds.serialize import store

#: Output root, relative to the package. ``daily`` is a sibling of ``out`` so a daily
#: run never collides with a one-shot run, and both stay under the package's write
#: boundary (NFR-4).
DEFAULT_OUT = Path(__file__).resolve().parents[1] / "out" / "daily"


def emit_day(
    estate: CanonicalEstate,
    out_root: Path,
    day: date,
    renderers: tuple[str, ...],
) -> tuple[Path, ...]:
    """Write one day's canonical estate and rendered artifacts; return the paths.

    ``out_root/<YYYY-MM-DD>/<seed>-<profile>-<currency>/{canonical,render}/`` — the
    day is the outer directory because that is the axis a daily run iterates, and
    because a re-run of one day then rewrites exactly one directory (FR-22.5).
    """
    day_dir = out_root / day.isoformat()
    canonical = store.write(estate, day_dir)
    run_dir = canonical.parent
    written: list[Path] = [canonical]
    for name in renderers:
        written.extend(get_renderer(name).render(estate, run_dir / "render"))
    return tuple(written)


def run_days(
    seed: int,
    profile: str,
    currency: str,
    days: tuple[date, ...],
    out_root: Path = DEFAULT_OUT,
    renderers: tuple[str, ...] | None = None,
) -> tuple[Path, ...]:
    """Generate and emit every day in ``days``, in the order given.

    Order-independence is a property of :func:`build_day`, not of this loop: each day
    is built from its own window, so generating a month backwards produces the same
    tree as generating it forwards. The loop exists only to sequence the writes.
    """
    names = renderers if renderers is not None else tuple(registered_names())
    written: list[Path] = []
    for day in days:
        estate = build_day(seed, profile, currency, day)
        written.extend(emit_day(estate, out_root, day, names))
    return tuple(written)


def run_range(
    seed: int,
    profile: str,
    currency: str,
    start: date,
    end: date,
    out_root: Path = DEFAULT_OUT,
    renderers: tuple[str, ...] | None = None,
) -> tuple[Path, ...]:
    """Generate and emit every day from ``start`` through ``end`` inclusive."""
    return run_days(seed, profile, currency, days_in_range(start, end), out_root, renderers)


def window_for(day: date) -> DailyWindow:
    """Return the window a given day is generated from. Exposed for callers and tests."""
    return DailyWindow(day)
