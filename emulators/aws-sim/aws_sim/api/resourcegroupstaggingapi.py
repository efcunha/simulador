"""Resource Groups Tagging API over the AWS JSON protocol: ``GetResources``.

Two filters exist on this operation and they are handled in opposite ways, on purpose:

* ``TagFilters`` is applied. It selects on the estate's own tag pairs, so it can be
  answered truthfully: a mapping survives when any of the filter's values matches the
  resource's value for that key, and a filter with no values selects on key presence —
  which is the API's own semantics.
* ``ResourceTypeFilters`` is **refused** with ``InvalidParameterException``. Its values
  live in the tagging API's ``service:resource`` notation (``ec2:instance``,
  ``elasticloadbalancing:loadbalancer``), which is not the estate's ``resource_type`` and
  not derivable from it without inventing a second naming scheme — and a filter answered
  with unfiltered rows is worse than a refusal.

``PaginationToken`` / ``ResourcesPerPage`` are ignored like every other page parameter in
this emulator: the estate is one page.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from tools.synthetic_clouds.model.estate import CanonicalEstate

from aws_sim import json_wire
from aws_sim.json_wire import JsonApiError
from aws_sim.projections import resourcegroupstaggingapi as rgta

WIRE = json_wire.JsonWire("resourcegroupstaggingapi")

_ACTIONS: frozenset[str] = frozenset({"GetResources"})

#: The error code the real API uses for a filter it cannot accept.
CODE_INVALID_PARAMETER = "InvalidParameterException"


def supported_actions() -> tuple[str, ...]:
    """The operations this slice answers, sorted."""
    return tuple(sorted(_ACTIONS))


def _matches(tags: Mapping[str, str], filters: Sequence[Mapping[str, Any]]) -> bool:
    """Whether a resource's tags pass every filter the caller sent.

    A filter with no values selects on key presence, which is the API's own semantics.
    """
    for tag_filter in filters:
        key = str(tag_filter.get("Key", ""))
        if key not in tags:
            return False
        wanted = [str(value) for value in tag_filter.get("Values") or []]
        if wanted and tags[key] not in wanted:
            return False
    return True


def dispatch(estate: CanonicalEstate, operation: str, body: dict[str, Any]) -> dict[str, Any]:
    """Answer one tagging-API JSON request, returning the result dict."""
    if operation != "GetResources":
        raise JsonApiError(
            "UnknownOperationException",
            f"Operation {operation} is not served by the tagging simulator. "
            f"Supported: {', '.join(supported_actions())}.",
        )

    if body.get("ResourceTypeFilters"):
        raise JsonApiError(
            CODE_INVALID_PARAMETER,
            "ResourceTypeFilters is not served by the tagging simulator: its service:resource "
            "notation has no counterpart in this estate. Filter with TagFilters instead.",
        )

    rows = list(rgta.resources(estate))
    filters = [f for f in body.get("TagFilters") or [] if isinstance(f, dict)]
    if filters:
        rows = [row for row in rows if _matches({t["Key"]: t["Value"] for t in row["Tags"]}, filters)]
    return {"ResourceTagMappingList": rows}


def render(estate: CanonicalEstate, target: str | None, body: dict[str, Any]) -> str:
    """Render the JSON body for an ``X-Amz-Target`` request."""
    operation = WIRE.operation_for_target(target)
    if operation is None:
        raise JsonApiError("UnknownOperationException", f"Target {target!r} is not served.")
    return WIRE.render_result(dispatch(estate, operation, body))
