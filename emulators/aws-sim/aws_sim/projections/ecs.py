"""The ECS projection: cluster and service ARNs.

Clusters exist in the estate (``resource_type == "ecs_cluster"``); **services do not**.
Rather than leave ``ListServices`` empty — which would read as "this account runs no
services" and quietly retire a whole inventory surface — the services are derived from
the clusters they belong to: two per cluster, named ``<cluster>-api`` and
``<cluster>-worker``. Deriving them from the cluster's own name is what keeps the answer
traceable: every service ARN names a real estate cluster, so a caller can walk back from
the service to the estate row behind it.

An ARN is the only identifier ECS returns here, which is why this projection emits ARNs
and not names: ``list_services`` answers with nothing else, and a caller wanting detail
has to call ``DescribeServices`` with the ARN it just received.
"""

from __future__ import annotations

from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.resource import Resource

from aws_sim import arns, ids, scope

RESOURCE_TYPE = "ecs_cluster"

#: The workloads every cluster in this estate is assumed to run. See the docstring:
#: the pair is what makes the derivation traceable, not a claim about a real workload.
SERVICE_SUFFIXES: tuple[str, ...] = ("api", "worker")


def clusters(estate: CanonicalEstate) -> tuple[str, ...]:
    """Every cluster ARN the estate carries, ordered."""
    return tuple(
        sorted(
            arn
            for arn in (arns.resource_arn(r) for r in scope.resources(estate) if r.resource_type == RESOURCE_TYPE)
            if arn is not None
        ),
    )


def service_arn(cluster: Resource, suffix: str) -> str:
    """The ARN of one derived service on ``cluster``.

    The service name is built from the cluster's own AWS id (``aws_sim.ids``) rather than
    from ``resource_name``, so the service ARN names exactly one cluster: the estate reuses
    a name across accounts, and two clusters sharing one would otherwise hand out the same
    pair of service ARNs.
    """
    name = ids.resource_id(cluster)
    return arns.arn(
        "ecs",
        cluster.region_id,
        cluster.parent_scope_id,
        f"service/{name}/{name}-{suffix}",
    )


def services(estate: CanonicalEstate, cluster_arn: str | None = None) -> tuple[str, ...]:
    """Every derived service ARN, or the ones on one cluster when ``cluster_arn`` is named.

    An unknown cluster ARN yields nothing rather than an error: ECS's
    ``ClusterNotFoundException`` is about a cluster the caller named that this account
    does not have, and the estate only has the ones it has.
    """
    rows: list[str] = []
    for resource in sorted(
        (r for r in scope.resources(estate) if r.resource_type == RESOURCE_TYPE),
        key=lambda r: r.resource_name,
    ):
        if cluster_arn and arns.resource_arn(resource) != cluster_arn:
            continue
        rows.extend(service_arn(resource, suffix) for suffix in SERVICE_SUFFIXES)
    return tuple(rows)
