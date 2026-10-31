"""The Prometheus plane of the k8s-sim: the instant query the CloudPilot consumer
reads the estate's namespace telemetry from.

This is the third projection of the SAME synthetic estate.
:mod:`k8s_sim.projections.allocation` describes what the estate **costs** (the
OpenCost allocation contract), :mod:`k8s_sim.projections.kubernetes` describes what it
**contains** (the objects a Kubernetes API server would list), and this module
describes what it **measures** (the usage series a Prometheus would serve).

All three describe one estate, so their constants agree by construction: the
namespace here is the ``NAMESPACE`` of the allocation projection, and the usage here
is the usage the allocation projection costs and the Kubernetes projection declares
in the pod's ``requests``. The consumer sums the requests of the pods of a namespace
to obtain that namespace's usage and the OpenCost allocation costs the same figure,
so publishing another number here would make the simulator say three different
truths about the same cluster.

**What the consumer reads, and where that was measured.** The CloudPilot provider
``opencost`` (``backend/app/services/k8s_finops/providers/opencost.py``) resolves an
optional Prometheus endpoint -- ``config.prometheus_endpoint`` or the global
``settings.K8S_PROMETHEUS_URL`` -- and, when it is set, asks it for namespace-grain
CPU and memory telemetry:

* ``opencost.py:112-132`` -- the request is ``GET {endpoint}/api/v1/query`` with the
  query in the ``query`` parameter, **without any authentication header**; the answer
  must be JSON and must carry ``status == "success"``, or the provider raises and the
  telemetry is dropped.
* ``opencost.py:134-148`` -- the answer is read as ``data.result[]``, each entry
  carrying ``metric.namespace`` and ``value`` -- a two-element list whose second
  element is the number, parsed as a decimal and kept only when it is finite and
  not negative.
* ``opencost.py:150-184`` -- the two queries sent are

  ``sum by (namespace) (rate(container_cpu_usage_seconds_total{cluster="<id>",container!="",image!=""}[5m])) * 1000``

  and

  ``sum by (namespace) (container_memory_working_set_bytes{cluster="<id>",container!="",image!=""})``

  The ``cluster`` term carries the id the consumer holds for the cluster -- the
  **native id** the discovery publishes (the EKS ARN, the AKS ARM resource id and
  the GKE ``selfLink``), the same alias the OpenCost plane accepts (see
  :func:`k8s_sim.projections.allocation.resolve_cluster_name`).

The plane therefore serves **exactly these two queries**. A query the estate has no
series for is answered the way a Prometheus answers it -- ``200`` with an **empty
vector**, never an error: the estate publishes no series for it, and saying so is
true. The plane is not a PromQL engine and does not pretend to be one.

**The shape of the answer** is the Prometheus HTTP API's
(``https://prometheus.io/docs/prometheus/latest/querying/api/``): a success carries
``status`` plus ``data`` with ``resultType`` and ``result``, and each entry carries
``metric`` (the label set) and ``value`` (the ``[timestamp, "value"]`` pair). A
failure carries ``status: "error"``, ``errorType`` and ``error``, with the HTTP
status ``400``.

Two details of the official shape are worth stating, because they are easy to get
wrong and the consumer reads the payload:

* **The aggregation drops the metric name.** ``sum by (namespace)`` groups by the
  ``namespace`` label only, and Prometheus removes ``__name__`` from the result of an
  aggregation that does not group by it. The label set published here is therefore
  ``namespace`` and ``cluster`` -- and **no** ``__name__``.
* **The value is a string.** Prometheus marshals the sample value as text; the
  consumer parses it as a decimal.

**The cluster label carries the estate's published identity**, the cluster's
**name**, not the alias the query came in through -- the same rule the OpenCost
plane follows (the alias is accepted, the name is published).

**The evaluation timestamp is the wall clock**, as it is in a Prometheus: an instant
query is evaluated *now* unless it carries a ``time`` parameter. The estate's usage
is constant, so the *value* does not depend on the instant; only the stamp does.
This is the one place in the k8s-sim that reads a clock, and it is the only thing
the clock is used for.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from k8s_sim.projections import allocation, kubernetes

#: The CPU query the consumer sends. The shape is read literally: the estate
#: evaluates these two queries and answers another one with an empty vector.
_CPU_QUERY = re.compile(
    r"^sum\s+by\s*\(\s*namespace\s*\)\s*\(\s*rate\(\s*container_cpu_usage_seconds_total"
    r"\{(?P<selector>[^{}]*)\}\s*\[\s*5m\s*\]\s*\)\s*\)\s*\*\s*1000\s*$"
)

#: The memory query the consumer sends.
_MEMORY_QUERY = re.compile(
    r"^sum\s+by\s*\(\s*namespace\s*\)\s*\(\s*container_memory_working_set_bytes"
    r"\{(?P<selector>[^{}]*)\}\s*\)\s*$"
)

#: A label matcher's key.
_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

#: A label matcher's operator. The consumer sends only ``=`` and ``!=``.
_OPERATOR = re.compile(r"!=|=~|!~|=")

#: The metric name of the CPU series.
_CPU_METRIC = "cpu"

#: The metric name of the memory series.
_MEMORY_METRIC = "memory"

#: The namespace the estate carries -- the same one the allocation projection costs
#: and the Kubernetes projection publishes.
NAMESPACE = kubernetes.NAMESPACE

#: The estate's CPU usage in millicores -- what the consumer's CPU query asks for.
#: The pod requests two cores and the estate declares the request IS the usage, so
#: the namespace burns two cores; the query multiplies the rate by 1000, and the
#: provider reads the answer as ``cpu_usage_millicores``.
_CPU_MILLICORES = kubernetes.CPU_CORES * 1000

#: The estate's memory usage in bytes -- what the consumer's memory query asks for.
#: The pod requests 4Gi and the estate declares the request IS the usage.
_MEMORY_BYTES = kubernetes.MEMORY_BYTES


class QueryError(ValueError):
    """The request is not one a Prometheus can answer.

    The Prometheus HTTP API answers such a request with the HTTP status ``400`` and
    the error envelope (``status``, ``errorType``, ``error``).
    """


@dataclass(frozen=True)
class ParsedQuery:
    """A query this plane reads: the metric asked for and the cluster it names.

    The cluster is kept **as written** -- the name, the estate's canonical id or the
    native id the discovery publishes. Resolving it is :func:`resolve_cluster`'s
    job, not the parser's.
    """

    metric: str
    cluster: str


def _parse_selector(selector: str) -> list[tuple[str, str, str]] | None:
    """The label matchers of a selector, in order, or ``None`` when it is not one.

    A matcher is ``key<op>"value"``. The value may carry escaped quotes and
    backslashes -- that is how the consumer escapes a cluster id that contains them
    (``opencost.py:155``). A comma inside a quoted value is part of the value and
    not a separator, so the selector is scanned instead of split.

    ``None`` means the selector is not a list of matchers this plane reads.
    """
    terms: list[tuple[str, str, str]] = []
    index = 0
    length = len(selector)

    while index < length:
        key_match = _KEY.match(selector, index)
        if key_match is None:
            return None
        index = key_match.end()

        operator_match = _OPERATOR.match(selector, index)
        if operator_match is None:
            return None
        index = operator_match.end()

        if index >= length or selector[index] != '"':
            return None
        index += 1

        chunks: list[str] = []
        while index < length:
            char = selector[index]
            if char == "\\":
                index += 1
                if index >= length:
                    return None
                chunks.append(selector[index])
                index += 1
                continue
            if char == '"':
                index += 1
                break
            chunks.append(char)
            index += 1
        else:
            # The value is not terminated.
            return None

        terms.append((key_match.group(), operator_match.group(), "".join(chunks)))

        if index >= length:
            break
        if selector[index] != ",":
            return None
        index += 1
        if index >= length:
            # A trailing comma is not a list of matchers.
            return None

    return terms


def _cluster_term(selector: str) -> str | None:
    """The cluster a selector names, or ``None`` when the selector is not the one
    the consumer sends.

    The consumer's selector carries exactly three matchers: the cluster it asks
    about (``cluster="<id>"``) and the two emptiness matchers that keep the pods
    without a container or without an image out of the sum
    (``container!=""`` and ``image!=""``). A selector with another set of matchers
    selects series this estate does not publish, so it is answered with an empty
    vector.
    """
    terms = _parse_selector(selector)
    if terms is None:
        return None

    cluster: str | None = None
    for key, operator, value in terms:
        if key == "cluster" and operator == "=":
            if cluster is not None:
                return None
            cluster = value
        elif key == "container" and operator == "!=" and value == "":
            continue
        elif key == "image" and operator == "!=" and value == "":
            continue
        else:
            return None

    return cluster


def parse_query(query: str) -> ParsedQuery | None:
    """The query this plane reads, or ``None`` when the estate has no series for it.

    ``None`` is the honest answer for every query that is not one of the two the
    consumer sends: a Prometheus answers a query that selects nothing with an
    empty vector, and this plane never invents a series to fill one.
    """
    text = query.strip()

    cpu_match = _CPU_QUERY.match(text)
    if cpu_match is not None:
        cluster = _cluster_term(cpu_match.group("selector"))
        if cluster is None:
            return None
        return ParsedQuery(metric=_CPU_METRIC, cluster=cluster)

    memory_match = _MEMORY_QUERY.match(text)
    if memory_match is not None:
        cluster = _cluster_term(memory_match.group("selector"))
        if cluster is None:
            return None
        return ParsedQuery(metric=_MEMORY_METRIC, cluster=cluster)

    return None


def resolve_cluster(term: str) -> str | None:
    """The name of the cluster a query names, or ``None``.

    The term is read the way the OpenCost plane reads its ``filter``: the name
    first, then the estate's canonical ``cluster_id``, then the **native id** the
    discovery publishes. All three are accepted aliases and none of them is
    published -- the answer carries the **name**, the estate's published identity.

    A term that names no cluster of the estate selects nothing.
    """
    return allocation.resolve_cluster_name(term)


def _evaluation_time(raw: str | None) -> float:
    """The instant a query is evaluated at, in seconds since the epoch.

    A Prometheus evaluates an instant query *now*, unless the request carries a
    ``time`` parameter -- a unix timestamp or an RFC 3339 instant. A ``time`` this
    plane cannot read is refused, the way the Prometheus HTTP API refuses it.
    """
    if raw is None:
        return time.time()

    text = raw.strip()
    if not text:
        return time.time()

    try:
        return float(text)
    except ValueError:
        pass

    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise QueryError(f'invalid parameter "time": cannot parse "{text}" to a valid timestamp') from exc

    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.timestamp()


def _series(metric: str, cluster: str, evaluated_at: float) -> list[dict[str, Any]]:
    """The series the estate publishes for a query.

    One series: the estate carries one namespace, and the aggregation the consumer
    sends groups by it. The label set is ``namespace`` and ``cluster`` -- and no
    ``__name__``, because an aggregation that does not group by the metric name
    drops it.
    """
    value = _CPU_MILLICORES if metric == _CPU_METRIC else _MEMORY_BYTES
    return [
        {
            "metric": {"namespace": NAMESPACE, "cluster": cluster},
            "value": [evaluated_at, str(value)],
        }
    ]


def success(result: list[dict[str, Any]]) -> dict[str, Any]:
    """The success envelope of the Prometheus HTTP API."""
    return {"status": "success", "data": {"resultType": "vector", "result": result}}


def failure(message: str) -> dict[str, Any]:
    """The error envelope of the Prometheus HTTP API."""
    return {"status": "error", "errorType": "bad_data", "error": message}


def evaluate(query: str | None, time_param: str | None = None) -> dict[str, Any]:
    """The answer of an instant query over the estate.

    :raises QueryError: when the request carries no query or a ``time`` this plane
        cannot read -- the Prometheus HTTP API answers those with the HTTP status
        ``400`` and the error envelope.
    """
    if query is None or not query.strip():
        raise QueryError('invalid parameter "query": 1:1: parse error: no expression found in input')

    evaluated_at = _evaluation_time(time_param)

    parsed = parse_query(query)
    if parsed is None:
        return success([])

    cluster = resolve_cluster(parsed.cluster)
    if cluster is None:
        return success([])

    return success(_series(parsed.metric, cluster, evaluated_at))
