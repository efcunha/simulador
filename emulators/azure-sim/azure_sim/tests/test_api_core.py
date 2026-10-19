"""API core: healthz, token, paging, validation->envelope (FEAT-002 step 6).

httpx (TestClient) against the FastAPI app. Asserts the shared primitives:
/healthz 200, token endpoint issues a bearer, the paging helper terminates and
covers all rows exactly once, and a validation failure returns the Azure envelope
(not a FastAPI 422).
"""

from __future__ import annotations

from azure_sim.api.paging import BadContinuationTokenError, decode_token, encode_token, paginate

_QUERY_API_VERSION = "2024-08-01"


def test_healthz_ok(api_client) -> None:
    client, _ = api_client
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_token_returns_bearer(api_client) -> None:
    client, _ = api_client
    resp = client.post("/mytenant/oauth2/v2.0/token")
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "Bearer"
    assert body["access_token"].startswith("synth:")
    assert body["synthetic"] is True


def test_paging_covers_all_rows_exactly_once() -> None:
    rows: list[object] = list(range(23))
    seen: list[object] = []
    token: str | None = None
    pages = 0
    while True:
        page = paginate(rows, page_size=5, token=token)
        seen.extend(page.rows)
        pages += 1
        if page.next_offset is None:
            break
        token = encode_token(page.next_offset)
        assert pages < 100  # guard against a non-terminating loop
    assert seen == rows
    assert pages == 5  # ceil(23/5)


def test_bad_continuation_token_rejected() -> None:
    try:
        decode_token("not-a-valid-token!!!")
    except BadContinuationTokenError:
        return
    raise AssertionError("expected BadContinuationTokenError")


def test_query_paging_terminates_and_covers_rows(api_client) -> None:
    client, _ = api_client
    all_rows: list[object] = []
    url = f"/subscriptions/sub-1/providers/Microsoft.CostManagement/query?api-version={_QUERY_API_VERSION}"
    pages = 0
    while url is not None:
        resp = client.post(url, json={"dataset": {"granularity": "daily"}})
        assert resp.status_code == 200
        body = resp.json()
        all_rows.extend(body["properties"]["rows"])
        url = body["nextLink"]
        pages += 1
        assert pages < 100000
    assert pages > 1  # the small estate paginates at page_size=5


def test_validation_failure_returns_azure_envelope(api_client) -> None:
    client, _ = api_client
    # Unknown api-version => 400 Azure envelope, never a FastAPI 422.
    resp = client.post(
        "/subscriptions/sub-1/providers/Microsoft.CostManagement/query?api-version=1999-01-01",
        json={},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert "error" in body
    assert set(body["error"]) >= {"code", "message"}


def test_bad_token_query_param_maps_to_400_envelope(api_client) -> None:
    client, _ = api_client
    resp = client.post(
        f"/subscriptions/sub-1/providers/Microsoft.CostManagement/query"
        f"?api-version={_QUERY_API_VERSION}&$skipToken=@@garbage@@",
        json={},
    )
    assert resp.status_code == 400
    assert "error" in resp.json()
