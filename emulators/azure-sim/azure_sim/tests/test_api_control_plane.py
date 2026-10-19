"""Control-plane router tests (FEAT-002 step 8).

Each router's official envelope + paging + error cases: Resource Graph,
Defender, Policy Insights, Advisor, Graph, Retail Prices, Monitor.
"""

from __future__ import annotations

import pytest

_RG_VERSION = "2024-04-01"
_DEFENDER_VERSION = "2023-01-01"
_POLICY_VERSION = "2024-10-01"
_ADVISOR_VERSION = "2023-01-01"
_GRAPH_VERSION = "v1.0"
_MONITOR_VERSION = "2024-02-01"
_METRIC_ALERTS_VERSION = "2018-03-01"
_ALERT_RULE_INCIDENTS_VERSION = "2016-03-01"

_SCOPE = "/subscriptions/sub-1"


def test_resource_graph_resources_envelope(api_client) -> None:
    client, _ = api_client
    resp = client.post(
        f"/providers/Microsoft.ResourceGraph/resources?api-version={_RG_VERSION}", json={}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "count" in body and "data" in body
    assert isinstance(body["data"], list)


def test_resource_graph_securityresources(api_client) -> None:
    client, _ = api_client
    resp = client.post(
        f"/providers/Microsoft.ResourceGraph/securityresources?api-version={_RG_VERSION}", json={}
    )
    assert resp.status_code == 200
    assert isinstance(resp.json()["data"], list)


def test_resource_graph_unknown_version_400(api_client) -> None:
    client, _ = api_client
    resp = client.post(
        "/providers/Microsoft.ResourceGraph/resources?api-version=1999-01-01", json={}
    )
    assert resp.status_code == 400
    assert "error" in resp.json()


def test_defender_assessments_uppercase_severity(api_client) -> None:
    client, _ = api_client
    resp = client.get(
        f"{_SCOPE}/providers/Microsoft.Security/assessments?api-version={_DEFENDER_VERSION}"
    )
    assert resp.status_code == 200
    rows = resp.json()["value"]
    for row in rows:
        assert row["severity"] == row["severity"].upper()


def test_defender_secure_scores_and_alerts(api_client) -> None:
    client, _ = api_client
    scores = client.get(
        f"{_SCOPE}/providers/Microsoft.Security/secureScores?api-version={_DEFENDER_VERSION}"
    )
    alerts = client.get(
        f"{_SCOPE}/providers/Microsoft.Security/alerts?api-version={_DEFENDER_VERSION}"
    )
    assert scores.status_code == 200
    assert alerts.status_code == 200
    assert "value" in scores.json()
    assert "value" in alerts.json()


def test_policy_states_native(api_client) -> None:
    client, _ = api_client
    resp = client.post(
        f"{_SCOPE}/providers/Microsoft.PolicyInsights/policyStates/latest/queryResults"
        f"?api-version={_POLICY_VERSION}",
        json={},
    )
    assert resp.status_code == 200
    rows = resp.json()["value"]
    for row in rows:
        assert row["complianceState"] in {"Compliant", "NonCompliant"}


def test_advisor_recommendations(api_client) -> None:
    client, _ = api_client
    resp = client.get(
        f"{_SCOPE}/providers/Microsoft.Advisor/recommendations?api-version={_ADVISOR_VERSION}"
    )
    assert resp.status_code == 200
    assert "value" in resp.json()


def test_graph_users_and_mfa(api_client) -> None:
    client, _ = api_client
    users = client.get(f"/users?api-version={_GRAPH_VERSION}")
    methods = client.get(f"/users/authentication/methods?api-version={_GRAPH_VERSION}")
    assert users.status_code == 200
    assert methods.status_code == 200
    for user in users.json()["value"]:
        assert user["userPrincipalName"].endswith("@contoso.example")
        assert isinstance(user["isMfaRegistered"], bool)


def test_retail_prices_odata_filter(api_client) -> None:
    client, _ = api_client
    resp = client.get("/api/retail/prices")
    assert resp.status_code == 200
    body = resp.json()
    assert "Items" in body
    assert isinstance(body["Items"], list)


def test_retail_prices_filter_by_currency(api_client) -> None:
    client, _ = api_client
    resp = client.get("/api/retail/prices?$filter=currencyCode eq 'USD'")
    assert resp.status_code == 200
    for item in resp.json()["Items"]:
        assert item["currencyCode"] == "USD"


def test_monitor_metrics_envelope(api_client) -> None:
    client, _ = api_client
    resp = client.get(
        f"{_SCOPE}/providers/Microsoft.Insights/metrics?api-version={_MONITOR_VERSION}"
    )
    assert resp.status_code == 200
    assert isinstance(resp.json()["value"], list)


def test_monitor_unknown_version_400(api_client) -> None:
    client, _ = api_client
    resp = client.get(f"{_SCOPE}/providers/Microsoft.Insights/metrics?api-version=1999-01-01")
    assert resp.status_code == 400
    assert "error" in resp.json()


# ── Monitor: metricDefinitions / metricAlerts / alert-rule incidents ─────────────


def test_metric_definitions_shape_matches_the_sdk_contract(api_client) -> None:
    """Every key is the one ``MetricDefinition._attribute_map`` names."""
    client, _ = api_client
    resp = client.get(
        f"{_SCOPE}/providers/Microsoft.Insights/metricDefinitions?api-version={_MONITOR_VERSION}"
    )
    assert resp.status_code == 200
    rows = resp.json()["value"]
    assert rows, "the small estate meters resources, so definitions cannot be empty"
    for row in rows:
        assert set(row["name"]) == {"value", "localizedValue"}
        assert row["primaryAggregationType"] == "Average"
        assert row["unit"]
        assert row["metricAvailabilities"][0]["timeGrain"]
        assert row["resourceId"]


def test_metric_alerts_nest_under_properties(api_client) -> None:
    """``MetricAlertResource._attribute_map`` reads ``properties.*`` off the model."""
    client, _ = api_client
    resp = client.get(
        f"{_SCOPE}/providers/Microsoft.Insights/metricAlerts?api-version={_METRIC_ALERTS_VERSION}"
    )
    assert resp.status_code == 200
    rows = resp.json()["value"]
    assert rows
    for row in rows:
        assert row["id"].startswith("/subscriptions/")
        assert "/resourceGroups/" in row["id"]
        props = row["properties"]
        assert props["enabled"] is True
        assert props["severity"] == 2
        assert props["scopes"]
        criteria = props["criteria"]
        assert criteria["odata.type"] == "Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria"
        assert criteria["allOf"][0]["threshold"] == 80.0


def test_alert_rule_incidents_join_on_the_rule_name(api_client) -> None:
    """The incidents endpoint is keyed by the name the rules endpoint published."""
    client, _ = api_client
    rules = client.get(
        f"{_SCOPE}/providers/Microsoft.Insights/metricAlerts?api-version={_METRIC_ALERTS_VERSION}"
    ).json()["value"]
    assert rules

    # The threshold sits inside the estate's metric range, so *some* rule must fire — but which
    # one depends on that resource's workload band (the estate emits percentages now, not a
    # uniform fraction), so find a firing rule rather than assuming the first one fires.
    rule_name: str | None = None
    rows: list[dict] = []
    for rule in rules:
        resp = client.get(
            f"{_SCOPE}/resourcegroups/rg-1/providers/microsoft.insights/alertrules/{rule['name']}"
            f"/incidents?api-version={_ALERT_RULE_INCIDENTS_VERSION}"
        )
        assert resp.status_code == 200
        candidate = resp.json()["value"]
        if candidate:
            rule_name, rows = str(rule["name"]), candidate
            break

    assert rule_name, "the threshold is inside the estate's metric range, so some rule must fire"
    for row in rows:
        assert row["ruleName"] == rule_name
        assert set(row) == {"name", "ruleName", "isActive", "activatedTime", "resolvedTime"}
        assert isinstance(row["isActive"], bool)
    # At most the last run can still be open.
    assert sum(1 for row in rows if row["isActive"]) <= 1


def test_incidents_are_case_sensitively_routed_as_the_sdk_requests(api_client) -> None:
    """The SDK's own template is lower-case; the capitalised spelling must not 404 only by luck."""
    client, _ = api_client
    resp = client.get(
        f"{_SCOPE}/resourcegroups/rg-1/providers/microsoft.insights/alertrules/nope"
        f"/incidents?api-version={_ALERT_RULE_INCIDENTS_VERSION}"
    )
    assert resp.status_code == 200
    assert resp.json()["value"] == []


def test_monitor_payloads_survive_the_real_azure_deserializer(api_client) -> None:
    """Round-trip the served JSON through the installed SDK, then read what FinOps reads.

    This is the assertion that a hand-written envelope cannot pass by accident:
    ``collect_alarms`` reads ``rule.enabled``/``severity``/``scopes``/``location`` and
    ``incident.is_active``/``activated_time``, and ``discover_metrics`` reads
    ``defn.name.value``/``localized_value``/``unit``/``primary_aggregation_type``. If
    the wire shape drifts, the SDK deserializes nothing and these go empty.
    """
    import json
    from typing import Any

    pytest.importorskip("azure.mgmt.monitor")

    from azure.core.pipeline.transport import HttpResponse, HttpTransport
    from azure.mgmt.monitor import MonitorManagementClient

    client, _ = api_client
    # Keyed by the distinctive path suffix: the SDK prefixes ``metricDefinitions`` with
    # whatever resource_uri the caller passed, so an exact-path key cannot match.
    served: dict[str, Any] = {
        "/providers/Microsoft.Insights/metricDefinitions": client.get(
            f"{_SCOPE}/providers/Microsoft.Insights/metricDefinitions?api-version={_MONITOR_VERSION}"
        ).json(),
        "/providers/Microsoft.Insights/metricAlerts": client.get(
            f"{_SCOPE}/providers/Microsoft.Insights/metricAlerts?api-version={_METRIC_ALERTS_VERSION}"
        ).json(),
    }
    rule_name = served["/providers/Microsoft.Insights/metricAlerts"]["value"][0]["name"]
    incidents_suffix = f"/providers/microsoft.insights/alertrules/{rule_name}/incidents"
    served[incidents_suffix] = client.get(
        f"{_SCOPE}/resourcegroups/rg-1/providers/microsoft.insights/alertrules/{rule_name}"
        f"/incidents?api-version={_ALERT_RULE_INCIDENTS_VERSION}"
    ).json()

    class ServedResponse(HttpResponse):
        """``HttpResponse`` refuses to serve a body unless ``body()`` is implemented."""

        def __init__(self, request: Any, payload: bytes) -> None:
            super().__init__(request=request, internal_response=None)
            self._payload = payload

        def body(self) -> bytes:
            return self._payload

    class Served(HttpTransport):
        def send(self, request: Any, **kwargs: Any) -> Any:
            path = str(request.url).split("?")[0].replace("https://management.azure.com", "")
            body: Any = next(
                (value for suffix, value in served.items() if path.endswith(suffix)),
                {"value": []},
            )
            response = ServedResponse(request, json.dumps(body).encode("utf-8"))
            response.status_code = 200
            response.headers = {"content-type": "application/json"}
            response.reason = "OK"
            return response

        def open(self):  # noqa: D102 - transport protocol
            return None

        def close(self):  # noqa: D102 - transport protocol
            return None

        def __enter__(self):  # noqa: D105 - transport protocol
            return self

        def __exit__(self, *args):  # noqa: D105 - transport protocol
            return False

    class StubCredential:
        def get_token(self, *args, **kwargs):  # noqa: D102 - credential protocol
            class Token:
                token = "synthetic"
                expires_on = 9999999999

            return Token()

        def close(self):  # noqa: D102 - credential protocol
            return None

    monitor = MonitorManagementClient(StubCredential(), "sub-1", transport=Served())

    definitions = list(monitor.metric_definitions.list(resource_uri="/subscriptions/sub-1/x"))
    assert definitions
    localized = definitions[0].name
    assert localized is not None
    assert localized.value == "cpu_utilization"
    assert localized.localized_value == "CPU utilization"
    assert str(definitions[0].unit) in {"Percent", "Unit.Percent"}
    assert definitions[0].primary_aggregation_type is not None

    rules = list(monitor.metric_alerts.list_by_subscription())
    assert rules
    assert rules[0].enabled is True
    assert rules[0].severity == 2
    assert rules[0].scopes
    assert rules[0].location

    # The threshold sits inside the estate's metric range, so some rule fires — that invariant
    # is pinned by test_alert_rule_incidents_join_on_the_rule_name over the raw API. This test's
    # job is the SDK round-trip: the endpoint must be callable and every row must deserialize.
    incidents = list(
        monitor.alert_rule_incidents.list_by_alert_rule(
            resource_group_name="rg-1",
            rule_name=rule_name,
        )
    )
    for incident in incidents:
        assert incident.is_active in (True, False)
        assert incident.activated_time is not None
