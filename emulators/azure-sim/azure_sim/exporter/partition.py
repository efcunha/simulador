"""Part naming + row-slicing for export partitioning (design §4.4).

A large export file is split into parts named ``part_<file>_<NNNN>`` and the
parser ingests parts independently; ``aggregate_cost_rows`` merges them, so
partitioning never changes aggregate totals (asserted by the fidelity test).

This module owns ONLY the pure concerns that do not touch FOCUS encoding:
  * computing the ordered row-index slices for a given ``max_rows_per_part``, and
  * naming each part and recording its byte count.

It deliberately does NOT render or re-encode bytes. The caller
(``focus_export.py``) produces each part's bytes by passing the corresponding
row slice through the UNCHANGED Phase 1 renderer, preserving the binding
fidelity rule (§4.1). Byte stability therefore follows from the renderer's fixed
``line_id`` sort: the same slice always renders to the same bytes.

Empty input yields ``parts: []`` (§4.4 / §4.7 empty-slice rule).
"""

from __future__ import annotations

from dataclasses import dataclass

_PART_INDEX_WIDTH = 4


@dataclass(slots=True, frozen=True)
class PartRef:
    """One laid-out part: its blob file name, byte count, and row span."""

    file_name: str
    byte_count: int
    row_start: int  # inclusive index into the sorted row list
    row_end: int  # exclusive index into the sorted row list


def part_file_name(file_stem: str, suffix: str, index: int) -> str:
    """Return ``part_<file_stem>_<NNNN><suffix>`` (1-based, zero-padded index).

    ``suffix`` includes the leading dot(s), e.g. ``.csv.gz`` or ``.parquet``.
    """
    return f"part_{file_stem}_{index:0{_PART_INDEX_WIDTH}d}{suffix}"


def row_slices(total_rows: int, max_rows_per_part: int) -> list[tuple[int, int]]:
    """Return ordered ``(start, end)`` half-open index slices.

    ``total_rows == 0`` yields ``[]`` (empty-slice rule). ``max_rows_per_part``
    is guaranteed ``>= 1`` by ``config.py`` validation; this function is defensive
    anyway and treats values ``< 1`` as a single slice.
    """
    if total_rows <= 0:
        return []
    step = max_rows_per_part if max_rows_per_part >= 1 else total_rows
    return [(start, min(start + step, total_rows)) for start in range(0, total_rows, step)]
