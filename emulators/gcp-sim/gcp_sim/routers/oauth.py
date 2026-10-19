"""OAuth2 token stub (design sec. 5.1).

Dev stub: accepts any ``assertion``/``client_assertion`` from the fictional
service account and returns a bearer token. Documented as a dev stub; it mints no
real credential and validates no real signature.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

router = APIRouter(tags=["oauth"])

# A fixed, obviously-synthetic opaque token. NOT a credential: the sim accepts any
# bearer and this value grants nothing outside the dev-local sim.
_SYNTH_ACCESS_TOKEN = "synthetic-access-token"  # noqa: S105 - dev stub, not a secret


def _token_body() -> dict[str, Any]:
    return {
        "access_token": _SYNTH_ACCESS_TOKEN,
        "token_type": "Bearer",
        "expires_in": 3600,
    }


@router.post("/token")
async def token() -> dict[str, Any]:
    """OAuth2 token endpoint (``POST /token``) -- returns a synthetic bearer."""
    return _token_body()


@router.post("/oauth2/v4/token")
async def oauth2_v4_token() -> dict[str, Any]:
    """OAuth2 token endpoint (``POST /oauth2/v4/token``) -- returns a synthetic bearer."""
    return _token_body()
