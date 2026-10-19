"""GCP nested BigQuery billing-export renderer (FR-G2, AC-13).

Projects ``BillingLine`` rows into the nested BigQuery billing-export shape and
emits BOTH (a) a JSON row dump and (b) a ``CREATE TABLE ... ARRAY<STRUCT<...>>`` +
``INSERT`` DDL script, because the spike proved the emulator only exposes
``UNNEST``-able arrays when tables are provisioned via DDL (DISCOVERY spike).

Nested shape (verified against the 5 real FinOps queries, DISCOVERY sec. 3):
  * ``service`` / ``sku`` / ``project`` / ``location`` / ``invoice`` -> STRUCT
  * ``credits`` / ``labels`` / ``project.labels`` / ``system_labels`` / ``tags`` /
    ``project.ancestors`` -> ``ARRAY<STRUCT<...>>``
  * ``usage_start_time`` / ``usage_end_time`` / ``export_time`` -> TIMESTAMP
  * ``cost`` -> FLOAT64; ``price.*`` / ``cost_at_effective_price_default`` /
    ``cost_at_list_consumption_model`` -> NUMERIC
  * ``invoice.month`` -> STRING ``YYYYMM``

The column set and the row shape are DERIVED from the spec, not hand-written:
``_fields()`` returns the tree read from
``specs/gcp/billing-export-standard.schema.json`` through ``fidelity.spec.load_spec``
(the normative reader) via ``render.gcp_bigquery_topology``, and ``_row`` only supplies
the values this probe actually projects — every other documented field is emitted as
absence. Before this, the module carried its own ``_DDL`` block that had already drifted
from the documentation (17 columns, untyped ``price``, no ``tags``).

Decimal->FLOAT64 (Finding F3, pinned for byte-determinism): quantize to 6-dp with
ROUND_HALF_EVEN, then ``float(...)``; the JSON dump uses ``json.dumps(sort_keys=
True)`` with CPython's stable ``float.__repr__``. The FLOAT64 column type stays per
FR-G2 (number, not string).

``TODO-verificar`` (DISCOVERY sec. 8, OA-5), never fabricated: the exact official field
SET is no longer an open question (it is read from the spec), but the enum literals and
semantics of ``cost_type``, ``adjustment_info``, ``invoice.month`` and the attribution of
``credits[].type``/``full_name`` remain, as does partitioning (``_PARTITIONTIME``, which
the standard spec records as UNVERIFIED).

No ``ServiceSubcategory`` / ``ChargeDescription`` FOCUS column exists here: this is the
NATIVE BigQuery export shape, not a FOCUS one, and it carries both facts inline instead
— ``service.description`` and ``sku.description``, which ``_row`` fills from the line's
own ``service_name`` / ``service_category``. So the AWS catalog table
(``generate/constants.py::FOCUS_SERVICE_DESCRIPTIONS``) has no GCP side to project, and
adding one here would invent a FOCUS column this export never emits.

The same holds for the two SKU-price columns ``focus_aws`` now populates
(``SkuPriceId`` / ``SkuPriceDetails``): this export has no column of either name. The
price facts it does carry are native ones — ``price`` (a ``STRUCT`` of
``effective_price`` / ``unit`` / …) and ``cost_at_list`` — which this renderer already
emits from the line's own costs. Deriving a FOCUS price identity here would add a
column the real BigQuery export does not have.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path
from typing import Any

from tools.synthetic_clouds.model.billing import BillingLine
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.render.gcp_bigquery_topology import (
    SpecField,
    build_row,
    ddl_columns,
    fields_for,
    insert_column_list,
    row_values,
)

_SIX = Decimal("0.000001")


def _fields() -> tuple[SpecField, ...]:
    """The table's columns, DERIVED from ``specs/gcp/billing-export-standard.schema.json``.

    This probe used to carry its own hand-written ``_DDL`` column block, which had already
    drifted from the documentation (no ``adjustment_info`` values, no ``tags``,
    ``cost_at_list``, ``price.list_price`` …). The column set now comes from the same
    spec-derived tree the Phase-3 topology renderer uses, so the two cannot disagree with
    each other or with the documentation.
    """
    return fields_for("standard")


def _ddl() -> str:
    """The ``CREATE TABLE`` DDL for the synthetic single-table probe (spec column set)."""
    return f"CREATE TABLE `synthetic.gcp_billing_export` (\n{ddl_columns(_fields())}\n);"


def _to_float(value: Decimal) -> float:
    """Quantize to 6-dp (banker's rounding) then cast to FLOAT64 (Finding F3)."""
    return float(value.quantize(_SIX, ROUND_HALF_EVEN))


def _month(line: BillingLine) -> str:
    return f"{line.billing_period_start.year:04d}{line.billing_period_start.month:02d}"


def _labels(line: BillingLine) -> list[dict[str, str]]:
    return [{"key": k, "value": v} for k, v in line.tags]


def _row(line: BillingLine, currency: str, conversion_rate: Decimal | None) -> dict[str, Any]:
    """Project one billing line into the standard-export row shape (all 71 spec fields).

    Só os caminhos que este probe realmente projeta aparecem no mapa; ``build_row``
    preenche o resto com ausência, de modo que a linha carregue exatamente os nomes
    documentados.
    """
    labels = _labels(line)
    values: dict[str, Any] = {
        "billing_account_id": line.billing_account_id,
        "service.id": line.service_name,
        "service.description": line.service_name,
        "sku.id": line.service_category,
        "sku.description": line.service_category,
        "usage_start_time": line.charge_period_start,
        "usage_end_time": line.charge_period_end,
        "project.id": line.sub_account_id,
        "project.name": line.sub_account_id,
        "project.labels": labels,
        "labels": labels,
        "location.location": line.region_id,
        "location.region": line.region_id,
        "cost": _to_float(line.billed_cost),
        "currency": currency,
        "currency_conversion_rate": _to_float(conversion_rate) if conversion_rate is not None else 1.0,
        "usage.amount": _to_float(line.pricing_quantity),
        "usage.unit": line.pricing_unit,
        "invoice.month": _month(line),
        "cost_type": "regular",  # TODO-verificar: official enum
        "export_time": line.export_time,
    }
    return build_row(_fields(), values)


def _gcp_lines(estate: CanonicalEstate) -> list[BillingLine]:
    """GCP-provider billing lines, sorted by line_id for determinism."""
    gcp = [line for line in estate.billing_lines if line.service_provider_name == "Google Cloud"]
    return sorted(gcp, key=lambda line: line.line_id)


def render_rows(estate: CanonicalEstate) -> list[dict[str, Any]]:
    """Return the standard-export rows for the GCP side of the estate."""
    return [_row(line, estate.currency, estate.currency_conversion_rate) for line in _gcp_lines(estate)]


def _json_default(value: object) -> str:
    """Serialise the row's datetimes as ISO strings (JSON has no timestamp type)."""
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"not JSON serialisable: {type(value).__name__}")


def render_json_bytes(estate: CanonicalEstate) -> bytes:
    """Return the byte-stable JSON row dump (sorted keys, stable float repr)."""
    rows = render_rows(estate)
    return (json.dumps(rows, sort_keys=True, ensure_ascii=False, default=_json_default) + "\n").encode("utf-8")


def render_ddl(estate: CanonicalEstate) -> str:
    """Return the CREATE TABLE DDL (spec columns) + a bounded sample INSERT script."""
    rows = render_rows(estate)
    fields = _fields()
    table_ref = "`synthetic.gcp_billing_export`"
    cols = insert_column_list(fields)
    lines = [_ddl(), ""]
    for row in rows[:5]:  # a bounded, representative sample INSERT (every spec column)
        # S608: emits a DDL *script file* (not an executed query) from the tool's own
        # synthetic, fictional values; no untrusted input, nothing hits a database.
        insert = f"INSERT INTO {table_ref} ({cols}) VALUES {row_values(row, fields)};"  # noqa: S608
        lines.append(insert)
    return "\n".join(lines) + "\n"


class GcpBigQueryRenderer:
    """Renders the canonical estate to nested GCP BigQuery rows + DDL."""

    name = "gcp_bigquery"

    def render(self, estate: CanonicalEstate, out_dir: Path) -> list[Path]:
        """Write ``rows.json`` and ``ddl.sql`` under ``out_dir/gcp_bigquery/``."""
        target = out_dir / "gcp_bigquery"
        target.mkdir(parents=True, exist_ok=True)
        rows_path = target / "rows.json"
        ddl_path = target / "ddl.sql"
        rows_path.write_bytes(render_json_bytes(estate))
        ddl_path.write_text(render_ddl(estate), encoding="utf-8")
        return [rows_path, ddl_path]
