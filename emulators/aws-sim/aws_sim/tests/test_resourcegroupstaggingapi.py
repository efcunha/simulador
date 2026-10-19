"""Resource Groups Tagging API tests, parsed with botocore's own parser.

This endpoint is what FinOps tag governance reads, so the assertions are on
coverage and on coherence: every resource that has an ARN appears with the estate's own
tag pairs, and the ARNs it reports are the same ones the per-service endpoints report.
"""

from __future__ import annotations

import json

import botocore.session
from botocore.parsers import create_parser

from aws_sim import arns, scope

_MODEL = botocore.session.get_session().get_service_model("resourcegroupstaggingapi")
_RDS_MODEL = botocore.session.get_session().get_service_model("rds")
_PARSER = create_parser("json")
_QUERY_PARSER = create_parser("query")


def _parse(client, operation: str, body: dict | None = None):
    target = f"{_MODEL.metadata['targetPrefix']}.{operation}"
    response = client.post("/", content=json.dumps(body or {}), headers={"X-Amz-Target": target})
    raw = {"status_code": response.status_code, "headers": dict(response.headers), "body": response.content}
    shape = _MODEL.operation_model(operation).output_shape
    if response.status_code != 200:
        return _PARSER._do_error_parse(raw, shape)
    return _PARSER.parse(raw, shape)


def _expected_tags(app) -> dict[str, list[list[tuple[str, str]]]]:
    rows: dict[str, list[list[tuple[str, str]]]] = {}
    for resource in scope.resources(app.state.estate):
        arn = arns.resource_arn(resource)
        if arn is not None:
            rows.setdefault(arn, []).append([(key, value) for key, value in resource.tags])
    return rows


def test_get_resources_covers_every_resource_that_has_an_arn(api_client) -> None:
    client, app = api_client
    mappings = _parse(client, "GetResources")["ResourceTagMappingList"]
    expected = _expected_tags(app)

    assert mappings, "the estate has AWS resources"
    assert len(mappings) == sum(len(tag_sets) for tag_sets in expected.values())
    for mapping in mappings:
        assert mapping["ResourceARN"].startswith("arn:aws:")
        assert [(tag["Key"], tag["Value"]) for tag in mapping["Tags"]] in expected[mapping["ResourceARN"]]


def test_a_resource_type_without_an_arn_is_not_reported(api_client) -> None:
    """``data_transfer`` is a cost line, not an object: it must not appear."""
    client, app = api_client
    resources = list(scope.resources(app.state.estate))
    with_arn = [resource for resource in resources if arns.resource_arn(resource) is not None]
    assert len(with_arn) < len(resources), "the estate carries rows with no AWS object behind them"
    assert len(_parse(client, "GetResources")["ResourceTagMappingList"]) == len(with_arn)


def test_tag_filters_select_on_the_estates_own_tags(api_client) -> None:
    client, _ = api_client
    all_rows = _parse(client, "GetResources")["ResourceTagMappingList"]
    filtered = _parse(client, "GetResources", {"TagFilters": [{"Key": "env"}]})["ResourceTagMappingList"]

    assert 0 < len(filtered) < len(all_rows)
    assert all(any(tag["Key"] == "env" for tag in row["Tags"]) for row in filtered)
    assert len(filtered) == sum(1 for row in all_rows if any(tag["Key"] == "env" for tag in row["Tags"]))


def test_resource_type_filters_is_refused(api_client) -> None:
    """Its ``service:resource`` notation has no counterpart here; a refusal beats a lie."""
    client, _ = api_client
    error = _parse(client, "GetResources", {"ResourceTypeFilters": ["ec2:instance"]})
    assert error["Error"]["Code"] == "InvalidParameterException"


def test_the_rds_arn_matches_describe_db_instances(api_client) -> None:
    """The ARN FinOps correlates across endpoints is one ARN, not two."""
    client, _ = api_client
    response = client.post("/", data={"Action": "DescribeDBInstances", "Version": _RDS_MODEL.api_version})
    raw = {"status_code": response.status_code, "headers": dict(response.headers), "body": response.content}
    instances = _QUERY_PARSER.parse(raw, _RDS_MODEL.operation_model("DescribeDBInstances").output_shape)
    rds_arns = {row["DBInstanceArn"] for row in instances["DBInstances"]}

    reported = {m["ResourceARN"] for m in _parse(client, "GetResources")["ResourceTagMappingList"]}
    assert rds_arns
    assert rds_arns <= reported
