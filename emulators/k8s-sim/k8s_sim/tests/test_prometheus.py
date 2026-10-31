"""Tests for the Prometheus plane of the k8s-sim: the instant query the CloudPilot
consumer reads the estate's namespace usage from.

**What the consumer does, and where that was measured** (read-only, 2026-10-31, on
``C:\\Projetos\\cloudpilot-deploy``):

* ``backend/app/services/k8s_finops/providers/opencost.py:112-132`` -- the provider
  asks ``GET {endpoint}/api/v1/query`` with the query in the ``query`` parameter and
  **without any authentication header**; the answer must carry ``status == "success"``
  or the telemetry is dropped.
* ``opencost.py:134-148`` -- the answer is read as ``data.result[]``, each entry
  carrying ``metric.namespace`` and ``value``, a two-element list whose second
  element is the number.
* ``opencost.py:150-184`` -- the two queries sent are the CPU one and the memory one,
  with the cluster the consumer holds in the selector -- the **native id** the
  discovery publishes.

The tests below pin the answer the way the consumer reads it, and pin the agreement
between the three planes of the same estate: the Kubernetes plane publishes the pod's
``requests``, the OpenCost plane costs them, and this plane measures them.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from k8s_sim.app import create_app
from k8s_sim.projections import allocation as allocation_projection
from k8s_sim.projections import kubernetes as kubernetes_projection

#: The namespace the estate carries.
_NAMESPACE = "payments"

#: The CPU the estate uses, in millicores: two cores.
_CPU_MILLICORES = "2000"

#: The memory the estate uses, in bytes: four gibibytes.
_MEMORY_BYTES = "4294967296"

#: The cluster the estate's first record carries -- the name is what the contract
#: publishes, and it is the label the answer carries.
_CLUSTER_NAME = "TEMP-aks_cluster-0025"


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


def _selector(cluster: str) -> str:
    """The selector the consumer builds, built the way the consumer builds it."""
    return f'cluster="{cluster}",container!="",image!=""'


def _cpu_query(cluster: str) -> str:
    """The CPU query the consumer sends."""
    return f"sum by (namespace) (rate(container_cpu_usage_seconds_total{{{_selector(cluster)}}}[5m])) * 1000"


def _memory_query(cluster: str) -> str:
    """The memory query the consumer sends."""
    return f"sum by (namespace) (container_memory_working_set_bytes{{{_selector(cluster)}}})"


def _result(client: TestClient, query: str) -> list[dict[str, Any]]:
    """The ``data.result`` of the answer, failing the test when it is not a success."""
    response = client.get("/api/v1/query", params={"query": query})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "success", payload
    result: list[dict[str, Any]] = payload["data"]["result"]
    return result


def test_the_plane_answers_without_a_token(client: TestClient) -> None:
    """The consumer sends no authentication header, so the plane asks for none.

    The provider's HTTP client carries no credential (``opencost.py:112-132``); a
    plane that demanded a token would answer ``401`` and the provider would drop the
    telemetry, which closes the rightsizing path.
    """
    response = client.get("/api/v1/query", params={"query": _cpu_query(_CLUSTER_NAME)})
    assert response.status_code == 200, response.text


def test_the_cpu_query_answers_the_namespace_usage(client: TestClient) -> None:
    """The CPU query answers the namespace's CPU, in millicores."""
    result = _result(client, _cpu_query(_CLUSTER_NAME))
    assert len(result) == 1, result
    assert result[0]["metric"]["namespace"] == _NAMESPACE
    assert result[0]["value"][1] == _CPU_MILLICORES


def test_the_memory_query_answers_the_namespace_usage(client: TestClient) -> None:
    """The memory query answers the namespace's memory, in bytes."""
    result = _result(client, _memory_query(_CLUSTER_NAME))
    assert len(result) == 1, result
    assert result[0]["metric"]["namespace"] == _NAMESPACE
    assert result[0]["value"][1] == _MEMORY_BYTES


def test_the_answer_carries_the_shape_the_consumer_reads(client: TestClient) -> None:
    """The answer is the Prometheus HTTP API's shape, read the way the consumer reads it.

    ``opencost.py:134-148`` wants ``status`` plus ``data.result[]``, and from each
    entry the ``metric.namespace`` and the ``value[1]`` -- a number it parses as a
    decimal and keeps only when it is finite and not negative.
    """
    response = client.get("/api/v1/query", params={"query": _cpu_query(_CLUSTER_NAME)})
    assert response.status_code == 200, response.text
    payload = response.json()

    assert set(payload) == {"status", "data"}
    assert payload["status"] == "success"
    assert payload["data"]["resultType"] == "vector"

    entry = payload["data"]["result"][0]
    assert set(entry) == {"metric", "value"}
    assert isinstance(entry["metric"]["namespace"], str)
    assert isinstance(entry["value"], list) and len(entry["value"]) == 2

    stamp, raw = entry["value"]
    assert isinstance(stamp, float)

    value = Decimal(str(raw))
    assert value.is_finite()
    assert value >= 0
    assert int(value) == 2000


def test_the_aggregation_drops_the_metric_name(client: TestClient) -> None:
    """The answer carries no ``__name__``: the aggregation groups by ``namespace`` only.

    Prometheus removes the metric name from the result of an aggregation that does not
    group by it, and the consumer's queries are exactly such an aggregation.
    """
    result = _result(client, _cpu_query(_CLUSTER_NAME))
    assert "__name__" not in result[0]["metric"], result[0]["metric"]


def test_the_three_planes_agree_on_the_usage(
    client: TestClient, a_cluster: dict[str, str]
) -> None:
    """The Kubernetes plane, the OpenCost plane and this plane describe one estate.

    The consumer builds the cost of a namespace by summing the ``requests`` of its
    pods, the OpenCost allocation costs that same figure, and this plane measures it.
    A fourth number would make the simulator say three different truths about the
    same cluster.
    """
    result = _result(client, _cpu_query(a_cluster["cluster_name"]))
    assert result[0]["value"][1] == _CPU_MILLICORES

    # The Kubernetes plane: the pod's requests.
    assert kubernetes_projection.CPU_REQUEST == "2"
    assert kubernetes_projection.MEMORY_REQUEST == "4Gi"

    # The OpenCost plane: the usage the allocation costs.
    response = client.get("/allocation/compute", params={"window": "2026-10-01,2026-10-01"})
    assert response.status_code == 200, response.text
    sets = response.json()["data"]
    assert sets, response.text
    items = sets[0]
    assert len(items) == 1, items
    allocation = next(iter(items.values()))
    assert allocation["cpuCores"] == 2.0
    assert allocation["ramBytes"] == 4294967296.0

    # This plane: the measured usage, in the unit the consumer reads it.
    assert int(_CPU_MILLICORES) == int(allocation["cpuCores"] * 1000)
    assert int(_MEMORY_BYTES) == int(allocation["ramBytes"])


def test_the_native_id_is_accepted_and_the_name_is_published(
    client: TestClient, a_cluster: dict[str, str]
) -> None:
    """The id the consumer holds is accepted; the answer carries the estate's name.

    The consumer keys its configuration by the **native id** the discovery publishes
    (the EKS ARN, the AKS ARM resource id, the GKE ``selfLink``) and sends it back in
    the selector. The estate accepts it as an alias and publishes the **name**, the
    same rule the OpenCost plane follows.
    """
    result = _result(client, _cpu_query(a_cluster["native_id"]))
    assert len(result) == 1, result
    assert result[0]["metric"]["cluster"] == a_cluster["cluster_name"]


def test_the_name_and_the_estate_id_are_accepted_too(
    client: TestClient, a_cluster: dict[str, str]
) -> None:
    """The other two aliases of the cluster answer the same series."""
    for alias in (a_cluster["cluster_name"], a_cluster["cluster_id"]):
        result = _result(client, _memory_query(alias))
        assert len(result) == 1, (alias, result)
        assert result[0]["value"][1] == _MEMORY_BYTES


def test_a_cluster_that_is_not_of_the_estate_selects_nothing(client: TestClient) -> None:
    """A cluster the estate does not carry selects no series.

    A Prometheus answers a query that selects nothing with an **empty vector**, not
    with an error -- and the OpenCost plane's ``400`` for an unknown cluster is the
    OpenCost plane's own contract, not this one's.
    """
    result = _result(client, _cpu_query("cluster-that-is-not-of-the-estate"))
    assert result == []


def test_a_query_the_estate_has_no_series_for_answers_an_empty_vector(client: TestClient) -> None:
    """A query this plane does not read answers with an empty vector.

    The estate publishes no series for the Karpenter metrics the consumer may ask
    for -- it models no Karpenter -- and inventing them would be saying something
    about an estate that does not exist.
    """
    for query in (
        "up",
        "karpenter_nodes_created_total",
        "karpenter_nodes_terminated_total",
        "histogram_quantile(0.95, sum(rate(karpenter_pods_startup_duration_seconds_bucket[5m])) by (le))",
    ):
        assert _result(client, query) == [], query


def test_a_request_without_a_query_is_refused(client: TestClient) -> None:
    """A request with no query is refused the way the Prometheus HTTP API refuses it."""
    response = client.get("/api/v1/query")
    assert response.status_code == 400, response.text
    payload = response.json()
    assert payload["status"] == "error"
    assert payload["errorType"] == "bad_data"
    assert "query" in payload["error"]


def test_the_evaluation_time_is_the_one_the_request_asks_for(client: TestClient) -> None:
    """A query carrying a ``time`` is evaluated at that instant.

    The Prometheus HTTP API takes the instant of the evaluation in the ``time``
    parameter -- a unix timestamp or an RFC 3339 instant.
    """
    for requested in ("1767225600", "2026-01-01T00:00:00Z"):
        response = client.get(
            "/api/v1/query", params={"query": _cpu_query(_CLUSTER_NAME), "time": requested}
        )
        assert response.status_code == 200, response.text
        stamp = response.json()["data"]["result"][0]["value"][0]
        assert stamp == pytest.approx(1767225600.0)


def test_an_unreadable_time_is_refused(client: TestClient) -> None:
    """A ``time`` this plane cannot read is refused, like the Prometheus HTTP API does."""
    response = client.get(
        "/api/v1/query", params={"query": _cpu_query(_CLUSTER_NAME), "time": "not-a-timestamp"}
    )
    assert response.status_code == 400, response.text
    payload = response.json()
    assert payload["status"] == "error"
    assert payload["errorType"] == "bad_data"
    assert "time" in payload["error"]


def test_the_value_is_the_same_across_calls(client: TestClient) -> None:
    """The estate's usage is constant, so only the evaluation instant moves.

    The value is what the consumer keeps; the stamp is the instant the query was
    evaluated at, and a Prometheus stamps it with the wall clock.
    """
    first = _result(client, _cpu_query(_CLUSTER_NAME))[0]
    second = _result(client, _cpu_query(_CLUSTER_NAME))[0]
    assert first["value"][1] == second["value"][1]
    assert first["metric"] == second["metric"]


def test_the_healthz_and_the_opencost_plane_are_untouched(client: TestClient) -> None:
    """The planes that already existed keep answering what they answered."""
    health = client.get("/healthz")
    assert health.status_code == 200, health.text

    allocation = client.get("/allocation/compute", params={"window": "2026-10-01,2026-10-01"})
    assert allocation.status_code == 200, allocation.text
    assert allocation.json()["code"] == 200


def test_the_kubernetes_plane_still_asks_for_a_token(client: TestClient) -> None:
    """The Kubernetes plane keeps its contract: a token is asked for, and required."""
    without = client.get("/api/v1/namespaces")
    assert without.status_code == 401, without.text

    with_token = client.get("/api/v1/namespaces", headers={"Authorization": "Bearer synthetic-token"})
    assert with_token.status_code == 200, with_token.text
