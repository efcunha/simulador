"""Azure Monitor router: metrics, metricDefinitions, metricAlerts, alert incidents.

Every path and api-version below was read off the **installed client** rather than
guessed — the ``azure-mgmt-monitor`` 7.0.0 operations were driven with a recording
transport and the URLs they emit are:

* ``GET {scope}/providers/Microsoft.Insights/metrics?api-version=2024-02-01``
* ``GET {scope}/providers/Microsoft.Insights/metricDefinitions?api-version=2024-02-01``
* ``GET {scope}/providers/Microsoft.Insights/metricAlerts?api-version=2018-03-01``
* ``GET {scope}/providers/microsoft.insights/alertrules/{rule}/incidents?api-version=2016-03-01``

The last one is **lower-case** in the SDK's own URL template (``resourcegroups``,
``microsoft.insights``, ``alertrules``). FastAPI matches paths case-sensitively, so
that spelling is load-bearing: the capitalized form would 404 the real client.

Monitor is the one Azure surface whose completion matters for the alert screens —
``<modulo do consumidor>.collect_alarms`` reads the rules and their incidents,
and ``<modulo do consumidor>.discover_metrics`` reads the definitions — so all four
projections here are consumed, not decorative.

TODO-verificar §11.11: the exact Monitor response envelopes and api-version strings
are NOT offline-verifiable; emitted official-shaped and flagged.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from azure_sim.api.common import get_estate, require_api_version
from azure_sim.projections.alerts import project_alert_rule_incidents, project_metric_alert_rules
from azure_sim.projections.metrics import project_metric_definitions, project_metrics

router = APIRouter()

# TODO-verificar §11.11: official Azure Monitor api-version strings.
_METRICS_VERSIONS: frozenset[str] = frozenset({"2018-01-01", "2024-02-01"})
_METRIC_DEFINITIONS_VERSIONS: frozenset[str] = frozenset({"2018-01-01", "2024-02-01"})
_METRIC_ALERTS_VERSIONS: frozenset[str] = frozenset({"2018-03-01"})
_ALERT_RULE_INCIDENTS_VERSIONS: frozenset[str] = frozenset({"2016-03-01"})


@router.get("/{scope:path}/providers/Microsoft.Insights/metrics")
async def metrics(request: Request, scope: str = "") -> dict[str, Any]:
    """Return native Monitor metric series (``{value:[...]}`` envelope)."""
    require_api_version(request, _METRICS_VERSIONS)
    return {"value": project_metrics(get_estate(request))}


@router.get("/{scope:path}/providers/Microsoft.Insights/metricDefinitions")
async def metric_definitions(request: Request, scope: str = "") -> dict[str, Any]:
    """Return the metric catalogue for the Azure resources the estate meters."""
    require_api_version(request, _METRIC_DEFINITIONS_VERSIONS)
    return {"value": project_metric_definitions(get_estate(request))}


@router.get("/{scope:path}/providers/Microsoft.Insights/metricAlerts")
async def metric_alerts(request: Request, scope: str = "") -> dict[str, Any]:
    """Return the synthetic metric-alert rules, one per metered Azure resource."""
    require_api_version(request, _METRIC_ALERTS_VERSIONS)
    return {"value": project_metric_alert_rules(get_estate(request))}


@router.get("/{scope:path}/providers/microsoft.insights/alertrules/{rule_name}/incidents")
async def alert_rule_incidents(
    request: Request,
    rule_name: str,
    scope: str = "",
) -> dict[str, Any]:
    """Return the firing incidents of ``rule_name`` (the caller passes the rule name)."""
    require_api_version(request, _ALERT_RULE_INCIDENTS_VERSIONS)
    return {"value": project_alert_rule_incidents(get_estate(request), rule_name)}
