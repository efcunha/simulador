"""Organizations over the AWS JSON protocol.

Two read operations: ``ListAccounts`` (what ``org_discovery.py`` consumes) and
``DescribeOrganization``. Both ignore paging — the estate has one page — and an unknown
operation is refused with ``InvalidActionException`` naming it.
"""

from __future__ import annotations

from typing import Any

from tools.synthetic_clouds.model.estate import CanonicalEstate

from aws_sim import json_wire
from aws_sim.json_wire import JsonApiError
from aws_sim.projections import organizations

WIRE = json_wire.JsonWire("organizations")

_ACTIONS: frozenset[str] = frozenset({"DescribeOrganization", "ListAccounts"})


def supported_actions() -> tuple[str, ...]:
    """The actions this slice answers, sorted."""
    return tuple(sorted(_ACTIONS))


def dispatch(estate: CanonicalEstate, operation: str, body: dict[str, Any]) -> dict[str, Any]:
    """Answer one Organizations JSON request, returning the result dict."""
    if operation == "ListAccounts":
        return {"Accounts": list(organizations.accounts(estate))}
    if operation == "DescribeOrganization":
        return organizations.organization_document(estate)
    raise JsonApiError(
        "InvalidActionException",
        f"Action {operation} is not served by the Organizations simulator. "
        f"Supported: {', '.join(supported_actions())}.",
    )


def render(estate: CanonicalEstate, target: str | None, body: dict[str, Any]) -> str:
    """Render the JSON body for an ``X-Amz-Target`` request."""
    operation = WIRE.operation_for_target(target)
    if operation is None:
        raise JsonApiError("InvalidActionException", f"Target {target!r} is not served.")
    return WIRE.render_result(dispatch(estate, operation, body))
