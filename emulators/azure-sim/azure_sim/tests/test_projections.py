"""Projection determinism + native-shape tests (FEAT-002 step 5).

Each projection is a pure function over the frozen gated estate: deterministic for
a fixed seed, native-only shapes, UPPERCASE severity preserved.
"""

from __future__ import annotations

from azure_sim.estate import build_simulated_estate
from azure_sim.projections import (
    arm,
    compute,
    cost_query,
    findings,
    inventory,
    metrics,
    prices,
    recommendations,
    scope,
)


def _estate():
    return build_simulated_estate(seed=42, profile="small", currency="USD")


def test_every_projection_answers_with_this_providers_rows_only() -> None:
    """The provider boundary, pinned.

    The estate is genuinely multi-cloud, so a projection that stops filtering starts
    returning AWS and GCP rows through Azure endpoints — which is what happened before
    ``projections/scope.py`` existed. Without this test the regression is silent: every
    envelope keeps its shape and only the *contents* are wrong.

    The ids are the ones this provider's resources are ADDRESSED by (``arm.resource_id_for``):
    an ARM id, which embeds the subscription GUID and the resource group, or — for a type this
    package serves no ARM path for — the estate's own uuid. Both are unique per resource,
    which is the property a foreign row would break.
    """
    estate = _estate()
    azure = [r for r in estate.resources if r.identity.provider == "azure"]
    azure_ids: set[str] = set()
    for resource in azure:
        azure_ids.add(resource.identity.uuid)
        arm_id = arm.resource_id_for(estate, resource)
        if arm_id is not None:
            azure_ids.add(arm_id)
    foreign = {r.identity.uuid for r in estate.resources if r.identity.provider != "azure"}
    assert azure_ids and foreign, "the estate must be multi-cloud for this test to mean anything"

    assert {row["id"] for row in inventory.project_resources(estate)} <= azure_ids
    assert {row["id"] for row in inventory.project_security_resources(estate)} <= azure_ids
    assert {row["targetResourceId"] for row in inventory.project_resource_changes(estate)} <= azure_ids
    assert {row["resourceId"] for row in findings.project_assessments(estate)} <= azure_ids
    assert {row["resourceId"] for row in findings.project_alerts(estate)} <= azure_ids
    assert {row["resourceId"] for row in recommendations.project_recommendations(estate)} <= azure_ids
    assert {row["resourceId"] for row in metrics.project_metrics(estate)} <= azure_ids
    assert {row["resourceId"] for row in metrics.project_metric_definitions(estate)} <= azure_ids

    # Nothing foreign may leak through any of them either — in ANY member, so a row that
    # moved a resource's uuid into a new key cannot carry one in unnoticed.
    for rows in (
        inventory.project_resources(estate),
        inventory.project_security_resources(estate),
        findings.project_assessments(estate),
        metrics.project_metrics(estate),
    ):
        served = " ".join(" ".join(str(value) for value in row.values()) for row in rows)
        assert not any(uuid in served for uuid in foreign)


def test_billing_scope_is_this_provider_only() -> None:
    """The export path is where a leak costs most: it writes the FOCUS file.

    ``runner._lines_in_window`` consumes this one scope function, so pinning the scope
    pins the export without reaching into the runner's own window arithmetic.
    """
    estate = _estate()
    lines = scope.billing_lines(estate)
    assert lines, "the estate carries Azure billing lines"
    assert len(lines) < len(estate.billing_lines), "the estate is multi-cloud"
    assert {line.service_provider_name for line in lines} == {"Microsoft Azure"}
    assert {line.line_id for line in lines} <= {line.line_id for line in estate.billing_lines}


def test_cost_query_shape_and_determinism() -> None:
    estate = _estate()
    first = cost_query.project_cost_query(estate, granularity="daily")
    second = cost_query.project_cost_query(estate, granularity="daily")
    assert first == second
    assert isinstance(first["columns"], list)
    assert isinstance(first["rows"], list)
    # Each row matches the column count.
    ncols = len(first["columns"])
    assert all(len(row) == ncols for row in first["rows"])


def test_cost_query_monthly_differs_from_daily() -> None:
    estate = _estate()
    daily = cost_query.project_cost_query(estate, granularity="daily")["rows"]
    monthly = cost_query.project_cost_query(estate, granularity="monthly")["rows"]
    # Monthly buckets collapse days, so there are no more monthly rows than daily.
    assert len(monthly) <= len(daily)


def test_cost_query_rejects_unknown_granularity() -> None:
    estate = _estate()
    try:
        cost_query.project_cost_query(estate, granularity="hourly")
    except ValueError:
        return
    raise AssertionError("expected ValueError for unknown granularity")


def test_inventory_resources_deterministic_and_sorted() -> None:
    estate = _estate()
    rows = inventory.project_resources(estate)
    assert rows == inventory.project_resources(estate)
    ids = [str(row["id"]) for row in rows]
    assert ids == sorted(ids)


def test_findings_preserve_uppercase_severity() -> None:
    estate = _estate()
    rows = findings.project_assessments(estate)
    assert rows  # the small estate has findings
    for row in rows:
        severity = str(row["severity"])
        assert severity == severity.upper()
        assert severity in {"CRITICAL", "HIGH", "MEDIUM", "LOW"}


def test_alerts_are_critical_high_subset() -> None:
    estate = _estate()
    alerts = findings.project_alerts(estate)
    for row in alerts:
        assert row["alertSeverity"] in {"CRITICAL", "HIGH"}


def test_recommendations_native_shape() -> None:
    estate = _estate()
    rows = recommendations.project_recommendations(estate)
    assert rows
    for row in rows:
        assert set(row) >= {"id", "resourceId", "category", "recommendationModel"}


def test_prices_native_shape() -> None:
    estate = _estate()
    retail = prices.project_retail_prices(estate)
    sheet = prices.project_price_sheet(estate)
    assert retail and sheet
    for item in retail:
        assert set(item) >= {"skuId", "retailPrice", "unitOfMeasure", "currencyCode"}


def test_prices_filter_equality() -> None:
    estate = _estate()
    retail = prices.project_retail_prices(estate)
    one_sku = str(retail[0]["skuId"])
    filtered = prices.filter_retail_prices(retail, sku_id=one_sku, currency=None)
    assert filtered
    assert all(item["skuId"] == one_sku for item in filtered)


def test_metrics_native_series_shape() -> None:
    """Native Monitor series — and the id they are attributed to.

    ``resourceId`` is asserted to be the id the resource plane publishes for the same
    resource, which is the correlation a caller actually makes (read ``vm.id`` from
    ``virtualMachines.list_all``, then ask Monitor about it). It used to be two values:
    Monitor reported the estate's uuid while the resource plane reported an ARM id, so every
    metric row a caller matched to a resource missed.

    The collision half is why the id is not the name: the estate reuses ``resource_name``
    across subscriptions (``virtual_machine-0000`` exists in three of them), so a telemetry row
    keyed by the name would be a row several resources claim. Two same-named VMs must resolve
    to two different ``resourceId`` values, each equal to its own ARM row's id.
    """
    estate = _estate()
    series = metrics.project_metrics(estate)
    assert series
    for row in series:
        assert set(row) >= {"name", "resourceId", "timeseries"}
        assert isinstance(row["timeseries"], list)

    vms = [
        r
        for r in estate.resources
        if r.identity.provider == "azure" and r.resource_type == "virtual_machine"
    ]
    assert vms, "the small estate carries virtual machines"
    vm_ids = {str(arm.resource_id_for(estate, resource)) for resource in vms}
    published = {str(row["id"]) for row in compute.project_virtual_machines(estate)}
    served = {str(row["resourceId"]) for row in series}
    assert published == vm_ids, "every VM is served under its own ARM id"
    metered = served & vm_ids
    assert metered, "the estate meters virtual machines, so their ids appear here"

    # Two metered VMs that share a name in two subscriptions answer two different ids.
    by_name: dict[str, list[str]] = {}
    for resource in vms:
        resource_id = str(arm.resource_id_for(estate, resource))
        if resource_id in metered:
            by_name.setdefault(resource.resource_name, []).append(resource_id)
    shared = next((ids for ids in by_name.values() if len(ids) > 1), None)
    assert shared is not None, "the estate reuses a metered VM name across subscriptions"
    assert len(set(shared)) == len(shared), "two VMs with one name must not answer one id"
    assert all(resource_id.startswith("/subscriptions/") for resource_id in shared)
