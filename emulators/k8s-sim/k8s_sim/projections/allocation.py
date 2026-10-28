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
with "/".
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
#: values with "/"; this estate has exactly one workload, so the key names it as
#: ``namespace/controller``. The stock key for the ``namespace`` aggregation alone
#: would be ``namespace`` -- see the "Deliberate deviations" section of
#: ``docs/k8s-sim-opencost-contract.md``.
WORKLOAD_KEY = f"{NAMESPACE}/{CONTROLLER}"

#: The only aggregation this phase serves.
SUPPORTED_AGGREGATE = "namespace"

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


def _rfc3339(moment: datetime) -> str:
    """Format an instant the way OpenCost formats its window bounds: RFC 3339, UTC."""
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def daily_figures() -> dict[str, Any]:
    """The workload's usage over one day and the cost that usage carries.

    The costs are computed in ``Decimal`` so the declared rate card produces exact
    decimal amounts (1.92, 0.576, 0.384, 1.00), and the total is then summed **on the
    floats that go on the wire**, in the order the contract names the components. The
    identity ``totalCost == cpuCost + ramCost + pvCost + networkCost`` therefore holds
    to the bit, not merely to the penny.
    """
    cpu_core_hours = _CPU_CORES * _HOURS_PER_DAY
    ram_byte_hours = _RAM_GIB * _GIB * _HOURS_PER_DAY
    pv_byte_hours = _PV_GIB * _GIB * _HOURS_PER_DAY
    network_transfer_bytes = _NETWORK_GIB * _GIB

    figures: dict[str, Any] = {
        "cpuCores": float(_CPU_CORES),
        "cpuCoreHours": float(cpu_core_hours),
        "ramBytes": float(_RAM_GIB * _GIB),
        "ramByteHours": float(ram_byte_hours),
        "pvBytes": float(_PV_GIB * _GIB),
        "pvByteHours": float(pv_byte_hours),
        "networkTransferBytes": float(network_transfer_bytes),
        "cpuCost": float(cpu_core_hours * _CPU_PRICE_PER_CORE_HOUR),
        "ramCost": float(_RAM_GIB * _HOURS_PER_DAY * _RAM_PRICE_PER_GIB_HOUR),
        "pvCost": float(_PV_GIB * _HOURS_PER_DAY * _PV_PRICE_PER_GIB_HOUR),
        "networkCost": float(_NETWORK_GIB * _NETWORK_PRICE_PER_GIB),
    }
    figures["totalCost"] = (
        figures["cpuCost"] + figures["ramCost"] + figures["pvCost"] + figures["networkCost"]
    )
    return figures


def build_allocation(day: date) -> dict[str, Any]:
    """The OpenCost allocation object for the single workload on ``day``."""
    start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    end = start + timedelta(days=1)

    allocation: dict[str, Any] = {
        "name": WORKLOAD_KEY,
        "properties": {
            "cluster": CLUSTER,
            "namespace": NAMESPACE,
            "controller": CONTROLLER,
        },
        "window": {"start": _rfc3339(start), "end": _rfc3339(end)},
        "start": _rfc3339(start),
        "end": _rfc3339(end),
        "minutes": float(_HOURS_PER_DAY * 60),
    }
    allocation.update(daily_figures())
    return allocation


def allocation_sets(start: date, end: date) -> list[dict[str, Any]]:
    """One allocation set per day between ``start`` and ``end``, both bounds included.

    OpenCost's ``data`` is a LIST of sets -- one per ``step`` -- and each set is a map
    from the allocation key to the allocation. This phase's step is one day.
    """
    sets: list[dict[str, Any]] = []
    day = start
    while day <= end:
        sets.append({WORKLOAD_KEY: build_allocation(day)})
        day += timedelta(days=1)
    return sets
