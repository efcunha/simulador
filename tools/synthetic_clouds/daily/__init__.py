"""Daily cadence: generate values, alerts and infrastructure for each simulated day.

FR-22 asks for a day-addressable generation surface so FinOps can ingest day
after day — for testing, debugging and alerting — instead of only ever seeing one
frozen window. Three modules:

* :mod:`window` — the calendar. A day's export is a **month-to-date** window, because
  FinOps promotion is REPLACE-per-period and a single-day export would erase
  the rest of the period on every run.
* :mod:`engine` — ``build_day``, deterministic in ``(seed, profile, currency, day)``
  alone, carrying the three axes (values, alerts, infrastructure) for all providers.
* :mod:`emit` — the same ``store.write`` and the same registered renderers the
  one-shot generator uses. A second emitter, never a third artifact format.

Nothing here reads the wall clock and nothing applies the 18 scenario transforms:
those are one-shot contract artefacts, and shifting them onto a moving window would
make the same scenario row jump between days.
"""

from __future__ import annotations

from tools.synthetic_clouds.daily.emit import DEFAULT_OUT, emit_day, run_days, run_range
from tools.synthetic_clouds.daily.engine import build_day
from tools.synthetic_clouds.daily.window import DailyWindow, days_in_range, month_start

__all__ = [
    "DEFAULT_OUT",
    "DailyWindow",
    "build_day",
    "days_in_range",
    "emit_day",
    "month_start",
    "run_days",
    "run_range",
]
