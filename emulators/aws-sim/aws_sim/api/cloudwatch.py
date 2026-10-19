"""CloudWatch over the AWS RPC-v2 wire.

Three operations, the set FinOps actually calls — confirmed by reading every
``client("cloudwatch")`` call site, not by copying the model's operation list:

* ``ListMetrics`` — ``aws_metrics.py (modulo do consumidor)`` ``discover_metrics``, paginated;
* ``DescribeAlarms`` — ``aws_collector.py (modulo do consumidor)``, ``StateValue="ALARM"``, paginated;
* ``GetMetricData`` — ``aws_metrics.py (modulo do consumidor)`` ``pull``/``_execute_batch`` and
  ``cloudwatch_metrics_provider.py (modulo do consumidor)``.

``GetMetricStatistics`` is deliberately not served: it appears in FinOps only as a
capability *label* in the inventory audit's registry, never as a call.

A request that is missing a required member is refused with the code CloudWatch itself
uses (``MissingRequiredParameterException``) rather than answered with an empty result that
would read as absence — the discipline ``api/ce.py`` already follows for ``TimePeriod``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from tools.synthetic_clouds.model.estate import CanonicalEstate

from aws_sim import smithy_rpc
from aws_sim.projections import cloudwatch
from aws_sim.smithy_rpc import SmithyRpcError

#: The JSON-1.0 framing. This is the one the installed botocore sends for CloudWatch:
#: ``ServiceModel.resolved_protocol`` resolves the model's protocol list to ``json``
#: (see ``aws_sim.smithy_rpc``), and a live capture of a real boto3 call confirms a
#: ``GraniteServiceVersion20100801.<Operation>`` target posted to the endpoint root.
WIRE = smithy_rpc.SmithyRpcWire("cloudwatch", smithy_rpc.PROTOCOL_JSON)

#: The CBOR framing — the protocol the model declares *first*. Unreachable for a client
#: that resolves to ``json``, and served because the model says the service speaks it.
CBOR_WIRE = smithy_rpc.SmithyRpcWire("cloudwatch", smithy_rpc.PROTOCOL_CBOR)

_ACTIONS: frozenset[str] = frozenset({"ListMetrics", "DescribeAlarms", "GetMetricData"})

_CODE_MISSING_PARAMETER = "MissingRequiredParameterException"
_CODE_INVALID_PARAMETER = "InvalidParameterValueException"


def supported_actions() -> tuple[str, ...]:
    """The operations this slice answers, sorted."""
    return tuple(sorted(_ACTIONS))


def operation_for_target(target: str | None) -> str | None:
    """The operation a ``<Prefix>.<Operation>`` target names, or ``None``.

    Resolution is framing-independent — both wirings carry the same target prefix — so the
    dispatcher asks here rather than picking a wire to ask.
    """
    return WIRE.operation_for_target(target)


def _required(body: dict[str, Any], key: str) -> Any:
    value = body.get(key)
    if value is None:
        raise SmithyRpcError(_CODE_MISSING_PARAMETER, f"{key} is required.")
    return value


def _timestamp(value: Any, key: str) -> datetime:
    """Parse one request timestamp, in whichever form the framing delivered it.

    The two framings do **not** agree here, which is why this is a boundary rather than a
    cast. JSON-1.0 sends epoch seconds, so ``StartTime`` arrives as a number. The CBOR
    serializer's ``unixtimestamp`` format is CBOR **tag 1** (epoch milliseconds), and
    ``cbor2`` decodes tag 1 straight into a ``datetime`` — so the same member arrives as a
    ``datetime`` there. ISO 8601 strings are accepted too, since a caller may hand boto3 a
    string and the serializer's choice of form is not the caller's contract.
    """
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return datetime.fromtimestamp(float(value), tz=UTC)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise SmithyRpcError(_CODE_INVALID_PARAMETER, f"{key} is not a valid timestamp: {value!r}.") from exc
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    raise SmithyRpcError(_CODE_INVALID_PARAMETER, f"{key} is not a valid timestamp: {value!r}.")


def dispatch(estate: CanonicalEstate, operation: str, body: dict[str, Any]) -> dict[str, Any]:
    """Answer one CloudWatch request, returning the result dict."""
    if operation == "ListMetrics":
        return {
            "Metrics": cloudwatch.metrics(
                estate,
                namespace=body.get("Namespace"),
                metric_name=body.get("MetricName"),
                dimensions=body.get("Dimensions"),
            ),
        }
    if operation == "DescribeAlarms":
        # No filter is applied because there is nothing to filter: the estate models no
        # alarm, so every filter — StateValue, AlarmNames, AlarmNamePrefix — selects from
        # an empty set. ``MetricAlarms`` is always present so the paginator FinOps uses
        # terminates on the first page instead of looking for a token.
        return {"MetricAlarms": cloudwatch.alarms(estate), "CompositeAlarms": []}
    if operation == "GetMetricData":
        queries = _required(body, "MetricDataQueries")
        start = _timestamp(_required(body, "StartTime"), "StartTime")
        end = _timestamp(_required(body, "EndTime"), "EndTime")
        try:
            results = cloudwatch.metric_data(estate, queries=queries, start=start, end=end)
        except ValueError as exc:
            # The projection refuses what it cannot evaluate (a math expression, an
            # unknown statistic); the wire reports it instead of answering empty.
            raise SmithyRpcError(_CODE_INVALID_PARAMETER, str(exc)) from exc
        return {"MetricDataResults": results}
    raise SmithyRpcError(
        "UnknownOperationException",
        f"Operation {operation} is not served by the CloudWatch simulator. "
        f"Supported: {', '.join(supported_actions())}.",
    )
