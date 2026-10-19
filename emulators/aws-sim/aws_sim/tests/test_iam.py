"""IAM Query-protocol tests, parsed with botocore's own parser.

Two load-bearing assertions: the report's ``Content`` is the blob FinOps decodes with
``.decode("utf-8")`` and its header is AWS's own column set, and the report that comes
back is the **calling account's** — the emulator's one account-from-credential rule, the
same one ``sts.GetCallerIdentity`` follows.
"""

from __future__ import annotations

import botocore.session
from botocore.parsers import create_parser

from aws_sim import scope
from aws_sim.projections import iam, sts

_MODEL = botocore.session.get_session().get_service_model("iam")
_PARSER = create_parser("query")


def _parse(client, operation: str, account: str | None = None, **params: str):
    """POST an IAM Query-protocol request and parse it the way the client does."""
    headers = {}
    if account is not None:
        headers["Authorization"] = (
            "AWS4-HMAC-SHA256 "
            f"Credential={sts.access_key_for_account(account)}/20260101/us-east-1/iam/aws4_request, "
            "SignedHeaders=host;x-amz-date, Signature=deadbeef"
        )
    form = {"Action": operation, "Version": _MODEL.api_version, **params}
    response = client.post("/", data=form, headers=headers)
    raw = {"status_code": response.status_code, "headers": dict(response.headers), "body": response.content}
    shape = _MODEL.operation_model(operation).output_shape
    if response.status_code != 200:
        return _PARSER._do_error_parse(raw, shape)
    return _PARSER.parse(raw, shape)


def _account_with_iam_findings(estate) -> str:
    index = scope.resource_index(estate)
    for finding in estate.findings:
        resource = index.get(finding.resource_uuid)
        if finding.provider == "aws" and finding.category == "IAM" and resource is not None:
            return resource.parent_scope_id
    raise AssertionError("the estate carries AWS IAM findings")


def test_generate_credential_report_is_complete(api_client) -> None:
    """A frozen estate has nothing to compute, so the report is ready on the first call."""
    client, app = api_client
    account = _account_with_iam_findings(app.state.estate)
    result = _parse(client, "GenerateCredentialReport", account=account)
    assert result["State"] == "COMPLETE"
    assert account in result["Description"]


def test_get_credential_report_is_the_blob_FinOps_decodes(api_client) -> None:
    client, app = api_client
    account = _account_with_iam_findings(app.state.estate)
    result = _parse(client, "GetCredentialReport", account=account)

    assert result["ReportFormat"] == "text/csv"
    assert result["GeneratedTime"] is not None
    assert isinstance(result["Content"], bytes), "botocore decodes the base64 blob to bytes"
    lines = result["Content"].decode("utf-8").strip().split("\n")
    assert lines[0].split(",") == list(iam.HEADER)
    assert lines[0].startswith("user,arn,user_creation_time,password_enabled")
    for line in lines[1:]:
        assert len(line.split(",")) == len(iam.HEADER)


def test_the_report_covers_the_calling_account(api_client) -> None:
    client, app = api_client
    estate = app.state.estate
    account = _account_with_iam_findings(estate)
    other = next(value for value in sorted(scope.scope_ids(estate)) if value != account)

    content = _parse(client, "GetCredentialReport", account=account)["Content"].decode("utf-8")
    lines = content.strip().split("\n")
    user_arns = {
        line.split(",")[1] for line in lines[1:] if line.split(",")[0] != iam.ROOT_USER
    }
    assert user_arns
    assert all(arn.startswith(f"arn:aws:iam::{account}:") for arn in user_arns)
    root_row = next(line for line in lines[1:] if line.split(",")[0] == iam.ROOT_USER)
    assert root_row.split(",")[1] == f"arn:aws:iam::{account}:root"

    other_content = _parse(client, "GetCredentialReport", account=other)["Content"].decode("utf-8")
    assert other_content != content


def test_high_severity_findings_become_users_without_mfa(api_client) -> None:
    """C09's "admin without MFA" case: the estate's own severities decide the report."""
    client, app = api_client
    estate = app.state.estate
    account = _account_with_iam_findings(estate)
    expected = {user.name for user in iam.users(estate, account) if not user.mfa_active}
    assert expected, "the estate carries a HIGH/CRITICAL IAM finding"

    content = _parse(client, "GetCredentialReport", account=account)["Content"].decode("utf-8")
    without_mfa = {
        line.split(",")[0]
        for line in content.strip().split("\n")[1:]
        if line.split(",")[iam.HEADER.index("mfa_active")] == "false"
    }
    assert without_mfa == expected
    assert all(
        line.split(",")[iam.HEADER.index("password_enabled")] == "true"
        for line in content.strip().split("\n")[1:]
        if line.split(",")[0] in without_mfa
    )
