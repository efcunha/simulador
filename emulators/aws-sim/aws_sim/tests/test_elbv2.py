"""ELBv2 Query-protocol tests, parsed with botocore's own parser.

The load-bearing assertion is coherence between the two operations FinOps ALB
collector calls in sequence: the ``LoadBalancerArn`` from ``DescribeLoadBalancers`` must
be the ``ResourceArn`` of ``DescribeTags`` for the same balancer, and the tags must be the
estate's own pairs. Two independent fixtures could not hold that.

``LoadBalancerName`` is asserted to be the resource's derived AWS id (``aws_sim.ids``) — the
name the ARN carries — rather than the estate's display name, which is reused across scopes.
"""

from __future__ import annotations

import botocore.session
from botocore.parsers import create_parser

from aws_sim import arns, ids, scope

_MODEL = botocore.session.get_session().get_service_model("elbv2")
_TAGGING_MODEL = botocore.session.get_session().get_service_model("resourcegroupstaggingapi")
_PARSER = create_parser("query")
_JSON_PARSER = create_parser("json")

SCHEMES = ("internet-facing", "internal")


def _parse(client, operation: str, **params: str):
    """POST an ELBv2 Query-protocol request and parse it the way the client does."""
    form = {"Action": operation, "Version": _MODEL.api_version, **params}
    response = client.post("/", data=form)
    raw = {"status_code": response.status_code, "headers": dict(response.headers), "body": response.content}
    shape = _MODEL.operation_model(operation).output_shape
    if response.status_code != 200:
        return _PARSER._do_error_parse(raw, shape)
    return _PARSER.parse(raw, shape)


def _tagged_resources(client) -> dict[str, list[dict[str, str]]]:
    """Every ARN the tagging API reports, mapped to its tags."""
    target = f"{_TAGGING_MODEL.metadata['targetPrefix']}.GetResources"
    response = client.post("/", content="{}", headers={"X-Amz-Target": target})
    raw = {"status_code": response.status_code, "headers": dict(response.headers), "body": response.content}
    parsed = _JSON_PARSER.parse(raw, _TAGGING_MODEL.operation_model("GetResources").output_shape)
    return {row["ResourceARN"]: row["Tags"] for row in parsed["ResourceTagMappingList"]}


def test_describe_load_balancers_derives_from_the_estate(api_client) -> None:
    client, app = api_client
    expected = sorted(
        (r for r in scope.resources(app.state.estate) if r.resource_type == "application_lb"),
        key=ids.resource_id,
    )
    balancers = _parse(client, "DescribeLoadBalancers")["LoadBalancers"]

    assert [row["LoadBalancerName"] for row in balancers] == [ids.resource_id(r) for r in expected]
    for row in balancers:
        assert row["LoadBalancerArn"].startswith("arn:aws:elasticloadbalancing:")
        assert row["LoadBalancerArn"].split("/")[-2] == row["LoadBalancerName"], "one name, not two"
        assert row["Type"] == "application"
        assert row["State"]["Code"] == "active"
        assert row["Scheme"] in SCHEMES
        assert row["DNSName"].startswith(f"{row['LoadBalancerName']}.")
        assert row["DNSName"].endswith(".elb.amazonaws.com")
        assert row["CreatedTime"] is not None
        assert row["AvailabilityZones"], "a balancer is attached to at least one zone"


def test_naming_arns_narrows_the_answer(api_client) -> None:
    client, _ = api_client
    first = _parse(client, "DescribeLoadBalancers")["LoadBalancers"][0]
    rows = _parse(client, "DescribeLoadBalancers", **{"LoadBalancerArns.member.1": first["LoadBalancerArn"]})[
        "LoadBalancers"
    ]
    assert [row["LoadBalancerArn"] for row in rows] == [first["LoadBalancerArn"]]


def test_describe_tags_returns_the_estates_own_tags(api_client) -> None:
    client, app = api_client
    arn = next(row["LoadBalancerArn"] for row in _parse(client, "DescribeLoadBalancers")["LoadBalancers"])
    resource = next(
        r
        for r in scope.resources(app.state.estate)
        if r.resource_type == "application_lb" and arns.resource_arn(r) == arn
    )
    descriptions = _parse(client, "DescribeTags", **{"ResourceArns.member.1": arn})["TagDescriptions"]

    assert len(descriptions) == 1
    assert descriptions[0]["ResourceArn"] == arn
    assert [(tag["Key"], tag["Value"]) for tag in descriptions[0]["Tags"]] == list(resource.tags)


def test_describe_tags_requires_resource_arns(api_client) -> None:
    client, _ = api_client
    error = _parse(client, "DescribeTags")
    assert error["Error"]["Code"] == "MissingParameter"


def test_the_load_balancer_arn_is_the_one_the_tagging_api_reports(api_client) -> None:
    """The cross-service invariant: one balancer, one ARN, whichever service is asked."""
    client, _ = api_client
    load_balancer_arns = {
        row["LoadBalancerArn"] for row in _parse(client, "DescribeLoadBalancers")["LoadBalancers"]
    }
    tagged = _tagged_resources(client)
    assert load_balancer_arns
    for arn in load_balancer_arns:
        assert arn in tagged, f"{arn} is missing from the tagging API's answer"
        described = _parse(client, "DescribeTags", **{"ResourceArns.member.1": arn})["TagDescriptions"][0]
        assert described["Tags"] == tagged[arn]
