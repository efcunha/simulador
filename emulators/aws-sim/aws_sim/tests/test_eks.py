"""EKS REST-JSON tests, parsed with botocore's own parser.

The paths are the ones the SDK composes from the model (``/clusters``,
``/clusters/{name}``, …), so a route that only worked for a hand-written URL would fail
here.

**The cluster document carries the estate's own name and the ARN AWS publishes for
it.** ``name`` is ``Resource.resource_name`` — the name the estate publishes, the name
the k8s-sim fixture carries and the name the CloudPilot sends back as
``filter=cluster:"<name>"`` — and ``arn`` is
``arn:aws:eks:<region>:<account>:cluster/<name>``, the shape AWS itself publishes (the
ARN's resource part IS the cluster name). The derived AWS id (``aws_sim.ids``:
``cluster-<17 hex>``) is **not published as a name**: it was the simulator's stand-in
for a name the estate reuses across accounts, and the ARN now carries the account, so
the identifier is unique without it.

**The list answers with the simulator's handle.** The EKS surface serves every
account of the estate on one endpoint, where the real service resolves a name inside
the account of the credentials; a name the estate reuses would therefore address only
one of the clusters carrying it, and the others' ARNs would never be published. The
consumer's discovery walks the list and describes every entry, so the list keeps the
one address that reaches every cluster. Both the handle and the estate's name are
**accepted** by the routes (an alias is accepted, never published — the rule the
k8s-sim's ``cluster_id`` alias follows), so a caller that stored either resolves.

**What does NOT follow the name.** The node group name and the IAM role name stay on
the derived id, because neither an estate name nor anything derived from it is a name
AWS accepts: ``eks_cluster-0021 (do not delete)`` is not an IAM role name and not a
node group name. Deriving a "clean" name from it would be inventing one.
"""

from __future__ import annotations

from collections import Counter

import botocore.session
from botocore.parsers import create_parser

from aws_sim import ids, scope
from aws_sim.projections import eks as projection

_MODEL = botocore.session.get_session().get_service_model("eks")
_PARSER = create_parser("rest-json")


def _parse(client, operation: str, path: str):
    response = client.get(path)
    raw = {"status_code": response.status_code, "headers": dict(response.headers), "body": response.content}
    shape = _MODEL.operation_model(operation).output_shape
    if response.status_code != 200:
        return _PARSER._do_error_parse(raw, shape)
    return _PARSER.parse(raw, shape)


def _clusters(app):
    return sorted(
        (r for r in scope.resources(app.state.estate) if r.resource_type == "eks_cluster"),
        key=ids.resource_id,
    )


def _cluster(app):
    return _clusters(app)[0]


def test_list_clusters_publishes_the_addressable_handle(api_client) -> None:
    """The list answers with the one address that reaches every cluster."""
    client, app = api_client
    expected = {ids.resource_id(r) for r in _clusters(app)}
    served = _parse(client, "ListClusters", "/clusters")["clusters"]

    assert set(served) == expected
    assert expected, "the estate has EKS clusters"
    assert len(served) == len(expected), "the list answers one entry per cluster"
    # The handle is an address, never a name: no cluster publishes it as one.
    assert not set(served) & {r.resource_name for r in _clusters(app)}


def test_describe_cluster_reports_the_estate_cluster(api_client) -> None:
    """The document carries the estate's name and the ARN AWS publishes."""
    client, app = api_client
    resource = _cluster(app)
    name = resource.resource_name
    cluster = _parse(client, "DescribeCluster", f"/clusters/{ids.resource_id(resource)}")["cluster"]

    assert cluster["name"] == name
    assert cluster["name"] != ids.resource_id(resource), "the derived id is not a name"
    assert cluster["arn"] == (
        f"arn:aws:eks:{resource.region_id}:{resource.parent_scope_id}:cluster/{name}"
    )
    assert cluster["status"] == "ACTIVE"
    assert cluster["version"]
    assert cluster["createdAt"] is not None
    assert cluster["endpoint"].startswith("https://")
    assert cluster["identity"]["oidc"]["issuer"].startswith("https://oidc.eks.")
    assert cluster["resourcesVpcConfig"]["endpointPublicAccess"] is True
    assert cluster["tags"] == {key: value for key, value in resource.tags}


def test_the_arn_identifies_exactly_one_cluster(api_client) -> None:
    """Every cluster of the estate has its own ARN, and the same one on every call.

    The estate reuses a name across accounts, so the name alone cannot identify a
    cluster; the ARN carries the account and the region, which is what makes it the
    key the CloudPilot needs (C-IDENT).
    """
    client, app = api_client
    arns_by_cluster = {ids.resource_id(r): projection.cluster_arn(r) for r in _clusters(app)}

    assert len(set(arns_by_cluster.values())) == len(arns_by_cluster), "two clusters share one ARN"
    for resource in _clusters(app):
        assert arns_by_cluster[ids.resource_id(resource)] == (
            f"arn:aws:eks:{resource.region_id}:{resource.parent_scope_id}:cluster/{resource.resource_name}"
        )

    # Every cluster is reachable through the list, and each one publishes its own ARN.
    published = {
        _parse(client, "DescribeCluster", f"/clusters/{ids.resource_id(r)}")["cluster"]["arn"]
        for r in _clusters(app)
    }
    assert published == set(arns_by_cluster.values()), "a cluster did not publish its own ARN"


def test_the_arn_is_stable_between_calls(api_client) -> None:
    """The same cluster answers the same ARN on every call."""
    client, app = api_client
    for resource in _clusters(app):
        handle = ids.resource_id(resource)
        first = _parse(client, "DescribeCluster", f"/clusters/{handle}")["cluster"]["arn"]
        second = _parse(client, "DescribeCluster", f"/clusters/{handle}")["cluster"]["arn"]
        assert first == second, "an ARN that moved between calls breaks the correlation"


def test_the_estate_name_resolves_as_an_alias(api_client) -> None:
    """The published name resolves too: an alias is accepted, never published."""
    client, app = api_client
    resource = _cluster(app)
    by_name = _parse(client, "DescribeCluster", f"/clusters/{resource.resource_name}")["cluster"]
    by_handle = _parse(client, "DescribeCluster", f"/clusters/{ids.resource_id(resource)}")["cluster"]

    assert by_name["name"] == resource.resource_name
    assert by_name["arn"].endswith(f":cluster/{resource.resource_name}")
    assert ids.resource_id(resource) not in by_name["arn"]


def test_a_name_the_estate_reuses_across_accounts_names_one_cluster(api_client) -> None:
    """A name shared by two accounts resolves to ONE cluster, and to the same one.

    **This is a declared gap, not a contract.** The EKS surface is account-agnostic:
    it serves every account of the estate on one endpoint, where the real service
    resolves a name inside the account of the credentials. A name the estate reuses
    across accounts therefore names one cluster here, and the other cluster's ARN is
    not published under that name.

    The ARN of every cluster is still unique (the test above), so the gap is in the
    ADDRESSING, not in the identifier: closing it means making the surface
    account-scoped, which this phase does not touch.
    """
    client, app = api_client
    shared = [
        name
        for name, count in Counter(r.resource_name for r in _clusters(app)).items()
        if count > 1
    ]
    assert shared, "the estate reuses a cluster name across accounts"

    for name in shared:
        first = _parse(client, "DescribeCluster", f"/clusters/{name}")["cluster"]
        second = _parse(client, "DescribeCluster", f"/clusters/{name}")["cluster"]
        assert first == second, "the same name answered two different clusters"
        assert first["name"] == name


def test_node_groups_and_addons(api_client) -> None:
    """The node group and the add-ons keep their own contract.

    The node group's NAME stays on the derived id: an estate name is not a node
    group name AWS would accept (``eks_cluster-0021 (do not delete)``), and
    renaming it would mean inventing one.
    """
    client, app = api_client
    resource = _cluster(app)
    handle = ids.resource_id(resource)
    node_groups = _parse(client, "ListNodegroups", f"/clusters/{handle}/node-groups")["nodegroups"]
    addons = _parse(client, "ListAddons", f"/clusters/{handle}/addons")["addons"]

    assert len(node_groups) == 1
    assert node_groups[0] == f"{handle}-ng"
    assert set(addons) == set(projection.DEFAULT_ADDONS)


def test_the_role_keeps_the_derived_id(api_client) -> None:
    """The service role is an IAM name: it cannot carry the estate's name."""
    client, app = api_client
    resource = _cluster(app)
    cluster = _parse(client, "DescribeCluster", f"/clusters/{ids.resource_id(resource)}")["cluster"]

    assert cluster["roleArn"] == (
        f"arn:aws:iam::{resource.parent_scope_id}:role/{ids.resource_id(resource)}-cluster-role"
    )


def test_an_unknown_cluster_is_not_found(api_client) -> None:
    client, _ = api_client
    error = _parse(client, "DescribeCluster", "/clusters/nope")
    assert error["Error"]["Code"] == "ResourceNotFoundException"
