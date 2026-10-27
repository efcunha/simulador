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

**The rows are the scope's rows, not the estate's.** Every subscription of the estate
reuses every cluster name (``generate/estate_builder.py:292`` restarts the counter per
scope), so a cluster name is not unique across the estate and the subscription is what
disambiguates the caller's question. The subscription is named in two spellings — the GUID
the served ids carry and the estate's own scope label — and both are accepted, the same
alias rule ``projections/subscription.py`` and ``projections/sql.py`` follow. A request
that names no subscription at all answers every cluster, as the sibling projections do.
"""

from __future__ import annotations

from tools.synthetic_clouds.model.estate import CanonicalEstate

from azure_sim.projections import arm, scope

MANAGED_CLUSTER = "aks_cluster"


def project_managed_clusters(
    estate: CanonicalEstate,
    subscription_id: str | None = None,
    resource_group: str | None = None,
) -> list[dict[str, object]]:
    """Return ``managedClusters.list`` rows: this provider's clusters, ordered by name.

    ``subscription_id`` is the subscription the request scope names, when it names one,
    and ``resource_group`` the resource group it names, when it names one. Both are
    optional: a request that is not scoped to a subscription answers every cluster.

    The two are narrowed on separately because they are two different claims: the
    subscription says WHICH subscription the caller asks under, and the resource group
    says which group inside it. The estate models one group per subscription — the group
    is named after the scope (``projections/arm.py``) — so a request that names both
    consistently answers that subscription's clusters, and one that names them
    inconsistently answers none.
    """
    clusters = scope.of_type(estate, MANAGED_CLUSTER)
    if subscription_id is not None:
        # The alias is resolved once: the GUID the caller holds and the estate's own
        # scope label name the same subscription, and a subscription the estate does not
        # carry selects nothing.
        label = scope.subscription_label(estate, subscription_id)
        clusters = tuple(resource for resource in clusters if label is not None and resource.parent_scope_id == label)
    rows: list[dict[str, object]] = []
    for resource in clusters:
        if resource_group is not None and resource.parent_scope_id != resource_group:
            continue
        rows.append(
            arm.arm_row(
                estate,
                resource,
                arm_type=arm.MANAGED_CLUSTER_TYPE,
                properties={"provisioningState": arm.PROVISIONING_SUCCEEDED},
            )
        )
    return rows
