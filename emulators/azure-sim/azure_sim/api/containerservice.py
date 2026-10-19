"""Container Service resource plane: ``managedClusters`` (Phase 6).

The read ``service_discovery.py (modulo do consumidor):393`` makes through
``ContainerServiceClient.managed_clusters.list()``.

**The api-version strings below could NOT be verified in this environment**: that package
is not installed here (``azure-mgmt-containerservice`` is imported lazily inside the
discovery function's ``try`` and is not a declared dependency of the backend), so unlike
the Compute/Network/SQL/Storage gates in this package they are not read off a client. They
are emitted as a small tolerance set of the stable versions the service has shipped, which
is what the ``TODO-verificar`` flag records; the catalogue row this belongs to is
``docs/synthetic-clouds/UNVERIFIED.md`` (Phase 6 — Azure resource plane), which lives
outside the package this change was scoped to. A wrong string here is not silent: the gate
answers the Azure 400 envelope and the caller's own per-provider ``except`` logs the
failure, so the tolerance set exists precisely so that an unverified guess cannot disable
AKS discovery on its own.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from azure_sim.api.common import get_estate, require_api_version, value_page
from azure_sim.projections.containerservice import project_managed_clusters

router = APIRouter()

# TODO-verificar: NOT read off an installed client (azure-mgmt-containerservice is absent);
# stable versions of the managedClusters list, pending confirmation.
_MANAGED_CLUSTER_VERSIONS: frozenset[str] = frozenset({"2024-09-01", "2025-01-01"})


@router.get("/{scope:path}/providers/Microsoft.ContainerService/managedClusters")
async def managed_clusters(request: Request, scope: str = "") -> dict[str, Any]:
    """Return ``managed_clusters.list`` rows for the scope (``{value:[...]}``)."""
    require_api_version(request, _MANAGED_CLUSTER_VERSIONS)
    return value_page(request, project_managed_clusters(get_estate(request)))
