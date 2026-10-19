"""Capacity reservations (FOCUS 1.2 ``CapacityReservationId`` / ``Status``).

A capacity reservation reserves *capacity* on a compute resource; it does not discount
spend. That is why it is NOT modelled as a ``Commitment`` (``model/commitments.py``),
which is the closest thing the estate already carried:

* ``Commitment`` carries the commitment-DISCOUNT facts the seven
  ``CommitmentDiscount*`` FOCUS columns project — ``kind`` (mapped to
  ``CommitmentDiscountType``/``Category`` by the renderers), ``committed_amount``,
  ``quantity`` and ``unit``. Folding a capacity reservation into it would report one
  construct twice, as discount AND as reserved capacity, in two column groups FOCUS 1.2
  keeps apart.
* the ``reservation`` kind is already taken: ``constants.COMMITMENT_LABEL`` names it
  ``Reserved Instance`` (the AWS billing construct, emitted by scenario A01), which is
  a different AWS thing from an EC2 *capacity* reservation.
* ``Commitment`` hangs off a scope (``scope_id``), while a capacity reservation targets
  ONE resource. Several reservations across accounts are the normal case, not one per
  account.

The reservation therefore lives ON the resource it reserves (``Resource.
capacity_reservation``), which is also the grain the renderer projects from: the FOCUS
pair is per line, and the line names its resource.

``TODO-verificar``: FOCUS 1.2's exact definition wording for ``CapacityReservationStatus``
(which charge each literal describes) is not verifiable offline. What is modelled here
follows the package's own literal domain — see ``constants.CAPACITY_RESERVATION_STATUSES``
— rather than a recollected definition.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(slots=True, frozen=True)
class CapacityReservation:
    """An EC2-style capacity reservation on ONE compute resource.

    ``reservation_id`` is the value the FOCUS ``CapacityReservationId`` column carries:
    derived deterministically for ``(seed, resource)`` by
    ``identity.capacity_reservation_id``, in the documented ``cr-`` + 17 lowercase hex
    shape. ``status`` is the FOCUS ``CapacityReservationStatus`` literal
    (``constants.CAPACITY_RESERVATION_STATUSES``) and is a modelled fact — the estate
    carries both reservations their instance consumes and reservations standing idle,
    drawn from a named stream for the resource (see
    ``EstateBuilder._capacity_reservation``) — not a literal chosen at render time.
    """

    reservation_id: str  # FOCUS CapacityReservationId
    resource_uuid: str  # the compute resource whose capacity it reserves
    scope_id: str  # the account it belongs to (== the resource's parent_scope_id here)
    period_start: date  # first day the reservation is in force
    period_end: date  # last day it is in force
    status: str  # FOCUS CapacityReservationStatus: "Used" | "Unused"
