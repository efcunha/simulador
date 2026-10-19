"""The EKS projection: clusters, node groups and add-ons.

Clusters are estate rows. **Node groups and add-ons are not**, and the two are treated
differently because that is what the two actually are:

* every EKS cluster runs the managed add-ons AWS installs with it (``vpc-cni``,
  ``kube-proxy``, ``coredns``), so reporting exactly those is a fact about EKS and not a
  claim about the estate — and the estate records nothing about add-ons that could
  contradict it.
* a node group is a customer's choice. The estate models none, so one is derived per
  cluster, named off the cluster (``<cluster>-ng``), which keeps the answer traceable to
  the cluster it hangs from and stops the caller from reading an empty list as "this
  cluster runs no compute".

Deliberately omitted, each because the estate cannot back it:

* ``resourcesVpcConfig`` carries the access flags only — no ``subnetIds`` (the estate
  models no subnets) and no ``securityGroupIds`` (security groups are not attached to
  anything in the model, so naming some would invent an attachment).
* ``version`` is the Kubernetes version AWS ships by default rather than a hashed
  number: a version no cluster ever ran would be worse than a constant.
* ``createdAt`` is the resource's earliest billed day, and is omitted when the estate has
  never billed the cluster.

A cluster's **name** is the resource's derived AWS id (``aws_sim.ids``), not its
``resource_name``: the estate reuses a name across accounts and an EKS cluster name is
scope-free, so a name read from the estate would answer the same value for every cluster
sharing it — one identity for several clusters, which is the correlation failure
:mod:`aws_sim.ids` exists to remove. Everything derived from the cluster hangs off that same
id (the node group ``<id>-ng``, the cluster role), and the ARN is built from it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.resource import Resource

from aws_sim import arns, ids, scope

RESOURCE_TYPE = "eks_cluster"

STATUS_ACTIVE = "ACTIVE"
KUBERNETES_VERSION = "1.30"

#: The managed add-ons AWS installs on every cluster.
DEFAULT_ADDONS: tuple[str, ...] = ("vpc-cni", "kube-proxy", "coredns")

#: The node group every cluster is assumed to run. See the module docstring.
NODE_GROUP_SUFFIX = "ng"

#: Access mode AWS uses for a cluster created by the console or the SDK default path.
AUTHENTICATION_MODE = "API_AND_CONFIG_MAP"


def _cluster_resources(estate: CanonicalEstate) -> tuple[Resource, ...]:
    return tuple(
        sorted(
            (r for r in scope.resources(estate) if r.resource_type == RESOURCE_TYPE),
            key=lambda r: r.resource_name,
        ),
    )


def clusters(estate: CanonicalEstate) -> tuple[str, ...]:
    """Every cluster name the estate carries, ordered."""
    return tuple(ids.resource_id(r) for r in _cluster_resources(estate))


def find_cluster(estate: CanonicalEstate, name: str) -> Resource | None:
    """Resolve one cluster by name, or ``None``."""
    return next((r for r in _cluster_resources(estate) if ids.resource_id(r) == name), None)


def node_groups(estate: CanonicalEstate, name: str) -> tuple[str, ...]:
    """The node group names for one cluster (empty for an unknown cluster)."""
    cluster = find_cluster(estate, name)
    if cluster is None:
        return ()
    return (f"{ids.resource_id(cluster)}-{NODE_GROUP_SUFFIX}",)


def addons(estate: CanonicalEstate, name: str) -> tuple[str, ...]:
    """The add-on names for one cluster (empty for an unknown cluster)."""
    if find_cluster(estate, name) is None:
        return ()
    return DEFAULT_ADDONS


def _epoch(value: datetime) -> float:
    """JSON/rest-JSON timestamps are numbers; the Query protocol's are ISO strings."""
    return value.astimezone(UTC).timestamp()


def cluster_document(estate: CanonicalEstate, cluster: Resource) -> dict[str, Any]:
    """The ``DescribeCluster`` cluster document for one estate cluster."""
    uuid = cluster.identity.uuid
    name = ids.resource_id(cluster)
    document: dict[str, Any] = {
        "name": name,
        "arn": arns.resource_arn(cluster),
        "version": KUBERNETES_VERSION,
        "endpoint": f"https://{arns.stable_digest(uuid)}.gr7.{cluster.region_id}.eks.amazonaws.com",
        "roleArn": f"arn:aws:iam::{cluster.parent_scope_id}:role/{name}-cluster-role",
        "resourcesVpcConfig": {
            "endpointPublicAccess": True,
            "endpointPrivateAccess": False,
            "publicAccessCidrs": ["0.0.0.0/0"],
        },
        "identity": {
            "oidc": {
                "issuer": (
                    f"https://oidc.eks.{cluster.region_id}.amazonaws.com/id/"
                    f"{arns.stable_digest(uuid, 32).upper()}"
                ),
            },
        },
        "accessConfig": {
            "authenticationMode": AUTHENTICATION_MODE,
            "bootstrapClusterCreatorAdminPermissions": True,
        },
        "status": STATUS_ACTIVE,
        "tags": {key: value for key, value in cluster.tags},
    }
    created = scope.first_charge(estate).get(uuid)
    if created is not None:
        document["createdAt"] = _epoch(created)
    return document
