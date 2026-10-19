"""DynamoDB JSON-protocol tests, parsed with botocore's own parser.

A table name is the resource's AWS id (``aws_sim.ids``), the same value its ARN ends in, so
the assertion is on identity rather than on the estate's ``resource_name``: the estate reuses
a name across accounts and a table name has to name one table.
"""

from __future__ import annotations

import json

import botocore.session
from botocore.parsers import create_parser

from aws_sim import ids, scope

_MODEL = botocore.session.get_session().get_service_model("dynamodb")
_PARSER = create_parser("json")


def _parse(client, operation: str, body: dict | None = None):
    target = f"{_MODEL.metadata['targetPrefix']}.{operation}"
    response = client.post("/", content=json.dumps(body or {}), headers={"X-Amz-Target": target})
    raw = {"status_code": response.status_code, "headers": dict(response.headers), "body": response.content}
    shape = _MODEL.operation_model(operation).output_shape
    if response.status_code != 200:
        return _PARSER._do_error_parse(raw, shape)
    return _PARSER.parse(raw, shape)


def test_list_tables_derives_from_the_estate(api_client) -> None:
    client, app = api_client
    expected = sorted(
        ids.resource_id(r)
        for r in scope.resources(app.state.estate)
        if r.resource_type == "dynamodb_table"
    )
    assert _parse(client, "ListTables")["TableNames"] == expected
    assert expected, "the estate has DynamoDB tables"
    assert len(set(expected)) == len(expected), "a table name names one table"


def test_an_unknown_operation_is_refused(api_client) -> None:
    client, _ = api_client
    error = _parse(client, "DescribeTable")
    assert error["Error"]["Code"] == "UnknownOperationException"
