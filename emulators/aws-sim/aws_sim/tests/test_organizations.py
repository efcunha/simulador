"""Organizations JSON-protocol tests, parsed with botocore's own parser."""

from __future__ import annotations

import json

import botocore.session
from botocore.parsers import create_parser
from tools.synthetic_clouds.render.markers import SYNTH_NAME_PREFIX, unmarked_name

_MODEL = botocore.session.get_session().get_service_model("organizations")
_PARSER = create_parser("json")


def _parse(client, operation: str, body: dict | None = None):
    target = f"{_MODEL.metadata['targetPrefix']}.{operation}"
    response = client.post(
        "/",
        content=json.dumps(body or {}),
        headers={"X-Amz-Target": target, "Content-Type": "application/x-amz-json-1.1"},
    )
    raw = {"status_code": response.status_code, "headers": dict(response.headers), "body": response.content}
    shape = _MODEL.operation_model(operation).output_shape
    if response.status_code != 200:
        return _PARSER._do_error_parse(raw, shape)
    return _PARSER.parse(raw, shape)


def test_list_accounts_parses(api_client) -> None:
    client, _ = api_client
    accounts = _parse(client, "ListAccounts")["Accounts"]
    assert accounts, "the estate has AWS member accounts"
    for account in accounts:
        assert len(account["Id"]) == 12 and account["Id"].isdigit()
        assert account["Arn"].startswith("arn:aws:organizations:")
        assert account["Status"] == "ACTIVE"
        assert account["JoinedTimestamp"] is not None


def test_list_accounts_serves_the_unmarked_account_name(api_client) -> None:
    """``ListAccounts`` serves the account's own name, with no FinOps marker.

    The estate keeps the ``[SYNTH] `` prefix — that is FinOps storage
    discriminator — but the cloud response must not: no real ``ListAccounts`` returns a
    simulator marker, and ``org_discovery.py (modulo do consumidor)`` persists the served ``Name``
    verbatim into ``cloud_accounts.name``.
    """
    client, app = api_client
    accounts = _parse(client, "ListAccounts")["Accounts"]
    estate_names = {
        str(account.account_id): account.name
        for org in app.state.estate.aws_orgs
        for account in org.accounts
    }
    assert accounts, "the estate has AWS member accounts"
    for account in accounts:
        served = account["Name"]
        assert served, "Name must not be empty"
        assert not served.startswith(SYNTH_NAME_PREFIX), f"marker leaked into ListAccounts: {served!r}"
        assert served == unmarked_name(estate_names[account["Id"]])
        # The marker stays where it is read: the canonical estate / FinOps storage.
        assert estate_names[account["Id"]].startswith(SYNTH_NAME_PREFIX)


def test_describe_organization(api_client) -> None:
    client, _ = api_client
    org = _parse(client, "DescribeOrganization")["Organization"]
    assert org["Id"].startswith("o-")
    assert org["MasterAccountId"]
    assert org["FeatureSet"] == "ALL"


def test_unknown_operation_is_refused(api_client) -> None:
    client, _ = api_client
    response = client.post(
        "/",
        content="{}",
        headers={"X-Amz-Target": f"{_MODEL.metadata['targetPrefix']}.CreateAccount"},
    )
    assert response.status_code == 400
    assert b"InvalidActionException" in response.content
