"""Cost Management Query contract: request-driven columns + GET continuation.

The CloudPilot Azure reader sends an aggregation alias (``CostInBillingCurrency``)
and a grouping list; the REAL Query API echoes those names as columns and
continues a page with a plain ``GET`` of ``nextLink``. These two facts are what
let the reader consume the simulator without any adaptation, so they are pinned
here.
"""

from __future__ import annotations

from dataclasses import replace

_API_VERSION = "2025-03-01"
_SCOPE = "/subscriptions/0de2e68d-bb29-52ac-9934-b4d930c33902"
_QUERY = {
    "type": "ActualCost",
    "timeframe": "Custom",
    "dataset": {
        "granularity": "Daily",
        "aggregation": {"CostInBillingCurrency": {"name": "Cost", "function": "Sum"}},
        "grouping": [
            {"type": "Dimension", "name": "MeterCategory"},
            {"type": "Dimension", "name": "BillingPeriodStartDate"},
            {"type": "Dimension", "name": "BillingPeriodEndDate"},
        ],
    },
}


def test_query_echoes_requested_alias_and_dimensions(api_client) -> None:
    client, _app = api_client
    resp = client.post(
        f"{_SCOPE}/providers/Microsoft.CostManagement/query?api-version={_API_VERSION}",
        json=_QUERY,
    )
    assert resp.status_code == 200
    columns = [column["name"] for column in resp.json()["properties"]["columns"]]
    assert columns[0] == "CostInBillingCurrency", columns
    assert "PreTaxCost" not in columns
    assert "MeterCategory" in columns
    assert "BillingPeriodStartDate" in columns
    assert "BillingPeriodEndDate" in columns
    # Every row matches the column count (the echo is positional).
    rows = resp.json()["properties"]["rows"]
    assert rows and all(len(row) == len(columns) for row in rows)


def test_next_link_is_served_by_a_plain_get(api_client) -> None:
    client, app = api_client
    # Force a tiny page so the first response carries a nextLink.
    app.state.settings = replace(app.state.settings, api_page_size=2)
    first = client.post(
        f"{_SCOPE}/providers/Microsoft.CostManagement/query?api-version={_API_VERSION}",
        json=_QUERY,
    )
    assert first.status_code == 200
    link = first.json()["nextLink"]
    assert link, "expected a continuation link with page size 2"

    second = client.get(link)
    assert second.status_code == 200, second.text
    second_rows = second.json()["properties"]["rows"]
    assert len(second_rows) == 2
    assert second_rows != first.json()["properties"]["rows"]
