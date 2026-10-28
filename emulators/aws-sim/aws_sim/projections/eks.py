"""The EKS projection: clusters, node groups and add-ons.

Clusters are estate rows. **Node groups and add-ons are not**, and the two are treated
differently because that is what the two actually are:

* every EKS cluster runs the managed add-ons AWS installs with it (``vpc-cni``,
  ``kube-proxy``, ``coredns``), so reporting exactly those is a fact about EKS and not a
  claim about the estate — and the estate records nothing about add-ons that could
  contradict it.
* a node group is a customer's choice. The estate models none, so one is derived per
  cluster, named off the cluster's own id (``<id>-ng``), which keeps the answer
  traceable to the cluster it hangs from and stops the caller from reading an empty
  list as "this cluster runs no compute".

Deliberately omitted, each because the estate cannot back it:

* ``resourcesVpcConfig`` carries the access flags only — no ``subnetIds`` (the estate
  models no subnets) and no ``securityGroupIds`` (security groups are not attached to
  anything in the model, so naming some would invent an attachment).
* ``version`` is the Kubernetes version AWS ships by default rather than a hashed
  number: a version no cluster ever ran would be worse than a constant.
* ``createdAt`` is the resource's earliest billed day, and is omitted when the estate has
  never billed the cluster.

**The cluster is published under the estate's OWN name, and carries the ARN AWS
publishes for it.** ``name`` is ``Resource.resource_name``: the name the estate
publishes, the name the k8s-sim fixture carries and the name the CloudPilot sends back
as ``filter=cluster:"<name>"``. ``arn`` is
``arn:aws:eks:<region>:<account>:cluster/<name>`` — the shape AWS itself publishes, whose
resource part IS the cluster name.

**The name alone cannot identify a cluster, and the ARN is what does.** The estate
reuses a name across accounts (``generate/estate_builder.py:292`` restarts the
per-scope counter for every account): measured on the canonical estate of 2026-10-28,
the 75 EKS clusters carry 40 distinct names, the same names repeated across the three
accounts. The ARN carries the account and the region besides the name, and is
therefore the unique key — which is what the CloudPilot needs (C-IDENT).

**THE LIST KEEPS THE SIMULATOR'S HANDLE, and that is deliberate.**
``ListClusters`` answers with the derived id (``cluster-<17 hex>``), the way it
always has, and the handle is what the routes address. The alternative — answering
with the names — would make the list a lossy address space: the EKS surface serves
every account of the estate on one endpoint (the real service resolves a name inside
the account of the credentials), so a name the estate reuses would resolve to ONE of
the clusters carrying it and the other one's ARN would never be published. The
consumer's discovery walks the list and describes every entry, so with names in the
list it would receive 40 of the 75 clusters (measured above), and C-IDENT could not
recover the other 35 — their identifiers would never have been published. With the
handle in the list, every cluster is described and every cluster publishes its own
ARN. The NAME the AWS contract publishes is in the cluster document, where the
account is published beside it.

**The derived id is therefore never published as a name.** It is the simulator's
address, and it is accepted as an **alias** by :func:`find_cluster` beside the
estate's own name, so a caller that stored either resolves: an alias is accepted,
never published — the rule the k8s-sim's ``cluster_id`` alias and the Azure
subscription-label alias already follow.

**What does NOT follow the name.** The node group name and the IAM role name stay on the
derived id: neither an IAM role name nor a node group name can carry the estate's names
(``eks_cluster-0021 (do not delete)`` is neither), and normalizing one into something AWS
would accept would be inventing a name. Everything else derived from the cluster — the
endpoint, the OIDC issuer, the tags — hangs off the resource's own identity and is
untouched.
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
    """The handle of every cluster the estate carries, ordered.

    The values are the simulator's own address for a cluster, the way
    ``eks.ListClusters`` has always answered: the EKS surface serves every account
    of the estate on one endpoint, so a name the estate reuses across accounts
    cannot address one of them (see the module docstring). The NAME the AWS
    contract publishes is in the cluster document.
    """
    return tuple(ids.resource_id(r) for r in _cluster_resources(estate))


def find_cluster(estate: CanonicalEstate, name: str) -> Resource | None:
    """Resolve one cluster by the estate's name or by the simulator's handle.

    Both are accepted, and both are aliases: neither is published as the
    cluster's name — the document carries ``Resource.resource_name`` and the ARN.
    The handle resolves to exactly one cluster; a name the estate reuses across
    accounts resolves to the first cluster carrying it, because the surface is
    account-agnostic (the real service resolves a name inside the account of the
    credentials). The ARN is what identifies a cluster across accounts.
    """
    resources = _cluster_resources(estate)
    for resource in resources:
        if ids.resource_id(resource) == name:
            return resource
    for resource in resources:
        if resource.resource_name == name:
            return resource
    return None


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


def cluster_arn(cluster: Resource) -> str:
    """The ARN AWS publishes for one cluster: ``arn:aws:eks:<region>:<account>:cluster/<name>``.

    The shape — the service and the ``cluster/`` segment — comes from the package's
    own ARN table (:func:`arns.arn_for_type`), so it is written in one place; what
    fills the resource-name slot is the cluster's OWN NAME, because that is what AWS
    puts there. The account and the region are the cluster's own, so the ARN names
    one cluster even where two accounts reuse a name.
    """
    arn = arns.arn_for_type(
        RESOURCE_TYPE,
        cluster.resource_name,
        cluster.region_id,
        cluster.parent_scope_id,
    )
    if arn is None:  # the ARN table holds the EKS shape, so this branch is unreachable
        raise ValueError(f"the ARN table has no shape for {RESOURCE_TYPE!r}")
    return arn


def _epoch(value: datetime) -> float:
    """JSON/rest-JSON timestamps are numbers; the Query protocol's are ISO strings."""
    return value.astimezone(UTC).timestamp()


def cluster_document(estate: CanonicalEstate, cluster: Resource) -> dict[str, Any]:
    """The ``DescribeCluster`` cluster document for one estate cluster."""
    uuid = cluster.identity.uuid
    name = cluster.resource_name
    document: dict[str, Any] = {
        "name": name,
        "arn": cluster_arn(cluster),
        "version": KUBERNETES_VERSION,
        "endpoint": f"https://{arns.stable_digest(uuid)}.gr7.{cluster.region_id}.eks.amazonaws.com",
        # The role is an IAM name: it stays on the derived id, because the estate's
        # own names are not names IAM accepts.
        "roleArn": f"arn:aws:iam::{cluster.parent_scope_id}:role/{ids.resource_id(cluster)}-cluster-role",
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
