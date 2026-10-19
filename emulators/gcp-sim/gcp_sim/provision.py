"""DDL/INSERT provisioner over the bigquery-emulator REST endpoint (design sec. 6).

Reads ``manifest.json`` + the ordered SQL scripts, waits for emulator health
(``datasets.list`` 200), submits each DDL/INSERT statement as a BigQuery query job
to the emulator REST endpoint via ``httpx``, polls completion, asserts the
``manifest.json`` row counts, and exits 0 on success / non-zero (logging the
failing statement + emulator error) on failure.

HARD CONSTRAINTS (design sec. 2, sec. 6):
  * NO ``--data-from-yaml`` -- tables are created via ``CREATE TABLE ...
    ARRAY<STRUCT<...>>`` + ``INSERT`` only (the spike's proven path).
  * NO Windows drive bind-mount -- scripts arrive via a named volume or podman cp.

M1 note: GCP INSERT rows only ever carry Usage/Purchase/Adjustment cost_types plus
the estate.taxes-derived tax rows; the renderer already guards illegal
charge_category, so this provisioner trusts its input scripts.

Statement splitting: scripts are split on ``;`` at end-of-line; ``--`` line
comments are stripped before submission (the emulator's query endpoint accepts a
single statement per job).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx

_DEFAULT_TIMEOUT = 30.0
_HEALTH_RETRIES = 40
_HEALTH_INTERVAL = 1.5
# Rows per tabledata.insertAll request. The streaming API has no SQL parse step, so this
# is a request-size choice rather than a parser limit; 500 keeps one request ~700 KB.
_BULK_BATCH = 500


class ProvisionError(RuntimeError):
    """Raised on a fatal provisioning failure (surfaces as non-zero exit)."""


def _strip_comments(sql: str) -> str:
    """Remove ``--`` line comments while preserving statement text."""
    out_lines: list[str] = []
    for line in sql.splitlines():
        idx = line.find("--")
        out_lines.append(line[:idx] if idx >= 0 else line)
    return "\n".join(out_lines)


def split_statements(sql: str) -> list[str]:
    """Split a SQL script into individual statements on ``;`` (comments stripped)."""
    cleaned = _strip_comments(sql)
    parts = [stmt.strip() for stmt in cleaned.split(";")]
    return [stmt for stmt in parts if stmt]


def wait_for_health(client: httpx.Client, endpoint: str, project: str) -> None:
    """Poll ``datasets.list`` until it returns 200 or retries are exhausted."""
    url = f"{endpoint}/bigquery/v2/projects/{project}/datasets"
    last_err = ""
    for _ in range(_HEALTH_RETRIES):
        try:
            resp = client.get(url, params={"maxResults": 1})
            if resp.status_code == 200:
                return
            last_err = f"{resp.status_code}: {resp.text[:200]}"
        except httpx.HTTPError as exc:  # noqa: PERF203 - retry loop
            last_err = str(exc)
        time.sleep(_HEALTH_INTERVAL)
    raise ProvisionError(f"emulator not healthy after {_HEALTH_RETRIES} tries: {last_err}")


def run_query(client: httpx.Client, endpoint: str, project: str, statement: str) -> dict[str, Any]:
    """Submit a single statement as a synchronous BigQuery query job (jobs.query).

    The emulator's ``jobs.query`` REST route runs DDL and INSERT as the spike's
    proven DDL path. If a specific emulator build rejects ``jobs.query`` for DDL,
    this is the single place to switch to ``jobs.insert`` (TODO-verificar sec. 13).
    """
    url = f"{endpoint}/bigquery/v2/projects/{project}/queries"
    payload = {"query": statement, "useLegacySql": False}
    resp = client.post(url, json=payload)
    if resp.status_code != 200:
        raise ProvisionError(f"statement failed [{resp.status_code}]: {resp.text[:500]}\n--SQL--\n{statement[:500]}")
    body: dict[str, Any] = resp.json()
    return body


def _count_rows(client: httpx.Client, endpoint: str, project: str, table_fqtn: str) -> int:
    """Return COUNT(*) for a fully-qualified ``project.dataset.table``."""
    # S608: table_fqtn is a synthetic, renderer-emitted identifier (not user input)
    # and this hits only the dev-local emulator; no live database.
    result = run_query(client, endpoint, project, f"SELECT COUNT(*) AS n FROM `{table_fqtn}`")  # noqa: S608
    rows = result.get("rows", [])
    if not rows:
        return 0
    return int(rows[0]["f"][0]["v"])


# Body substrings the goccy emulator uses when a dataset already exists; matched
# because it answers 500 -- not 409 -- for that case (see create_dataset).
_ALREADY_EXISTS_MARKERS = ("already created", "already exists")


def _insert_all_url(endpoint: str, project: str, table_fqtn: str) -> str:
    """Return the streaming-insert URL for a ``project.dataset.table`` fqtn."""
    dataset, table = table_fqtn.split(".")[-2:]
    return f"{endpoint}/bigquery/v2/projects/{project}/datasets/{dataset}/tables/{table}/insertAll"


def insert_rows(
    client: httpx.Client,
    endpoint: str,
    project: str,
    table_fqtn: str,
    rows: list[dict[str, Any]],
    *,
    batch_size: int = _BULK_BATCH,
) -> int:
    """Stream ``rows`` into ``table_fqtn`` via tabledata.insertAll; return rows sent.

    The renderer's SQL INSERT scripts cannot be used at production scale: the emulator's
    parser panics (``googlesqlite: slice bounds out of range``) above ~166 KB in one
    statement and, cumulatively, after roughly 54k rows in a single table -- measured on
    the v0.3.1 image with a 282-day estate. The streaming API never parses SQL: 4 x 500
    rows carrying nested STRUCT and ARRAY fields returned 200 and ``COUNT(*)`` matched
    exactly. A 200 carrying ``insertErrors`` still means rows were rejected, so that is
    treated as a failure rather than counted as progress.
    """
    url = _insert_all_url(endpoint, project, table_fqtn)
    sent = 0
    for start in range(0, len(rows), batch_size):
        chunk = rows[start : start + batch_size]
        payload = {
            "kind": "bigquery#tableDataInsertAllRequest",
            "rows": [{"insertId": str(start + i), "json": row} for i, row in enumerate(chunk)],
        }
        resp = client.post(url, json=payload)
        if resp.status_code != 200:
            raise ProvisionError(
                f"insertAll {table_fqtn} failed [{resp.status_code}] at row {start}: {resp.text[:300]}"
            )
        if "insertErrors" in resp.text:
            raise ProvisionError(
                f"insertAll {table_fqtn} reported insertErrors at row {start}: {resp.text[:300]}"
            )
        sent += len(chunk)
    return sent


def bulk_load(
    client: httpx.Client,
    endpoint: str,
    project: str,
    manifest: dict[str, Any],
    script_dir: Path,
) -> None:
    """Stream every table the manifest declares a bulk payload for (see insert_rows)."""
    for key, filename in manifest.get("bulk_rows", {}).items():
        spec = manifest["tables"][key]
        rows = json.loads((script_dir / filename).read_text(encoding="utf-8"))
        if not rows:
            print(f"ok: {filename} (0 rows)")
            continue
        sent = insert_rows(client, endpoint, project, spec["table"], rows)
        print(f"ok: {filename} ({sent} rows streamed into {spec['table']})")


def create_dataset(client: httpx.Client, endpoint: str, project: str, dataset: str) -> None:
    """Create a dataset via the REST datasets.insert API (idempotent).

    The goccy emulator does NOT persist ``CREATE SCHEMA`` submitted as a query job,
    so datasets are created via ``datasets.insert`` -- the Podman-safe REST path the
    design mandates (sec. 6). A 409 (already exists) is treated as success.

    The emulator does not always answer 409 for an existing dataset: against a live
    emulator it returns **500** with ``"dataset <name> is already created"``. Accepting
    only 409 made a second provision run fail on the very first dataset, which broke
    every re-provision (the recurring cadence in particular). The already-exists body
    is matched instead of the status alone, so a genuine 500 still raises.
    """
    url = f"{endpoint}/bigquery/v2/projects/{project}/datasets"
    payload = {"datasetReference": {"datasetId": dataset, "projectId": project}}
    resp = client.post(url, json=payload)
    if resp.status_code in (200, 409):
        return
    body = resp.text.lower()
    if resp.status_code in (400, 500) and any(marker in body for marker in _ALREADY_EXISTS_MARKERS):
        return
    raise ProvisionError(f"datasets.insert {dataset} failed [{resp.status_code}]: {resp.text[:300]}")


def reset_tables(client: httpx.Client, endpoint: str, project: str, tables: list[str]) -> None:
    """Refuse to run: dropping tables corrupts the goccy emulator's catalog.

    Measured, not assumed: a ``DROP TABLE`` against the live emulator leaves every
    later statement failing with ``panic runtime error: slice bounds out of range
    [-2137152816:]`` / ``failed to get projects`` -- including ``SELECT 1``. The
    emulator cannot be re-provisioned in place; the reset is to **recreate the
    emulator container** (``scripts/synthetic-clouds/gcp-up.ps1``) and provision into
    a fresh, empty one. Kept as an executable guard so nobody re-introduces the drop.
    """
    raise ProvisionError(
        "reset_tables is unsafe against the goccy emulator (DROP corrupts its catalog); "
        "recreate the emulator container instead"
    )


def provision(manifest_path: Path, endpoint: str, project: str, *, verify_counts: bool = True) -> int:
    """Run the full provisioning sequence; return a process exit code."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    script_dir = manifest_path.parent
    with httpx.Client(timeout=_DEFAULT_TIMEOUT) as client:
        wait_for_health(client, endpoint, project)
        # Datasets first, via REST insert (CREATE SCHEMA job is not persisted by the
        # emulator). 01_datasets.sql remains the human-readable record of intent.
        for dataset in (manifest["user_dataset"], manifest["focus_dataset"]):
            create_dataset(client, endpoint, project, dataset)
            print(f"ok: dataset {dataset}")
        # The emulator must be EMPTY at this point: gcp-up.ps1 recreates it first.
        # Provisioning a populated emulator in place is not supported (CREATE TABLE
        # collides with 400; DROP TABLE corrupts the catalog -- see reset_tables).
        # ``provision_scripts`` excludes the two INSERT scripts the manifest also
        # ships as a bulk payload: those rows arrive over insertAll instead (see
        # insert_rows). Falls back to the full list for a manifest without the key.
        for script_name in manifest.get("provision_scripts") or manifest["scripts"]:
            script_path = script_dir / script_name
            statements = split_statements(script_path.read_text(encoding="utf-8"))
            for statement in statements:
                run_query(client, endpoint, project, statement)
            print(f"ok: {script_name} ({len(statements)} statements)")
        bulk_load(client, endpoint, project, manifest, script_dir)
        if verify_counts:
            _verify_counts(client, endpoint, project, manifest)
    print("provisioning complete")
    return 0


def _verify_counts(client: httpx.Client, endpoint: str, project: str, manifest: dict[str, Any]) -> None:
    """Assert each table's row count matches the manifest's expected count."""
    for key, spec in manifest["tables"].items():
        expected = int(spec["expected_rows"])
        actual = _count_rows(client, endpoint, project, spec["table"])
        if actual != expected:
            raise ProvisionError(f"row-count mismatch for {key} ({spec['table']}): expected {expected}, got {actual}")
        print(f"ok: {key} row count {actual} == {expected}")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m gcp_sim.provision")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--endpoint", default="http://bigquery-emulator:9050")
    parser.add_argument("--project", default="synthetic")
    parser.add_argument("--no-verify-counts", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for the provisioner."""
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    try:
        return provision(args.manifest, args.endpoint, args.project, verify_counts=not args.no_verify_counts)
    except ProvisionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
