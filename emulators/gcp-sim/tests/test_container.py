"""The GKE cluster surface: ``projects.locations.clusters.list`` (container v1).

The Kubernetes Engine client reads the clusters of a project with
``GET https://container.googleapis.com/v1/projects/{project}/locations/{location}/clusters``
and reads a ``ListClustersResponse``: the ``clusters`` array and the ``missingZones``
array. The envelope is the API's, not the simulator's, so the test asserts the response
carries **exactly** those two members -- an extra one would be a member the provider
does not publish.

Each cluster carries only what the REST reference publishes for the members the estate
can answer for: ``name``, ``selfLink``, ``endpoint``, ``location`` and
``masterAuth.clusterCaCertificate``.
Every other published member of ``Cluster`` is registered as unproven in
``specs/gcp/container-clusters.schema.json``, so the absence of ``currentMasterVersion``,
``nodePools`` or ``network`` here is the spec's own rule, not an omission of the route.

The CA certificate is checked as a **certificate**, not as a string: it must parse, it
must be a CA, and it must carry no private key -- the reference publishes it as the
base64-encoded public certificate that roots the cluster's trust, and publishing the key
would publish a secret nobody published.
"""

from __future__ import annotations

import base64

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from fastapi.testclient import TestClient
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.resource import Resource

from gcp_sim import scope
from gcp_sim.estate import load_estate

_AUTH = {"Authorization": "Bearer synthetic-token"}

#: The published members of the list response (ListClustersResponse).
ENVELOPE_MEMBERS = frozenset({"clusters", "missingZones"})

#: The published members of one cluster, for the members the estate answers for.
CLUSTER_MEMBERS = frozenset({"name", "selfLink", "endpoint", "location", "masterAuth"})

#: ``MasterAuth`` publishes six members; the estate answers for one of them.
MASTER_AUTH_MEMBERS = frozenset({"clusterCaCertificate"})


def _project_id(estate: CanonicalEstate) -> str:
    """The first GCP project of the estate's org/folder tree."""
    return str(scope.projects(estate)[0].project.project_id)


def _clusters_of(estate: CanonicalEstate, project_id: str) -> tuple[Resource, ...]:
    """The estate's GKE clusters of one project."""
    return scope.resources_of_type(estate, "gke_cluster", project_id=project_id)


def _list(client: TestClient, project: str, location: str = "-") -> dict:
    """The raw response body of the cluster list."""
    resp = client.get(f"/container/v1/projects/{project}/locations/{location}/clusters", headers=_AUTH)
    assert resp.status_code == 200, resp.text
    body: dict = resp.json()
    return body


# -- the envelope ---------------------------------------------------------------------


def test_list_clusters_requires_a_bearer(client: TestClient) -> None:
    project = _project_id(load_estate())
    resp = client.get(f"/container/v1/projects/{project}/locations/-/clusters")
    assert resp.status_code == 401
    assert resp.json()["error"]["status"] == "UNAUTHENTICATED"


def test_the_envelope_carries_exactly_clusters_and_missing_zones(client: TestClient) -> None:
    project = _project_id(load_estate())
    body = _list(client, project)
    assert set(body) == ENVELOPE_MEMBERS
    assert body["missingZones"] == []
    assert body["clusters"], "the estate carries GKE clusters"


def test_a_cluster_carries_only_the_documented_members(client: TestClient) -> None:
    project = _project_id(load_estate())
    for row in _list(client, project)["clusters"]:
        assert set(row) == CLUSTER_MEMBERS
        assert set(row["masterAuth"]) == MASTER_AUTH_MEMBERS
        # The members the reference publishes and the estate does not model stay out.
        for absent in ("currentMasterVersion", "nodePools", "network", "status", "zone"):
            assert absent not in row


# -- the values ----------------------------------------------------------------------


def test_name_and_location_come_from_the_estate(client: TestClient) -> None:
    estate = load_estate()
    project = _project_id(estate)
    expected = _clusters_of(estate, project)
    served = {row["name"]: row for row in _list(client, project)["clusters"]}
    assert set(served) == {resource.resource_name for resource in expected}
    for resource in expected:
        row = served[resource.resource_name]
        assert row["location"] == resource.region_id


def test_the_self_link_is_the_full_resource_path(client: TestClient) -> None:
    """``selfLink`` names the cluster the way the Kubernetes Engine names it.

    The reference publishes ``selfLink`` as the server-defined URL of the resource;
    the canonical shape of that path is
    ``projects/<project>/locations/<location>/clusters/<name>``, and every segment
    of it is a field the estate carries -- the project that owns the cluster, the
    location it sits in and its own name. So the path is PUBLISHED, not invented.

    The name alone cannot identify a cluster: the estate reuses it across
    projects, and the path carries the project. That is what makes the path the
    key the CloudPilot needs (C-IDENT).
    """
    estate = load_estate()
    project = _project_id(estate)
    expected = _clusters_of(estate, project)
    served = {row["name"]: row for row in _list(client, project)["clusters"]}

    for resource in expected:
        row = served[resource.resource_name]
        assert row["selfLink"] == (
            f"projects/{project}/locations/{resource.region_id}/clusters/{resource.resource_name}"
        )
        # The short name stays the short name: the path does not replace it.
        assert row["name"] == resource.resource_name
        assert "/" not in row["name"]

    links = [row["selfLink"] for row in _list(client, project)["clusters"]]
    assert len(set(links)) == len(links), "two clusters share one self link"
    # Two calls describe the same clusters: a value that moved between calls would
    # make a client correlate two different answers about one cluster.
    assert _list(client, project) == _list(client, project)


def test_the_endpoint_is_a_deterministic_https_url(client: TestClient) -> None:
    estate = load_estate()
    project = _project_id(estate)
    by_name = {resource.resource_name: resource for resource in _clusters_of(estate, project)}
    for row in _list(client, project)["clusters"]:
        assert row["endpoint"].startswith("https://")
        # The endpoint is derived from the resource's own identity, so it names one cluster.
        assert by_name[row["name"]].identity.uuid in row["endpoint"]
    # Two calls describe the same clusters: a value that moved between calls would make
    # a client correlate two different answers about one cluster.
    assert _list(client, project) == _list(client, project)


def test_the_ca_certificate_is_a_certificate_and_carries_no_private_key(client: TestClient) -> None:
    project = _project_id(load_estate())
    for row in _list(client, project)["clusters"]:
        encoded = row["masterAuth"]["clusterCaCertificate"]
        pem = base64.b64decode(encoded, validate=True)
        assert pem.startswith(b"-----BEGIN CERTIFICATE-----")
        assert b"PRIVATE KEY" not in pem
        certificate = x509.load_pem_x509_certificate(pem)
        # It roots the cluster's trust, so it is a CA and it is not expired.
        assert certificate.extensions.get_extension_for_class(x509.BasicConstraints).value.ca is True
        assert certificate.not_valid_after_utc > certificate.not_valid_before_utc
        assert certificate.fingerprint(hashes.SHA256())


def test_one_cluster_always_carries_the_same_ca_certificate(client: TestClient) -> None:
    project = _project_id(load_estate())
    first = {row["name"]: row["masterAuth"]["clusterCaCertificate"] for row in _list(client, project)["clusters"]}
    second = {row["name"]: row["masterAuth"]["clusterCaCertificate"] for row in _list(client, project)["clusters"]}
    assert first == second
    # Two clusters are two roots of trust, not one shared by both.
    assert len(set(first.values())) == len(first)


# -- the scope -----------------------------------------------------------------------


def test_the_location_narrows_the_page_and_dash_matches_every_location(client: TestClient) -> None:
    estate = load_estate()
    project = _project_id(estate)
    expected = _clusters_of(estate, project)
    regions = sorted({resource.region_id for resource in expected})
    assert len(regions) > 1, "the estate places clusters in more than one location"
    for region in regions:
        rows = _list(client, project, region)["clusters"]
        assert rows
        assert {row["location"] for row in rows} == {region}
    # "-" matches all zones and all regions (published on the list method).
    assert len(_list(client, project, "-")["clusters"]) == len(expected)


def test_a_project_or_location_the_estate_does_not_carry_selects_nothing(client: TestClient) -> None:
    project = _project_id(load_estate())
    assert _list(client, "no-such-project")["clusters"] == []
    assert _list(client, project, "no-such-location")["clusters"] == []


def test_the_page_carries_no_other_provider_cluster(client: TestClient) -> None:
    estate = load_estate()
    project = _project_id(estate)
    served = {row["name"] for row in _list(client, project)["clusters"]}
    foreign = {r.resource_name for r in estate.resources if r.resource_type in {"aks_cluster", "eks_cluster"}}
    assert foreign
    assert served & foreign == set()


@pytest.mark.parametrize(
    "path",
    [
        "/container/v1/projects/contoso-prod-01/locations/-/clusters",
        "/container/v1/projects/contoso-prod-01/locations/us-central1/clusters",
    ],
)
def test_every_container_path_requires_a_bearer(client: TestClient, path: str) -> None:
    resp = client.get(path)
    assert resp.status_code == 401
    assert resp.json()["error"]["status"] == "UNAUTHENTICATED"
