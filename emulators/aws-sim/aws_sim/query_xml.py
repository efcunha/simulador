"""Query-protocol XML, generated from botocore's own service model (design sec. 22.3).

The Query protocol is form-encoded ``Action=...`` answered with XML, and several AWS
services speak it (CloudFormation, STS, …). Two traps follow, and both are silent rather
than loud:

1. Every list in these operations is **non-flattened**, so Query XML must wrap each
   element in ``<member>``. Emitting a flattened list parses to an empty list with no
   error at all.
2. A member typed **``string``** in the model holds its own serialized document (e.g.
   CloudFormation's ``ExpectedProperties``) — an emulator emitting an object is parsed as
   garbage.

Hand-writing the XML per operation is where this component would rot, so the renderer is
**generic and shape-driven**: it walks the output shape botocore exposes for the same
operation the client will call, which makes the envelope a function of the model rather
than of care. One :class:`QueryWire` instance per service carries that service's model
and namespace; the module-level functions are the CloudFormation instance, kept so the
first slice's callers and tests are unchanged.

The cost is a runtime dependency on ``botocore`` (its service models, not its
credentials); the benefit is that correctness is checkable offline — the tests parse this
output with ``botocore.parsers``, the same parser the real client uses.

**EC2 does not speak Query.** botocore names its protocol ``ec2``: form-encoded in, XML
out, but not the same XML — and again the traps are silent rather than loud:

3. The members sit **directly** under ``<{Operation}Response>``; there is no
   ``<{Operation}Result>`` wrapper. A result rendered by the Query envelope parses to an
   **empty dict** with no error, because the parser looks for the operation's members among
   the response element's own children.
4. Every tag is the model's own ``serialization.name``: ``VpcId`` arrives as ``<vpcId>``,
   ``Reservations`` as ``<reservationSet>``. A tag the parser does not look up is dropped
   without a word, so a member written under its Python name is a member the caller never
   sees.
5. The request id is a lowercase ``<requestId>`` child of the response element, not the
   Query envelope's ``<ResponseMetadata><RequestId>``.

So :class:`EC2Wire` is a subclass rather than a flag on :class:`QueryWire`: the envelope
differs, and subclassing makes that difference impossible to forget at a call site. The one
thing that is a parameter is the member naming, because that is a property of the service
model rather than of the protocol, and only ``render_result`` needs to ask for it.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from xml.sax.saxutils import escape

import botocore.session

#: The canonical AWS wire timestamp. botocore parses it without a dateutil fallback.
_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def _text(value: Any, shape: Any) -> str:
    """Render a scalar member's text, using the shape's own type."""
    if shape.type_name == "timestamp" and isinstance(value, datetime):
        return value.astimezone(UTC).strftime(_TIMESTAMP_FORMAT)
    if shape.type_name == "boolean":
        return "true" if value else "false"
    return escape(str(value))


def _member_tag(member: str, shape: Any, *, model_names: bool) -> str:
    """The XML tag one structure member is written under.

    ``model_names`` is what the ``ec2`` protocol needs: it renames members at the wire
    level (``VpcId`` -> ``vpcId``, ``Reservations`` -> ``reservationSet``) and its parser
    looks the member up under that name only, so a member written under its Python name is
    silently absent from the parsed result. The Query services keep the Python name, which
    is the name their own models serialize under.
    """
    if model_names:
        return str(shape.serialization.get("name") or member)
    return member


def _write_members(out: list[str], shape: Any, value: Mapping[str, Any], *, model_names: bool) -> None:
    """Append every member of ``shape`` that ``value`` carries, at the current level.

    This is the body without the wrapper, which is what makes it usable twice: the Query
    protocol wraps it in ``<{Operation}Result>``, and the ``ec2`` protocol has no wrapper
    to put it in and writes it straight into the response element.
    """
    for key, member_shape in shape.members.items():
        if key not in value:
            continue
        tag = _member_tag(key, member_shape, model_names=model_names)
        _write(out, tag, member_shape, value[key], model_names=model_names)


def _write(out: list[str], name: str, shape: Any, value: Any, *, model_names: bool = False) -> None:
    """Append ``value`` as ``<name>`` according to ``shape``."""
    if value is None:
        return

    kind = shape.type_name
    if kind == "list":
        member = shape.member
        if shape.serialization.get("flattened"):
            # Flattened lists put the members straight into the parent element.
            for item in value:
                _write(out, member.serialization.get("name") or member.name, member, item, model_names=model_names)
            return
        # A non-flattened list element's tag is irrelevant to both parsers (each walks the
        # list element's children), so the model's own name — ``item`` for EC2, ``member``
        # for Query — is used for fidelity rather than for correctness.
        item_tag = str(member.serialization.get("name") or "member") if model_names else "member"
        out.append(f"<{name}>")
        for item in value:
            _write(out, item_tag, member, item, model_names=model_names)
        out.append(f"</{name}>")
        return

    if kind == "structure":
        out.append(f"<{name}>")
        _write_members(out, shape, value, model_names=model_names)
        out.append(f"</{name}>")
        return

    out.append(f"<{name}>{_text(value, shape)}</{name}>")


class QueryWire:
    """The Query-protocol renderer for one service.

    The service model is loaded once, lazily, so importing this module stays cheap and a
    service whose model is absent fails at the first request rather than at import.
    """

    def __init__(self, service: str, namespace: str) -> None:
        self.service = service
        self.namespace = namespace
        self._model: Any = None

    def service_model(self) -> Any:
        """Return this service's botocore model, loaded once and cached."""
        if self._model is None:
            self._model = botocore.session.get_session().get_service_model(self.service)
        return self._model

    def api_version(self) -> str:
        """The api version the client sends and this service must accept."""
        return str(self.service_model().api_version)

    def render_result(self, operation: str, result: Mapping[str, Any], request_id: str) -> str:
        """Render an operation result as the Query-protocol XML envelope."""
        shape = self.service_model().operation_model(operation).output_shape
        body: list[str] = []
        if shape is not None:
            _write(body, f"{operation}Result", shape, dict(result))
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            f'<{operation}Response xmlns="{self.namespace}">'
            + "".join(body)
            + f"<ResponseMetadata><RequestId>{escape(request_id)}</RequestId></ResponseMetadata>"
            + f"</{operation}Response>"
        )

    def render_error(self, code: str, message: str, request_id: str) -> str:
        """Render the Query-protocol error envelope.

        Shape taken from botocore's query error parser (``<ErrorResponse><Error>…``),
        which is what turns an emulator failure into a real ``ClientError`` with a
        readable code instead of an opaque transport error.
        """
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            f'<ErrorResponse xmlns="{self.namespace}">'
            f"<Error><Type>Sender</Type><Code>{escape(code)}</Code>"
            f"<Message>{escape(message)}</Message></Error>"
            f"<RequestId>{escape(request_id)}</RequestId>"
            "</ErrorResponse>"
        )


class EC2Wire(QueryWire):
    """The ``ec2`` protocol renderer: the same input, a different response envelope.

    Subclassed from :class:`QueryWire` because everything except the envelope is shared —
    the model lookup, the api version, the shape-driven member writer, and the error
    envelope, which the ``ec2`` parser reads as-is: it finds ``<ErrorResponse><Error>``
    through the Query error path and lifts ``<RequestId>`` into ``ResponseMetadata`` itself
    (``api/app.py`` therefore needs no EC2-specific error branch). What it cannot share is
    :meth:`QueryWire.render_result`, for the three reasons in the module docstring.
    """

    def render_result(self, operation: str, result: Mapping[str, Any], request_id: str) -> str:
        """Render an operation result as the ec2-protocol XML envelope.

        No ``{operation}Result`` wrapper, members named from the model, and the request id
        as a lowercase ``<requestId>`` child of the response element.
        """
        shape = self.service_model().operation_model(operation).output_shape
        body: list[str] = []
        if shape is not None:
            _write_members(body, shape, dict(result), model_names=True)
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            f'<{operation}Response xmlns="{self.namespace}">'
            + "".join(body)
            + f"<requestId>{escape(request_id)}</requestId>"
            + f"</{operation}Response>"
        )


CLOUDFORMATION = QueryWire("cloudformation", "http://cloudformation.amazonaws.com/doc/2010-05-15/")
STS = QueryWire("sts", "https://sts.amazonaws.com/doc/2011-06-15/")
# The inventory and security slices speak this same protocol, so they are instances of
# the same renderer rather than a second implementation of it.
RDS = QueryWire("rds", "http://rds.amazonaws.com/doc/2014-10-31/")
ELBV2 = QueryWire("elbv2", "http://elasticloadbalancing.amazonaws.com/doc/2015-12-01/")
IAM = QueryWire("iam", "http://iam.amazonaws.com/doc/2010-05-08/")
EC2 = EC2Wire("ec2", "http://ec2.amazonaws.com/doc/2016-11-15/")

SERVICE = CLOUDFORMATION.service
NAMESPACE = CLOUDFORMATION.namespace


# ── CloudFormation facade (the first slice's module-level API, unchanged) ─────


def service_model() -> Any:
    """Return the CloudFormation service model, loaded once."""
    return CLOUDFORMATION.service_model()


def api_version() -> str:
    """The api version the CloudFormation client sends and this service must accept."""
    return CLOUDFORMATION.api_version()


def render_result(operation: str, result: Mapping[str, Any], request_id: str) -> str:
    """Render a CloudFormation operation result as the Query-protocol XML envelope."""
    return CLOUDFORMATION.render_result(operation, result, request_id)


def render_error(code: str, message: str, request_id: str) -> str:
    """Render the CloudFormation Query-protocol error envelope."""
    return CLOUDFORMATION.render_error(code, message, request_id)
