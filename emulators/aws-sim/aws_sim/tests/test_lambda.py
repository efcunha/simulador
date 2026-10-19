"""Lambda REST-JSON tests, parsed with botocore's own parser.

``LastModified`` is asserted to be a **string** in Lambda's own format: the model types
that member as a string, so a datetime or a numeric epoch would reach FinOps where it
expects text and the inventory row would show a Python repr.

``FunctionName`` is asserted to be the resource's AWS id (``aws_sim.ids``) and to be the name
the ARN ends in, so the two members cannot name two different functions.
"""

from __future__ import annotations

import re

import botocore.session
from botocore.parsers import create_parser

from aws_sim import arns, ids, scope
from aws_sim.projections import lambda_ as projection

_MODEL = botocore.session.get_session().get_service_model("lambda")
_PARSER = create_parser("rest-json")

_LAST_MODIFIED = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}\+0000$")


def _parse(client, path: str = "/2015-03-31/functions"):
    response = client.get(path)
    raw = {"status_code": response.status_code, "headers": dict(response.headers), "body": response.content}
    shape = _MODEL.operation_model("ListFunctions").output_shape
    if response.status_code != 200:
        return _PARSER._do_error_parse(raw, shape)
    return _PARSER.parse(raw, shape)


def test_list_functions_derives_from_the_estate(api_client) -> None:
    client, app = api_client
    expected = sorted(
        (
            r
            for r in scope.resources(app.state.estate)
            if r.resource_type == "lambda_function"
        ),
        key=ids.resource_id,
    )
    functions = _parse(client)["Functions"]

    assert [row["FunctionName"] for row in functions] == [ids.resource_id(r) for r in expected]
    assert [row["FunctionArn"] for row in functions] == [arns.resource_arn(r) for r in expected]
    for row in functions:
        assert row["FunctionArn"].endswith(f":function:{row['FunctionName']}"), "one identity, not two"
        assert row["Runtime"] in projection.RUNTIMES
        assert row["MemorySize"] in projection.MEMORY_MB
        assert row["State"] == "Active"
        assert isinstance(row["LastModified"], str)
        assert _LAST_MODIFIED.match(row["LastModified"])


def test_the_documented_uri_with_a_trailing_slash_reaches_the_same_handler(api_client) -> None:
    client, _ = api_client
    assert _parse(client, "/2015-03-31/functions/")["Functions"] == _parse(client)["Functions"]
