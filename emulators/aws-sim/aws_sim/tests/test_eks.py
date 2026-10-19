"""EKS REST-JSON tests, parsed with botocore's own parser.

The paths are the ones the SDK composes from the model (``/clusters``,
``/clusters/{name}``, …), so a route that only worked for a hand-written URL would fail
here.

A cluster's ``name`` is asserted to be the resource's derived AWS id (``aws_sim.ids``), which
is what the ARN and the node-group names hang off: the estate reuses a name across accounts,
so a name read from the estate would name several clusters at once.
"""

from __future__ import annotations

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


def _cluster(app):
    return sorted(
        (r for r in scope.resources(app.state.estate) if r.resource_type == "eks_cluster"),
        key=ids.resource_id,
    )[0]


def test_list_clusters_derives_from_the_estate(api_client) -> None:
    client, app = api_client
    expected = [
        ids.resource_id(r)
        for r in sorted(
            (r for r in scope.resources(app.state.estate) if r.resource_type == "eks_cluster"),
            key=lambda r: r.resource_name,
        )
    ]
    assert _parse(client, "ListClusters", "/clusters")["clusters"] == expected
    assert expected, "the estate has EKS clusters"


def test_describe_cluster_reports_the_estate_cluster(api_client) -> None:
    client, app = api_client
    resource = _cluster(app)
    name = ids.resource_id(resource)
    cluster = _parse(client, "DescribeCluster", f"/clusters/{name}")["cluster"]

    assert cluster["name"] == name
    assert cluster["arn"].startswith("arn:aws:eks:")
    assert cluster["arn"].endswith(f":cluster/{name}"), "one name, not two"
    assert cluster["status"] == "ACTIVE"
    assert cluster["version"]
    assert cluster["createdAt"] is not None
    assert cluster["endpoint"].startswith("https://")
    assert cluster["identity"]["oidc"]["issuer"].startswith("https://oidc.eks.")
    assert cluster["resourcesVpcConfig"]["endpointPublicAccess"] is True
    assert cluster["tags"] == {key: value for key, value in resource.tags}


def test_node_groups_and_addons(api_client) -> None:
    client, app = api_client
    name = ids.resource_id(_cluster(app))
    node_groups = _parse(client, "ListNodegroups", f"/clusters/{name}/node-groups")["nodegroups"]
    addons = _parse(client, "ListAddons", f"/clusters/{name}/addons")["addons"]

    assert len(node_groups) == 1
    assert node_groups[0].startswith(name)
    assert set(addons) == set(projection.DEFAULT_ADDONS)


def test_an_unknown_cluster_is_not_found(api_client) -> None:
    client, _ = api_client
    error = _parse(client, "DescribeCluster", "/clusters/nope")
    assert error["Error"]["Code"] == "ResourceNotFoundException"
