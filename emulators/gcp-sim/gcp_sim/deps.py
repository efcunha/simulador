"""Shared request validation + auth helpers for gcp-sim routers (design sec. 5.4).

Read-only, dev-local, but still validates each request: bearer presence (401 on
missing/invalid), scope/parent prefix (400 on mismatch), pageSize clamp to
[1, 1000]. All failures raise ``GcpError`` which the app maps to the GCP envelope.
"""

from __future__ import annotations

from fastapi import Request

from gcp_sim.errors import GcpError

_PAGE_SIZE_MIN = 1
_PAGE_SIZE_MAX = 1000


def require_bearer(request: Request) -> str:
    """Return the bearer token; raise 401 if missing/invalid (design sec. 5.4).

    The OAuth2 stub issues any token for the fictional SA; this only checks that a
    ``Authorization: Bearer <token>`` header is present and non-empty.
    """
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise GcpError(401, "missing or invalid bearer token")
    token = header[len("bearer ") :].strip()
    if not token:
        raise GcpError(401, "missing or invalid bearer token")
    return token


def validate_prefix(value: str, allowed_prefixes: tuple[str, ...], field: str) -> str:
    """Validate a scope/parent/name path param prefix; raise 400 on mismatch."""
    if not value:
        raise GcpError(400, f"{field} is required")
    if not any(value.startswith(p) for p in allowed_prefixes):
        raise GcpError(400, f"{field} must start with one of {', '.join(allowed_prefixes)}")
    return value


def clamp_page_size(page_size: int | None) -> int:
    """Clamp ``pageSize`` to [1, 1000] (out-of-range clamps, not errors; sec. 5.4)."""
    if page_size is None:
        return _PAGE_SIZE_MAX
    return max(_PAGE_SIZE_MIN, min(_PAGE_SIZE_MAX, page_size))
