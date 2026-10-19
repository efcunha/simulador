"""Phase 3 renderer tests: gcp_bigquery_topology + gcp_rest_fixtures.

Covers AC-P3-1a (location.region), AC-P3-4 (ARRAY<STRUCT> + tax/adjustment rows),
AC-P3-5 (C17 later export_time + C06 credits sum + cud row), AC-P3-6/P3-7 (REST
native inputs + marker-free cloud fields), M1 defensive RenderError, F4/NIT-2 k8s
label, and byte-determinism. Marked ``topology`` / ``fixtures`` for ``-k`` selection.
"""

from __future__ import annotations

import json as _json
import re
from dataclasses import replace
from decimal import Decimal

import pytest

from tools.synthetic_clouds.generate.estate_builder import build_estate
from tools.synthetic_clouds.model.billing import BillingLine
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.render import gcp_bigquery_topology as mod
from tools.synthetic_clouds.render.base import RenderError
from tools.synthetic_clouds.render.gcp_bigquery_topology import GcpBigQueryTopologyRenderer
from tools.synthetic_clouds.render.gcp_rest_fixtures import GcpRestFixturesRenderer
from tools.synthetic_clouds.render.markers import SYNTH_NAME_PREFIX, unmarked_name
from tools.synthetic_clouds.scenarios.emit import apply_all

_GCP = "Google Cloud"


def _estate() -> CanonicalEstate:
    return apply_all(build_estate(seed=123, profile="small", currency="USD"))


def _gcp_lines(estate: CanonicalEstate) -> list[BillingLine]:
    return [line for line in estate.billing_lines if line.service_provider_name == _GCP]


# -- topology: DDL shape (AC-P3-4) -----------------------------------------------


def test_topology_ddl_declares_array_of_struct() -> None:
    _names, files, _counts = GcpBigQueryTopologyRenderer().build_scripts(_estate())
    tables = files["02_tables.sql"]
    for col in ("credits", "labels", "system_labels"):
        assert re.search(rf"\b{col} ARRAY<STRUCT<", tables), f"{col} must be ARRAY<STRUCT<...>>"
    assert "labels ARRAY<STRUCT<key STRING, value STRING>>" in tables  # project.labels nested
    for struct_col in (
        "service STRUCT<",
        "sku STRUCT<",
        "project STRUCT<",
        "location STRUCT<",
        "usage STRUCT<",
        "invoice STRUCT<",
        "adjustment_info STRUCT<",
        "price STRUCT<",
    ):
        assert struct_col in tables, f"missing record column {struct_col}"
    assert "usage_start_time TIMESTAMP" in tables
    assert "cost FLOAT64" in tables
    # The detailed table adds the spec's `resource` record; `resource` is a zetasql
    # reserved word, so it is declared backtick-quoted (the column is literally named
    # `resource`). Subfields are the documented ones (spec order: global_name, name).
    resource_record = re.search(r"`resource` STRUCT<([^>]*)>", tables)
    assert resource_record is not None, "missing the detailed export's `resource` record"
    assert set(resource_record.group(1).split(", ")) == {"global_name STRING", "name STRING"}


def test_topology_datasets_and_tables_present() -> None:
    names, files, _counts = GcpBigQueryTopologyRenderer().build_scripts(_estate())
    datasets = files["01_datasets.sql"]
    assert names.user_dataset in datasets
    assert names.focus_dataset in datasets
    tables = files["02_tables.sql"]
    for fqtn in (names.standard_table, names.resource_table, names.pricing_table, names.cud_table, names.focus_table):
        assert fqtn in tables


def test_topology_todo_verificar_annotated() -> None:
    _names, files, _counts = GcpBigQueryTopologyRenderer().build_scripts(_estate())
    assert "TODO-verificar" in files["02_tables.sql"]


# -- topology: row projection + determinism (AC-P3-4/5, AC-P3-1a) ----------------


def test_topology_byte_deterministic() -> None:
    renderer = GcpBigQueryTopologyRenderer()
    assert renderer.build_scripts(_estate())[1] == renderer.build_scripts(_estate())[1]


def test_topology_gcp_only_azure_excluded() -> None:
    _names, files, _counts = GcpBigQueryTopologyRenderer().build_scripts(_estate())
    inserts = files["03_insert_standard.sql"]
    assert "contoso-prod-" in inserts
    assert "'sub-01'" not in inserts and "'sub-02'" not in inserts


def test_topology_emits_no_FinOps_marker_in_any_column() -> None:
    """No cloud export column may carry the ``[SYNTH] `` storage marker.

    The marker is how ``seed/cleanup.py`` recognises the seed's own account rows, so
    it belongs on the canonical estate and in FinOps own tables -- never in the
    GCP billing export, which is a cloud-facing artifact.
    """
    _names, files, _counts = GcpBigQueryTopologyRenderer().build_scripts(_estate())
    for name, body in files.items():
        assert SYNTH_NAME_PREFIX.strip() not in body, f"marker leaked into {name}"


def test_topology_location_region_equals_region_id() -> None:
    """AC-P3-1a: location.region projects BillingLine.region_id directly."""
    estate = _estate()
    gcp_lines = [line for line in _gcp_lines(estate) if line.charge_category in {"Usage", "Purchase", "Adjustment"}]
    distinct_regions = {line.region_id for line in gcp_lines}
    _names, files, _counts = GcpBigQueryTopologyRenderer().build_scripts(estate)
    inserts = files["03_insert_standard.sql"]
    for region in distinct_regions:
        assert f"'{region}' AS region" in inserts, f"region {region} not projected into location.region"


def test_topology_credits_sum_equals_negative_credit() -> None:
    """AC-P3-5/C06: sum(credits[].amount) == -Credit.amount per GCP credit (6-dp).

    ``credits[].name`` is a cloud export column, so it carries the credit's name
    WITHOUT the FinOps ``[SYNTH] `` storage marker.
    """
    estate = _estate()
    names = GcpBigQueryTopologyRenderer().build_scripts(estate)[0]
    gcp_lines = mod._gcp_lines(estate)
    credits_by_line = mod._allocate_credits(estate, gcp_lines, names)
    gcp_scopes = {line.sub_account_id for line in gcp_lines}
    for credit in estate.credits:
        if credit.scope_id not in gcp_scopes:
            continue
        total = Decimal("0")
        for elements in credits_by_line.values():
            for el in elements:
                if el["name"] == unmarked_name(credit.name):
                    total += Decimal(str(el["amount"]))
        assert total == -credit.amount, f"credit {credit.name}: sum {total} != {-credit.amount}"


def test_topology_credit_type_from_commitment_kind() -> None:
    """AC-P3-5/F3: GCP credits are COMMITTED_USAGE_DISCOUNT (Commitment.kind == cud)."""
    estate = _estate()
    names = GcpBigQueryTopologyRenderer().build_scripts(estate)[0]
    gcp_lines = mod._gcp_lines(estate)
    credits_by_line = mod._allocate_credits(estate, gcp_lines, names)
    all_types = {el["type"] for elements in credits_by_line.values() for el in elements}
    assert all_types, "no GCP credits attached"
    assert all_types == {"COMMITTED_USAGE_DISCOUNT"}


def test_topology_tax_rows_from_estate_taxes() -> None:
    """AC-P3-4: one tax row per GCP-scope Tax, cost_type=tax.

    The row is discriminated by ``cost_type="tax"`` + ``project.id`` (both modelled
    by the estate). ``service``/``sku`` are EMPTY: this estate has no tax service or
    SKU, and the sentinels that used to sit there (``SYNTH-TAX``, ``[SYNTH] Tax``)
    were synthetic markers in two real cloud columns.
    """
    estate = _estate()
    gcp_lines = mod._gcp_lines(estate)
    tax_rows = mod._tax_rows(estate, gcp_lines, "us")
    gcp_scopes = {line.sub_account_id for line in gcp_lines}
    expected = [t for t in estate.taxes if t.scope_id in gcp_scopes]
    assert len(tax_rows) == len(expected)
    for row in tax_rows:
        assert row["cost_type"] == "tax"
        assert row["service"] == {"id": "", "description": ""}
        assert row["sku"] == {"id": "", "description": ""}
        assert row["project"]["name"] == row["project"]["id"]
        assert row["credits"] == []
        assert re.fullmatch(r"\d{6}", row["invoice"]["month"])
    by_month = {(t.scope_id, f"{t.period_start.year:04d}{t.period_start.month:02d}"): t for t in expected}
    for row in tax_rows:
        key = (row["project"]["id"], row["invoice"]["month"])
        assert float(by_month[key].amount) == row["cost"]


def test_topology_k8s_cluster_label_injected() -> None:
    """F4/NIT-2: every k8s-namespace GCP row carries goog-k8s-cluster-name == resource_name."""
    estate = _estate()
    names = GcpBigQueryTopologyRenderer().build_scripts(estate)[0]
    gcp_lines = mod._gcp_lines(estate)
    credits_by_line = mod._allocate_credits(estate, gcp_lines, names)
    resource_names = mod._resource_name_by_uuid(estate)
    k8s_lines = [line for line in gcp_lines if line.k8s_namespace is not None]
    assert k8s_lines, "no GCP k8s namespace lines (C15) present"
    for line in k8s_lines:
        assert line.resource_uuid is not None
        row = mod._standard_row(line, estate, credits_by_line, resource_names, "us")
        label_map = {entry["key"]: entry["value"] for entry in row["labels"]}
        assert "goog-k8s-cluster-name" in label_map
        assert label_map["goog-k8s-cluster-name"] == resource_names[line.resource_uuid]


def test_topology_c17_adjustment_later_export_time() -> None:
    """AC-P3-5: C17 adjustment row has cost_type=adjustment and a later export_time."""
    estate = _estate()
    adj = [line for line in _gcp_lines(estate) if line.charge_category == "Adjustment"]
    assert adj, "no GCP adjustment line (C17) present"
    for line in adj:
        assert line.restates_date is not None
        assert line.export_time.date() > line.restates_date


def test_topology_cud_subscription_row_present() -> None:
    """AC-P3-5: a cud_subscriptions_export row keyed by the GCP Commitment exists."""
    estate = _estate()
    _names, files, _counts = GcpBigQueryTopologyRenderer().build_scripts(estate)
    cud_rows = mod._cud_rows(estate, mod._gcp_lines(estate))
    assert cud_rows, "no GCP CUD subscription rows"
    assert "INSERT INTO" in files["06_insert_cud.sql"]


def test_topology_manifest_counts_match() -> None:
    renderer = GcpBigQueryTopologyRenderer()
    names, _files, counts = renderer.build_scripts(_estate())
    manifest = renderer._manifest(names, counts)
    assert manifest["tables"]["standard"]["expected_rows"] == counts[names.standard_table]
    assert manifest["tables"]["standard"]["expected_rows"] > 0
    assert "todo_verificar" in manifest


def test_topology_defensive_render_error_on_illegal_category() -> None:
    """M1: a GCP line with charge_category not in {Usage,Purchase,Adjustment} raises."""
    estate = _estate()
    victim = next(line for line in _gcp_lines(estate) if line.charge_category == "Usage")
    tampered = replace(victim, charge_category="Tax")
    others = tuple(line for line in estate.billing_lines if line.line_id != victim.line_id)
    bad_estate = replace(estate, billing_lines=(*others, tampered))
    with pytest.raises(RenderError):
        GcpBigQueryTopologyRenderer().build_scripts(bad_estate)


# -- fixtures (AC-P3-6/P3-7) -----------------------------------------------------


def _collect_uuids(obj: object) -> list[str]:
    found: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "resourceUuid" and isinstance(v, str) and v:
                found.append(v)
            else:
                found.extend(_collect_uuids(v))
    elif isinstance(obj, list):
        for item in obj:
            found.extend(_collect_uuids(item))
    return found


def test_fixtures_no_orphan_resource_uuids() -> None:
    """P2: every resourceUuid referenced in a fixture exists in the estate."""
    estate = _estate()
    valid = estate.resource_uuids()
    for name, body in GcpRestFixturesRenderer().build_fixtures(estate).items():
        for uuid_ref in _collect_uuids(body):
            assert uuid_ref in valid, f"orphan uuid {uuid_ref} in fixture {name}"


def test_fixtures_byte_deterministic() -> None:
    renderer = GcpRestFixturesRenderer()
    assert renderer.build_fixtures(_estate()) == renderer.build_fixtures(_estate())


def test_fixtures_scc_findings_native_shape() -> None:
    estate = _estate()
    fixtures = GcpRestFixturesRenderer().build_fixtures(estate)
    scc = fixtures["scc_findings.json"]
    gcp_findings = [f for f in estate.findings if f.provider == "gcp"]
    assert scc["totalSize"] == len(gcp_findings)
    for item in scc["listFindingsResults"]:
        f = item["finding"]
        assert f["state"] == "ACTIVE"
        assert f["severity"] in {"CRITICAL", "HIGH", "MEDIUM", "LOW"}  # UPPERCASE native


def test_fixtures_carry_no_FinOps_marker_and_stay_fictional() -> None:
    """AC-P3-7 re-read: markers stay OUT of cloud fields, fictional ids stay IN.

    ``[SYNTH] `` is FinOps STORAGE discriminator (``seed/cleanup.py`` matches
    ``cloud_accounts.name LIKE '[SYNTH] %'``) and every synthetic value must still be
    fictional (``contoso.example``). The two are different obligations: the first must
    never reach a cloud-facing field, the second must always hold.
    """
    estate = _estate()
    fixtures = GcpRestFixturesRenderer().build_fixtures(estate)
    for name, body in fixtures.items():
        assert SYNTH_NAME_PREFIX.strip() not in _json.dumps(body), f"marker leaked into {name}"
    members = fixtures["cai_search_all_iam_policies.json"]["results"][0]["policy"]["bindings"][0]["members"]
    assert "contoso.example" in members[0]
    assert fixtures["scc_sources.json"]["sources"][0]["name"].startswith("organizations/900900900/sources/")


def test_fixtures_scc_findings_have_no_invented_source_properties_key() -> None:
    """The SCC Finding shape has no ``synthetic`` key; it must not be emitted.

    The canonical ``NativeFinding.evidence_json`` is a FinOps-side marker bag.
    Spreading it into ``sourceProperties`` wrote an invented field into every finding;
    it is projected onto the published ``Explanation``/``Recommendation`` keys instead.
    """
    estate = _estate()
    scc = GcpRestFixturesRenderer().build_fixtures(estate)["scc_findings.json"]
    assert scc["listFindingsResults"], "no findings to check"
    for item in scc["listFindingsResults"]:
        props = item["finding"]["sourceProperties"]
        assert props, "sourceProperties must carry the detector verdict"
        assert set(props) == {"Explanation", "Recommendation"}
        assert all(isinstance(value, str) and value for value in props.values())


def test_fixtures_recommender_content_carries_no_marker() -> None:
    """``content`` is a free-form Struct, but the marker bag is not a payload."""
    estate = _estate()
    fixtures = GcpRestFixturesRenderer().build_fixtures(estate)
    for name in ("recommender_recommendations.json", "recommender_insights.json"):
        rows = fixtures[name]["recommendations" if "recommendation" in name else "insights"]
        assert rows
        for row in rows:
            assert row["content"] == {}


def test_fixtures_no_computed_outputs() -> None:
    """P1: no FinOps-computed output field names leak into any fixture."""
    estate = _estate()
    fixtures = GcpRestFixturesRenderer().build_fixtures(estate)
    forbidden = {"drift_result", "compliance_result", "opportunity", "anomaly", "tag_score", "forecast"}
    for name, body in fixtures.items():
        text = _json.dumps(body)
        for token in forbidden:
            assert token not in text, f"computed output {token} leaked in fixture {name}"


def test_topology_emits_bulk_json_rows() -> None:
    """The bulk payloads mirror the SQL rows and are safe for tabledata.insertAll.

    The emulator's SQL parser cannot take the INSERT scripts at production scale, so the
    renderer also emits the same rows as JSON. insertAll rejects any field the table does
    not declare -- hence the dropped ``_``-prefixed renderer keys on the tax rows -- and
    it needs ISO strings for the TIMESTAMP columns.
    """
    names, files, counts = GcpBigQueryTopologyRenderer().build_scripts(_estate())
    std = _json.loads(files["08_rows_standard.json"])
    res = _json.loads(files["09_rows_resource.json"])
    assert len(std) == counts[names.standard_table]
    assert len(res) == counts[names.resource_table]
    assert all(not [k for k in row if k.startswith("_")] for row in std)
    assert all("resource" in row for row in res)
    assert isinstance(std[0]["usage_start_time"], str)
    assert std[0]["project"]["id"]  # nested STRUCT survives as a nested object
    # byte-deterministic, like the SQL scripts
    again = GcpBigQueryTopologyRenderer().build_scripts(_estate())[1]
    assert files["08_rows_standard.json"] == again["08_rows_standard.json"]


# -- monitoring descriptors + alert policies (FR-25) -------------------------------


def _served_series(fixtures: dict[str, dict[str, object]]) -> list[dict]:
    """The timeSeries rows this renderer publishes, as a plain list."""
    rows = fixtures["monitoring_time_series.json"]["timeSeries"]
    assert isinstance(rows, list)
    return rows


def test_fixtures_metric_descriptors_describe_the_served_series() -> None:
    """A descriptor must describe a series the SAME renderer publishes, on both axes.

    ``GAUGE``/``DOUBLE`` are the type of the points already published, and
    ``monitoredResourceTypes`` is the resource type those points are attributed to. The
    test asserts the agreement instead of the literals: a descriptor that named a metric
    type no series carries, or an attribution the series does not use, would make a
    consumer's discovery and query disagree.
    """
    fixtures = GcpRestFixturesRenderer().build_fixtures(_estate())
    series = _served_series(fixtures)
    by_type: dict[str, set[str]] = {}
    for row in series:
        by_type.setdefault(row["metric"]["type"], set()).add(row["resource"]["type"])

    descriptors = fixtures["monitoring_metric_descriptors.json"]["metricDescriptors"]
    assert descriptors, "no metric descriptors rendered"
    for descriptor in descriptors:
        assert descriptor["type"] in by_type, descriptor["type"]
        assert set(descriptor["monitoredResourceTypes"]) == by_type[descriptor["type"]]
        assert descriptor["metricKind"] == "GAUGE"
        assert descriptor["valueType"] == "DOUBLE"
        # The estate meters percentages; a name with no unit table entry gets no unit.
        assert descriptor["unit"] == "percent"

    assert len(descriptors) == len(by_type)


def test_fixtures_alert_policies_watch_a_served_series_and_invent_no_threshold() -> None:
    """One policy per series, joining back to it -- and no fabricated threshold value.

    The estate models no alerting configuration, so the derived condition is an ABSENCE
    condition: its filter names a real series and the window is FinOps own read
    lookback. A ``conditionThreshold`` here would carry a number nothing in the estate
    supports, which is the fabrication this assertion keeps out.
    """
    fixtures = GcpRestFixturesRenderer().build_fixtures(_estate())
    series = _served_series(fixtures)
    by_type: dict[str, set[str]] = {}
    for row in series:
        by_type.setdefault(row["metric"]["type"], set()).add(row["resource"]["labels"]["resourcePath"])

    policies = fixtures["monitoring_alert_policies.json"]["alertPolicies"]
    assert len(policies) == len(series)

    for policy in policies:
        condition = policy["conditions"][0]["conditionAbsent"]
        assert "conditionThreshold" not in policy["conditions"][0]
        watched = condition["filter"].split('metric.type = "', 1)[1].split('"', 1)[0]
        path = condition["filter"].split('resource.label.resourcePath = "', 1)[1].split('"', 1)[0]
        assert path in by_type[watched], f"{policy['name']} watches {path}, which no series carries"
        assert condition["duration"] == "600s"
        assert policy["enabled"] is True
        assert policy["name"].split("/alertPolicies/")[0].startswith("projects/")
