"""Per-run ``manifest.json`` builder (design §4.2, §9).

One manifest per run carries, at minimum: export name/type/format, the
billing/charge period window, the column list, the list of blob parts with byte
counts, a ``runId``, ``synthetic: true``, and a deterministic ``schemaFingerprint``.

The fingerprint uses the Phase 1 ``markers.source_fingerprint(logical)`` with the
logical key pinned by the design (§4.2):

    logical = f"{export_type}:{agreement}:{focus_version}:{seed}:{profile}:{currency}"
    schemaFingerprint = source_fingerprint(logical)   # e.g. "synth:focus:mca:1.2:42:small:USD"

For Actual/Amortized exports ``focus_version`` is replaced by the dataset tag for
that export type. The derivation input is PINNED here; it never reads a clock.

TODO-verificar §11.2: the full official manifest field names/nesting (``runInfo``,
``blobs[]``, ``schema``, dataset version strings) and the exact field name that
holds the fingerprint and the manifest ``export_time`` are NOT offline-verifiable.
This builder emits an official-SHAPED superset and flags the unverified keys
inline; it never fabricates an unverified value as confirmed.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from tools.synthetic_clouds.render.markers import source_fingerprint

from azure_sim.exporter.layout import PeriodWindow
from azure_sim.exporter.partition import PartRef

# Dataset tag used in the fingerprint logical key per export type (§4.2). FOCUS
# uses the FOCUS spec version; Actual/Amortized use their dataset name.
# TODO-verificar §11.5: the doc-supported FOCUS export version string.
FOCUS_VERSION = "1.2"


def build_schema_fingerprint(
    *,
    export_type: str,
    agreement: str,
    dataset_version: str,
    seed: int,
    profile: str,
    currency: str,
) -> str:
    """Return the deterministic ``synth:``-prefixed schema fingerprint (§4.2)."""
    logical = f"{export_type}:{agreement}:{dataset_version}:{seed}:{profile}:{currency}"
    return source_fingerprint(logical)


def build_manifest(
    *,
    export_name: str,
    export_type: str,
    export_format: str,
    agreement: str,
    period: PeriodWindow,
    columns: Sequence[str],
    parts: Sequence[PartRef],
    run_id: str,
    export_time: datetime,
    dataset_version: str,
    seed: int,
    profile: str,
    currency: str,
) -> dict[str, Any]:
    """Return the manifest dict for one run.

    ``export_format`` is the single format this manifest describes (``csv`` or
    ``parquet``); one manifest is written per (export_type, format) run.
    ``parts`` may be empty (empty-slice rule) -> ``blobs: []``.
    """
    fingerprint = build_schema_fingerprint(
        export_type=export_type,
        agreement=agreement,
        dataset_version=dataset_version,
        seed=seed,
        profile=profile,
        currency=currency,
    )
    return {
        # Core, confirmed-shape fields.
        "runId": run_id,
        "exportName": export_name,
        "exportType": export_type,  # focus | actual | amortized
        "format": export_format,  # csv | parquet
        "agreement": agreement,  # mca | ea
        "billingPeriodStart": period.start.isoformat(),
        "billingPeriodEnd": period.end.isoformat(),
        # TODO-verificar §11.2: exact field name holding the manifest export time.
        "exportTime": export_time.isoformat(),
        "schema": {
            "columns": list(columns),
            # TODO-verificar §11.5: doc-supported dataset/FOCUS version string.
            "datasetVersion": dataset_version,
        },
        # TODO-verificar §11.2: official key is likely ``blobs``/``runInfo`` with a
        # different nesting; emitted as an official-shaped superset.
        "blobs": [
            {"blobName": part.file_name, "byteCount": part.byte_count}
            for part in parts
        ],
        # Synthetic provenance (design §9): never a real artifact.
        "synthetic": True,
        "schemaFingerprint": fingerprint,
    }
