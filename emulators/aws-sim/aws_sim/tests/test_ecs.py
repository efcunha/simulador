"""ECS JSON-protocol tests, parsed with botocore's own parser.

The clusters come from the estate; the services are derived from those clusters. The
assertions are that both are ARNs of real estate clusters — a service ARN that named a
cluster the estate does not have would be an invented resource.
"""

from __future__ import annotations

import json

import botocore.session
from botocore.parsers import create_parser

from aws_sim import arns, scope
from aws_sim.projections import ecs

_MODEL = botocore.session.get_session().get_service_model("ecs")
_PARSER = create_parser("json")


def _parse(client, operation: str, body: dict | None = None):
    target = f"{_MODEL.metadata['targetPrefix']}.{operation}"
    response = client.post("/", content=json.dumps(body or {}), headers={"X-Amz-Target": target})
    raw = {"status_code": response.status_code, "headers": dict(response.headers), "body": response.content}
    shape = _MODEL.operation_model(operation).output_shape
    if response.status_code != 200:
        return _PARSER._do_error_parse(raw, shape)
    return _PARSER.parse(raw, shape)


def test_list_clusters_derives_from_the_estate(api_client) -> None:
    client, app = api_client
    expected = sorted(
        (
            r
            for r in scope.resources(app.state.estate)
            if r.resource_type == "ecs_cluster"
        ),
        key=lambda r: r.resource_name,
    )
    expected_arns = sorted(arn for r in expected if (arn := arns.resource_arn(r)) is not None)
    cluster_arns = _parse(client, "ListClusters")["clusterArns"]
    assert cluster_arns == expected_arns
    assert all(arn.startswith("arn:aws:ecs:") and ":cluster/" in arn for arn in cluster_arns)


def test_list_services_names_its_clusters(api_client) -> None:
    client, _ = api_client
    cluster_arns = _parse(client, "ListClusters")["clusterArns"]
    service_arns = _parse(client, "ListServices")["serviceArns"]

    assert len(service_arns) == len(cluster_arns) * len(ecs.SERVICE_SUFFIXES)
    for cluster_arn in cluster_arns:
        cluster_name = cluster_arn.rsplit("/", 1)[-1]
        assert {arn for arn in service_arns if f":service/{cluster_name}/" in arn}


def test_list_services_can_be_scoped_to_one_cluster(api_client) -> None:
    client, _ = api_client
    cluster_arn = _parse(client, "ListClusters")["clusterArns"][0]
    service_arns = _parse(client, "ListServices", {"cluster": cluster_arn})["serviceArns"]

    assert len(service_arns) == len(ecs.SERVICE_SUFFIXES)
    assert all(f":service/{cluster_arn.rsplit('/', 1)[-1]}/" in arn for arn in service_arns)


def test_an_unknown_operation_is_refused(api_client) -> None:
    client, _ = api_client
    error = _parse(client, "DescribeClusters")
    assert error["Error"]["Code"] == "InvalidParameterException"
