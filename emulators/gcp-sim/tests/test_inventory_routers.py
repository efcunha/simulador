"""Phase 6 router tests: the five API families projected from the canonical estate.

Same shape as ``test_routers.py`` (200 bodies, 400/401 through the GCP error envelope),
plus the assertion each new family owes: **the rows served are GCP rows**. Every family is
checked against the estate's own GCP resources -- the roster the projection must equal --
and against the neighbouring providers' equivalents (an Azure VM, an AWS EC2 instance, an
S3 bucket), which must never appear. A projection that walks ``estate.resources`` without
the boundary in ``gcp_sim/scope.py`` leaks exactly there, so that is where it is caught.

The estate is read through ``gcp_sim.estate.load_estate``, the same call app startup makes,
so the test and the served response describe one generation by construction.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.resource import Resource

from gcp_sim import scope
from gcp_sim.estate import load_estate

_AUTH = {"Authorization": "Bearer synthetic-token"}


def _of_type(estate: CanonicalEstate, resource_type: str, provider: str) -> tuple[Resource, ...]:
    """Every resource of one type on one provider (the leak check's reference set)."""
    return tuple(r for r in estate.resources if r.resource_type == resource_type and r.identity.provider == provider)


def _project_id(estate: CanonicalEstate) -> str:
    """The first GCP project of the estate's org/folder tree."""
    return str(scope.projects(estate)[0].project.project_id)


# -- cloudresourcemanager: projects.list -------------------------------------------


def test_projects_list_serves_the_estate_project_tree(client: TestClient) -> None:
    estate = load_estate()
    resp = client.get("/v1/projects", headers=_AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["nextPageToken"] == ""
    rows = body["projects"]
    assert [row["projectId"] for row in rows] == [owned.project.project_id for owned in scope.projects(estate)]
    folders = {owned.project.project_id: owned.folder_id for owned in scope.projects(estate)}
    for row in rows:
        assert row["name"]
        assert row["lifecycleState"] == "ACTIVE"
        assert row["parent"] == {"type": "folder", "id": folders[row["projectId"]]}
        # The estate mints a uuid, not GCP's numeric project id: absent, not invented.
        assert "projectNumber" not in row


def test_projects_list_carries_no_other_provider_scope(client: TestClient) -> None:
    estate = load_estate()
    served = {row["projectId"] for row in client.get("/v1/projects", headers=_AUTH).json()["projects"]}
    foreign = {s.subscription_id for group in estate.azure_mgmt_groups for s in group.subscriptions}
    foreign |= {account.account_id for org in estate.aws_orgs for account in org.accounts}
    assert served == {owned.project.project_id for owned in scope.projects(estate)}
    assert served & foreign == set()


@pytest.mark.parametrize(
    "path",
    [
        "/v1/projects",
        "/compute/v1/projects/contoso-prod-01/aggregated/instances",
        "/compute/v1/projects/contoso-prod-01/zones/us-central1-a/instances",
        "/v1/projects/contoso-prod-01/locations/-/functions",
        "/v1/projects/contoso-prod-01/locations/-/events",
        "/storage/v1/b?project=contoso-prod-01",
    ],
)
def test_every_new_family_requires_a_bearer(client: TestClient, path: str) -> None:
    resp = client.get(path)
    assert resp.status_code == 401
    assert resp.json()["error"]["status"] == "UNAUTHENTICATED"


# -- compute: instances.aggregatedList + instances.list ----------------------------


def test_aggregated_instances_groups_the_estate_instances_by_zone(client: TestClient) -> None:
    estate = load_estate()
    project = _project_id(estate)
    resp = client.get(f"/compute/v1/projects/{project}/aggregated/instances", headers=_AUTH)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert items, "the estate carries compute instances"
    assert all(key.startswith("zones/") for key in items)
    rows = [row for page in items.values() for row in page["instances"]]
    expected = scope.resources_of_type(estate, "compute_instance", project_id=project)
    assert sorted(row["name"] for row in rows) == sorted(r.resource_name for r in expected)
    for row in rows:
        assert f"zones/{row['zone']}" in items
        # The derived zone stays inside the resource's region -- the prefix the client filters on.
        assert row["zone"].rsplit("-", 1)[0] in {r.region_id for r in expected}
        assert row["machineType"] == f"zones/{row['zone']}/machineTypes/e2-standard-2"
        assert row["status"] == "RUNNING"
        assert isinstance(row["labels"], dict)


def test_zonal_instances_match_the_aggregated_zone(client: TestClient) -> None:
    estate = load_estate()
    project = _project_id(estate)
    aggregated = client.get(f"/compute/v1/projects/{project}/aggregated/instances", headers=_AUTH).json()["items"]
    zone = sorted(aggregated)[0].split("/", 1)[1]
    resp = client.get(f"/compute/v1/projects/{project}/zones/{zone}/instances", headers=_AUTH)
    assert resp.status_code == 200
    served = [row["name"] for row in resp.json()["items"]]
    assert served == [row["name"] for row in aggregated[f"zones/{zone}"]["instances"]]
    assert all(row["zone"] == zone for row in resp.json()["items"])


def test_instances_carry_no_other_provider_rows(client: TestClient) -> None:
    estate = load_estate()
    project = _project_id(estate)
    body = client.get(f"/compute/v1/projects/{project}/aggregated/instances", headers=_AUTH).json()
    served = {row["name"] for page in body["items"].values() for row in page["instances"]}
    assert served == {r.resource_name for r in scope.resources_of_type(estate, "compute_instance", project)}
    assert served & {r.resource_name for r in _of_type(estate, "ec2_instance", "aws")} == set()
    assert served & {r.resource_name for r in _of_type(estate, "virtual_machine", "azure")} == set()
    # A zone the estate places nothing in is not invented, and selects nothing.
    empty = client.get(f"/compute/v1/projects/{project}/zones/{project}-z9/instances", headers=_AUTH).json()
    assert empty["items"] == []


# -- functions: list_functions -----------------------------------------------------


def test_list_functions_serves_the_estate_functions(client: TestClient) -> None:
    estate = load_estate()
    project = _project_id(estate)
    resp = client.get(f"/v1/projects/{project}/locations/-/functions", headers=_AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["nextPageToken"] == ""
    expected = scope.resources_of_type(estate, "cloud_function", project_id=project)
    assert [row["name"] for row in body["functions"]] == [
        f"projects/{project}/locations/{r.region_id}/functions/{r.resource_name}" for r in expected
    ]
    for row in body["functions"]:
        assert row["status"] == "ACTIVE"
        assert isinstance(row["labels"], dict)
        # No estate field states a runtime, so none is served.
        assert "runtime" not in row


def test_list_functions_location_narrows_and_unknown_project_is_empty(client: TestClient) -> None:
    estate = load_estate()
    project = _project_id(estate)
    region = scope.resources_of_type(estate, "cloud_function", project_id=project)[0].region_id
    narrowed = client.get(f"/v1/projects/{project}/locations/{region}/functions", headers=_AUTH).json()
    assert narrowed["functions"], "the estate carries functions in every GCP region"
    assert all(f"/locations/{region}/" in row["name"] for row in narrowed["functions"])
    unknown = client.get("/v1/projects/no-such-project/locations/-/functions", headers=_AUTH).json()
    assert unknown == {"functions": [], "nextPageToken": ""}


def test_list_functions_carries_no_other_provider_rows(client: TestClient) -> None:
    estate = load_estate()
    project = _project_id(estate)
    served = client.get(f"/v1/projects/{project}/locations/-/functions", headers=_AUTH).json()["functions"]
    assert served
    foreign = {r.resource_name for r in _of_type(estate, "lambda_function", "aws")}
    assert {row["name"].rsplit("/", 1)[1] for row in served} & foreign == set()


# -- servicehealth: events.list ----------------------------------------------------


def test_service_health_events_is_an_empty_page(client: TestClient) -> None:
    """The estate models no health event, so the page is empty rather than invented."""
    project = _project_id(load_estate())
    resp = client.get(f"/v1/projects/{project}/locations/-/events", headers=_AUTH)
    assert resp.status_code == 200
    assert resp.json() == {"events": [], "nextPageToken": ""}


def test_service_health_events_stay_empty_for_any_location_or_filter(client: TestClient) -> None:
    project = _project_id(load_estate())
    for query in ("", "?pageSize=10&filter=state%3D%22ACTIVE%22", "?pageSize=1000"):
        resp = client.get(f"/v1/projects/{project}/locations/us-central1/events{query}", headers=_AUTH)
        assert resp.status_code == 200
        assert resp.json()["events"] == []


# -- storage: buckets.list ---------------------------------------------------------


def test_storage_buckets_serve_the_estate_buckets(client: TestClient) -> None:
    estate = load_estate()
    project = _project_id(estate)
    resp = client.get("/storage/v1/b", params={"project": project}, headers=_AUTH)
    assert resp.status_code == 200
    body = resp.json()
    # An exhausted page carries NO token: google-cloud-storage keeps paging while the
    # field is not None, so an empty one would loop forever.
    assert "nextPageToken" not in body
    expected = scope.resources_of_type(estate, "gcs_bucket", project_id=project)
    assert [row["name"] for row in body["items"]] == [r.resource_name for r in expected]
    for row, resource in zip(body["items"], expected, strict=True):
        assert row["location"] == resource.region_id
        assert row["storageClass"] == "STANDARD"
        assert isinstance(row["labels"], dict)


def test_storage_buckets_require_a_project(client: TestClient) -> None:
    resp = client.get("/storage/v1/b", headers=_AUTH)
    assert resp.status_code == 400
    assert resp.json()["error"]["status"] == "INVALID_ARGUMENT"


def test_storage_buckets_unknown_project_and_no_other_provider_rows(client: TestClient) -> None:
    estate = load_estate()
    unknown: dict[str, Any] = client.get("/storage/v1/b", params={"project": "no-such-project"}, headers=_AUTH).json()
    assert unknown == {"items": []}
    project = _project_id(estate)
    served = {row["name"] for row in client.get("/storage/v1/b", params={"project": project}, headers=_AUTH).json()["items"]}
    assert served == {r.resource_name for r in scope.resources_of_type(estate, "gcs_bucket", project)}
    assert served & {r.resource_name for r in _of_type(estate, "s3_bucket", "aws")} == set()
    assert served & {r.resource_name for r in _of_type(estate, "storage_account", "azure")} == set()
