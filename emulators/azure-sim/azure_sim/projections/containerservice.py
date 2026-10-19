"""Azure Kubernetes Service resource plane: ``managedClusters`` (Phase 6).

``managed_clusters.list`` is consumed — ``service_discovery.py (modulo do consumidor):393`` reads ``cluster.name`` and ``cluster.location`` — and that pair
is the whole row this estate can back honestly. It models an ``aks_cluster`` as identity,
region, tags and a node SKU (``azure-aks-node-d4s``); it has no Kubernetes version, no node
pool, no DNS prefix, no identity block and no service principal, so none of those appear.
In particular ``properties.agentPoolProfiles`` is omitted rather than emitted empty: an
empty pool list asserts a cluster with no node pools, which is a claim about the cluster,
whereas an absent member is the estate's silence. The node SKU is NOT promoted to a size
either — Azure's agent-pool VM size vocabulary (``Standard_D4s_v5``) is a different axis
from a node-pool name, and nothing reads it.
"""

from __future__ import annotations

from tools.synthetic_clouds.model.estate import CanonicalEstate

from azure_sim.projections import arm, scope

MANAGED_CLUSTER = "aks_cluster"


def project_managed_clusters(estate: CanonicalEstate) -> list[dict[str, object]]:
    """Return ``managedClusters.list`` rows: this provider's clusters, ordered by name."""
    return [
        arm.arm_row(
            estate,
            resource,
            arm_type=arm.MANAGED_CLUSTER_TYPE,
            properties={"provisioningState": arm.PROVISIONING_SUCCEEDED},
        )
        for resource in scope.of_type(estate, MANAGED_CLUSTER)
    ]

