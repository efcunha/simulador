"""Invoices (design sec. 4.6).

``invoice_issue_status`` reuses ``Issued``/``Estimated`` from the AWS CUR mapper;
the FOCUS 1.4 canonical set stays ``TODO-verificar`` (OA-6).

The C14 Estimated->Issued transition is append-only: two snapshots at different
``export_time`` values (an Estimated invoice, then an Issued invoice for the same
period emitted later), never a mutation of an existing invoice (design sec. 4.6).

``total == sum(line amounts)`` for every invoice EXCEPT a declared C07 invoice,
which diverges by the pinned multiplicative factor (design sec. 9).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(slots=True, frozen=True)
class InvoiceLine:
    """One invoice line referencing a billing line."""

    invoice_id: str
    billing_line_id: str  # FK -> BillingLine.line_id
    amount: Decimal


@dataclass(slots=True, frozen=True)
class Invoice:
    """A provider invoice for one billing period."""

    invoice_id: str
    billing_account_id: str
    billing_period_start: date
    billing_period_end: date
    invoice_issue_status: str  # "Issued" | "Estimated" (reuse AWS mapper values; OA-6)
    total: Decimal  # == sum(line amounts), EXCEPT C07
    currency: str
    lines: tuple[InvoiceLine, ...]
    is_c07_divergence: bool = False  # declared C07 invoice: total diverges by design
