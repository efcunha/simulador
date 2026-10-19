"""SSO and SSO-OIDC REST-JSON tests.

These paths are what the AWS CLI/SDK hits during an SSO login and when it exchanges a role
for credentials, so the assertions are on the wire shape the SDK parses (paths, query
params, JSON keys) rather than on an internal helper.
"""

from __future__ import annotations

from aws_sim import scope


def test_get_role_credentials(api_client) -> None:
    client, app = api_client
    account = sorted(scope.scope_ids(app.state.estate))[0]
    response = client.get(
        "/federation/credentials", params={"account_id": account, "role_name": "readonly-consumer"}
    )
    assert response.status_code == 200
    credentials = response.json()["roleCredentials"]
    assert credentials["accessKeyId"].startswith("ASIA")
    assert credentials["sessionToken"]
    assert isinstance(credentials["expiration"], int)


def test_unknown_account_is_not_found(api_client) -> None:
    client, _ = api_client
    response = client.get(
        "/federation/credentials", params={"account_id": "000000000000", "role_name": "r"}
    )
    assert response.status_code == 404
    assert "ResourceNotFoundException" in response.json()["__type"]


def test_missing_params_is_invalid_request(api_client) -> None:
    client, _ = api_client
    response = client.get("/federation/credentials")
    assert response.status_code == 400
    assert "InvalidRequestException" in response.json()["__type"]


def test_register_client(api_client) -> None:
    client, _ = api_client
    response = client.post("/client/register", json={"clientName": "FinOps", "clientType": "public"})
    assert response.status_code == 200
    body = response.json()
    assert body["clientId"].startswith("synthetic-")
    assert body["clientSecret"]


def test_device_authorization(api_client) -> None:
    client, _ = api_client
    response = client.post(
        "/device_authorization",
        json={"clientId": "synthetic-consumer", "clientSecret": "x", "startUrl": "https://x.awsapps.com/start"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["deviceCode"] and body["userCode"] and body["verificationUri"]


def test_create_token(api_client) -> None:
    client, _ = api_client
    response = client.post(
        "/token", json={"clientId": "synthetic-consumer", "grantType": "device_code", "deviceCode": "d"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["accessToken"]
    assert body["tokenType"] == "Bearer"
    assert isinstance(body["expiresIn"], int)
