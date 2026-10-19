"""Cloud Monitoring gRPC plane for gcp-sim (FR-25).

The monitoring client FinOps builds speaks **gRPC only**: ``google-cloud-monitoring``
ships no REST transport for any of its eight services (verified across 0.36.2 -> 2.32.0:
``services/*/transports/`` holds ``{base,grpc,grpc_asyncio}`` and no ``rest``), so
``MetricServiceClient(transport="rest")`` is a ``KeyError``, not a shortcut. Serving these
operations over HTTP therefore reaches nobody. This module serves the plane the client
actually uses, and it serves it from the **client's own descriptors** -- the method paths
and message classes below are read off the installed package, so the sim cannot drift from
the wire contract and nothing is hand-written:

    /google.monitoring.v3.MetricService/ListTimeSeries
    /google.monitoring.v3.MetricService/ListMetricDescriptors
    /google.monitoring.v3.AlertPolicyService/ListAlertPolicies

Data comes from the SAME rendered fixtures the REST plane serves (``FixtureStore``), so one
estate backs both planes; the fixture bodies are GCP's proto-JSON spelling, which is what
``json_format.ParseDict`` consumes and what the real REST API returns.

Auth: none. FinOps builds this client anonymously when the endpoint override is set
(``<modulo do consumidor>.GCPClient.monitoring_client``, mirroring ``bigquery_client``'s
anonymous emulator branch), so a bearer check here would reject the only client that uses
the plane. The REST plane keeps its bearer check for the REST clients that send one.

The import of ``google.cloud.monitoring_v3`` is deliberately lazy (``_load_operations``):
the REST plane must not depend on the client package, so a deployment shipping the sim
without it still answers every REST route.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from concurrent import futures
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import grpc
from google.protobuf import json_format

from gcp_sim.fixtures import FixtureStore, fixtures_dir, load_fixtures

#: Port the plane listens on when ``GCP_SIM_GRPC_PORT`` is unset and the CLI is used
#: without ``--port``. The container image sets the env var to this value and publishes
#: the port alongside the REST plane's 8085.
DEFAULT_PORT = 8087

#: Env var that enables the plane. Unset (the default) means the process serves the REST
#: plane only, exactly as it did before this module existed -- ``python -m gcp_sim.app``
#: and ``uvicorn gcp_sim.app:app`` are unchanged.
PORT_ENV = "GCP_SIM_GRPC_PORT"

#: The scope prefix every monitoring request's ``name`` must carry (mirrors the REST
#: plane's ``validate_prefix(name, ("projects/",), "name")``).
_SCOPE_PREFIX = "projects/"

_MAX_WORKERS = 8


@dataclass(frozen=True, slots=True)
class _Operation:
    """One monitoring method, bound to its request/response classes and its fixture."""

    service: str
    method: str
    fixture: str
    request: Any
    response: Any

    @property
    def path(self) -> str:
        """The gRPC method path the client's transport stubs, verbatim."""
        return f"/{self.service}/{self.method}"


def _load_operations() -> tuple[_Operation, ...]:
    """Build the operation table from the descriptors the client package ships.

    Lazy on purpose: importing ``google.cloud.monitoring_v3`` here instead would make the
    whole REST plane require the client package.
    """
    from google.cloud.monitoring_v3.types import alert_service, metric_service

    return (
        _Operation(
            service="google.monitoring.v3.MetricService",
            method="ListTimeSeries",
            fixture="monitoring_time_series.json",
            request=metric_service.ListTimeSeriesRequest,
            response=metric_service.ListTimeSeriesResponse,
        ),
        _Operation(
            service="google.monitoring.v3.MetricService",
            method="ListMetricDescriptors",
            fixture="monitoring_metric_descriptors.json",
            request=metric_service.ListMetricDescriptorsRequest,
            response=metric_service.ListMetricDescriptorsResponse,
        ),
        _Operation(
            service="google.monitoring.v3.AlertPolicyService",
            method="ListAlertPolicies",
            fixture="monitoring_alert_policies.json",
            request=alert_service.ListAlertPoliciesRequest,
            response=alert_service.ListAlertPoliciesResponse,
        ),
    )


def _handler(operation: _Operation, fixtures: FixtureStore) -> Any:
    """Return the unary handler for ``operation``, serving its fixture body."""

    def _serve(request: Any, context: grpc.ServicerContext) -> Any:
        name = str(request.name)
        if not name.startswith(_SCOPE_PREFIX):
            context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                f"name must start with one of {_SCOPE_PREFIX}",
            )
        body = fixtures.get(operation.fixture)
        if not body:
            context.abort(
                grpc.StatusCode.NOT_FOUND,
                f"no {operation.fixture} fixture loaded for {operation.method}",
            )
        # ParseDict consumes GCP's proto-JSON spelling and the wrapped message serialises
        # to exactly the bytes the client's ``response_deserializer`` expects.
        return operation.response.wrap(json_format.ParseDict(body, operation.response.pb()()))

    return _serve


def _generic_handler(operation: _Operation, fixtures: FixtureStore) -> Any:
    """Bind ``operation`` to its service name using the client's own serializers.

    Both codecs are proto-plus classmethods from the installed package, so request
    parsing and response encoding are the client's, not a re-implementation of them.
    """
    return grpc.method_handlers_generic_handler(
        operation.service,
        {
            operation.method: grpc.unary_unary_rpc_method_handler(
                _handler(operation, fixtures),
                request_deserializer=operation.request.deserialize,
                response_serializer=operation.response.serialize,
            )
        },
    )


def create_server(fixtures: FixtureStore) -> grpc.Server:
    """Build (but do not start) the monitoring gRPC server over ``fixtures``."""
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=_MAX_WORKERS))
    server.add_generic_rpc_handlers(
        tuple(_generic_handler(operation, fixtures) for operation in _load_operations())
    )
    return server


def start(fixtures: FixtureStore, port: int) -> grpc.Server:
    """Start the plane on ``port`` and return the running server."""
    server = create_server(fixtures)
    bound = server.add_insecure_port(f"0.0.0.0:{port}")
    if bound == 0:
        raise RuntimeError(f"could not bind the monitoring gRPC plane to port {port}")
    server.start()
    return server


def configured_port() -> int | None:
    """Return the port from ``GCP_SIM_GRPC_PORT``, or ``None`` when the plane is off.

    Unset/empty is the default and keeps the process REST-only. A non-numeric value is a
    configuration error: it disables the plane loudly rather than silently binding a
    default port the operator did not ask for.
    """
    raw = os.environ.get(PORT_ENV, "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        print(f"warning: {PORT_ENV}={raw!r} is not a port; monitoring gRPC plane disabled", file=sys.stderr)
        return None


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m gcp_sim.monitoring_grpc")
    parser.add_argument(
        "--port",
        type=int,
        default=configured_port() or DEFAULT_PORT,
        help=f"port to serve on (default: {PORT_ENV} or {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--fixtures",
        type=Path,
        default=fixtures_dir(),
        help=f"rendered fixtures dir (default: GCP_SIM_FIXTURES_DIR or {fixtures_dir()})",
    )
    return parser.parse_args(list(argv))


def main(argv: Sequence[str] | None = None) -> int:
    """Serve the plane until interrupted (standalone entry point)."""
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    fixtures = load_fixtures(args.fixtures)
    server = start(fixtures, args.port)
    print(f"gcp-sim monitoring gRPC plane on :{args.port} ({len(_load_operations())} operations)")
    server.wait_for_termination()
    return 0


if __name__ == "__main__":
    sys.exit(main())
