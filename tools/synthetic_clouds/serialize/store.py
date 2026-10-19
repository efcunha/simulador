"""Deterministic on-disk serialization of the canonical estate (OA-1, NFR-1/6).

Writes partitioned Parquet per entity under
``<out>/<seed>-<profile>-<currency>/canonical/`` plus a ``meta.json`` sidecar.
Every reproducibility lever is pinned so the Parquet bytes are a pure function of
the sorted rows (design sec. 11): fixed column order, rows sorted by a natural key
before write, explicit pyarrow ``version``/``compression``, no write-time
timestamp, ``write_statistics=False``. Run metadata (seed/profile/currency/counts/
schema fingerprint/CPython version) lives ONLY in ``meta.json``, never in Parquet
key-value metadata, so the bytes carry no wall-clock value.

NO sorted-content fallback: callers compare bytes. Sorting happens at write time
by a stable natural key, not at compare time.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import platform
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from tools.synthetic_clouds.model.estate import CanonicalEstate

# Pinned pyarrow write options (design sec. 11). ``store_schema`` keeps the Arrow
# schema but no pandas/wall-clock metadata is attached.
_PARQUET_VERSION = "2.6"
_COMPRESSION = "snappy"

# Per-entity natural-key sort columns (stable, total order within an entity).
_SORT_KEYS: dict[str, tuple[str, ...]] = {
    "resources": ("uuid",),
    "consumption": ("resource_uuid", "usage_date", "export_time"),
    "billing_lines": ("line_id",),
    "invoices": ("invoice_id",),
    "inventory": ("resource_uuid",),
    "findings": ("finding_id",),
    "recommendations": ("recommendation_id",),
    "metrics": ("resource_uuid", "metric_name"),
    "iac_snapshots": ("snapshot_id",),
}


def _scalar(value: Any) -> Any:
    """Normalize a canonical value into a Parquet-safe, deterministic scalar."""
    if isinstance(value, Decimal):
        return str(value)  # exact 6-dp text; no float rounding
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, tuple):
        return json.dumps(list(value), sort_keys=True, default=str)
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True, default=str)
    return value


def _rows_for_resources(estate: CanonicalEstate) -> list[dict[str, Any]]:
    return [
        {
            "uuid": r.identity.uuid,
            "logical_path": r.identity.logical_path,
            "provider": r.identity.provider,
            "parent_scope_id": r.parent_scope_id,
            "service_name": r.service_name,
            "service_category": r.service_category,
            "resource_type": r.resource_type,
            "resource_name": r.resource_name,
            "region_id": r.region_id,
            "region_name": r.region_name,
            "tags": _scalar(r.tags),
            "sku_id": r.sku_id,
        }
        for r in estate.resources
    ]


def _rows_from_dataclasses(items: tuple[Any, ...]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in items:
        row: dict[str, Any] = {}
        for field in dataclasses.fields(item):
            row[field.name] = _scalar(getattr(item, field.name))
        rows.append(row)
    return rows


def _invoice_rows(estate: CanonicalEstate) -> list[dict[str, Any]]:
    return [
        {
            "invoice_id": inv.invoice_id,
            "billing_account_id": inv.billing_account_id,
            "billing_period_start": inv.billing_period_start.isoformat(),
            "billing_period_end": inv.billing_period_end.isoformat(),
            "invoice_issue_status": inv.invoice_issue_status,
            "total": str(inv.total),
            "currency": inv.currency,
            "is_c07_divergence": inv.is_c07_divergence,
            "lines": json.dumps(
                [{"billing_line_id": li.billing_line_id, "amount": str(li.amount)} for li in inv.lines],
                sort_keys=True,
            ),
        }
        for inv in estate.invoices
    ]


def _metric_rows(estate: CanonicalEstate) -> list[dict[str, Any]]:
    return [
        {
            "resource_uuid": s.resource_uuid,
            "metric_name": s.metric_name,
            "points": json.dumps([{"ts": p.ts.isoformat(), "value": p.value} for p in s.points], sort_keys=True),
        }
        for s in estate.metrics
    ]


def _iac_rows(estate: CanonicalEstate) -> list[dict[str, Any]]:
    return [
        {
            "snapshot_id": snap.snapshot_id,
            "scope_id": snap.scope_id,
            "captured_at": snap.captured_at.isoformat(),
            "metadata": json.dumps(snap.metadata, sort_keys=True, default=str),
            "resource_states": json.dumps(
                [{"resource_uuid": st.resource_uuid, "declared_config": st.declared_config} for st in snap.resource_states],
                sort_keys=True,
                default=str,
            ),
        }
        for snap in estate.iac_snapshots
    ]


def _entity_rows(estate: CanonicalEstate) -> dict[str, list[dict[str, Any]]]:
    return {
        "resources": _rows_for_resources(estate),
        "consumption": _rows_from_dataclasses(estate.consumption),
        "billing_lines": _rows_from_dataclasses(estate.billing_lines),
        "invoices": _invoice_rows(estate),
        "inventory": _rows_from_dataclasses(estate.inventory),
        "findings": _rows_from_dataclasses(estate.findings),
        "recommendations": _rows_from_dataclasses(estate.recommendations),
        "metrics": _metric_rows(estate),
        "iac_snapshots": _iac_rows(estate),
    }


def _sorted_rows(entity: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keys = _SORT_KEYS[entity]
    return sorted(rows, key=lambda row: tuple(str(row.get(k, "")) for k in keys))


def _write_parquet(rows: list[dict[str, Any]], path: Path) -> None:
    if rows:
        columns = list(rows[0].keys())
        table = pa.table({col: [row[col] for row in rows] for col in columns})
    else:
        table = pa.table({})
    pq.write_table(
        table,
        path,
        version=_PARQUET_VERSION,
        compression=_COMPRESSION,
        coerce_timestamps="us",
        allow_truncated_timestamps=False,
        write_statistics=False,
        store_schema=True,
    )


def _schema_fingerprint(entity_rows: dict[str, list[dict[str, Any]]]) -> str:
    shape = {entity: (len(rows), list(rows[0].keys()) if rows else []) for entity, rows in entity_rows.items()}
    blob = json.dumps(shape, sort_keys=True)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()


def run_dir_name(estate: CanonicalEstate) -> str:
    """Return the deterministic run directory name ``<seed>-<profile>-<currency>``."""
    return f"{estate.seed}-{estate.profile}-{estate.currency}"


def write(estate: CanonicalEstate, out_dir: Path) -> Path:
    """Serialize ``estate`` to ``out_dir/<run>/canonical/`` deterministically.

    Returns the ``canonical`` directory path. The byte content of each Parquet
    file is a pure function of ``(seed, profile, currency)`` for a fixed CPython
    version (recorded in meta.json).
    """
    run = out_dir / run_dir_name(estate)
    canonical = run / "canonical"
    canonical.mkdir(parents=True, exist_ok=True)

    entity_rows = _entity_rows(estate)
    counts: dict[str, int] = {}
    for entity, rows in entity_rows.items():
        sorted_rows = _sorted_rows(entity, rows)
        counts[entity] = len(sorted_rows)
        _write_parquet(sorted_rows, canonical / f"{entity}.parquet")

    meta = {
        "seed": estate.seed,
        "profile": estate.profile,
        "currency": estate.currency,
        "currency_conversion_rate": str(estate.currency_conversion_rate)
        if estate.currency_conversion_rate is not None
        else None,
        "sim_start": estate.sim_start.isoformat(),
        "sim_now": estate.sim_now.isoformat(),
        "counts": counts,
        "schema_fingerprint": _schema_fingerprint(entity_rows),
        "cpython_version": platform.python_version(),
        "scenario_ids": list(estate.scenario_ids),
    }
    (canonical / "meta.json").write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return canonical
