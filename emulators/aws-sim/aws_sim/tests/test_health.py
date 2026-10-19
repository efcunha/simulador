"""AWS Health tests: a REAL boto3 client against a served app, plus the measured wire.

The load-bearing test is :func:`test_real_boto3_client_round_trip`: it starts the app on a
real socket and drives it with ``boto3.client("health")``, so the request goes through
botocore's own serializer, signer and response parser. A transport error, a content-type
mismatch or a body the parser cannot read fails there.

:func:`test_protocol_readings_agree_on_json` pins the *measured* fact the slice is built
on. ``metadata["protocol"]`` and ``ServiceModel.resolved_protocol`` are two different
readings and they disagreed for CloudWatch (declared ``smithy-rpc-v2-cbor``, resolved
``json``); for AWS Health both say ``json``. If a future botocore changes either, this
fails loudly instead of the emulator silently serving the wrong framing.

The empty results are asserted as *emptiness*, not merely as a 200: the estate models no
health entity, so an event appearing here would be a fabricated outage reaching
``aws_collector.py (modulo do consumidor)`` and, from there, the Operations center.
"""

from __future__ import annotations

import socket
import threading
import time
from typing import Any

import boto3
import botocore.session
import pytest
import uvicorn

_AWS_CREDENTIALS = {"aws_access_key_id": "x", "aws_secret_access_key": "y"}
_REGION = "us-east-1"

_MODEL = botocore.session.get_session().get_service_model("health")

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
    return boto3.client("health", endpoint_url=endpoint_url, region_name=_REGION, **_AWS_CREDENTIALS, **kwargs)


# ── the measured wire ─────────────────────────────────────────────────────────


def test_protocol_readings_agree_on_json() -> None:
    """Both protocol readings say ``json`` — unlike CloudWatch, where they differ."""
    assert _MODEL.metadata["protocol"] == "json"
    assert list(_MODEL.protocols) == ["json"]
    assert _MODEL.resolved_protocol == "json"


def test_the_body_type_is_json_1_1_not_1_0() -> None:
    """The model's ``jsonVersion`` is 1.1, so the body type the client sends is 1.1."""
    assert _MODEL.metadata["jsonVersion"] == "1.1"


def test_client_sends_json_1_1_to_the_endpoint_root(endpoint_url: str) -> None:
    """The client posts to ``/`` carrying an ``AWSHealth_20160804.<Operation>`` target."""
    captured: dict[str, Any] = {}

    def _capture(request: Any, **_kwargs: Any) -> None:
        captured["url"] = request.url
        captured["headers"] = {
            key: value.decode("utf-8") if isinstance(value, bytes) else value
            for key, value in dict(request.headers).items()
        }
        body = request.body
        captured["body"] = body.decode("utf-8") if isinstance(body, bytes) else body
        return None

    client = _client(endpoint_url)
    client.meta.events.register_first("before-send.health.DescribeEvents", _capture)
    client.describe_events(filter={"eventStatusCodes": ["open", "upcoming"]}, maxResults=10)

    assert captured["headers"]["Content-Type"] == "application/x-amz-json-1.1"
    assert captured["headers"]["X-Amz-Target"] == f"{_TARGET_PREFIX}.DescribeEvents"
    assert captured["url"].endswith("/")
    assert "/service/" not in captured["url"], "the CBOR transport path must not be used by this client"


# ── the boto3 round trip ──────────────────────────────────────────────────────


def test_real_boto3_client_round_trip(endpoint_url: str) -> None:
    """Both served operations answer a real boto3 client with parsed Python data."""
    client = _client(endpoint_url)

    # The exact request ``collect_health_events`` issues.
    events = client.describe_events(filter={"eventStatusCodes": ["open", "upcoming"]}, maxResults=10)
    assert events["ResponseMetadata"]["HTTPStatusCode"] == 200
    assert events["events"] == []

    # The enrichment call, with an ARN of the shape the caller builds from a real response.
    details = client.describe_event_details(
        eventArns=["arn:aws:health:us-east-1::event/EC2/AWS_EC2_OPERATIONAL_ISSUE/SYNTHETIC_EXAMPLE"],
    )
    assert details["ResponseMetadata"]["HTTPStatusCode"] == 200
    assert details["successfulSet"] == []


def test_the_estate_reports_no_events_for_any_filter(endpoint_url: str) -> None:
    """No filter selects an event, because the estate models none — not because one is new.

    An unfiltered call is the widest possible question, so it is the one that would expose
    a fabricated row if the slice ever grew one.
    """
    client = _client(endpoint_url)
    assert client.describe_events()["events"] == []
    assert client.describe_events(filter={"eventTypeCategories": ["issue", "accountNotification"]})["events"] == []


def test_no_next_token_is_emitted(endpoint_url: str) -> None:
    """Real AWS omits ``nextToken`` on the last page, and this page is the last one."""
    client = _client(endpoint_url)
    assert "nextToken" not in client.describe_events()


# ── refusals ──────────────────────────────────────────────────────────────────


def test_unknown_operation_is_refused(api_client: Any) -> None:
    """An operation outside the two FinOps calls is refused, not answered empty."""
    client, _ = api_client
    response = client.post(
        "/",
        content="{}",
        headers={"X-Amz-Target": f"{_TARGET_PREFIX}.DescribeAffectedEntities"},
    )
    assert response.status_code == 400
    assert b"UnknownOperationException" in response.content


def test_a_foreign_target_prefix_is_not_claimed(api_client: Any) -> None:
    """Another service's target must not be resolved by this slice."""
    client, _ = api_client
    response = client.post("/", content="{}", headers={"X-Amz-Target": "AccessAnalyzer_20150331.ListAnalyzers"})
    assert response.status_code == 400
    assert b"UnknownOperationException" in response.content
