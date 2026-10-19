"""Calendar arithmetic for the daily cadence (FR-22.1).

Deliberately trivial and deliberately separate from the generator: everything the
daily surface does is derived from a ``DailyWindow``, so "which days exist and what
window backs day N" is decided in one place that a reviewer can read in full.

The date is always an argument. Nothing here reads the wall clock, so a test can
reproduce a year of days in one run — and a daily run that silently produced
"today" would pass locally and fail the same check a day later.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta


def month_start(day: date) -> date:
    """Return the first day of ``day``'s month."""
    return day.replace(day=1)


def days_in_range(start: date, end: date) -> tuple[date, ...]:
    """Return every day from ``start`` through ``end`` inclusive, ascending."""
    if end < start:
        raise ValueError(f"end {end} precedes start {start}")
    return tuple(start + timedelta(days=offset) for offset in range((end - start).days + 1))


@dataclass(frozen=True, slots=True)
class DailyWindow:
    """The **month-to-date** window that ends on ``day``.

    A day's export is month-to-date rather than a single day, and that is not a
    convenience: FinOps promotion is REPLACE-per-period, so an export holding
    one day of a billing period would overwrite the rest of that period on every run
    and nothing would ever accumulate. It is also what a real FOCUS *daily* delivery
    contains.

    Deriving the start from the day itself is what keeps FR-22.1 true under that
    choice: the window is a pure function of the day, so day N can be generated
    without day N-1 ever having been generated.
    """

    day: date

    @property
    def start(self) -> date:
        """First day of the month containing :attr:`day`."""
        return month_start(self.day)

    @property
    def days(self) -> int:
        """Number of days in the window, inclusive: ``1`` to ``31``."""
        return (self.day - self.start).days + 1
