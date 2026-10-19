"""GCP-style error envelopes for the gcp-sim service (design sec. 5.4).

Every failure returns the official GCP error shape ``{"error": {"code": ...,
"message": ..., "status": ...}}`` -- never a bare FastAPI 422 -- so a client that
expects google.api_core error parsing behaves as against real GCP.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

# Canonical gRPC/HTTP status strings (subset used by this sim).
_STATUS_BY_CODE = {
    400: "INVALID_ARGUMENT",
    401: "UNAUTHENTICATED",
    403: "PERMISSION_DENIED",
    404: "NOT_FOUND",
    500: "INTERNAL",
}


class GcpError(Exception):
    """A GCP-shaped error carrying an HTTP status code and message."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def error_body(code: int, message: str) -> dict[str, Any]:
    """Return the official GCP error envelope dict for ``code``/``message``."""
    return {
        "error": {
            "code": code,
            "message": message,
            "status": _STATUS_BY_CODE.get(code, "UNKNOWN"),
        }
    }


def gcp_error_response(code: int, message: str) -> JSONResponse:
    """Return a ``JSONResponse`` carrying the GCP error envelope."""
    return JSONResponse(status_code=code, content=error_body(code, message))


async def gcp_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    """FastAPI exception handler mapping ``GcpError`` to the GCP envelope."""
    if isinstance(exc, GcpError):
        return gcp_error_response(exc.code, exc.message)
    return gcp_error_response(500, "internal error")  # pragma: no cover - defensive
