"""Cloud Monitoring gRPC plane tests (FR-25): reachability proven with the REAL client.

These tests drive the official ``google-cloud-monitoring`` classes over a real gRPC channel
against the plane this package serves. Nothing is stubbed, and that is the point: a test
that re-implemented the wire format would pass while a real client failed, and a real client
failing is the exact state this plane fixes -- ``google-cloud-monitoring`` ships no REST
transport in any version, so an HTTP-only answer surface is unreachable from FinOps.
"""

from __future__ import annotations

import socket
from collections.abc import Iterator
from pathlib import Path

import grpc
import pytest
from fastapi.testclient import TestClient
from google.api_core.exceptions import InvalidArgument
from google.cloud.monitoring_v3 import AlertPolicyServiceClient, MetricServiceClient
from google.cloud.monitoring_v3.services.alert_policy_service.transports import (
    AlertPolicyServiceGrpcTransport,
)
from google.cloud.monitoring_v3.services.metric_service.transports import (
    MetricServiceGrpcTransport,
)

from gcp_sim import monitoring_grpc
from gcp_sim.fixtures import load_fixtures

#: The sim answers any project scope (the REST plane's timeSeries route behaves the same).
_PROJECT = "projects/contoso-prod-01"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture(scope="module")
def monitoring_target(fixtures_dir: Path) -> Iterator[str]:
    """Serve the monitoring plane over the rendered fixtures; yield its ``host:port``."""
    port = _free_port()
    server = monitoring_grpc.start(load_fixtures(fixtures_dir), port)
    yield f"127.0.0.1:{port}"
    server.stop(0)


@pytest.fixture()
def channel(monitoring_target: str) -> Iterator[grpc.Channel]:
    grpc_channel = grpc.insecure_channel(monitoring_target)
    yield grpc_channel
    grpc_channel.close()


@pytest.fixture()
def metric_client(channel: grpc.Channel) -> MetricServiceClient:
    """A real ``MetricServiceClient`` talking to the sim over the real gRPC transport."""
    return MetricServiceClient(transport=MetricServiceGrpcTransport(channel=channel))


@pytest.fixture()
def alert_client(channel: grpc.Channel) -> AlertPolicyServiceClient:
    return AlertPolicyServiceClient(transport=AlertPolicyServiceGrpcTransport(channel=channel))


class TestPlaneSwitch:
    def test_port_unset_means_the_plane_is_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Unset is the default: the process serves REST only, exactly as it did before."""
        monkeypatch.delenv(monitoring_grpc.PORT_ENV, raising=False)
        assert monitoring_grpc.configured_port() is None

    def test_a_non_numeric_port_disables_the_plane(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A bad port disables loudly rather than binding a default nobody asked for."""
        monkeypatch.setenv(monitoring_grpc.PORT_ENV, "not-a-port")
        assert monitoring_grpc.configured_port() is None

    def test_the_rest_plane_is_unaffected_by_the_switch(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The REST plane must never depend on the optional plane being up."""
        monkeypatch.delenv(monitoring_grpc.PORT_ENV, raising=False)
        assert client.get("/healthz").json() == {"status": "ok"}


class TestOperationTable:
    def test_every_served_path_is_a_method_the_client_stubs(self) -> None:
        """Each served path must exist on the real client, or the plane answers a ghost.

        The client builds its stubs from ``/service/method`` paths over proto-plus
        serializers, so a path the client never stubs is a route nothing can reach.
        """
        assert {operation.path for operation in monitoring_grpc._load_operations()} == {
            "/google.monitoring.v3.MetricService/ListTimeSeries",
            "/google.monitoring.v3.MetricService/ListMetricDescriptors",
            "/google.monitoring.v3.AlertPolicyService/ListAlertPolicies",
        }


class TestRealClientCalls:
    def test_list_metric_descriptors_returns_parsed_descriptors(self, metric_client: MetricServiceClient) -> None:
        """The operation that had no answer surface at all, read by the real client."""
        descriptors = list(metric_client.list_metric_descriptors(name=_PROJECT))

        assert descriptors, "no metric descriptors served"
        by_type = {d.type: d for d in descriptors}
        assert "compute.googleapis.com/instance/cpu_utilization" in by_type
        cpu = by_type["compute.googleapis.com/instance/cpu_utilization"]
        assert cpu.display_name == "Cpu Utilization"
        assert cpu.unit == "percent"
        assert list(cpu.monitored_resource_types) == ["gce_instance"]
        assert cpu.name.startswith("projects/") and "/metricDescriptors/" in cpu.name

    def test_list_time_series_returns_parsed_series_with_points(self, metric_client: MetricServiceClient) -> None:
        """The third operation: served here too, because one client speaks one transport."""
        series = list(metric_client.list_time_series(request={"name": _PROJECT, "filter": 'metric.type = "*"'}))
        assert series, "no time series served"

        first = series[0]
        assert first.metric.type.endswith("cpu_utilization")
        assert first.resource.type in {"gce_instance", "cloudsql_database"}
        assert first.points, "series carries no points"
        assert first.points[0].value.double_value > 0
        # The identity the resource-list fixtures publish, so all three surfaces resolve
        # one resource.
        assert "resourcePath" in dict(first.resource.labels)

    def test_list_alert_policies_returns_parsed_policies(self, alert_client: AlertPolicyServiceClient) -> None:
        """The second operation that had no answer surface, read by the real client."""
        policies = list(alert_client.list_alert_policies(request={"name": _PROJECT}))

        assert policies, "no alert policies served"
        policy = policies[0]
        assert policy.name.startswith("projects/") and "/alertPolicies/" in policy.name
        assert policy.display_name
        assert policy.enabled is True
        condition = policy.conditions[0].condition_absent
        assert 'metric.type = "' in condition.filter
        assert "resource.label.resourcePath" in condition.filter
        assert condition.duration.total_seconds() == 600

    def test_alert_policies_watch_the_series_the_other_operations_publish(
        self, metric_client: MetricServiceClient, alert_client: AlertPolicyServiceClient
    ) -> None:
        """One estate behind all three operations: a policy's filter names a served type."""
        served = {
            series.metric.type
            for series in metric_client.list_time_series(request={"name": _PROJECT, "filter": 'metric.type = "*"'})
        }
        policies = list(alert_client.list_alert_policies(request={"name": _PROJECT}))
        for policy in policies:
            condition_filter = policy.conditions[0].condition_absent.filter
            watched = condition_filter.split('metric.type = "', 1)[1].split('"', 1)[0]
            assert watched in served, f"{policy.name} watches {watched}, which no series carries"


class TestRequestValidation:
    def test_a_name_outside_the_projects_scope_is_rejected(self, metric_client: MetricServiceClient) -> None:
        """The REST plane validates the scope prefix; the gRPC plane must too."""
        with pytest.raises(InvalidArgument):
            list(metric_client.list_metric_descriptors(name="organizations/123"))
