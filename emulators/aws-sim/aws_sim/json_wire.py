"""AWS JSON-1.1 protocol wire (Cost Explorer, Organizations, …).

These services do not speak the Query protocol: the client POSTs a JSON body to ``/``
with an ``X-Amz-Target: <TargetPrefix>.<Operation>`` header and reads a JSON response.
The target prefix and api version are read from the service model
(``metadata.targetPrefix`` / ``metadata.apiVersion``) rather than hard-coded, so the
dispatcher cannot drift from what the client sends.

Error envelopes follow the JSON-1.1 shape ``{"__type": "<Prefix>#<Code>", "message":
"…"}``. botocore's JSON error parser takes the code after the last ``#``, which is what
turns an emulator failure into a real ``ClientError`` with a readable code instead of an
opaque transport error.
"""

from __future__ import annotations

import json
from typing import Any

import botocore.session

CONTENT_TYPE = "application/x-amz-json-1.1"


class JsonApiError(Exception):
    """An error that renders as the JSON-1.1 error envelope."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class JsonWire:
    """The JSON-1.1 renderer for one service, keyed by its ``X-Amz-Target`` prefix."""

    def __init__(self, service: str) -> None:
        self.service = service
        self._model: Any = None

    def service_model(self) -> Any:
        """Return this service's botocore model, loaded once and cached."""
        if self._model is None:
            self._model = botocore.session.get_session().get_service_model(self.service)
        return self._model

    @property
    def target_prefix(self) -> str:
        """The ``X-Amz-Target`` prefix the client sends (from the model, not hard-coded)."""
        return str(self.service_model().metadata.get("targetPrefix", ""))

    @property
    def content_type(self) -> str:
        """The ``Content-Type`` a response from this wire carries."""
        return CONTENT_TYPE

    def api_version(self) -> str:
        """The api version declared by the model (informational for JSON-1.1)."""
        return str(self.service_model().metadata.get("apiVersion", ""))

    def operation_for_target(self, target: str | None) -> str | None:
        """Return the operation named by an ``X-Amz-Target`` header, or ``None``."""
        prefix, _, operation = (target or "").partition(".")
        if prefix != self.target_prefix or not operation:
            return None
        return operation

    def render_result(self, result: dict[str, Any]) -> str:
        """Serialize an operation result as the JSON body (no envelope)."""
        return json.dumps(result, separators=(",", ":"), default=str)

    def render_error(self, code: str, message: str) -> str:
        """Serialize the JSON-1.1 error envelope."""
        return json.dumps(
            {"__type": f"{self.target_prefix}#{code}", "message": message},
            separators=(",", ":"),
        )
