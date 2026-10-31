"""FastAPI app factory + router registration + error-envelope interceptor (design §5.3/§5.4).

``create_app(settings)`` builds the gated estate ONCE (shared read-only on
``app.state``), registers every router, exposes ``GET /healthz``, and installs the
exception handlers that map all errors to the Azure ``{error:{code,message}}``
envelope — crucially mapping FastAPI's default 422 validation response to a 400
Azure envelope (§5.4), and the paging ``BadContinuationToken`` to a 400 envelope
(§5.3).

The estate is built via ``azure_sim.estate.build_simulated_estate`` (fail-closed
gate) at app-create time, so a request never rebuilds it and every router projects
from the same frozen source.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from azure_sim.api import (
    advisor,
    compute,
    containerservice,
    cost_management,
    defender,
    deployment_stacks,
    graph,
    monitor,
    network,
    policy_insights,
    resource_graph,
    retail_prices,
    sql,
    storage,
    subscription,
    token,
    web,
)
from azure_sim.api.common import (
    CODE_INVALID_REQUEST,
    CODE_NOT_FOUND,
    AzureApiError,
    error_envelope,
)
from azure_sim.api.paging import BadContinuationTokenError
from azure_sim.config import Settings
from azure_sim.estate import build_simulated_estate


def _register_exception_handlers(app: FastAPI) -> None:
    """Install handlers that render every error as an Azure error envelope (§5.3)."""

    @app.exception_handler(AzureApiError)
    async def _azure_api_error(request: Request, exc: AzureApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_envelope(exc.azure_code, exc.azure_message),
        )

    @app.exception_handler(BadContinuationTokenError)
    async def _bad_token(request: Request, exc: BadContinuationTokenError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content=error_envelope(CODE_INVALID_REQUEST, str(exc)),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Map FastAPI's default 422 to a 400 Azure envelope (§5.4).
        return JSONResponse(
            status_code=400,
            content=error_envelope(CODE_INVALID_REQUEST, "The request is invalid."),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        detail = exc.detail
        if isinstance(detail, dict) and "code" in detail and "message" in detail:
            body = error_envelope(str(detail["code"]), str(detail["message"]))
        else:
            code = CODE_NOT_FOUND if exc.status_code == 404 else CODE_INVALID_REQUEST
            body = error_envelope(code, str(detail))
        return JSONResponse(status_code=exc.status_code, content=body)


def create_app(settings: Settings) -> FastAPI:
    """Build the FastAPI app for ``settings`` (estate built once, routers registered)."""
    app = FastAPI(title="azure-sim", docs_url=None, redoc_url=None, openapi_url=None)
    # Build the frozen, gated estate ONCE; shared read-only by every router.
    app.state.settings = settings
    app.state.estate = build_simulated_estate(
        seed=settings.seed,
        profile=settings.profile,
        currency=settings.currency,
        window_days=settings.window_days,
    )
    app.state.exports = {}
    app.state.budgets = {}

    _register_exception_handlers(app)

    @app.get("/healthz")
    async def healthz() -> dict[str, Any]:
        """Liveness probe (design §6.1)."""
        return {"status": "ok", "synthetic": True}

    @app.post("/admin/estate/refresh")
    async def refresh_estate(days: int | None = None) -> dict[str, Any]:
        """Rebuild the estate with a window covering ``days``.

        Operational hook for the daily cadence: the Cost Management Query API
        serves this estate, so extending its window is how a newly generated
        day becomes visible to a caller without restarting the container. The
        estate is deterministic on ``(seed, profile, currency, day)``, so the
        refreshed data is the same the daily render produced. Not an Azure API
        path, and therefore outside the ``api-version`` gate on purpose.
        """
        window = days if days is not None else settings.window_days
        app.state.estate = build_simulated_estate(
            seed=settings.seed,
            profile=settings.profile,
            currency=settings.currency,
            window_days=window,
        )
        return {"status": "ok", "window_days": window}

    # Register every router. Routers match on official Azure path shapes.
    app.include_router(token.router)
    app.include_router(deployment_stacks.router)
    app.include_router(cost_management.router)
    app.include_router(resource_graph.router)
    app.include_router(defender.router)
    app.include_router(policy_insights.router)
    app.include_router(advisor.router)
    app.include_router(graph.router)
    app.include_router(retail_prices.router)
    app.include_router(monitor.router)
    # Resource-plane (ARM) routers: the Microsoft.* resource managers FinOps own
    # Azure path calls. Registered after the control plane so no two-segment control-plane
    # path (``/users``, ``/api/retail/prices``) can be shadowed by a resource route.
    app.include_router(subscription.router)
    app.include_router(compute.router)
    app.include_router(containerservice.router)
    app.include_router(network.router)
    app.include_router(sql.router)
    app.include_router(storage.router)
    app.include_router(web.router)
    return app
