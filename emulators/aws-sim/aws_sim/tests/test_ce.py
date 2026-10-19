"""Cost Explorer JSON-protocol tests, parsed with botocore's own parser.

The load-bearing assertion is coherence with the CUR basis: CE is calculated from the same
billing lines the CUR promoter consumes, so its ``UnblendedCost`` total must equal the sum
of the estate's AWS ``billed_cost`` for the same period. A fixture could not hold that.
"""

from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal

import botocore.session
from botocore.parsers import create_parser

_MODEL = botocore.session.get_session().get_service_model("ce")
_PARSER = create_parser("json")


def _parse(client, operation: str, body: dict):
    target = f"{_MODEL.metadata['targetPrefix']}.{operation}"
    response = client.post(
        "/",
        content=json.dumps(body),
        headers={"X-Amz-Target": target, "Content-Type": "application/x-amz-json-1.1"},
    )
    raw = {"status_code": response.status_code, "headers": dict(response.headers), "body": response.content}
    shape = _MODEL.operation_model(operation).output_shape
    if response.status_code != 200:
        return _PARSER._do_error_parse(raw, shape)
    return _PARSER.parse(raw, shape)


def _window(estate):
    return estate.sim_start.isoformat(), (estate.sim_now + timedelta(days=1)).isoformat()


def _expected_total(estate, start: str, end: str) -> Decimal:
    from datetime import date

    lo, hi = date.fromisoformat(start), date.fromisoformat(end)
    lines = [
        line
        for line in estate.billing_lines
        if line.service_provider_name == "Amazon Web Services" and lo <= line.charge_period_start.date() < hi
    ]
    return sum((line.billed_cost for line in lines), Decimal("0"))


def test_get_cost_and_usage_matches_the_cur_basis(api_client) -> None:
    """CE total == the estate's AWS billed total for the same period (FR-8 coherence)."""
    client, app = api_client
    estate = app.state.estate
    start, end = _window(estate)
    result = _parse(
        client,
        "GetCostAndUsage",
        {
            "TimePeriod": {"Start": start, "End": end},
            "Granularity": "MONTHLY",
            "Metrics": ["UnblendedCost"],
            "GroupBy": [{"Type": "DIMENSION", "Key": "SERVICE"}],
        },
    )
    assert result["ResultsByTime"], "the estate has AWS lines in the window"
    grouped = sum(
        Decimal(group["Metrics"]["UnblendedCost"]["Amount"])
        for entry in result["ResultsByTime"]
        for group in entry["Groups"]
    )
    assert grouped == _expected_total(estate, start, end)
    for entry in result["ResultsByTime"]:
        for group in entry["Groups"]:
            assert group["Keys"], "a grouped bucket has keys"
            assert group["Metrics"]["UnblendedCost"]["Unit"] == "USD"


def test_ungrouped_request_returns_a_total(api_client) -> None:
    client, app = api_client
    start, end = _window(app.state.estate)
    result = _parse(
        client, "GetCostAndUsage", {"TimePeriod": {"Start": start, "End": end}, "Granularity": "MONTHLY"}
    )
    total = sum(
        Decimal(entry["Total"]["UnblendedCost"]["Amount"])
        for entry in result["ResultsByTime"]
        if entry["Total"]
    )
    assert total == _expected_total(app.state.estate, start, end)


def test_get_dimension_values_lists_services(api_client) -> None:
    client, app = api_client
    start, end = _window(app.state.estate)
    result = _parse(
        client,
        "GetDimensionValues",
        {"TimePeriod": {"Start": start, "End": end}, "Dimension": "SERVICE"},
    )
    values = [row["Value"] for row in result["DimensionValues"]]
    assert values
    assert result["TotalSize"] == len(values)


def test_missing_time_period_is_a_validation_exception(api_client) -> None:
    client, _ = api_client
    error = _parse(client, "GetCostAndUsage", {"Granularity": "MONTHLY"})
    assert error["Error"]["Code"] == "ValidationException"


def test_unknown_operation_is_refused(api_client) -> None:
    client, _ = api_client
    response = client.post(
        "/",
        content="{}",
        headers={"X-Amz-Target": f"{_MODEL.metadata['targetPrefix']}.GetAnomalies"},
    )
    assert response.status_code == 400
    assert b"UnknownOperationException" in response.content
