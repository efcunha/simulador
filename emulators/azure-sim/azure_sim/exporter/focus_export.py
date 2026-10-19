"""FOCUS export: Phase 1 renderer bytes UNCHANGED, laid out + partitioned (§4.1, §4.5).

Binding fidelity rule (non-negotiable, §4.1): the FOCUS export files MUST be the
byte output of the Phase 1 ``AzureFocusRenderer``. Phase 2 only:
  (a) optionally gzips the CSV to ``*.csv.gz`` (matching the parser's suffix
      detection in ``parse_cur_bytes``),
  (b) splits into parts under the official layout, and
  (c) records byte counts for the manifest.

No re-encoding, no re-quantizing money, no re-encoding ``Tags``, and NO invented
``x_*`` columns (§4.5 / TODO-verificar §11.4 — default: none).

Partitioning preserves fidelity because each part is produced by passing the
corresponding ``line_id``-sorted slice of billing lines through the UNCHANGED
renderer (via ``dataclasses.replace`` on the frozen estate, swapping only
``billing_lines``). The renderer's own fixed ``line_id`` sort makes a slice
byte-reproducible, and the real parser's ``aggregate_cost_rows`` merges parts so
totals are conserved (proven by the fidelity test).

Determinism note: the CSV gzip wrapper is written with ``mtime=0`` so the gzip
header carries no wall-clock timestamp — a re-run of the same slice is
byte-identical (§4.3 determinism contract).
"""

from __future__ import annotations

import dataclasses
import gzip

from tools.synthetic_clouds.model.billing import BillingLine
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.render.focus_azure import (
    _COLUMNS,
    render_csv_bytes,
    render_parquet_bytes,
)

from azure_sim.exporter.partition import PartRef, part_file_name, row_slices

# The FOCUS column list is exactly the Phase 1 renderer's column tuple — never a
# Phase 2 reinvention. Exposed for the manifest column list (§4.2).
FOCUS_COLUMNS: tuple[str, ...] = _COLUMNS

# FOCUS export dataset version used in the manifest fingerprint (§4.2).
# TODO-verificar §11.5: doc-supported FOCUS export version.
FOCUS_DATASET_VERSION = "1.2"

_CSV_SUFFIX = ".csv.gz"
_PARQUET_SUFFIX = ".parquet"
_FILE_STEM = "focus"


@dataclasses.dataclass(slots=True, frozen=True)
class LaidOutPart:
    """One FOCUS part: its blob file name and raw bytes (ready for the writer)."""

    file_name: str
    data: bytes


def _sorted_lines(estate: CanonicalEstate) -> list[BillingLine]:
    """Return billing lines in the renderer's canonical ``line_id`` order."""
    return sorted(estate.billing_lines, key=lambda line: line.line_id)


def _estate_with_lines(estate: CanonicalEstate, lines: list[BillingLine]) -> CanonicalEstate:
    """Return a copy of ``estate`` with ``billing_lines`` replaced by ``lines``.

    Only the billing-line projection input changes; every other field is shared,
    so the renderer sees the same estate shape it always does.
    """
    return dataclasses.replace(estate, billing_lines=tuple(lines))


def _gzip_stable(raw: bytes) -> bytes:
    """Gzip ``raw`` with a zeroed mtime so the output is byte-reproducible."""
    return gzip.compress(raw, mtime=0)


def _render_slice(estate: CanonicalEstate, lines: list[BillingLine], export_format: str) -> bytes:
    """Render one slice through the UNCHANGED Phase 1 renderer, then wrap only."""
    sub_estate = _estate_with_lines(estate, lines)
    if export_format == "parquet":
        return render_parquet_bytes(sub_estate)
    # csv: gzip-wrap the renderer bytes exactly (no re-encode).
    return _gzip_stable(render_csv_bytes(sub_estate))


def lay_out_focus_parts(
    estate: CanonicalEstate, *, export_format: str, max_rows_per_part: int
) -> list[LaidOutPart]:
    """Lay out the FOCUS export for one format into ordered parts.

    ``export_format`` is ``csv`` (gzip -> ``*.csv.gz``) or ``parquet``. An estate
    with zero billing lines yields ``[]`` (empty-slice rule, §4.4/§4.7).
    """
    suffix = _PARQUET_SUFFIX if export_format == "parquet" else _CSV_SUFFIX
    sorted_lines = _sorted_lines(estate)
    slices = row_slices(len(sorted_lines), max_rows_per_part)
    parts: list[LaidOutPart] = []
    for index, (start, end) in enumerate(slices, start=1):
        data = _render_slice(estate, sorted_lines[start:end], export_format)
        parts.append(LaidOutPart(file_name=part_file_name(_FILE_STEM, suffix, index), data=data))
    return parts


def part_refs(parts: list[LaidOutPart], *, max_rows_per_part: int, total_rows: int) -> list[PartRef]:
    """Build manifest ``PartRef`` entries (byte counts + row spans) for the parts."""
    slices = row_slices(total_rows, max_rows_per_part)
    return [
        PartRef(
            file_name=part.file_name,
            byte_count=len(part.data),
            row_start=start,
            row_end=end,
        )
        for part, (start, end) in zip(parts, slices, strict=True)
    ]
