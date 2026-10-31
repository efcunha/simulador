"""Tests for the Kubecost plane of the k8s-sim: the Model API's allocation route, the
one the CloudPilot consumer's ``kubecost`` provider reads.

**What the consumer does, and where that was measured** (read-only, 2026-10-31, on
``C:\\Projetos\\cloudpilot-deploy``):

* ``backend/app/services/k8s_finops/providers/kubecost.py:305-323`` -- ``get_cluster_costs``
  asks ``GET {endpoint}/model/allocation`` with ``window``, ``aggregate=namespace``,
  ``filterClusters`` and ``accumulate=false``.
* ``kubecost.py:326-343`` -- ``get_namespace_costs`` asks the same route with
  ``aggregate=controller``, ``filterClusters`` and ``filterNamespaces``.
* ``kubecost.py:404-424`` -- ``get_resource_labels`` asks the same route with
  ``aggregate=controller``, ``filterClusters``, ``filterNamespaces`` and
  ``filterControllers``.
* ``kubecost.py:378-402`` and ``kubecost.py:544-559`` -- ``get_cluster_health`` and
  ``test_connection`` ask ``GET {endpoint}/model/clusterInfo``, a route the Kubecost
  Model API does **not** publish (F15 lists its fifteen paths and this is not one of
  them).

Those three requests were measured against this service on 2026-10-31, before the
plane existed: all of them answered ``404``. The tests below pin the answer the way
the consumer reads it, and pin the agreement between the four planes of the same estate:
the Kubernetes plane publishes the pod's ``requests``, the Prometheus plane measures
them, the OpenCost plane costs them, and this plane costs them through the other
contract.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from k8s_sim.app import create_app
from k8s_sim.projections import allocation as allocation_projection
from k8s_sim.projections import kubernetes as kubernetes_projection

#: The costs of the workload over one day, in the order the rate card names them.
_CPU_COST = 1.92
_RAM_COST = 0.576
_PV_COST = 0.384
_NETWORK_COST = 1.0
_TOTAL_COST = 3.88

#: The CPU the estate uses: two cores, as the request and as the usage.
_CPU_CORES = 2.0

#: The memory the estate uses, in bytes: four gibibytes.
_MEMORY_BYTES = 4294967296.0

#: The window the consumer asks for, spelled the way it spells it.
_WINDOW = "2026-10-01,2026-10-01"

#: A window of three days.
_WINDOW_THREE_DAYS = "2026-10-01,2026-10-03"


@pytest.fixture(scope="module")
def client() -> Any:
    """A TestClient over a freshly built app."""
    return TestClient(create_app())


@pytest.fixture(scope="module")
def a_cluster() -> dict[str, str]:
    """One cluster of the estate -- the first one, in the fixture's own order.

    The record carries the three aliases the estate accepts: the name, the canonical
    ``cluster_id`` and the ``native_id`` the discovery publishes.
    """
    records = list(allocation_projection.estate_clusters().values())
    assert records, "the estate fixture carries no cluster"
    return records[0]


def _the_allocation(payload: dict[str, Any]) -> dict[str, Any]:
    """The one allocation of the answer, read the way the consumer reads it."""
    sets = payload["data"]
    assert len(sets) == 1, "the answer carries one allocation set"
    allocation: dict[str, Any] = next(iter(sets[0].values()))
    return allocation


def test_the_consumer_request_answers_the_model_api_envelope(
    client: Any, a_cluster: dict[str, str]
) -> None:
    """The request the consumer sends -- measured, not guessed -- is answered."""
    response = client.get(
        "/model/allocation",
        params={
            "window": _WINDOW,
            "aggregate": "namespace",
            "filterClusters": a_cluster["native_id"],
            "accumulate": "false",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 200
    assert isinstance(payload["data"], list)
    assert len(payload["data"]) == 1


def test_the_allocation_carries_the_kubecost_field_names(
    client: Any, a_cluster: dict[str, str]
) -> None:
    """The allocation carries the fields the Kubecost Model API publishes."""
    response = client.get(
        "/model/allocation",
        params={"window": _WINDOW, "filterClusters": a_cluster["native_id"]},
    )

    allocation = _the_allocation(response.json())
    assert allocation["cpuCost"] == pytest.approx(_CPU_COST)
    assert allocation["ramCost"] == pytest.approx(_RAM_COST)
    assert allocation["pvCost"] == pytest.approx(_PV_COST)
    assert allocation["networkCost"] == pytest.approx(_NETWORK_COST)
    assert allocation["totalCost"] == pytest.approx(_TOTAL_COST)


def test_the_allocation_does_not_carry_mem_cost(client: Any, a_cluster: dict[str, str]) -> None:
    """``memCost`` is not a field the Kubecost model publishes, so it is not published.

    The consumer's parser reads ``alloc.get("memCost", 0)`` (``kubecost.py:216``), so its
    memory cost is zero against a Kubecost that publishes ``ramCost`` (F16). That is a
    consumer-side reading: this plane publishes the field the source publishes.
    """
    response = client.get(
        "/model/allocation",
        params={"window": _WINDOW, "filterClusters": a_cluster["native_id"]},
    )

    allocation = _the_allocation(response.json())
    assert "memCost" not in allocation
    assert "ramCost" in allocation


def test_the_allocation_does_not_carry_minutes(client: Any, a_cluster: dict[str, str]) -> None:
    """``minutes`` is not a field of the Model API's ``Allocation`` schema."""
    response = client.get(
        "/model/allocation",
        params={"window": _WINDOW, "filterClusters": a_cluster["native_id"]},
    )

    assert "minutes" not in _the_allocation(response.json())


def test_the_allocation_carries_the_four_averages(
    client: Any, a_cluster: dict[str, str]
) -> None:
    """The four averages the Model API publishes are there, and they agree.

    The estate declares that the request **is** the usage -- the pod asks for two cores
    and four gibibytes and the Prometheus plane measures exactly that figure -- so the
    request average and the usage average carry the same number.
    """
    response = client.get(
        "/model/allocation",
        params={"window": _WINDOW, "filterClusters": a_cluster["native_id"]},
    )

    allocation = _the_allocation(response.json())
    assert allocation["cpuCoreRequestAverage"] == pytest.approx(_CPU_CORES)
    assert allocation["cpuCoreUsageAverage"] == pytest.approx(_CPU_CORES)
    assert allocation["ramByteRequestAverage"] == pytest.approx(_MEMORY_BYTES)
    assert allocation["ramByteUsageAverage"] == pytest.approx(_MEMORY_BYTES)


def test_the_allocation_publishes_the_cluster_name(
    client: Any, a_cluster: dict[str, str]
) -> None:
    """The alias the request came in through is accepted; the **name** is published."""
    response = client.get(
        "/model/allocation",
        params={"window": _WINDOW, "filterClusters": a_cluster["native_id"]},
    )

    allocation = _the_allocation(response.json())
    assert allocation["properties"]["cluster"] == a_cluster["cluster_name"]


def test_the_allocation_publishes_the_workload(
    client: Any, a_cluster: dict[str, str]
) -> None:
    """The allocation names the workload the estate carries."""
    response = client.get(
        "/model/allocation",
        params={"window": _WINDOW, "filterClusters": a_cluster["native_id"]},
    )

    allocation = _the_allocation(response.json())
    assert allocation["properties"]["namespace"] == allocation_projection.NAMESPACE
    assert allocation["properties"]["controller"] == allocation_projection.CONTROLLER


def test_the_namespace_aggregate_keys_by_the_namespace(
    client: Any, a_cluster: dict[str, str]
) -> None:
    """``aggregate=namespace`` keys by the namespace, as the official key rule says."""
    response = client.get(
        "/model/allocation",
        params={
            "window": _WINDOW,
            "aggregate": "namespace",
            "filterClusters": a_cluster["native_id"],
        },
    )

    (key,) = response.json()["data"][0]
    assert key == kubernetes_projection.NAMESPACE


def test_the_controller_aggregate_keys_by_the_controller(
    client: Any, a_cluster: dict[str, str]
) -> None:
    """``aggregate=controller`` keys by the controller -- the consumer's second request."""
    response = client.get(
        "/model/allocation",
        params={
            "window": _WINDOW,
            "aggregate": "controller",
            "filterClusters": a_cluster["native_id"],
            "filterNamespaces": kubernetes_projection.NAMESPACE,
            "accumulate": "false",
        },
    )

    assert response.status_code == 200
    (key,) = response.json()["data"][0]
    assert key == allocation_projection.CONTROLLER


def test_a_cluster_the_estate_does_not_have_is_answered_empty(
    client: Any,
) -> None:
    """A cluster that is not in the fixture selects nothing, and nothing is invented."""
    response = client.get(
        "/model/allocation",
        params={"window": _WINDOW, "filterClusters": "cluster-that-does-not-exist"},
    )

    assert response.status_code == 200
    assert response.json()["data"] == []


def test_a_namespace_the_estate_does_not_carry_is_answered_empty(
    client: Any, a_cluster: dict[str, str]
) -> None:
    """A namespace the estate does not carry selects nothing."""
    response = client.get(
        "/model/allocation",
        params={
            "window": _WINDOW,
            "filterClusters": a_cluster["native_id"],
            "filterNamespaces": "namespace-that-does-not-exist",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"] == []


def test_a_filter_list_is_refused(client: Any) -> None:
    """The Model API publishes the filters as lists; this phase reads one value."""
    response = client.get(
        "/model/allocation",
        params={"window": _WINDOW, "filterClusters": "cluster-a,cluster-b"},
    )

    assert response.status_code == 400
    assert response.json()["code"] == 400


def test_a_missing_window_is_refused(client: Any, a_cluster: dict[str, str]) -> None:
    """``window`` is required by the Model API."""
    response = client.get(
        "/model/allocation", params={"filterClusters": a_cluster["native_id"]}
    )

    assert response.status_code == 400
    assert response.json()["code"] == 400


def test_a_malformed_window_is_refused(client: Any, a_cluster: dict[str, str]) -> None:
    """A window this phase cannot read is refused, not guessed."""
    response = client.get(
        "/model/allocation",
        params={"window": "2026-10-01", "filterClusters": a_cluster["native_id"]},
    )

    assert response.status_code == 400


def test_an_unsupported_aggregate_is_refused(client: Any, a_cluster: dict[str, str]) -> None:
    """An aggregation this phase cannot answer is refused with a 400."""
    response = client.get(
        "/model/allocation",
        params={
            "window": _WINDOW,
            "aggregate": "service",
            "filterClusters": a_cluster["native_id"],
        },
    )

    assert response.status_code == 400
    assert response.json()["code"] == 400


def test_an_unsupported_step_is_refused(client: Any, a_cluster: dict[str, str]) -> None:
    """A step this phase cannot serve is refused with a 400."""
    response = client.get(
        "/model/allocation",
        params={
            "window": _WINDOW,
            "step": "1h",
            "filterClusters": a_cluster["native_id"],
        },
    )

    assert response.status_code == 400


def test_a_parameter_this_phase_does_not_read_is_refused(
    client: Any, a_cluster: dict[str, str]
) -> None:
    """A filter this phase cannot honour is refused, never ignored."""
    response = client.get(
        "/model/allocation",
        params={
            "window": _WINDOW,
            "filterClusters": a_cluster["native_id"],
            "filterLabels": "app:payments",
        },
    )

    assert response.status_code == 400
    assert response.json()["code"] == 400


def test_the_csv_format_is_refused(client: Any, a_cluster: dict[str, str]) -> None:
    """The Model API publishes a CSV format; this phase serves the JSON one only."""
    response = client.get(
        "/model/allocation",
        params={
            "window": _WINDOW,
            "format": "csv",
            "filterClusters": a_cluster["native_id"],
        },
    )

    assert response.status_code == 400


def test_without_a_step_the_answer_is_one_set_for_the_window(
    client: Any, a_cluster: dict[str, str]
) -> None:
    """The Model API's default step is the window itself (F15)."""
    response = client.get(
        "/model/allocation",
        params={"window": _WINDOW_THREE_DAYS, "filterClusters": a_cluster["native_id"]},
    )

    payload = response.json()
    assert len(payload["data"]) == 1
    allocation = _the_allocation(payload)
    assert allocation["totalCost"] == pytest.approx(_TOTAL_COST * 3)


def test_with_a_daily_step_the_answer_is_one_set_per_day(
    client: Any, a_cluster: dict[str, str]
) -> None:
    """``step=1d`` yields one set per day, each with the cost of its day."""
    response = client.get(
        "/model/allocation",
        params={
            "window": _WINDOW_THREE_DAYS,
            "step": "1d",
            "filterClusters": a_cluster["native_id"],
        },
    )

    payload = response.json()
    assert len(payload["data"]) == 3
    for day_set in payload["data"]:
        (allocation,) = day_set.values()
        assert allocation["totalCost"] == pytest.approx(_TOTAL_COST)


def test_accumulate_sums_the_window(client: Any, a_cluster: dict[str, str]) -> None:
    """``accumulate=true`` asks for the whole range in a single set."""
    response = client.get(
        "/model/allocation",
        params={
            "window": _WINDOW_THREE_DAYS,
            "step": "1d",
            "accumulate": "true",
            "filterClusters": a_cluster["native_id"],
        },
    )

    payload = response.json()
    assert len(payload["data"]) == 1
    assert _the_allocation(payload)["totalCost"] == pytest.approx(_TOTAL_COST * 3)


def test_the_authorization_header_is_accepted_and_not_required(
    client: Any, a_cluster: dict[str, str]
) -> None:
    """The Model API declares no security scheme, so no token is demanded.

    The consumer always sends one; it is welcome and unused.
    """
    params = {"window": _WINDOW, "filterClusters": a_cluster["native_id"]}

    without = client.get("/model/allocation", params=params)
    with_header = client.get(
        "/model/allocation", params=params, headers={"Authorization": "Bearer a-token"}
    )

    assert without.status_code == 200
    assert with_header.status_code == 200
    assert without.json() == with_header.json()


def test_the_kubecost_plane_costs_the_same_estate_as_the_opencost_plane(
    client: Any, a_cluster: dict[str, str]
) -> None:
    """One estate, two contracts, the same numbers.

    The OpenCost plane answers the same window with the same cost -- the contract that
    already existed is untouched, and the new plane does not make the simulator say two
    truths about the same cluster.
    """
    params = {"window": _WINDOW, "filterClusters": a_cluster["native_id"]}
    kubecost = _the_allocation(client.get("/model/allocation", params=params).json())

    opencost_response = client.get(
        "/allocation/compute",
        params={
            "window": _WINDOW,
            "aggregate": "namespace",
            "step": "1d",
            "filter": f'cluster:"{a_cluster["native_id"]}"',
        },
    )
    (opencost,) = opencost_response.json()["data"][0].values()

    assert kubecost["totalCost"] == pytest.approx(opencost["totalCost"])
    assert kubecost["cpuCost"] == pytest.approx(opencost["cpuCost"])
    assert kubecost["ramCost"] == pytest.approx(opencost["ramCost"])
    assert kubecost["pvCost"] == pytest.approx(opencost["pvCost"])
    assert kubecost["networkCost"] == pytest.approx(opencost["networkCost"])


def test_the_kubecost_plane_agrees_with_the_prometheus_plane(
    client: Any, a_cluster: dict[str, str]
) -> None:
    """The averages agree with the usage the Prometheus plane measures."""
    response = client.get(
        "/model/allocation",
        params={"window": _WINDOW, "filterClusters": a_cluster["native_id"]},
    )

    allocation = _the_allocation(response.json())
    assert allocation["cpuCoreUsageAverage"] == pytest.approx(
        kubernetes_projection.CPU_CORES
    )
    assert allocation["ramByteUsageAverage"] == pytest.approx(
        kubernetes_projection.MEMORY_BYTES
    )


def test_the_routes_the_model_api_does_not_publish_are_not_served() -> None:
    """``/model/clusterInfo`` and ``/savings/requestSizing`` are not published.

    The consumer asks for both (F18); the Kubecost Model API publishes neither (F15),
    and this service does not serve what the source does not publish. The gaps are
    declared in ``docs/k8s-sim-opencost-contract.md``.
    """
    client = TestClient(create_app())

    assert client.get("/model/clusterInfo").status_code == 404
    assert client.get("/savings/requestSizing").status_code == 404


def test_the_health_probe_still_answers(client: Any) -> None:
    """The liveness probe the sibling sims expose is untouched."""
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "synthetic": True}
