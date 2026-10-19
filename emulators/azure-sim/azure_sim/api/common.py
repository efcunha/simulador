"""Shared API primitives: error envelope, api-version validation, estate access (design §5.3/§5.4).

Every router reuses these so the Azure ``{error:{code,message}}`` envelope and the
``api-version`` gate are declared once. The estate is built ONCE at app-create
time and shared read-only by all routers (it is frozen and gated), so a request
never rebuilds it.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request

# Azure error ``code`` strings. TODO-verificar §11.7: exact per-service ``code``
# vocabulary (``InvalidApiVersion`` etc.) is NOT offline-verifiable; emitted
# official-shaped and flagged.
CODE_INVALID_API_VERSION = "InvalidApiVersion"
CODE_INVALID_REQUEST = "BadRequest"
CODE_MISSING_TOKEN = "AuthenticationFailed"  # noqa: S105 - an Azure error code, not a credential
CODE_NOT_FOUND = "NotFound"


class AzureApiError(HTTPException):
    """An HTTPException carrying an Azure error ``code`` for the envelope handler."""

    def __init__(self, status_code: int, *, code: str, message: str) -> None:
        super().__init__(status_code=status_code, detail={"code": code, "message": message})
        self.azure_code = code
        self.azure_message = message


def error_envelope(code: str, message: str) -> dict[str, Any]:
    """Return the Azure ``{error:{code,message}}`` envelope body (§5.3)."""
    return {"error": {"code": code, "message": message}}


def require_api_version(request: Request, allowed: frozenset[str]) -> str:
    """Return the request's ``api-version`` or raise a 400 Azure envelope (§5.4).

    The ``api-version`` must be present and in the router's allowed set. TODO-
    verificar §11.6-§11.11: the allowed version STRINGS default to the latest
    known value per service and are flagged where unverifiable.
    """
    version = request.query_params.get("api-version")
    if version is None or version not in allowed:
        raise AzureApiError(
            400,
            code=CODE_INVALID_API_VERSION,
            message=(
                f"The api-version {version!r} is not supported; "
                f"expected one of {sorted(allowed)}."
            ),
        )
    return version


def get_estate(request: Request) -> Any:
    """Return the shared, pre-built ``CanonicalEstate`` from app state."""
    return request.app.state.estate


def get_settings(request: Request) -> Any:
    """Return the shared validated ``Settings`` from app state."""
    return request.app.state.settings


def value_page(
    request: Request,
    rows: list[dict[str, Any]],
    *,
    token_field: str = "nextLink",  # noqa: S107 - a paging field name, not a credential
) -> dict[str, Any]:
    """Return the common ``{value, nextLink}`` list envelope for a page of rows.

    Centralizes the ``{value, nextLink}`` shape shared by Defender, Advisor,
    Policy Insights, Graph, and Reservations list endpoints. ``token_field`` is
    the continuation query-param name (default ``nextLink``). The import is local
    to avoid a circular import between ``common`` and ``paging``.
    """
    from azure_sim.api.paging import page_rows_and_link

    settings = get_settings(request)
    page_rows, next_link = page_rows_and_link(
        list(rows),
        page_size=settings.api_page_size,
        request_url=str(request.url),
        token_field=token_field,
    )
    return {"value": page_rows, "nextLink": next_link}
