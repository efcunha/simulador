"""Azure Monitor metrics projection (design §5).

Projects ``estate.metrics`` into Azure Monitor ``metrics`` series and
``metricDefinitions`` rows. Both are native cloud INPUTS (the raw timeseries Monitor
returns, and the metric catalogue it advertises); FinOps computes
utilization/idle verdicts from these (P1).

The ``metricDefinitions`` wire contract is verified against the installed
``azure-mgmt-monitor`` 7.0.0 deserializer rather than assumed: the operation
deserializes as ``MetricDefinitionCollection`` (``{"value": [...]}``), each row as
``MetricDefinition`` with ``name`` a ``LocalizableString``
(``{"value","localizedValue"}``) and ``unit``/``primaryAggregationType`` camelCase.

**``resourceId`` is the resource's ARM id, and that is the point of this module.** Monitor
does not identify a series by a name: it names the resource the samples are attributed to,
and the value it returns is the ARM id — the string the resource-plane projection published
for that resource (``projections/arm.resource_id_for``), carrying the subscription GUID, the
resource group and the resource's own type. So a caller that reads ``vm.id`` from
``virtualMachines.list_all`` and asks Monitor about it resolves the series that belongs to
that VM; while this projection answered the estate's uuid instead, the two calls named the
same resource two ways and every correlation through the metric row missed. The MAPPING is
also why a ``resource_name`` cannot serve here: the estate reuses names across
subscriptions, so a name-keyed row would be a row several resources claim.

A series whose resource type this package serves no ARM path for is reported under the
estate's own uuid: that id is unique but not ARM-shaped (``arm.resource_id_for`` documents
which types those are), and no resource-plane projection publishes a rival value for it.

TODO-verificar §11.11: the exact Monitor ``metrics`` response envelope
(``value[].timeseries[].data[]`` nesting, ``timeStamp``/``average`` key casing,
``unit`` vocabulary) is NOT offline-verifiable. Series are emitted official-shaped
and flagged.
"""

from __future__ import annotations

from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.metrics import MetricSeries

from azure_sim.projections import arm, scope

#: Synthetic metric presentation. The canonical estate meters two metric names
#: (``cpu_utilization`` and ``memory_utilization``, see
#: ``generate/estate_builder._build_metrics``); only the first belongs to a type this
#: provider owns, because the memory series is metered for the AWS ``ec2_instance`` that
#: the rightsizing consumer asks memory about. This table therefore carries that one
#: entry plus a documented fallback. The display name and unit are the only authored
#: values in this projection and are recorded in
#: ``docs/synthetic-clouds/UNVERIFIED.md``.
#:
#: Cadence: the estate samples every series HOURLY (24 points per day —
#: ``estate_builder._METRIC_HOURS_PER_DAY``). This projection aggregates nothing, it
#: forwards every point it is handed, so Monitor answers with one datapoint per hour and
#: a caller's own bucketing decides the resolution it reads.
_METRIC_PRESENTATION: dict[str, tuple[str, str]] = {
    "cpu_utilization": ("CPU utilization", "Percent"),
}
_DEFAULT_UNIT = "Count"
_AGGREGATION = "Average"
_TIME_GRAIN = "PT5M"
_RETENTION = "P30D"


def _presentation(metric_name: str) -> tuple[str, str]:
    """Return ``(localized display name, unit)`` for a metric name."""
    return _METRIC_PRESENTATION.get(
        metric_name,
        (metric_name.replace("_", " ").capitalize(), _DEFAULT_UNIT),
    )


def _azure_metric_series(estate: CanonicalEstate) -> tuple[MetricSeries, ...]:
    """Metric series belonging to this provider's resources (``projections/scope.py``)."""
    return scope.metric_series(estate)


def resource_id(estate: CanonicalEstate, series: MetricSeries) -> str:
    """The Monitor ``resourceId`` of a series: the measured resource's ARM id.

    ``arm.resource_id_of_uuid`` resolves the series' ``resource_uuid`` to the id the
    resource-plane projection of the same resource publishes, so the metric row and the
    resource row name one resource; a resource type with no ARM path keeps the estate's uuid,
    which no other projection contradicts.
    """
    return arm.resource_id_of_uuid(estate, series.resource_uuid) or series.resource_uuid


def _series_row(estate: CanonicalEstate, series: MetricSeries) -> dict[str, object]:
    """Project one metric series into a Monitor ``value[]`` entry."""
    # TODO-verificar §11.11: official Monitor metrics envelope nesting/casing.
    data = [
        {"timeStamp": point.ts.isoformat(), "average": point.value}
        for point in series.points
    ]
    return {
        "name": {"value": series.metric_name},
        "resourceId": resource_id(estate, series),
        "timeseries": [{"data": data}],
    }


def project_metrics(estate: CanonicalEstate) -> list[dict[str, object]]:
    """Return Monitor ``value[]`` metric series for THIS provider, ordered."""
    rows = [_series_row(estate, series) for series in scope.metric_series(estate)]
    return sorted(rows, key=lambda row: (str(row["resourceId"]), str(row["name"])))


def _definition_row(estate: CanonicalEstate, series: MetricSeries) -> dict[str, object]:
    """Project one metric series into a Monitor ``MetricDefinition`` row."""
    display_name, unit = _presentation(series.metric_name)
    return {
        "resourceId": resource_id(estate, series),
        "name": {"value": series.metric_name, "localizedValue": display_name},
        "unit": unit,
        "primaryAggregationType": _AGGREGATION,
        "supportedAggregationTypes": [_AGGREGATION],
        "metricAvailabilities": [{"timeGrain": _TIME_GRAIN, "retention": _RETENTION}],
        "dimensions": [],
    }


def project_metric_definitions(estate: CanonicalEstate) -> list[dict[str, object]]:
    """Return Monitor ``metricDefinitions`` rows for Azure resources, ordered by id."""
    rows = [_definition_row(estate, series) for series in _azure_metric_series(estate)]
    return sorted(rows, key=lambda row: (str(row["resourceId"]), str(row["name"])))
