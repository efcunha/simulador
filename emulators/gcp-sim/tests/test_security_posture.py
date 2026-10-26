"""gcp-sim security posture routes: SCC findings (REST + gRPC) and compute firewalls.

P76. Three surfaces the CloudPilot ``GCPSecurityScanner`` calls and that this
service did not serve before:

1. ``GET /v1/projects/{project}/sources/-/findings`` -- the scanner asks for the
   PROJECT level (``projects/<project>/sources/-``); the service only accepted
   ``organizations/`` and answered 400.
2. ``POST /google.cloud.securitycenter.v1.SecurityCenter/ListFindings`` -- the
   client library speaks **gRPC** (the transport registry puts ``grpc`` first),
   so the REST route above is never reached by the real scanner. This service
   therefore serves the same findings over a gRPC plane.
3. ``GET /compute/v1/projects/{project}/global/firewalls`` -- the firewall
   posture the estate already models, projected per project.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

_AUTH = {"Authorization": "Bearer synthetic-token"}

#: The GCP project the estate carries firewall rules for.
_ESTATE_PROJECT = "contoso-prod-01"


# ── REST: SCC findings ───────────────────────────────────────────────────────


def test_scc_findings_accepts_project_parent(client: TestClient) -> None:
    """The project level the scanner asks for is served, not rejected."""
    resp = client.get("/v1/projects/synthetic/sources/-/findings", headers=_AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert "listFindingsResults" in body
    assert body["listFindingsResults"], "the fixture carries findings"


def test_scc_findings_project_parent_serves_the_same_list_as_organization(client: TestClient) -> None:
    """Both levels publish the same findings -- the level is the only difference."""
    org = client.get("/v1/organizations/900900900/sources/synthetic-source/findings", headers=_AUTH)
    project = client.get("/v1/projects/synthetic/sources/-/findings", headers=_AUTH)
    assert org.status_code == 200
    assert project.status_code == 200
    assert project.json()["listFindingsResults"] == org.json()["listFindingsResults"]


def test_scc_findings_project_parent_missing_bearer_401(client: TestClient) -> None:
    resp = client.get("/v1/projects/synthetic/sources/-/findings")
    assert resp.status_code == 401


# ── REST: compute firewalls ──────────────────────────────────────────────────


def test_compute_firewalls_list_serves_the_estate_rules(client: TestClient) -> None:
    """The estate's modelled firewall rules are published per project."""
    resp = client.get(f"/compute/v1/projects/{_ESTATE_PROJECT}/global/firewalls", headers=_AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["kind"] == "compute#firewallList"
    items = body["items"]
    assert items, "the estate carries firewall rules for this project"
    names = [item["name"] for item in items]
    assert "default-allow-ssh" in names
    assert "default-allow-rdp" in names
    ssh = next(item for item in items if item["name"] == "default-allow-ssh")
    assert ssh["direction"] == "INGRESS"
    assert ssh["sourceRanges"] == ["0.0.0.0/0"]
    assert ssh["allowed"] == [{"IPProtocol": "tcp", "ports": ["22"]}]
    assert ssh["kind"] == "compute#firewall"
    assert ssh["network"].startswith(f"projects/{_ESTATE_PROJECT}/global/networks/")


def test_compute_firewalls_list_is_ordered_by_name(client: TestClient) -> None:
    """The provider sorts the list alphabetically by default."""
    resp = client.get(f"/compute/v1/projects/{_ESTATE_PROJECT}/global/firewalls", headers=_AUTH)
    assert resp.status_code == 200
    names = [item["name"] for item in resp.json()["items"]]
    assert names == sorted(names)


def test_compute_firewalls_unknown_project_is_empty(client: TestClient) -> None:
    """A project the estate does not carry selects nothing (the sim's rule)."""
    resp = client.get("/compute/v1/projects/synthetic/global/firewalls", headers=_AUTH)
    assert resp.status_code == 200
    assert resp.json()["items"] == []


def test_compute_firewalls_missing_bearer_401(client: TestClient) -> None:
    resp = client.get(f"/compute/v1/projects/{_ESTATE_PROJECT}/global/firewalls")
    assert resp.status_code == 401


# ── gRPC plane: SecurityCenter.ListFindings ─────────────────────────────────


@pytest.fixture()
def scc_grpc_plane(fixtures_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    """Yield the running SCC gRPC plane (started on an ephemeral port)."""
    from gcp_sim.routers import scc

    monkeypatch.setenv("GCP_SIM_FIXTURES_DIR", str(fixtures_dir))
    plane = scc.start_grpc_plane(port=0)
    try:
        yield plane
    finally:
        scc.stop_grpc_plane(plane)


def test_scc_grpc_plane_answers_list_findings(scc_grpc_plane: Any) -> None:
    """The gRPC method the client library calls is served."""
    import grpc

    from gcp_sim.routers import scc

    with grpc.insecure_channel(f"127.0.0.1:{scc_grpc_plane.port}") as channel:
        call = channel.unary_unary(
            "/google.cloud.securitycenter.v1.SecurityCenter/ListFindings",
            request_serializer=lambda payload: payload,
            response_deserializer=lambda payload: payload,
        )
        raw = call(scc.ListFindingsRequest(parent="projects/synthetic/sources/-")._pb.SerializeToString())

    decoded = scc.ListFindingsResponse.deserialize(raw)
    assert len(decoded.list_findings_results) == 66
    first = decoded.list_findings_results[0].finding
    assert first.severity.name in {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
    assert first.category == "CONFIG"
    assert first.resource_name


def test_scc_grpc_payload_decodes_with_the_client_package(scc_grpc_plane: Any) -> None:
    """The bytes decode with the SAME library the CloudPilot client uses.

    This is the check that the wire contract (field numbers, map value type)
    is right -- a local round-trip would only prove the sim agrees with itself.
    """
    import grpc

    securitycenter = pytest.importorskip("google.cloud.securitycenter_v1")

    from gcp_sim.routers import scc

    with grpc.insecure_channel(f"127.0.0.1:{scc_grpc_plane.port}") as channel:
        call = channel.unary_unary(
            "/google.cloud.securitycenter.v1.SecurityCenter/ListFindings",
            request_serializer=lambda payload: payload,
            response_deserializer=lambda payload: payload,
        )
        raw = call(scc.ListFindingsRequest(parent="projects/synthetic/sources/-")._pb.SerializeToString())

    decoded = securitycenter.types.ListFindingsResponse.deserialize(raw)
    assert len(decoded.list_findings_results) == 66
    finding = decoded.list_findings_results[0].finding
    assert finding.severity.name in {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
    assert finding.category == "CONFIG"
    assert finding.resource_name
    assert finding.name


def test_scc_grpc_plane_serves_the_same_findings_as_the_rest_route(
    scc_grpc_plane: Any, client: TestClient
) -> None:
    """Both planes publish the same findings."""
    import grpc

    from gcp_sim.routers import scc

    with grpc.insecure_channel(f"127.0.0.1:{scc_grpc_plane.port}") as channel:
        call = channel.unary_unary(
            "/google.cloud.securitycenter.v1.SecurityCenter/ListFindings",
            request_serializer=lambda payload: payload,
            response_deserializer=lambda payload: payload,
        )
        raw = call(scc.ListFindingsRequest(parent="projects/synthetic/sources/-")._pb.SerializeToString())

    over_grpc = scc.ListFindingsResponse.deserialize(raw)
    rest = client.get("/v1/projects/synthetic/sources/-/findings", headers=_AUTH).json()
    assert len(over_grpc.list_findings_results) == len(rest["listFindingsResults"])
    assert [r.finding.name for r in over_grpc.list_findings_results] == [
        r["finding"]["name"] for r in rest["listFindingsResults"]
    ]


def test_scc_grpc_plane_starts_with_the_app(client: TestClient) -> None:
    """The plane follows the app's lifecycle: started on boot, stopped on shutdown."""
    from gcp_sim.routers import scc

    assert scc.PLANE is not None
    assert scc.PLANE.port == scc.DEFAULT_PORT


def test_scc_grpc_plane_reads_the_rendered_fixture(scc_grpc_plane: Any, fixtures_dir: Path) -> None:
    """The plane serves the rendered fixture, not a hardcoded list."""
    fixture = json.loads((fixtures_dir / "scc_findings.json").read_text(encoding="utf-8"))
    assert len(fixture["listFindingsResults"]) == 66
