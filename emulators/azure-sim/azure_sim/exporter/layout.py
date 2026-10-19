"""Official export folder-path builder (MCA default + EA) (design §4.2, §4.3).

Azure Cost Management Exports write a per-run folder tree into a blob container:

    <container>/<rootDirectory>/<exportName>/
      <YYYYMMDD>-<YYYYMMDD>/        # billing/charge period window
        <runId>/                     # one folder per run (deterministic, §4.3)
          manifest.json
          part_<file>_<NNNN>.csv.gz  (or .parquet)

TODO-verificar §11.1: exact segment casing/order for MCA and EA, the per-run vs
per-period nesting, and retention of prior runs are the KNOWN layout but are not
offline-verifiable. The EA branch is isolated in ``_export_root`` so the MCA
default stays untouched when the EA segments are later confirmed.

Determinism (§4.3): ``runId`` is a stable hash of
``(seed, profile, currency, schedule, period, run_index)`` — never the container
clock — so a re-run is byte-reproducible and Phase 4 tests are stable.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date

_WINDOW_FMT = "%Y%m%d"

# TODO-verificar §11.1: the EA directory layout differs from MCA. Until the exact
# EA root segment is confirmed, EA reuses the MCA shape with this marker prefix
# kept empty so the emitted path stays official-shaped and the single switch
# point for the later fix is obvious.
_EA_ROOT_PREFIX = ""


@dataclass(slots=True, frozen=True)
class PeriodWindow:
    """A billing/charge period window ``[start, end]`` (inclusive end day)."""

    start: date
    end: date

    def folder_segment(self) -> str:
        """Return the ``<YYYYMMDD>-<YYYYMMDD>`` window segment."""
        return f"{self.start.strftime(_WINDOW_FMT)}-{self.end.strftime(_WINDOW_FMT)}"


def compute_run_id(
    *,
    seed: int,
    profile: str,
    currency: str,
    schedule: str,
    period: PeriodWindow,
    run_index: int,
) -> str:
    """Return a deterministic ``runId`` (16 hex chars) — no wall-clock (§4.3).

    The same inputs always yield the same id, so daily re-runs of the same slice
    land in the same folder and Phase 4 ingestion is reproducible. ``run_index``
    distinguishes intentionally distinct runs over the same window.
    """
    logical = f"{seed}:{profile}:{currency}:{schedule}:{period.folder_segment()}:{run_index}"
    digest = hashlib.sha256(logical.encode("utf-8")).hexdigest()
    return digest[:16]


def _export_root(*, root_directory: str, export_name: str, agreement: str) -> str:
    """Return the container-relative export root for the given agreement.

    MCA (default) and EA share the ``<rootDirectory>/<exportName>`` shape here;
    the EA-specific root segment prefix is isolated so §11.1 verification only
    touches this branch. ``agreement`` is validated upstream by ``config.py``.
    """
    base = f"{root_directory}/{export_name}"
    if agreement == "ea" and _EA_ROOT_PREFIX:
        # TODO-verificar §11.1: prepend the confirmed EA root segment here.
        return f"{_EA_ROOT_PREFIX}/{base}"
    return base


def build_run_prefix(
    *,
    root_directory: str,
    export_name: str,
    agreement: str,
    period: PeriodWindow,
    run_id: str,
) -> str:
    """Return the full container-relative prefix for one run's blobs.

    Shape: ``<rootDirectory>/<exportName>/<YYYYMMDD>-<YYYYMMDD>/<runId>``.
    The container name is NOT included (the blob writer scopes to the container).
    """
    export_root = _export_root(
        root_directory=root_directory,
        export_name=export_name,
        agreement=agreement,
    )
    return f"{export_root}/{period.folder_segment()}/{run_id}"


def part_blob_name(run_prefix: str, part_file_name: str) -> str:
    """Return the container-relative blob name for a part under ``run_prefix``."""
    return f"{run_prefix}/{part_file_name}"


def manifest_blob_name(run_prefix: str) -> str:
    """Return the container-relative blob name for the run's ``manifest.json``."""
    return f"{run_prefix}/manifest.json"
