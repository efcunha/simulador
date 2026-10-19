"""The ``Resource`` entity — the identity carrier (design sec. 4.3).

Every resource belongs to a valid Azure subscription or GCP project via
``parent_scope_id`` (a hard FK enforced by the gate, FR-E3/AC-8). ``tags`` is an
immutable tuple of ``(key, value)`` pairs mapping directly to FOCUS 1.2's
list-of-tuples ``Tags`` shape; it may be empty for the ~15% untagged subset
(FR-D2). Names may be off-standard (FR-D3).

``capacity_reservation`` is the compute resource's capacity reservation, or ``None``
when it carries none. It hangs off the resource because a reservation targets ONE
resource and the renderer projects the FOCUS ``CapacityReservation*`` pair from the
resource a line names (see ``model/capacity.py`` for why it is not a ``Commitment``).
"""

from __future__ import annotations

from dataclasses import dataclass

from tools.synthetic_clouds.model.capacity import CapacityReservation
from tools.synthetic_clouds.model.identity import ResourceIdentity


@dataclass(slots=True, frozen=True)
class Resource:
    """A cloud resource carrying the stable identity threaded end-to-end (P2)."""

    identity: ResourceIdentity
    parent_scope_id: str  # Azure subscription_id OR GCP project_id (FK, FR-E3)
    service_name: str  # FOCUS ServiceName / BQ service.description
    service_category: str  # FOCUS ServiceCategory
    resource_type: str  # e.g. "virtual_machine", "bucket", "aks_cluster"
    resource_name: str  # may be off-standard (FR-D3)
    region_id: str
    region_name: str
    tags: tuple[tuple[str, str], ...]  # list-of-(key,value); may be empty (FR-D2)
    sku_id: str
    capacity_reservation: CapacityReservation | None  # None = the resource carries none
