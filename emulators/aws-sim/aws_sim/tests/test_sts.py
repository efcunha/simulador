"""STS Query-protocol tests, parsed with botocore's own parser.

The load-bearing assertion is the confused-deputy path: ``AssumeRole`` mints credentials
whose access key encodes the target account, and ``GetCallerIdentity`` — called with those
credentials — must report **that same account**, because FinOps raises on a mismatch.
Parsing through ``botocore.parsers`` is what makes the assertion meaningful: it is the
parser the real client runs, so a hand-written envelope cannot pass by accident.
"""

from __future__ import annotations

import botocore.session
import pytest
from botocore.parsers import create_parser
from fastapi.testclient import TestClient

from aws_sim import query_xml, scope
from aws_sim.api.sts import supported_actions

_MODEL = botocore.session.get_session().get_service_model("sts")
_PARSER = create_parser("query")


def _parse(client: TestClient, operation: str, headers: dict[str, str] | None = None, **params):
    """POST an STS Query-protocol request and parse the response the way the client does."""
    form = {"Action": operation, "Version": query_xml.STS.api_version(), **params}
    response = client.post("/", data=form, headers=headers or {})
    raw = {"status_code": response.status_code, "headers": dict(response.headers), "body": response.content}
    shape = _MODEL.operation_model(operation).output_shape
    if response.status_code != 200:
        return _PARSER._do_error_parse(raw, shape)
    return _PARSER.parse(raw, shape)


def _client(denied_account: str = "") -> TestClient:
    from aws_sim.api.app import create_app
    from aws_sim.config import load_settings

    app = create_app(
        load_settings(env={}, SEED="42", PROFILE="small", CURRENCY="USD", AWS_SIM_DENIED_ACCOUNT=denied_account)
    )
    return TestClient(app)


@pytest.fixture(scope="module")
def _known_account(api_client) -> str:
    _, app = api_client
    return sorted(scope.scope_ids(app.state.estate))[0]


def test_api_version_matches_the_service_model() -> None:
    assert query_xml.STS.api_version() == "2011-06-15"


def test_serves_only_the_two_control_operations() -> None:
    assert supported_actions() == ("AssumeRole", "GetCallerIdentity")


def test_assume_role_then_get_caller_identity_reports_the_same_account(api_client, _known_account) -> None:
    """The confused-deputy guard: the assumed account survives the round trip."""
    client, _ = api_client
    role_arn = f"arn:aws:iam::{_known_account}:role/readonly-consumer"

    assumed = _parse(client, "AssumeRole", RoleArn=role_arn, RoleSessionName="consumer-test", DurationSeconds="3600")
    credentials = assumed["Credentials"]
    assert credentials["AccessKeyId"].startswith("ASIA")
    assert credentials["SessionToken"]
    assert credentials["Expiration"] is not None
    assert assumed["AssumedRoleUser"]["Arn"].endswith("/consumer-test")

    authorization = (
        "AWS4-HMAC-SHA256 "
        f"Credential={credentials['AccessKeyId']}/20260101/us-east-1/sts/aws4_request, "
        "SignedHeaders=host;x-amz-date, Signature=deadbeef"
    )
    identity = _parse(client, "GetCallerIdentity", headers={"Authorization": authorization})
    assert identity["Account"] == _known_account


def test_assume_role_denied_account_is_an_access_denied(_known_account) -> None:
    """A08: the designated member is refused the way STS refuses — AccessDenied."""
    client = _client(denied_account=_known_account)
    error = _parse(
        client,
        "AssumeRole",
        RoleArn=f"arn:aws:iam::{_known_account}:role/readonly-consumer",
        RoleSessionName="consumer-test",
    )
    assert error["Error"]["Code"] == "AccessDenied"


def test_assume_role_unknown_account_is_an_access_denied(api_client) -> None:
    client, _ = api_client
    error = _parse(
        client,
        "AssumeRole",
        RoleArn="arn:aws:iam::000000000000:role/readonly-consumer",
        RoleSessionName="consumer-test",
    )
    assert error["Error"]["Code"] == "AccessDenied"


def test_malformed_role_arn_is_a_validation_error(api_client) -> None:
    client, _ = api_client
    error = _parse(client, "AssumeRole", RoleArn="not-an-arn", RoleSessionName="consumer-test")
    assert error["Error"]["Code"] == "ValidationError"


def test_missing_role_arn_is_a_missing_parameter(api_client) -> None:
    client, _ = api_client
    error = _parse(client, "AssumeRole", RoleSessionName="consumer-test")
    assert error["Error"]["Code"] == "MissingParameter"


def test_wrong_api_version_is_rejected(api_client) -> None:
    client, _ = api_client
    response = client.post("/", data={"Action": "GetCallerIdentity", "Version": "1999-01-01"})
    assert response.status_code == 400
    error = _PARSER._do_error_parse(
        {"status_code": 400, "headers": dict(response.headers), "body": response.content}, None
    )
    assert error["Error"]["Code"] == "InvalidParameterValue"


def test_unknown_action_is_an_invalid_action(api_client) -> None:
    client, _ = api_client
    error = _parse(client, "GetFederationToken")
    assert error["Error"]["Code"] == "InvalidAction"
    assert "GetFederationToken" in error["Error"]["Message"]
