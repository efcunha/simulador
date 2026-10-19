"""EC2 over the **ec2** protocol: the ten ``Describe*`` reads FinOps collectors make.

EC2 is not a Query service, and the envelope difference (no result wrapper, model-named
tags, lowercase ``requestId``) lives in ``query_xml.EC2Wire``. What is left for this module
is the action set and the parameter handling, as ``api/rds.py`` and ``api/elbv2.py`` are for
theirs — the route itself is the one in ``api/app.py``, because EC2 posts to the endpoint
root like every other Action-dispatched service.

Two parameter decisions, both of which are silent when they are wrong:

* The selectors the estate can answer are honored. EC2 encodes a list parameter as
  ``<element>.<n>`` under the **singular** name the model gives it — ``InstanceIds`` arrives
  as ``InstanceId.1``, not as the Query protocol's ``InstanceIds.member.1``. So the element
  name is read off the service model rather than typed out: the Query spelling appears in no
  EC2 request, and looking for it would simply match nothing and return every row the caller
  did not ask for.
* ``Filter.N.*`` is refused rather than ignored, for the reason ``api/rds.py`` gives: the
  estate carries no attribute to select on, and a filter answered with unfiltered rows reads
  as a successful filter that matched everything. ``MaxResults`` and ``NextToken`` are not
  applied either, and need not be — the whole estate comes back as one page with no
  ``NextToken``, which is what the paginators FinOps uses read as the end.

An id the estate does not carry selects nothing rather than erroring, as in
``projections/elbv2.py``: a caller hears that this account has no such volume instead of
hearing about a volume that does not exist.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterable, Mapping
from typing import Any, NamedTuple

from tools.synthetic_clouds.model.estate import CanonicalEstate

from aws_sim import query_xml
from aws_sim.api.cloudformation import (
    CODE_INVALID_ACTION,
    CODE_INVALID_PARAMETER,
    CODE_MISSING_PARAMETER,
    AwsApiError,
)
from aws_sim.projections import ec2

WIRE = query_xml.EC2

#: EC2's own code for "no such VPC", so an emulated miss reads like a real one to a caller
#: that branches on it.
CODE_INVALID_VPC_ID = "InvalidVpcID.NotFound"

#: A projection: the estate plus the names to narrow to, or ``None`` for every row.
Projection = Callable[[CanonicalEstate, "Iterable[str] | None"], tuple[dict[str, Any], ...]]


class Read(NamedTuple):
    """One served read: the result member it fills, how it narrows, and what derives it."""

    #: The member of the operation's output shape the rows belong to.
    member: str
    #: The **input members** that name the rows to return (``InstanceIds``, ``GroupIds``).
    #: Their singular wire names come from the model, in :func:`_element`.
    selectors: tuple[str, ...]
    project: Projection


_READS: dict[str, Read] = {
    "DescribeInstances": Read("Reservations", ("InstanceIds",), ec2.reservations),
    "DescribeVolumes": Read("Volumes", ("VolumeIds",), ec2.volumes),
    "DescribeVpcs": Read("Vpcs", ("VpcIds",), ec2.vpcs),
    "DescribeSecurityGroups": Read("SecurityGroups", ("GroupIds", "GroupNames"), ec2.security_groups),
    "DescribeNatGateways": Read("NatGateways", ("NatGatewayIds",), ec2.nat_gateways),
    "DescribeAddresses": Read("Addresses", ("AllocationIds",), ec2.addresses),
    "DescribeRegions": Read("Regions", ("RegionNames",), ec2.regions),
    "DescribeRouteTables": Read("RouteTables", ("RouteTableIds",), ec2.route_tables),
    "DescribeInstanceStatus": Read("InstanceStatuses", ("InstanceIds",), ec2.instance_statuses),
}

#: ``DescribeVpcAttribute`` is served but is not a :class:`Read`: it takes a single
#: ``VpcId`` plus the ``Attribute`` to report, and answers one structure rather than a list.
_ATTRIBUTE_ACTION = "DescribeVpcAttribute"

_ACTIONS: frozenset[str] = frozenset({*_READS, _ATTRIBUTE_ACTION})


def supported_actions() -> tuple[str, ...]:
    """The actions this slice answers, sorted. Used by tests and by ``InvalidAction``."""
    return tuple(sorted(_ACTIONS))


def _element(operation: str, member: str) -> str:
    """The form key EC2 uses for one element of a list parameter.

    Derived exactly as ``botocore.serialize.EC2Serializer`` derives it: the model's
    ``queryName`` if it has one, otherwise the member's serialized name with its first letter
    capitalized, because EC2 capitalizes a location name on input. ``GroupIds`` therefore
    arrives as ``GroupId.1`` and ``RegionNames`` as ``RegionName.1``.
    """
    shape = WIRE.service_model().operation_model(operation).input_shape.members[member]
    name: str | None = shape.serialization.get("queryName") or shape.serialization.get("name")
    if not name:
        return member
    return name[0].upper() + name[1:]


def _members(form: Mapping[str, str], element: str) -> tuple[str, ...]:
    """Read one EC2 list parameter, in the order the client sent it."""
    indexed: list[tuple[int, str]] = []
    for key, value in form.items():
        prefix, _, index = key.rpartition(".")
        if prefix == element and index.isdigit():
            indexed.append((int(index), value.strip()))
    return tuple(value for _, value in sorted(indexed) if value)


def _selection(
    form: Mapping[str, str],
    operation: str,
    selectors: tuple[str, ...],
) -> tuple[str, ...] | None:
    """The names this request narrows to, or ``None`` when it names none.

    ``None`` and "the caller sent an empty list" are the same thing, which is why an empty
    selection reads as no selection: the ec2 serializer omits a list it has no members for, so
    an absent selector and an empty one are indistinguishable on the wire.
    """
    values = tuple(
        value for member in selectors for value in _members(form, _element(operation, member))
    )
    return values or None


def _refuse_filters(form: Mapping[str, str]) -> None:
    """Refuse ``Filter`` rather than answering an unfiltered question as if it were filtered."""
    if any(key == "Filter" or key.startswith("Filter.") for key in form):
        raise AwsApiError(
            CODE_INVALID_PARAMETER,
            "Filters are not served by the EC2 simulator; select with the id parameters instead.",
        )


def _vpc_attribute(estate: CanonicalEstate, form: Mapping[str, str]) -> dict[str, Any]:
    """``DescribeVpcAttribute``: the requested attribute of the requested VPC.

    ``VpcId`` and ``Attribute`` are both required by the real service and by this one: with
    either missing the request has no question to answer. The attribute names are the ones
    the model defines, and anything else is an ``InvalidParameterValue`` — a caller that
    mistyped the name should hear about the name, not receive an empty structure that looks
    like a VPC with no attributes.
    """
    vpc_id = form.get("VpcId", "").strip()
    if not vpc_id:
        raise AwsApiError(CODE_MISSING_PARAMETER, "VpcId is required for this operation.")

    attribute = form.get("Attribute", "").strip()
    if not attribute:
        raise AwsApiError(CODE_MISSING_PARAMETER, "Attribute is required for this operation.")
    if attribute not in ec2.VPC_ATTRIBUTES:
        raise AwsApiError(
            CODE_INVALID_PARAMETER,
            f"Attribute {attribute!r} is not supported; expected one of "
            f"{', '.join(sorted(ec2.VPC_ATTRIBUTES))}.",
        )

    answer = ec2.vpc_attribute(estate, vpc_id, attribute)
    if answer is None:
        raise AwsApiError(CODE_INVALID_VPC_ID, f"The vpc ID {vpc_id!r} does not exist")
    return answer


def dispatch_form(estate: CanonicalEstate, region: str, form: Mapping[str, str]) -> str:
    """Answer one EC2 request, returning the XML body."""
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
            f"Action {action} is not served by the EC2 simulator. Supported: {', '.join(supported_actions())}.",
        )

    _refuse_filters(form)

    if action == _ATTRIBUTE_ACTION:
        result = _vpc_attribute(estate, form)
    else:
        read = _READS[action]
        result = {read.member: list(read.project(estate, _selection(form, action, read.selectors)))}

    return WIRE.render_result(action, result, f"synth-{uuid.uuid4().hex[:8]}")
