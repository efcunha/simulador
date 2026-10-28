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

**``properties.fqdn`` is the API server endpoint the cluster answers on.** The field is
official -- ``Microsoft.ContainerService/managedClusters.properties.fqdn``, published by
the Azure model reference as "The FQDN of the master pool" (the host the AKS control
plane answers on), consulted 2026-10-28:
https://learn.microsoft.com/en-us/python/api/azure-mgmt-containerservice/azure.mgmt.containerservice.models.managedclusterproperties?view=azure-python
It is what the FinOps Kubernetes discovery reads (``_list_aks_clusters`` reads it off the
ARM payload by NAME, because ``azure-mgmt-resource`` types ``GenericResource.properties``
as ``object`` and hands over a plain dict) and what ``get_cluster_health`` hands back as
the cluster's ``endpoint``. Without it the estate published an empty endpoint, and the
cost path that needs one had nothing to consume.

**The value is DERIVED, and it is not resolvable.** The estate models no DNS prefix and
no Kubernetes API server, so the FQDN is minted from the cluster's own identity rather
than read from somewhere -- ``sha256(identity.uuid + resource_name + region_id)``, with
the name normalized into a DNS label. It is a CONTRACT (a host, stable, unique per
cluster, identical on both routes), not a route: nothing listens on it and it does not
resolve. The shape is ``<cluster>-<hash>.<region>.azmk8s.io`` -- the suffix AKS
publishes under, with the region the cluster sits in.

Two properties of the derivation are load-bearing and are why the identity is in the
digest at all:

- **The hash is what makes the FQDN unique.** The estate reuses cluster names across
  subscriptions, so a name alone cannot key an endpoint: two subscriptions would publish
  the same host for two different clusters. The identity uuid does not repeat, so the
  hash does not either.
- **The hash is computed with ``hashlib``, never ``hash()``.** ``hash()`` is salted per
  process, so the same cluster would answer a different FQDN on every restart -- the
  opposite of a contract. This is the same rule ``model/identity.py`` follows (AC-6).

**Only ``fqdn`` is added.** The other properties stay exactly as they were:
``provisioningState`` and nothing else. In particular ``agentPoolProfiles``,
``dnsPrefix`` and ``privateFqdn`` stay ABSENT rather than empty -- an empty member
asserts a fact about the cluster (a cluster with no node pools, a cluster with no DNS
prefix), whereas an absent member is the estate's silence.
"""

from __future__ import annotations

import hashlib
import re

from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.resource import Resource

from azure_sim.projections import arm, scope

MANAGED_CLUSTER = "aks_cluster"

#: The suffix AKS publishes its API server FQDN under.
_FQDN_SUFFIX = "azmk8s.io"

#: The length of the hash segment of the FQDN. Ten hex characters is 40 bits, which
#: separates the estate's 123 clusters with a margin wide enough to be asserted rather
#: than assumed, and it leaves the 63-character budget of the first DNS label to the
#: cluster's own name.
_HASH_LENGTH = 10

#: The maximum length of a DNS label (RFC 1035).
_MAX_LABEL_LENGTH = 63

#: Every run of characters that a DNS label does not carry.
_NOT_DNS = re.compile(r"[^a-z0-9]+")


def _dns_label(value: str) -> str:
    """Normalize ``value`` into a DNS label.

    Lower-case, only ``[a-z0-9-]``, no leading or trailing hyphen, at most 63
    characters. The estate's names are GENERATOR names, not hostnames --
    ``aks_cluster-0043_FINAL_v2`` carries an underscore and upper-case characters --
    and a host cannot carry them, so the name is normalized rather than rejected.
    """
    label = _NOT_DNS.sub("-", value.strip().lower()).strip("-")
    # The truncation can cut a hyphen in half, so the label is stripped again after it.
    return label[:_MAX_LABEL_LENGTH].strip("-")


def cluster_fqdn(resource: Resource) -> str:
    """The API server FQDN of one managed cluster, in the shape AKS publishes.

    ``<cluster>-<hash>.<region>.azmk8s.io`` -- a HOST: no scheme, no port, no path.

    The hash is ``sha256`` over the cluster's identity uuid, its name and its region,
    so it is deterministic for a given estate (the same cluster answers the same FQDN
    on every call and on every rebuild) and unique across the estate (the uuid does
    not repeat, even where the name does). The name is normalized into a DNS label and
    the region is the one the cluster sits in.

    A region the estate does not carry yields a host WITHOUT the region segment rather
    than one with an invented region: the estate assigns every resource a region, so
    the segment is always there in practice, and the shape stays a valid DNS name
    either way.
    """
    digest = hashlib.sha256(
        f"{resource.identity.uuid}:{resource.resource_name}:{resource.region_id}".encode()
    ).hexdigest()[:_HASH_LENGTH]
    # The name yields to the hash when the two together would exceed a DNS label: the
    # hash is what keeps the FQDN unique, the name is what makes it readable.
    name = _dns_label(resource.resource_name) or "aks"
    name = name[: _MAX_LABEL_LENGTH - len(digest) - 1].strip("-") or "aks"
    region = _dns_label(resource.region_id)
    segments = [f"{name}-{digest}"]
    if region:
        segments.append(region)
    segments.append(_FQDN_SUFFIX)
    return ".".join(segments)


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

    Every row carries ``properties.fqdn``: the API server endpoint the cluster answers
    on, derived from the cluster's own identity (see :func:`cluster_fqdn`). Both routes
    that serve managed clusters -- the typed list and the ARM resources list -- go
    through this function, which is what makes the FQDN of a cluster the SAME on both.
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
                properties={
                    "provisioningState": arm.PROVISIONING_SUCCEEDED,
                    "fqdn": cluster_fqdn(resource),
                },
            )
        )
    return rows
