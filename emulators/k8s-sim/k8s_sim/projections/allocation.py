"""The OpenCost allocation projection: one synthetic AKS workload, costed per day.

This is the only place in k8s-sim that knows what the synthetic estate *is*. The HTTP
layer in :mod:`k8s_sim.app` parses the query string and hands the window over; this
module turns the window into allocation sets.

Two rules shape what comes out:

**Nothing is invented at request time.** The workload, its usage and its prices are
declared here as constants and the payload is a pure function of the requested window.
No clock is read, no price list is fetched, no database is opened. That is what makes
two identical calls return identical bytes -- and it is also why the numbers below are
SYNTHETIC: they are a made-up rate card for a made-up cluster, they are not AKS prices,
and they do not reconcile with any billing line. Reconciling them is S4b's job.

**The field names are OpenCost's, not this project's.** They were read from the
official sources cited in ``docs/k8s-sim-opencost-contract.md``: the envelope from
``core/pkg/protocol/http.go`` (``HTTPResponse``), the allocation fields from
``core/pkg/opencost/allocation_json.go`` (``AllocationJSON``), the property names from
``core/pkg/opencost/allocationprops.go`` (``AllocationProperties``) and the key rule
from ``AllocationProperties.GenerateKey``, which joins the aggregated property values
with "/". The key holds **the aggregated properties only**: this phase serves
``aggregate=namespace``, so the key is the namespace and the controller stays in
``properties``.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

#: The one cluster this simulator models.
CLUSTER = "aks-synthetic-01"

#: The namespace the workload lives in.
NAMESPACE = "payments"

#: The workload inside the namespace.
CONTROLLER = "api"

#: The allocation-set key. OpenCost builds it by joining the aggregated property
#: values with "/" (``AllocationProperties.GenerateKey``,
#: ``core/pkg/opencost/allocationprops.go:361``), and the key holds **the aggregated
#: properties only**. This phase serves ``aggregate=namespace``, and the namespace is
#: the only aggregated property, so the key is the namespace alone. The controller is
#: a property of the allocation, not part of the aggregation, so it stays in
#: ``properties``: the official ``aggregate=namespace`` produces ``payments``, not
#: ``payments/api``.
ALLOCATION_KEY = NAMESPACE

#: The only aggregation this phase serves.
SUPPORTED_AGGREGATE = "namespace"

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


class WindowError(ValueError):
    """The ``window`` parameter is not a pair of dates this phase can read."""


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


def build_allocation(start: datetime, end: datetime, days: int) -> dict[str, Any]:
    """The OpenCost allocation object for the window that runs from ``start`` to ``end``.

    ``days`` is the length of that window in days: one for a daily set, the length of
    the whole request for an accumulated one.
    """
    allocation: dict[str, Any] = {
        "name": ALLOCATION_KEY,
        "properties": {
            "cluster": CLUSTER,
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
    start: date, end: date, accumulate: str = ACCUMULATE_NONE
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
    """
    if accumulate == ACCUMULATE_ALL:
        window_start = datetime(start.year, start.month, start.day, tzinfo=UTC)
        window_end = datetime(end.year, end.month, end.day, tzinfo=UTC) + timedelta(days=1)
        days = (end - start).days + 1
        return [{ALLOCATION_KEY: build_allocation(window_start, window_end, days)}]

    sets: list[dict[str, Any]] = []
    day = start
    while day <= end:
        day_start = datetime(day.year, day.month, day.day, tzinfo=UTC)
        day_end = day_start + timedelta(days=1)
        sets.append({ALLOCATION_KEY: build_allocation(day_start, day_end, 1)})
        day += timedelta(days=1)
    return sets
