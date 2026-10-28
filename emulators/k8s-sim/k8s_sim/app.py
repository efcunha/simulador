"""FastAPI app for k8s-sim: the OpenCost allocation contract for one synthetic AKS cluster.

Two routes, and nothing else:

``/healthz``
    The liveness probe the sibling sims (aws-sim, gcp-sim, azure-sim) expose, with the
    same body.

``/allocation/compute``
    The OpenCost allocation API. The response is the official envelope -- ``code`` plus
    ``data`` -- and ``data`` is a list of allocation sets, one per day of the requested
    window, each a map from the allocation key to the allocation.

The app is stateless. There is no estate to build, no clock to read, no price list to
fetch and no connection to open: every answer is a pure function of the query string.

The wire shape, the sources it was read from, and the places where this phase narrows
or deviates from OpenCost are documented in ``docs/k8s-sim-opencost-contract.md``.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from k8s_sim.projections import allocation


def _error(status: int, message: str) -> JSONResponse:
    """The OpenCost error envelope: ``code`` plus ``message``.

    OpenCost writes its errors through ``protocol.WriteError``, which emits exactly
    this shape with the HTTP status as the code.
    """
    return JSONResponse(status_code=status, content={"code": status, "message": message})


def create_app() -> FastAPI:
    """Build the k8s-sim app."""
    app = FastAPI(title="k8s-sim", docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/healthz")
    async def healthz() -> dict[str, Any]:
        """Liveness probe, JSON like the sibling sims."""
        return {"status": "ok", "synthetic": True}

    @app.get("/allocation/compute")
    async def allocation_compute(
        window: str | None = None,
        aggregate: str | None = None,
        # ``includeIdle`` is the OpenCost parameter name, camelCase and all: the query
        # string is the contract, and the query string is spelled ``includeIdle``.
        includeIdle: str | None = None,  # noqa: N803
        accumulate: str | None = None,
    ) -> JSONResponse:
        """The OpenCost allocation API for the synthetic cluster.

        ``window`` is required and read as ``YYYY-MM-DD,YYYY-MM-DD``; it yields one
        allocation set per day, both bounds included. ``aggregate`` is accepted, and
        this phase serves exactly one aggregation -- ``namespace``. Another aggregation
        is refused with a 400 rather than answered with the namespace view wearing the
        other aggregation's name.

        The parameters are taken as raw strings on purpose: FastAPI would answer 422
        for a malformed boolean, and this contract has exactly one error shape -- the
        400 of the OpenCost envelope.

        ``includeIdle`` is accepted and ignored. The synthetic estate models no idle
        resource, so there is no ``__idle__`` allocation to add and the answer does
        not change: what the payload says about idle is true either way.

        ``accumulate`` is refused. This phase always accumulates by day, and honoring
        ``accumulate=true`` would mean answering with ONE set for the whole window
        instead of one per day -- a different shape wearing the same name. Refusing it
        says "this phase does not serve that" instead of "here is the answer, but it is
        not what you asked for".
        """
        requested = (aggregate or "").strip() or allocation.SUPPORTED_AGGREGATE
        if requested != allocation.SUPPORTED_AGGREGATE:
            return _error(
                400,
                f"Invalid 'aggregate' parameter: this phase supports only '{allocation.SUPPORTED_AGGREGATE}'.",
            )

        if (accumulate or "").strip():
            return _error(
                400,
                "Invalid 'accumulate' parameter: this phase always accumulates by day and does not serve 'accumulate'.",
            )

        if window is None:
            return _error(400, "Invalid 'window' parameter: the parameter is required.")
        try:
            start, end = allocation.parse_window(window)
        except allocation.WindowError as exc:
            return _error(400, f"Invalid 'window' parameter: {exc}")

        return JSONResponse(
            status_code=200,
            content={"code": 200, "data": allocation.allocation_sets(start, end)},
        )

    return app
