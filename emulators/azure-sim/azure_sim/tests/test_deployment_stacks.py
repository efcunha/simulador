"""Deployment Stacks what-if results: official path, api-version gate and 404.

The result is projected from the same frozen estate the other ARM routers use. The test
reads the projection to discover the result id, so it exercises the real C11 selection
instead of hard-coding a subscription/resource group.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from azure_sim.api.app import create_app
from azure_sim.config import load_settings
from tools.synthetic_clouds.model.drift import project_drift_views

_API_VERSION = "2025-07-01"


def _client() -> TestClient:
    return TestClient(create_app(load_settings(env={}, SEED=123, PROFILE="small")))


def _parts(client: TestClient) -> tuple[str, str, str]:
    result = project_drift_views(client.app.state.estate).azure_what_if_results[0]
    segments = [segment for segment in result.id.split("/") if segment]
    return segments[1], segments[3], segments[-1]


def test_list_and_get_what_if_result() -> None:
    with _client() as client:
        subscription, resource_group, name = _parts(client)
        base = (
            f"/subscriptions/{subscription}/resourceGroups/{resource_group}"
            "/providers/Microsoft.Resources/deploymentStacksWhatIfResults"
        )

        listed = client.get(f"{base}?api-version={_API_VERSION}")
        assert listed.status_code == 200
        assert listed.json()["value"]

        fetched = client.get(f"{base}/{name}?api-version={_API_VERSION}")
        assert fetched.status_code == 200
        body = fetched.json()
        assert body["type"] == "Microsoft.Resources/deploymentStacksWhatIfResults"
        changes = body["properties"]["changes"]["resourceChanges"]
        assert any(change["changeType"] == "modify" for change in changes)
        assert any(change["changeType"] == "detach" for change in changes)
        modify = next(change for change in changes if change["changeType"] == "modify")
        assert modify["resourceConfigurationChanges"]["delta"][0]["path"].startswith("tags.")


def test_unknown_result_is_a_404_envelope() -> None:
    with _client() as client:
        subscription, resource_group, _ = _parts(client)
        response = client.get(
            f"/subscriptions/{subscription}/resourceGroups/{resource_group}"
            "/providers/Microsoft.Resources/deploymentStacksWhatIfResults/does-not-exist"
            f"?api-version={_API_VERSION}"
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NotFound"


def test_api_version_is_required() -> None:
    with _client() as client:
        subscription, resource_group, name = _parts(client)
        response = client.get(
            f"/subscriptions/{subscription}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.Resources/deploymentStacksWhatIfResults/{name}"
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "InvalidApiVersion"
