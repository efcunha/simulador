"""FastAPI app for k8s-sim: the OpenCost allocation contract for the estate's clusters,
the Kubernetes API the CloudPilot consumer reads the estate's namespaces and pods
from, the Prometheus instant query it reads the estate's usage from, and the Kubecost
Model API's allocation route, the one its ``kubecost`` provider reads.

Four planes, eight routes:

**The OpenCost plane** (the contract this service was born with):

``/healthz``
    The liveness probe the sibling sims (aws-sim, gcp-sim, azure-sim) expose, with the
    same body.

``/allocation/compute``
    The OpenCost allocation API. The response is the official envelope -- ``code`` plus
    ``data`` -- and ``data`` is a list of allocation sets, one per day of the requested
    window, each a map from the allocation key to the allocation.

``/clusterInfo``
    The cluster the request asks about, described by the ``filter`` it carries.

**The Kubernetes API plane** (the subset the CloudPilot consumer calls):

``/api/v1/namespaces``
    The namespaces of the synthetic cluster. The CloudPilot ``ConnectionTester`` reads
    this route to decide whether a kubeconfig connects at all, and the GCP and Azure
    providers read it to learn the estate's namespaces.

``/api/v1/pods``
    Every pod of the cluster. The EKS provider reads it with the official ``kubernetes``
    client (``CoreV1Api.list_pod_for_all_namespaces``).

``/api/v1/namespaces/{namespace}/pods``
    The pods of one namespace. The GCP and Azure providers read it after listing the
    namespaces.

**The Prometheus plane** (the usage the CloudPilot consumer measures):

``/api/v1/query``
    The Prometheus instant query. The CloudPilot ``opencost`` provider reads it to
    obtain the estate's namespace-grain CPU and memory telemetry, and the rightsizing
    path is closed without that telemetry.

**The Kubecost plane** (the contract the CloudPilot ``kubecost`` provider reads):

``/model/allocation``
    The allocation route of the Kubecost Model API. The CloudPilot ``kubecost`` provider
    reads it for the cluster's costs, for a namespace's costs and for a workload's
    labels. The answer is the published envelope -- ``code`` plus ``data`` -- and
    ``data`` is a list of allocation sets, each a map from the allocation key to the
    allocation, exactly as the OpenCost plane answers.

    The Model API publishes fifteen paths and this is the only one the consumer reads.
    The consumer also asks ``/model/clusterInfo`` and ``/savings/requestSizing``:
    **neither is published by the Model API**, and this service does not serve what the
    source does not publish -- the gap is declared in
    ``docs/k8s-sim-opencost-contract.md``.

The four planes describe ONE estate, so their constants agree by construction (see
:mod:`k8s_sim.projections.kubernetes`). They answer with different envelopes on
purpose: the OpenCost and the Kubecost planes with the ``code`` plus ``data`` envelope
the cost APIs publish, the Kubernetes plane with the official Kubernetes shapes
(``NamespaceList``, ``PodList`` and, on a failure, a ``Status``), and the Prometheus
plane with the Prometheus envelope (``status`` plus ``data``, or the error envelope).
The Kubernetes plane asks for a bearer token -- the consumer always sends one -- and the
OpenCost, Prometheus and Kubecost planes do not, so the contracts that already existed
are untouched.

The app is stateless. There is no estate to build, no price list to fetch and no
connection to open: every answer is a pure function of the query string. The one
clock the service reads is the Prometheus evaluation instant (see
:mod:`k8s_sim.projections.prometheus`). The estate's clusters are DATA -- the
versioned fixture ``k8s_sim/fixtures/clusters.json`` -- and the generator is not a
dependency of the service.

The wire shape, the sources it was read from, and the places where this phase narrows
or deviates from OpenCost are documented in ``docs/k8s-sim-opencost-contract.md``.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Header
from fastapi.responses import JSONResponse

from k8s_sim.projections import allocation, kubecost, kubernetes, prometheus


def _error(status: int, message: str) -> JSONResponse:
    """The OpenCost error envelope: ``code`` plus ``message``.

    OpenCost writes its errors through ``protocol.WriteError``, which emits exactly
    this shape with the HTTP status as the code.
    """
    return JSONResponse(status_code=status, content={"code": status, "message": message})


def _kubernetes_status(code: int, reason: str, message: str) -> JSONResponse:
    """The Kubernetes ``Status`` object the API plane answers a failure with.

    The shape is the official one: ``status`` says the request failed, ``reason``
    is the machine-readable cause, ``message`` is for a person, and ``code`` is
    the HTTP status repeated inside the body.
    """
    return JSONResponse(
        status_code=code,
        content={
            "kind": "Status",
            "apiVersion": "v1",
            "metadata": {},
            "status": "Failure",
            "message": message,
            "reason": reason,
            "code": code,
        },
    )


def _authorized(authorization: str | None) -> bool:
    """Whether the request carries a bearer token the API plane accepts.

    The simulator models no identity and no RBAC: the estate keeps no list of
    valid tokens, so **any** non-empty bearer token is accepted -- the token is
    the operator's own, and refusing it would be refusing a fact the simulator
    cannot check. A request without a usable token is refused with a 401, the
    shape the CloudPilot ``ConnectionTester`` categorizes as ``auth_rejected``.

    The scheme is matched case-insensitively, as HTTP requires.
    """
    if not authorization:
        return False

    scheme, _, token = authorization.partition(" ")
    return scheme.lower() == "bearer" and bool(token.strip())


def _unauthorized() -> JSONResponse:
    """The 401 the API plane answers a request without a bearer token with."""
    return _kubernetes_status(401, "Unauthorized", "Unauthorized")


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
        the way the CloudPilot provider writes them. The ``cluster`` term accepts
        three aliases of the same cluster -- its **name**, the estate's canonical
        ``cluster_id`` and the **native id** the discovery publishes (the EKS ARN,
        the AKS ARM resource id and the GKE ``selfLink``); whichever one the request
        came in through, the payload publishes the name. A filter that names a
        cluster the estate does not have is answered with an **empty** ``data``: the
        request selected nothing, and nothing is invented to fill it.

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
        exist. The estate's canonical id and the **native id** the discovery
        publishes (the EKS ARN, the AKS ARM resource id and the GKE ``selfLink``) are
        accepted as aliases, exactly as in ``/allocation/compute``.

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

    @app.get("/api/v1/namespaces")
    async def list_namespaces(authorization: str | None = Header(default=None)) -> JSONResponse:
        """The namespaces of the synthetic cluster.

        The CloudPilot ``ConnectionTester`` reads this route to decide whether a
        kubeconfig connects at all: it counts the ``items`` and **fails when the
        list is empty**. The GCP and Azure providers read it to learn the
        estate's namespaces, and use each name to ask for that namespace's pods.

        The payload is the official ``NamespaceList``: ``kind``, ``apiVersion``,
        ``metadata`` and ``items``. It is NOT the OpenCost envelope -- the two
        planes answer in their own contracts.
        """
        if not _authorized(authorization):
            return _unauthorized()

        return JSONResponse(status_code=200, content=kubernetes.namespace_list())

    @app.get("/api/v1/pods")
    async def list_pods(authorization: str | None = Header(default=None)) -> JSONResponse:
        """Every pod of the synthetic cluster, across every namespace.

        This is the route the official ``kubernetes`` client reaches through
        ``CoreV1Api.list_pod_for_all_namespaces`` (``GET /api/v1/pods``), which
        the CloudPilot EKS provider calls when the cluster is reached through a
        kubeconfig. The client deserializes the answer into a ``V1PodList``.
        """
        if not _authorized(authorization):
            return _unauthorized()

        return JSONResponse(status_code=200, content=kubernetes.pod_list())

    @app.get("/api/v1/namespaces/{namespace}/pods")
    async def list_namespaced_pods(
        namespace: str,
        authorization: str | None = Header(default=None),
    ) -> JSONResponse:
        """The pods of one namespace.

        The GCP and Azure providers read it right after listing the namespaces:
        one request per namespace, and the sum of the pods' requests is that
        namespace's usage.

        A namespace the estate does not have is a **404** with the official
        ``Status`` object -- the resource is not there, and nothing is invented
        to fill the gap. The consumer treats anything above 399 as "no pods
        here" and moves on.
        """
        if not _authorized(authorization):
            return _unauthorized()

        if not kubernetes.has_namespace(namespace):
            return _kubernetes_status(
                404,
                "NotFound",
                f'namespaces "{namespace}" not found',
            )

        return JSONResponse(status_code=200, content=kubernetes.pod_list())

    @app.get("/api/v1/query")
    async def prometheus_query(query: str | None = None, time: str | None = None) -> JSONResponse:
        """The Prometheus instant query over the estate.

        The CloudPilot ``opencost`` provider reads this route to obtain the
        namespace-grain CPU and memory telemetry it materializes into the snapshot
        (``cpu_usage_current_millicores`` and ``memory_usage_current_bytes``), and
        the rightsizing path is closed without it. The provider sends **no**
        authentication header, so this plane does not ask for one -- the OpenCost
        plane does not either, and the contract that already existed is untouched.

        The answer is the Prometheus HTTP API's shape: ``status`` plus ``data``
        (``resultType`` and ``result``) on success, and ``status``, ``errorType``
        and ``error`` on a failure -- which carries the HTTP status ``400``.

        A query the estate has no series for is answered with an **empty vector**,
        the way a Prometheus answers a query that selects nothing. The estate
        publishes no series for the Karpenter queries the consumer may send, because
        it models no Karpenter.
        """
        try:
            payload = prometheus.evaluate(query=query, time_param=time)
        except prometheus.QueryError as exc:
            return JSONResponse(status_code=400, content=prometheus.failure(str(exc)))

        return JSONResponse(status_code=200, content=payload)

    @app.get("/model/allocation")
    async def model_allocation(
        window: str | None = None,
        aggregate: str | None = None,
        step: str | None = None,
        accumulate: str | None = None,
        idle: str | None = None,
        external: str | None = None,
        # The filter parameters are spelled the way the Model API spells them, camelCase
        # and all: the query string is the contract.
        filterClusters: str | None = None,  # noqa: N803
        filterNamespaces: str | None = None,  # noqa: N803
        filterControllers: str | None = None,  # noqa: N803
        filterControllerKinds: str | None = None,  # noqa: N803
        filterLabels: str | None = None,  # noqa: N803
        filterAnnotations: str | None = None,  # noqa: N803
        filterServices: str | None = None,  # noqa: N803
        shareIdle: str | None = None,  # noqa: N803
        splitIdle: str | None = None,  # noqa: N803
        idleByNode: str | None = None,  # noqa: N803
        format: str | None = None,  # noqa: N803
        authorization: str | None = Header(default=None),
    ) -> JSONResponse:
        """The allocation route of the Kubecost Model API.

        The CloudPilot ``kubecost`` provider reads this route for the cluster's costs
        (``aggregate=namespace``), for a namespace's costs and for a workload's labels
        (``aggregate=controller``). It sends ``window``, ``aggregate``, ``accumulate``
        and the filters, and it sends ``Authorization: Bearer <token>``.

        ``window`` is required and read as ``YYYY-MM-DD,YYYY-MM-DD`` -- the spelling the
        provider sends. The Model API also documents durations and relative windows
        (F15); this phase reads exactly one spelling and refuses the rest instead of
        guessing what was meant.

        ``aggregate`` accepts the aggregations this estate can answer -- ``namespace``,
        ``namespace,controller``, ``controller`` and ``cluster``. The Model API
        publishes more (F15); the others are refused with a 400 rather than answered
        with another aggregation's view wearing its name.

        ``step`` is accepted in its one-day form (``1d``) and left out. **Left out means
        the window itself** (F15: "If unspecified, this defaults to the window, so that
        you receive exactly one set for the entire window"), so a request without a step
        is answered with one set whose costs are summed over the window. Any other step
        is refused with a 400.

        ``accumulate`` is resolved the way the OpenCost plane resolves it: ``true`` asks
        for the whole window in a single set.

        The filters are read one value each -- the Model API publishes them as
        comma-separated lists, and a list names more than one cluster, namespace or
        controller, so it is refused rather than resolved to one of its members. The
        cluster is read with the estate's three aliases (its name, its canonical
        ``cluster_id`` and the **native id** the discovery publishes), exactly as the
        OpenCost plane reads it, and the answer publishes the **name**. A cluster the
        estate does not have is answered with an **empty** ``data``: the request
        selected nothing, and nothing is invented to fill it.

        The parameters the Model API publishes and this phase does not read are refused
        with a 400, never ignored: answering a filtered request with an unfiltered
        answer would be a lie about what was served.

        ``idle`` and ``external`` are accepted and ignored. The estate models no idle
        resource and no out-of-cluster cost, so the answer does not change either way:
        what the payload says about idle and about external cost is true either way.

        The ``Authorization`` header is accepted and ignored. The Model API's published
        definition declares no security scheme (F15), so this phase does not demand a
        token the source does not ask for; the provider's token is welcome and unused.

        The error envelope is the one the sibling plane answers with -- ``code`` plus
        ``message``, with the HTTP status as the code. The Model API declares the
        ``400`` status but not the body (F15), and the two cost planes of this service
        answer with the same shape.
        """
        del authorization

        for name, value in (
            ("filterControllerKinds", filterControllerKinds),
            ("filterLabels", filterLabels),
            ("filterAnnotations", filterAnnotations),
            ("filterServices", filterServices),
            ("shareIdle", shareIdle),
            ("splitIdle", splitIdle),
            ("idleByNode", idleByNode),
        ):
            if value is not None:
                return _error(400, f"Invalid '{name}' parameter: this phase does not read it.")

        requested_format = (format or "").strip().lower()
        if requested_format and requested_format not in kubecost.SUPPORTED_FORMATS:
            return _error(
                400,
                "Invalid 'format' parameter: this phase serves only "
                f"{', '.join(kubecost.SUPPORTED_FORMATS)}.",
            )

        requested_aggregate = (aggregate or "").strip() or allocation.DEFAULT_AGGREGATE
        if requested_aggregate not in allocation.SUPPORTED_AGGREGATES:
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

        if window is None:
            return _error(400, "Invalid 'window' parameter: the parameter is required.")

        try:
            start, end = allocation.parse_window(window)
        except allocation.WindowError as exc:
            return _error(400, f"Invalid 'window' parameter: {exc}")

        try:
            alloc_filter = kubecost.parse_filter(
                filterClusters, filterNamespaces, filterControllers
            )
        except kubecost.KubecostFilterError as exc:
            return _error(400, f"Invalid filter: {exc}")

        if requested_step == allocation.SUPPORTED_STEP:
            accumulate_option = allocation.resolve_accumulate(accumulate)
        else:
            # No step: the Model API's default is the window itself (F15), so the answer
            # is ONE set for the whole window, with the costs summed.
            accumulate_option = allocation.ACCUMULATE_ALL

        return JSONResponse(
            status_code=200,
            content={
                "code": 200,
                "data": kubecost.allocation_sets(
                    start, end, accumulate_option, requested_aggregate, alloc_filter
                ),
            },
        )

    return app
