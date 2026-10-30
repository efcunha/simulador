"""CLI: ``python -m tools.synthetic_clouds.deliver``.

Delivers one already-generated day to the emulators that the CloudPilot
ingestion reads through its production connectors. It never generates: the
day must exist under ``out/daily`` (run the daily CLI or the scheduler first).
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

from tools.synthetic_clouds.daily.emit import DEFAULT_OUT
from tools.synthetic_clouds.deliver.core import (
    DEFAULT_AWS_BUCKET,
    DEFAULT_AWS_EXPORT_NAME,
    deliver_day,
)

_PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def _parse_targets(raw: str) -> tuple[str, ...]:
    targets = tuple(item.strip().lower() for item in raw.split(",") if item.strip())
    valid = {"aws", "gcp", "azure"}
    unknown = sorted(set(targets) - valid)
    if unknown:
        raise ValueError(f"unknown target(s) {unknown}; valid: {sorted(valid)}")
    return targets


def _aws_settings() -> dict[str, str]:
    """Resolve the AWS target's endpoint, bucket, prefix and export segment.

    The environment may override the namespace; the fallback is the name the
    renderer emits, which is also the name the CloudPilot CUR reader is
    configured with. A delivery that publishes under any other name writes into
    a namespace no reader looks at -- silently.
    """
    return {
        "aws_endpoint": os.environ.get("DELIVERY_AWS_ENDPOINT", "http://localhost:9090"),
        "aws_bucket": os.environ.get("DELIVERY_AWS_BUCKET", DEFAULT_AWS_BUCKET),
        "aws_prefix": os.environ.get("DELIVERY_AWS_PREFIX", "focus12-full"),
        "aws_export_name": os.environ.get(
            "DELIVERY_AWS_EXPORT_NAME", DEFAULT_AWS_EXPORT_NAME
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.synthetic_clouds.deliver")
    parser.add_argument("--day", required=True, help="YYYY-MM-DD day to deliver")
    parser.add_argument(
        "--targets",
        default=os.environ.get("DELIVERY_TARGETS", "aws,gcp,azure"),
        help="comma-separated subset of aws,gcp,azure (default: all)",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="daily output root (default: the package's out/daily)",
    )
    args = parser.parse_args(argv)

    try:
        targets = _parse_targets(args.targets)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    try:
        day = date.fromisoformat(args.day)
    except ValueError:
        print(f"error: --day must be YYYY-MM-DD, got {args.day!r}", file=sys.stderr)
        return 2

    daily_root = Path(args.out) if args.out else DEFAULT_OUT
    result = deliver_day(
        day,
        daily_root=daily_root,
        targets=targets,
        **_aws_settings(),
        gcp_endpoint=os.environ.get("DELIVERY_GCP_ENDPOINT", "http://localhost:9050"),
        gcp_project=os.environ.get("DELIVERY_GCP_PROJECT", "synthetic"),
        gcp_dataset=os.environ.get("DELIVERY_GCP_DATASET", "all_billing_data"),
        azure_endpoint=os.environ.get("DELIVERY_AZURE_ENDPOINT", "http://localhost:8080"),
    )

    print(json_line(result))
    for error in result.errors:
        print(f"erro: {error}", file=sys.stderr)
    return 0 if result.ok else 1


def json_line(result: object) -> str:
    import json

    return json.dumps(result.as_dict(), sort_keys=True)  # type: ignore[attr-defined]


if __name__ == "__main__":
    raise SystemExit(main())
