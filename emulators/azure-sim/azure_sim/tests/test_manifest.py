"""Manifest keys + deterministic fingerprint (FEAT-001 step 6 / plan item 2)."""

from __future__ import annotations

from datetime import date, datetime

from azure_sim.exporter.layout import PeriodWindow
from azure_sim.exporter.manifest import build_manifest, build_schema_fingerprint
from azure_sim.exporter.partition import PartRef

_WINDOW = PeriodWindow(start=date(2026, 2, 1), end=date(2026, 2, 28))
_COLUMNS = ("BilledCost", "BillingPeriodStart", "Tags")


def _manifest(parts: list[PartRef]) -> dict:
    return build_manifest(
        export_name="focus-cost",
        export_type="focus",
        export_format="csv",
        agreement="mca",
        period=_WINDOW,
        columns=_COLUMNS,
        parts=parts,
        run_id="runabc",
        export_time=datetime(2026, 3, 1, 4, 0, 0),
        dataset_version="1.2",
        seed=42,
        profile="small",
        currency="USD",
    )


def test_fingerprint_is_deterministic_and_prefixed() -> None:
    fp = build_schema_fingerprint(
        export_type="focus",
        agreement="mca",
        dataset_version="1.2",
        seed=42,
        profile="small",
        currency="USD",
    )
    assert fp == "synth:focus:mca:1.2:42:small:USD"


def _fp(
    *,
    export_type: str = "focus",
    agreement: str = "mca",
    dataset_version: str = "1.2",
    seed: int = 42,
    profile: str = "small",
    currency: str = "USD",
) -> str:
    return build_schema_fingerprint(
        export_type=export_type,
        agreement=agreement,
        dataset_version=dataset_version,
        seed=seed,
        profile=profile,
        currency=currency,
    )


def test_fingerprint_varies_with_inputs() -> None:
    assert _fp() != _fp(agreement="ea")
    assert _fp() != _fp(seed=1)


def test_manifest_has_core_keys() -> None:
    part = PartRef(file_name="part_focus_0001.csv.gz", byte_count=123, row_start=0, row_end=10)
    m = _manifest([part])
    for key in ("runId", "exportName", "exportType", "format", "agreement", "schema", "blobs"):
        assert key in m
    assert m["runId"] == "runabc"
    assert m["exportType"] == "focus"
    assert m["format"] == "csv"
    assert m["schema"]["columns"] == list(_COLUMNS)


def test_manifest_marks_synthetic_and_fingerprint() -> None:
    m = _manifest([])
    assert m["synthetic"] is True
    assert m["schemaFingerprint"] == "synth:focus:mca:1.2:42:small:USD"


def test_manifest_blobs_carry_byte_counts() -> None:
    parts = [
        PartRef(file_name="part_focus_0001.csv.gz", byte_count=100, row_start=0, row_end=5),
        PartRef(file_name="part_focus_0002.csv.gz", byte_count=200, row_start=5, row_end=10),
    ]
    m = _manifest(parts)
    assert m["blobs"] == [
        {"blobName": "part_focus_0001.csv.gz", "byteCount": 100},
        {"blobName": "part_focus_0002.csv.gz", "byteCount": 200},
    ]


def test_empty_slice_yields_empty_blobs() -> None:
    assert _manifest([])["blobs"] == []
