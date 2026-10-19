"""gcp-sim: synthetic GCP control-plane REST service (Phase 3).

Serves Cloud Asset Inventory, Security Command Center, Recommender, Cloud Billing
Catalog, Cloud Monitoring, Billing Budgets, and an OAuth2 token stub in the
official REST wire shape, from a rendered snapshot of the canonical estate
(``gcp_rest_fixtures``). Native inputs only (P1); no FinOps-computed output.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"
