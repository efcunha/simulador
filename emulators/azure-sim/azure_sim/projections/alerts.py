"""Azure Monitor metric-alert projections: rules, and the incidents each one fired.

Both surfaces are **derived from the estate**, never authored:

* :func:`project_metric_alert_rules` emits one Metric Alerts rule per Azure resource
  the estate meters.
* :func:`project_alert_rule_incidents` computes that rule's firing history by
  comparing the *same* resource's metric series against the *same* threshold, so the
  alarm screen and the metric chart cannot disagree — an incident exists exactly when
  the estate's data says the threshold was crossed.

The threshold is the one thing the estate does not model (FinOps estate has no
operator-authored alert rules), so it is declared once, here, as synthetic
*configuration* rather than scattered through the projection. Its value and the
metric namespace question are recorded in ``docs/synthetic-clouds/UNVERIFIED.md``.

Wire contract, verified against the installed ``azure-mgmt-monitor`` 7.0.0
deserializer rather than assumed:

* ``metricAlerts`` deserializes as ``MetricAlertResourceCollection`` — ``{"value":
  [...]}`` — and ``MetricAlertResource._attribute_map`` flattens ``properties.*`` onto
  the model, so ``description``/``severity``/``enabled``/``scopes`` must be nested
  under ``properties`` to be readable as attributes.
* ``.../incidents`` deserializes as ``IncidentListResult``, whose items carry flat
  ``name``/``ruleName``/``isActive``/``activatedTime``/``resolvedTime`` keys.
* The caller extracts the resource group from the rule ``id``, so the id is emitted
  ARM-shaped with a ``/resourceGroups/<name>/`` segment, and its subscription segment is the
  GUID the resource-plane ids carry (``arm.subscription_id``) rather than the generator's
  scope label — otherwise the rule and the resource it watches would name two subscriptions.
* ``scopes`` is the watched resource's **ARM id** (``arm.resource_id_for``), the same value
  ``projections/metrics.py`` reports as ``resourceId`` and the resource plane publishes as a
  row's ``id``. A rule scoped to a name would watch every resource sharing it.
"""

from __future__ import annotations

from datetime import datetime

from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.metrics import MetricPoint, MetricSeries
from tools.synthetic_clouds.model.resource import Resource

from azure_sim.projections import arm, metrics, scope

#: Synthetic alerting configuration. The estate's ``cpu_utilization`` points are CPU
#: percentages on a 0..100 scale (the generator's workload bands) and ``project_metrics``
#: publishes them raw, so the threshold is expressed on that same scale. Declared, not
#: derived: nothing in the canonical model represents an operator's alert rule. A fraction
#: threshold here (0.8) would sit below every sample and fire on the whole estate.
#:
#: Note the grain when reading the incident counts: the series are HOURLY (24 points per
#: day), so a resource only crosses this ceiling in the hours around its peak — the
#: incidents are hour-resolved runs, and one busy day contributes several of them.
THRESHOLD = 80.0
OPERATOR = "GreaterThan"
TIME_AGGREGATION = "Average"

#: Azure severity is a number (0 Critical … 4 Verbose).
SEVERITY = 2

#: The criteria discriminator Azure returns for a single-resource metric alert.
CRITERIA_TYPE = "Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria"
CRITERION_TYPE = "StaticThresholdCriterion"


def rule_name_for(resource_uuid: str) -> str:
    """Return the deterministic alert-rule name for a resource.

    The caller passes the rule's own ``name`` straight back into
    ``alert_rule_incidents.list_by_alert_rule(rule_name=...)``, so this is the join
    key between the two endpoints and must stay a pure function of the resource.
    """
    return f"alert-{resource_uuid[:8]}"


def _azure_resources(estate: CanonicalEstate) -> tuple[Resource, ...]:
    """This provider's resources (the boundary lives in ``projections/scope.py``)."""
    return scope.resources(estate)


def _series_by_resource(estate: CanonicalEstate) -> dict[str, MetricSeries]:
    return {series.resource_uuid: series for series in scope.metric_series(estate)}


def _rule_id(estate: CanonicalEstate, resource: Resource, name: str) -> str:
    """The rule's ARM id: the subscription GUID, the resource group and the alert type.

    ``arm.subscription_id`` rather than ``resource.parent_scope_id``: the scope label
    (``sub-01``) is the generator's internal key, and every other id this package serves
    carries the subscription GUID, so a rule id built from the label would put the rule in a
    subscription that does not exist.
    """
    subscription = arm.subscription_id(estate, resource.parent_scope_id)
    return (
        f"/subscriptions/{subscription}/resourceGroups/{resource.parent_scope_id}"
        f"/providers/Microsoft.Insights/metricAlerts/{name}"
    )


def _rule_row(estate: CanonicalEstate, resource: Resource, series: MetricSeries) -> dict[str, object]:
    """One ``MetricAlertResource`` as Azure returns it."""
    name = rule_name_for(resource.identity.uuid)
    return {
        "id": _rule_id(estate, resource, name),
        "name": name,
        "type": "Microsoft.Insights/metricAlerts",
        "location": resource.region_id,
        "properties": {
            "description": f"Synthetic metric alert on {series.metric_name} for {resource.resource_name}",
            "severity": SEVERITY,
            "enabled": True,
            # The watched resource, named the way the resource plane and Monitor name it.
            "scopes": [metrics.resource_id(estate, series)],
            "evaluationFrequency": "PT5M",
            "windowSize": "PT15M",
            "criteria": {
                "odata.type": CRITERIA_TYPE,
                "allOf": [
                    {
                        "criterionType": CRITERION_TYPE,
                        "name": "metric1",
                        "metricName": series.metric_name,
                        "timeAggregation": TIME_AGGREGATION,
                        "operator": OPERATOR,
                        "threshold": THRESHOLD,
                    },
                ],
            },
        },
    }


def project_metric_alert_rules(estate: CanonicalEstate) -> list[dict[str, object]]:
    """Return Metric Alerts rules, one per metered Azure resource, ordered by id."""
    series_by_resource = _series_by_resource(estate)
    rows = [
        _rule_row(estate, resource, series_by_resource[resource.identity.uuid])
        for resource in _azure_resources(estate)
        if resource.identity.uuid in series_by_resource
    ]
    return sorted(rows, key=lambda row: str(row["id"]))


def _firing_runs(points: tuple[MetricPoint, ...]) -> list[tuple[MetricPoint, MetricPoint | None]]:
    """Collapse consecutive above-threshold points into firing runs.

    A run is ``(first firing point, first healthy point after it)``; the second element
    is ``None`` while the run is still open, which is what makes the incident active.

    The collapse rule is the series' own, so the grain decides the resolution rather
    than the projection: the estate samples HOURLY (24 points per day —
    ``estate_builder._METRIC_HOURS_PER_DAY``), so ``activatedTime`` is the hour a run
    started in, not the day, and ``isActive`` is decided by the series' LAST hourly
    sample. Consecutive over-threshold hours are still one run; they are an hour apart
    instead of a day apart, which is why this rule reads the points in order and never
    compares timestamps.
    """
    runs: list[tuple[MetricPoint, MetricPoint | None]] = []
    start: MetricPoint | None = None
    for point in points:
        firing = point.value > THRESHOLD
        if firing and start is None:
            start = point
        elif not firing and start is not None:
            runs.append((start, point))
            start = None
    if start is not None:
        runs.append((start, None))
    return runs


def _incident_row(rule_name: str, index: int, run: tuple[MetricPoint, MetricPoint | None]) -> dict[str, object]:
    start, end = run
    return {
        "name": f"{rule_name}-{index}",
        "ruleName": rule_name,
        "isActive": end is None,
        "activatedTime": start.ts.isoformat(),
        "resolvedTime": end.ts.isoformat() if end is not None else None,
    }


def project_alert_rule_incidents(estate: CanonicalEstate, rule_name: str) -> list[dict[str, object]]:
    """Return the firing incidents of ``rule_name``, oldest first.

    An unknown rule name yields an empty list rather than an error: Azure answers a
    rule with no incidents exactly that way, and the caller wraps this call in its own
    error handling.
    """
    series_by_resource = _series_by_resource(estate)
    for resource in _azure_resources(estate):
        if rule_name_for(resource.identity.uuid) != rule_name:
            continue
        series = series_by_resource.get(resource.identity.uuid)
        if series is None:
            return []
        return [
            _incident_row(rule_name, index, run)
            for index, run in enumerate(_firing_runs(series.points), start=1)
        ]
    return []


def last_point_timestamp(estate: CanonicalEstate) -> datetime | None:
    """Return the newest metric timestamp in the estate (used by tests and callers)."""
    newest: datetime | None = None
    for series in estate.metrics:
        for point in series.points:
            if newest is None or point.ts > newest:
                newest = point.ts
    return newest
