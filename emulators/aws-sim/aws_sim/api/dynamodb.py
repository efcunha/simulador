"""DynamoDB over the AWS JSON protocol: ``ListTables``.

One operation, one page, no ``LastEvaluatedTableName``: an absent token is the end of the
list for the paginator FinOps uses.
"""

from __future__ import annotations

from typing import Any

from tools.synthetic_clouds.model.estate import CanonicalEstate

from aws_sim import json_wire
from aws_sim.json_wire import JsonApiError
from aws_sim.projections import dynamodb

WIRE = json_wire.JsonWire("dynamodb")

_ACTIONS: frozenset[str] = frozenset({"ListTables"})


def supported_actions() -> tuple[str, ...]:
    """The operations this slice answers, sorted."""
    return tuple(sorted(_ACTIONS))


def dispatch(estate: CanonicalEstate, operation: str, body: dict[str, Any]) -> dict[str, Any]:
    """Answer one DynamoDB JSON request, returning the result dict."""
    if operation == "ListTables":
        return {"TableNames": list(dynamodb.tables(estate))}
    raise JsonApiError(
        "UnknownOperationException",
        f"Operation {operation} is not served by the DynamoDB simulator. Supported: {', '.join(supported_actions())}.",
    )


def render(estate: CanonicalEstate, target: str | None, body: dict[str, Any]) -> str:
    """Render the JSON body for an ``X-Amz-Target`` request."""
    operation = WIRE.operation_for_target(target)
    if operation is None:
        raise JsonApiError("UnknownOperationException", f"Target {target!r} is not served.")
    return WIRE.render_result(dispatch(estate, operation, body))
