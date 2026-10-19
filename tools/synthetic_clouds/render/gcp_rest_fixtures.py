"""GCP REST fixtures renderer (Phase 3, design sec. 5.3).

Projects the ``CanonicalEstate`` into the JSON response bodies the ``gcp-sim``
FastAPI service serves (one file per endpoint family under
``out_dir/gcp_rest_fixtures/``). Both the BigQuery plane and this REST plane are
projections of the SAME estate, so a resource uuid referenced by an SCC finding is
the same uuid that appears in a BigQuery ``project.labels`` entry.

Purity (P1): emits native INPUTS only -- inventory assets, native findings
(status=open, UPPERCASE severity), native recommendations, pricing catalog,
monitoring series, native budget definitions. It NEVER emits a FinOps-computed
output (opportunity/drift/compliance/tag-score/anomaly/forecast).

Export fidelity (NFR-3 read correctly): a cloud-facing field carries no FinOps
marker. ``[SYNTH] `` is the seed's STORAGE discriminator (``seed/cleanup.py`` matches
``cloud_accounts.name LIKE '[SYNTH] %'``), and the canonical ``evidence_json`` /
``detail_json`` marker bags (``synthetic``/``rule``/``kind``) are not keys any
official cloud shape defines. Both are therefore projected onto published keys -- or
dropped where the estate models nothing (absence is absence) -- instead of being
written verbatim into a cloud's own field.

Byte-determinism: entities sorted by stable keys; ``json.dumps(sort_keys=True)``.

No-orphan (P2): every referenced resource uuid exists in ``estate.resource_uuids()``
(re-asserted as defense-in-depth in the unit test).

``TODO-verificar`` (design sec. 5.1, sec. 9 #7): the official CAI/SCC/Recommender/
Catalog/Monitoring/Budgets REST verb+route + response envelope are offline-
unverifiable; the fixtures are best-effort official-shaped and flagged.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.metrics import MetricSeries
from tools.synthetic_clouds.model.native import NativeFinding, NativeRecommendation
from tools.synthetic_clouds.model.resource import Resource
from tools.synthetic_clouds.render.markers import FICTIONAL_DOMAIN

_GCP = "gcp"

# Ids the API assigns server-side that a fixture has to mint itself (here: the budget
# id). Fixed and seedless on purpose -- the same pattern as
# ``gcp_bigquery_topology._NS``: the key already carries the estate's own ids, so the
# derived id stays deterministic while the marker slug it replaces
# (``synthetic-budget``) was synthetic text sitting in a real cloud resource name.
_FIXTURE_NS = uuid.UUID("3c9d1a54-6f8b-4a2c-9d31-0b7e5f4a8c62")

# SCC source names are ``organizations/{org_number}/sources/{source_number}``, and the
# source number is the int64 id SCC mints -- never a slug. ``_SCC_ORG_NUMBER`` mirrors
# ``GcpOrg.org_id`` in ``generate/estate_builder.py``. The source number below is a
# synthetic int64 in the id's SHAPE, NOT any real source's id
# (TODO-verificar #7: the id of the built-in Security Health Analytics source is
# offline-unverifiable); the previous value, ``sources/synthetic-source``, put a
# synthetic marker in a real name field.
_SCC_ORG_NUMBER = "900900900"
_SCC_SOURCE_NUMBER = "9009009000000000001"
_SCC_SOURCE_NAME = f"organizations/{_SCC_ORG_NUMBER}/sources/{_SCC_SOURCE_NUMBER}"

# The native Recommender/Insight type this fixture publishes. These are real type ids
# from the Google Recommender catalog; the previous value, ``google.synthetic`` (used
# for both the recommender and the insight type), put a synthetic marker in a cloud
# resource name. TODO-verificar #7: the official type id PER recommendation kind (this
# estate's ``kind`` is rightsize/idle/sku_change) is offline-unverifiable, so one
# catalog type is published for all of them rather than a guessed per-kind mapping.
_RECOMMENDER_ID = "google.compute.instance.MachineTypeRecommender"
_INSIGHT_TYPE = "google.compute.instance.MachineTypeInsight"


def _gcp_resources(estate: CanonicalEstate) -> list[Resource]:
    return sorted(
        (r for r in estate.resources if r.identity.provider == _GCP),
        key=lambda r: r.identity.uuid,
    )


def _gcp_project_for(estate: CanonicalEstate) -> str:
    """Return a representative GCP project id (the first project), for scope strings."""
    orgs = estate.gcp_orgs
    if orgs and orgs[0].folders and orgs[0].folders[0].projects:
        return orgs[0].folders[0].projects[0].project_id
    return "unknown-project"


def _asset_path(resource: Resource) -> str:
    """The GCP path naming ONE resource: ``projects/<project>/<type>/<name>``.

    This is the identity every GCP projection in these fixtures answers for a resource, and
    the reason it is a path and not the estate's ``resource_name``: a GCP resource name is
    unique inside its project ONLY, while the generator restarts its per-scope counter for
    every project (``generate/estate_builder.py:292``), so ``compute_instance-0000`` exists in
    three projects. The ``projects/<p>/`` segment carries the scope, which makes the value
    unique across the estate AND matches the shape of a real GCP resource name
    (``resources.py (modulo do consumidor):81`` builds an instance's id as
    ``projects/<p>/zones/<zone>/instances/<name>``), so a caller that lists resources and a
    caller that reads a metric resolve the same resource.
    """
    return f"projects/{resource.parent_scope_id}/{resource.resource_type}/{resource.resource_name}"


# -- Cloud Asset Inventory (searchAllResources) ------------------------------------


def _cai_resources(estate: CanonicalEstate) -> dict[str, Any]:
    """CAI searchAllResources response: one asset per GCP resource (TODO-verificar #7)."""
    results = [
        {
            "name": f"//cloudresourcemanager.googleapis.com/{_asset_path(r)}",
            "assetType": f"{r.resource_type}.googleapis.com/Resource",  # TODO-verificar #7
            "project": f"projects/{r.parent_scope_id}",
            "displayName": r.resource_name,
            "location": r.region_id,
            "labels": dict(r.tags),
            "resourceUuid": r.identity.uuid,  # synthetic cross-plane join key (P2)
        }
        for r in _gcp_resources(estate)
    ]
    return {"results": results, "nextPageToken": ""}


def _cai_iam_policies(estate: CanonicalEstate) -> dict[str, Any]:
    """CAI searchAllIamPolicies response (native IAM policy bindings; TODO-verificar #7)."""
    results = [
        {
            "resource": f"//cloudresourcemanager.googleapis.com/projects/{r.parent_scope_id}",
            "project": f"projects/{r.parent_scope_id}",
            "policy": {
                "bindings": [
                    {
                        "role": "roles/viewer",
                        "members": [f"serviceAccount:security-audit@{FICTIONAL_DOMAIN}"],
                    },
                ]
            },
            "resourceUuid": r.identity.uuid,
        }
        for r in _gcp_resources(estate)
    ]
    return {"results": results, "nextPageToken": ""}


def _cai_analyze_iam(estate: CanonicalEstate) -> dict[str, Any]:
    """CAI analyzeIamPolicy response (minimal native shape; TODO-verificar #7)."""
    project = _gcp_project_for(estate)
    return {
        "mainAnalysis": {
            "analysisQuery": {"scope": f"projects/{project}"},
            "analysisResults": [],
        },
        "fullyExplored": True,
    }


# -- Security Command Center (sources + findings) ----------------------------------


def _scc_sources(estate: CanonicalEstate) -> dict[str, Any]:
    """SCC sources list (one source; TODO-verificar #7)."""
    return {
        "sources": [
            {
                "name": _SCC_SOURCE_NAME,
                "displayName": "Security Health Analytics",
                "description": "Built-in SCC service that scans for misconfigurations.",
            }
        ],
        "nextPageToken": "",
    }


def _scc_source_properties(f: NativeFinding) -> dict[str, str]:
    """Return ``sourceProperties`` for ``f`` using PUBLISHED SCC keys.

    Security Health Analytics reports the detector verdict in ``Explanation`` and the
    remediation in ``Recommendation``; those are the keys an SCC consumer reads.

    ``NativeFinding.evidence_json`` is a FinOps-side marker bag
    (``synthetic`` + ``rule`` + optional ``scenario``) and is NOT part of the SCC
    Finding shape, so it is projected onto the published keys instead of being spread
    verbatim. Spreading it wrote a ``synthetic`` key -- which the official shape does
    not have -- into every finding.
    """
    rule = str(f.evidence_json.get("rule", "")).strip() or f.category.lower()
    return {
        "Explanation": f"{rule} condition detected on the resource ({f.category}).",
        "Recommendation": f"Review and remediate the {rule} condition.",
    }


def _scc_finding(f: NativeFinding) -> dict[str, Any]:
    """One SCC finding in native REST shape (status open, UPPERCASE severity)."""
    return {
        "name": f"{_SCC_SOURCE_NAME}/findings/{f.finding_id}",
        "parent": _SCC_SOURCE_NAME,
        "resourceName": f"//cloudasset.googleapis.com/{f.resource_uuid}",
        "state": "ACTIVE",
        "category": f.category,
        "severity": f.severity,  # UPPERCASE native convention
        "findingClass": "MISCONFIGURATION",  # TODO-verificar #7
        "sourceProperties": _scc_source_properties(f),
        "resourceUuid": f.resource_uuid,  # synthetic cross-plane join key (P2)
    }


def _scc_findings(estate: CanonicalEstate) -> dict[str, Any]:
    """SCC findings list for GCP native findings (TODO-verificar #7)."""
    gcp_findings = sorted(
        (f for f in estate.findings if f.provider == _GCP),
        key=lambda f: f.finding_id,
    )
    return {
        "listFindingsResults": [{"finding": _scc_finding(f)} for f in gcp_findings],
        "nextPageToken": "",
        "totalSize": len(gcp_findings),
    }


# -- Recommender (recommendations + insights) --------------------------------------


def _recommendation(rec: NativeRecommendation) -> dict[str, Any]:
    """One native recommendation (TODO-verificar #7).

    ``content`` is empty on purpose: it is a free-form ``google.protobuf.Struct`` in
    the official shape, and the only thing this estate carries for it is
    ``detail_json`` -- a FinOps-side marker bag (``synthetic`` + ``kind``) whose
    keys the shape does not define. The native type is already published, marker-free,
    in ``recommenderSubtype``.
    """
    return {
        "name": (
            f"projects/-/locations/global/recommenders/{_RECOMMENDER_ID}"
            f"/recommendations/{rec.recommendation_id}"
        ),
        "recommenderSubtype": rec.kind,  # TODO-verificar #7
        "stateInfo": {"state": "ACTIVE"},
        "content": {},
        "resourceUuid": rec.resource_uuid,
    }


def _recommender_recommendations(estate: CanonicalEstate) -> dict[str, Any]:
    gcp_recs = sorted(
        (r for r in estate.recommendations if r.provider == _GCP),
        key=lambda r: r.recommendation_id,
    )
    return {"recommendations": [_recommendation(r) for r in gcp_recs], "nextPageToken": ""}


def _recommender_insights(estate: CanonicalEstate) -> dict[str, Any]:
    """Recommender insights list (derived from the same native recs; TODO-verificar #7).

    ``content`` is empty for the reason ``_recommendation`` records.
    """
    gcp_recs = sorted(
        (r for r in estate.recommendations if r.provider == _GCP),
        key=lambda r: r.recommendation_id,
    )
    insights = [
        {
            "name": f"projects/-/locations/global/insightTypes/{_INSIGHT_TYPE}/insights/{r.recommendation_id}",
            "insightSubtype": r.kind,
            "stateInfo": {"state": "ACTIVE"},
            "content": {},
            "resourceUuid": r.resource_uuid,
        }
        for r in gcp_recs
    ]
    return {"insights": insights, "nextPageToken": ""}


# -- Cloud Billing Catalog (services + skus) ---------------------------------------


def _catalog_services(estate: CanonicalEstate) -> dict[str, Any]:
    """Cloud Billing Catalog services, derived from GCP resource service names."""
    names = sorted({r.service_name for r in _gcp_resources(estate)})
    services = [
        {
            "name": f"services/{name.replace(' ', '-').upper()}",
            "serviceId": name.replace(" ", "-").upper(),
            "displayName": name,
        }
        for name in names
    ]
    return {"services": services, "nextPageToken": ""}


def _catalog_skus(estate: CanonicalEstate) -> dict[str, Any]:
    """Cloud Billing Catalog SKUs, derived from GCP resource sku ids (TODO-verificar #7)."""
    seen: dict[str, Resource] = {}
    for r in _gcp_resources(estate):
        seen.setdefault(r.sku_id, r)
    skus = [
        {
            "name": f"services/{res.service_name.replace(' ', '-').upper()}/skus/{sku_id}",
            "skuId": sku_id,
            "description": res.service_name,
            "category": {"serviceDisplayName": res.service_name, "resourceFamily": res.service_category},
        }
        for sku_id, res in sorted(seen.items())
    ]
    return {"skus": skus, "nextPageToken": ""}


# -- Cloud Monitoring (timeSeries) --------------------------------------------------

#: Estate ``resource_type`` -> ``(metric type namespace, monitored resource type)``.
#: A Cloud Monitoring series belongs to the resource it MEASURES: ``metric.type`` is
#: namespaced by the service that publishes the metric, and ``resource.type`` names the
#: monitored resource the samples are attributed to. Typing every series as
#: ``compute.googleapis.com/instance`` on a ``gce_instance`` published Cloud SQL's
#: ``cpu_utilization`` in Compute Engine's namespace and attributed it to an instance no
#: Cloud SQL database owns -- both halves of the descriptor belonged to another service.
#:
#: Only the types ``generate/estate_builder._build_metrics`` actually meters are listed
#: (GCP's ``compute_instance`` and ``cloud_sql``). The monitored resource type of the
#: other GCP catalog types is offline-unverifiable (TODO-verificar #7), and a guessed
#: mapping is the invention this table exists to avoid; a series on a type the table
#: cannot map is omitted rather than mislabelled.
_MONITORED_RESOURCE: dict[str, tuple[str, str]] = {
    "compute_instance": ("compute.googleapis.com/instance", "gce_instance"),
    "cloud_sql": ("cloudsql.googleapis.com/database", "cloudsql_database"),
}


#: Estate metric name -> the Cloud Monitoring unit of the series carrying it.
#:
#: Both names the generator meters are PERCENTAGES of the resource's capacity --
#: ``generate/estate_builder._build_metrics`` records the three consumer tables that
#: declare it (``aws_metrics``'s unit table, ``templates.py``'s registry and this
#: renderer's own ``doubleValue``), and ``<modulo do consumidor>._GCP_UNIT_MAP`` maps
#: ``percent`` back to the display label ``Percent``. A metric name this table does not
#: know gets NO ``unit`` field rather than a guessed one, the same discipline
#: ``_MONITORED_RESOURCE`` follows.
_METRIC_UNIT: dict[str, str] = {
    "cpu_utilization": "percent",
    "memory_utilization": "percent",
}

#: The absence window on a derived alert policy: the ten minutes FinOps OWN reads
#: look back over (``<modulo do consumidor>._LOOKBACK_MINUTES = 10``, and the
#: ``timedelta(minutes=10)`` interval ``<modulo do consumidor>`` queries with). The
#: fixture can cite it; a threshold VALUE could not be cited from anywhere, which is why
#: the derived condition is an absence condition (see ``_monitoring_alert_policies``).
_ALERT_ABSENCE_WINDOW = "600s"


def _metric_display_name(metric_type: str) -> str:
    """``compute.googleapis.com/instance/cpu_utilization`` -> ``Cpu Utilization``.

    Humanises the metric NAME, which is the type's last segment by construction --
    ``_metered_series`` builds the type as ``<namespace>/<estate metric_name>``, so the
    trailing segment is the estate's own ``cpu_utilization``. (FinOps
    ``<modulo do consumidor>._gcp_metric_to_display_name`` humanises everything after the
    FIRST slash instead, which folds this estate's ``instance``/``database`` resource
    segment into the label and renders ``Instance/cpu Utilization``; emitting the label
    here is what keeps a discovery surface legible, and it is why the field is published
    rather than left to that fallback.)
    """
    short = metric_type.rsplit("/", 1)[-1]
    return " ".join(word.capitalize() for word in short.split("_"))


def _metered_series(estate: CanonicalEstate) -> list[tuple[MetricSeries, Resource, str, str]]:
    """The GCP series this renderer can publish, as ``(series, resource, metric type, resource type)``.

    The single iteration both monitoring surfaces share: a series whose resource is not a
    GCP resource, or whose resource type ``_MONITORED_RESOURCE`` cannot map, is omitted --
    so ``timeSeries``, ``metricDescriptors`` and ``alertPolicies`` are projections of ONE
    set and cannot describe different estates.
    """
    gcp_resources = {r.identity.uuid: r for r in _gcp_resources(estate)}
    metered: list[tuple[MetricSeries, Resource, str, str]] = []
    for series in sorted(estate.metrics, key=lambda s: (s.resource_uuid, s.metric_name)):
        resource = gcp_resources.get(series.resource_uuid)
        if resource is None:
            continue
        monitored = _MONITORED_RESOURCE.get(resource.resource_type)
        if monitored is None:
            continue
        metric_namespace, resource_type = monitored
        metered.append((series, resource, f"{metric_namespace}/{series.metric_name}", resource_type))
    return metered


def _monitoring_timeseries(estate: CanonicalEstate) -> dict[str, Any]:
    """Cloud Monitoring timeSeries for GCP resource metrics (TODO-verificar #7).

    **A series is attributed to the SAME id the resource-list fixture publishes**:
    ``_asset_path`` — ``projects/<project>/<type>/<name>`` — plus the project on its own
    ``project_id`` label, which is a real Cloud Monitoring label for both monitored types
    here. That is what makes the two surfaces agree by construction, and it is why the
    identity is a path rather than the estate's ``resource_name``: a name is unique only
    inside its project, so a series keyed by one would be a series several projects claim
    (the generator restarts its per-scope counter, so ``compute_instance-0000`` exists in
    three projects). A caller that lists resources and a caller that reads a metric
    therefore resolve one resource, which is what the GCP metric reader does
    (``gcp_metrics.py (modulo do consumidor)`` matches a service against the series' resource labels).

    ``resourceUuid`` stays alongside it as the synthetic cross-plane join key (P2) the other
    fixtures also carry, so a holder of the estate's own id can still reach the series.
    """
    gcp_resources = {r.identity.uuid: r for r in _gcp_resources(estate)}
    series = sorted(
        (s for s in estate.metrics if s.resource_uuid in gcp_resources),
        key=lambda s: (s.resource_uuid, s.metric_name),
    )
    time_series: list[dict[str, Any]] = []
    for s in series:
        resource = gcp_resources[s.resource_uuid]
        monitored = _MONITORED_RESOURCE.get(resource.resource_type)
        if monitored is None:
            continue
        metric_namespace, resource_type = monitored
        time_series.append(
            {
                "metric": {"type": f"{metric_namespace}/{s.metric_name}"},  # TODO-verificar #7
                "resource": {
                    "type": resource_type,
                    "labels": {
                        "project_id": resource.parent_scope_id,
                        "resourcePath": _asset_path(resource),
                        "resourceUuid": s.resource_uuid,
                    },
                },
                "points": [
                    {
                        "interval": {"endTime": p.ts.isoformat()},
                        "value": {"doubleValue": p.value},
                    }
                    for p in s.points
                ],
            }
        )
    return {"timeSeries": time_series, "nextPageToken": ""}


def _monitoring_metric_descriptors(estate: CanonicalEstate) -> dict[str, Any]:
    """metricDescriptors.list: one descriptor per metric TYPE the estate meters.

    The descriptor describes a series this renderer already publishes, and nothing else:
    ``GAUGE`` is what one value per timestamp IS, ``DOUBLE`` is the type of the
    ``doubleValue`` those same points carry, and ``monitoredResourceTypes`` is the
    resource type the matching ``timeSeries`` entry is attributed to. A consumer that
    discovers metrics over the wire and then queries them therefore reads two surfaces
    that describe one series rather than two guesses that might disagree.

    The ``name`` path is project-scoped like every GCP descriptor name; it carries the
    representative project (``_gcp_project_for``, the same choice ``_budgets`` makes)
    because a descriptor type is project-wide, while the series' own attribution stays on
    the resource's project (TODO-verificar #7: the catalog-wide-vs-project-wide scope of
    a descriptor is offline-unverifiable).
    """
    metric_types: dict[str, set[str]] = {}
    for _series, _resource, metric_type, resource_type in _metered_series(estate):
        metric_types.setdefault(metric_type, set()).add(resource_type)

    project = _gcp_project_for(estate)
    descriptors: list[dict[str, Any]] = []
    for metric_type in sorted(metric_types):
        descriptor: dict[str, Any] = {
            "name": f"projects/{project}/metricDescriptors/{metric_type}",
            "type": metric_type,
            "displayName": _metric_display_name(metric_type),
            "metricKind": "GAUGE",
            "valueType": "DOUBLE",
            "monitoredResourceTypes": sorted(metric_types[metric_type]),
        }
        unit = _METRIC_UNIT.get(metric_type.rsplit("/", 1)[-1])
        if unit:
            descriptor["unit"] = unit
        descriptors.append(descriptor)
    return {"metricDescriptors": descriptors, "nextPageToken": ""}


def _monitoring_alert_policies(estate: CanonicalEstate) -> dict[str, Any]:
    """AlertPolicyService.listAlertPolicies: one policy per metered series (TODO-verificar #7).

    The estate models no alerting configuration, so a policy is DERIVED from the series
    the estate does report -- one per series, named after the resource it watches, with a
    condition whose filter names that series' real metric type and real resource path. It
    joins back to ``timeSeries`` and ``metricDescriptors`` on exactly those values.

    The condition is an ABSENCE condition on purpose: the estate carries no operator's
    threshold, and minting a number (``> 80``) would put a fabricated threshold in a real
    alert-policy field. The duration is the one window that can be cited from FinOps
    itself (``_ALERT_ABSENCE_WINDOW``). ``enabled``/``ACTIVE`` states the policy exists and
    is watched, the same derivation ``_recommendation`` already uses for its
    ``stateInfo.state``; a disabled policy would be one this estate claims exists but
    gates off, which is a claim nothing here supports.

    The cross-plane join key rides in ``userLabels`` and NOT as a top-level key, unlike the
    hand-shaped envelopes above: this body is parsed into the CLIENT's own ``AlertPolicy``
    proto, which declares no top-level ``resourceUuid`` and rejects the whole response when
    one is present (measured: ``ParseDict`` fails with "has no field named resourceUuid").
    ``userLabels`` is a free-form map the type does declare, and its key is lowercase
    because GCP's own user-label key rules require it.
    """
    policies: list[dict[str, Any]] = []
    for series, resource, metric_type, _resource_type in _metered_series(estate):
        label = _metric_display_name(metric_type)
        policy_id = uuid.uuid5(_FIXTURE_NS, f"gcp/alert-policy/{series.resource_uuid}/{series.metric_name}")
        policies.append(
            {
                "name": f"projects/{resource.parent_scope_id}/alertPolicies/{policy_id}",
                "displayName": f"{resource.resource_name}: {label}",
                "combiner": "AND",
                "enabled": True,
                "conditions": [
                    {
                        "displayName": f"{label} stops reporting",
                        "conditionAbsent": {
                            "filter": (
                                f'metric.type = "{metric_type}" AND '
                                f'resource.label.resourcePath = "{_asset_path(resource)}"'
                            ),
                            "duration": _ALERT_ABSENCE_WINDOW,
                        },
                    }
                ],
                # Synthetic cross-plane join key (P2), in the map field the proto
                # declares; the key is lowercase per GCP's user-label key rules.
                "userLabels": {"resource_uuid": series.resource_uuid},
            }
        )
    return {"alertPolicies": policies, "nextPageToken": ""}

# -- Billing Budgets (native budget definitions) -----------------------------------


def _budgets(estate: CanonicalEstate) -> dict[str, Any]:
    """Native GCP Billing Budgets definitions (NOT FinOps budget evaluations; P1).

    The budget id is a UUID, which is what the API assigns; the previous
    ``synthetic-budget`` slug was a synthetic marker in the resource name, and the
    ``[SYNTH] `` display prefix was FinOps storage discriminator in a cloud field
    (see ``render/markers.py``).
    """
    gcp_ba = next((b for b in estate.billing_accounts if b.provider == _GCP), None)
    ba_id = gcp_ba.billing_account_id if gcp_ba else "unknown"
    budgets = [
        {
            "name": f"billingAccounts/{ba_id}/budgets/{uuid.uuid5(_FIXTURE_NS, f'gcp/budget/{ba_id}')}",
            "displayName": "Monthly Budget",
            "budgetFilter": {"projects": [f"projects/{_gcp_project_for(estate)}"]},
            "amount": {"specifiedAmount": {"currencyCode": estate.currency, "units": "1000"}},
        }
    ]
    return {"budgets": budgets, "nextPageToken": ""}


class GcpRestFixturesRenderer:
    """Renders the canonical estate into gcp-sim REST response fixtures."""

    name = "gcp_rest_fixtures"

    def build_fixtures(self, estate: CanonicalEstate) -> dict[str, dict[str, Any]]:
        """Return a map ``{filename: response_body}`` -- pure, no filesystem."""
        return {
            "cai_search_all_resources.json": _cai_resources(estate),
            "cai_search_all_iam_policies.json": _cai_iam_policies(estate),
            "cai_analyze_iam_policy.json": _cai_analyze_iam(estate),
            "scc_sources.json": _scc_sources(estate),
            "scc_findings.json": _scc_findings(estate),
            "recommender_recommendations.json": _recommender_recommendations(estate),
            "recommender_insights.json": _recommender_insights(estate),
            "catalog_services.json": _catalog_services(estate),
            "catalog_skus.json": _catalog_skus(estate),
            "monitoring_time_series.json": _monitoring_timeseries(estate),
            "monitoring_metric_descriptors.json": _monitoring_metric_descriptors(estate),
            "monitoring_alert_policies.json": _monitoring_alert_policies(estate),
            "budgets.json": _budgets(estate),
        }

    def render(self, estate: CanonicalEstate, out_dir: Path) -> list[Path]:
        """Write one JSON fixture per endpoint family under ``out_dir/gcp_rest_fixtures/``."""
        target = out_dir / "gcp_rest_fixtures"
        target.mkdir(parents=True, exist_ok=True)
        written: list[Path] = []
        for filename, body in sorted(self.build_fixtures(estate).items()):
            path = target / filename
            path.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            written.append(path)
        return written
