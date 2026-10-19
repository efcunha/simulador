"""IaC state snapshots and inventory assets (design sec. 4.7).

``IacResourceState`` and ``InventoryAsset`` bind to an existing resource identity.
A resource that is in inventory but ABSENT from the IaC snapshot is the drift
INPUT for C11 (the generator emits the input only; drift itself is computed by
FinOps, P1).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(slots=True, frozen=True)
class InventoryAsset:
    """A provider-native inventory asset (1:1 with a Resource)."""

    resource_uuid: str  # FK -> ResourceIdentity.uuid
    asset_type: str  # provider-native asset type string
    config_json: dict[str, Any]  # metadata.synthetic = true (NFR-3)
    managed_by_iac: bool  # feeds drift input (C11)


@dataclass(slots=True, frozen=True)
class IacResourceState:
    """A declared IaC state for a resource (its absence is a drift input)."""

    resource_uuid: str  # FK -> ResourceIdentity.uuid
    declared_config: dict[str, Any]


@dataclass(slots=True, frozen=True)
class IacStateSnapshot:
    """An IaC state snapshot for a scope at a point in time."""

    snapshot_id: str
    scope_id: str  # subscription_id / project_id
    captured_at: datetime
    resource_states: tuple[IacResourceState, ...]
    metadata: dict[str, Any]  # metadata.synthetic = true (NFR-3)
