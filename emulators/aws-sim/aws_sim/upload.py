"""Upload a rendered FOCUS tree to S3/MinIO, preserving the BCM key layout.

**Ordering is the load-bearing part, not the upload.** The S3 reader pins the newest
execution per billing period by ``LastModified`` with a directory-path tie-break
(``s3_reader.py:154-168``), and S3 sets ``LastModified`` from upload time — the client
cannot write it. So the guarantee comes from *upload order*: objects go up in sorted
relative-path order, and because the renderer makes execution ids deterministic and
sortable on purpose (design sec. 19.4), lexicographic order is chronological order. The
last execution of a period therefore finishes uploading last and carries the newest
``LastModified``, which is exactly what the reader pins.

Nothing here rewrites a key. The rendered layout
``{prefix}/{export_name}/data/billing_period=YYYY-MM/<execution>/…`` is uploaded verbatim,
because any remapping would put the emulator's output somewhere the real reader does not
look.

Uses **botocore** rather than boto3: one S3 client is needed, not the resource layer, and
botocore is already a runtime dependency for the service model.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

import botocore.session
from botocore.config import Config

#: Recognised data suffixes, mirroring ``s3_reader``. The manifest and ``metadata/``
#: objects are uploaded too — they are a fidelity requirement even though the reader
#: skips them (A0.3), and skipping them here would make the delivered tree not look like
#: an AWS export.
_SKIP_SUFFIXES: tuple[str, ...] = ()


def s3_client(*, endpoint: str, access_key: str, secret_key: str, region: str = "us-east-1") -> Any:
    """Build an S3 client pointed at ``endpoint`` with path-style addressing.

    Path-style is not a preference: MinIO serves buckets as path segments, and virtual-host
    style would resolve ``bucket.minio`` — a name that does not exist inside the compose
    network.
    """
    session = botocore.session.get_session()
    return session.create_client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
        config=Config(s3={"addressing_style": "path"}, signature_version="s3v4"),
    )


def _objects(root: Path) -> list[tuple[str, Path]]:
    """Return ``(key, path)`` pairs sorted by key.

    The sort is the ordering mechanism described in the module docstring, so it is not a
    cosmetic detail: it is what makes the pinned execution correct.
    """
    pairs: list[tuple[str, Path]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix in _SKIP_SUFFIXES:
            continue
        pairs.append((path.relative_to(root).as_posix(), path))
    return sorted(pairs, key=lambda pair: pair[0])


def ensure_bucket(client: Any, bucket: str) -> None:
    """Create ``bucket`` when absent; a present bucket is not an error."""
    try:
        client.head_bucket(Bucket=bucket)
        return
    except Exception:  # noqa: BLE001 - any "cannot head" means "try to create"
        client.create_bucket(Bucket=bucket)


def upload_tree(
    root: Path,
    *,
    bucket: str,
    endpoint: str,
    access_key: str,
    secret_key: str,
    region: str = "us-east-1",
    client: Any | None = None,
) -> int:
    """Upload every object under ``root`` to ``bucket``; return the object count.

    ``client`` is injectable so a test can assert the key set and the upload order without
    a live MinIO.
    """
    if not root.is_dir():
        raise NotADirectoryError(f"rendered tree not found: {root}")

    s3 = client if client is not None else s3_client(
        endpoint=endpoint,
        access_key=access_key,
        secret_key=secret_key,
        region=region,
    )
    ensure_bucket(s3, bucket)

    count = 0
    for key, path in _objects(root):
        s3.put_object(Bucket=bucket, Key=key, Body=path.read_bytes())
        count += 1
    return count


def upload_order(root: Path) -> list[str]:
    """The key order :func:`upload_tree` uses. Exposed so a test can pin it."""
    return [key for key, _path in _objects(root)]


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m aws_sim.upload")
    parser.add_argument("--dir", type=Path, required=True, help="rendered tree to upload")
    parser.add_argument("--bucket", default=os.environ.get("AWS_SIM_BUCKET", ""))
    parser.add_argument("--endpoint", default=os.environ.get("S3_ENDPOINT", ""))
    parser.add_argument("--access-key", default=os.environ.get("S3_ACCESS_KEY", ""))
    parser.add_argument("--secret-key", default=os.environ.get("S3_SECRET_KEY", ""))
    parser.add_argument("--region", default=os.environ.get("AWS_SIM_REGION", "us-east-1"))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Upload a rendered tree; return a process exit code.

    Every setting falls back to the environment so the compose service can run this with no
    arguments, and so credentials never appear on a command line (where they would show up
    in ``podman inspect`` and shell history).
    """
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    missing = [
        name
        for name, value in (
            ("--bucket/AWS_SIM_BUCKET", args.bucket),
            ("--endpoint/S3_ENDPOINT", args.endpoint),
            ("--access-key/S3_ACCESS_KEY", args.access_key),
            ("--secret-key/S3_SECRET_KEY", args.secret_key),
        )
        if not value
    ]
    if missing:
        print(f"error: missing settings: {', '.join(missing)}", file=sys.stderr)
        return 1

    try:
        count = upload_tree(
            args.dir,
            bucket=args.bucket,
            endpoint=args.endpoint,
            access_key=args.access_key,
            secret_key=args.secret_key,
            region=args.region,
        )
    except Exception as exc:  # noqa: BLE001 - surfaced as an exit code, never swallowed
        print(f"error: upload failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(f"ok: uploaded {count} object(s) from {args.dir} to {args.bucket}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
