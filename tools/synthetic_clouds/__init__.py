"""FinOps synthetic multi-cloud canonical generator (Phase 1).

Builds a deterministic, correlated multi-cloud estate (canonical frozen-dataclass
model), validates it with a referential-integrity/quality gate, serializes it, and
renders it into the cloud-native wire shapes FinOps ingestion already consumes
(Azure FOCUS 1.2 Data Export; GCP nested BigQuery billing export). Emits an 18-row
scenario gabarito at ``docs/synthetic-clouds/scenarios.json``.

Determinism is absolute: all identity derives from UUIDv5/hashlib seeded by
``--seed``. Python's built-in ``hash()`` is never used. The package touches no
production code, no DB, no migration tooling, no containers (Phase 1 boundary).
"""

from __future__ import annotations

__all__ = ["__version__"]
__version__ = "0.1.0"
