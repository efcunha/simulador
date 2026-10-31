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

**The FQDN the discovery reads is published here too.** ``_list_aks_clusters`` reads
``properties.fqdn`` off the ARM payload and ``get_cluster_health`` hands it back as
the cluster's ``endpoint``; before this phase the estate published no FQDN at all,
so the endpoint was an empty string. The last section of this file pins the contract
of that field: a DNS host under the AKS suffix, stable, unique per cluster, and the
SAME on both routes -- because both routes serve the same projection. The estate
those assertions run against is the DEPLOYED one (``SEED=123``, ``medium``: 41
clusters in ``sub-01``), not the suite's default fixture.
"""

from __future__ import annotations

import re
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

#: The seed and profile the DEPLOYED stack runs with. The suite's shared ``api_client``
#: fixture runs the estate's defaults (seed 42, ``small`` profile), whose ``sub-01``
#: carries 8 clusters; the deployed estate carries 41, and 41 is the number the
#: discovery actually sees.
_DEPLOY_SEED = "123"
_DEPLOY_PROFILE = "medium"
_DEPLOY_SUBSCRIPTION_CLUSTERS = 41

#: The suffix AKS publishes its API server FQDN under.
_AKS_SUFFIX = ".azmk8s.io"

#: A DNS label: lower-case, only ``[a-z0-9-]``, no leading or trailing hyphen, and
#: at most 63 characters (RFC 1035).
_DNS_LABEL = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")

#: The characters a derived hash is written in.
_HEX = frozenset("0123456789abcdef")


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


def _typed_list(client, subscription_id: str) -> Any:
    """The typed ``managedClusters`` list of one subscription."""
    return client.get(
        f"/subscriptions/{subscription_id}/providers/Microsoft.ContainerService/managedClusters"
        f"?api-version={_TYPED_VERSION}"
    )


def _assert_dns_hostname(value: object) -> None:
    """Assert ``value`` is a DNS host under the AKS suffix -- and nothing more.

    A host is not a URL: no scheme, no port, no path. The consumer (``_AKSKubernetesClient``)
    builds the endpoint out of it, so a value that carried ``https://`` would be a
    broken contract rather than a different spelling.
    """
    assert isinstance(value, str), f"the FQDN must be a string, got {type(value).__name__}"
    assert value, "the FQDN must not be empty"
    assert "://" not in value, f"the FQDN is a host, not a URL: {value!r}"
    assert ":" not in value, f"the FQDN carries no port: {value!r}"
    assert "/" not in value, f"the FQDN carries no path: {value!r}"
    assert value.endswith(_AKS_SUFFIX), f"the FQDN is not under {_AKS_SUFFIX}: {value!r}"
    assert len(value) <= 253, f"the FQDN is longer than a DNS name: {value!r}"
    for label in value.split("."):
        assert _DNS_LABEL.match(label), f"not a DNS label: {label!r} (in {value!r})"


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


# ── The FQDN the discovery reads ─────────────────────────────────────────────────


@pytest.fixture(scope="module")
def deploy_client():
    """A client bound to the DEPLOYED estate: ``SEED=123``, ``PROFILE=medium``.

    The suite's shared ``api_client`` fixture runs the estate's defaults (seed 42,
    ``small`` profile), whose ``sub-01`` carries 8 clusters. The deployed stack runs
    SEED=123/medium, whose ``sub-01`` carries 41 -- the number the discovery actually
    sees, and the number the FQDN contract is proved against.

    The estate is built once for the module: the generator is deterministic in
    ``(seed, profile)``, so a second request answers the same rows.
    """
    from fastapi.testclient import TestClient

    from azure_sim.api.app import create_app
    from azure_sim.config import load_settings

    settings = load_settings(
        env={"SEED": _DEPLOY_SEED, "PROFILE": _DEPLOY_PROFILE},
        API_PAGE_SIZE=10000,
    )
    app = create_app(settings)
    with TestClient(app) as client:
        yield client, app


def test_the_deployed_subscription_carries_its_forty_one_clusters(deploy_client) -> None:
    """The deployed estate's ``sub-01`` is the 41-cluster one the discovery reads."""
    client, app = deploy_client
    rows = _resources_list(client, _guid(app)).json()["value"]

    assert len(_estate_clusters(app, _SCOPE_LABEL)) == _DEPLOY_SUBSCRIPTION_CLUSTERS
    assert len(rows) == _DEPLOY_SUBSCRIPTION_CLUSTERS


def test_every_row_of_both_routes_carries_an_fqdn(deploy_client) -> None:
    """Both routes publish a non-empty ``properties.fqdn`` on every cluster row."""
    client, app = deploy_client
    guid = _guid(app)
    resources = _resources_list(client, guid).json()["value"]
    typed = _typed_list(client, guid).json()["value"]

    assert resources and typed
    for row in resources + typed:
        properties = row["properties"]
        assert "fqdn" in properties, f"no fqdn published for {row['name']!r}"
        assert properties["fqdn"], f"an empty fqdn published for {row['name']!r}"


def test_the_fqdn_is_a_host_under_the_aks_suffix(deploy_client) -> None:
    """A host, not a URL: no scheme, no port, and under the AKS suffix."""
    client, app = deploy_client
    rows = _resources_list(client, _guid(app)).json()["value"]

    for row in rows:
        _assert_dns_hostname(row["properties"]["fqdn"])


def test_the_fqdn_has_the_published_shape(deploy_client) -> None:
    """``<cluster>-<hash>.<region>.azmk8s.io``: the cluster, a hash, and the region.

    The suffix is TWO labels (``azmk8s`` and ``io``), so the host has four of them.
    """
    client, app = deploy_client
    rows = _resources_list(client, _guid(app)).json()["value"]

    for row in rows:
        fqdn = row["properties"]["fqdn"]
        cluster_label, region, zone, tld = fqdn.split(".")
        assert (zone, tld) == ("azmk8s", "io")
        assert region == row["location"]

        label, _, digest = cluster_label.rpartition("-")
        assert label, f"no cluster label in {fqdn!r}"
        assert digest and set(digest) <= _HEX, f"the hash is not hex in {fqdn!r}"


def test_a_name_that_is_not_a_dns_label_is_normalized(deploy_client) -> None:
    """``aks_cluster-0187 (do not delete)`` is published as a DNS-valid host.

    The estate's cluster names are generator names, not DNS labels: they carry
    underscores, upper-case characters, spaces and parentheses. The published host is
    the normalized reading of that name, so the field stays a hostname a client can be
    handed -- and the name's CONTENT survives the normalization, so the host still
    names the cluster.
    """
    client, app = deploy_client
    rows = _resources_list(client, _guid(app)).json()["value"]
    by_name = {row["name"]: row["properties"]["fqdn"] for row in rows}

    awkward = [name for name in by_name if "_" in name or name != name.lower()]
    assert awkward, "the deployed estate carries a name that needs normalizing"

    for name in awkward:
        fqdn = by_name[name]
        _assert_dns_hostname(fqdn)
        assert "_" not in fqdn
        assert "(" not in fqdn and " " not in fqdn
        # Every run of letters and digits of the name survives the normalization: the
        # host still NAMES the cluster, it is not a hash of nothing.
        cluster_label = fqdn.split(".")[0]
        for run in re.findall(r"[a-z0-9]+", name.lower()):
            assert run in cluster_label, f"{run!r} of {name!r} is missing from {fqdn!r}"


def test_the_fqdn_is_stable_between_calls(deploy_client) -> None:
    """The same cluster answers the same FQDN on every call."""
    client, app = deploy_client
    guid = _guid(app)

    first = {row["name"]: row["properties"]["fqdn"] for row in _resources_list(client, guid).json()["value"]}
    second = {row["name"]: row["properties"]["fqdn"] for row in _resources_list(client, guid).json()["value"]}

    assert first == second
    assert all(first.values())


def test_the_fqdn_is_unique_per_cluster(deploy_client) -> None:
    """No two clusters of the subscription share an FQDN."""
    client, app = deploy_client
    rows = _resources_list(client, _guid(app)).json()["value"]
    fqdns = [row["properties"]["fqdn"] for row in rows]

    assert len(set(fqdns)) == len(fqdns)
    assert len(fqdns) == _DEPLOY_SUBSCRIPTION_CLUSTERS


def test_both_routes_serve_the_same_fqdn_for_the_same_cluster(deploy_client) -> None:
    """The typed list and the ARM resources list agree, cluster by cluster.

    Both routes serve the same projection, so a cluster cannot answer one FQDN on
    the typed list and another on the resources list: the consumer that reads the
    resources list and the consumer that reads the typed one would then disagree
    about the same cluster.
    """
    client, app = deploy_client
    guid = _guid(app)
    resources = {row["name"]: row["properties"]["fqdn"] for row in _resources_list(client, guid).json()["value"]}
    typed = {row["name"]: row["properties"]["fqdn"] for row in _typed_list(client, guid).json()["value"]}

    assert resources == typed


def test_the_properties_carry_no_field_beyond_the_fqdn(deploy_client) -> None:
    """``fqdn`` joins ``provisioningState``; no other property is published.

    The absence matters as much as the presence: an empty ``agentPoolProfiles``
    would claim a cluster with no node pools, and a ``dnsPrefix`` would claim a DNS
    prefix the estate does not model. Both stay absent.
    """
    client, app = deploy_client
    rows = _resources_list(client, _guid(app)).json()["value"]

    for row in rows:
        assert set(row["properties"]) == {"provisioningState", "fqdn"}
        assert "agentPoolProfiles" not in row["properties"]
        assert "dnsPrefix" not in row["properties"]
        assert "privateFqdn" not in row["properties"]
