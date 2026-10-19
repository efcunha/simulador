"""The EC2 projection: instances, volumes, VPCs, security groups, NAT gateways and EIPs.

One function per ``resource_type`` the estate carries, so every row here has an estate row
behind it and a type the estate has none of answers an empty list rather than a placeholder.

**The identifier rule is what holds this slice together.** The AWS id a row reports
(``InstanceId``, ``VolumeId``, ``GroupId``, …) is the resource's own AWS id
(``aws_sim.ids.resource_id`` — minted from the resource identity in the shape its
``resource_type`` uses), and ``aws_sim.arns`` builds that row's ARN from the very same
value (``instance/<id>``, ``security-group/<id>``). So the id read here, the ``ResourceARN``
the Resource Groups Tagging API reports for the same row, and the ARN a caller rebuilds from
region + account + id — which is exactly what ``security (modulo do consumidor)`` does
with ``arn:aws:ec2:<region>:<OwnerId>:security-group/<GroupId>`` — are one value. A caller
cannot end up holding two identities for one instance, and that is checkable, so the tests
check it.

**Why the id is not the name.** ``Resource.resource_name`` is a real FOCUS column and the
resource's display name, and the estate reuses it across scopes: 18 EC2 instances carry 11
distinct names in the small profile. An ``InstanceId`` is scope-free, so a projection that
answered the name would answer ONE id for three instances in three accounts — and the
CloudWatch shim, which dimensions a metric by that same value, would then resolve all three
to whichever series it matched first. So the name stays a display field (it is what
``GroupName`` carries for a security group, where AWS's own member IS a name) and every id
member carries the derived id. An id the caller names selects on that id, and a security
group — the one type whose two selection parameters are genuinely two different values —
is matched on either.

**Where a derived value is allowed, and where it is not.** The estate records a cost basis,
not a configuration: a region, an account, tags and a ``sku_id``. It carries no network
topology, no attachment and no rule. So:

* A field is emitted when it is an attribute **of this one object** with an AWS-native
  closed vocabulary, derived deterministically from the object's own uuid — instance type
  and volume type from the SKU, volume size and VPC CIDR from a small catalog, the AZ
  letter from the region, states from AWS's vocabulary. The key is the resource's own
  identity: a random or clock-derived choice would make two calls about the same resource
  disagree, and FinOps correlates those answers across a scan.
* A field that asserts a **relation to a resource the estate does not link** is omitted:
  ``VpcId``/``SubnetId`` on an instance, ``Attachments`` on a volume, ``VpcId`` on a
  security group, ``SubnetId``/``NatGatewayAddresses`` on a NAT gateway, ``AssociationId``
  and ``InstanceId`` on an address. Each would be an invented attachment.
* ``IpPermissions``/``IpPermissionsEgress`` are omitted for that reason and one more: the
  estate models no rule, so the emulator cannot report an open port, and an **empty** ingress
  list would instead assert that the group has none. Omitting leaves the rules absent, which
  is what they are — and it is why an emulated security scan finds nothing to flag.
* ``LaunchTime``/``CreateTime`` come from the resource's earliest billed day
  (``scope.first_charge``), the only timestamp the estate asserts about a resource, and are
  omitted for a resource it has never billed rather than filled with the sim's clock.
* An id the caller names that this estate does not carry selects nothing, as in
  ``projections/elbv2.py``: the emulator answers about what it owns instead of inventing a
  row for something it does not.

A row is keyed by the model's **Python** member name, not by the tag it is written under:
the renderer asks the model for the tag (``State`` -> ``<instanceState>``, ``Tags`` ->
``<tagSet>``), so a row keyed by the wire name is a member the renderer skips and the caller
never sees. Two reads can therefore disagree about the same concept through no mistake —
``DescribeInstances`` has a member named ``State`` where ``DescribeInstanceStatus`` has one
named ``InstanceState``, and each row uses its own operation's name.

Three consequences of the model, stated because a reader will meet them:

* Every id this endpoint answers is unique across the whole estate rather than only inside
  one account, because it is derived from the resource's identity and not from its name
  (``aws_sim.ids``) — so ``InstanceIds=[x]`` comes back with exactly the one instance a real
  account would have produced, even though one endpoint serves every account. The ARN
  remains the value that carries the account as well, and :mod:`aws_sim.arns` builds it from
  that same id.
* Every volume reports ``State: available`` and no ``Attachments``. The two agree, and that
  is the honest reading of an estate that links a volume to nothing — so a caller hunting
  unattached volumes sees them all. That is a property of the estate, not a claim this
  projection makes.
* ``DescribeRouteTables`` answers nothing at all: the estate has no route-table resource,
  and a route table invented to point at a NAT gateway would hand
  ``_collect_nat_gateway`` a fabricated dependency graph to report as fact.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any

from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.resource import Resource

from aws_sim import arns, ids, scope

INSTANCE = "ec2_instance"
VOLUME = "ebs_volume"
VPC = "vpc"
SECURITY_GROUP = "security_group"
NAT_GATEWAY = "nat_gateway"
ELASTIC_IP = "elastic_ip"

#: ``sku_id`` -> the instance type it names. A closed map: the SKU catalog is the
#: generator's, so an unmapped SKU is a code change upstream and a KeyError names it.
INSTANCE_TYPES_BY_SKU: dict[str, str] = {
    "aws-ec2-m5-large": "m5.large",
}

#: ``sku_id`` -> the volume type it names (``aws-ebs-gp3`` really does say ``gp3``).
VOLUME_TYPES_BY_SKU: dict[str, str] = {
    "aws-ebs-gp3": "gp3",
}

VOLUME_SIZES_GB: tuple[int, ...] = (20, 100, 500)
VPC_CIDRS: tuple[str, ...] = ("10.0.0.0/16", "10.1.0.0/16", "172.16.0.0/16", "192.168.0.0/16")
AZ_LETTERS: tuple[str, ...] = ("a", "b", "c")
CONNECTIVITY_TYPES: tuple[str, ...] = ("public", "private")

#: EC2's own state vocabulary. The estate is a running baseline, so these are the "live"
#: members of each set: a resource the estate bills for exists, and that is all it says.
VOLUME_STATE = "available"
VPC_STATE = "available"
NAT_GATEWAY_STATE = "available"
INSTANCE_TENANCY = "default"
ADDRESS_DOMAIN = "vpc"
ADDRESS_POOL = "203.0.113"  # RFC 5737 TEST-NET-3: a public address that is never routable
OPT_IN_NOT_REQUIRED = "opt-in-not-required"
STATUS_OK = "ok"
STATUS_REACHABILITY = "reachability"
STATUS_PASSED = "passed"

#: The attribute names ``DescribeVpcAttribute`` accepts, mapped to the member the model
#: returns each one in. AWS's three, read off the input shape rather than guessed.
VPC_ATTRIBUTES: dict[str, str] = {
    "enableDnsHostnames": "EnableDnsHostnames",
    "enableDnsSupport": "EnableDnsSupport",
    "enableNetworkAddressUsageMetrics": "EnableNetworkAddressUsageMetrics",
}


def _bucket(key: str, count: int) -> int:
    """A stable catalog index for ``key`` (a resource uuid or a uuid-derived key)."""
    return int(arns.stable_digest(key, 8), 16) % count


def _of_type(estate: CanonicalEstate, resource_type: str) -> tuple[Resource, ...]:
    """The estate's resources of one type, ordered by name."""
    return tuple(
        sorted(
            (r for r in scope.resources(estate) if r.resource_type == resource_type),
            key=lambda r: r.resource_name,
        ),
    )


def _selection(values: Iterable[str] | None) -> frozenset[str] | None:
    """The ids a read is narrowed to, or ``None`` for "every row".

    ``None`` means the caller sent no selector at all. A selector that carried no usable
    member means the same thing, because the ec2 serializer omits a list it has no elements
    for — so an empty selector is an absent one, not a request for nothing.
    """
    if values is None:
        return None
    wanted = frozenset(value.strip() for value in values if value.strip())
    return wanted or None


def _kept(selection: frozenset[str] | None, *values: str) -> bool:
    """Whether the caller asked for a row that identifies itself by any of ``values``.

    Every read narrows on the resource's own AWS id (``aws_sim.ids``), which is unique
    across the estate, and one value is enough for all of them but
    ``DescribeSecurityGroups``: ``GroupIds`` and ``GroupNames`` are two parameters naming
    the same group two ways, and ``api/ec2.py`` merges them into one selector, so a group
    is matched on its id AND on its name. ``DescribeRegions`` passes a region id, which is
    not a resource at all.
    """
    return selection is None or any(value in selection for value in values)


def _availability_zone(resource: Resource) -> str:
    """The zone the resource sits in: its own region plus a letter.

    The estate records a region and nothing finer, so the letter is derived from the
    resource uuid and is stable across calls — which a random letter would not be.
    """
    return f"{resource.region_id}{AZ_LETTERS[_bucket(f'{resource.identity.uuid}:az', len(AZ_LETTERS))]}"


def _tag_set(resource: Resource) -> list[dict[str, str]]:
    """The resource's own tag pairs, in the wire shape every EC2 row carries them in."""
    return [{"Key": key, "Value": value} for key, value in resource.tags]


def _instance_state() -> dict[str, Any]:
    """``InstanceState`` for a running instance. Fresh each call, so no two rows alias."""
    return {"Code": 16, "Name": "running"}


def _status_summary() -> dict[str, Any]:
    """A passing ``InstanceStatusSummary``. Fresh each call, so no two rows alias."""
    return {"Status": STATUS_OK, "Details": [{"Name": STATUS_REACHABILITY, "Status": STATUS_PASSED}]}


def _attribute_value() -> dict[str, bool]:
    """``AttributeBooleanValue`` for a VPC attribute the estate does not carry.

    The sim's estate is a healthy, configured baseline — RDS reports ``StorageEncrypted``,
    ELBv2 reports an active state — and FinOps own VPC collector reads a missing
    attribute as ``True``. So ``True`` here is that stated baseline rather than a value
    derived from anything.
    """
    return {"Value": True}


def _private_ip(key: str) -> str:
    """A deterministic RFC 1918 address for ``key``, out of the 10/8 block EC2 hands out.

    The estate records no address, so one is derived from the resource uuid: the same
    instance reports the same address on every call, which a random address could not
    promise and FinOps would read as a different host on each scan.
    """
    digest = arns.stable_digest(f"{key}:private-ip", 6)
    # 1..254 per octet, because .0 and .255 are not host addresses.
    octets = [int(digest[index:index + 2], 16) % 254 + 1 for index in (0, 2, 4)]
    return "10." + ".".join(str(octet) for octet in octets)


def _public_ip(key: str) -> str:
    """A deterministic public-looking address for ``key``, out of TEST-NET-3.

    RFC 5737 reserves ``203.0.113.0/24`` for documentation, so the address can never be
    confused with a real allocation — which matters more here than realism would, because
    an emulator handing out an address that belongs to somebody is a worse lie than one
    that is obviously synthetic.
    """
    return f"{ADDRESS_POOL}.{_bucket(f'{key}:public-ip', 254) + 1}"


def _instance(resource: Resource, launched: datetime | None) -> dict[str, Any]:
    """One ``Instances`` entry for an estate EC2 instance.

    The member is ``State`` and not ``InstanceState``: the model names the member ``State``
    and only renames it to ``instanceState`` on the wire, and a row is keyed by the member
    name the renderer looks up, not by the tag it writes. ``DescribeInstanceStatus`` has a
    member genuinely called ``InstanceState``, so the two reads differ here by the model.
    """
    row: dict[str, Any] = {
        "InstanceId": ids.resource_id(resource),
        "InstanceType": INSTANCE_TYPES_BY_SKU[resource.sku_id],
        "State": _instance_state(),
        "Placement": {"AvailabilityZone": _availability_zone(resource)},
        "PrivateIpAddress": _private_ip(resource.identity.uuid),
        "Tags": _tag_set(resource),
    }
    if launched is not None:
        row["LaunchTime"] = launched
    return row


def _reservation(resource: Resource, instance: dict[str, Any]) -> dict[str, Any]:
    """One ``Reservations`` entry: the account that owns the instance, and the instance."""
    return {
        "ReservationId": f"r-{arns.stable_digest(resource.identity.uuid, 17)}",
        "OwnerId": resource.parent_scope_id,
        "Instances": [instance],
    }


def _volume(resource: Resource, created: datetime | None) -> dict[str, Any]:
    """One ``Volumes`` entry for an estate EBS volume."""
    row: dict[str, Any] = {
        "VolumeId": ids.resource_id(resource),
        "VolumeType": VOLUME_TYPES_BY_SKU[resource.sku_id],
        "Size": VOLUME_SIZES_GB[_bucket(f"{resource.identity.uuid}:size", len(VOLUME_SIZES_GB))],
        "State": VOLUME_STATE,
        "AvailabilityZone": _availability_zone(resource),
        "Encrypted": True,
        "Tags": _tag_set(resource),
    }
    if created is not None:
        row["CreateTime"] = created
    return row


def _vpc(resource: Resource) -> dict[str, Any]:
    """One ``Vpcs`` entry for an estate VPC."""
    return {
        "VpcId": ids.resource_id(resource),
        "CidrBlock": VPC_CIDRS[_bucket(f"{resource.identity.uuid}:cidr", len(VPC_CIDRS))],
        "State": VPC_STATE,
        "IsDefault": False,
        "InstanceTenancy": INSTANCE_TENANCY,
        "OwnerId": resource.parent_scope_id,
        "Tags": _tag_set(resource),
    }


def _security_group(resource: Resource) -> dict[str, Any]:
    """One ``SecurityGroups`` entry for an estate security group.

    ``GroupId`` is the derived AWS id and ``GroupName`` the estate's own name, because those
    are two different members in AWS: an id AWS assigned, and the name the owner chose. A
    group is selected by either (see :func:`_kept`), so a caller holding one of them still
    reaches the row.
    """
    return {
        "GroupId": ids.resource_id(resource),
        "GroupName": resource.resource_name,
        "SecurityGroupArn": arns.resource_arn(resource),
        "OwnerId": resource.parent_scope_id,
        "Tags": _tag_set(resource),
    }


def _nat_gateway(resource: Resource, created: datetime | None) -> dict[str, Any]:
    """One ``NatGateways`` entry for an estate NAT gateway."""
    row: dict[str, Any] = {
        "NatGatewayId": ids.resource_id(resource),
        "State": NAT_GATEWAY_STATE,
        "ConnectivityType": CONNECTIVITY_TYPES[
            _bucket(f"{resource.identity.uuid}:connectivity", len(CONNECTIVITY_TYPES))
        ],
        "Tags": _tag_set(resource),
    }
    if created is not None:
        row["CreateTime"] = created
    return row


def _address(resource: Resource) -> dict[str, Any]:
    """One ``Addresses`` entry for an estate elastic IP."""
    return {
        "AllocationId": ids.resource_id(resource),
        "PublicIp": _public_ip(resource.identity.uuid),
        "Domain": ADDRESS_DOMAIN,
        "Tags": _tag_set(resource),
    }


def reservations(
    estate: CanonicalEstate,
    instance_ids: Iterable[str] | None = None,
) -> tuple[dict[str, Any], ...]:
    """One ``Reservations`` entry per instance the estate carries, ordered by instance id.

    The estate models no reservation, so one is synthesized **per instance** rather than
    per account. A reservation groups the instances launched together, and one entry per
    account would assert exactly that; one instance per reservation asserts nothing beyond
    the instance, which the estate does vouch for.
    """
    launched = scope.first_charge(estate)
    selection = _selection(instance_ids)
    return tuple(
        _reservation(resource, _instance(resource, launched.get(resource.identity.uuid)))
        for resource in _of_type(estate, INSTANCE)
        if _kept(selection, ids.resource_id(resource))
    )


def instance_statuses(
    estate: CanonicalEstate,
    instance_ids: Iterable[str] | None = None,
) -> tuple[dict[str, Any], ...]:
    """One ``InstanceStatuses`` entry per instance, from the same rows as ``reservations``.

    Both operations walk the estate's ``ec2_instance`` resources, so an instance cannot be
    running for ``DescribeInstances`` and missing from ``DescribeInstanceStatus``. The check
    passes: the sim's estate is a healthy baseline, which is what ``ok`` means here.
    """
    selection = _selection(instance_ids)
    return tuple(
        {
            "InstanceId": ids.resource_id(resource),
            "AvailabilityZone": _availability_zone(resource),
            "InstanceState": _instance_state(),
            "InstanceStatus": _status_summary(),
            "SystemStatus": _status_summary(),
        }
        for resource in _of_type(estate, INSTANCE)
        if _kept(selection, ids.resource_id(resource))
    )


def volumes(
    estate: CanonicalEstate,
    volume_ids: Iterable[str] | None = None,
) -> tuple[dict[str, Any], ...]:
    """Every EBS volume the estate carries, ordered by volume id."""
    created = scope.first_charge(estate)
    selection = _selection(volume_ids)
    return tuple(
        _volume(resource, created.get(resource.identity.uuid))
        for resource in _of_type(estate, VOLUME)
        if _kept(selection, ids.resource_id(resource))
    )


def vpcs(estate: CanonicalEstate, vpc_ids: Iterable[str] | None = None) -> tuple[dict[str, Any], ...]:
    """Every VPC the estate carries, ordered by VPC id."""
    selection = _selection(vpc_ids)
    return tuple(
        _vpc(resource)
        for resource in _of_type(estate, VPC)
        if _kept(selection, ids.resource_id(resource))
    )


def security_groups(
    estate: CanonicalEstate,
    group_names: Iterable[str] | None = None,
) -> tuple[dict[str, Any], ...]:
    """Every security group the estate carries, ordered by group id.

    ``DescribeSecurityGroups`` selects by id or by name, and both work here because a row
    carries both members: its ``GroupId`` is the derived AWS id and its ``GroupName`` the
    estate's own name. The two are genuinely different values — a name is reused across
    scopes, an id is not — so the group a caller names is the one it gets.
    """
    selection = _selection(group_names)
    return tuple(
        _security_group(resource)
        for resource in _of_type(estate, SECURITY_GROUP)
        if _kept(selection, ids.resource_id(resource), resource.resource_name)
    )


def nat_gateways(
    estate: CanonicalEstate,
    nat_gateway_ids: Iterable[str] | None = None,
) -> tuple[dict[str, Any], ...]:
    """Every NAT gateway the estate carries, ordered by gateway id."""
    created = scope.first_charge(estate)
    selection = _selection(nat_gateway_ids)
    return tuple(
        _nat_gateway(resource, created.get(resource.identity.uuid))
        for resource in _of_type(estate, NAT_GATEWAY)
        if _kept(selection, ids.resource_id(resource))
    )


def addresses(
    estate: CanonicalEstate,
    allocation_ids: Iterable[str] | None = None,
) -> tuple[dict[str, Any], ...]:
    """Every elastic IP the estate carries, ordered by allocation id."""
    selection = _selection(allocation_ids)
    return tuple(
        _address(resource)
        for resource in _of_type(estate, ELASTIC_IP)
        if _kept(selection, ids.resource_id(resource))
    )


def route_tables(
    estate: CanonicalEstate,
    route_table_ids: Iterable[str] | None = None,
) -> tuple[dict[str, Any], ...]:
    """Always empty: the estate models no route table.

    A route table exists to say where traffic goes, so inventing one would invent a route
    from a subnet to a NAT gateway that no estate row records — a fabricated dependency
    graph, which is a worse answer than none. Absence is the answer.

    The selector is accepted and unused for the same reason the other projections take one:
    every read has the same call shape, and there is no row here for a selector to narrow.
    """
    return ()


def regions(
    estate: CanonicalEstate,
    region_names: Iterable[str] | None = None,
) -> tuple[dict[str, Any], ...]:
    """One ``Regions`` entry per region the estate's AWS resources live in.

    The distinct ``region_id`` values of the estate's own resources, not a static AWS
    catalog: a hard-coded list would report regions this estate has nothing in, and
    FinOps scans whatever ``DescribeRegions`` tells it exists.
    """
    selection = _selection(region_names)
    return tuple(
        {
            "RegionName": region_id,
            "Endpoint": f"ec2.{region_id}.amazonaws.com",
            "OptInStatus": OPT_IN_NOT_REQUIRED,
        }
        for region_id in sorted({resource.region_id for resource in scope.resources(estate)})
        if _kept(selection, region_id)
    )


def vpc_attribute(estate: CanonicalEstate, vpc_id: str, attribute: str) -> dict[str, Any] | None:
    """``{VpcId, <Attribute>: {"Value": True}}`` for one of the estate's VPCs.

    ``attribute`` must be one of :data:`VPC_ATTRIBUTES`; the caller validates it first, so an
    unrecognized name fails there with AWS's own code instead of leaking a ``KeyError``.
    ``None`` means the estate has no such VPC, which is a different error again — a caller
    that confused the two would report a missing VPC as a bad attribute name. The id is the
    same one ``DescribeVpcs`` reports, so a caller can ask about the VPC it was just served.
    """
    member = VPC_ATTRIBUTES[attribute]
    for resource in _of_type(estate, VPC):
        if ids.resource_id(resource) == vpc_id:
            return {"VpcId": vpc_id, member: _attribute_value()}
    return None
