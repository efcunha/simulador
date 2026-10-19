"""Build the estate as FinOps would see it on one simulated day (FR-22.3).

One function, and its whole job is to decide *what a day is*. The result carries the
three axes FR-22 names, for all three providers, without any further projection:

* **values** — ``billing_lines`` for the month to date, each row's own day readable
  from ``charge_period_start``/``usage_date``;
* **alerts** — the findings whose ``raised_on`` has arrived by this day, so they
  accumulate across the month;
* **infrastructure** — the resources and their inventory assets, as the simulators
  project them into their screens.

Scenarios are **not** applied here, on purpose. ``scenarios/emit.py`` injects its 18
conditions relative to ``sim_start``, so on a shifting month-to-date window the same
scenario row would move from one day's export to the next. Scenarios are a one-shot
contract-testing concern; the daily surface emits the baseline estate that the
simulators serve.
"""

from __future__ import annotations

from datetime import date

from tools.synthetic_clouds.daily.window import DailyWindow
from tools.synthetic_clouds.generate.estate_builder import build_estate
from tools.synthetic_clouds.model.estate import CanonicalEstate


def build_day(seed: int, profile: str, currency: str, day: date) -> CanonicalEstate:
    """Build the canonical estate whose window is the month to date ending on ``day``.

    Deterministic in ``(seed, profile, currency, day)`` alone: the window start comes
    from the day, and every stream the builder draws from is keyed by the store, the
    resource or the finding rather than by how many days happen to precede it. Two
    calls with the same ``day`` produce byte-identical artifacts, which is AC-22's
    "day N alone equals day N inside a range".
    """
    window = DailyWindow(day)
    return build_estate(
        seed=seed,
        profile=profile,
        currency=currency,
        sim_start=window.start,
        window_days=window.days,
    )
