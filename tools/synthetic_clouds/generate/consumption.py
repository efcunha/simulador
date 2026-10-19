"""Daily consumption model: weekly seasonality x growth x seeded jitter (FR-D1).

Pure, deterministic given the passed ``random.Random`` stream. The quantity is
``base x seasonality(weekday) x growth(day_index) x jitter`` — all factors
seed-derived so the same inputs reproduce the same quantity (NFR-1).
"""

from __future__ import annotations

import random
from decimal import Decimal

from tools.synthetic_clouds.generate import constants as const


def growth_factor(day_index: int) -> Decimal:
    """Return the linear growth multiplier for ``day_index`` (FR-D1)."""
    return Decimal("1") + const.GROWTH_PER_DAY * Decimal(day_index)


def seasonality_factor(weekday: int) -> Decimal:
    """Return the weekday seasonality multiplier (Mon=0..Sun=6; FR-D1)."""
    return const.WEEKDAY_SEASONALITY[weekday % 7]


def daily_quantity(base_units: Decimal, weekday: int, day_index: int, rng: random.Random) -> Decimal:
    """Return the seeded daily usage quantity for a resource-day.

    ``jitter`` is a deterministic +/-10% band drawn from the provided RNG stream.
    """
    jitter = Decimal(str(round(rng.uniform(0.90, 1.10), 6)))
    qty = base_units * seasonality_factor(weekday) * growth_factor(day_index) * jitter
    return qty.quantize(const.SIX_DP)
