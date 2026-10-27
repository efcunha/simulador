"""The AKS discovery list: the route the FinOps Kubernetes discovery actually reads.

FinOps lists the Azure clusters of the workspace's subscription through the ARM
**resources** list, filtered by resource type:
``ResourceManagementClient.resources.list(filter="resourceType eq
'Microsoft.ContainerService/managedClusters'")`` builds

    GET /subscriptions/{subscriptionId}/resources
        ?$filter=resourceType eq 'Microsoft.ContainerService/managedClusters'
        &api-version=2025-04-01

That is the request this file reproduces. The emulator had no route at that path, so
the request answered ``404`` with the ARM error envelope and the discovery failed on
it: the deployed stack's backend logged ``cluster_discovery_azure_error`` with
``(NotFound) Not Found`` while the simulator logged the same path as ``404 Not
Found``. The typed route (``.../providers/Microsoft.ContainerService/managedClusters``)
answered, but it answered with the estate's clusters of EVERY subscription, so a
caller asking about one subscription was handed another's rows.

Two spellings of a subscription are accepted, and both are exercised here: the GUID
the estate mints for its scope label (``identity.azure_subscription_guid``) and the
label itself (``sub-01``). The GUID is never written by hand in this file -- it is
derived from the estate's own seed -- so the route answers whatever subscription id
the caller holds, and the file pins no subscription into the code.
"""

from __future__ import annotations

from typing import Any

import pytest
from tools.synthetic_clouds.model.identity import azure_subscription_guid

#: The api-version the ARM resources list is read with, read off the installed
#: ``azure-mgmt-resource`` client (the operation's current version).
_RESOURCES_VERSION = "2025-04-01"

#: The api-version the typed ``managedClusters`` list is read with.
_TYPED_VERSION = "2024-09-01"

#: The resource type the discovery filters the resources list on.
_AKS_TYPE = "Microsoft.ContainerService/managedClusters"

#: The scope label the estate keys its Azure subscriptions under.
_SCOPE_LABEL = "sub-01"


def _guid(app) -> str:
    """The GUID the estate mints for its first subscription."""
    return azure_subscription_guid(app.state.estate.seed, _SCOPE_LABEL)


def _estate_clusters(app, scope_label: str) -> list[Any]:
    """The estate's Azure ``aks_cluster`` resources of one scope."""
    return [
        resource
        for resource in app.state.estate.resources
        if resource.identity.provider == "azure"
        and resource.resource_type == "aks_cluster"
        and resource.parent_scope_id == scope_label
    ]


def _resources_list(client, subscription_id: str, *, resource_type: str = _AKS_TYPE) -> Any:
    """The ARM resources list, filtered by resource type, as the client sends it."""
    return client.get(
        f"/subscriptions/{subscription_id}/resources",
        params={"$filter": f"resourceType eq '{resource_type}'", "api-version": _RESOURCES_VERSION},
    )


# ── The request the client makes ─────────────────────────────────────────────────


def test_the_discovery_list_answers_the_clients_request(api_client) -> None:
    """The list the discovery reads answers the estate's clusters of that subscription."""
    client, app = api_client
    resp = _resources_list(client, _guid(app))

    assert resp.status_code == 200, resp.text
    rows = resp.json()["value"]
    assert rows, "the estate carries Azure Kubernetes Service clusters"


def test_the_discovery_list_answers_the_subscription_the_caller_holds(api_client) -> None:
    """The GUID the caller holds is the estate's GUID for its subscription."""
    client, app = api_client
    guid = _guid(app)

    assert guid == azure_subscription_guid(app.state.estate.seed, _SCOPE_LABEL)
    assert _resources_list(client, guid).status_code == 200


def test_the_discovery_list_answers_the_scope_label_too(api_client) -> None:
    """The estate's own label is an accepted spelling, exactly like ``subscriptions.get``."""
    client, app = api_client
    by_guid = _resources_list(client, _guid(app)).json()["value"]
    by_label = _resources_list(client, _SCOPE_LABEL).json()["value"]

    assert by_label == by_guid


# ── The rows are the estate's rows ───────────────────────────────────────────────


def test_every_row_is_an_estate_cluster_of_the_subscription(api_client) -> None:
    """No cluster is invented: one row per estate cluster of that subscription."""
    client, app = api_client
    guid = _guid(app)
    rows = _resources_list(client, guid).json()["value"]

    expected = _estate_clusters(app, _SCOPE_LABEL)
    assert len(rows) == len(expected)
    assert {row["name"] for row in rows} == {resource.resource_name for resource in expected}

    for row in rows:
        assert row["type"] == _AKS_TYPE
        assert row["location"]
        assert isinstance(row["tags"], dict)
        # The subscription segment is a GUID and it is the one the caller asked under.
        assert str(row["id"]).split("/")[2] == guid
        assert "/resourceGroups/" in str(row["id"])
        assert str(row["id"]).endswith(f"/{row['name']}")


def test_a_subscription_answers_only_its_own_clusters(api_client) -> None:
    """Another subscription's scope must not answer with this one's clusters."""
    client, app = api_client
    guid = _guid(app)
    other = azure_subscription_guid(app.state.estate.seed, "sub-02")

    rows = _resources_list(client, guid).json()["value"]
    foreign = _resources_list(client, other).json()["value"]

    assert rows
    assert foreign
    assert {row["id"] for row in rows}.isdisjoint({row["id"] for row in foreign})


def test_an_unknown_subscription_answers_no_cluster(api_client) -> None:
    """A subscription the estate does not carry selects nothing, as the list surfaces do."""
    client, _ = api_client
    resp = _resources_list(client, "00000000-0000-0000-0000-000000000000")

    assert resp.status_code == 200
    assert resp.json()["value"] == []


# ── The filter ───────────────────────────────────────────────────────────────────


def test_a_filter_for_another_resource_type_is_refused(api_client) -> None:
    """The filter is read: a type this surface does not serve is refused, not emptied.

    An empty list would be read as "this subscription owns no resource of that type",
    which is false -- the estate carries virtual machines, published through the Compute
    resource plane's own list route.
    """
    client, app = api_client
    resp = _resources_list(client, _guid(app), resource_type="Microsoft.Compute/virtualMachines")

    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "BadRequest"


def test_the_filter_is_matched_case_insensitively(api_client) -> None:
    """ARM compares the resource type case-insensitively, so the gate does too."""
    client, app = api_client
    resp = _resources_list(client, _guid(app), resource_type="microsoft.containerservice/managedclusters")

    assert resp.status_code == 200
    assert resp.json()["value"]


def test_a_filter_the_emulator_cannot_read_is_rejected(api_client) -> None:
    """A filter it cannot apply is refused rather than answered with rows it ignores."""
    client, app = api_client
    resp = client.get(
        f"/subscriptions/{_guid(app)}/resources",
        params={"$filter": "tagName eq 'env'", "api-version": _RESOURCES_VERSION},
    )

    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "BadRequest"


# ── The api-version gate, shared by every one of them ────────────────────────────


def test_the_resources_list_gates_the_api_version(api_client) -> None:
    """An unsupported version is a 400 Azure envelope, never a silently served answer."""
    client, app = api_client
    path = f"/subscriptions/{_guid(app)}/resources"

    without_version = client.get(path, params={"$filter": f"resourceType eq '{_AKS_TYPE}'"})
    unsupported = client.get(
        path,
        params={"$filter": f"resourceType eq '{_AKS_TYPE}'", "api-version": "1999-01-01"},
    )
    for resp in (without_version, unsupported):
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "InvalidApiVersion"


# ── The typed route, under the same scope ────────────────────────────────────────


def test_the_typed_route_answers_the_clusters_of_the_scope(api_client) -> None:
    """``.../providers/Microsoft.ContainerService/managedClusters`` narrows on the scope."""
    client, app = api_client
    resp = client.get(
        f"/subscriptions/{_guid(app)}/providers/Microsoft.ContainerService/managedClusters?api-version={_TYPED_VERSION}"
    )

    assert resp.status_code == 200
    rows = resp.json()["value"]
    expected = _estate_clusters(app, _SCOPE_LABEL)
    assert len(rows) == len(expected)
    assert {row["name"] for row in rows} == {resource.resource_name for resource in expected}


def test_the_typed_route_under_a_resource_group_answers_the_same_clusters(api_client) -> None:
    """The resource-group spelling of the scope narrows on the same subscription."""
    client, app = api_client
    resp = client.get(
        f"/subscriptions/{_guid(app)}/resourceGroups/{_SCOPE_LABEL}"
        f"/providers/Microsoft.ContainerService/managedClusters?api-version={_TYPED_VERSION}"
    )

    assert resp.status_code == 200
    rows = resp.json()["value"]
    assert len(rows) == len(_estate_clusters(app, _SCOPE_LABEL))


def test_an_unknown_subscription_answers_no_cluster_on_the_typed_route(api_client) -> None:
    """The typed list selects nothing for a subscription the estate does not carry."""
    client, _ = api_client
    resp = client.get(
        "/subscriptions/00000000-0000-0000-0000-000000000000"
        f"/providers/Microsoft.ContainerService/managedClusters?api-version={_TYPED_VERSION}"
    )

    assert resp.status_code == 200
    assert resp.json()["value"] == []


@pytest.mark.parametrize("version", ["", "1999-01-01"])
def test_the_typed_route_gates_the_api_version(api_client, version: str) -> None:
    """An unsupported version is a 400 Azure envelope, never a silently served answer."""
    client, app = api_client
    query = f"?api-version={version}" if version else ""
    resp = client.get(f"/subscriptions/{_guid(app)}/providers/Microsoft.ContainerService/managedClusters{query}")

    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "InvalidApiVersion"
