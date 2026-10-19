"""Cost Management API tests (FEAT-002 step 7).

Query envelope + paging, Exports execute triggers a run (faked writer), Budgets /
Price Sheet / Reservations shapes, unknown api-version -> 400 Azure envelope.
"""

from __future__ import annotations

_QUERY_VERSION = "2024-08-01"
_EXPORTS_VERSION = "2023-08-01"
_BUDGETS_VERSION = "2024-08-01"
_PRICESHEET_VERSION = "2024-08-01"
_RESERVATIONS_VERSION = "2024-08-01"

_SCOPE = "/subscriptions/sub-1"


def test_query_envelope_shape(api_client) -> None:
    client, _ = api_client
    resp = client.post(
        f"{_SCOPE}/providers/Microsoft.CostManagement/query?api-version={_QUERY_VERSION}",
        json={"type": "ActualCost", "dataset": {"granularity": "monthly"}},
    )
    assert resp.status_code == 200
    props = resp.json()["properties"]
    assert "columns" in props and "rows" in props
    assert isinstance(props["columns"], list)
    assert isinstance(props["rows"], list)


def test_query_unknown_api_version_400(api_client) -> None:
    client, _ = api_client
    resp = client.post(
        f"{_SCOPE}/providers/Microsoft.CostManagement/query?api-version=1999-01-01",
        json={},
    )
    assert resp.status_code == 400
    assert "error" in resp.json()


def test_exports_crud_and_execute_triggers_run(api_client) -> None:
    client, app = api_client
    base = f"{_SCOPE}/providers/Microsoft.CostManagement/exports/daily-focus"
    # PUT a native export definition.
    put = client.put(f"{base}?api-version={_EXPORTS_VERSION}", json={"properties": {"schedule": "daily"}})
    assert put.status_code == 200
    assert put.json()["name"] == "daily-focus"
    # GET it back.
    got = client.get(f"{base}?api-version={_EXPORTS_VERSION}")
    assert got.status_code == 200
    # Execute: triggers a run via the faked writer.
    before = len(app.state.export_writer.calls)
    run = client.post(f"{base}/run?api-version={_EXPORTS_VERSION}")
    assert run.status_code == 200
    assert run.json()["status"] == "Completed"
    assert len(app.state.export_writer.calls) > before  # a run was written


def test_export_get_missing_404(api_client) -> None:
    client, _ = api_client
    resp = client.get(
        f"{_SCOPE}/providers/Microsoft.CostManagement/exports/does-not-exist"
        f"?api-version={_EXPORTS_VERSION}"
    )
    assert resp.status_code == 404
    assert "error" in resp.json()


def test_budgets_put_get_native_definition(api_client) -> None:
    client, _ = api_client
    base = f"{_SCOPE}/providers/Microsoft.Consumption/budgets/monthly-cap"
    put = client.put(
        f"{base}?api-version={_BUDGETS_VERSION}",
        json={"properties": {"amount": 1000, "timeGrain": "Monthly"}},
    )
    assert put.status_code == 200
    got = client.get(f"{base}?api-version={_BUDGETS_VERSION}")
    assert got.status_code == 200
    assert got.json()["name"] == "monthly-cap"


def test_pricesheet_shape(api_client) -> None:
    client, _ = api_client
    resp = client.post(
        f"{_SCOPE}/providers/Microsoft.CostManagement/pricesheet?api-version={_PRICESHEET_VERSION}",
        json={},
    )
    assert resp.status_code == 200
    assert "pricesheets" in resp.json()["properties"]


def test_reservations_shape_and_native_status(api_client) -> None:
    client, _ = api_client
    resp = client.get(
        f"/providers/Microsoft.Capacity/reservations?api-version={_RESERVATIONS_VERSION}"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "value" in body
    for row in body["value"]:
        # Native CommitmentDiscountStatus is Used|Unused (never a computed verdict).
        assert row["usageStatus"] in {"Used", "Unused"}
