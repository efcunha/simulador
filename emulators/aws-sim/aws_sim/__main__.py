"""Entry point: ``python -m aws_sim serve`` (FR-15 order matters).

The refusal guard runs **before** the settings load and before uvicorn binds a port, so
a machine holding real AWS credentials fails with exit code 2 and no listening socket —
the ordering is the safety property, not the check on its own.
"""

from __future__ import annotations

import argparse
import sys

from aws_sim.config import ConfigError, load_settings
from aws_sim.guard import REFUSAL_EXIT_CODE, SafetyRefusalError, assert_no_real_credentials

_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 8086


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m aws_sim")
    sub = parser.add_subparsers(dest="command")
    serve = sub.add_parser("serve", help="run the CloudFormation control-plane shim")
    serve.add_argument("--host", default=_DEFAULT_HOST)
    serve.add_argument("--port", type=int, default=_DEFAULT_PORT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run the requested command; return a process exit code."""
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    if args.command != "serve":
        print("usage: python -m aws_sim serve [--host H] [--port P]", file=sys.stderr)
        return 2

    try:
        # FIRST: refuse real credential material, before any settings or socket.
        assert_no_real_credentials()
        settings = load_settings()
    except SafetyRefusalError as exc:
        print(str(exc), file=sys.stderr)
        return REFUSAL_EXIT_CODE
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 1

    import uvicorn  # noqa: PLC0415 - imported after the guard on purpose

    from aws_sim.api.app import create_app  # noqa: PLC0415

    uvicorn.run(create_app(settings), host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
