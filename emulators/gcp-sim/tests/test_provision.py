"""Provisioner tests (design sec. 11): manifest parsing + statement batching with a
MOCKED httpx transport (no live emulator); row-count mismatch -> non-zero result.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from gcp_sim import provision as prov


def test_split_statements_strips_comments() -> None:
    sql = "CREATE TABLE a (x INT64);  -- comment\nINSERT INTO a VALUES (1);\n-- trailing\n"
    stmts = prov.split_statements(sql)
    assert stmts == ["CREATE TABLE a (x INT64)", "INSERT INTO a VALUES (1)"]


def _render_topology(tmp_path: Path) -> Path:
    import sys

    repo_root = Path(__file__).resolve().parents[4]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from tools.synthetic_clouds.generate.estate_builder import build_estate
    from tools.synthetic_clouds.render.gcp_bigquery_topology import GcpBigQueryTopologyRenderer
    from tools.synthetic_clouds.scenarios.emit import apply_all

    estate = apply_all(build_estate(seed=123, profile="small", currency="USD"))
    GcpBigQueryTopologyRenderer().render(estate, tmp_path)
    return tmp_path / "gcp_bigquery_topology" / "manifest.json"


class _Recorder:
    """Records submitted statements, streamed rows, and answers COUNT(*) from the manifest."""

    def __init__(self, counts: dict[str, int]) -> None:
        self.statements: list[str] = []
        self.streamed: dict[str, int] = {}
        self._counts = counts

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/datasets"):
            return httpx.Response(200, json={"datasets": []})
        if path.endswith("/insertAll"):
            table = path.split("/tables/")[1].split("/")[0]
            payload = json.loads(request.content.decode())
            self.streamed[table] = self.streamed.get(table, 0) + len(payload["rows"])
            return httpx.Response(200, json={})
        body = json.loads(request.content.decode())
        stmt = body["query"]
        self.statements.append(stmt)
        if stmt.upper().startswith("SELECT COUNT(*)"):
            table = stmt.split("`")[1]  # backtick-quoted fqtn in the FROM clause
            n = self._counts.get(table, 0)
            return httpx.Response(200, json={"rows": [{"f": [{"v": str(n)}]}]})
        return httpx.Response(200, json={})


def _run_provision(monkeypatch: pytest.MonkeyPatch, recorder: _Recorder, manifest_path: Path, project: str) -> int:
    transport = httpx.MockTransport(recorder.handler)
    real_client = httpx.Client  # capture before patching to avoid self-recursion

    def _fake_client(**_kwargs: object) -> httpx.Client:
        return real_client(transport=transport)

    monkeypatch.setattr(prov.httpx, "Client", _fake_client)
    return prov.provision(manifest_path, "http://emu:9050", project)


def test_provision_submits_scripts_in_order_and_verifies(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest_path = _render_topology(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    counts = {spec["table"]: spec["expected_rows"] for spec in manifest["tables"].values()}
    recorder = _Recorder(counts)
    rc = _run_provision(monkeypatch, recorder, manifest_path, manifest["project"])
    assert rc == 0
    create_idx = [i for i, s in enumerate(recorder.statements) if s.startswith("CREATE")]
    insert_idx = [i for i, s in enumerate(recorder.statements) if s.startswith("INSERT")]
    if insert_idx:
        assert max(create_idx) < min(insert_idx)


def test_provision_row_count_mismatch_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest_path = _render_topology(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    recorder = _Recorder({})  # wrong counts -> COUNT(*) 0 -> mismatch on a non-empty table
    with pytest.raises(prov.ProvisionError):
        _run_provision(monkeypatch, recorder, manifest_path, manifest["project"])


def test_create_dataset_tolerates_emulator_already_created() -> None:
    """The emulator answers 500 -- not 409 -- for an existing dataset."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": {"message": "dataset all_billing_data is already created"}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        prov.create_dataset(client, "http://emu:9050", "synthetic", "all_billing_data")


def test_create_dataset_raises_on_a_real_failure() -> None:
    """A 500 that is NOT an already-exists answer must still fail loudly."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": {"message": "backend unavailable"}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client, pytest.raises(prov.ProvisionError):
        prov.create_dataset(client, "http://emu:9050", "synthetic", "all_billing_data")


def test_reset_tables_refuses_to_drop(tmp_path: Path) -> None:
    """Dropping tables corrupts the goccy emulator's catalog; the guard must refuse.

    Measured: after a DROP TABLE the emulator answers every later statement (even
    ``SELECT 1``) with a googlesqlite slice-bounds panic, so a re-provision must
    recreate the emulator instead.
    """
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={}))) as client:
        with pytest.raises(prov.ProvisionError, match="unsafe"):
            prov.reset_tables(client, "http://emu:9050", "synthetic", ["synthetic.ds.t"])


def test_provision_creates_tables_before_inserting(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The DDL must precede the INSERT scripts (statement order in the manifest)."""
    manifest_path = _render_topology(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    counts = {spec["table"]: spec["expected_rows"] for spec in manifest["tables"].values()}
    recorder = _Recorder(counts)
    assert _run_provision(monkeypatch, recorder, manifest_path, manifest["project"]) == 0
    create_idx = [i for i, s in enumerate(recorder.statements) if s.startswith("CREATE TABLE")]
    insert_idx = [i for i, s in enumerate(recorder.statements) if s.startswith("INSERT")]
    assert create_idx and insert_idx
    assert max(create_idx) < min(insert_idx)
    assert not [s for s in recorder.statements if s.startswith("DROP")]


def test_provision_streams_bulk_rows_instead_of_insert_scripts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The row tables arrive over insertAll, never as the unparseable INSERT scripts.

    The emulator's parser panics above ~166 KB per statement and after ~54k rows in one
    table, so the provisioner must stream the manifest's bulk payloads and skip the two
    INSERT scripts that carry the same rows.
    """
    manifest_path = _render_topology(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    counts = {spec["table"]: spec["expected_rows"] for spec in manifest["tables"].values()}
    recorder = _Recorder(counts)
    assert _run_provision(monkeypatch, recorder, manifest_path, manifest["project"]) == 0

    assert manifest["bulk_rows"], "the manifest must declare its bulk payloads"
    for key, _filename in manifest["bulk_rows"].items():
        spec = manifest["tables"][key]
        table = spec["table"].split(".")[-1]
        assert recorder.streamed.get(table) == spec["expected_rows"], f"{key} not fully streamed"
        assert not [s for s in recorder.statements if s.startswith(f"INSERT INTO `{spec['table']}`")], (
            f"{key} was submitted as a query job instead of streamed"
        )
