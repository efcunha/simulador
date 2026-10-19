"""RDS Query-protocol tests, parsed with botocore's own parser.

The load-bearing assertion is derivation: every instance here has to come from the
estate's own ``rds_instance`` rows, with the ARN the tagging API reports for the same
row (``test_resourcegroupstaggingapi.py`` asserts the other half of that pair). A
hard-coded instance list could not hold that.

The identifier is the resource's **derived AWS id** (``aws_sim.ids``), not its
``resource_name``: the estate reuses a name across scopes and an RDS identifier carries no
scope, so a name-keyed row would identify several instances at once — and the CloudWatch
shim dimensions the CPU series by this very value, which is how several instances came to be
judged on one resource's samples.
"""

from __future__ import annotations

import botocore.session
from botocore.parsers import create_parser

from aws_sim import ids, scope

_MODEL = botocore.session.get_session().get_service_model("rds")
_PARSER = create_parser("query")


def _parse(client, operation: str, **params: str):
    """POST an RDS Query-protocol request and parse it the way the client does."""
    form = {"Action": operation, "Version": _MODEL.api_version, **params}
    response = client.post("/", data=form)
    raw = {"status_code": response.status_code, "headers": dict(response.headers), "body": response.content}
    shape = _MODEL.operation_model(operation).output_shape
    if response.status_code != 200:
        return _PARSER._do_error_parse(raw, shape)
    return _PARSER.parse(raw, shape)


def _estate_instances(app):
    return sorted(
        (r for r in scope.resources(app.state.estate) if r.resource_type == "rds_instance"),
        key=ids.resource_id,
    )


def test_describe_db_instances_derives_from_the_estate(api_client) -> None:
    client, app = api_client
    expected = _estate_instances(app)
    instances = _parse(client, "DescribeDBInstances")["DBInstances"]

    assert [row["DBInstanceIdentifier"] for row in instances] == [ids.resource_id(r) for r in expected]
    assert len({row["DBInstanceIdentifier"] for row in instances}) == len(instances), "one id per instance"
    for row in instances:
        assert row["DBInstanceStatus"] == "available"
        assert row["DBInstanceClass"].startswith("db.")
        assert row["Engine"]
        assert row["EngineVersion"]
        assert row["DBInstanceArn"].startswith("arn:aws:rds:")
        assert row["DBInstanceArn"].endswith(f":db:{row['DBInstanceIdentifier']}")
        assert isinstance(row["MultiAZ"], bool)
        assert row["Endpoint"]["Port"] > 0
        assert row["Endpoint"]["Address"].startswith(f"{row['DBInstanceIdentifier']}.")
        assert row["AllocatedStorage"] > 0
    assert all(row["InstanceCreateTime"] is not None for row in instances)


def test_one_instance_can_be_named(api_client) -> None:
    client, app = api_client
    identifier = ids.resource_id(_estate_instances(app)[0])
    instances = _parse(client, "DescribeDBInstances", DBInstanceIdentifier=identifier)["DBInstances"]
    assert len(instances) == 1
    assert instances[0]["DBInstanceIdentifier"] == identifier


def test_unknown_instance_is_a_not_found(api_client) -> None:
    client, _ = api_client
    error = _parse(client, "DescribeDBInstances", DBInstanceIdentifier="nope")
    assert error["Error"]["Code"] == "DBInstanceNotFoundFault"


def test_filters_are_refused_rather_than_ignored(api_client) -> None:
    """A filter over a field the estate does not carry must not answer with every row."""
    client, _ = api_client
    error = _parse(client, "DescribeDBInstances", **{"Filters.member.1.FilterName": "engine"})
    assert error["Error"]["Code"] == "InvalidParameterValue"
