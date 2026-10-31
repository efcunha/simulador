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
``cluster-<17 hex>``) is **not published as a name**: it is the simulator's own address
for a cluster, not a name AWS publishes.

**The list publishes the SAME name the document publishes, and it is scoped by the
account of the credentials.** The real EKS resolves a name inside the account that
signed the request; the emulator does the same, decoding the account from the SigV4
credential the way ``sts.GetCallerIdentity`` and the IAM credential report already do
(``projections/sts.py``). So ``ListClusters`` answers with the names of the calling
account's clusters, and every name it publishes is a name ``DescribeCluster`` answers
with — the list and the document say the same thing, and a name the estate reuses across
accounts names one cluster per account.

**What does NOT follow the name.** The node group name and the IAM role name stay on the
derived id, because neither an estate name nor anything derived from it is a name AWS
accepts: ``eks_cluster-0021 (do not delete)`` is not an IAM role name and not a node
group name. Deriving a "clean" name from it would be inventing one.
"""

from __future__ import annotations

from collections import Counter

import botocore.session
import pytest
from botocore.parsers import create_parser

from aws_sim import ids, scope
from aws_sim.projections import eks as projection
from aws_sim.projections import sts

_MODEL = botocore.session.get_session().get_service_model("eks")
_PARSER = create_parser("rest-json")


def _parse(client, operation: str, path: str, headers: dict[str, str] | None = None):
    response = client.get(path, headers=headers or {})
    raw = {"status_code": response.status_code, "headers": dict(response.headers), "body": response.content}
    shape = _MODEL.operation_model(operation).output_shape
    if response.status_code != 200:
        return _PARSER._do_error_parse(raw, shape)
    return _PARSER.parse(raw, shape)


def _auth(account: str) -> dict[str, str]:
    """The SigV4 credential the emulator decodes the account from."""
    return {
        "Authorization": (
            "AWS4-HMAC-SHA256 "
            f"Credential={sts.access_key_for_account(account)}/20260101/us-east-1/eks/aws4_request, "
            "SignedHeaders=host;x-amz-date, Signature=deadbeef"
        )
    }


def _clusters(app, account: str | None = None):
    resources = [
        r for r in scope.resources(app.state.estate) if r.resource_type == "eks_cluster"
    ]
    if account is not None:
        resources = [r for r in resources if r.parent_scope_id == account]
    return sorted(resources, key=ids.resource_id)


def _cluster(app):
    return _clusters(app)[0]


def _accounts(app) -> tuple[str, ...]:
    return tuple(sorted(scope.scope_ids(app.state.estate)))


@pytest.fixture(scope="module")
def canonical_client():
    """A client bound to the CANONICAL estate (seed 123, ``medium``): 75 EKS clusters.

    The shared ``api_client`` fixture carries the ``small`` profile (15 clusters), which
    is the same shape but too small to prove the "every cluster, once, across the three
    accounts" property this phase is about. The canonical estate is the one the impact
    map measures (75 clusters, 3 accounts), so the contract test measures it too.
    """
    from fastapi.testclient import TestClient

    from aws_sim.api.app import create_app
    from aws_sim.config import load_settings

    app = create_app(load_settings(env={}, SEED="123", PROFILE="medium", CURRENCY="USD"))
    with TestClient(app) as client:
        yield client, app


def test_the_list_publishes_the_names_the_document_publishes(canonical_client) -> None:
    """Every name ``ListClusters`` publishes is a name ``DescribeCluster`` answers with.

    The list and the document say the same thing: the same ``name`` and the ARN that
    carries it. A list that answered with anything else (the simulator's own address,
    for instance) would make the caller describe a name the document does not publish.
    """
    client, app = canonical_client

    for account in _accounts(app):
        listed = _parse(client, "ListClusters", "/clusters", _auth(account))["clusters"]
        assert listed, f"account {account} owns clusters"

        for name in listed:
            document = _parse(client, "DescribeCluster", f"/clusters/{name}", _auth(account))["cluster"]
            assert document["name"] == name, "the document answers a different name than the list published"
            assert document["arn"].endswith(f":cluster/{name}"), "the ARN does not carry the published name"
            assert f":{account}:" in document["arn"], "the ARN does not carry the account of the caller"


def test_the_list_publishes_no_simulator_handle(canonical_client) -> None:
    """No cluster is published under the simulator's own address."""
    client, app = canonical_client

    for account in _accounts(app):
        listed = _parse(client, "ListClusters", "/clusters", _auth(account))["clusters"]
        handles = {ids.resource_id(r) for r in _clusters(app, account)}
        assert not set(listed) & handles, "the list published a derived id as a name"


def test_each_account_sees_only_its_own_clusters(canonical_client) -> None:
    """The list is scoped: an account never reaches a cluster of another account.

    The estate reuses a NAME across accounts, so the names alone cannot tell a leak
    from a shared name — what tells them apart is WHICH cluster a name resolves to.
    Every name the account's list publishes must resolve, inside that account, to a
    cluster that account owns.
    """
    client, app = canonical_client

    for account in _accounts(app):
        listed = _parse(client, "ListClusters", "/clusters", _auth(account))["clusters"]
        headers = _auth(account)
        for name in listed:
            document = _parse(client, "DescribeCluster", f"/clusters/{name}", headers)["cluster"]
            owned = [
                r
                for r in _clusters(app)
                if r.parent_scope_id == account and r.resource_name == name
            ]
            assert owned, f"the list published {name!r}, which the account does not own"
            assert document["arn"] == projection.cluster_arn(owned[0]), (
                "the name resolved to a cluster of another account"
            )


def test_every_cluster_is_listed_once_across_the_accounts(canonical_client) -> None:
    """The canonical estate's 75 clusters are listed once each, spread over 3 accounts."""
    client, app = canonical_client

    accounts = _accounts(app)
    assert len(accounts) == 3, "the canonical estate carries three accounts"

    total = 0
    for account in accounts:
        listed = _parse(client, "ListClusters", "/clusters", _auth(account))["clusters"]
        expected = {r.resource_name for r in _clusters(app, account)}
        assert len(listed) == len(expected), "the list does not answer one entry per cluster"
        assert len(listed) == len(set(listed)), "the list repeats a cluster"
        assert set(listed) == expected, "the list does not answer the account's own clusters"
        total += len(listed)

    assert total == 75, f"the canonical estate carries 75 EKS clusters, the lists carry {total}"


def test_describe_cluster_reports_the_estate_cluster(api_client) -> None:
    """The document carries the estate's name and the ARN AWS publishes."""
    client, app = api_client
    resource = _cluster(app)
    name = resource.resource_name
    cluster = _parse(client, "DescribeCluster", f"/clusters/{name}", _auth(resource.parent_scope_id))["cluster"]

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
        _parse(client, "DescribeCluster", f"/clusters/{r.resource_name}", _auth(r.parent_scope_id))["cluster"][
            "arn"
        ]
        for r in _clusters(app)
    }
    assert published == set(arns_by_cluster.values()), "a cluster did not publish its own ARN"


def test_the_arn_is_stable_between_calls(api_client) -> None:
    """The same cluster answers the same ARN on every call."""
    client, app = api_client
    for resource in _clusters(app):
        headers = _auth(resource.parent_scope_id)
        first = _parse(client, "DescribeCluster", f"/clusters/{resource.resource_name}", headers)["cluster"]["arn"]
        second = _parse(client, "DescribeCluster", f"/clusters/{resource.resource_name}", headers)["cluster"]["arn"]
        assert first == second, "an ARN that moved between calls breaks the correlation"


def test_the_simulator_handle_is_still_an_alias(api_client) -> None:
    """The derived id resolves too: an alias is accepted, never published."""
    client, app = api_client
    resource = _cluster(app)
    headers = _auth(resource.parent_scope_id)
    by_name = _parse(client, "DescribeCluster", f"/clusters/{resource.resource_name}", headers)["cluster"]
    by_handle = _parse(client, "DescribeCluster", f"/clusters/{ids.resource_id(resource)}", headers)["cluster"]

    assert by_name["name"] == resource.resource_name
    assert by_handle["name"] == resource.resource_name
    assert by_name["arn"].endswith(f":cluster/{resource.resource_name}")
    assert ids.resource_id(resource) not in by_name["arn"]


def test_a_name_the_estate_reuses_across_accounts_names_one_cluster_per_account(api_client) -> None:
    """A name shared by two accounts names ONE cluster — and a DIFFERENT one per account.

    The surface is account-scoped now, so the same name inside two accounts answers the
    cluster of the account that signed the request, which is what the real service does.
    """
    client, app = api_client
    shared = [
        name
        for name, count in Counter(r.resource_name for r in _clusters(app)).items()
        if count > 1
    ]
    assert shared, "the estate reuses a cluster name across accounts"

    for name in shared:
        owners = {r.parent_scope_id for r in _clusters(app) if r.resource_name == name}
        for account in owners:
            headers = _auth(account)
            first = _parse(client, "DescribeCluster", f"/clusters/{name}", headers)["cluster"]
            second = _parse(client, "DescribeCluster", f"/clusters/{name}", headers)["cluster"]
            assert first == second, "the same name answered two different clusters"
            assert first["name"] == name
            assert f":{account}:" in first["arn"], "the name resolved outside the account of the caller"


def test_node_groups_and_addons(api_client) -> None:
    """The node group and the add-ons keep their own contract.

    The node group's NAME stays on the derived id: an estate name is not a node
    group name AWS would accept (``eks_cluster-0021 (do not delete)``), and
    renaming it would mean inventing one.
    """
    client, app = api_client
    resource = _cluster(app)
    handle = ids.resource_id(resource)
    headers = _auth(resource.parent_scope_id)
    node_groups = _parse(client, "ListNodegroups", f"/clusters/{handle}/node-groups", headers)["nodegroups"]
    addons = _parse(client, "ListAddons", f"/clusters/{handle}/addons", headers)["addons"]

    assert len(node_groups) == 1
    assert node_groups[0] == f"{handle}-ng"
    assert set(addons) == set(projection.DEFAULT_ADDONS)


def test_the_role_keeps_the_derived_id(api_client) -> None:
    """The service role is an IAM name: it cannot carry the estate's name."""
    client, app = api_client
    resource = _cluster(app)
    headers = _auth(resource.parent_scope_id)
    cluster = _parse(client, "DescribeCluster", f"/clusters/{resource.resource_name}", headers)["cluster"]

    assert cluster["roleArn"] == (
        f"arn:aws:iam::{resource.parent_scope_id}:role/{ids.resource_id(resource)}-cluster-role"
    )


def test_an_unknown_cluster_is_not_found(api_client) -> None:
    client, _ = api_client
    error = _parse(client, "DescribeCluster", "/clusters/nope")
    assert error["Error"]["Code"] == "ResourceNotFoundException"
