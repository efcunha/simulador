"""RDS over the Query protocol: ``DescribeDBInstances``.

The route lives once in ``api.app`` (the Query protocol has one), so this module owns the
RDS action set and its XML rendering, as ``sts`` does for STS.

Paging is not implemented and does not need to be: the result is one page with no
``Marker``, which is what the paginators FinOps uses treat as the end.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from tools.synthetic_clouds.model.estate import CanonicalEstate

from aws_sim import query_xml
from aws_sim.api.cloudformation import (
    CODE_INVALID_ACTION,
    CODE_INVALID_PARAMETER,
    CODE_MISSING_PARAMETER,
    AwsApiError,
)
from aws_sim.projections import rds

WIRE = query_xml.RDS

#: RDS's own code for "that instance does not exist", so an emulated miss reads like a
#: real one to a caller that branches on it.
CODE_INSTANCE_NOT_FOUND = "DBInstanceNotFoundFault"

_ACTIONS: frozenset[str] = frozenset({"DescribeDBInstances"})


def supported_actions() -> tuple[str, ...]:
    """The actions this slice answers, sorted. Used by tests and by ``InvalidAction``."""
    return tuple(sorted(_ACTIONS))


def dispatch_form(estate: CanonicalEstate, region: str, form: Mapping[str, str]) -> str:
    """Answer one RDS Query-protocol request, returning the XML body."""
    action = form.get("Action", "").strip()
    if not action:
        raise AwsApiError(CODE_MISSING_PARAMETER, "Action is required.")

    version = form.get("Version", "").strip()
    if version != WIRE.api_version():
        raise AwsApiError(
            CODE_INVALID_PARAMETER,
            f"Version {version!r} is not supported; expected {WIRE.api_version()!r}.",
        )

    if action not in _ACTIONS:
        raise AwsApiError(
            CODE_INVALID_ACTION,
            f"Action {action} is not served by the RDS simulator. Supported: {', '.join(supported_actions())}.",
        )

    # ``Filters`` selects on fields the estate does not carry. Refusing is the only
    # honest answer: returning every instance would look like a successful filter that
    # matched everything.
    if any(key.startswith("Filters.") for key in form):
        raise AwsApiError(
            CODE_INVALID_PARAMETER,
            "Filters are not served by the RDS simulator; select with DBInstanceIdentifier.",
        )

    identifier = form.get("DBInstanceIdentifier", "").strip()
    if not identifier:
        result: dict[str, Any] = {"DBInstances": list(rds.instances(estate))}
    else:
        instance = rds.find(estate, identifier)
        if instance is None:
            raise AwsApiError(CODE_INSTANCE_NOT_FOUND, f"DBInstance {identifier} not found")
        result = {"DBInstances": [instance]}

    return WIRE.render_result(action, result, f"synth-{uuid.uuid4().hex[:8]}")
