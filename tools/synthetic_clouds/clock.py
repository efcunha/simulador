"""Simulated clock: SIM_NOW, day advance, export latency, restatements (FR-B).

The generator walks a window day-by-day. For each simulated day ``D``:

* usage/charge rows carry ``charge_period_start/end`` on ``D``;
* their ``export_time`` is ``D + 1 day`` at ``00:00 UTC`` (FR-B2 latency — data
  for day ``D`` first *appears* at ``D+1``);
* a restatement (FR-B3) appends a NEW row for an earlier ``usage_date`` with a
  LATER ``export_time``, leaving the original row byte-identical. The restatement
  is modeled as a signed ``Adjustment`` delta (see ``generate/consumption.py`` and
  ``generate/pricing.py``); this module only computes the clock values.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta


def export_time_for(usage_day: date) -> datetime:
    """Return the export availability instant for a charge dated ``usage_day``.

    FR-B2: a charge dated day ``D`` is first exported at ``D + 1 day`` at
    ``00:00 UTC``.
    """
    return datetime.combine(usage_day + timedelta(days=1), time(0, 0, 0), tzinfo=UTC)


def restatement_export_time_for(original_usage_day: date, restated_on_day: date) -> datetime:
    """Return the (later) export instant for a restatement of ``original_usage_day``.

    FR-B3: the restatement is exported on ``restated_on_day`` (strictly after the
    original export), so its ``export_time`` is ``restated_on_day + 1 day`` at
    ``00:00 UTC`` — strictly later than the original ``export_time`` whenever
    ``restated_on_day > original_usage_day``.
    """
    return export_time_for(restated_on_day)


@dataclass(slots=True)
class SimClock:
    """Owns ``SIM_NOW`` and advances the simulation day-by-day.

    ``sim_start`` is the first simulated day; ``sim_now`` is the current (last
    emitted) day. ``advance`` moves ``sim_now`` forward one day at a time. The
    clock never mutates already-emitted rows — advancing only appends new days.
    """

    sim_start: date
    sim_now: date

    @classmethod
    def starting_at(cls, sim_start: date, window_days: int) -> SimClock:
        """Build a clock whose ``sim_now`` is ``window_days - 1`` days after start.

        A ``window_days`` of 1 means ``sim_now == sim_start`` (a single day).
        """
        if window_days < 1:
            raise ValueError("window_days must be >= 1")
        return cls(sim_start=sim_start, sim_now=sim_start + timedelta(days=window_days - 1))

    def days(self) -> list[date]:
        """Return every simulated day from ``sim_start`` through ``sim_now``."""
        span = (self.sim_now - self.sim_start).days
        return [self.sim_start + timedelta(days=i) for i in range(span + 1)]

    def is_last_day(self, day: date) -> bool:
        """Return ``True`` when ``day`` is exactly ``sim_now`` (the latest day)."""
        return day == self.sim_now
