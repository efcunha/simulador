"""``python -m azure_sim`` dispatch: ``serve`` | ``export`` (design §4.6, §6.1).

``serve`` runs uvicorn against the ``api.app`` factory. ``export`` performs one
exporter run via ``exporter/runner.py`` using CLI flags that override env per §4.6.
Both pass through ``config.load_settings`` first, so bad input fails CLOSED with a
non-zero exit BEFORE any serve or blob write (§4.7).

Exit codes:
  * 0  — success.
  * 2  — bad CLI (unknown subcommand / argparse error).
  * 1  — config/validation failure (ConfigError) or export runtime failure.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from tools.synthetic_clouds.model.estate import CanonicalEstate

from azure_sim.config import ConfigError, Settings, load_settings

_PROG = "azure_sim"

# CLI flag -> ENV key the override maps to (uppercased), per §4.6.
_EXPORT_FLAGS: dict[str, str] = {
    "seed": "SEED",
    "profile": "PROFILE",
    "currency": "CURRENCY",
    "agreement": "AGREEMENT",
    "exports": "EXPORTS",
    "format": "FORMAT",
    "schedule": "SCHEDULE",
    "latency_hours": "LATENCY_HOURS",
    "max_rows_per_part": "MAX_ROWS_PER_PART",
    "blob_container": "BLOB_CONTAINER",
    "root_directory": "ROOT_DIRECTORY",
    "azure_blob_endpoint": "AZURE_BLOB_ENDPOINT",
}


def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the ``serve``/``export`` subcommands."""
    parser = argparse.ArgumentParser(prog=_PROG)
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve = subparsers.add_parser("serve", help="Run the control-plane HTTP API.")
    serve.add_argument("--host", default="0.0.0.0")  # noqa: S104 - sim binds all in-container
    serve.add_argument("--port", type=int, default=8080)
    # Optional TLS listener. CloudPilot reaches the simulator as the REAL cloud
    # hostnames (management.azure.com / login.microsoftonline.com) over 443; the
    # plain listener stays for the simulator's own tooling and health probe.
    serve.add_argument("--tls-port", type=int, default=None)
    serve.add_argument("--tls-cert", default=None)
    serve.add_argument("--tls-key", default=None)

    export = subparsers.add_parser("export", help="Run one Cost Management export into Azurite.")
    for flag in _EXPORT_FLAGS:
        export.add_argument(f"--{flag.replace('_', '-')}", dest=flag, default=None)
    return parser


def _overrides(args: argparse.Namespace) -> dict[str, str | None]:
    """Collect the export CLI overrides keyed by their ENV name (§4.6).

    A ``None`` value (unset flag) is passed through and ignored by
    ``load_settings`` so the env/default wins.
    """
    return {env_key: getattr(args, flag) for flag, env_key in _EXPORT_FLAGS.items()}


def _run_serve(args: argparse.Namespace) -> int:
    """Validate settings, then run uvicorn against the app factory (fail-closed)."""
    settings = load_settings()  # validates env; ConfigError => caller maps to exit 1
    import threading

    import uvicorn

    from azure_sim.api.app import create_app

    app = create_app(settings)

    if args.tls_port:
        if not args.tls_cert or not args.tls_key:
            raise ConfigError("--tls-port requires --tls-cert and --tls-key")
        # The TLS listener runs beside the plain one, in its own thread/loop.
        # uvicorn only installs signal handlers on the main thread, so the
        # process stays owned by the plain server below.
        threading.Thread(
            target=uvicorn.run,
            kwargs={
                "app": app,
                "host": args.host,
                "port": args.tls_port,
                "ssl_certfile": args.tls_cert,
                "ssl_keyfile": args.tls_key,
            },
            name="azure-sim-tls",
            daemon=True,
        ).start()

    uvicorn.run(app, host=args.host, port=args.port)
    return 0


def _run_export(args: argparse.Namespace) -> int:
    """Validate settings (CLI overriding env), then run one export (fail-closed)."""
    settings: Settings = load_settings(None, **_overrides(args))
    from azure_sim.exporter.blob_writer import AzuriteBlobWriter
    from azure_sim.exporter.runner import run_export

    writer = AzuriteBlobWriter(endpoint=settings.azure_blob_endpoint)
    prefixes = run_export(_estate_for(settings), settings, writer)
    print(f"wrote {len(prefixes)} run prefix(es)")  # noqa: T201 - CLI user feedback
    return 0


def _estate_for(settings: Settings) -> CanonicalEstate:
    """Build the gated estate for the export run (fail-closed via the gate)."""
    from azure_sim.estate import build_simulated_estate

    return build_simulated_estate(
        seed=settings.seed,
        profile=settings.profile,
        currency=settings.currency,
        window_days=settings.window_days,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Dispatch ``serve``/``export``; fail closed (non-zero) on bad input (§4.7)."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "serve":
            return _run_serve(args)
        return _run_export(args)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)  # noqa: T201 - CLI error channel
        return 1
    except Exception as exc:  # noqa: BLE001 - fail-closed: any runtime failure => exit 1
        print(f"error: {exc}", file=sys.stderr)  # noqa: T201 - CLI error channel
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
