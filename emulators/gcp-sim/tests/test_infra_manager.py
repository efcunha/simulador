"""Infrastructure Manager resourceDrifts routes: official path, envelope and 401.

The records are projected from the same estate the other GCP routers use. The test does
not hard-code a resource name: it reads the projection and asks the service for that exact
preview, so a change in the C11 selection cannot leave the route untested.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tools.synthetic_clouds.model.drift import project_drift_views


def _sample_name(client: TestClient) -> str:
    estate = client.app.state.estate
    drift = project_drift_views(estate).gcp_resource_drifts[0]
    return drift.name


def test_list_resource_drifts_returns_the_official_envelope(client: TestClient) -> None:
    name = _sample_name(client)
    parts = name.split("/")
    project, location, preview = parts[1], parts[3], parts[5]

    response = client.get(
        f"/v1/projects/{project}/locations/{location}/previews/{preview}/resourceDrifts",
        headers={"Authorization": "Bearer synthetic"},
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"resourceDrifts", "nextPageToken", "unreachable"}
    assert body["resourceDrifts"]
    item = body["resourceDrifts"][0]
    assert set(item) == {"name", "terraformInfo", "propertyDrifts"}
    assert item["terraformInfo"]["type"] == "google_compute_instance"
    assert item["propertyDrifts"][0]["path"].startswith("labels.")


def test_get_resource_drift_by_name(client: TestClient) -> None:
    name = _sample_name(client)
    parts = name.split("/")
    project, location, preview, drift_id = parts[1], parts[3], parts[5], parts[7]

    response = client.get(
        f"/v1/projects/{project}/locations/{location}/previews/{preview}/resourceDrifts/{drift_id}",
        headers={"Authorization": "Bearer synthetic"},
    )

    assert response.status_code == 200
    assert response.json()["name"] == name


def test_resource_drifts_requires_a_bearer(client: TestClient) -> None:
    name = _sample_name(client)
    parts = name.split("/")
    response = client.get(
        f"/v1/projects/{parts[1]}/locations/{parts[3]}/previews/{parts[5]}/resourceDrifts"
    )
    assert response.status_code == 401
