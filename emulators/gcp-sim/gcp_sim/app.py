"""gcp-sim FastAPI application (design sec. 5).

Loads the rendered REST fixtures at startup (fatal if missing/empty), builds the frozen
estate the Phase 6 families project (also fatal if the gate rejects it), mounts one router
per GCP API family, exposes ``/healthz``, and maps every ``GcpError`` to the official GCP
error envelope.

Route-registration order matters: FastAPI matches routes in registration order, so the
routers with concrete prefixes (catalog ``/v1/services``, cloudresourcemanager
``/v1/projects``, compute, functions, servicehealth, storage, scc sources, budgets,
recommender, monitoring) are mounted BEFORE the greedy ``{scope:path}`` / ``{parent:path}``
routers (cai, scc findings) so the greedy patterns do not shadow the concrete ones.
"""

from __future__ import annotations

import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from gcp_sim.errors import GcpError, gcp_error_handler
from gcp_sim.estate import load_estate
from gcp_sim.fixtures import FixtureError, load_fixtures
from gcp_sim.routers import (
    budgets,
    cai,
    catalog,
    cloudresourcemanager,
    compute,
    container,
    functions,
    infra_manager,
    monitoring,
    oauth,
    recommender,
    scc,
    servicehealth,
    storage,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Load fixtures and build the estate into ``app.state``; fail the process if either is absent.

    Also starts the Cloud Monitoring **gRPC** plane when ``GCP_SIM_GRPC_PORT`` is set
    (FR-25). That plane is optional and additive: with the variable unset this lifespan does
    exactly what it did before, and if the plane cannot start -- the client package or
    grpcio absent from a stale image -- the REST plane still serves every route. Failing the
    process instead would take down the surface that is definitely wired to buy one that is
    not, so the failure is reported loudly and the process continues.
    """
    try:
        app.state.fixtures = load_fixtures()
    except FixtureError as exc:
        print(f"fatal: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    # Phase 6 projections read the estate directly (no fixture carries their resources).
    app.state.estate = load_estate()

    app.state.monitoring_grpc_server = None
    try:
        from gcp_sim import monitoring_grpc

        port = monitoring_grpc.configured_port()
        if port is not None:
            app.state.monitoring_grpc_server = monitoring_grpc.start(app.state.fixtures, port)
    except Exception as exc:  # noqa: BLE001 - the optional plane must not break the REST plane
        print(f"warning: monitoring gRPC plane not started: {exc}", file=sys.stderr)

    try:
        yield
    finally:
        server = app.state.monitoring_grpc_server
        if server is not None:
            server.stop(0)


def create_app() -> FastAPI:
    """Build and return the configured FastAPI app."""
    app = FastAPI(title="gcp-sim", version="0.1.0", lifespan=lifespan)
    app.add_exception_handler(GcpError, gcp_error_handler)

    @app.get("/healthz")
    async def healthz() -> dict[str, Any]:
        return {"status": "ok"}

    # Concrete-prefix routers first (so greedy {scope|parent:path} do not shadow).
    app.include_router(oauth.router)
    app.include_router(catalog.router)
    app.include_router(cloudresourcemanager.router)
    app.include_router(compute.router)
    app.include_router(container.router)
    app.include_router(functions.router)
    app.include_router(servicehealth.router)
    app.include_router(storage.router)
    app.include_router(budgets.router)
    app.include_router(recommender.router)
    app.include_router(monitoring.router)
    app.include_router(scc.router)
    # Infrastructure Manager: concrete prefix, mounted before the greedy CAI router.
    app.include_router(infra_manager.router)
    # Greedy {scope:path}:verb routes last.
    app.include_router(cai.router)
    return app


app = create_app()
