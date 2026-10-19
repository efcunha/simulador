"""gcp-sim router tests (design sec. 11): 200 shapes, 400/401, GCP error envelopes."""

from __future__ import annotations

from fastapi.testclient import TestClient

_AUTH = {"Authorization": "Bearer synthetic-token"}


def test_healthz_ok(client: TestClient) -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_oauth_token_returns_bearer(client: TestClient) -> None:
    resp = client.post("/token")
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "Bearer"
    assert body["access_token"]


def test_cai_search_all_resources_ok(client: TestClient) -> None:
    resp = client.post("/v1/projects/contoso-prod-01:searchAllResources", headers=_AUTH, json={})
    assert resp.status_code == 200
    assert "results" in resp.json()


def test_cai_missing_bearer_401(client: TestClient) -> None:
    resp = client.post("/v1/projects/contoso-prod-01:searchAllResources", json={})
    assert resp.status_code == 401
    assert resp.json()["error"]["status"] == "UNAUTHENTICATED"


def test_cai_bad_scope_400(client: TestClient) -> None:
    resp = client.post("/v1/garbage-scope:searchAllResources", headers=_AUTH, json={})
    assert resp.status_code == 400
    assert resp.json()["error"]["status"] == "INVALID_ARGUMENT"


def test_scc_sources_ok(client: TestClient) -> None:
    resp = client.get("/v1/organizations/900900900/sources", headers=_AUTH)
    assert resp.status_code == 200
    assert "sources" in resp.json()


def test_scc_findings_ok(client: TestClient) -> None:
    resp = client.get("/v1/organizations/900900900/sources/synthetic-source/findings", headers=_AUTH)
    assert resp.status_code == 200
    assert "listFindingsResults" in resp.json()


def test_scc_findings_missing_bearer_401(client: TestClient) -> None:
    resp = client.get("/v1/organizations/900900900/sources/synthetic-source/findings")
    assert resp.status_code == 401


def test_recommender_recommendations_ok(client: TestClient) -> None:
    resp = client.get(
        "/v1/projects/contoso-prod-01/locations/global/recommenders/google.synthetic/recommendations",
        headers=_AUTH,
    )
    assert resp.status_code == 200
    assert "recommendations" in resp.json()


def test_recommender_insights_ok(client: TestClient) -> None:
    resp = client.get(
        "/v1/projects/contoso-prod-01/locations/global/insightTypes/google.synthetic/insights",
        headers=_AUTH,
    )
    assert resp.status_code == 200
    assert "insights" in resp.json()


def test_catalog_services_ok(client: TestClient) -> None:
    resp = client.get("/v1/services", headers=_AUTH)
    assert resp.status_code == 200
    assert "services" in resp.json()


def test_catalog_skus_ok(client: TestClient) -> None:
    resp = client.get("/v1/services/COMPUTE-ENGINE/skus", headers=_AUTH)
    assert resp.status_code == 200
    assert "skus" in resp.json()


def test_monitoring_timeseries_ok(client: TestClient) -> None:
    resp = client.get("/v3/projects/contoso-prod-01/timeSeries", headers=_AUTH)
    assert resp.status_code == 200
    assert "timeSeries" in resp.json()


def test_monitoring_bad_name_400(client: TestClient) -> None:
    resp = client.get("/v3/garbage/timeSeries", headers=_AUTH)
    assert resp.status_code == 400


def test_budgets_ok(client: TestClient) -> None:
    resp = client.get("/v1/billingAccounts/ba-gcp-1/budgets", headers=_AUTH)
    assert resp.status_code == 200
    assert "budgets" in resp.json()


def test_error_envelope_shape(client: TestClient) -> None:
    """Every error is the GCP envelope, never a bare FastAPI 422."""
    resp = client.post("/v1/projects/contoso-prod-01:searchAllResources", json={})
    body = resp.json()
    assert set(body["error"]) >= {"code", "message", "status"}
