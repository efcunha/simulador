"""The OpenCost allocation contract, exercised through FastAPI's TestClient.

What these tests pin is the **wire contract**, not the implementation: the key
``payments/api`` and the cost field names are written as literals here so that
changing a constant in the simulator breaks the test instead of silently redefining
the contract.

The contract, the sources it was read from, and the places where this phase narrows or
deviates from OpenCost are documented in ``docs/k8s-sim-opencost-contract.md``.
"""

from __future__ import annotations

import math
from typing import Any

import pytest
from fastapi.testclient import TestClient

from k8s_sim.app import create_app

#: The window the phase prescribes: two consecutive days, one allocation set per day.
_WINDOW = "2026-10-01,2026-10-02"

#: The allocation-set key. OpenCost joins the aggregated property values with "/" (see
#: ``AllocationProperties.GenerateKey`` in the official source); this simulator has a
#: single workload, so the key names it.
_WORKLOAD_KEY = "payments/api"

#: The five cost fields the phase requires on every allocation.
_COST_FIELDS = ("cpuCost", "ramCost", "pvCost", "networkCost", "totalCost")


@pytest.fixture(scope="module")
def client() -> Any:
    """A TestClient over a freshly built app."""
    return TestClient(create_app())


def _get(client: Any, **params: str) -> Any:
    """GET /allocation/compute with the given query parameters."""
    return client.get("/allocation/compute", params=params)


# ── liveness ─────────────────────────────────────────────────────────────────


def test_healthz_answers_ok(client: Any) -> None:
    """The liveness probe answers 200 with the sibling sims' body."""
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "synthetic": True}


# ── the envelope ─────────────────────────────────────────────────────────────


def test_allocation_compute_answers_the_opencost_envelope(client: Any) -> None:
    """The response is the OpenCost envelope: ``code`` plus ``data``."""
    response = _get(client, window=_WINDOW, aggregate="namespace")
    assert response.status_code == 200

    body = response.json()
    assert body["code"] == 200
    assert isinstance(body["data"], list)


def test_the_window_yields_one_allocation_set_per_day(client: Any) -> None:
    """Two days in, two sets out -- ``data`` is a list of windows."""
    response = _get(client, window=_WINDOW, aggregate="namespace")
    data = response.json()["data"]
    assert len(data) == 2


# ── the allocation set ───────────────────────────────────────────────────────


def test_each_set_is_a_dict_keyed_by_the_workload(client: Any) -> None:
    """Each window is a dict whose single key is the workload."""
    response = _get(client, window=_WINDOW, aggregate="namespace")
    for window in response.json()["data"]:
        assert isinstance(window, dict)
        assert list(window.keys()) == [_WORKLOAD_KEY]


def test_the_allocation_carries_the_cluster_namespace_and_controller(client: Any) -> None:
    """The allocation names the cluster, the namespace and the controller."""
    response = _get(client, window=_WINDOW, aggregate="namespace")
    allocation = response.json()["data"][0][_WORKLOAD_KEY]

    properties = allocation["properties"]
    assert properties["cluster"] == "aks-synthetic-01"
    assert properties["namespace"] == "payments"
    assert properties["controller"] == "api"


def test_the_allocation_carries_the_five_cost_fields(client: Any) -> None:
    """Every cost field the phase names is present."""
    response = _get(client, window=_WINDOW, aggregate="namespace")
    allocation = response.json()["data"][0][_WORKLOAD_KEY]

    for field in _COST_FIELDS:
        assert field in allocation, field
        assert isinstance(allocation[field], (int, float))


def test_the_total_is_the_exact_sum_of_its_components(client: Any) -> None:
    """``totalCost`` is the sum of the four component costs, to the bit."""
    response = _get(client, window=_WINDOW, aggregate="namespace")
    for window in response.json()["data"]:
        allocation = window[_WORKLOAD_KEY]
        assert allocation["totalCost"] == (
            allocation["cpuCost"]
            + allocation["ramCost"]
            + allocation["pvCost"]
            + allocation["networkCost"]
        )


def test_the_costs_are_finite_and_not_negative(client: Any) -> None:
    """No NaN, no infinity, no negative cost."""
    response = _get(client, window=_WINDOW, aggregate="namespace")
    for window in response.json()["data"]:
        allocation = window[_WORKLOAD_KEY]
        for field in _COST_FIELDS:
            value = allocation[field]
            assert math.isfinite(value), field
            assert value >= 0, field


def test_each_set_covers_the_day_it_names(client: Any) -> None:
    """The first set is 10-01, the second is 10-02, each ending at the next midnight."""
    response = _get(client, window=_WINDOW, aggregate="namespace")
    data = response.json()["data"]

    assert data[0][_WORKLOAD_KEY]["window"] == {
        "start": "2026-10-01T00:00:00Z",
        "end": "2026-10-02T00:00:00Z",
    }
    assert data[1][_WORKLOAD_KEY]["window"] == {
        "start": "2026-10-02T00:00:00Z",
        "end": "2026-10-03T00:00:00Z",
    }


# ── determinism ──────────────────────────────────────────────────────────────


def test_two_identical_calls_return_the_same_payload(client: Any) -> None:
    """The payload is a pure function of the request: no clock, no randomness."""
    first = _get(client, window=_WINDOW, aggregate="namespace").json()
    second = _get(client, window=_WINDOW, aggregate="namespace").json()
    assert first == second


def test_the_window_alone_decides_the_payload(client: Any) -> None:
    """The aggregate parameter does not change what this phase serves."""
    with_aggregate = _get(client, window=_WINDOW, aggregate="namespace").json()
    without_aggregate = _get(client, window=_WINDOW).json()
    assert with_aggregate == without_aggregate


# ── refusals ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "window",
    [
        "not-a-window",
        "2026-10-01",
        "2026-10-01,2026-10-02,2026-10-03",
        "2026-13-01,2026-10-02",
        "2026-10-32,2026-11-02",
        "2026-10-02,2026-10-01",
    ],
)
def test_an_invalid_window_is_refused(client: Any, window: str) -> None:
    """A window this phase cannot read is a 400, not a silent fallback."""
    response = _get(client, window=window, aggregate="namespace")
    assert response.status_code == 400
    assert response.json()["code"] == 400


def test_a_missing_window_is_refused(client: Any) -> None:
    """``window`` is required by the OpenCost contract, so its absence is a 400."""
    response = _get(client, aggregate="namespace")
    assert response.status_code == 400
    assert response.json()["code"] == 400


def test_an_unsupported_aggregate_is_refused(client: Any) -> None:
    """This phase serves one aggregation; another one is refused, not approximated."""
    response = _get(client, window=_WINDOW, aggregate="cluster")
    assert response.status_code == 400
    assert response.json()["code"] == 400


def test_include_idle_does_not_change_the_payload(client: Any) -> None:
    """The estate models no idle resource, so asking for idle adds nothing."""
    without_idle = _get(client, window=_WINDOW, aggregate="namespace").json()
    with_idle = _get(client, window=_WINDOW, aggregate="namespace", includeIdle="true").json()
    assert without_idle == with_idle


def test_an_accumulate_request_is_refused(client: Any) -> None:
    """This phase accumulates by day; another accumulation is refused, not faked."""
    response = _get(client, window=_WINDOW, aggregate="namespace", accumulate="true")
    assert response.status_code == 400
    assert response.json()["code"] == 400
