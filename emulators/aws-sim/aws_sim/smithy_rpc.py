"""The AWS RPC-v2 wire (CloudWatch) — the third wire beside Query and JSON-1.1.

CloudWatch is the one AWS service whose botocore model declares
``metadata.protocol == "smithy-rpc-v2-cbor"``, a binary protocol, so neither the XML
responder nor the JSON-1.1 responder can serve it by accident. It is not, however, a
blocker, and it is not CBOR on this wire either — both facts were measured against the
installed botocore rather than read off the model, and both are load-bearing:

**The framing the client actually sends is JSON-1.0.** The model declares a *list*:
``metadata.protocols == ["smithy-rpc-v2-cbor", "json", "query"]``, and botocore picks one
with ``ServiceModel.resolved_protocol``, which walks ``PRIORITY_ORDERED_SUPPORTED_PROTOCOLS
= ("json", "rest-json", "rest-xml", "smithy-rpc-v2-cbor", "query", "ec2")`` and returns the
**first entry the service also lists**. ``json`` precedes ``smithy-rpc-v2-cbor`` there, so
CloudWatch resolves to ``json``. A live capture of a real ``boto3.client("cloudwatch")``
call confirms the outcome::

    POST /  (endpoint root)
    Content-Type: application/x-amz-json-1.0
    X-Amz-Target: GraniteServiceVersion20100801.ListMetrics
    x-amzn-query-mode: true
    body: {"Namespace": "AWS/EC2"}

So the transport matches the Query and JSON services already served here — one endpoint,
one POST — and :data:`PROTOCOL_JSON` is the framer FinOps calls need.
``x-amzn-query-mode`` is set by botocore because the model carries the
``awsQueryCompatible`` trait (``ServiceModel.is_query_compatible``); it is informational for
this emulator, since the error envelope below already yields the right code either way.

**The declared protocol is CBOR, and it is still served.** ``resolved_protocol`` is a
client-side preference, not a property of the service: a client that exercises the
model's *first* declared protocol speaks CBOR, and then it POSTs to a different path.
``BaseRpcV2Serializer.serialize_to_request`` overrides the operation's ``http.requestUri``
of ``/`` with ``/service/<targetPrefix>/operation/<Operation>``, so the CBOR request does
**not** reach the endpoint root — which is why :mod:`aws_sim.api.app` registers that path
too rather than sniffing a header on ``/``. It carries
``smithy-protocol: rpc-v2-cbor`` and ``Accept: application/cbor``.

Both framings are rendered here because both are the same protocol family over the same
target prefix and the same dispatch; only the codec and the path differ.

Two encoding details are botocore's, not choices:

* Timestamps. The JSON framing emits epoch seconds, which
  ``botocore.parsers.parse_timestamp`` reads as an epoch value. The CBOR framing must emit
  CBOR tag 1 over epoch **seconds**: ``BaseCBORParser._parse_tag`` accepts tag 1 and raises
  ``ResponseParserError`` for every other tag, and its ``_default_handle`` passes a
  timestamp-valued shape through untouched — so the tag is the only thing that turns a
  number into a ``datetime``, and a self-describe tag (55799) would break the parse. The
  unit is seconds: see :data:`_CBOR_EPOCH_TAG` for the bytes that settle it.
* Errors. Both framings use the same envelope, ``{"__type": "<prefix>#<Code>",
  "message": …}``; ``_do_error_parse`` on each parser strips everything before the last
  ``#``, which is what turns a failure into a real ``ClientError`` carrying the code
  instead of an opaque transport error.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import botocore.session

#: The header the RPC-v2 serializer sets on a CBOR request.
SMITHY_PROTOCOL_HEADER = "smithy-protocol"

#: Its value when the body is CBOR — the marker that selects this framing.
SMITHY_PROTOCOL_CBOR = "rpc-v2-cbor"

#: ``ServiceModel.resolved_protocol`` as this emulator serves it (JSON-1.0).
PROTOCOL_JSON = "json"

#: The protocol the CloudWatch model declares first.
PROTOCOL_CBOR = "smithy-rpc-v2-cbor"

#: The model's ``jsonVersion`` is 1.0, so this is the type the client sent.
CONTENT_TYPE_JSON = "application/x-amz-json-1.0"

CONTENT_TYPE_CBOR = "application/cbor"

#: CBOR major type 6, tag 1. The only tag ``botocore.parsers.BaseCBORParser`` accepts, and
#: therefore the only way a CBOR response can carry a timestamp — it raises on any other
#: tag, so a self-describe tag (55799) breaks the parse outright.
#:
#: The payload is **epoch seconds**, and that is measured rather than assumed. The
#: parser's own comment reads "Epoch-based date/time in milliseconds", but its code hands
#: the value to ``parse_timestamp``, which reads it as seconds — and the serializer writes
#: seconds too: a request for 2026-01-01T00:00Z carries the bytes ``c1 1a 69 55 b9 00``,
#: i.e. tag 1 over the integer 1767225600. Encoding milliseconds there would make
#: ``parse_timestamp`` raise ``OverflowError`` on its own response.
_CBOR_EPOCH_TAG = 1


class SmithyRpcError(Exception):
    """An error that renders as the RPC-v2 error envelope."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def _cbor2() -> Any:
    """Import ``cbor2`` on demand, the only module this package needs for CBOR.

    Deferred rather than imported at module scope: the JSON-1.0 framing is what the
    installed client sends, so a deployment that serves only that framing does not need
    the dependency to be importable, and a deployment that lacks it gets a clear protocol
    error on a CBOR request instead of an unimportable module on every request.
    """
    try:
        import cbor2
    except ImportError as exc:
        raise SmithyRpcError(
            "InternalFailure",
            "The RPC-v2 CBOR framing requires the 'cbor2' package.",
            500,
        ) from exc
    return cbor2


def _epoch_seconds(value: datetime) -> float:
    return value.timestamp()


def _as_json_value(value: Any) -> Any:
    """Rewrite a result for the JSON framing: timestamps become epoch seconds."""
    if isinstance(value, datetime):
        return _epoch_seconds(value)
    if isinstance(value, dict):
        return {key: _as_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_as_json_value(item) for item in value]
    return value


def _as_cbor_value(value: Any, cbor: Any) -> Any:
    """Rewrite a result for the CBOR framing: timestamps become tag-1 epoch seconds."""
    if isinstance(value, datetime):
        return cbor.CBORTag(_CBOR_EPOCH_TAG, int(_epoch_seconds(value)))
    if isinstance(value, dict):
        return {key: _as_cbor_value(item, cbor) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_as_cbor_value(item, cbor) for item in value]
    return value


class SmithyRpcWire:
    """One framing of the RPC-v2 wire for one service, keyed by its target prefix.

    ``target_prefix`` and :meth:`operation_for_target` are read from the service model and
    are the same in both framings; only :meth:`render_result` / :meth:`render_error` /
    :meth:`parse_request` and :attr:`content_type` depend on ``protocol``.
    """

    def __init__(self, service: str, protocol: str = PROTOCOL_JSON) -> None:
        if protocol not in (PROTOCOL_JSON, PROTOCOL_CBOR):
            raise ValueError(f"Unsupported RPC-v2 framing: {protocol!r}")
        self.service = service
        self.protocol = protocol
        self._model: Any = None

    def service_model(self) -> Any:
        """Return this service's botocore model, loaded once and cached."""
        if self._model is None:
            self._model = botocore.session.get_session().get_service_model(self.service)
        return self._model

    @property
    def target_prefix(self) -> str:
        """The target prefix the client sends (from the model, not hard-coded)."""
        return str(self.service_model().metadata.get("targetPrefix", ""))

    @property
    def content_type(self) -> str:
        """The ``Content-Type`` a response in this framing carries."""
        return CONTENT_TYPE_CBOR if self.protocol == PROTOCOL_CBOR else CONTENT_TYPE_JSON

    def operation_for_target(self, target: str | None) -> str | None:
        """Return the operation named by a ``<Prefix>.<Operation>`` target, or ``None``."""
        prefix, _, operation = (target or "").partition(".")
        if prefix != self.target_prefix or not operation:
            return None
        return operation

    def parse_request(self, raw: bytes) -> dict[str, Any]:
        """Decode a request body in this framing. An empty body is an empty request."""
        if not raw:
            return {}
        if self.protocol == PROTOCOL_CBOR:
            cbor = _cbor2()
            parsed = cbor.loads(raw)
            if not isinstance(parsed, dict):
                raise SmithyRpcError(
                    "SerializationException",
                    "The CBOR request body must be a map.",
                )
            return parsed
        parsed_json: Any = json.loads(raw)
        if not isinstance(parsed_json, dict):
            raise SmithyRpcError("SerializationException", "The request body must be a map.")
        return parsed_json

    def render_result(self, result: dict[str, Any]) -> bytes:
        """Serialize an operation result as this framing's body (no envelope)."""
        if self.protocol == PROTOCOL_CBOR:
            cbor = _cbor2()
            return bytes(cbor.dumps(_as_cbor_value(result, cbor)))
        return json.dumps(_as_json_value(result), separators=(",", ":"), default=str).encode("utf-8")

    def render_error(self, code: str, message: str) -> bytes:
        """Serialize the RPC-v2 error envelope for this framing."""
        envelope = {"__type": f"{self.target_prefix}#{code}", "message": message}
        if self.protocol == PROTOCOL_CBOR:
            cbor = _cbor2()
            return bytes(cbor.dumps(envelope))
        return json.dumps(envelope, separators=(",", ":")).encode("utf-8")


def is_cbor_request(headers: Any) -> bool:
    """Whether ``headers`` mark an RPC-v2 CBOR request.

    The serializer sets ``smithy-protocol: rpc-v2-cbor``; the ``Accept``/``Content-Type``
    pair is checked as a fallback so a client that omits the marker is still served.
    """
    protocol = str(headers.get(SMITHY_PROTOCOL_HEADER) or "").strip().lower()
    if protocol:
        return protocol == SMITHY_PROTOCOL_CBOR
    accept = str(headers.get("accept") or "").lower()
    return CONTENT_TYPE_CBOR in accept
