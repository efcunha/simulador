"""Fake OAuth2 token endpoint (design §5.1, §9).

``POST .../{tenant}/oauth2/v2.0/token`` always issues a SYNTHETIC bearer token and
NEVER validates a real client secret — this is a simulator, so Phase 4's
``ClientSecretCredential(..., authority=<sim>)`` path can obtain a token without a
real Azure AD. The issued token is a plainly-synthetic opaque string carrying the
``synth:`` marker (§9) so no reader mistakes it for a real credential.

The token is NOT a secret: it grants nothing, is accepted by any router, and
embeds a visible synthetic marker. It exists only to shape the SDK's auth round-
trip.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from tools.synthetic_clouds.render.markers import SOURCE_FINGERPRINT_PREFIX

router = APIRouter()

# Synthetic bearer value: a plainly-fake, non-secret marker string. It is prefixed
# with ``synth:`` so it reads as synthetic in any log and grants no real access.
_SYNTHETIC_BEARER = f"{SOURCE_FINGERPRINT_PREFIX}azure-sim-fake-bearer"
_TOKEN_TTL_SECONDS = 3600


@router.post("/{tenant}/oauth2/v2.0/token")
async def issue_token(tenant: str, request: Request) -> dict[str, object]:
    """Issue a synthetic bearer token (never validates a real secret, §9)."""
    return {
        "token_type": "Bearer",
        "expires_in": _TOKEN_TTL_SECONDS,
        "ext_expires_in": _TOKEN_TTL_SECONDS,
        "access_token": _SYNTHETIC_BEARER,
        # Provenance marker so the token is unmistakably synthetic (§9).
        "synthetic": True,
    }
