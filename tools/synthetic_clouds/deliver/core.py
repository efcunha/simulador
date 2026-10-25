"""Deliver one simulated day to the cloud emulators (FR-22, daily cadence).

The daily generator writes ``out/daily/<day>/...`` and, until this module, that
was the end of the road: the emulators that stand in for AWS/GCP/Azure (the ones
the CloudPilot ingestion actually reads through its production connectors) never
saw the day. This module closes that gap with the same delivery shape each real
cloud uses:

* **AWS** -- the FOCUS 1.2 export is uploaded to the S3 store under
  ``{prefix}/{export_name}/data/billing_period=YYYY-MM/<execution>/...``, which is
  the key layout the BCM Data Export reader lists. Upload order is chronological,
  so the newest execution of the period carries the newest ``LastModified``.
* **GCP** -- the day's BigQuery detailed-export rows are streamed into the
  ``all_billing_data`` tables with ``tabledata.insertAll``: the same API a real
  billing export populates. Only the target day's rows are sent (the export is
  append-only), so re-running a day does not grow the table with duplicates.
* **Azure** -- Cost Management is served from the simulator's generated estate.
  Delivery means extending that estate's window to the day; the estate is
  deterministic on ``(seed, profile, currency, day)``, so the refreshed data is
  the same data the daily render produced.

The transport is stdlib ``urllib`` on purpose: the delivery runs inside the
scheduled task's interpreter and must not add a runtime dependency to the
package. Every call is a plain HTTP request against the emulator endpoint.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

#: Canonical first day of the simulated estate (the generator's epoch).
EPOCH = date(2026, 1, 1)

#: Rows per ``insertAll`` request: the same 500 the GCP provisioner uses.
_BULK_BATCH = 500

#: Resource table the CloudPilot GCP connector reads, and the standard export.
_RESOURCE_TABLE = "gcp_billing_export_resource_v1_ba_gcp_1"
_STANDARD_TABLE = "gcp_billing_export_v1_ba_gcp_1"


@dataclass(slots=True)
class DeliveryResult:
    """What one delivery run did, per target."""

    day: str
    aws_objects: int = 0
    gcp_rows: int = 0
    azure_days: int | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict[str, Any]:
        return {
            "day": self.day,
            "aws_objects": self.aws_objects,
            "gcp_rows": self.gcp_rows,
            "azure_days": self.azure_days,
            "errors": list(self.errors),
            "ok": self.ok,
        }


def _request(url: str, *, method: str, data: bytes | None = None, timeout: float = 60.0) -> bytes:
    """Send one HTTP request and return the body; raise on a non-2xx answer."""
    request = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - operator-configured emulator URL
            return response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:400]
        raise RuntimeError(f"{method} {url} -> HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"{method} {url} -> {exc.reason}") from exc


def _run_render_dir(daily_root: Path, day: date) -> Path:
    """Return ``out/daily/<day>/<seed>-<profile>-<currency>/render`` for the day."""
    candidates = sorted((daily_root / day.isoformat()).glob("*/render"))
    if not candidates:
        raise FileNotFoundError(
            f"no render directory under {daily_root / day.isoformat()} (was the day generated?)"
        )
    return candidates[0]


def _source_export_dir(focus_root: Path) -> Path:
    """Return the renderer's own export folder under ``aws_focus/focus12-full``."""
    children = sorted(p for p in focus_root.iterdir() if p.is_dir())
    if not children:
        raise FileNotFoundError(f"no export directory under {focus_root}")
    return children[0]


def deliver_aws(
    day: date,
    *,
    daily_root: Path,
    endpoint: str,
    bucket: str,
    prefix: str,
    export_name: str,
) -> int:
    """Upload the day's FOCUS 1.2 export to the S3 store; return objects written."""
    focus_root = _run_render_dir(daily_root, day) / "aws_focus" / "focus12-full"
    source = _source_export_dir(focus_root)
    written = 0
    for path in sorted(source.rglob("*"), key=lambda item: item.as_posix()):
        if not path.is_file():
            continue
        relative = path.relative_to(source).as_posix()
        # Rewrite the export_name segment: a real S3 delivery is keyed by the
        # name the reader was configured with, not by the renderer's folder.
        key = f"{prefix}/{export_name}/{relative}"
        url = f"{endpoint.rstrip('/')}/{bucket}/{key}"
        _request(url, method="PUT", data=path.read_bytes())
        written += 1
    return written


def _iter_day_rows(path: Path, day: str) -> Iterator[dict[str, Any]]:
    """Yield the rows of a topology JSON payload whose usage day is ``day``."""
    with path.open(encoding="utf-8") as handle:
        rows = json.load(handle)
    for row in rows:
        if not isinstance(row, dict):
            continue
        stamp = str(row.get("usage_start_time") or row.get("charge_period_start") or "")
        if stamp[:10] == day:
            yield row


def _insert_rows(
    endpoint: str, project: str, dataset: str, table: str, rows: Iterable[dict[str, Any]]
) -> int:
    """Stream ``rows`` into one BigQuery table with ``tabledata.insertAll``."""
    url = (
        f"{endpoint.rstrip('/')}/bigquery/v2/projects/{project}"
        f"/datasets/{dataset}/tables/{table}/insertAll"
    )
    written = 0
    batch: list[dict[str, Any]] = []
    for row in rows:
        batch.append({"json": row})
        if len(batch) >= _BULK_BATCH:
            _request(url, method="POST", data=json.dumps({"rows": batch}).encode("utf-8"))
            written += len(batch)
            batch = []
    if batch:
        _request(url, method="POST", data=json.dumps({"rows": batch}).encode("utf-8"))
        written += len(batch)
    return written


def _delete_day(endpoint: str, project: str, dataset: str, table: str, day: str) -> None:
    """Remove ``day``'s rows from one table before re-inserting them.

    ``insertAll`` is append-only: re-running a day (``tick --force``) would
    otherwise stack a second copy of the same rows in the export. The emulator
    accepts the DML ``DELETE`` (verified), so delivery is idempotent per day.
    """
    url = f"{endpoint.rstrip('/')}/bigquery/v2/projects/{project}/queries"
    sql = (
        f"DELETE FROM `{project}.{dataset}.{table}` "
        f"WHERE DATE(usage_start_time) = '{day}'"
    )
    _request(url, method="POST", data=json.dumps({"query": sql, "useLegacySql": False}).encode("utf-8"))


def deliver_gcp(
    day: date,
    *,
    daily_root: Path,
    endpoint: str,
    project: str,
    dataset: str,
) -> int:
    """Insert the day's billing-export rows into BigQuery; return rows written."""
    topology = _run_render_dir(daily_root, day) / "gcp_bigquery_topology"
    day_text = day.isoformat()
    written = 0
    for filename, table in (
        ("09_rows_resource.json", _RESOURCE_TABLE),
        ("08_rows_standard.json", _STANDARD_TABLE),
    ):
        path = topology / filename
        if path.exists():
            _delete_day(endpoint, project, dataset, table, day_text)
            written += _insert_rows(endpoint, project, dataset, table, _iter_day_rows(path, day_text))
    return written


def deliver_azure(day: date, *, endpoint: str) -> int:
    """Extend the azure-sim estate window through ``day`` (never below today).

    The Cost Management reader windows on the **UTC** day
    (``billing_window``: ``[today-1, today+1)``), so an estate that stops at
    the generated day (D-1) answers ``no_rows`` when the UTC clock has already
    rolled over. A real cloud has current-day cost data; the window therefore
    covers at least the UTC today, not only the delivered day.
    """
    today = datetime.now(UTC).date()
    through = max(day, today)
    window_days = (through - EPOCH).days + 1
    url = f"{endpoint.rstrip('/')}/admin/estate/refresh?days={window_days}"
    _request(url, method="POST", data=b"{}", timeout=300.0)
    return window_days


def deliver_day(
    day: date,
    *,
    daily_root: Path,
    targets: Iterable[str] = ("aws", "gcp", "azure"),
    aws_endpoint: str = "http://localhost:9090",
    aws_bucket: str = "cloudpilot-focus12-daily-full",
    aws_prefix: str = "focus12-full",
    aws_export_name: str = "cloudpilot-focus12-daily-full",
    gcp_endpoint: str = "http://localhost:9050",
    gcp_project: str = "synthetic",
    gcp_dataset: str = "all_billing_data",
    azure_endpoint: str = "http://localhost:8080",
) -> DeliveryResult:
    """Deliver ``day`` to every requested target; never raises for one target."""
    result = DeliveryResult(day=day.isoformat())
    for target in targets:
        try:
            if target == "aws":
                result.aws_objects = deliver_aws(
                    day,
                    daily_root=daily_root,
                    endpoint=aws_endpoint,
                    bucket=aws_bucket,
                    prefix=aws_prefix,
                    export_name=aws_export_name,
                )
            elif target == "gcp":
                result.gcp_rows = deliver_gcp(
                    day,
                    daily_root=daily_root,
                    endpoint=gcp_endpoint,
                    project=gcp_project,
                    dataset=gcp_dataset,
                )
            elif target == "azure":
                result.azure_days = deliver_azure(day, endpoint=azure_endpoint)
            else:
                result.errors.append(f"unknown target {target!r}")
        except Exception as exc:  # noqa: BLE001 - one target must not stop the others
            result.errors.append(f"{target}: {type(exc).__name__}: {exc}")
    return result


__all__ = [
    "EPOCH",
    "DeliveryResult",
    "deliver_aws",
    "deliver_azure",
    "deliver_day",
    "deliver_gcp",
]
