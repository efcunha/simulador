"""SSO and SSO-OIDC over the AWS REST-JSON protocol.

These two services are not Query and not JSON-1.1: the client hits a **path** and reads a
JSON body. ``sso.GetRoleCredentials`` is ``GET /federation/credentials`` (the credential
the AWS CLI/SDK actually uses), and the SSO-OIDC device flow is ``POST /token``,
``/client/register`` and ``/device_authorization``.

Minted credentials reuse the STS encoding (``projections/sts.py``), so an SSO role's
credentials decode to the same account an ``AssumeRole`` would — the emulator has one
account-from-credential rule, not two.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from tools.synthetic_clouds.model.estate import CanonicalEstate

from aws_sim import scope
from aws_sim.projections import sts

router = APIRouter()

_SSO_ERROR_PREFIX = "com.amazonaws.sso#"
_SSO_OIDC_ERROR_PREFIX = "com.amazonaws.ssooidc#"

#: Token lifetime, in seconds and in epoch millis (the two services disagree on unit).
_TOKEN_LIFETIME_SECONDS = 3600


def _error(prefix: str, code: str, message: str, status_code: int = 400) -> JSONResponse:
    return JSONResponse(
        {"message": message, "__type": f"{prefix}{code}"},
        status_code=status_code,
        headers={"x-amzn-errortype": code},
    )


def _role_credentials(account_id: str) -> dict[str, Any]:
    expiration = datetime.now(UTC) + timedelta(seconds=_TOKEN_LIFETIME_SECONDS)
    return {
        "accessKeyId": sts.access_key_for_account(account_id),
        "secretAccessKey": f"synthetic-secret-{account_id}",
        "sessionToken": f"synthetic-session-{account_id}",
        "expiration": int(expiration.timestamp() * 1000),
    }


@router.get("/federation/credentials")
async def get_role_credentials(request: Request, account_id: str = "", role_name: str = "") -> Any:
    """``sso.GetRoleCredentials`` — the credentials for one account/role pair.

    The ``x-amz-sso_bearer_token`` header is required by the real service but not read
    here: the emulator answers any caller, and a value the emulator cannot verify would be
    a claim it cannot keep.
    """
    if not account_id or not role_name:
        return _error(_SSO_ERROR_PREFIX, "InvalidRequestException", "account_id and role_name are required.")
    estate: CanonicalEstate = request.app.state.estate
    if account_id not in scope.scope_ids(estate):
        return _error(
            _SSO_ERROR_PREFIX,
            "ResourceNotFoundException",
            f"No role '{role_name}' found for account {account_id}.",
            404,
        )
    return {"roleCredentials": _role_credentials(account_id)}


@router.post("/client/register")
async def register_client(request: Request) -> Any:
    """``sso-oidc.RegisterClient`` — register a device-flow client."""
    body = await _json_body(request)
    name = str(body.get("clientName", "FinOps"))
    issued = int(datetime.now(UTC).timestamp())
    return {
        "clientId": f"synthetic-{name}",
        "clientSecret": f"synthetic-secret-{name}",
        "clientIdIssuedAt": issued,
        "clientSecretExpiresAt": issued + _TOKEN_LIFETIME_SECONDS,
    }


@router.post("/device_authorization")
async def start_device_authorization(request: Request) -> Any:
    """``sso-oidc.StartDeviceAuthorization`` — begin the device flow."""
    body = await _json_body(request)
    if not body.get("clientId"):
        return _error(_SSO_OIDC_ERROR_PREFIX, "InvalidRequestException", "clientId is required.")
    code = str(body["clientId"]).removeprefix("synthetic-")
    return {
        "deviceCode": f"device-{code}",
        "userCode": "SYNTH-CODE",
        "verificationUri": "https://synthetic.contoso.example/device",
        "verificationUriComplete": f"https://synthetic.contoso.example/device?user_code=SYNTH-CODE&client={code}",
        "expiresIn": _TOKEN_LIFETIME_SECONDS,
        "interval": 1,
    }


@router.post("/token")
async def create_token(request: Request) -> Any:
    """``sso-oidc.CreateToken`` — mint an access token for any grant type."""
    body = await _json_body(request)
    client_id = str(body.get("clientId", "synthetic"))
    if not client_id:
        return _error(_SSO_OIDC_ERROR_PREFIX, "InvalidRequestException", "clientId is required.")
    return {
        "accessToken": f"synthetic-access-{client_id}",
        "tokenType": "Bearer",
        "expiresIn": _TOKEN_LIFETIME_SECONDS,
        "refreshToken": f"synthetic-refresh-{client_id}",
        "idToken": f"synthetic-id-{client_id}",
    }


async def _json_body(request: Request) -> dict[str, Any]:
    """Parse a JSON body, tolerating an empty one (a body-less smoke request)."""
    raw = await request.body()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
