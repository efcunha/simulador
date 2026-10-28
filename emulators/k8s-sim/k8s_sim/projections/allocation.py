"""The OpenCost allocation projection: one synthetic workload, costed per day, in any
cluster of the estate.

This is the only place in k8s-sim that knows what the synthetic estate *is*. The HTTP
layer in :mod:`k8s_sim.app` parses the query string and hands the window over; this
module turns the window into allocation sets.

Three rules shape what comes out:

**Nothing is invented at request time.** The workload, its usage and its prices are
declared here as constants and the payload is a pure function of the requested window.
No clock is read, no price list is fetched, no database is opened. That is what makes
two identical calls return identical bytes -- and it is also why the numbers below are
SYNTHETIC: they are a made-up rate card for a made-up cluster, they are not AKS prices,
and they do not reconcile with any billing line. Reconciling them is S4b's job.

**The clusters are data, not code.** The estate's 309 Kubernetes clusters live in the
versioned fixture ``k8s_sim/fixtures/clusters.json``, derived from the estate by
``scripts/export_clusters.py``. The service reads that file; it never imports the
generator, and it never invents a cluster that is not in the file.

**The cluster's identity is its NAME.** The CloudPilot discovery returns the estate's
``resource_name`` and the consumer sends it back as ``filter=cluster:"<name>"``, so the
name is what the filter selects, what ``properties.cluster`` carries and what
``aggregate=cluster`` keys by. The estate's canonical ``uuid`` is kept in the fixture as
the auxiliary ``cluster_id`` and is accepted as an **alias** of the name in the filter --
an alias is accepted, never published: the payload always carries the name.

**The field names are OpenCost's, not this project's.** They were read from the
official sources cited in ``docs/k8s-sim-opencost-contract.md``: the envelope from
``core/pkg/protocol/http.go`` (``HTTPResponse``), the allocation fields from
``core/pkg/opencost/allocation_json.go`` (``AllocationJSON``), the property names from
``core/pkg/opencost/allocationprops.go`` (``AllocationProperties``) and the key rule
from ``AllocationProperties.GenerateKey``, which joins the aggregated property values
with "/". The key holds **the aggregated properties only**: ``aggregate=namespace``
keys by the namespace, ``aggregate=namespace,controller`` keys by ``payments/api``,
``aggregate=controller`` keys by the controller and ``aggregate=cluster`` keys by the
cluster.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

#: The cluster served when the request names no cluster of the estate. It is the
#: synthetic cluster of the previous phase (S4a) and it is **not** one of the estate's
#: clusters: the fixture is the catalog of the estate, and a request that wants an
#: estate cluster has to name it in the ``filter``.
CLUSTER = "aks-synthetic-01"

#: The namespace the workload lives in.
NAMESPACE = "payments"

#: The workload inside the namespace.
CONTROLLER = "api"

#: The aggregations this phase serves. ``aggregate=namespace,controller`` is what the
#: CloudPilot provider asks for; ``aggregate=cluster`` is what its connection test
#: asks for; ``aggregate=namespace`` and ``aggregate=controller`` are what its
#: namespace and workload lookups ask for.
SUPPORTED_AGGREGATES: tuple[str, ...] = (
    "namespace",
    "namespace,controller",
    "controller",
    "cluster",
)

#: The aggregation served when the parameter is absent.
DEFAULT_AGGREGATE = "namespace"

#: The step this phase serves. The provider sends ``step=1d``; any other step is
#: refused rather than approximated.
SUPPORTED_STEP = "1d"

#: The keys the ``filter`` parameter may use. The OpenCost filter language is much
#: wider than this; the terms this phase does not read are refused, never ignored
#: (see :func:`parse_filter`).
SUPPORTED_FILTER_KEYS: tuple[str, ...] = ("cluster", "namespace", "controller")

#: The versioned catalog of the estate's Kubernetes clusters. It is DATA: the
#: generator is a development-time tool and is not a dependency of the service.
FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "clusters.json"

#: The accumulation options this phase distinguishes, mirroring the official
#: ``AccumulateOption`` (``core/pkg/opencost/query.go:47-57``).
ACCUMULATE_NONE = "none"
ACCUMULATE_DAY = "day"
ACCUMULATE_ALL = "all"

#: The spellings Go's ``strconv.ParseBool`` reads as true
#: (``core/pkg/util/mapper/mapper.go:411-419``). The official handler falls back to
#: the boolean reading when the ``accumulate`` value is not one of the named
#: options.
_BOOL_TRUE = frozenset({"1", "t", "T", "TRUE", "true", "True"})

#: One gibibyte, the unit the synthetic usage below is expressed in.
_GIB = 1024**3

#: The synthetic usage of the workload over one day.
_CPU_CORES = Decimal("2")
_RAM_GIB = Decimal("4")
_PV_GIB = Decimal("20")
_NETWORK_GIB = Decimal("50")

#: The synthetic rate card. These are NOT Azure Retail Prices and NOT a price list:
#: they are round numbers chosen so the arithmetic in the documentation can be checked
#: by hand, and they are declared here so the cost of the estate is auditable.
_CPU_PRICE_PER_CORE_HOUR = Decimal("0.04")
_RAM_PRICE_PER_GIB_HOUR = Decimal("0.006")
_PV_PRICE_PER_GIB_HOUR = Decimal("0.0008")
_NETWORK_PRICE_PER_GIB = Decimal("0.02")

#: The length of one allocation set.
_HOURS_PER_DAY = Decimal("24")

#: A date in the format this phase reads. ``date.fromisoformat`` alone is too
#: permissive on Python 3.11+ (it also accepts the basic ``20261001`` form), so the
#: shape is checked before the value is parsed.
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

#: One filter term: a key, a colon and a quoted value.
_FILTER_TERM = re.compile(r'^(?P<key>[A-Za-z_][A-Za-z0-9_]*):"(?P<value>[^"]+)"$')


class WindowError(ValueError):
    """The ``window`` parameter is not a pair of dates this phase can read."""


class FilterError(ValueError):
    """The ``filter`` parameter is not a filter this phase can honour."""


@dataclass(frozen=True)
class AllocationFilter:
    """The filter terms this phase reads, one per supported key.

    A term that is absent is not a constraint: ``None`` means "the request did not
    say", which is different from "the request said something that does not match".

    The ``cluster`` term is kept **as written** -- the name the discovery returns, or
    the estate's canonical id used as an alias. Resolving it is
    :func:`resolve_cluster_name`'s job, not the parser's.
    """

    cluster: str | None = None
    namespace: str | None = None
    controller: str | None = None

    def matches_workload(self) -> bool:
        """Whether the synthetic workload satisfies the namespace and controller terms.

        The estate models ONE workload -- ``payments/api`` -- and it lives in every
        cluster of the estate. A filter that names another namespace or another
        controller therefore names something that does not exist here, and the answer
        is an empty one.
        """
        if self.namespace is not None and self.namespace != NAMESPACE:
            return False
        return not (self.controller is not None and self.controller != CONTROLLER)


@lru_cache(maxsize=1)
def estate_clusters() -> dict[str, dict[str, str]]:
    """The estate's Kubernetes clusters, read from the versioned fixture.

    The fixture is the catalog of the estate's 309 clusters (75 EKS, 111 GKE, 123
    AKS), derived from the canonical ``resources.parquet`` by
    ``scripts/export_clusters.py``. It is read once and cached: the answer of the
    service must be a pure function of the request, and a file read on every request
    would make it depend on the file system as well.

    The index is keyed by the ``cluster_id`` -- the estate's canonical ``uuid`` --
    because that is the one identity that is unique across the estate. Every cluster
    of the estate is kept, including the ones that share a name.

    :raises FileNotFoundError: when the fixture is missing -- a deployment error, and
        it must not be papered over with an empty catalog.
    """
    records = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return {record["cluster_id"]: record for record in records}


@lru_cache(maxsize=1)
def estate_clusters_by_name() -> dict[str, dict[str, str]]:
    """The estate's clusters, indexed by the name the discovery returns.

    The name is the contract's identity, and the estate **reuses names across
    scopes**: the 309 clusters carry 160 distinct names (measured on the canonical
    estate of 2026-10-28), so a name is unique within a scope, not across the
    estate. The index therefore keeps the first record of each name -- the catalog is
    sorted deterministically, so "first" is well defined -- and the payload publishes
    the name, which is the same for every cluster that shares it.
    """
    index: dict[str, dict[str, str]] = {}
    for record in estate_clusters().values():
        index.setdefault(record["cluster_name"], record)
    return index


def resolve_cluster_name(term: str) -> str | None:
    """The name of the cluster a filter term names, or ``None``.

    The term is read as the **name** first -- that is the identity the consumer
    sends -- and as the estate's canonical ``cluster_id`` second, where it is an
    accepted **alias**. An alias is only ever accepted: the answer carries the name,
    so a request answered through the alias is indistinguishable from one answered
    through the name.

    A term that is neither names no cluster of the estate: the request selected nothing.
    """
    record = estate_clusters_by_name().get(term)
    if record is not None:
        return record["cluster_name"]

    record = estate_clusters().get(term)
    if record is not None:
        return record["cluster_name"]

    return None


def parse_filter(raw: str | None) -> AllocationFilter:
    """Parse the ``filter`` parameter into the terms this phase reads.

    The shape is the one the CloudPilot provider sends: terms written as
    ``key:"value"`` and joined with ``+`` -- ``cluster:"<name>"+namespace:"<ns>"``.

    Only ``cluster``, ``namespace`` and ``controller`` are read. A term this phase
    cannot honour is **refused**, not ignored: answering a filtered request with an
    unfiltered answer would be a lie about what was served, and the simulator does not
    lie about what it answered. The same goes for a term that is not written as
    ``key:"value"``.

    :raises FilterError: when the filter is malformed, names an unsupported key, or
        repeats a key.
    """
    if raw is None:
        return AllocationFilter()

    text = raw.strip()
    if not text:
        return AllocationFilter()

    values: dict[str, str] = {}
    for term in text.split("+"):
        piece = term.strip()
        match = _FILTER_TERM.match(piece)
        if match is None:
            raise FilterError(f"{piece!r} is not a filter term written as key:\"value\"")

        key = match.group("key")
        value = match.group("value")
        if key not in SUPPORTED_FILTER_KEYS:
            raise FilterError(
                f"{key!r} is not a filter this phase reads "
                f"(it reads: {', '.join(SUPPORTED_FILTER_KEYS)})"
            )
        if key in values:
            raise FilterError(f"{key!r} was given twice")
        values[key] = value

    return AllocationFilter(
        cluster=values.get("cluster"),
        namespace=values.get("namespace"),
        controller=values.get("controller"),
    )


def resolve_cluster(alloc_filter: AllocationFilter) -> str | None:
    """The cluster the request selects, **by name**.

    A request that names no cluster gets the synthetic default cluster. A request
    that names a cluster of the estate -- by its name, or by the canonical id used
    as an alias -- gets that cluster's **name**. A request that names a cluster the
    estate does not have selects **nothing**: the answer is an empty one, never a
    made-up cluster.

    :returns: the cluster's name, or ``None`` when the request selects no cluster.
    """
    if alloc_filter.cluster is None:
        return CLUSTER
    return resolve_cluster_name(alloc_filter.cluster)


def allocation_key(aggregate: str, cluster: str) -> str:
    """The key the allocation is filed under.

    The rule is the official one (``AllocationProperties.GenerateKey``,
    ``core/pkg/opencost/allocationprops.go:361``): the key holds **the aggregated
    properties only**, joined by ``"/"``. The controller enters the key when the
    aggregation asks for it -- not because the allocation has it -- so
    ``aggregate=namespace`` keys by ``payments`` and ``aggregate=namespace,controller``
    keys by ``payments/api``.

    ``aggregate=cluster`` keys by the cluster's **name** -- the identity the consumer
    sends and the one the estate carries.

    The ``controllerKind`` does not prefix the controller here: the synthetic
    allocation has no ``controllerKind``, and the official key only carries it when
    the allocation has one.
    """
    if aggregate == "namespace":
        return NAMESPACE
    if aggregate == "namespace,controller":
        return f"{NAMESPACE}/{CONTROLLER}"
    if aggregate == "controller":
        return CONTROLLER
    return cluster


def parse_window(raw: str) -> tuple[date, date]:
    """Parse ``YYYY-MM-DD,YYYY-MM-DD`` into its two bounds.

    The OpenCost contract accepts far more spellings of ``window`` (words like
    ``today``, durations like ``7d``, RFC 3339 pairs and Unix timestamps); this phase
    reads exactly one of them, and refuses the rest instead of guessing what was meant.

    :raises WindowError: when the pair is malformed, when a bound is not a real date,
        or when the end precedes the start.
    """
    parts = raw.split(",")
    if len(parts) != 2:
        raise WindowError("expected two comma-separated dates as YYYY-MM-DD,YYYY-MM-DD")

    bounds: list[date] = []
    for part in parts:
        text = part.strip()
        if not _ISO_DATE.match(text):
            raise WindowError(f"{text!r} is not a date written as YYYY-MM-DD")
        try:
            bounds.append(date.fromisoformat(text))
        except ValueError as exc:
            raise WindowError(f"{text!r} is not a real date: {exc}") from exc

    start, end = bounds
    if end < start:
        raise WindowError("the end date is before the start date")
    return start, end


def resolve_accumulate(raw: str | None) -> str:
    """Resolve the ``accumulate`` parameter the way the official handler does.

    The official handler resolves it in three steps (``resolveAccumulateFromQuery``,
    ``pkg/costmodel/aggregation.go:84-96``): the literal ``all`` (case-insensitive)
    means the whole window; the named options are read by ``ParseAccumulate``
    (``core/pkg/opencost/query.go:60-79``); and whatever is left falls back to the
    boolean reading, where any value Go's ``strconv.ParseBool`` accepts as true also
    means the whole window.

    The official handler never refuses an ``accumulate`` value, and neither does this
    one. What each option means for the payload is in :func:`allocation_sets`.
    """
    raw = raw or ""
    text = raw.strip()
    if not text:
        return ACCUMULATE_NONE

    lowered = text.lower()
    if lowered in ("all", "true"):
        return ACCUMULATE_ALL
    if lowered == "day":
        return ACCUMULATE_DAY

    # Everything else falls back to the boolean reading. The official handler reads the
    # RAW value there (``qp.GetBool``), not the trimmed one, so this does too.
    if raw in _BOOL_TRUE:
        return ACCUMULATE_ALL
    return ACCUMULATE_NONE


def _rfc3339(moment: datetime) -> str:
    """Format an instant the way OpenCost formats its window bounds: RFC 3339, UTC."""
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def figures(days: int) -> dict[str, Any]:
    """The workload's usage over ``days`` days and the cost that usage carries.

    The costs are computed in ``Decimal`` so the declared rate card produces exact
    decimal amounts (1.92, 0.576, 0.384, 1.00 per day), and the total is then summed
    **on the floats that go on the wire**, in the order the contract names the
    components. The identity ``totalCost == cpuCost + ramCost + pvCost + networkCost``
    therefore holds to the bit, not merely to the penny.

    ``cpuCores``, ``ramBytes`` and ``pvBytes`` are **not** scaled with the days. The
    official allocation derives them from the summed hours divided by the summed
    minutes (``Allocation.CPUCores``, ``core/pkg/opencost/allocation.go:1109``), so a
    workload whose daily use does not change keeps the same figures when the window
    is accumulated.
    """
    day_count = Decimal(days)
    cpu_core_hours = _CPU_CORES * _HOURS_PER_DAY * day_count
    ram_byte_hours = _RAM_GIB * _GIB * _HOURS_PER_DAY * day_count
    pv_byte_hours = _PV_GIB * _GIB * _HOURS_PER_DAY * day_count
    network_transfer_bytes = _NETWORK_GIB * _GIB * day_count

    result: dict[str, Any] = {
        "cpuCores": float(_CPU_CORES),
        "cpuCoreHours": float(cpu_core_hours),
        "ramBytes": float(_RAM_GIB * _GIB),
        "ramByteHours": float(ram_byte_hours),
        "pvBytes": float(_PV_GIB * _GIB),
        "pvByteHours": float(pv_byte_hours),
        "networkTransferBytes": float(network_transfer_bytes),
        "cpuCost": float(cpu_core_hours * _CPU_PRICE_PER_CORE_HOUR),
        "ramCost": float(_RAM_GIB * _HOURS_PER_DAY * day_count * _RAM_PRICE_PER_GIB_HOUR),
        "pvCost": float(_PV_GIB * _HOURS_PER_DAY * day_count * _PV_PRICE_PER_GIB_HOUR),
        "networkCost": float(_NETWORK_GIB * day_count * _NETWORK_PRICE_PER_GIB),
    }
    result["totalCost"] = (
        result["cpuCost"] + result["ramCost"] + result["pvCost"] + result["networkCost"]
    )
    return result


def build_allocation(
    start: datetime, end: datetime, days: int, cluster: str, key: str
) -> dict[str, Any]:
    """The OpenCost allocation object for the window that runs from ``start`` to ``end``.

    ``days`` is the length of that window in days: one for a daily set, the length of
    the whole request for an accumulated one. ``cluster`` is the **name** of the cluster
    the request selected, and ``key`` is the key the aggregation files the allocation
    under.
    """
    allocation: dict[str, Any] = {
        "name": key,
        "properties": {
            "cluster": cluster,
            "namespace": NAMESPACE,
            "controller": CONTROLLER,
        },
        "window": {"start": _rfc3339(start), "end": _rfc3339(end)},
        "start": _rfc3339(start),
        "end": _rfc3339(end),
        "minutes": float(_HOURS_PER_DAY * 60 * days),
    }
    allocation.update(figures(days))
    return allocation


def allocation_sets(
    start: date,
    end: date,
    accumulate: str = ACCUMULATE_NONE,
    aggregate: str = DEFAULT_AGGREGATE,
    alloc_filter: AllocationFilter | None = None,
) -> list[dict[str, Any]]:
    """The allocation sets for the window that runs from ``start`` to ``end``.

    OpenCost's ``data`` is a LIST of sets -- one per ``step`` -- and each set is a map
    from the allocation key to the allocation. This phase's step is one day.

    ``accumulate`` is the resolved option (see :func:`resolve_accumulate`):

    - ``ACCUMULATE_ALL`` -- the whole window in **one** set, with the costs summed.
      This is what the official handler does with ``accumulate=true``: the step
      becomes the whole window (``resolveDefaultStepFromAccumulate``,
      ``pkg/costmodel/aggregation.go:135-136``) and the sets are merged into a single
      one (``AllocationSetRange.accumulateByAll``,
      ``core/pkg/opencost/allocation.go:3330``).
    - ``ACCUMULATE_DAY`` and ``ACCUMULATE_NONE`` -- one set per day, which is the step
      this phase already fixed.

    A request that selects no cluster -- because it named one the estate does not
    have, or because it named a namespace or controller this estate does not carry --
    gets **no set at all**: an empty list. The answer does not invent a cluster.
    """
    alloc_filter = alloc_filter or AllocationFilter()

    cluster = resolve_cluster(alloc_filter)
    if cluster is None or not alloc_filter.matches_workload():
        return []

    key = allocation_key(aggregate, cluster)

    if accumulate == ACCUMULATE_ALL:
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
