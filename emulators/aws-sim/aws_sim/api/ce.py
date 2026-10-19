"""Cost Explorer over the AWS JSON protocol.

Two operations, matching the audit's call sites: ``GetCostAndUsage`` (seven of the eight
sites) and ``GetDimensionValues``. A request without a ``TimePeriod`` is refused with
``ValidationException`` — the same code CE itself uses — rather than answered with an
empty result that would look like absence.
"""

from __future__ import annotations

from typing import Any

from tools.synthetic_clouds.model.estate import CanonicalEstate

from aws_sim import json_wire
from aws_sim.json_wire import JsonApiError
from aws_sim.projections import ce

WIRE = json_wire.JsonWire("ce")

_ACTIONS: frozenset[str] = frozenset({"GetCostAndUsage", "GetDimensionValues"})


def supported_actions() -> tuple[str, ...]:
    """The operations this slice answers, sorted."""
    return tuple(sorted(_ACTIONS))


def _time_period(body: dict[str, Any]) -> dict[str, Any]:
    time_period = body.get("TimePeriod")
    if not isinstance(time_period, dict) or "Start" not in time_period or "End" not in time_period:
        raise JsonApiError("ValidationException", "TimePeriod with Start and End is required.")
    return time_period


def dispatch(estate: CanonicalEstate, operation: str, body: dict[str, Any]) -> dict[str, Any]:
    """Answer one Cost Explorer JSON request, returning the result dict."""
    if operation == "GetCostAndUsage":
        return ce.get_cost_and_usage(
            estate,
            time_period=_time_period(body),
            granularity=str(body.get("Granularity") or ce.GRANULARITY_DAILY),
            metrics=body.get("Metrics"),
            group_by=body.get("GroupBy"),
        )
    if operation == "GetDimensionValues":
        return ce.get_dimension_values(
            estate,
            time_period=_time_period(body),
            dimension=str(body.get("Dimension") or ""),
            search_string=str(body.get("SearchString") or ""),
        )
    raise JsonApiError(
        "UnknownOperationException",
        f"Operation {operation} is not served by the Cost Explorer simulator. "
        f"Supported: {', '.join(supported_actions())}.",
    )


def render(estate: CanonicalEstate, target: str | None, body: dict[str, Any]) -> str:
    """Render the JSON body for an ``X-Amz-Target`` request."""
    operation = WIRE.operation_for_target(target)
    if operation is None:
        raise JsonApiError("UnknownOperationException", f"Target {target!r} is not served.")
    return WIRE.render_result(dispatch(estate, operation, body))
