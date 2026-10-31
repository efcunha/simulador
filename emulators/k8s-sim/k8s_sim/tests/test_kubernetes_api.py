"""The Kubernetes API plane of the k8s-sim, exercised through FastAPI's TestClient.

These tests pin the **wire contract the CloudPilot consumer reads**, not the implementation.
The literals here -- the namespace name, the workload name, the CPU and the memory -- are
written out on purpose, so that changing a constant in the simulator breaks the test instead
of silently redefining the contract.

What the consumer does with each route:

``/api/v1/namespaces``
    The ``ConnectionTester`` (the kubeconfig test that runs BEFORE a kubeconfig is saved)
    issues ``GET /api/v1/namespaces`` with a bearer token and **fails when the list of items
    is empty** ("Server returned 200 but no namespace items found"). The GCP and Azure
    providers read the same route to learn the estate's namespaces.

``/api/v1/pods``
    The EKS provider reaches it through the official ``kubernetes`` client
    (``CoreV1Api.list_pod_for_all_namespaces``), which deserializes the answer into a
    ``V1PodList``. Two fields of that model are required and are therefore pinned here:
    ``items`` on the list and ``name`` on every container.

``/api/v1/namespaces/{namespace}/pods``
    The GCP and Azure providers read it once per namespace, and build the namespace's usage
    out of the **requests** of the pods it returns.

The two planes of the simulator describe ONE estate, so the namespace and the workload here
are the same ones the OpenCost contract costs, and the pod's requests name the same usage the
allocation prices. The last test in this file pins that coherence: if the simulator ever
publishes two different truths about the same cluster, that test breaks.

The contract and the places where this phase narrows it are documented in
``docs/k8s-sim-opencost-contract.md``.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from k8s_sim.app import create_app
from k8s_sim.projections import allocation as allocation_projection
from k8s_sim.projections import kubernetes as kubernetes_projection

#: The token the consumer sends. The simulator models no identity, so any non-empty
#: bearer token is accepted -- what matters is that the header is there and is a bearer.
_TOKEN = "synthetic-token"

#: The namespace the estate carries.
_NAMESPACE = "payments"

#: The workload (the OpenCost controller) inside the namespace.
_WORKLOAD = "api"

#: The CPU the pod requests.
_CPU_REQUEST = "2"

#: The memory the pod requests.
_MEMORY_REQUEST = "4Gi"

#: The window the OpenCost plane is exercised with, for the non-regression tests.
_WINDOW = "2026-10-01,2026-10-02"

#: The fields the official Kubernetes model REQUIRES, read from the ``kubernetes``
#: 37.x models (``model_fields`` with ``is_required()``). The consumer deserializes
#: the answer with the official client, and a missing required field raises a
#: ``ValidationError`` before the payload is ever read -- so they are pinned here as
#: literals: ``V1OwnerReference`` requires ``apiVersion``, ``kind``, ``name`` and
#: ``uid``; ``V1Container`` requires ``name``; ``V1PodSpec`` requires ``containers``;
#: ``V1PodList`` and ``V1NamespaceList`` require ``items``.
_REQUIRED_OWNER_FIELDS = ("apiVersion", "kind", "name", "uid")


@pytest.fixture(scope="module")
def client() -> Any:
    return TestClient(create_app())


def _auth(token: str = _TOKEN) -> dict[str, str]:
    """The header the consumer sends on every Kubernetes API call."""
    return {"Authorization": f"Bearer {token}"}


def _memory_quantity_bytes(quantity: str) -> int:
    """The bytes a Kubernetes memory quantity names, read the way the consumer reads it.

    The consumer parses the binary suffixes (``Ki``, ``Mi``, ``Gi``, ``Ti``, ``Pi``) as
    powers of 1024 and the decimal ones (``k``, ``M``, ``G``, ``T``, ``P``) as powers of
    1000, and a bare number as bytes. Only the form this simulator publishes is handled
    here: a test that meets another form fails loudly instead of guessing.
    """
    for suffix, factor in (("Ki", 1024), ("Mi", 1024**2), ("Gi", 1024**3)):
        if quantity.endswith(suffix):
            return int(quantity[: -len(suffix)]) * factor
    raise AssertionError(f"the simulator publishes no memory quantity in this form: {quantity!r}")


# ── The namespaces ─────────────────────────────────────────────────────────────


def test_namespaces_without_a_bearer_token_are_refused(client: Any) -> None:
    """No token means 401 -- the shape the consumer categorizes as ``auth_rejected``."""
    response = client.get("/api/v1/namespaces")

    assert response.status_code == 401


def test_the_refusal_is_the_official_status_object(client: Any) -> None:
    """The failure carries the official ``Status`` shape, not the OpenCost envelope."""
    response = client.get("/api/v1/namespaces")
    body = response.json()

    assert body["kind"] == "Status"
    assert body["apiVersion"] == "v1"
    assert body["status"] == "Failure"
    assert body["reason"] == "Unauthorized"
    assert body["code"] == 401
    assert body["message"]


@pytest.mark.parametrize(
    "header",
    [
        "",
        "Bearer",
        "Bearer ",
        "Bearer    ",
        "Basic dXNlcjpwYXNz",
        "bearer-without-space",
    ],
)
def test_a_header_that_is_not_a_bearer_token_is_refused(client: Any, header: str) -> None:
    """Only a usable bearer token opens the plane."""
    response = client.get("/api/v1/namespaces", headers={"Authorization": header})

    assert response.status_code == 401


def test_the_bearer_scheme_is_matched_case_insensitively(client: Any) -> None:
    """HTTP says the scheme is case-insensitive, and so does this plane."""
    response = client.get("/api/v1/namespaces", headers={"Authorization": "bearer " + _TOKEN})

    assert response.status_code == 200


def test_namespaces_lists_the_estate_namespace(client: Any) -> None:
    """The route answers the official ``NamespaceList``."""
    response = client.get("/api/v1/namespaces", headers=_auth())
    body = response.json()

    assert response.status_code == 200
    assert body["kind"] == "NamespaceList"
    assert body["apiVersion"] == "v1"
    assert "metadata" in body
    assert isinstance(body["items"], list)


def test_the_namespace_list_carries_at_least_one_item(client: Any) -> None:
    """The consumer's test FAILS on an empty list -- that is its success condition."""
    response = client.get("/api/v1/namespaces", headers=_auth())
    items = response.json()["items"]

    assert len(items) >= 1


def test_the_namespace_is_named_the_way_the_estate_names_it(client: Any) -> None:
    """The consumer reads ``metadata.name`` -- that is the field it needs."""
    response = client.get("/api/v1/namespaces", headers=_auth())
    item = response.json()["items"][0]

    assert item["kind"] == "Namespace"
    assert item["apiVersion"] == "v1"
    assert item["metadata"]["name"] == _NAMESPACE


def test_the_api_plane_does_not_answer_with_the_opencost_envelope(client: Any) -> None:
    """The two planes answer in their own contracts -- no ``code``/``data`` here."""
    body = client.get("/api/v1/namespaces", headers=_auth()).json()

    assert "code" not in body
    assert "data" not in body


def test_two_equal_namespace_calls_answer_the_same_payload(client: Any) -> None:
    """The service is a pure function of the request."""
    first = client.get("/api/v1/namespaces", headers=_auth()).json()
    second = client.get("/api/v1/namespaces", headers=_auth()).json()

    assert first == second


# ── The pods ────────────────────────────────────────────────────────────────────


def test_pods_without_a_bearer_token_are_refused(client: Any) -> None:
    """The whole Kubernetes plane is behind the token."""
    response = client.get("/api/v1/pods")

    assert response.status_code == 401


def test_pods_lists_the_estate_pod(client: Any) -> None:
    """The route answers the official ``PodList``."""
    response = client.get("/api/v1/pods", headers=_auth())
    body = response.json()

    assert response.status_code == 200
    assert body["kind"] == "PodList"
    assert body["apiVersion"] == "v1"
    assert "metadata" in body
    assert isinstance(body["items"], list)
    assert len(body["items"]) == 1


def test_the_pod_carries_the_namespace_and_the_name(client: Any) -> None:
    """``metadata.namespace`` and ``metadata.name`` are what the consumer reads."""
    response = client.get("/api/v1/pods", headers=_auth())
    pod = response.json()["items"][0]

    assert pod["kind"] == "Pod"
    assert pod["apiVersion"] == "v1"
    assert pod["metadata"]["namespace"] == _NAMESPACE
    assert pod["metadata"]["name"] == _WORKLOAD


def test_the_pod_is_owned_by_the_workload(client: Any) -> None:
    """The consumer reads the owner to learn which workload the pod belongs to.

    The GCP and Azure providers take the owner's **name** as the workload -- and that name
    has to be the controller the OpenCost contract costs, or the two planes would name two
    different workloads. The EKS provider reads ``kind/name``.
    """
    response = client.get("/api/v1/pods", headers=_auth())
    owners = response.json()["items"][0]["metadata"]["ownerReferences"]

    assert len(owners) == 1
    assert owners[0]["kind"] == "Deployment"
    assert owners[0]["name"] == _WORKLOAD
    assert owners[0]["controller"] is True


def test_the_pod_declares_the_requests_the_consumer_reads(client: Any) -> None:
    """The consumer sums the pods' requests to obtain the namespace's usage."""
    response = client.get("/api/v1/pods", headers=_auth())
    containers = response.json()["items"][0]["spec"]["containers"]

    assert len(containers) == 1
    requests = containers[0]["resources"]["requests"]
    assert requests["cpu"] == _CPU_REQUEST
    assert requests["memory"] == _MEMORY_REQUEST


def test_every_owner_reference_carries_the_required_fields(client: Any) -> None:
    """``V1OwnerReference`` requires ``apiVersion``, ``kind``, ``name`` and ``uid``.

    The official client raises a ``ValidationError`` while deserializing a reference
    without them -- measured against the ``kubernetes`` 37.x models. The ``uid`` is the
    one that is easy to forget, because the estate models no object identity: the
    reference still names one.
    """
    response = client.get("/api/v1/pods", headers=_auth())
    owners = response.json()["items"][0]["metadata"]["ownerReferences"]

    for owner in owners:
        for field in _REQUIRED_OWNER_FIELDS:
            assert owner.get(field)


def test_every_container_has_a_name(client: Any) -> None:
    """``V1Container.name`` is REQUIRED by the official model.

    The consumer's EKS path deserializes the answer with the official ``kubernetes``
    client, and that client builds the model with ``klass(**data)`` -- a container without
    a name raises before the payload is ever read. This test is the guard against that.
    """
    response = client.get("/api/v1/pods", headers=_auth())

    for pod in response.json()["items"]:
        for container in pod["spec"]["containers"]:
            assert container["name"]


def test_every_list_carries_its_items_key(client: Any) -> None:
    """``items`` is what the consumer iterates -- an absent key is a ``None`` to them."""
    namespaces = client.get("/api/v1/namespaces", headers=_auth()).json()
    pods = client.get("/api/v1/pods", headers=_auth()).json()

    assert "items" in namespaces
    assert "items" in pods


# ── The pods of one namespace ───────────────────────────────────────────────────


def test_the_pods_of_a_namespace_are_served(client: Any) -> None:
    """The route the GCP and Azure providers call once per namespace."""
    response = client.get(f"/api/v1/namespaces/{_NAMESPACE}/pods", headers=_auth())
    body = response.json()

    assert response.status_code == 200
    assert body["kind"] == "PodList"
    assert len(body["items"]) == 1
    assert body["items"][0]["metadata"]["namespace"] == _NAMESPACE


def test_the_pods_of_a_namespace_without_a_token_are_refused(client: Any) -> None:
    """The token guards the route, not just the listing."""
    response = client.get(f"/api/v1/namespaces/{_NAMESPACE}/pods")

    assert response.status_code == 401


def test_a_namespace_the_estate_does_not_have_is_not_found(client: Any) -> None:
    """A namespace that is not there is a 404 with the official ``Status``."""
    response = client.get("/api/v1/namespaces/inexistente/pods", headers=_auth())
    body = response.json()

    assert response.status_code == 404
    assert body["kind"] == "Status"
    assert body["reason"] == "NotFound"
    assert body["code"] == 404


def test_two_equal_pod_calls_answer_the_same_payload(client: Any) -> None:
    """The service is a pure function of the request."""
    first = client.get("/api/v1/pods", headers=_auth()).json()
    second = client.get("/api/v1/pods", headers=_auth()).json()

    assert first == second


# ── The OpenCost plane is untouched ─────────────────────────────────────────────


def test_healthz_still_answers_without_a_token(client: Any) -> None:
    """The liveness probe the sibling sims expose stays open."""
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "synthetic": True}


def test_the_allocation_contract_still_answers_without_a_token(client: Any) -> None:
    """The OpenCost plane does not ask for a token -- it never did."""
    response = client.get(
        "/allocation/compute",
        params={
            "window": _WINDOW,
            "aggregate": "namespace",
            "step": "1d",
            "filter": 'cluster:"TEMP-aks_cluster-0025"',
        },
    )

    assert response.status_code == 200
    assert response.json()["code"] == 200


def test_the_cluster_info_route_still_answers_without_a_token(client: Any) -> None:
    """The OpenCost plane does not ask for a token -- it never did."""
    response = client.get(
        "/clusterInfo",
        params={"filter": 'cluster:"TEMP-aks_cluster-0025"'},
    )

    assert response.status_code == 200
    assert response.json() == {"code": 200, "data": {"version": "synthetic"}}


# ── The two planes describe one estate ──────────────────────────────────────────


def test_the_two_planes_name_the_same_namespace_and_workload(client: Any) -> None:
    """One estate, two projections -- the names cannot drift apart."""
    namespaces = client.get("/api/v1/namespaces", headers=_auth()).json()
    owner = client.get("/api/v1/pods", headers=_auth()).json()["items"][0]["metadata"][
        "ownerReferences"
    ][0]

    assert namespaces["items"][0]["metadata"]["name"] == allocation_projection.NAMESPACE
    assert owner["name"] == allocation_projection.CONTROLLER
    assert kubernetes_projection.NAMESPACE == allocation_projection.NAMESPACE
    assert kubernetes_projection.WORKLOAD == allocation_projection.CONTROLLER


def test_the_pod_requests_name_the_usage_the_allocation_prices(client: Any) -> None:
    """The consumer builds a namespace's cost out of the pods' requests.

    The allocation contract costs two CPU cores and four gibibytes of RAM per day; the pod
    requests two CPU cores and four gibibytes of RAM. If either side moved alone, the
    simulator would price a usage that the API plane does not declare.
    """
    figures = allocation_projection.figures(1)
    containers = client.get("/api/v1/pods", headers=_auth()).json()["items"][0]["spec"][
        "containers"
    ]
    requests = containers[0]["resources"]["requests"]

    assert float(requests["cpu"]) == figures["cpuCores"]
    assert _memory_quantity_bytes(requests["memory"]) == figures["ramBytes"]
