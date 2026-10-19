"""Microsoft Graph router: users / authentication methods (MFA) / roleAssignments (design §5.1, §8 C09).

Serves a NATIVE identity projection (users, their MFA registration state, and role
assignments) derived deterministically from the estate's identity-related
findings. MFA gaps are the C09 input; FinOps computes any identity-risk
verdict from these (P1).

Identities are fictional and live under the ``contoso.example`` domain (markers,
§9). The user set is derived from identity/IAM findings so the MFA-gap signal is
coherent with the Defender findings surface.

TODO-verificar §11.8: the exact Graph ``value[]`` envelope keys, the
``isMfaRegistered`` field name, and the ``$top``/``@odata.nextLink`` paging field
are NOT offline-verifiable; emitted official-shaped and flagged.
"""

from __future__ import annotations

import hashlib
from typing import Any

from fastapi import APIRouter, Request
from tools.synthetic_clouds.render.markers import FICTIONAL_DOMAIN

from azure_sim.api.common import get_estate, require_api_version, value_page

router = APIRouter()

# TODO-verificar §11.8: official Microsoft Graph api-version values (v1.0 | beta).
_API_VERSIONS: frozenset[str] = frozenset({"v1.0", "beta"})

# IAM-related native finding categories that seed the identity surface.
_IDENTITY_CATEGORIES: frozenset[str] = frozenset({"IAM", "IDENTITY"})


def _user_id(seed: int, scope_id: str) -> str:
    """Deterministic synthetic user id from (seed, scope) — no wall-clock."""
    digest = hashlib.sha256(f"{seed}:user:{scope_id}".encode()).hexdigest()
    return digest[:16]


def _identity_scopes(estate: Any) -> list[str]:
    """Return the distinct scopes that carry an identity/IAM finding (deterministic)."""
    scopes = {
        finding.resource_uuid
        for finding in estate.findings
        if finding.category.upper() in _IDENTITY_CATEGORIES
    }
    return sorted(scopes)


def _users(estate: Any) -> list[dict[str, Any]]:
    """Project native users with their MFA registration state (C09 input)."""
    flagged = set(_identity_scopes(estate))
    rows: list[dict[str, Any]] = []
    # One synthetic user per subscription scope present in the inventory.
    scopes = sorted({r.parent_scope_id for r in estate.resources})
    for scope in scopes:
        uid = _user_id(estate.seed, scope)
        rows.append(
            {
                "id": uid,
                "userPrincipalName": f"user-{uid}@{FICTIONAL_DOMAIN}",
                # MFA gap is the native input: a scope with an IAM finding is unregistered.
                "isMfaRegistered": scope not in flagged,
            }
        )
    return rows


def _role_assignments(estate: Any) -> list[dict[str, Any]]:
    """Project native role assignments (one per synthetic user, deterministic)."""
    rows: list[dict[str, Any]] = []
    for user in _users(estate):
        rows.append(
            {
                "id": f"ra-{user['id']}",
                "principalId": user["id"],
                "roleDefinitionId": "Reader",
            }
        )
    return rows


@router.get("/users")
async def users(request: Request) -> dict[str, Any]:
    """Return native Graph ``users`` (fictional, contoso.example)."""
    require_api_version(request, _API_VERSIONS)
    return value_page(request, _users(get_estate(request)))


@router.get("/users/authentication/methods")
async def authentication_methods(request: Request) -> dict[str, Any]:
    """Return per-user MFA registration state (the C09 MFA-gap input)."""
    require_api_version(request, _API_VERSIONS)
    estate = get_estate(request)
    rows = [
        {"userId": user["id"], "isMfaRegistered": user["isMfaRegistered"]}
        for user in _users(estate)
    ]
    return value_page(request, rows)


@router.get("/roleAssignments")
async def role_assignments(request: Request) -> dict[str, Any]:
    """Return native role assignments (one per synthetic user)."""
    require_api_version(request, _API_VERSIONS)
    return value_page(request, _role_assignments(get_estate(request)))
