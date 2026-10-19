"""The ELBv2 projection: ``DescribeLoadBalancers`` and ``DescribeTags``.

Both operations read the same estate rows (``resource_type == "application_lb"``), which
is what makes the two coherent: the ``LoadBalancerArn`` from ``DescribeLoadBalancers`` is
the ``ResourceArn`` from ``DescribeTags`` for the same balancer by construction, so a
caller that correlates them (FinOps ALB collector does) sees one balancer and not
two.

Derivations worth stating:

* ``Scheme`` has no counterpart in the model, so it is picked from AWS's own vocabulary
  (``internet-facing`` / ``internal``) keyed on the resource uuid — stable across calls,
  and varied enough that an exposure check has both cases to look at.
* ``LoadBalancerName`` is the resource's derived AWS id (``aws_sim.ids``), the same value
  the ARN and ``DescribeTags`` carry: the estate reuses a ``resource_name`` across scopes,
  and an ELBv2 name is scope-free, so a row named after the resource would give two
  balancers in two accounts one identity. The name is what ``DescribeTags`` is asked about
  here (by ARN) and what a caller filters on, so it has to be unique.
* ``AvailabilityZones`` names the balancer's own region plus an AZ letter: the estate
  records a region per resource and nothing about subnets, so a ``SubnetId`` would be an
  identifier no estate row backs.
* ``VpcId`` is omitted for the same reason: the account owns several VPCs and picking one
  would be an invented attachment.
* ``CreatedTime`` is the resource's earliest billed day (``scope.first_charge``), the only
  timestamp the estate carries, and is omitted when the estate has never billed it.
* ``DescribeTargetGroups`` / ``DescribeTargetHealth`` are NOT answered: the estate models
  no target groups, and an empty list would read as "there are none" instead of "the
  emulator does not know".
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any

from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.resource import Resource

from aws_sim import arns, ids, scope

RESOURCE_TYPE = "application_lb"

LOAD_BALANCER_TYPE = "application"
STATE_ACTIVE = "active"
SCHEMES: tuple[str, ...] = ("internet-facing", "internal")
AZ_LETTERS: tuple[str, ...] = ("a", "b")
IP_ADDRESS_TYPE = "ipv4"


def _bucket(key: str, count: int) -> int:
    """A stable catalog index for ``key`` (a resource uuid or a uuid-derived key)."""
    return int(arns.stable_digest(key, 8), 16) % count


def _balancer(resource: Resource, created: datetime | None) -> dict[str, Any]:
    """One ``LoadBalancers`` entry for an estate load balancer."""
    uuid = resource.identity.uuid
    name = ids.resource_id(resource)
    row: dict[str, Any] = {
        "LoadBalancerArn": arns.resource_arn(resource),
        "LoadBalancerName": name,
        "DNSName": f"{name}.{resource.region_id}.elb.amazonaws.com",
        "Scheme": SCHEMES[_bucket(f"{uuid}:scheme", len(SCHEMES))],
        "Type": LOAD_BALANCER_TYPE,
        "State": {"Code": STATE_ACTIVE},
        "IpAddressType": IP_ADDRESS_TYPE,
        "AvailabilityZones": [
            {"ZoneName": f"{resource.region_id}{AZ_LETTERS[index]}"}
            for index in range(_bucket(f"{uuid}:azs", len(AZ_LETTERS)) + 1)
        ],
    }
    if created is not None:
        row["CreatedTime"] = created
    return row


def _load_balancer_resources(estate: CanonicalEstate) -> tuple[Resource, ...]:
    return tuple(r for r in scope.resources(estate) if r.resource_type == RESOURCE_TYPE)


def load_balancers(estate: CanonicalEstate) -> tuple[dict[str, Any], ...]:
    """Every load balancer the estate carries, ordered by name."""
    first_charge = scope.first_charge(estate)
    rows = [
        _balancer(resource, first_charge.get(resource.identity.uuid))
        for resource in _load_balancer_resources(estate)
    ]
    return tuple(sorted(rows, key=lambda row: row["LoadBalancerName"]))


def find(estate: CanonicalEstate, name_or_arn: str) -> dict[str, Any] | None:
    """Resolve one balancer by name or ARN, the two ways a client may name it."""
    return next(
        (
            row
            for row in load_balancers(estate)
            if name_or_arn in (row["LoadBalancerName"], row["LoadBalancerArn"])
        ),
        None,
    )


def tag_descriptions(
    estate: CanonicalEstate,
    resource_arns: Iterable[str] | None = None,
) -> tuple[dict[str, Any], ...]:
    """One ``TagDescriptions`` entry per balancer, from the resource's own tag pairs.

    An ARN that is not one of this estate's balancers yields no entry: the caller asked
    about a balancer this account does not own, and an empty tag set would claim it
    exists and is untagged.
    """
    wanted = None if resource_arns is None else {value.strip() for value in resource_arns if value.strip()}
    descriptions: list[dict[str, Any]] = []
    for resource in sorted(_load_balancer_resources(estate), key=lambda r: r.resource_name):
        arn = arns.resource_arn(resource)
        if wanted is not None and arn not in wanted:
            continue
        descriptions.append(
            {
                "ResourceArn": arn,
                "Tags": [{"Key": key, "Value": value} for key, value in resource.tags],
            },
        )
    return tuple(descriptions)
