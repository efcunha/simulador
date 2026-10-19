"""The uploader: key layout preserved, upload ordered by key.

The ordering is not a cosmetic detail. The S3 reader pins the newest execution per billing
period by ``LastModified`` with a directory-path tie-break, and S3 sets ``LastModified``
from upload time — the client cannot write it. So **upload order is the only mechanism**
that decides which execution the reader sees, and these tests pin it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from aws_sim import upload


def _tree(tmp_path: Path) -> Path:
    """A two-execution, one-period tree in the BCM layout the renderer emits."""
    root = tmp_path / "aws_focus"
    daily = root / "focus12-full" / "synthetic-focus12-daily-full"
    for execution, body in (("20260318T000000Z-aaaa", b"older"), ("20260319T000000Z-aaaa", b"newer")):
        part = daily / "data" / "billing_period=2026-03" / execution
        part.mkdir(parents=True)
        (part / "synthetic-focus12-daily-full-00001.snappy.parquet").write_bytes(body)
    manifest = daily / "metadata" / "billing_period=2026-03" / "20260319T000000Z-aaaa"
    manifest.mkdir(parents=True)
    (manifest / "synthetic-focus12-daily-full-Manifest.json").write_text("{}", encoding="utf-8")
    return root


class _RecordingS3:
    """Records the keys it is asked to upload, in order."""

    def __init__(self) -> None:
        self.keys: list[str] = []
        self.created: list[str] = []
        self.headed: list[str] = []

    def head_bucket(self, Bucket: str) -> dict:  # noqa: N803 - botocore keyword casing
        self.headed.append(Bucket)
        return {}

    def put_object(self, Bucket: str, Key: str, Body: bytes) -> dict:  # noqa: N803
        assert Body, f"{Key} uploaded empty"
        self.keys.append(Key)
        return {}


def test_upload_order_is_sorted_by_key(tmp_path: Path) -> None:
    """Sorted key order is chronological order, which is what the reader pins on."""
    keys = upload.upload_order(_tree(tmp_path))
    assert keys == sorted(keys)
    # The manifest must sort after the data of its own execution? No — it sorts by path, and
    # ``data/`` < ``metadata/``. What matters is that the newest EXECUTION is last among the
    # billing-period keys, which is what the reader compares.
    period_keys = [key for key in keys if "billing_period=2026-03" in key]
    assert period_keys[-1].startswith("focus12-full/synthetic-focus12-daily-full/metadata/")
    data_keys = [key for key in keys if "/data/" in key]
    assert data_keys[-1].startswith("focus12-full/synthetic-focus12-daily-full/data/billing_period=2026-03/20260319T")


def test_upload_tree_preserves_the_layout_verbatim(tmp_path: Path) -> None:
    """No key is rewritten: a remapped key lands where the reader does not look."""
    s3 = _RecordingS3()
    count = upload.upload_tree(
        _tree(tmp_path),
        bucket="synthetic-focus12-daily-full",
        endpoint="http://minio:9000",
        access_key="k",
        secret_key="s",
        client=s3,
    )
    assert count == 3  # noqa: PLR2004 - two data parts + one manifest
    assert s3.created == []  # head_bucket succeeded, so no create_bucket call
    assert s3.keys == sorted(s3.keys)
    for key in s3.keys:
        assert key.startswith("focus12-full/synthetic-focus12-daily-full/")
    assert any(key.endswith(".snappy.parquet") for key in s3.keys)
    assert any(key.endswith("-Manifest.json") for key in s3.keys)


def test_ensure_bucket_creates_when_absent() -> None:
    class Missing:
        def __init__(self) -> None:
            self.created: list[str] = []

        def head_bucket(self, Bucket: str) -> dict:  # noqa: N803
            raise RuntimeError("404")

        def create_bucket(self, Bucket: str) -> dict:  # noqa: N803
            self.created.append(Bucket)
            return {}

    client = Missing()
    upload.ensure_bucket(client, "new-bucket")
    assert client.created == ["new-bucket"]


def test_unknown_tree_is_an_error_not_a_silent_no_op(tmp_path: Path) -> None:
    """An empty upload would look like a successful run and deliver nothing."""
    with pytest.raises(NotADirectoryError):
        upload.upload_tree(
            tmp_path / "absent",
            bucket="b",
            endpoint="",
            access_key="",
            secret_key="",
            client=_RecordingS3(),
        )
