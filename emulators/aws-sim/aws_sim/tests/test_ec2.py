"""EC2 (the ``ec2`` protocol) tests, driven by botocore in BOTH directions.

Hand-writing either side of this protocol would let a wrong guess pass, because every one of
its traps is silent:

* the response has no ``<{Operation}Result>`` wrapper and its tags are the model's own names
  (``<vpcId>``, ``<reservationSet>``), so a member written the Query way is not an error — it
  is a member the parser never looks up and the caller never sees;
* a request encodes a list as ``InstanceId.1``, not as the Query protocol's
  ``InstanceIds.member.1``.

So the form body is built by ``EC2Serializer`` — what a boto3 client actually sends — and the
answer is read back with ``create_parser("ec2")``, the parser the real client uses. Were the
envelope wrong, the parsed dict would come back empty or short with no error at all, which is
what these assertions catch.

The load-bearing assertions are derivation and identity: every row has to come from the
estate's own resource of that type, and the id read here has to be the one the Resource Groups
Tagging API builds its ARN from (``test_resourcegroupstaggingapi.py`` asserts the other half
of that pair). A hard-coded row could hold neither.

**Which id.** The id a row reports is the resource's own AWS id (``aws_sim.ids``) and not
``Resource.resource_name``: the estate reuses a name across scopes (18 EC2 instances, 11
distinct names in the small profile) while an ``InstanceId`` carries no scope, so a row named
after the resource would answer ONE id for every instance sharing the name — which is exactly
what made the CloudWatch shim resolve several instances to one series. So the assertions below
are on the derived id, its uniqueness across the estate, and the fact that a selector narrows
to the ONE resource it names; :func:`test_the_ec2_id_is_the_one_the_tagging_api_reports` adds
the two-same-named-instances proof.
"""

from __future__ import annotations

from datetime import UTC, datetime, time
from typing import Any

import botocore.session
from botocore.parsers import create_parser
from botocore.serialize import create_serializer

from aws_sim import arns, ids, scope

_MODEL = botocore.session.get_session().get_service_model("ec2")
_PARSER = create_parser("ec2")
_SERIALIZER = create_serializer("ec2")
_TAGGING_MODEL = botocore.session.get_session().get_service_model("resourcegroupstaggingapi")
_JSON_PARSER = create_parser("json")

#: CloudWatch is reached through the SAME endpoint (``api/app.py``: one endpoint, the protocol
#: told apart by the target prefix), so the metric half of the id proof needs nothing but the
#: client the rest of this module already has.
_CLOUDWATCH_MODEL = botocore.session.get_session().get_service_model("cloudwatch")
_CLOUDWATCH_SERIALIZER = create_serializer("json")
_CLOUDWATCH_PARSER = create_parser("json")


def _form(operation: str, **params: Any) -> dict[str, str]:
    """The form body a botocore EC2 client sends for ``operation``.

    Built by the serializer rather than by hand, so a test can never encode a parameter the
    emulator would never receive — which is the trap the emulator has to survive.
    """
    request = _SERIALIZER.serialize_to_request(params, _MODEL.operation_model(operation))
    return {key: str(value) for key, value in request["body"].items()}


def _parse(client, operation: str, **params: Any):
    """POST an ec2-protocol request (built by botocore) and parse it the way the client does."""
    response = client.post("/", data=_form(operation, **params))
    raw = {"status_code": response.status_code, "headers": dict(response.headers), "body": response.content}
    return _PARSER.parse(raw, _MODEL.operation_model(operation).output_shape)


def _estate(app, resource_type: str):
    """The estate's resources of one type, in the order the projections order them."""
    return sorted(
        (r for r in scope.resources(app.state.estate) if r.resource_type == resource_type),
        key=lambda r: r.resource_name,
    )


def _tagged_resources(client) -> dict[str, list[dict[str, str]]]:
    """Every ARN the tagging API reports, mapped to its tags."""
    target = f"{_TAGGING_MODEL.metadata['targetPrefix']}.GetResources"
    response = client.post("/", content="{}", headers={"X-Amz-Target": target})
    raw = {"status_code": response.status_code, "headers": dict(response.headers), "body": response.content}
    parsed = _JSON_PARSER.parse(raw, _TAGGING_MODEL.operation_model("GetResources").output_shape)
    return {row["ResourceARN"]: row["Tags"] for row in parsed["ResourceTagMappingList"]}


def _same_named_pair(resources) -> tuple[Any, Any] | None:
    """The first two resources that SHARE a ``resource_name`` in different scopes."""
    seen: dict[str, Any] = {}
    for resource in resources:
        other = seen.get(resource.resource_name)
        if other is not None and other.parent_scope_id != resource.parent_scope_id:
            return other, resource
        seen.setdefault(resource.resource_name, resource)
    return None


def _cpu_percentiles(client, app, instance_id: str) -> list[float]:
    """The estate's CPU series as CloudWatch answers a query for ONE instance id.

    The query is the one ``cloudwatch_metrics_provider.py (modulo do consumidor)`` sends
    (``AWS/EC2`` + ``CPUUtilization`` + the ``InstanceId`` dimension, ``Period=3600``, p95),
    built and parsed by botocore so the assertion is on the wire rather than on a projection
    call. Its window is the estate's own: the series only carries samples the estate metered.
    """
    estate = app.state.estate
    request = _CLOUDWATCH_SERIALIZER.serialize_to_request(
        {
            "MetricDataQueries": [
                {
                    "Id": "cpu_p95",
                    "MetricStat": {
                        "Metric": {
                            "Namespace": "AWS/EC2",
                            "MetricName": "CPUUtilization",
                            "Dimensions": [{"Name": "InstanceId", "Value": instance_id}],
                        },
                        "Period": 3600,
                        "Stat": "p95",
                        "Unit": "Percent",
                    },
                },
            ],
            "StartTime": datetime.combine(estate.sim_start, time(0, 0), tzinfo=UTC),
            "EndTime": datetime.combine(estate.sim_now, time(0, 0), tzinfo=UTC),
        },
        _CLOUDWATCH_MODEL.operation_model("GetMetricData"),
    )
    response = client.post(request["url_path"], content=request["body"], headers=request["headers"])
    raw = {"status_code": response.status_code, "headers": dict(response.headers), "body": response.content}
    parsed = _CLOUDWATCH_PARSER.parse(raw, _CLOUDWATCH_MODEL.operation_model("GetMetricData").output_shape)
    return list(parsed["MetricDataResults"][0]["Values"])


def test_describe_instances_derives_from_the_estate(api_client) -> None:
    """The members sit directly under the response element, and the request id is ``requestId``.

    The parse is the proof rather than a reading of the XML: ``EC2QueryParser`` collects an
    operation's members from the **root's** children, so a result wrapped in
    ``<DescribeInstancesResult>`` parses to an empty dict, and the Query envelope's
    ``<ResponseMetadata><RequestId>`` parses to a result with no ``ResponseMetadata`` at all.
    Neither raises, so only the parse distinguishes them.
    """
    client, app = api_client
    expected = _estate(app, "ec2_instance")
    accounts = {r.parent_scope_id for r in expected}
    regions = {r.region_id for r in expected}

    parsed = _parse(client, "DescribeInstances")
    instances = [row for reservation in parsed["Reservations"] for row in reservation["Instances"]]

    assert [row["InstanceId"] for row in instances] == [ids.resource_id(r) for r in expected]
    assert parsed["ResponseMetadata"]["RequestId"], "only a lowercase <requestId> is read"
    assert "NextToken" not in parsed, "the estate is one page, so the paginator stops"

    for reservation in parsed["Reservations"]:
        assert reservation["OwnerId"] in accounts
        assert reservation["ReservationId"].startswith("r-")
        assert len(reservation["Instances"]) == 1, "one instance per reservation asserts no grouping"

    for row, resource in zip(instances, expected, strict=True):
        assert row["State"] == {"Code": 16, "Name": "running"}
        assert row["InstanceType"] == "m5.large", "read out of the SKU, not invented"
        assert row["Placement"]["AvailabilityZone"][:-1] in regions
        assert row["PrivateIpAddress"].startswith("10.")
        assert row["Tags"] == [{"Key": k, "Value": v} for k, v in resource.tags]
        assert isinstance(row["LaunchTime"], datetime), "the earliest billed day"

    # The estate reuses a name across accounts, and one endpoint serves them all — but the id
    # is derived from the resource's identity rather than from its name, so a selector comes
    # back with exactly the one instance it named. Were the projection still keyed on
    # ``resource_name`` this would return every instance sharing the name.
    one = ids.resource_id(expected[0])
    narrowed = [
        row
        for reservation in _parse(client, "DescribeInstances", InstanceIds=[one])["Reservations"]
        for row in reservation["Instances"]
    ]
    assert [row["InstanceId"] for row in narrowed] == [one]
    assert len(narrowed) < len(instances), "the selector narrowed the answer, so InstanceId.1 was read"


def test_describe_instance_status_agrees_with_describe_instances(api_client) -> None:
    """Both reads walk the same estate rows, so an instance cannot be missing from one."""
    client, app = api_client

    installed = [
        row
        for reservation in _parse(client, "DescribeInstances")["Reservations"]
        for row in reservation["Instances"]
    ]
    statuses = _parse(client, "DescribeInstanceStatus")["InstanceStatuses"]

    assert [row["InstanceId"] for row in statuses] == [row["InstanceId"] for row in installed]
    for row in statuses:
        assert row["InstanceState"]["Name"] == "running"
        assert row["InstanceStatus"]["Status"] == "ok"
        assert row["SystemStatus"]["Details"][0]["Name"] == "reachability"

    # ``InstanceIds`` reaches the emulator as ``InstanceId.1``, not as the Query protocol's
    # ``InstanceIds.member.1``; were it the latter the selector would match nothing and this
    # would return every instance instead of one id's worth.
    one = installed[0]["InstanceId"]
    narrowed = _parse(client, "DescribeInstanceStatus", InstanceIds=[one])["InstanceStatuses"]
    assert 0 < len(narrowed) < len(statuses)
    assert {row["InstanceId"] for row in narrowed} == {one}


def test_describe_volumes_addresses_and_nat_gateways_derive_from_the_estate(api_client) -> None:
    """Three inventory types, each row from its own estate resource and nothing else."""
    client, app = api_client

    volumes = _parse(client, "DescribeVolumes")["Volumes"]
    expected_volumes = _estate(app, "ebs_volume")
    assert [row["VolumeId"] for row in volumes] == [ids.resource_id(r) for r in expected_volumes]
    for row in volumes:
        assert row["VolumeType"] == "gp3", "read out of the SKU"
        assert row["Size"] > 0
        assert row["State"] == "available"
        assert row["Encrypted"] is True
        assert "Attachments" not in row, "the estate links a volume to nothing"
        assert isinstance(row["CreateTime"], datetime)

    # ``DescribeVolumes`` with ``VolumeIds`` is how the waste executor asks about one volume.
    named = ids.resource_id(expected_volumes[0])
    narrowed = _parse(client, "DescribeVolumes", VolumeIds=[named])["Volumes"]
    assert [row["VolumeId"] for row in narrowed] == [named]
    assert 0 < len(narrowed) < len(volumes), "VolumeIds narrowed the answer, so VolumeId.1 was read"

    addresses = _parse(client, "DescribeAddresses")["Addresses"]
    expected_addresses = _estate(app, "elastic_ip")
    assert [row["AllocationId"] for row in addresses] == [ids.resource_id(r) for r in expected_addresses]
    for row in addresses:
        assert row["Domain"] == "vpc"
        assert row["PublicIp"].startswith("203.0.113."), "TEST-NET-3, so it is never routable"
        assert "AssociationId" not in row, "no estate row records an association"

    gateways = _parse(client, "DescribeNatGateways")["NatGateways"]
    expected_gateways = _estate(app, "nat_gateway")
    assert [row["NatGatewayId"] for row in gateways] == [ids.resource_id(r) for r in expected_gateways]
    for row in gateways:
        assert row["State"] == "available"
        assert row["ConnectivityType"] in {"public", "private"}
        assert "SubnetId" not in row


def test_describe_vpcs_and_security_groups_derive_from_the_estate(api_client) -> None:
    """VPCs, and the groups named either way: ``GroupId`` and ``GroupName`` are two values."""
    client, app = api_client

    vpcs = _parse(client, "DescribeVpcs")["Vpcs"]
    expected_vpcs = _estate(app, "vpc")
    assert [row["VpcId"] for row in vpcs] == [ids.resource_id(r) for r in expected_vpcs]
    for row, resource in zip(vpcs, expected_vpcs, strict=True):
        assert row["CidrBlock"].endswith("/16")
        assert row["State"] == "available"
        assert row["IsDefault"] is False
        assert row["InstanceTenancy"] == "default"
        assert row["OwnerId"] == resource.parent_scope_id
        assert row["Tags"] == [{"Key": k, "Value": v} for k, v in resource.tags]

    groups = _parse(client, "DescribeSecurityGroups")["SecurityGroups"]
    expected_groups = _estate(app, "security_group")
    assert [row["GroupId"] for row in groups] == [ids.resource_id(r) for r in expected_groups]
    for row, resource in zip(groups, expected_groups, strict=True):
        assert row["GroupName"] == resource.resource_name, "the name stays the estate's display name"
        assert row["GroupId"] != row["GroupName"], "the id is the derived one, not the reused name"
        assert row["SecurityGroupArn"].startswith("arn:aws:ec2:")
        assert row["SecurityGroupArn"].endswith(f"security-group/{row['GroupId']}")
        assert "IpPermissions" not in row, "the estate models no rule, so none is claimed"

    # A group is named by id or by name, and the two must select the same ONE row. ``GroupIds``
    # carries a lowercase ``groupId`` location name that EC2 capitalizes on input, so this is
    # also where the derived element name is proved.
    group = expected_groups[0]
    wanted = [ids.resource_id(group)]
    by_name = _parse(client, "DescribeSecurityGroups", GroupNames=[group.resource_name])["SecurityGroups"]
    by_id = _parse(client, "DescribeSecurityGroups", GroupIds=[wanted[0]])["SecurityGroups"]
    assert [row["GroupId"] for row in by_name] == wanted
    assert [row["GroupId"] for row in by_id] == wanted
    assert 0 < len(by_id) < len(groups), "the selector narrowed the answer, so GroupId.1 was read"


def test_describe_vpc_attribute_answers_only_the_requested_attribute(api_client) -> None:
    """One attribute per call, in the model's own ``AttributeBooleanValue`` shape."""
    client, app = api_client
    vpc = _estate(app, "vpc")[0]
    vpc_id = ids.resource_id(vpc)

    for attribute in ("enableDnsSupport", "enableDnsHostnames"):
        parsed = _parse(client, "DescribeVpcAttribute", VpcId=vpc_id, Attribute=attribute)
        member = f"Enable{attribute.removeprefix('enable')}"
        assert parsed["VpcId"] == vpc_id
        assert parsed[member] == {"Value": True}
        assert [key for key in parsed if key not in {"VpcId", "ResponseMetadata"}] == [member]


def test_the_ec2_id_is_the_one_the_tagging_api_reports(api_client) -> None:
    """One resource, one ARN, one series: the id here, the tagging API's ARN, and CloudWatch.

    FinOps rebuilds an ARN from region + account + id — ``security (modulo do consumidor)``
    builds ``arn:aws:ec2:<region>:<OwnerId>:security-group/<GroupId>`` — so an id that is not
    the ARN's resource part would give one resource two identities. The group is where that
    can be checked without leaving the wire, because the response carries the id, the account
    and the ARN together; the instance only carries the id, so there the ARN is traced back
    through the estate.

    The **collision** half is the telemetry-correlation bug this id was derived for: the estate
    reuses ``resource_name`` across scopes (18 EC2 instances carry 11 names), and while the id
    a projection answered WAS that name, two instances in two accounts resolved to ONE
    CloudWatch series — the shim matched the first name it found, so the rightsizing path
    judged several instances on whichever samples came back first. The pair below settles it:
    two same-named instances answer DIFFERENT ids, each id yields a non-empty CPU read, and
    the two reads are different samples.
    """
    client, app = api_client
    tagged = _tagged_resources(client)
    expected = _estate(app, "ec2_instance")
    assert expected and tagged

    described = {
        row["InstanceId"]
        for reservation in _parse(client, "DescribeInstances")["Reservations"]
        for row in reservation["Instances"]
    }
    assert described == {ids.resource_id(r) for r in expected}
    for resource in expected:
        arn = arns.resource_arn(resource)
        assert arn in tagged, f"{resource.resource_name} is missing from the tagging API's answer"
        assert arn.split(":")[-1] == f"instance/{ids.resource_id(resource)}", "the id is the ARN's resource part"

    # Two different resources that share a name, in different scopes.
    pair = _same_named_pair(expected)
    assert pair is not None, "the estate reuses an instance name across accounts"
    first, second = pair
    assert first.parent_scope_id != second.parent_scope_id
    assert first.resource_name == second.resource_name
    first_id, second_id = ids.resource_id(first), ids.resource_id(second)
    assert first_id != second_id, "two instances with one name must not answer one id"
    assert {first_id, second_id} <= described

    first_cpu = _cpu_percentiles(client, app, first_id)
    second_cpu = _cpu_percentiles(client, app, second_id)
    assert first_cpu and second_cpu, "each instance's own id must return ITS series"
    assert first_cpu != second_cpu, "one name, two instances, two series — not the first match twice"

    groups = _parse(client, "DescribeSecurityGroups")["SecurityGroups"]
    assert groups
    for row in groups:
        assert row["SecurityGroupArn"] in tagged
        region = row["SecurityGroupArn"].split(":")[3]
        rebuilt = f"arn:aws:ec2:{region}:{row['OwnerId']}:security-group/{row['GroupId']}"
        assert row["SecurityGroupArn"] == rebuilt


def test_describe_regions_lists_the_regions_the_estate_uses(api_client) -> None:
    """The distinct ``region_id`` values of the estate's own resources."""
    client, app = api_client
    expected = sorted({r.region_id for r in scope.resources(app.state.estate)})

    parsed = _parse(client, "DescribeRegions")["Regions"]
    assert [row["RegionName"] for row in parsed] == expected
    for row in parsed:
        assert row["Endpoint"] == f"ec2.{row['RegionName']}.amazonaws.com"
        assert row["OptInStatus"] == "opt-in-not-required"

    only = _parse(client, "DescribeRegions", RegionNames=[expected[0]])["Regions"]
    assert [row["RegionName"] for row in only] == [expected[0]]


def test_a_resource_type_the_estate_has_none_of_answers_empty(api_client) -> None:
    """A type the estate does not model yields an empty list — never a placeholder row."""
    client, app = api_client
    assert not [r for r in scope.resources(app.state.estate) if r.resource_type == "route_table"]

    parsed = _parse(client, "DescribeRouteTables")
    assert parsed["RouteTables"] == []
    assert parsed["ResponseMetadata"]["RequestId"]


def test_filters_and_unknown_attributes_are_refused(api_client) -> None:
    """A narrowing the estate cannot answer is refused, not answered with everything."""
    client, app = api_client

    filtered = _parse(client, "DescribeVolumes", Filters=[{"Name": "status", "Values": ["available"]}])
    assert filtered["Error"]["Code"] == "InvalidParameterValue"

    unknown_attribute = _parse(
        client,
        "DescribeVpcAttribute",
        VpcId=ids.resource_id(_estate(app, "vpc")[0]),
        Attribute="enableSomethingElse",
    )
    assert unknown_attribute["Error"]["Code"] == "InvalidParameterValue"

    missing_vpc = _parse(client, "DescribeVpcAttribute", VpcId="vpc-nope", Attribute="enableDnsSupport")
    assert missing_vpc["Error"]["Code"] == "InvalidVpcID.NotFound"

    unsupported = _parse(client, "DescribeAvailabilityZones")
    assert unsupported["Error"]["Code"] == "InvalidAction"
