"""Metric series bound to resource identities (design sec. 4.7)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True, frozen=True)
class MetricPoint:
    """A single metric sample."""

    ts: datetime
    value: float


@dataclass(slots=True, frozen=True)
class MetricSeries:
    """A metric series bound to a resource identity (FK -> ResourceIdentity.uuid)."""

    resource_uuid: str
    metric_name: str  # e.g. "cpu_utilization"
    points: tuple[MetricPoint, ...]
