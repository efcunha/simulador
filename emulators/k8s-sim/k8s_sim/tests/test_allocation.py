"""The OpenCost allocation contract, exercised through FastAPI's TestClient.

What these tests pin is the **wire contract**, not the implementation: the key
``payments`` and the cost field names are written as literals here so that
changing a constant in the simulator breaks the test instead of silently redefining
the contract.

The contract, the sources it was read from, and the places where this phase narrows or
deviates from OpenCost are documented in ``docs/k8s-sim-opencost-contract.md``.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from k8s_sim.app import create_app

#: The window the phase prescribes: two consecutive days, one allocation set per day.
_WINDOW = "2026-10-01,2026-10-02"

#: The versioned catalog of the estate's Kubernetes clusters, derived from the estate
#: by ``scripts/export_clusters.py``. It is DATA, not code: the service reads it at
#: runtime and never imports the generator.
_FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "clusters.json"

#: The synthetic workload every cluster of the estate carries.
_NAMESPACE = "payments"
_CONTROLLER = "api"

#: The allocation-set key. OpenCost builds it by joining the aggregated property
#: values with "/" (see ``AllocationProperties.GenerateKey`` in the official
#: source); with ``aggregate=namespace`` the only aggregated property is the
#: namespace, so the key is the namespace alone. The controller stays in
#: ``properties`` -- it is not part of the aggregation.
_ALLOCATION_KEY = "payments"

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


def test_each_set_is_a_dict_keyed_by_the_namespace(client: Any) -> None:
    """Each window is a dict whose single key is the namespace."""
    response = _get(client, window=_WINDOW, aggregate="namespace")
    for window in response.json()["data"]:
        assert isinstance(window, dict)
        assert list(window.keys()) == [_ALLOCATION_KEY]


def test_the_allocation_is_named_after_its_key(client: Any) -> None:
    """``name`` is the key the allocation is filed under."""
    response = _get(client, window=_WINDOW, aggregate="namespace")
    allocation = response.json()["data"][0][_ALLOCATION_KEY]
    assert allocation["name"] == _ALLOCATION_KEY


def test_the_allocation_carries_the_cluster_namespace_and_controller(client: Any) -> None:
    """The allocation names the cluster, the namespace and the controller."""
    response = _get(client, window=_WINDOW, aggregate="namespace")
    allocation = response.json()["data"][0][_ALLOCATION_KEY]

    properties = allocation["properties"]
    assert properties["cluster"] == "aks-synthetic-01"
    assert properties["namespace"] == "payments"
    assert properties["controller"] == "api"


def test_the_allocation_carries_the_five_cost_fields(client: Any) -> None:
    """Every cost field the phase names is present."""
    response = _get(client, window=_WINDOW, aggregate="namespace")
    allocation = response.json()["data"][0][_ALLOCATION_KEY]

    for field in _COST_FIELDS:
        assert field in allocation, field
        assert isinstance(allocation[field], (int, float))


def test_the_total_is_the_exact_sum_of_its_components(client: Any) -> None:
    """``totalCost`` is the sum of the four component costs, to the bit."""
    response = _get(client, window=_WINDOW, aggregate="namespace")
    for window in response.json()["data"]:
        allocation = window[_ALLOCATION_KEY]
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
        allocation = window[_ALLOCATION_KEY]
        for field in _COST_FIELDS:
            value = allocation[field]
            assert math.isfinite(value), field
            assert value >= 0, field


def test_each_set_covers_the_day_it_names(client: Any) -> None:
    """The first set is 10-01, the second is 10-02, each ending at the next midnight."""
    response = _get(client, window=_WINDOW, aggregate="namespace")
    data = response.json()["data"]

    assert data[0][_ALLOCATION_KEY]["window"] == {
        "start": "2026-10-01T00:00:00Z",
        "end": "2026-10-02T00:00:00Z",
    }
    assert data[1][_ALLOCATION_KEY]["window"] == {
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
    """An aggregation this phase does not serve is refused, not approximated."""
    response = _get(client, window=_WINDOW, aggregate="node")
    assert response.status_code == 400
    assert response.json()["code"] == 400


def test_include_idle_does_not_change_the_payload(client: Any) -> None:
    """The estate models no idle resource, so asking for idle adds nothing."""
    without_idle = _get(client, window=_WINDOW, aggregate="namespace").json()
    with_idle = _get(client, window=_WINDOW, aggregate="namespace", includeIdle="true").json()
    assert without_idle == with_idle


def test_an_accumulate_request_is_served(client: Any) -> None:
    """``accumulate`` is a valid OpenCost parameter: it is served, never refused."""
    response = _get(client, window=_WINDOW, aggregate="namespace", accumulate="true")
    assert response.status_code == 200
    assert response.json()["code"] == 200


@pytest.mark.parametrize("accumulate", ["true", "1", "t", "T", "TRUE", "True", "all", "ALL"])
def test_every_spelling_of_the_whole_window_accumulates(client: Any, accumulate: str) -> None:
    """Every value the official handler reads as the whole window is one set."""
    response = _get(client, window=_WINDOW, aggregate="namespace", accumulate=accumulate)
    assert response.status_code == 200

    data = response.json()["data"]
    assert len(data) == 1
    assert data[0][_ALLOCATION_KEY]["minutes"] == 2880.0


def test_an_accumulated_window_is_a_single_set(client: Any) -> None:
    """``accumulate=true`` sums the whole window into one set, as OpenCost does."""
    response = _get(client, window=_WINDOW, aggregate="namespace", accumulate="true")
    data = response.json()["data"]

    assert len(data) == 1
    assert list(data[0].keys()) == [_ALLOCATION_KEY]

    allocation = data[0][_ALLOCATION_KEY]
    assert allocation["window"] == {
        "start": "2026-10-01T00:00:00Z",
        "end": "2026-10-03T00:00:00Z",
    }
    assert allocation["start"] == "2026-10-01T00:00:00Z"
    assert allocation["end"] == "2026-10-03T00:00:00Z"
    assert allocation["minutes"] == 2880.0


def test_the_accumulated_costs_are_the_sum_of_the_days(client: Any) -> None:
    """Two days of the synthetic rate card, summed."""
    response = _get(client, window=_WINDOW, aggregate="namespace", accumulate="true")
    allocation = response.json()["data"][0][_ALLOCATION_KEY]

    assert allocation["cpuCoreHours"] == 96.0
    assert allocation["ramByteHours"] == 206158430208.0
    assert allocation["pvByteHours"] == 1030792151040.0
    assert allocation["networkTransferBytes"] == 107374182400.0

    assert allocation["cpuCost"] == 3.84
    assert allocation["ramCost"] == 1.152
    assert allocation["pvCost"] == 0.768
    assert allocation["networkCost"] == 2.0
    assert allocation["totalCost"] == 7.76


def test_the_accumulated_total_is_the_exact_sum_of_its_components(client: Any) -> None:
    """The total identity survives the accumulation, to the bit."""
    response = _get(client, window=_WINDOW, aggregate="namespace", accumulate="true")
    allocation = response.json()["data"][0][_ALLOCATION_KEY]

    assert allocation["totalCost"] == (
        allocation["cpuCost"]
        + allocation["ramCost"]
        + allocation["pvCost"]
        + allocation["networkCost"]
    )


def test_the_accumulated_usage_is_the_average_and_not_the_sum(client: Any) -> None:
    """OpenCost derives ``cpuCores``/``ramBytes``/``pvBytes`` from the summed hours
    divided by the summed minutes, so a constant estate keeps the same figures."""
    response = _get(client, window=_WINDOW, aggregate="namespace", accumulate="true")
    allocation = response.json()["data"][0][_ALLOCATION_KEY]

    assert allocation["cpuCores"] == 2.0
    assert allocation["ramBytes"] == 4294967296.0
    assert allocation["pvBytes"] == 21474836480.0


@pytest.mark.parametrize("accumulate", ["false", "0", "day"])
def test_an_accumulation_that_is_not_the_whole_window_keeps_the_daily_sets(
    client: Any, accumulate: str
) -> None:
    """Anything that does not ask for the whole window keeps one set per day."""
    response = _get(client, window=_WINDOW, aggregate="namespace", accumulate=accumulate)
    assert response.status_code == 200

    data = response.json()["data"]
    assert len(data) == 2
    assert list(data[0].keys()) == [_ALLOCATION_KEY]


# ── the estate's cluster catalog ──────────────────────────────────────────────


@pytest.fixture(scope="module")
def estate_clusters() -> list[dict[str, str]]:
    """The estate's cluster catalog, read from the versioned fixture."""
    records: list[dict[str, str]] = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    return records


@pytest.fixture(scope="module")
def a_cluster_id(estate_clusters: list[dict[str, str]]) -> str:
    """One cluster of the estate -- the first one, in the fixture's own order."""
    return estate_clusters[0]["cluster_id"]


def test_the_fixture_holds_the_estate_clusters(estate_clusters: list[dict[str, str]]) -> None:
    """309 clusters -- 75 EKS, 111 GKE, 123 AKS -- the estate's own numbers."""
    assert len(estate_clusters) == 309

    counts = Counter(cluster["provider"] for cluster in estate_clusters)
    assert counts == {"aws": 75, "gcp": 111, "azure": 123}


def test_the_fixture_is_sorted_and_has_no_repeated_cluster(
    estate_clusters: list[dict[str, str]],
) -> None:
    """The catalog is sorted by id and holds no cluster twice."""
    ids = [cluster["cluster_id"] for cluster in estate_clusters]
    assert ids == sorted(ids)
    assert len(set(ids)) == len(ids)


def test_the_fixture_names_a_provider_and_a_region_for_every_cluster(
    estate_clusters: list[dict[str, str]],
) -> None:
    """Every record carries the three fields the catalog publishes."""
    for cluster in estate_clusters:
        assert set(cluster) == {"cluster_id", "provider", "region_id"}
        assert cluster["cluster_id"]
        assert cluster["provider"]
        assert cluster["region_id"]


# ── the real OpenCost parameters ──────────────────────────────────────────────


def test_the_namespace_and_controller_aggregation_keys_by_both(
    client: Any, a_cluster_id: str
) -> None:
    """``aggregate=namespace,controller`` keys the allocation by namespace AND controller."""
    response = _get(
        client,
        window=_WINDOW,
        aggregate="namespace,controller",
        filter=f'cluster:"{a_cluster_id}"',
        step="1d",
        accumulate="false",
    )
    assert response.status_code == 200

    data = response.json()["data"]
    assert list(data[0].keys()) == [f"{_NAMESPACE}/{_CONTROLLER}"]

    allocation = data[0][f"{_NAMESPACE}/{_CONTROLLER}"]
    assert allocation["properties"]["namespace"] == _NAMESPACE
    assert allocation["properties"]["controller"] == _CONTROLLER
    assert allocation["properties"]["cluster"] == a_cluster_id


def test_the_namespace_aggregation_keys_by_the_namespace_only(
    client: Any, a_cluster_id: str
) -> None:
    """``aggregate=namespace`` keys the allocation by the namespace alone."""
    response = _get(
        client,
        window=_WINDOW,
        aggregate="namespace",
        filter=f'cluster:"{a_cluster_id}"',
    )
    assert response.status_code == 200

    data = response.json()["data"]
    assert list(data[0].keys()) == [_NAMESPACE]


def test_the_controller_aggregation_keys_by_the_controller_only(
    client: Any, a_cluster_id: str
) -> None:
    """``aggregate=controller`` keys the allocation by the controller alone."""
    response = _get(
        client,
        window=_WINDOW,
        aggregate="controller",
        filter=f'cluster:"{a_cluster_id}"+namespace:"{_NAMESPACE}"+controller:"{_CONTROLLER}"',
    )
    assert response.status_code == 200

    data = response.json()["data"]
    assert list(data[0].keys()) == [_CONTROLLER]

    allocation = data[0][_CONTROLLER]
    assert allocation["properties"]["namespace"] == _NAMESPACE
    assert allocation["properties"]["controller"] == _CONTROLLER


def test_the_cluster_aggregation_keys_by_the_cluster(
    client: Any, a_cluster_id: str
) -> None:
    """``aggregate=cluster`` keys the allocation by the cluster -- the connection test."""
    response = _get(
        client,
        window=_WINDOW,
        aggregate="cluster",
        filter=f'cluster:"{a_cluster_id}"',
    )
    assert response.status_code == 200

    data = response.json()["data"]
    assert list(data[0].keys()) == [a_cluster_id]

    allocation = data[0][a_cluster_id]
    assert allocation["name"] == a_cluster_id
    assert allocation["properties"]["cluster"] == a_cluster_id


def test_the_filter_selects_the_cluster_it_names(client: Any, a_cluster_id: str) -> None:
    """The cluster the filter names is the cluster the payload carries."""
    response = _get(
        client,
        window=_WINDOW,
        aggregate="namespace",
        filter=f'cluster:"{a_cluster_id}"',
    )
    assert response.status_code == 200

    allocation = response.json()["data"][0][_NAMESPACE]
    assert allocation["properties"]["cluster"] == a_cluster_id


def test_a_filter_that_names_no_cluster_of_the_estate_answers_no_data(
    client: Any,
) -> None:
    """A cluster the estate does not have is an empty answer, never an invented one."""
    response = _get(
        client,
        window=_WINDOW,
        aggregate="namespace",
        filter='cluster:"not-a-cluster-of-the-estate"',
    )
    assert response.status_code == 200
    assert response.json()["data"] == []


def test_two_identical_calls_with_a_filter_return_the_same_payload(
    client: Any, a_cluster_id: str
) -> None:
    """The filtered payload is a pure function of the request, as the unfiltered one is."""
    params = {
        "window": _WINDOW,
        "aggregate": "namespace,controller",
        "filter": f'cluster:"{a_cluster_id}"',
        "step": "1d",
        "accumulate": "false",
    }
    first = _get(client, **params).json()
    second = _get(client, **params).json()
    assert first == second


def test_the_one_day_step_is_accepted(client: Any, a_cluster_id: str) -> None:
    """``step=1d`` is the step the provider sends, and it is served."""
    response = _get(
        client,
        window=_WINDOW,
        aggregate="namespace,controller",
        filter=f'cluster:"{a_cluster_id}"',
        step="1d",
        accumulate="false",
    )
    assert response.status_code == 200
    assert len(response.json()["data"]) == 2


@pytest.mark.parametrize("step", ["1h", "24h", "2d", "1w", "month"])
def test_a_step_other_than_one_day_is_refused(client: Any, step: str) -> None:
    """A step this phase does not serve is a 400, not a silently wrong set."""
    response = _get(client, window=_WINDOW, aggregate="namespace", step=step)
    assert response.status_code == 400
    assert response.json()["code"] == 400


def test_the_accumulation_still_sums_the_window_with_a_filter(
    client: Any, a_cluster_id: str
) -> None:
    """``accumulate=true`` still sums the whole window into one set."""
    response = _get(
        client,
        window=_WINDOW,
        aggregate="namespace",
        filter=f'cluster:"{a_cluster_id}"',
        accumulate="true",
    )
    assert response.status_code == 200

    data = response.json()["data"]
    assert len(data) == 1
    assert data[0][_NAMESPACE]["minutes"] == 2880.0


def test_the_daily_accumulation_still_serves_one_set_per_day(
    client: Any, a_cluster_id: str
) -> None:
    """``accumulate=false`` still keeps one set per day."""
    response = _get(
        client,
        window=_WINDOW,
        aggregate="namespace",
        filter=f'cluster:"{a_cluster_id}"',
        accumulate="false",
    )
    assert response.status_code == 200
    assert len(response.json()["data"]) == 2


@pytest.mark.parametrize(
    "filter_expression",
    [
        'pod:"a-pod"',
        'cluster:"x"+pod:"a-pod"',
        "cluster:x",
        'cluster:"x',
        'cluster:""',
    ],
)
def test_a_filter_this_phase_cannot_honour_is_refused(
    client: Any, filter_expression: str
) -> None:
    """A filter the phase cannot read is a 400 -- it is never served unfiltered."""
    response = _get(client, window=_WINDOW, aggregate="namespace", filter=filter_expression)
    assert response.status_code == 400
    assert response.json()["code"] == 400


# ── /clusterInfo ──────────────────────────────────────────────────────────────


def test_cluster_info_answers_for_the_filtered_cluster(
    client: Any, a_cluster_id: str
) -> None:
    """``/clusterInfo`` describes the cluster the filter names."""
    response = client.get("/clusterInfo", params={"filter": f'cluster:"{a_cluster_id}"'})
    assert response.status_code == 200

    body = response.json()
    assert body["code"] == 200
    assert body["data"] == {"version": "synthetic"}


def test_cluster_info_refuses_a_cluster_the_estate_does_not_have(client: Any) -> None:
    """A cluster the estate does not have is refused, not described."""
    response = client.get("/clusterInfo", params={"filter": 'cluster:"not-a-cluster"'})
    assert response.status_code == 400
    assert response.json()["code"] == 400


def test_cluster_info_refuses_a_request_without_a_cluster(client: Any) -> None:
    """``/clusterInfo`` describes ONE cluster: it needs to be told which."""
    response = client.get("/clusterInfo")
    assert response.status_code == 400
    assert response.json()["code"] == 400
