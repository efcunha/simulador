"""azure-sim: FinOps Azure synthetic-cloud simulator (Phase 2).

A pure consumer of the Phase 1 generator ``tools.synthetic_clouds``: it builds a
frozen, gated ``CanonicalEstate`` and projects it into Azure Cost Management
exports (Azurite blobs) and real-shaped control-plane HTTP APIs. It never
reinvents estate construction and never emits a FinOps-computed output.
"""

from __future__ import annotations

__version__ = "0.1.0"
