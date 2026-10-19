"""ECS over the AWS JSON protocol: ``ListClusters`` and ``ListServices``.

Both operations return ARNs only, and both ignore paging: the estate is one page, and an
absent ``nextToken`` is what the paginators FinOps uses treat as the end.

``ListServices`` honors the ``cluster`` its caller names. Called without one it answers
with every cluster's services rather than refusing — the real API requires the parameter,
and a smoke request that omits it is asking the wider question this emulator can answer.
"""

from __future__ import annotations

from typing import Any

from tools.synthetic_clouds.model.estate import CanonicalEstate

from aws_sim import json_wire
from aws_sim.json_wire import JsonApiError
from aws_sim.projections import ecs

WIRE = json_wire.JsonWire("ecs")

_ACTIONS: frozenset[str] = frozenset({"ListClusters", "ListServices"})


def supported_actions() -> tuple[str, ...]:
    """The operations this slice answers, sorted."""
    return tuple(sorted(_ACTIONS))


def dispatch(estate: CanonicalEstate, operation: str, body: dict[str, Any]) -> dict[str, Any]:
    """Answer one ECS JSON request, returning the result dict."""
    if operation == "ListClusters":
        return {"clusterArns": list(ecs.clusters(estate))}
    if operation == "ListServices":
        cluster = str(body.get("cluster") or "").strip() or None
        return {"serviceArns": list(ecs.services(estate, cluster))}
    raise JsonApiError(
        "InvalidParameterException",
        f"Operation {operation} is not served by the ECS simulator. Supported: {', '.join(supported_actions())}.",
    )


def render(estate: CanonicalEstate, target: str | None, body: dict[str, Any]) -> str:
    """Render the JSON body for an ``X-Amz-Target`` request."""
    operation = WIRE.operation_for_target(target)
    if operation is None:
        raise JsonApiError("InvalidParameterException", f"Target {target!r} is not served.")
    return WIRE.render_result(dispatch(estate, operation, body))
