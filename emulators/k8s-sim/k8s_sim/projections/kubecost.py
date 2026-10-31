"""The Kubecost plane of the k8s-sim: the Model API's allocation route -- the one the
CloudPilot consumer's ``kubecost`` provider reads.

This is the FOURTH projection of the SAME synthetic estate.
:mod:`k8s_sim.projections.allocation` describes what the estate **costs** (the OpenCost
allocation contract), :mod:`k8s_sim.projections.kubernetes` describes what it
**contains** (the objects a Kubernetes API server would list),
:mod:`k8s_sim.projections.prometheus` describes what it **measures** (the usage series a
Prometheus would serve), and this module describes what the estate costs **through the
Kubecost Model API** -- the same estate, read through a different contract.

**What the consumer does, and where that was measured** (read-only, 2026-10-31, on
``C:\\Projetos\\cloudpilot-deploy``):

* ``backend/app/services/k8s_finops/providers/kubecost.py:305-323`` -- ``get_cluster_costs``
  asks ``GET {endpoint}/model/allocation`` with ``window``, ``aggregate=namespace``,
  ``filterClusters`` and ``accumulate=false``.
* ``kubecost.py:326-343`` -- ``get_namespace_costs`` asks the same route with
  ``aggregate=controller``, ``filterClusters`` and ``filterNamespaces``.
* ``kubecost.py:404-424`` -- ``get_resource_labels`` asks the same route with
  ``aggregate=controller``, ``filterClusters``, ``filterNamespaces`` and
  ``filterControllers``.
* ``kubecost.py:378-402`` and ``kubecost.py:544-559`` -- ``get_cluster_health`` and
  ``test_connection`` ask ``GET {endpoint}/model/clusterInfo``. **That route is NOT
  published by the Kubecost Model API** (F15 lists its fifteen paths and
  ``/model/clusterInfo`` is not one of them), so this plane does not serve it: see
  :mod:`k8s_sim.app` and the contract's "lacunas declaradas".
* ``kubecost.py:404-424`` -- the request carries ``Authorization: Bearer <token>``; the
  provider refuses to send anything without one (``kubecost.py:80-95``).

The three requests the consumer sends were **measured against this service on
2026-10-31**, before this plane existed: all of them answered ``404``. The raw access
log lines are in ``docs/regression/mapa-impacto-s4b2i.md``.

**The route is the published one.** The Kubecost Model API publishes fifteen paths
(F15); this plane serves the single one the consumer reads, ``/model/allocation``. The
other fourteen (``/model/assets``, ``/model/budget``, ``/model/cloudCost``,
``/model/forecast/allocation``, ``/model/savings/*``) are outside this phase: nothing in
the consumer reads them.

**The envelope is the published one.** F15 declares the ``200`` response of
``/model/allocation`` as an object with ``code`` and ``data``, where ``data`` is an array
of objects whose additional properties are ``Allocation`` -- a list of allocation sets,
each a map from the allocation key to the allocation. That is the same envelope the
OpenCost plane answers with, and the consumer's parser reads it the same way
(``kubecost.py:176-197``: ``raw_data["data"]`` -> ``period_data.items()``).

**The allocation object is the published one.** F15's ``Allocation`` schema publishes
``name``, ``properties``, ``window``, ``start``, ``end``, ``cpuCores``,
``cpuCoreRequestAverage``, ``cpuCoreUsageAverage``, ``cpuCoreHours``, ``cpuCost``,
``networkTransferBytes``, ``networkCost``, ``pvBytes``, ``pvByteHours``, ``pvCost``,
``ramBytes``, ``ramByteRequestAverage``, ``ramByteUsageAverage``, ``ramByteHours``,
``ramCost``, ``totalCost`` and more. This phase publishes the ones the estate has a
figure for, and **does not** publish the ones it has none for (GPU, shared cost,
external cost, load balancer, the cost adjustments and the efficiencies) -- for the same
reason the OpenCost plane publishes no zeros for them: a number there would be a claim
about a fact the estate does not have.

**The memory cost is published as ``ramCost``, and the consumer reads ``memCost``.** The
Kubecost model publishes ``ramCost`` (F16: ``pkg/kubecost/allocation.go``, ``RAMCost
float64 `json:"ramCost"```), and ``memCost`` appears nowhere in it. The consumer's
parser reads ``alloc.get("memCost", 0)`` (``kubecost.py:216``), so the memory cost it
reports is zero. That is a **consumer-side** reading, not a simulator one: this phase
publishes the field the source publishes and declares the mismatch -- it does not
invent a ``memCost`` to make the consumer's number come out.

**The filters are the published ones.** F15 declares ``filterClusters``,
``filterNamespaces`` and ``filterControllerKinds``/``filterControllers`` as
comma-separated lists. This phase reads **one** cluster, one namespace and one controller
per request, and **refuses** a list instead of picking one of its members. The cluster is
read with the estate's three aliases (its name, its canonical ``cluster_id`` and the
**native id** the discovery publishes), exactly as the OpenCost plane reads it, and the
answer publishes the **name**.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from k8s_sim.projections import allocation

#: The route this plane serves -- the one path of the Kubecost Model API the consumer
#: reads (F15).
ROUTE = "/model/allocation"

#: The output formats the Model API publishes (F15 declares ``json`` and ``csv``, with
#: ``json`` as the default). This phase serves the JSON one only: a CSV answer would be
#: a second contract to keep coherent with the first.
SUPPORTED_FORMATS: tuple[str, ...] = ("json",)

#: The parameters this phase reads.
SUPPORTED_PARAMETERS: tuple[str, ...] = (
    "window",
    "aggregate",
    "step",
    "accumulate",
    "idle",
    "external",
    "filterClusters",
    "filterNamespaces",
    "filterControllers",
    "format",
)

#: The parameters the Model API publishes and this phase does **not** read. A request
#: that carries one of them is refused with a 400 rather than answered as if the
#: parameter had not been there: answering a filtered request with an unfiltered answer
#: is a lie about what was served.
UNSUPPORTED_PARAMETERS: tuple[str, ...] = (
    "filterControllerKinds",
    "filterLabels",
    "filterAnnotations",
    "filterServices",
    "shareIdle",
    "splitIdle",
    "idleByNode",
)


class KubecostFilterError(ValueError):
    """The request carries a filter this phase does not read.

    The Model API answers such a request with the HTTP status ``400`` and the error
    envelope (``code`` plus ``message``).
    """


def _single(value: str | None, name: str) -> str | None:
    """Read one value out of a filter the Model API declares as a list.

    The Model API publishes these filters as comma-separated lists (F15). This phase
    reads **one** value: a list names more than one cluster, namespace or controller,
    and the estate publishes one workload, so choosing one of them would be answering a
    question that was not asked. The list is refused instead.

    :raises KubecostFilterError: when the value carries a comma.
    """
    if value is None:
        return None

    text = value.strip()
    if not text:
        return None

    if "," in text:
        raise KubecostFilterError(
            f"{name} carries a list ({value!r}); this phase reads one cluster, namespace "
            "or controller per request"
        )
    return text


def parse_filter(
    filter_clusters: str | None = None,
    filter_namespaces: str | None = None,
    filter_controllers: str | None = None,
) -> allocation.AllocationFilter:
    """Read the filters of a Model API allocation request.

    The three filters this phase reads become the terms of the estate's own filter (see
    :class:`k8s_sim.projections.allocation.AllocationFilter`), so the cluster is
    resolved with the estate's three aliases and the namespace and the controller are
    matched against the workload the estate carries.

    :raises KubecostFilterError: when a filter carries a list.
    """
    return allocation.AllocationFilter(
        cluster=_single(filter_clusters, "filterClusters"),
        namespace=_single(filter_namespaces, "filterNamespaces"),
        controller=_single(filter_controllers, "filterControllers"),
    )


def _rfc3339(moment: datetime) -> str:
    """Format an instant the way the allocation model formats its window bounds: RFC
    3339, UTC."""
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_allocation(
    start: datetime, end: datetime, days: int, cluster: str, key: str
) -> dict[str, Any]:
    """The Kubecost allocation object for the window that runs from ``start`` to ``end``.

    ``days`` is the length of that window in days: one for a daily set, the length of the
    whole request for an accumulated one. ``cluster`` is the **name** of the cluster the
    request selected, and ``key`` is the key the aggregation files the allocation under.

    The object carries the figures the estate has (the same ones the OpenCost plane
    costs) plus the four **averages** the Model API publishes and the OpenCost one does
    not (F15): the CPU and the memory, as a request and as a usage. The estate declares
    that the request **is** the usage -- the pod asks for two cores and four gibibytes
    and the Prometheus plane measures exactly that figure (see
    :mod:`k8s_sim.projections.prometheus`) -- so the two averages carry the same number.

    It does **not** carry ``minutes``: the Model API's ``Allocation`` schema has no such
    field (F15), and it does not carry ``memCost``: the field the consumer reads does not
    exist in the Kubecost model (F16).
    """
    figures = allocation.figures(days)

    result: dict[str, Any] = {
        "name": key,
        "properties": {
            "cluster": cluster,
            "namespace": allocation.NAMESPACE,
            "controller": allocation.CONTROLLER,
        },
        "window": {"start": _rfc3339(start), "end": _rfc3339(end)},
        "start": _rfc3339(start),
        "end": _rfc3339(end),
        "cpuCoreRequestAverage": figures["cpuCores"],
        "cpuCoreUsageAverage": figures["cpuCores"],
        "ramByteRequestAverage": figures["ramBytes"],
        "ramByteUsageAverage": figures["ramBytes"],
    }
    result.update(figures)
    return result


def allocation_sets(
    start: date,
    end: date,
    accumulate: str = allocation.ACCUMULATE_NONE,
    aggregate: str = allocation.DEFAULT_AGGREGATE,
    alloc_filter: allocation.AllocationFilter | None = None,
) -> list[dict[str, Any]]:
    """The allocation sets for the window that runs from ``start`` to ``end``.

    The Model API's ``data`` is a list of sets, each a map from the allocation key to
    the allocation (F15) -- the same shape the OpenCost plane answers with.

    ``accumulate`` is the resolved option (see
    :func:`k8s_sim.projections.allocation.resolve_accumulate`):

    - ``ACCUMULATE_ALL`` -- the whole window in **one** set, with the costs summed.
    - ``ACCUMULATE_DAY`` and ``ACCUMULATE_NONE`` -- one set per day, which is the step
      the consumer asks for when it sends ``step=1d``.

    A request that selects no cluster -- because it named one the estate does not have,
    or because it named a namespace or controller this estate does not carry -- gets
    **no set at all**: an empty list. The answer does not invent a cluster.
    """
    alloc_filter = alloc_filter or allocation.AllocationFilter()

    cluster = allocation.resolve_cluster(alloc_filter)
    if cluster is None or not alloc_filter.matches_workload():
        return []

    key = allocation.allocation_key(aggregate, cluster)

    if accumulate == allocation.ACCUMULATE_ALL:
        window_start = datetime(start.year, start.month, start.day, tzinfo=UTC)
        window_end = datetime(end.year, end.month, end.day, tzinfo=UTC) + timedelta(days=1)
        days = (end - start).days + 1
        return [{key: build_allocation(window_start, window_end, days, cluster, key)}]

    sets: list[dict[str, Any]] = []
    day = start
    while day <= end:
        day_start = datetime(day.year, day.month, day.day, tzinfo=UTC)
        day_end = day_start + timedelta(days=1)
        sets.append({key: build_allocation(day_start, day_end, 1, cluster, key)})
        day += timedelta(days=1)
    return sets
