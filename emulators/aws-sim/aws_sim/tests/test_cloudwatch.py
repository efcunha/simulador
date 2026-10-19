"""CloudWatch tests: a REAL boto3 client against a served app, plus the CBOR framing.

The load-bearing test is :func:`test_real_boto3_client_round_trip`: it starts the app on a
real socket and drives it with ``boto3.client("cloudwatch")``, so the request goes through
botocore's own serializer, signer and response parser. A transport error, a content-type
mismatch or a body the parser cannot read fails there — which is exactly what the emulator
must not do.

:func:`test_client_sends_json_1_0_to_the_endpoint_root` pins the *measured* wire the whole
slice is built on. The CloudWatch model declares ``protocol: smithy-rpc-v2-cbor``, which
reads as a hard blocker, but ``metadata.protocols`` also lists ``json`` and
``ServiceModel.resolved_protocol`` returns the first entry of
``PRIORITY_ORDERED_SUPPORTED_PROTOCOLS`` that the service lists — ``json`` precedes
``smithy-rpc-v2-cbor`` there. So the installed client posts JSON-1.0 to the root. If a
future botocore reorders that list, this test fails loudly instead of the emulator silently
serving the wrong framing.
"""

from __future__ import annotations

import json
import socket
import threading
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import boto3
import botocore.session
import pytest
import uvicorn
from botocore.parsers import create_parser
from botocore.serialize import create_serializer

_AWS_CREDENTIALS = {"aws_access_key_id": "x", "aws_secret_access_key": "y"}
_REGION = "us-east-1"

_MODEL = botocore.session.get_session().get_service_model("cloudwatch")

#: The target prefix comes from the model, never hard-coded.
_TARGET_PREFIX = str(_MODEL.metadata["targetPrefix"])


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture(scope="module")
def endpoint_url() -> Any:
    """Serve the app on a real socket for the module, and hand back its endpoint URL.

    A real server rather than a TestClient shim: the point of these tests is that
    botocore's transport, serializer and parser all agree with what the emulator writes on
    the wire, and a shim would bypass the one part that can disagree.
    """
    from aws_sim.api.app import create_app
    from aws_sim.config import load_settings

    app = create_app(load_settings(env={}, SEED="42", PROFILE="small", CURRENCY="USD"))
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 20
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    assert server.started, "the app did not start listening"
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=20)


def _client(endpoint_url: str, **kwargs: Any) -> Any:
    return boto3.client("cloudwatch", endpoint_url=endpoint_url, region_name=_REGION, **_AWS_CREDENTIALS, **kwargs)


# ── the measured wire ─────────────────────────────────────────────────────────


def test_client_sends_json_1_0_to_the_endpoint_root(endpoint_url: str) -> None:
    """The client speaks JSON-1.0 to ``/`` — not CBOR, whatever the model's protocol says."""
    captured: dict[str, Any] = {}

    def _capture(request: Any, **_kwargs: Any) -> None:
        captured["url"] = request.url
        # botocore's prepared request carries raw header values; normalise for comparison.
        captured["headers"] = {
            key: value.decode("utf-8") if isinstance(value, bytes) else value
            for key, value in dict(request.headers).items()
        }
        body = request.body
        captured["body"] = body.decode("utf-8") if isinstance(body, bytes) else body
        return None

    client = _client(endpoint_url)
    client.meta.events.register_first("before-send.cloudwatch.ListMetrics", _capture)
    client.list_metrics(Namespace="AWS/EC2")

    assert captured["headers"]["Content-Type"] == "application/x-amz-json-1.0"
    assert captured["headers"]["X-Amz-Target"] == f"{_TARGET_PREFIX}.ListMetrics"
    assert captured["headers"]["x-amzn-query-mode"] == "true"
    assert json.loads(captured["body"]) == {"Namespace": "AWS/EC2"}
    assert captured["url"].endswith("/")
    assert "/service/" not in captured["url"], "the CBOR transport path must not be used by this client"


def test_resolved_protocol_is_json_despite_the_cbor_declaration() -> None:
    """The fact the dispatch rests on, asserted directly against the model."""
    assert _MODEL.protocol == "smithy-rpc-v2-cbor"
    assert "json" in _MODEL.protocols
    assert _MODEL.resolved_protocol == "json"


# ── the boto3 round trip ──────────────────────────────────────────────────────


def test_real_boto3_client_round_trip(endpoint_url: str) -> None:
    """All three served operations answer a real boto3 client with parsed Python data."""
    client = _client(endpoint_url)

    listed = client.list_metrics(Namespace="AWS/EC2")
    assert listed["ResponseMetadata"]["HTTPStatusCode"] == 200
    assert isinstance(listed["Metrics"], list)

    alarms = client.describe_alarms(StateValue="ALARM", MaxRecords=100)
    assert alarms["ResponseMetadata"]["HTTPStatusCode"] == 200
    assert alarms["MetricAlarms"] == []
    assert alarms["CompositeAlarms"] == []

    end = datetime(2026, 2, 15, tzinfo=UTC)
    metric_data = client.get_metric_data(
        MetricDataQueries=[
            {
                "Id": "cpu_p95",
                "MetricStat": {
                    "Metric": {
                        "Namespace": "AWS/EC2",
                        "MetricName": "CPUUtilization",
                        "Dimensions": [{"Name": "InstanceId", "Value": "i-0000000000"}],
                    },
                    "Period": 3600,
                    "Stat": "p95",
                    "Unit": "Percent",
                },
            },
        ],
        StartTime=end - timedelta(days=30),
        EndTime=end,
    )
    assert metric_data["ResponseMetadata"]["HTTPStatusCode"] == 200
    assert [result["Id"] for result in metric_data["MetricDataResults"]] == ["cpu_p95"]


def test_metric_data_answers_every_query_FinOps_builds(endpoint_url: str) -> None:
    """The exact query set ``cloudwatch_metrics_provider.py (modulo do consumidor)`` sends.

    Four ``MetricStat`` queries over ``AWS/EC2`` and ``CWAgent``, read by ``Id``. Each must
    come back as its own result row: a dropped row is indistinguishable from a dropped
    request to the caller.
    """
    client = _client(endpoint_url)
    end = datetime(2026, 2, 15, tzinfo=UTC)
    queries = [
        {
            "Id": metric_id,
            "MetricStat": {
                "Metric": {
                    "Namespace": namespace,
                    "MetricName": metric_name,
                    "Dimensions": [{"Name": "InstanceId", "Value": "i-1111111111"}],
                },
                "Period": 3600,
                "Stat": statistic,
                "Unit": "Percent",
            },
        }
        for metric_id, namespace, metric_name, statistic in (
            ("cpu_p50", "AWS/EC2", "CPUUtilization", "p50"),
            ("cpu_p95", "AWS/EC2", "CPUUtilization", "p95"),
            ("memory_p50", "CWAgent", "MemoryUtilization", "p50"),
            ("memory_p95", "CWAgent", "MemoryUtilization", "p95"),
        )
    ]
    response = client.get_metric_data(
        MetricDataQueries=queries,
        StartTime=end - timedelta(days=1),
        EndTime=end,
    )
    results = {result["Id"]: result for result in response["MetricDataResults"]}
    assert set(results) == {"cpu_p50", "cpu_p95", "memory_p50", "memory_p95"}
    for result in results.values():
        assert result["StatusCode"] == "Complete"
        assert result["Values"] == []
        assert result["Timestamps"] == []


def test_paginators_terminate(endpoint_url: str) -> None:
    """The two paginators FinOps uses each finish instead of hunting for a token."""
    client = _client(endpoint_url)
    metrics_pages = list(client.get_paginator("list_metrics").paginate(Namespace="AWS/EC2"))
    assert len(metrics_pages) == 1
    # The estate meters AWS now, so this page carries metrics. What the test pins is that
    # the paginator TERMINATES (one page, no token hunt), not that the list is empty.
    assert metrics_pages[0]["Metrics"]

    alarm_pages = list(
        client.get_paginator("describe_alarms").paginate(StateValue="ALARM", MaxRecords=100),
    )
    assert len(alarm_pages) == 1
    assert alarm_pages[0]["MetricAlarms"] == []


# ── what the estate does and does not carry ───────────────────────────────────


def test_aws_resources_do_carry_metric_series(endpoint_url: str) -> None:
    """The generator meters AWS now, so CloudWatch answers with real data.

    It meters ``ec2_instance`` (``AWS/EC2``, plus memory in ``CWAgent``) and ``rds_instance``
    (``AWS/RDS``) — the two types FinOps CloudWatch call sites and this shim's namespace
    table agree on. This is the tripwire that used to stand here (when the estate metered only
    Azure/GCP types), inverted: it now fails if AWS metering is dropped, rather than if it is
    added.
    """
    client = _client(endpoint_url)
    metrics = client.list_metrics()["Metrics"]
    assert metrics, "the estate meters AWS resources, so this cannot be empty"
    assert {m["Namespace"] for m in metrics} <= {"AWS/EC2", "AWS/RDS", "CWAgent"}


def test_memory_is_listed_in_the_agent_namespace_for_the_same_instance(endpoint_url: str) -> None:
    """The ``CWAgent`` half, which is what the rightsizing provider's memory query needs.

    ``cloudwatch_metrics_provider.py (modulo do consumidor)`` asks ``CWAgent`` +
    ``MemoryUtilization`` + ``InstanceId`` beside its ``AWS/EC2`` CPU query; the instance the
    listed row names must be the same id ``DescribeInstances`` reports (pinned for the CPU row
    by :func:`test_metric_data_projects_a_metered_aws_resource`), so both halves of one
    measurement resolve to one instance. Asserted as set equality against the CPU rows'
    ``InstanceId`` values, which is the alignment stated in the other namespace's terms.
    """
    client = _client(endpoint_url)
    listed = client.list_metrics(Namespace="CWAgent")["Metrics"]
    cpu_rows = client.list_metrics(Namespace="AWS/EC2", MetricName="CPUUtilization")["Metrics"]

    assert listed, "ec2 instances are metered on memory, so CWAgent is not empty"
    assert {m["MetricName"] for m in listed} == {"MemoryUtilization"}
    assert {m["Dimensions"][0]["Name"] for m in listed} == {"InstanceId"}
    assert {m["Dimensions"][0]["Value"] for m in listed} == {
        m["Dimensions"][0]["Value"] for m in cpu_rows
    }


def test_a_resource_without_a_series_yields_no_metric(endpoint_url: str) -> None:
    """A dimension naming an estate resource still yields nothing when it has no series."""
    client = _client(endpoint_url)
    listed = client.list_metrics(
        Namespace="AWS/EC2",
        Dimensions=[{"Name": "InstanceId", "Value": "i-2222222222"}],
    )
    assert listed["Metrics"] == []


# ── refusals ──────────────────────────────────────────────────────────────────


def test_unknown_operation_is_refused(endpoint_url: str) -> None:
    """The protocol's own error shape: a ``ClientError`` with a readable code.

    ``ListDashboards`` requires no member, so the request reaches the server and the
    refusal is the emulator's — not botocore's parameter validation.
    """
    from botocore.exceptions import ClientError

    client = _client(endpoint_url)
    with pytest.raises(ClientError) as excinfo:
        client.list_dashboards()
    error = excinfo.value.response["Error"]
    assert error["Code"] == "UnknownOperationException"
    assert "ListDashboards" in error["Message"]


def test_missing_required_parameter_is_refused(api_client: Any) -> None:
    """A body without ``StartTime`` is refused, not answered with an empty result.

    Posted as a raw request rather than through boto3: ``StartTime`` is required in the
    model, so the client refuses it before it ever leaves the process, and this test is
    about the *server's* refusal.
    """
    client, _ = api_client
    response = client.post(
        "/",
        content=json.dumps(
            {
                "MetricDataQueries": [{"Id": "a", "MetricStat": {"Metric": {"Namespace": "AWS/EC2"}, "Period": 60, "Stat": "Average"}}],
                "EndTime": 1767225600,
            },
        ),
        headers={"X-Amz-Target": f"{_TARGET_PREFIX}.GetMetricData", "Content-Type": "application/x-amz-json-1.0"},
    )
    assert response.status_code == 400
    assert b"MissingRequiredParameterException" in response.content


def test_expression_query_is_refused(endpoint_url: str) -> None:
    """A math expression needs an evaluator this emulator has none of — so it is refused."""
    from botocore.exceptions import ClientError

    client = _client(endpoint_url)
    with pytest.raises(ClientError) as excinfo:
        client.get_metric_data(
            MetricDataQueries=[{"Id": "e1", "Expression": "m1+m2"}],
            StartTime=datetime(2026, 1, 1, tzinfo=UTC),
            EndTime=datetime(2026, 1, 2, tzinfo=UTC),
        )
    assert excinfo.value.response["Error"]["Code"] == "InvalidParameterValueException"


# ── the CBOR framing ──────────────────────────────────────────────────────────


def _cbor_call(client: Any, operation: str, params: dict[str, Any]) -> Any:
    """Post a CBOR request built by botocore's own serializer and parse it with its parser.

    Both halves are botocore's, so the assertion is that its serializer and its parser
    agree with what this emulator writes — the same standard the JSON framing is held to.
    """
    serialized = create_serializer("smithy-rpc-v2-cbor").serialize_to_request(
        params,
        _MODEL.operation_model(operation),
    )
    response = client.post(serialized["url_path"], content=serialized["body"], headers=serialized["headers"])
    raw = {
        "status_code": response.status_code,
        "headers": dict(response.headers),
        "body": response.content,
    }
    parser = create_parser("smithy-rpc-v2-cbor")
    shape = _MODEL.operation_model(operation).output_shape
    if response.status_code != 200:
        return parser._do_error_parse(raw, shape)
    return parser.parse(raw, shape)


@pytest.fixture()
def cbor_site() -> Any:
    """The CBOR framing needs ``cbor2`` on the server, which the test venv may not carry."""
    return pytest.importorskip("cbor2")


def test_cbor_transport_path_and_headers(api_client: Any) -> None:
    """The CBOR request does not go to ``/``: the serializer rewrites the path."""
    serialized = create_serializer("smithy-rpc-v2-cbor").serialize_to_request(
        {"Namespace": "AWS/EC2"},
        _MODEL.operation_model("ListMetrics"),
    )
    assert serialized["url_path"] == f"/service/{_TARGET_PREFIX}/operation/ListMetrics"
    assert serialized["headers"]["smithy-protocol"] == "rpc-v2-cbor"
    assert serialized["headers"]["Accept"] == "application/cbor"
    assert isinstance(serialized["body"], bytes)


def test_cbor_list_metrics_round_trip(api_client: Any, cbor_site: Any) -> None:
    client, _ = api_client
    parsed = _cbor_call(client, "ListMetrics", {"Namespace": "AWS/EC2"})
    assert parsed["Metrics"] == []


def test_cbor_describe_alarms_round_trip(api_client: Any, cbor_site: Any) -> None:
    client, _ = api_client
    parsed = _cbor_call(client, "DescribeAlarms", {"StateValue": "ALARM"})
    assert parsed["MetricAlarms"] == []


def test_cbor_get_metric_data_round_trip(api_client: Any, cbor_site: Any) -> None:
    """The CBOR framing answers with the same result the JSON framing does."""
    client, _ = api_client
    start = datetime(2026, 1, 1, tzinfo=UTC)
    parsed = _cbor_call(
        client,
        "GetMetricData",
        {
            "MetricDataQueries": [
                {
                    "Id": "cpu",
                    "MetricStat": {
                        "Metric": {
                            "Namespace": "AWS/EC2",
                            "MetricName": "CPUUtilization",
                            "Dimensions": [{"Name": "InstanceId", "Value": "i-3333333333"}],
                        },
                        "Period": 3600,
                        "Stat": "Average",
                    },
                },
            ],
            "StartTime": start,
            "EndTime": start + timedelta(days=1),
        },
    )
    assert [result["Id"] for result in parsed["MetricDataResults"]] == ["cpu"]
    assert parsed["MetricDataResults"][0]["Values"] == []


def test_cbor_error_is_parsed_by_botocore(api_client: Any, cbor_site: Any) -> None:
    """An unknown operation is refused in CBOR too, with the code the CBOR parser reads."""
    client, _ = api_client
    parsed = _cbor_call(client, "PutMetricAlarm", {"AlarmName": "x"})
    assert parsed["Error"]["Code"] == "UnknownOperationException"


def test_a_misframed_body_on_the_cbor_path_is_refused(api_client: Any, cbor_site: Any) -> None:
    """The CBOR path is the CBOR transport, so a request that does not declare CBOR fails.

    Without this the JSON body would reach the CBOR decoder and surface as an unhandled
    error instead of a protocol refusal a client can read.
    """
    client, _ = api_client
    response = client.post(
        f"/service/{_TARGET_PREFIX}/operation/ListMetrics",
        content=b'{"Namespace": "AWS/EC2"}',
        headers={"Content-Type": "application/x-amz-json-1.0"},
    )
    assert response.status_code == 400
    assert b"SerializationException" in response.content


def test_another_services_prefix_is_refused_on_the_cbor_path(api_client: Any, cbor_site: Any) -> None:
    """The path's prefix is resolved through the model, not trusted."""
    client, _ = api_client
    parsed = _cbor_call(client, "ListMetrics", {"Namespace": "AWS/EC2"})
    assert parsed["Metrics"] == []

    serialized = create_serializer("smithy-rpc-v2-cbor").serialize_to_request(
        {"Namespace": "AWS/EC2"},
        _MODEL.operation_model("ListMetrics"),
    )
    response = client.post(
        "/service/SomeOtherService/operation/ListMetrics",
        content=serialized["body"],
        headers=serialized["headers"],
    )
    assert response.status_code == 400
    parsed_error = create_parser("smithy-rpc-v2-cbor")._do_error_parse(
        {"status_code": response.status_code, "headers": dict(response.headers), "body": response.content},
        None,
    )
    assert parsed_error["Error"]["Code"] == "UnknownOperationException"


# ── the encodings the empty estate cannot reach ───────────────────────────────


def test_cbor_response_timestamps_must_be_tag_1(cbor_site: Any) -> None:
    """botocore's CBOR parser accepts tag 1 and *raises on every other tag*.

    The frozen estate carries no AWS series, so no served response ever contains a
    timestamp and this encoding would otherwise ship unexercised. This asserts it against
    botocore's own parser: the tag is what turns the number back into a ``datetime``, and a
    self-describe tag (55799) would break the parse outright.
    """
    from aws_sim import smithy_rpc

    timestamp = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    wire = smithy_rpc.SmithyRpcWire("cloudwatch", smithy_rpc.PROTOCOL_CBOR)
    body = wire.render_result(
        {
            "MetricDataResults": [
                {"Id": "c", "Label": "CPUUtilization", "Timestamps": [timestamp], "Values": [12.5], "StatusCode": "Complete"},
            ],
        },
    )
    parsed = create_parser("smithy-rpc-v2-cbor").parse(
        {"status_code": 200, "headers": {}, "body": body},
        _MODEL.operation_model("GetMetricData").output_shape,
    )
    result = parsed["MetricDataResults"][0]
    assert result["Timestamps"] == [timestamp]
    assert result["Values"] == [12.5]


def test_json_response_timestamps_must_be_epoch_seconds() -> None:
    """The JSON framing's timestamps are epoch numbers, which its parser reads back."""
    from aws_sim import smithy_rpc

    timestamp = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    wire = smithy_rpc.SmithyRpcWire("cloudwatch", smithy_rpc.PROTOCOL_JSON)
    body = wire.render_result(
        {
            "MetricDataResults": [
                {"Id": "c", "Label": "CPUUtilization", "Timestamps": [timestamp], "Values": [12.5], "StatusCode": "Complete"},
            ],
        },
    )
    parsed = create_parser("json").parse(
        {"status_code": 200, "headers": {}, "body": body},
        _MODEL.operation_model("GetMetricData").output_shape,
    )
    assert parsed["MetricDataResults"][0]["Timestamps"] == [timestamp]


def test_metric_data_projects_a_metered_aws_resource(api_client: Any) -> None:
    """The projection's mapping and statistics, against a series the estate would carry.

    The frozen estate meters no AWS resource, so this attaches a series to a **real** estate
    ``ec2_instance``: the namespace, the dimension name and the dimension value all come
    from that resource, and only the samples are supplied — because the estate supplies
    none. Without this the bucketing, the statistic math and the percentile rank would ship
    entirely unexercised.
    """
    from dataclasses import replace

    from tools.synthetic_clouds.model.metrics import MetricPoint, MetricSeries

    from aws_sim import ids, scope
    from aws_sim.projections import cloudwatch as cw

    _, app = api_client
    estate = app.state.estate
    instance = next(r for r in scope.resources(estate) if r.resource_type == "ec2_instance")
    start = datetime(2026, 1, 1, tzinfo=UTC)
    samples = [10.0, 20.0, 30.0, 40.0]
    series = MetricSeries(
        resource_uuid=instance.identity.uuid,
        metric_name="cpu_utilization",
        points=tuple(
            MetricPoint(ts=start + timedelta(hours=index), value=value)
            for index, value in enumerate(samples)
        ),
    )
    metered = replace(estate, metrics=(series,))

    # The resource decides the AWS identity: AWS/EC2 dimensioned by its own id, which is the
    # value DescribeInstances reports for it and the one its ARN carries.
    instance_id = ids.resource_id(instance)
    assert cw.metrics(metered) == [
        {
            "Namespace": "AWS/EC2",
            "MetricName": "CPUUtilization",
            "Dimensions": [{"Name": "InstanceId", "Value": instance_id}],
        },
    ]
    assert cw.metrics(metered, namespace="AWS/RDS") == []
    assert cw.metrics(metered, dimensions=[{"Name": "InstanceId", "Value": "i-does-not-exist"}]) == []

    metric = {
        "Namespace": "AWS/EC2",
        "MetricName": "CPUUtilization",
        "Dimensions": [{"Name": "InstanceId", "Value": instance_id}],
    }

    def _query(query_id: str, stat: str, period: int) -> dict[str, Any]:
        return {"Id": query_id, "MetricStat": {"Metric": metric, "Period": period, "Stat": stat}}

    window = (start, start + timedelta(hours=4))
    results = {
        result["Id"]: result
        for result in cw.metric_data(metered, queries=[_query("avg", "Average", 14400), _query("count", "SampleCount", 14400), _query("p95", "p95", 14400), _query("max", "Maximum", 14400)], start=window[0], end=window[1])
    }
    # One 4h bucket holding all four samples.
    assert results["avg"]["Values"] == [25.0]
    assert results["count"]["Values"] == [4.0]
    assert results["max"]["Values"] == [40.0]
    # Nearest rank: ceil(0.95 * 4) = 4 -> the largest of the four.
    assert results["p95"]["Values"] == [40.0]
    assert results["avg"]["Timestamps"] == [start]
    assert results["avg"]["StatusCode"] == "Complete"
    assert results["avg"]["Label"] == "CPUUtilization"

    # Hourly buckets keep one sample each, and the window is half-open on the right.
    hourly = cw.metric_data(metered, queries=[_query("avg", "Average", 3600)], start=window[0], end=start + timedelta(hours=2))
    assert hourly[0]["Values"] == [10.0, 20.0]
    assert hourly[0]["Timestamps"] == [start, start + timedelta(hours=1)]

    # A window that holds no sample reports neither a timestamp nor a value.
    later = cw.metric_data(metered, queries=[_query("avg", "Average", 3600)], start=start + timedelta(days=1), end=start + timedelta(days=2))
    assert later[0]["Values"] == []
    assert later[0]["Timestamps"] == []
