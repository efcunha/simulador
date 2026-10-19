"""Commitments, credits, and taxes (design sec. 4.4)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from tools.synthetic_clouds.model.identity import ResourceIdentity


@dataclass(slots=True, frozen=True)
class Commitment:
    """A reservation / Savings Plan / CUD applied to a scope.

    ``name``/``quantity``/``unit`` are the three fields the FOCUS
    ``CommitmentDiscountName``/``Quantity``/``Unit`` columns project: a real
    commitment has a display name the customer picks, a metered quantity and the
    unit that quantity is expressed in. They live here rather than in a renderer
    because inventing them at render time is exactly what the phase's
    derive-never-invent rule forbids.
    """

    identity: ResourceIdentity
    kind: str  # "reservation" | "savings_plan" | "cud"
    scope_id: str  # subscription_id / project_id it applies to
    period_start: date
    period_end: date
    committed_amount: Decimal
    status: str  # "Used" | "Unused" (FOCUS CommitmentDiscountStatus)
    name: str  # display name; carries the FinOps ``[SYNTH] `` marker
    quantity: Decimal  # metered amount the commitment covers, in ``unit``
    unit: str  # the unit ``quantity`` is expressed in (FOCUS CommitmentDiscountUnit)


@dataclass(slots=True, frozen=True)
class Credit:
    """A credit validated against applicable cost (FR-E2: amount <= applicable_cost)."""

    identity: ResourceIdentity
    scope_id: str  # subscription_id / project_id
    name: str
    amount: Decimal  # <= applicable_cost (FR-E2)
    applicable_cost: Decimal  # the cost this credit is validated against
    period_start: date
    period_end: date  # when the credit runs out (C06)


@dataclass(slots=True, frozen=True)
class Tax:
    """A tax amount applied to a scope for a period."""

    scope_id: str
    period_start: date
    amount: Decimal
    currency: str
