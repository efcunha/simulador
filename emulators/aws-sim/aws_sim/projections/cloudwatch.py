"""The CloudWatch projection: metrics and alarms read from the canonical estate.

**What the AWS slice of the estate carries, because it shapes this module.**
The generator meters six resource types (``tools/synthetic_clouds/generate/estate_builder.py``
``_build_metrics``): ``virtual_machine``, ``compute_instance``, ``cloud_sql`` and
``sql_database`` — Azure and GCP types — plus the two AWS types FinOps CloudWatch call
sites and this shim's namespace table agree on, ``ec2_instance`` and ``rds_instance``. The
AWS types carry CPU (``AWS/EC2`` / ``AWS/RDS``), and ``ec2_instance`` also carries memory,
because FinOps rightsizing provider cannot return a window at all without a memory
sample (``CWAgent`` — see :data:`_NAMESPACE`).

So on this estate :func:`metrics` lists those AWS series and :func:`metric_data` answers with
their values. A resource the estate does **not** meter still yields no row rather than a
fabricated ``CPUUtilization``: "absence is absence" holds, and the mapping below remains the
same slice in AWS's vocabulary, no wider.

**Where a value is derived, and from what.** Nothing here is random or clock-derived:

* A metric row is emitted for a series **only** if the estate carries it for a resource's
  uuid (:data:`_METRIC_NAME` maps the estate's metric vocabulary onto CloudWatch's). A
  resource with no series yields no row.
* The namespace and dimension name come from a closed map over the estate's own resource
  types and metric names (:data:`_NAMESPACE`), which are the generator's catalog — a pair
  with no entry reports nothing rather than a guessed namespace. The map is deliberately
  limited to the compute and managed-database families the estate meters in ``AWS/EC2``,
  ``AWS/RDS`` and ``CWAgent``: it is the same slice, in AWS's vocabulary, and no wider.
* The dimension **value** is the resource's own AWS id — the same value the resource's
  ``Describe*`` projection reports and its ARN ends in (``aws_sim.ids``). That is the
  identifier rule :mod:`aws_sim.projections.ec2` and :mod:`aws_sim.projections.rds` hold,
  so a metric read here names exactly the instance ``DescribeInstances`` reported and
  FinOps ``InstanceId`` correlation works across the two calls. It is **not** the
  estate's ``resource_name``: that value is reused across scopes (18 EC2 instances carry 11
  names in the small profile), so two different resources would resolve to one series and
  the rightsizing path would judge several instances on whichever samples matched first.
* Timestamps are the series' own point timestamps. The window the request names selects
  points; it never shifts or resamples them, and a point outside the window is not
  reported.
* The series is sampled **hourly** — one point per hour of every simulated day
  (``estate_builder._METRIC_HOURS_PER_DAY``) — because that is the grain FinOps
  right-sizing provider reads at: it queries with ``Period=3600`` and then prices the
  window in the same unit (``expected_samples = (end - start) // 3600``) against a
  coverage floor, so the buckets below come out one sample deep per hour and the sample
  count a caller derives from ``Values`` is a count of HOURS. This projection does not
  depend on the cadence — it buckets whatever the estate carries — which is exactly why
  the estate had to move to the consumer's grain rather than the reverse.

**Alarms are absent, by the estate's construction, not by omission.** The canonical model
carries no alarm entity at all: there is no ``Alarm`` in ``tools/synthetic_clouds/model``.
So :func:`alarms` answers ``[]``, and there is no field on an alarm this module could
honestly fill. A synthetic ``StateValue: "ALARM"`` row would hand
``aws_collector.py (modulo do consumidor)`` a health finding for an alarm nobody declared.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any

from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.resource import Resource

from aws_sim import ids, scope

#: estate ``(resource_type, metric_name)`` -> ``(CloudWatch namespace, dimension name)``.
#:
#: The AWS counterparts of the families the generator meters: compute instances and managed
#: SQL databases for CPU, plus the CloudWatch Agent namespace for an instance's memory. All
#: three halves are the CALLER's own vocabulary, read from the call sites rather than
#: guessed: ``CPUUtilization`` in ``AWS/EC2`` dimensioned by ``InstanceId`` and the RDS one
#: in ``AWS/RDS`` dimensioned by ``DBInstanceIdentifier`` are what
#: ``aws_metrics.py (modulo do consumidor)`` builds from the ``aws_ec2`` / ``aws_rds``
#: templates, and ``CWAgent`` + ``MemoryUtilization`` + ``InstanceId`` is the memory query
#: ``cloudwatch_metrics_provider.py (modulo do consumidor)`` sends beside its CPU one. The
#: key is the PAIR because the namespace is per metric, not per resource: one ``ec2_instance``
#: is metered on CPU in ``AWS/EC2`` and on memory in ``CWAgent``.
_NAMESPACE: dict[tuple[str, str], tuple[str, str]] = {
    ("ec2_instance", "cpu_utilization"): ("AWS/EC2", "InstanceId"),
    ("rds_instance", "cpu_utilization"): ("AWS/RDS", "DBInstanceIdentifier"),
    ("ec2_instance", "memory_utilization"): ("CWAgent", "InstanceId"),
}

#: estate ``metric_name`` -> its CloudWatch ``MetricName``. A metric the estate grows that
#: is not in this map is skipped rather than reported under a guessed name.
_METRIC_NAME: dict[str, str] = {
    "cpu_utilization": "CPUUtilization",
    "memory_utilization": "MemoryUtilization",
}

#: The statistics CloudWatch accepts by name. ``pNN`` is handled separately.
_NAMED_STATISTICS = ("Average", "Sum", "Minimum", "Maximum", "SampleCount")

#: ``GetMetricData`` reports this when a query was answered in full.
_STATUS_COMPLETE = "Complete"


def _identity(resource: Resource, metric_name: str) -> tuple[str, str, str] | None:
    """``(namespace, dimension_name, dimension_value)`` for a series, or ``None``.

    The dimension VALUE is the resource's AWS id (``aws_sim.ids.resource_id``) whichever
    namespace the metric belongs to, so a memory read names the same instance its CPU read
    and ``DescribeInstances`` do — and each instance gets its own series rather than sharing
    the first one its name matched.
    """
    entry = _NAMESPACE.get((resource.resource_type, metric_name))
    if entry is None:
        return None
    namespace, dimension_name = entry
    return namespace, dimension_name, ids.resource_id(resource)


def _series(estate: CanonicalEstate) -> list[tuple[str, str, str, str, tuple[Any, ...]]]:
    """Every metric row the estate supports, as ``(namespace, metric, dim, value, points)``.

    Sorted, so two calls about the same estate answer in the same order — the pagination
    ``list_metrics`` clients do would otherwise be non-deterministic.
    """
    index = scope.resource_index(estate)
    rows: list[tuple[str, str, str, str, tuple[Any, ...]]] = []
    for series in estate.metrics:
        resource = index.get(series.resource_uuid)
        if resource is None:
            continue  # a non-AWS (or unknown) resource's series is not this endpoint's
        metric_name = _METRIC_NAME.get(series.metric_name)
        if metric_name is None:
            continue
        identity = _identity(resource, series.metric_name)
        if identity is None:
            continue
        namespace, dimension_name, dimension_value = identity
        rows.append((namespace, metric_name, dimension_name, dimension_value, series.points))
    return sorted(rows, key=lambda row: (row[0], row[1], row[2], row[3]))


def _matches_dimensions(dimensions: Sequence[Mapping[str, Any]] | None, name: str, value: str) -> bool:
    """Whether a requested dimension filter names this row's single dimension.

    CloudWatch filters by the dimensions the caller names; the estate carries exactly one
    dimension per metric, so a filter naming a different dimension (or a different value)
    selects nothing.
    """
    if not dimensions:
        return True
    return all(
        str(dimension.get("Name")) == name and str(dimension.get("Value")) == value for dimension in dimensions
    )


def metrics(
    estate: CanonicalEstate,
    *,
    namespace: str | None = None,
    metric_name: str | None = None,
    dimensions: Sequence[Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """The ``ListMetrics`` rows the estate supports, filtered by the request."""
    rows: list[dict[str, Any]] = []
    for row_namespace, row_metric, dimension_name, dimension_value, _points in _series(estate):
        if namespace and row_namespace != namespace:
            continue
        if metric_name and row_metric != metric_name:
            continue
        if not _matches_dimensions(dimensions, dimension_name, dimension_value):
            continue
        rows.append(
            {
                "Namespace": row_namespace,
                "MetricName": row_metric,
                "Dimensions": [{"Name": dimension_name, "Value": dimension_value}],
            },
        )
    return rows


def alarms(estate: CanonicalEstate) -> list[dict[str, Any]]:
    """The ``DescribeAlarms`` rows: none, because the estate models no alarm."""
    _ = estate
    return []


def _percentile(values: Sequence[float], percentile: float) -> float:
    """The nearest-rank percentile of ``values``.

    CloudWatch does not publish its exact percentile algorithm, so this uses the standard
    nearest-rank definition rather than imitating a formula it never documented: sort, then
    take the ``ceil(p/100 * n)``-th value, clamped into range.
    """
    ordered = sorted(values)
    rank = math.ceil(percentile / 100 * len(ordered))
    index = min(max(rank, 1), len(ordered)) - 1
    return ordered[index]


def _statistic(values: Sequence[float], stat: str) -> float:
    """Compute one datapoint's statistic over a bucket's values."""
    if stat == "Sum":
        return math.fsum(values)
    if stat == "Minimum":
        return min(values)
    if stat == "Maximum":
        return max(values)
    if stat == "SampleCount":
        return float(len(values))
    if stat == "Average":
        return math.fsum(values) / len(values)
    if stat.startswith("p") and stat[1:].isdigit():
        return _percentile(values, float(stat[1:]))
    raise ValueError(f"Unsupported statistic: {stat!r}")


def _points_in_window(
    points: Sequence[Any],
    start: datetime,
    end: datetime,
) -> list[Any]:
    """The series' points inside ``[start, end)`` — CloudWatch's own half-open window."""
    return [point for point in points if start <= point.ts < end]


def _bucketed(
    points: Sequence[Any],
    start: datetime,
    period: int,
    stat: str,
) -> tuple[list[datetime], list[float]]:
    """Aggregate ``points`` into ``period``-second buckets anchored at ``start``.

    A bucket with no samples contributes neither a timestamp nor a value: absence is
    absence, so a gap stays a gap instead of becoming a fabricated zero.
    """
    buckets: dict[int, list[float]] = {}
    for point in points:
        offset = int((point.ts - start).total_seconds() // period)
        buckets.setdefault(offset, []).append(float(point.value))
    timestamps: list[datetime] = []
    values: list[float] = []
    for offset in sorted(buckets):
        timestamps.append(start + timedelta(seconds=offset * period))
        values.append(_statistic(buckets[offset], stat))
    return timestamps, values


def _metric_for_series(
    estate: CanonicalEstate,
    metric: Mapping[str, Any],
) -> tuple[Any, ...] | None:
    """The estate's series named by a ``MetricStat.Metric``, or ``None`` if it has none."""
    namespace = str(metric.get("Namespace") or "")
    metric_name = str(metric.get("MetricName") or "")
    dimensions = metric.get("Dimensions") or []
    for row_namespace, row_metric, dimension_name, dimension_value, points in _series(estate):
        if row_namespace != namespace or row_metric != metric_name:
            continue
        if not _matches_dimensions(dimensions, dimension_name, dimension_value):
            continue
        return points
    return None


def metric_data(
    estate: CanonicalEstate,
    *,
    queries: Sequence[Mapping[str, Any]],
    start: datetime,
    end: datetime,
) -> list[dict[str, Any]]:
    """The ``GetMetricData`` results for ``queries``, in request order.

    Every query yields a result row, because FinOps reads ``MetricDataResults`` by
    ``Id`` and a missing row is indistinguishable from a dropped request. A query that
    names a metric the estate does not carry yields a row with empty ``Values`` — the
    metric genuinely has no samples — whereas a query the emulator cannot evaluate at all
    (an ``Expression``, which needs a math evaluator this emulator does not have) is
    refused, so the caller sees a real error instead of a silent empty answer.
    """
    results: list[dict[str, Any]] = []
    for query in queries:
        query_id = str(query.get("Id") or "")
        metric_stat = query.get("MetricStat")
        if not isinstance(metric_stat, Mapping):
            raise ValueError(
                f"MetricDataQuery {query_id!r} carries no MetricStat. This simulator serves "
                "metric statistics only; math expressions are not evaluated.",
            )
        metric = metric_stat.get("Metric") or {}
        period = int(metric_stat.get("Period") or 60)
        stat = str(metric_stat.get("Stat") or "Average")
        requested_label = query.get("Label")
        points = _metric_for_series(estate, metric)
        timestamps: list[datetime] = []
        values: list[float] = []
        if points is not None:
            timestamps, values = _bucketed(_points_in_window(points, start, end), start, period, stat)
        label = str(requested_label) if requested_label else str(metric.get("MetricName") or "")
        results.append(
            {
                "Id": query_id,
                "Label": label,
                "Timestamps": timestamps,
                "Values": values,
                "StatusCode": _STATUS_COMPLETE,
            },
        )
    return results
