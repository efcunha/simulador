"""Azure AD / Entra OAuth2 endpoints the real SDKs call (design §5.1, §9).

``azure-identity`` (MSAL) does not accept an override to "believe any token":
it performs the same discovery it performs against the real cloud. Because
``login.microsoftonline.com`` is a well-known authority, MSAL skips instance
discovery and calls the tenant's OIDC document directly:

    GET  /{tenant}/v2.0/.well-known/openid-configuration
    POST /{tenant}/oauth2/v2.0/token          (application/x-www-form-urlencoded)

Both are implemented here against the REAL hostname. The token is a real
JWT-shaped bearer (header.payload.signature) so it survives every consumer that
inspects shape; it is signed with a simulator-local HMAC key and grants nothing.
The ``synth:`` marker stays in the response (and in ``jti``) so no log mistakes
it for a credential. A real client secret is never validated — this is a
simulator, and the surrounding TLS/DNS mapping is what makes the SDK reach it.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid
from typing import Any
from urllib.parse import parse_qs

from fastapi import APIRouter, Request

from tools.synthetic_clouds.render.markers import SOURCE_FINGERPRINT_PREFIX

router = APIRouter()

_TOKEN_TTL_SECONDS = 3600

# Simulator-local signing key. It is not a credential: nothing verifies the
# signature (MSAL only reads the response fields), and every token this endpoint
# issues is prefixed/marked synthetic below.
_DEV_SIGNING_KEY = b"synthetic-clouds/azure-sim/dev-jwt-key"

_TENANT_AUTHORITY = "https://login.microsoftonline.com"


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _encode_jwt(*, tenant: str, client_id: str, scope: str) -> str:
    """Return a JWT-shaped bearer carrying standard claims and a synthetic marker."""
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT", "kid": "synth-azure-sim"}
    payload = {
        "aud": scope or "https://management.azure.com",
        "iss": f"{_TENANT_AUTHORITY}/{tenant}/v2.0",
        "iat": now,
        "nbf": now,
        "exp": now + _TOKEN_TTL_SECONDS,
        "appid": client_id,
        "azp": client_id,
        "tid": tenant,
        "sub": client_id or "synthetic-service-principal",
        "jti": f"{SOURCE_FINGERPRINT_PREFIX}{uuid.uuid4()}",
        "roles": ["synthetic.reader"],
        "x_synthetic": True,
    }
    signing_input = f"{_b64url(json.dumps(header, separators=(',', ':')).encode())}." + _b64url(
        json.dumps(payload, separators=(",", ":")).encode()
    )
    signature = hmac.new(_DEV_SIGNING_KEY, signing_input.encode("ascii"), hashlib.sha256).digest()
    return f"{signing_input}.{_b64url(signature)}"


def _openid_configuration(tenant: str) -> dict[str, Any]:
    authority = f"{_TENANT_AUTHORITY}/{tenant}"
    return {
        "token_endpoint": f"{authority}/oauth2/v2.0/token",
        "authorization_endpoint": f"{authority}/oauth2/v2.0/authorize",
        "device_authorization_endpoint": f"{authority}/oauth2/v2.0/devicecode",
        "issuer": f"{authority}/v2.0",
        "token_endpoint_auth_methods_supported": [
            "client_secret_post",
            "client_secret_basic",
            "private_key_jwt",
        ],
        "response_types_supported": ["code", "id_token", "code id_token", "token id_token"],
        "response_modes_supported": ["query", "fragment", "form_post"],
        "grant_types_supported": [
            "authorization_code",
            "client_credentials",
            "refresh_token",
        ],
        "subject_types_supported": ["pairwise"],
        "scopes_supported": ["openid", "profile", "email", "offline_access"],
        "id_token_signing_alg_values_supported": ["RS256"],
        "token_endpoint_auth_signing_alg_values_supported": ["RS256"],
        "claims_supported": ["aud", "iss", "iat", "exp", "sub", "tid", "appid"],
        "tenant_region_scope": "NA",
        "cloud_instance_name": "microsoftonline.com",
        "cloud_graph_host_name": "graph.windows.net",
        "msgraph_host": "graph.microsoft.com",
        "rbac_url": "https://pas.windows.net",
    }


@router.get("/{tenant}/v2.0/.well-known/openid-configuration")
async def openid_configuration(tenant: str) -> dict[str, Any]:
    """Serve the tenant OIDC discovery document MSAL fetches before a token call."""
    return _openid_configuration(tenant)


@router.get("/common/discovery/instance")
async def instance_discovery(request: Request) -> dict[str, Any]:
    """Serve the instance-discovery document (MSAL skips it for a known host).

    Kept because a deployment that validates an unknown authority path still
    calls it; the payload is the documented ``tenant_discovery_endpoint`` shape.
    """
    tenant = "common"
    endpoint = f"{_TENANT_AUTHORITY}/{tenant}/v2.0/.well-known/openid-configuration"
    authorization_endpoint = request.query_params.get("authorization_endpoint", "")
    return {
        "tenant_discovery_endpoint": endpoint,
        "api-version": request.query_params.get("api-version", "1.1"),
        "metadata": [
            {
                "preferred_network": "login.microsoftonline.com",
                "preferred_cache": "login.windows.net",
                "aliases": [
                    "login.microsoftonline.com",
                    "login.windows.net",
                    "login.microsoft.com",
                    "sts.windows.net",
                ],
                "authorization_endpoint": authorization_endpoint,
            }
        ],
    }


@router.post("/{tenant}/oauth2/v2.0/token")
async def issue_token(tenant: str, request: Request) -> dict[str, object]:
    """Issue the bearer MSAL asks for; a real client secret is never validated."""
    # Parsed from the raw body on purpose: ``request.form()`` needs
    # python-multipart, which this image does not install, and the token request
    # is always ``application/x-www-form-urlencoded``.
    raw = (await request.body()).decode("utf-8", "replace")
    form = parse_qs(raw, keep_blank_values=True)
    client_id = (form.get("client_id") or [""])[0]
    scope = (form.get("scope") or [""])[0]
    access_token = _encode_jwt(tenant=tenant, client_id=client_id, scope=scope)
    return {
        "token_type": "Bearer",
        "expires_in": _TOKEN_TTL_SECONDS,
        "ext_expires_in": _TOKEN_TTL_SECONDS,
        "scope": scope or "https://management.azure.com/.default",
        "access_token": access_token,
        # Provenance marker so the token is unmistakably synthetic (§9).
        "synthetic": True,
    }
