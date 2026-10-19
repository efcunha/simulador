"""ELBv2 over the Query protocol: ``DescribeLoadBalancers`` and ``DescribeTags``.

Both wire operations FinOps ALB collector calls (``resources (modulo do consumidor)``).
The collector asks for the balancers, then asks for their tags one ARN at a time, so the
two answers must agree — they do, because both project the same estate rows.

Only two list filters exist and both are honored (``Names``, ``LoadBalancerArns``):
silently ignoring a filter would answer a narrow question with a wide result and look
like success.
"""

from __future__ import annotations

import re
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
from aws_sim.projections import elbv2

WIRE = query_xml.ELBV2

_ACTIONS: frozenset[str] = frozenset({"DescribeLoadBalancers", "DescribeTags"})

#: Query-protocol lists are ``<Name>.member.<n>`` (they are not flattened in the ELBv2
#: model, which botocore's own serializer confirms).
_MEMBER_KEY = re.compile(r"^(?P<name>[A-Za-z]+)\.member\.(?P<index>\d+)$")


def supported_actions() -> tuple[str, ...]:
    """The actions this slice answers, sorted. Used by tests and by ``InvalidAction``."""
    return tuple(sorted(_ACTIONS))


def _members(form: Mapping[str, str], name: str) -> tuple[str, ...]:
    """Read one Query-protocol list parameter, in the order the client sent it."""
    indexed: list[tuple[int, str]] = []
    for key, value in form.items():
        match = _MEMBER_KEY.match(key)
        if match is not None and match.group("name") == name:
            indexed.append((int(match.group("index")), value.strip()))
    return tuple(value for _, value in sorted(indexed) if value)


def dispatch_form(estate: CanonicalEstate, region: str, form: Mapping[str, str]) -> str:
    """Answer one ELBv2 Query-protocol request, returning the XML body."""
    action = form.get("Action", "").strip()
    if not action:
        raise AwsApiError(CODE_MISSING_PARAMETER, "Action is required.")

    version = form.get("Version", "").strip()
    if version != WIRE.api_version():
        raise AwsApiError(
            CODE_INVALID_PARAMETER,
            f"Version {version!r} is not supported; expected {WIRE.api_version()!r}.",
        )

    if action == "DescribeLoadBalancers":
        result = _describe_load_balancers(estate, form)
    elif action == "DescribeTags":
        result = _describe_tags(estate, form)
    else:
        raise AwsApiError(
            CODE_INVALID_ACTION,
            f"Action {action} is not served by the ELBv2 simulator. Supported: {', '.join(supported_actions())}.",
        )

    return WIRE.render_result(action, result, f"synth-{uuid.uuid4().hex[:8]}")


def _describe_load_balancers(estate: CanonicalEstate, form: Mapping[str, str]) -> dict[str, Any]:
    """``DescribeLoadBalancers``, filtered by the ARNs or names the caller named."""
    arns = _members(form, "LoadBalancerArns")
    names = _members(form, "Names")
    rows: list[dict[str, Any]] = list(elbv2.load_balancers(estate))
    if arns:
        rows = [row for row in rows if row["LoadBalancerArn"] in arns]
    if names:
        rows = [row for row in rows if row["LoadBalancerName"] in names]
    return {"LoadBalancers": rows}


def _describe_tags(estate: CanonicalEstate, form: Mapping[str, str]) -> dict[str, Any]:
    """``DescribeTags`` for the requested ARNs.

    ``ResourceArns`` is required by the real service and by this one: without it the
    operation has no question to answer, and "every balancer's tags" is not what the
    caller asked for.
    """
    arns = _members(form, "ResourceArns")
    if not arns:
        raise AwsApiError(CODE_MISSING_PARAMETER, "ResourceArns is required for this operation.")
    return {"TagDescriptions": list(elbv2.tag_descriptions(estate, arns))}
