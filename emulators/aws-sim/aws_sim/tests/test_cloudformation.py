"""CloudFormation Query-protocol tests, parsed with botocore's own parser.

The value of parsing through ``botocore.parsers`` rather than reading the XML by hand is
that a hand-written envelope cannot pass by accident: this is the parser the real client
runs, and the two failures the design flags are both *silent* ones — a flattened list
parses to ``[]`` with no error, and a property blob emitted as an object parses to
garbage. Asserting the shape of my own XML would have caught neither.
"""

from __future__ import annotations

import json

import botocore.session
from botocore.parsers import create_parser

from aws_sim import query_xml
from aws_sim.api.cloudformation import supported_actions

_MODEL = botocore.session.get_session().get_service_model("cloudformation")
_PARSER = create_parser("query")


def _parse(client, operation: str, **params):
    """POST a Query-protocol request and parse the response the way the client does."""
    form = {"Action": operation, "Version": query_xml.api_version(), **params}
    response = client.post("/", data=form)
    raw = {
        "status_code": response.status_code,
        "headers": dict(response.headers),
        "body": response.content,
    }
    shape = _MODEL.operation_model(operation).output_shape
    if response.status_code != 200:
        return _PARSER._do_error_parse(raw, shape)
    return _PARSER.parse(raw, shape)


def _first_stack(client):
    stacks = _parse(client, "ListStacks")["StackSummaries"]
    assert stacks, "the small estate has AWS accounts with IaC snapshots"
    return stacks[0]


def test_api_version_matches_the_service_model() -> None:
    """The version the emulator accepts is the one botocore says the API uses."""
    assert query_xml.api_version() == "2010-05-15"


def test_serves_only_the_five_drift_operations() -> None:
    """The slice boundary, pinned: the stack-set operations are the second slice."""
    assert supported_actions() == (
        "DescribeStackDriftDetectionStatus",
        "DescribeStackResourceDrifts",
        "DetectStackDrift",
        "ListStackResources",
        "ListStacks",
    )


def test_healthz(api_client) -> None:
    client, _ = api_client
    assert client.get("/healthz").json() == {"status": "ok", "synthetic": True}


def test_list_stacks_parses_through_botocore(api_client) -> None:
    """Non-flattened lists need `<member>`; a flattened emitter yields an empty list."""
    client, _ = api_client
    parsed = _parse(client, "ListStacks")
    stacks = parsed["StackSummaries"]
    assert len(stacks) >= 1
    for stack in stacks:
        assert stack["StackName"].startswith("synth-")
        assert stack["StackId"].startswith("arn:aws:cloudformation:")
        assert stack["StackStatus"] == "CREATE_COMPLETE"
        assert stack["DriftInformation"]["StackDriftStatus"] in {"DRIFTED", "IN_SYNC"}
        assert stack["CreationTime"] is not None


def test_detect_then_describe_drift_round_trips(api_client) -> None:
    """``DetectStackDrift``'s id is what ``DescribeStackDriftDetectionStatus`` takes."""
    client, _ = api_client
    stack = _first_stack(client)

    detected = _parse(client, "DetectStackDrift", StackName=stack["StackName"])
    detection_id = detected["StackDriftDetectionId"]
    assert detection_id

    status = _parse(client, "DescribeStackDriftDetectionStatus", StackDriftDetectionId=detection_id)
    assert status["DetectionStatus"] == "DETECTION_COMPLETE"
    assert status["StackId"] == stack["StackId"]
    assert status["StackDriftStatus"] in {"DRIFTED", "IN_SYNC"}
    # integer, not a string: the model types it as integer and botocore must coerce it.
    assert isinstance(status["DriftedStackResourceCount"], int)


def test_stack_name_and_arn_are_both_accepted(api_client) -> None:
    """FinOps may pass either; the ARN resolves to the same stack."""
    client, _ = api_client
    stack = _first_stack(client)
    by_arn = _parse(client, "DetectStackDrift", StackName=stack["StackId"])
    assert by_arn["StackDriftDetectionId"] == _parse(
        client, "DetectStackDrift", StackName=stack["StackName"]
    )["StackDriftDetectionId"]


def test_resource_drifts_carry_json_strings_not_objects(api_client) -> None:
    """Design sec. 22.2: the model types both as `string`, so both must be strings.

    An object here parses to garbage in the client, and `drift_detector.py`'s ``[:500]``
    slicing would raise — so this assertion is the difference between a working drift
    screen and a ``TypeError``.
    """
    client, _ = api_client
    stack = _first_stack(client)
    drifts = _parse(client, "DescribeStackResourceDrifts", StackName=stack["StackName"])["StackResourceDrifts"]
    assert drifts, "a stack has resources"
    for drift in drifts:
        assert isinstance(drift["ExpectedProperties"], str)
        assert isinstance(drift["ActualProperties"], str)
        assert isinstance(json.loads(drift["ExpectedProperties"]), dict)
        assert isinstance(json.loads(drift["ActualProperties"]), dict)
        assert drift["StackResourceDriftStatus"] in {"IN_SYNC", "MODIFIED"}
        assert drift["StackId"] == stack["StackId"]


def test_drifted_count_matches_the_reported_drifts(api_client) -> None:
    """Coherence by construction: the count and the rows cannot disagree."""
    client, _ = api_client
    stack = _first_stack(client)
    drifts = _parse(client, "DescribeStackResourceDrifts", StackName=stack["StackName"])["StackResourceDrifts"]
    drifted = [row for row in drifts if row["StackResourceDriftStatus"] != "IN_SYNC"]

    status = _parse(
        client,
        "DescribeStackDriftDetectionStatus",
        StackDriftDetectionId=_parse(client, "DetectStackDrift", StackName=stack["StackName"])[
            "StackDriftDetectionId"
        ],
    )
    assert status["DriftedStackResourceCount"] == len(drifted)
    assert status["StackDriftStatus"] == ("DRIFTED" if drifted else "IN_SYNC")


def test_list_stack_resources(api_client) -> None:
    client, _ = api_client
    stack = _first_stack(client)
    summaries = _parse(client, "ListStackResources", StackName=stack["StackName"])["StackResourceSummaries"]
    assert summaries
    for summary in summaries:
        assert summary["LogicalResourceId"]
        assert summary["PhysicalResourceId"]
        assert summary["ResourceType"]
        assert summary["DriftInformation"]["StackResourceDriftStatus"] in {"IN_SYNC", "MODIFIED"}


def test_only_aws_resources_appear(api_client) -> None:
    """The provider boundary, applied to this sim (the G12 discipline).

    The estate really is multi-cloud, or this test would pass on an empty set.
    """
    client, app = api_client
    estate = app.state.estate
    aws = {r.identity.uuid for r in estate.resources if r.identity.provider == "aws"}
    foreign = {r.identity.uuid for r in estate.resources if r.identity.provider != "aws"}
    assert aws and foreign, "the estate must be multi-cloud for this test to mean anything"

    seen: set[str] = set()
    for stack in _parse(client, "ListStacks")["StackSummaries"]:
        seen.update(
            row["PhysicalResourceId"]
            for row in _parse(client, "DescribeStackResourceDrifts", StackName=stack["StackName"])[
                "StackResourceDrifts"
            ]
        )
    assert seen <= aws
    assert not (seen & foreign)


def test_unknown_action_is_an_invalid_action_error(api_client) -> None:
    """A stack-set operation is refused by name, not with a bare 404."""
    client, _ = api_client
    error = _parse(client, "CreateStackSet", StackSetName="x")
    assert error["Error"]["Code"] == "InvalidAction"
    assert "CreateStackSet" in error["Error"]["Message"]


def test_wrong_api_version_is_rejected(api_client) -> None:
    client, _ = api_client
    response = client.post("/", data={"Action": "ListStacks", "Version": "1999-01-01"})
    assert response.status_code == 400
    error = _PARSER._do_error_parse(
        {"status_code": 400, "headers": dict(response.headers), "body": response.content},
        None,
    )
    assert error["Error"]["Code"] == "InvalidParameterValue"


def test_missing_parameter_is_rejected(api_client) -> None:
    client, _ = api_client
    error = _parse(client, "ListStackResources")
    assert error["Error"]["Code"] == "MissingParameter"


def test_unknown_stack_is_a_validation_error(api_client) -> None:
    """CloudFormation's own code for a stack that does not exist."""
    client, _ = api_client
    error = _parse(client, "ListStackResources", StackName="synth-000000000000")
    assert error["Error"]["Code"] == "ValidationError"
    assert "does not exist" in error["Error"]["Message"]


def test_missing_action_is_rejected(api_client) -> None:
    client, _ = api_client
    response = client.post("/", data={"Version": query_xml.api_version()})
    assert response.status_code == 400
    assert b"MissingParameter" in response.content
