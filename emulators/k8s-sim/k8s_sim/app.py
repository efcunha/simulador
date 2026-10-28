"""FastAPI app for k8s-sim: the OpenCost allocation contract for the estate's clusters.

Three routes, and nothing else:

``/healthz``
    The liveness probe the sibling sims (aws-sim, gcp-sim, azure-sim) expose, with the
    same body.

``/allocation/compute``
    The OpenCost allocation API. The response is the official envelope -- ``code`` plus
    ``data`` -- and ``data`` is a list of allocation sets, one per day of the requested
    window, each a map from the allocation key to the allocation.

``/clusterInfo``
    The cluster the request asks about, described by the ``filter`` it carries.

The app is stateless. There is no estate to build, no clock to read, no price list to
fetch and no connection to open: every answer is a pure function of the query string.
The estate's clusters are DATA -- the versioned fixture
``k8s_sim/fixtures/clusters.json`` -- and the generator is not a dependency of the
service.

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
        # ``step`` and ``filter`` are the OpenCost parameter names, spelled the way the
        # CloudPilot provider sends them.
        step: str | None = None,
        filter: str | None = None,
    ) -> JSONResponse:
        """The OpenCost allocation API for the estate's clusters.

        ``window`` is required and read as ``YYYY-MM-DD,YYYY-MM-DD``; it yields one
        allocation set per day, both bounds included.

        ``aggregate`` accepts exactly the four aggregations this phase serves --
        ``namespace``, ``namespace,controller``, ``controller`` and ``cluster``. Any
        other value is refused with a 400 rather than answered with another
        aggregation's view wearing its name.

        ``filter`` selects the cluster, and constrains the namespace and the
        controller. The terms are written as ``key:"value"`` and joined with ``+``,
        the way the CloudPilot provider writes them. A filter that names a cluster the
        estate does not have is answered with an **empty** ``data``: the request
        selected nothing, and nothing is invented to fill it.

        ``step`` is accepted in its one-day form (``1d``) and left out; any other
        step is refused with a 400.

        The parameters are taken as raw strings on purpose: FastAPI would answer 422
        for a malformed boolean, and this contract has exactly one error shape -- the
        400 of the OpenCost envelope.

        ``includeIdle`` is accepted and ignored. The synthetic estate models no idle
        resource, so there is no ``__idle__`` allocation to add and the answer does
        not change: what the payload says about idle is true either way.

        ``accumulate`` is accepted and resolved the way the official handler
        resolves it. ``accumulate=true`` (and the spellings that mean the same
        thing) asks for the whole window in a single set with the costs summed, and
        that is what it gets; the other options keep the step this phase already
        fixed, one set per day. The official handler never refuses an ``accumulate``
        value, so neither does this one.
        """
        requested = (aggregate or "").strip() or allocation.DEFAULT_AGGREGATE
        if requested not in allocation.SUPPORTED_AGGREGATES:
            return _error(
                400,
                f"Invalid 'aggregate' parameter: this phase supports only "
                f"{', '.join(allocation.SUPPORTED_AGGREGATES)}.",
            )

        requested_step = (step or "").strip()
        if requested_step and requested_step != allocation.SUPPORTED_STEP:
            return _error(
                400,
                f"Invalid 'step' parameter: this phase supports only "
                f"'{allocation.SUPPORTED_STEP}'.",
            )

        try:
            alloc_filter = allocation.parse_filter(filter)
        except allocation.FilterError as exc:
            return _error(400, f"Invalid 'filter' parameter: {exc}")

        accumulate_option = allocation.resolve_accumulate(accumulate)

        if window is None:
            return _error(400, "Invalid 'window' parameter: the parameter is required.")
        try:
            start, end = allocation.parse_window(window)
        except allocation.WindowError as exc:
            return _error(400, f"Invalid 'window' parameter: {exc}")

        return JSONResponse(
            status_code=200,
            content={
                "code": 200,
                "data": allocation.allocation_sets(
                    start, end, accumulate_option, requested, alloc_filter
                ),
            },
        )

    @app.get("/clusterInfo")
    async def cluster_info(filter: str | None = None) -> JSONResponse:
        """The cluster the request asks about.

        The ``filter`` names the cluster, the way the CloudPilot provider names it:
        ``cluster:"<name>"``. The cluster has to be one of the estate's -- the
        versioned fixture is the catalog, and a cluster that is not in it does not
        exist. The estate's canonical id is accepted as an alias, exactly as in
        ``/allocation/compute``.

        The answer says only what is true: this is a synthetic cluster. No node count
        and no pod count are published, because the estate does not model them: a
        number here would be a claim about a fact the simulator does not have.
        """
        try:
            alloc_filter = allocation.parse_filter(filter)
        except allocation.FilterError as exc:
            return _error(400, f"Invalid 'filter' parameter: {exc}")

        if alloc_filter.cluster is None:
            return _error(
                400,
                "Invalid 'filter' parameter: the cluster is required, as "
                'cluster:"<name>".',
            )

        if allocation.resolve_cluster_name(alloc_filter.cluster) is None:
            return _error(
                400,
                f"Invalid 'filter' parameter: {alloc_filter.cluster!r} is not a cluster "
                "of the estate.",
            )

        return JSONResponse(status_code=200, content={"code": 200, "data": {"version": "synthetic"}})

    return app
