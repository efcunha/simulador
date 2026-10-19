"""AWS Health over the AWS JSON protocol: ``DescribeEvents`` and ``DescribeEventDetails``.

**The protocol was measured, not read off the model.** Both readings agree for this
service — ``metadata["protocol"]`` is ``json`` and ``ServiceModel.resolved_protocol`` is
``json`` — which is the opposite of CloudWatch, where the declared protocol
(``smithy-rpc-v2-cbor``) is not the effective one. Two consequences follow from the same
measurement rather than from a convention: the transport is the JSON one already served
here (``X-Amz-Target: AWSHealth_20160804.<Operation>`` posted to the endpoint root), and
the body type is **1.1** — the model's ``jsonVersion`` is ``1.1``, not CloudWatch's
``1.0`` — which is what :data:`WIRE` carries and what the client sends.

**The two operations are the ones FinOps calls, read off the call site, not copied
from the model's operation list** (``aws_collector.py (modulo do consumidor)``
``collect_health_events``): ``DescribeEvents`` with
``filter={"eventStatusCodes": ["open", "upcoming"]}, maxResults=10``, and
``DescribeEventDetails`` with the ARNs the first call returned. The fields that caller
reads are the whole contract:

* from ``DescribeEvents``: ``events[].arn``, ``.service``, ``.statusCode``,
  ``.eventTypeCode``, ``.startTime``, ``.region``, ``.eventTypeCategory``,
  ``.lastUpdatedTime``, ``.eventScopeCode``;
* from ``DescribeEventDetails``: ``successfulSet[].eventDescription.latestDescription``
  and ``successfulSet[].eventMetadata``.

(One caller-side detail that does not change what is served, recorded so a reviewer does
not read enrichment into an empty ``successfulSet``: the enrichment loop keys the details
by ``detail["eventArn"]`` but looks them up with ``ev.event_url`` — the console URL — so
even a real AWS response would never match and the fields above are unreachable as
written, ``aws_collector.py (modulo do consumidor):294-301``.)

**Both operations answer an EMPTY page, and that is the estate's own answer.** The
canonical estate models no health entity at all: ``tools/synthetic_clouds/model`` and
``generate`` name no incident, no maintenance window, no event category and no affected
service — the only similar surface, CloudWatch alarms, is absent by the same
construction (see :mod:`aws_sim.projections.cloudwatch`). So there is nothing to project
and nothing is invented. This is the one place where inventing a row would be worse than
an empty list: the collector turns each event into a ``HealthEvent`` carrying a severity,
a recommended action and affected resources, so a synthesized "outage" would raise a
false incident in the owner's Operations center about a fictional cloud. Emitting
``{"events": []}`` states exactly what the estate knows — no known events — which is also
what AWS returns for an account with none, and it is the precedent gcp-sim's
``servicehealth`` router set for the same caller pattern.

The empty answers are *well-formed* rather than bare:

* ``events`` and ``successfulSet`` are always present, so the caller's
  ``response.get(..., [])`` reads a list and never a missing key;
* ``nextToken`` is omitted, not empty — real AWS omits the member when the page is the
  last one, and the caller issues no paginator;
* ``failedSet`` is **not** emitted. An entry there is a claim about a *specific ARN*, and
  the model declares no per-ARN error code to make it in (its only declared error is
  ``UnsupportedLocale``), so any code would be fabricated vocabulary. The caller reads
  ``successfulSet`` alone, and an empty one already says the true thing: no detail exists
  for the ARNs that were asked for.

``filter`` and ``maxResults`` are accepted and ignored rather than parsed: there is
nothing for them to narrow, and a half-implemented filter language would reject the
caller's real filter string instead of serving it.

``estate`` is part of the signature because every JSON slice in this package shares the
dispatcher's ``render(estate, target, body)``; it is deliberately unread here, since the
estate carries no health entity to read.
"""

from __future__ import annotations

from typing import Any

from tools.synthetic_clouds.model.estate import CanonicalEstate

from aws_sim import json_wire
from aws_sim.json_wire import JsonApiError

WIRE = json_wire.JsonWire("health")

_ACTIONS: frozenset[str] = frozenset({"DescribeEvents", "DescribeEventDetails"})


def supported_actions() -> tuple[str, ...]:
    """The operations this slice answers, sorted."""
    return tuple(sorted(_ACTIONS))


def dispatch(estate: CanonicalEstate, operation: str, body: dict[str, Any]) -> dict[str, Any]:
    """Answer one AWS Health JSON request, returning the result dict.

    Both served operations return their empty page; see the module docstring for why an
    empty page is the honest answer and not a stub.
    """
    if operation == "DescribeEvents":
        return {"events": []}
    if operation == "DescribeEventDetails":
        return {"successfulSet": []}
    raise JsonApiError(
        "UnknownOperationException",
        f"Operation {operation} is not served by the AWS Health simulator. "
        f"Supported: {', '.join(supported_actions())}.",
    )


def render(estate: CanonicalEstate, target: str | None, body: dict[str, Any]) -> str:
    """Render the JSON body for an ``X-Amz-Target`` request."""
    operation = WIRE.operation_for_target(target)
    if operation is None:
        raise JsonApiError("UnknownOperationException", f"Target {target!r} is not served.")
    return WIRE.render_result(dispatch(estate, operation, body))
