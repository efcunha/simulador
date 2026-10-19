"""The ``cur2_aws`` renderer: the 131 documented CUR 2.0 columns, proved per artifact.

Five axes:

  * **Column fidelity.** The emitted columns ARE the columns the cited specification
    declares -- measured on the artifact the renderer actually wrote
    (``fidelity.artifacts.columns_of`` over the emitted Parquet and CSV), compared with
    ``fidelity.checker.check`` against ``spec.emittable_names``. A column outside the
    spec, a documented column missing, or a column that does not belong to the format
    fails here; the list in memory is never the thing under test.
  * **Null-empty columns.** A column the documentation says exists and never carries a
    value must be emitted and must stay empty. There is none on this surface, and the
    test is written against the spec's own set so it keeps holding if one appears.
  * **Delivery layout.** ``data/`` and ``metadata/`` prefixes as the spec states them, the
    uppercase ``BILLING_PERIOD=YYYY-MM`` partition, five-digit chunk numbering and
    ``.snappy.parquet`` names -- and the ``metadata/`` prefix deliberately EMPTY, because
    the manifest AWS documents there has no published schema and a document whose field
    names we chose is the same fabrication as an invented column. The run is recorded in
    the sibling ``_provenance.json`` instead, and a test fails if any other document ever
    appears in the delivered tree.
  * **Value projection.** The columns that carry data are rebuilt here from MODEL rows,
    never asserted against a renderer literal, so a test cannot pass by agreeing with
    the implementation.
  * **Determinism and boundary.** Same seed => same bytes; everything lands under
    ``out_dir/cur2_aws/``; the provenance lists objects that exist.

The estate is built once per module: each build is ~15s and the renderer is pure.
"""

from __future__ import annotations

import csv
import io
import json
import re
from datetime import UTC
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from tools.synthetic_clouds.fidelity import check, columns_of, is_faithful, load_spec
from tools.synthetic_clouds.generate import constants as const
from tools.synthetic_clouds.generate.estate_builder import build_estate
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.render import cur2_aws, focus_aws
from tools.synthetic_clouds.render.base import get_renderer, registered_names
from tools.synthetic_clouds.render.markers import SYNTH_NAME_PREFIX, unmarked_name
from tools.synthetic_clouds.scenarios.emit import apply_all

_REPO_ROOT = Path(__file__).resolve().parents[3]
# The contract of columns comes from the cited specification, not from a copy of the list.
_SPEC = _REPO_ROOT / "specs" / "aws" / "bcm-data-exports-cur2.schema.json"

# Mirrors s3_reader.py (modulo do consumidor): the reader matches the period partition
# case-insensitively and accepts exactly these data suffixes.
_PARTITION_RE = re.compile(r"(?P<key>[A-Za-z_]+)=(?P<year>\d{4})-(?P<month>\d{2})")
_DATA_SUFFIXES = (".parquet", ".snappy.parquet", ".csv", ".csv.gz")
# The delivery's own names: the partition (BILLING_PERIOD=YYYY-MM) and the execution
# directory a create-new delivery stamps (<timestamp>-<execution-id>).
_PERIOD_RE = re.compile(r"BILLING_PERIOD=\d{4}-\d{2}")
_EXECUTION_RE = re.compile(r"\d{8}T\d{6}Z-[0-9a-f]{8}")
_SIX = Decimal("0.000001")


@pytest.fixture(scope="module")
def estate() -> CanonicalEstate:
    """The fully scenario-applied small estate (AWS scopes included)."""
    return apply_all(build_estate(seed=123, profile="small", currency="USD"))


@pytest.fixture(scope="module")
def rows(estate: CanonicalEstate) -> list[dict[str, str]]:
    """The CSV rows, parsed once (the renderer is pure, so one render is enough)."""
    text = cur2_aws.render_csv_bytes(estate).decode("utf-8")
    parsed = list(csv.DictReader(io.StringIO(text)))
    assert parsed
    return parsed


@pytest.fixture(scope="module")
def tree(estate: CanonicalEstate, tmp_path_factory: pytest.TempPathFactory) -> list[Path]:
    """The rendered export tree, written once for the artifact-level assertions."""
    written = cur2_aws.AwsCur2Renderer().render(estate, tmp_path_factory.mktemp("cur2"))
    assert written
    return written


def _documented() -> tuple[str, ...]:
    """Nomes das colunas na ordem em que a documentacao oficial as declara."""
    return load_spec(_SPEC).names


def _data_objects(written: list[Path]) -> list[Path]:
    return [path for path in written if "/data/" in path.as_posix()]


def _metadata_objects(written: list[Path]) -> list[Path]:
    return [path for path in written if "/metadata/" in path.as_posix()]


# ── the specification contract ───────────────────────────────────────────────


def test_spec_declares_the_131_documented_columns() -> None:
    """The surface is what the module claims: 131 columns, all belonging to the file."""
    spec = load_spec(_SPEC)
    assert spec.surface == cur2_aws.SURFACE == "aws/bcm-data-exports-cur2"
    assert len(spec.columns) == 131, f"spec declares {len(spec.columns)} columns, expected 131"
    assert len(spec.names) == 131
    assert len(set(spec.names)) == 131, "no duplicate column names"
    assert spec.emittable_count == 131, "every documented column belongs to the artifact"


def test_column_set_is_derived_from_the_spec() -> None:
    """``_COLUMNS`` IS the spec's emittable set -- there is no second copy to drift.

    Compared as a SET: in an AWS Data Export the column order comes from the definition's
    own ``SELECT``, not from the provider, so order is not a contract. The tuple does
    follow the documentation's order, which is why that identity is asserted too.
    """
    spec = load_spec(_SPEC)
    assert len(cur2_aws._COLUMNS) == 131
    assert len(set(cur2_aws._COLUMNS)) == 131, "no duplicates"
    assert set(cur2_aws._COLUMNS) == spec.emittable_names
    assert cur2_aws._COLUMNS == spec.names, "the emitted order is the documentation's order"
    assert _documented() == spec.names


def test_no_column_outside_the_format_can_be_emitted() -> None:
    """``unverified``/non-emittable names never reach an artifact."""
    spec = load_spec(_SPEC)
    assert set(cur2_aws._COLUMNS) <= spec.emittable_names
    assert set(cur2_aws._COLUMNS) & spec.forbidden_names == set()


def test_renderer_is_registered() -> None:
    assert "cur2_aws" in registered_names()
    assert get_renderer("cur2_aws").name == "cur2_aws"
    assert isinstance(get_renderer("cur2_aws"), cur2_aws.AwsCur2Renderer)


# ── artifact fidelity: the emitted FILE, not the list in memory ──────────────


def test_parquet_artifact_carries_exactly_the_documented_columns(tree: list[Path]) -> None:
    """The delivered Parquet's OWN schema equals the specification's column set.

    This is the check that cannot be satisfied by agreeing with the renderer: the names
    come from ``columns_of`` reading the Parquet footer, and the comparison is ``check``
    against the cited spec.
    """
    spec = load_spec(_SPEC)
    parts = _data_objects(tree)
    assert parts, "expected at least one data object"
    for part in parts:
        observed = columns_of(part)
        findings = check(spec, observed)
        assert is_faithful(findings), "\n".join(str(finding) for finding in findings)
        assert set(observed) == spec.emittable_names
        assert len(observed) == 131, f"{part.name} carries {len(observed)} columns"
        assert len(set(observed)) == 131, "a column emitted twice is not the same schema"


def test_csv_artifact_carries_exactly_the_documented_columns(
    estate: CanonicalEstate, tmp_path: Path
) -> None:
    """The CSV header is the same contract, measured on the file that was written."""
    spec = load_spec(_SPEC)
    path = tmp_path / "cur2.csv"
    path.write_bytes(cur2_aws.render_csv_bytes(estate))
    observed = columns_of(path)
    findings = check(spec, observed)
    assert is_faithful(findings), "\n".join(str(finding) for finding in findings)
    assert set(observed) == spec.emittable_names
    assert len(observed) == 131


def test_parquet_artifact_declares_every_column_as_a_string(tree: list[Path]) -> None:
    """The encoding decision, asserted on the artifact: every column is a UTF-8 string.

    A ``map`` column handed to pyarrow as a dict would land as a struct and the reader
    would decode garbage -- the trap ``focus_aws`` records for ``Tags``.
    """
    import pyarrow as pa
    import pyarrow.parquet as pq

    part = _data_objects(tree)[0]
    schema = pq.read_schema(part)
    assert set(schema.names) == set(cur2_aws._COLUMNS)
    assert all(field.type == pa.string() for field in schema)


def test_no_column_of_the_null_empty_set_is_filled(rows: list[dict[str, str]]) -> None:
    """A column that belongs to the file but may never carry a value stays empty.

    This surface has none (all 131 columns are generatable), and the assertion is written
    against the spec's own set so it keeps holding if one appears: a ``null-empty`` column
    shipped FILLED is the contract violation the fidelity core separates from mere
    emission.
    """
    spec = load_spec(_SPEC)
    for name in sorted(spec.null_empty_names):
        assert name in cur2_aws._COLUMNS, f"{name} belongs to the file and must be emitted"
        assert all(row[name] == "" for row in rows), f"{name} must be emitted empty"


def test_every_emitted_field_belongs_to_the_format(rows: list[dict[str, str]]) -> None:
    """Every field of every row belongs to the format or can receive a value."""
    spec = load_spec(_SPEC)
    for row in rows[:50]:
        assert set(row) == set(spec.emittable_names)
        assert set(row) & spec.forbidden_names == set()


# ── AWS-lines-only ───────────────────────────────────────────────────────────


def test_emits_aws_lines_only(estate: CanonicalEstate, rows: list[dict[str, str]]) -> None:
    """No foreign provider may leak into the AWS export (``focus_azure``'s precedent)."""
    aws_lines = [line for line in estate.billing_lines if line.service_provider_name == const.PROVIDER_AWS]
    assert len(rows) == len(aws_lines), "row count must equal the AWS billing lines exactly"
    raw = "\n".join(",".join(row[column] for column in sorted(row)) for row in rows)
    assert const.PROVIDER_AZURE not in raw
    assert const.PROVIDER_GCP not in raw
    assert "contoso-prod" not in raw, "no GCP project scope label may appear"


def test_export_columns_carry_no_synth_marker(rows: list[dict[str, str]]) -> None:
    """``[SYNTH] `` is FinOps storage discriminator, not an AWS export value."""
    marker = SYNTH_NAME_PREFIX.strip()
    for row in rows:
        assert marker not in json.dumps(row)
        assert not row["bill_payer_account_name"].startswith(SYNTH_NAME_PREFIX)
        assert not row["line_item_usage_account_name"].startswith(SYNTH_NAME_PREFIX)


# ── value projections, rebuilt from the model ────────────────────────────────


def _aws_model_lines(estate: CanonicalEstate) -> list[Any]:
    """The AWS billing lines in the order the renderer emits them (``line_id``)."""
    return sorted(
        (line for line in estate.billing_lines if line.service_provider_name == const.PROVIDER_AWS),
        key=lambda line: line.line_id,
    )


def _bound_rows(estate: CanonicalEstate, rows: list[dict[str, str]]) -> list[tuple[Any, dict[str, str]]]:
    """Pair each emitted row with its own ``BillingLine``.

    The export carries the model's own ``line_id`` in ``identity_line_item_id`` and that
    identity is asserted, so the pairing does not rest on the ordering alone.
    """
    lines = _aws_model_lines(estate)
    assert len(lines) == len(rows)
    pairs: list[tuple[Any, dict[str, str]]] = []
    for line, row in zip(lines, rows, strict=True):
        assert row["identity_line_item_id"] == line.line_id
        pairs.append((line, row))
    return pairs


def test_identity_is_the_lines_own_natural_key(
    estate: CanonicalEstate, rows: list[dict[str, str]]
) -> None:
    """The line id is the model's key and the interval is the documented ``start/end``."""
    for line, row in _bound_rows(estate, rows):
        start = line.charge_period_start.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        end = line.charge_period_end.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        assert row["identity_time_interval"] == f"{start}/{end}"
        assert row["line_item_usage_start_date"] == start
        assert row["line_item_usage_end_date"] == end
        assert line.line_id not in (start, end)


def test_costs_and_rates_are_projections_of_the_lines_own_costs(
    estate: CanonicalEstate, rows: list[dict[str, str]]
) -> None:
    """Every money column is rebuilt here from the model's Decimals.

    The three cost columns are the line's own ``billed_cost`` (unblended),
    ``effective_cost`` (net, after every discount) and ``list_cost`` (public on-demand),
    and each rate is the corresponding cost divided by the row's own quantity at 6 dp --
    never a literal.
    """
    for line, row in _bound_rows(estate, rows):
        assert row["line_item_unblended_cost"] == str(line.billed_cost.quantize(_SIX))
        assert row["line_item_net_unblended_cost"] == str(line.effective_cost.quantize(_SIX))
        assert row["pricing_public_on_demand_cost"] == str(line.list_cost.quantize(_SIX))
        assert row["line_item_usage_amount"] == str(line.pricing_quantity.quantize(_SIX))
        if line.pricing_quantity != 0:
            for column, cost in (
                ("line_item_unblended_rate", line.billed_cost),
                ("line_item_net_unblended_rate", line.effective_cost),
                ("pricing_public_on_demand_rate", line.list_cost),
            ):
                assert Decimal(row[column]) == (cost / line.pricing_quantity).quantize(_SIX), column
        assert row["line_item_currency_code"] == row["pricing_currency"] == line.currency
        assert row["pricing_unit"] == row["product_pricing_unit"] == line.pricing_unit


def test_the_three_cost_columns_are_three_different_facts(
    estate: CanonicalEstate, rows: list[dict[str, str]]
) -> None:
    """A02's discount moves the NET cost while the amount billed holds.

    Without a row where the three differ, the three columns could be one projection
    repeated three times and the test above would still pass.
    """
    discounted = 0
    for line, row in _bound_rows(estate, rows):
        assert Decimal(row["pricing_public_on_demand_cost"]) == line.list_cost
        if line.effective_cost != line.billed_cost:
            discounted += 1
            assert Decimal(row["line_item_net_unblended_cost"]) != Decimal(
                row["line_item_unblended_cost"]
            )
    assert discounted, "A02 must make the net cost diverge from the billed cost somewhere"


def test_pricing_term_covers_the_documented_closed_domain(
    estate: CanonicalEstate, rows: list[dict[str, str]]
) -> None:
    """``Reserved``/``On-Demand`` is a closed domain, and BOTH literals must be reachable."""
    for line, row in _bound_rows(estate, rows):
        committed = line.commitment_discount_id is not None or line.pricing_category == "Committed"
        assert row["pricing_term"] == ("Reserved" if committed else "On-Demand")
    assert {row["pricing_term"] for row in rows} == {"Reserved", "On-Demand"}


def test_line_item_type_follows_the_rows_own_signals(
    estate: CanonicalEstate, rows: list[dict[str, str]]
) -> None:
    """The literal is derived from the row's category, commitment and pricing tier."""
    commitments = {commitment.identity.uuid for commitment in estate.commitments}
    covered = 0
    for line, row in _bound_rows(estate, rows):
        if line.charge_category == "Usage":
            committed = line.commitment_discount_id is not None or line.pricing_category == "Committed"
            expected = "DiscountedUsage" if committed else "Usage"
        elif line.charge_category == "Purchase":
            expected = "RIFee" if line.commitment_discount_id else "Fee"
        elif line.charge_category == "Tax":
            expected = "Tax"
        elif line.charge_category == "Credit":
            expected = "Credit"
        else:
            expected = "Refund"
        assert row["line_item_line_item_type"] == expected
        if row["line_item_line_item_type"] == "DiscountedUsage":
            covered += 1
            assert (line.commitment_discount_id in commitments) or line.pricing_category == "Committed"
    assert covered, "the estate must carry commitment-covered usage"
    # Every documented literal this projection can use must actually occur, or part of
    # the mapping would be unobservable.
    assert {"Usage", "DiscountedUsage", "RIFee", "Fee", "Tax"} <= {
        row["line_item_line_item_type"] for row in rows
    }


def test_bill_columns_follow_the_documented_domains(rows: list[dict[str, str]]) -> None:
    """The bill columns use the documented literals and the row's own service."""
    assert {row["bill_bill_type"] for row in rows} <= {"Anniversary", "Purchase", "Refund"}
    marketplace = [row for row in rows if row["bill_billing_entity"] == "AWS Marketplace"]
    assert marketplace, "A10 must emit a Marketplace line"
    assert all(row["line_item_legal_entity"] == "" for row in marketplace)
    assert all(row["bill_invoicing_entity"] == "Amazon Web Services, Inc." for row in rows)
    assert all(row["bill_billing_entity"] in {"AWS", "AWS Marketplace"} for row in rows)


def test_invoice_id_is_the_lines_own_invoice(
    estate: CanonicalEstate, rows: list[dict[str, str]]
) -> None:
    """``bill_invoice_id`` is the line's ``invoice_id`` -- empty until the period is issued."""
    for line, row in _bound_rows(estate, rows):
        assert row["bill_invoice_id"] == (line.invoice_id or "")
    assert any(row["bill_invoice_id"] for row in rows), "a closed period must carry its invoice id"


def test_availability_zone_is_derived_from_the_region(
    estate: CanonicalEstate, rows: list[dict[str, str]]
) -> None:
    for line, row in _bound_rows(estate, rows):
        expected = "" if not line.region_id or line.region_id == "global" else f"{line.region_id}a"
        assert row["line_item_availability_zone"] == expected


def test_resource_columns_project_the_resource_and_empty_without_one(
    estate: CanonicalEstate, rows: list[dict[str, str]]
) -> None:
    """The resource-backed columns come from the row's resource, and are empty without one.

    Two ways in, both asserted, exactly as the FOCUS renderer's slice tests do: a row
    whose resource the estate models, and the billing-only constructs (FR-D5 / A01 / A10)
    that have no resource at all.
    """
    resources = {resource.identity.uuid: resource for resource in estate.resources}
    table = const.FOCUS_SERVICE_DESCRIPTIONS[const.PROVIDER_KEY_AWS]
    resource_less = 0
    described = 0
    for line, row in _bound_rows(estate, rows):
        if line.resource_uuid is None:
            resource_less += 1
            for column in (
                "line_item_resource_id",
                "product_sku",
                "product_servicecode",
                "line_item_product_code",
                "line_item_operation",
                "product_operation",
                "line_item_line_item_description",
            ):
                assert row[column] == "", f"{column} must be empty on a resource-less line"
            continue
        resource = resources[line.resource_uuid]
        assert row["line_item_resource_id"] == resource.identity.uuid
        assert row["product_sku"] == resource.sku_id
        assert row["product_servicecode"] == row["line_item_product_code"]
        assert row["product_operation"] == row["line_item_operation"]
        assert row["product_region_code"] == resource.region_id
        assert row["product_location"] == resource.region_name
        assert row["product_product_family"] == resource.service_category
        # The description is the CATALOG's template filled with the row's own values.
        _subcategory, template = table[resource.resource_type]
        assert row["line_item_line_item_description"] == template.format(
            service_name=line.service_name, sku_id=resource.sku_id
        )
        described += 1
    assert resource_less, "the AWS estate must carry its billing-only lines"
    assert described == len(rows) - resource_less


def test_product_columns_carry_the_catalog_operation_and_product_code(
    estate: CanonicalEstate, rows: list[dict[str, str]]
) -> None:
    """The product code and operation reuse the ``focus_aws`` catalog maps.

    The two AWS FinOps exports must agree about a service, so the value is asserted
    against the shared map (rebuilt from the model's own ``resource_type``) rather than
    against this renderer's own output.
    """
    resources = {resource.identity.uuid: resource for resource in estate.resources}
    seen = 0
    for line, row in _bound_rows(estate, rows):
        if line.resource_uuid is None:
            continue
        resource_type = resources[line.resource_uuid].resource_type
        expected_code = focus_aws._SERVICE_CODE.get(resource_type, "")
        expected_operation = focus_aws._OPERATION.get(resource_type, "")
        assert expected_code and expected_operation, resource_type
        assert row["product_servicecode"] == expected_code
        assert row["line_item_product_code"] == expected_code
        assert row["product_operation"] == expected_operation
        assert row["line_item_operation"] == expected_operation
        seen += 1
    assert seen, "no AWS row resolved a catalogued resource"


def test_product_map_carries_the_same_facts_as_the_static_columns(rows: list[dict[str, str]]) -> None:
    """The map is the same projection in the other shape -- and drops empty values."""
    seen = 0
    for row in rows:
        document = json.loads(row["product"])
        assert isinstance(document, dict)
        for legacy, static in cur2_aws._PRODUCT_MAP_KEYS:
            if row[static]:
                assert document[legacy] == row[static]
            else:
                assert legacy not in document
        if document:
            seen += 1
    assert seen == len(rows), "every AWS row has a region and a service, so every map is non-empty"


def test_map_columns_are_json_object_strings(rows: list[dict[str, str]]) -> None:
    """A ``map`` column is a JSON object string -- never a struct, never a bare word."""
    for row in rows:
        for column in ("resource_tags", "tags", "product", "discount", "cost_category"):
            document = json.loads(row[column])
            assert isinstance(document, dict), f"{column} must decode to an object"
            assert all(isinstance(value, str) for value in document.values()), column
        assert row["cost_category"] == "{}", "no cost-category construct is modelled"


def test_tags_carry_the_documented_resource_tag_prefix(
    estate: CanonicalEstate, rows: list[dict[str, str]]
) -> None:
    """``tags`` is the unified map; the one prefix the estate can back is ``resourceTags/``."""
    resources = {resource.identity.uuid: resource for resource in estate.resources}
    tagged = 0
    for line, row in _bound_rows(estate, rows):
        tags = {} if line.resource_uuid is None else dict(resources[line.resource_uuid].tags)
        expected = {key: value for key, value in tags.items() if value}
        assert json.loads(row["resource_tags"]) == expected
        assert json.loads(row["tags"]) == {f"resourceTags/{key}": value for key, value in expected.items()}
        if expected:
            tagged += 1
    assert tagged, "the estate must carry tagged resources"
    assert tagged < len(rows), "the untagged subset must stay untagged"


def test_discount_document_is_the_reduction_between_the_rows_own_costs(
    estate: CanonicalEstate, rows: list[dict[str, str]]
) -> None:
    """The discount map is DERIVED from the row's own money columns, so a reader can check it."""
    with_document = 0
    without = 0
    for line, row in _bound_rows(estate, rows):
        document = json.loads(row["discount"])
        reduction = line.list_cost - line.billed_cost
        if reduction > 0:
            with_document += 1
            assert Decimal(document["ListCost"]) == Decimal(row["pricing_public_on_demand_cost"])
            assert Decimal(document["BilledCost"]) == Decimal(row["line_item_unblended_cost"])
            assert Decimal(document["DiscountAmount"]) == Decimal(row["discount_total_discount"])
            assert Decimal(row["discount_total_discount"]) == reduction.quantize(_SIX)
        else:
            without += 1
            assert row["discount_total_discount"] == ""
    assert with_document, "the base estate is priced below list, so discounts must exist"
    assert without, "the Tax/Purchase billing-only rows are charged their own amount"
    assert any(row["discount"] == "{}" for row in rows)
    for row in rows:
        if row["discount"] == "{}":
            assert Decimal(row["pricing_public_on_demand_cost"]) <= Decimal(row["line_item_unblended_cost"])


def test_capacity_reservation_columns_project_the_resource_reservation(
    estate: CanonicalEstate, rows: list[dict[str, str]]
) -> None:
    """Both columns come from the reservation the row's own resource carries."""
    resources = {resource.identity.uuid: resource for resource in estate.resources}
    populated = 0
    for line, row in _bound_rows(estate, rows):
        reservation = None if line.resource_uuid is None else resources[line.resource_uuid].capacity_reservation
        if reservation is None:
            assert row["capacity_reservation_capacity_reservation_arn"] == ""
            assert row["capacity_reservation_capacity_reservation_status"] == ""
            continue
        populated += 1
        assert row["capacity_reservation_capacity_reservation_arn"] == reservation.reservation_id
        assert row["capacity_reservation_capacity_reservation_status"] == reservation.status
    assert populated, "the estate must model capacity reservations on eligible compute"
    assert populated < len(rows), "the non-reserving rows must not carry one"
    # The type is EMPTY, always: the documented domain is ODCR / EC2 Capacity Blocks for
    # ML, and the model does not distinguish them.
    assert {row["capacity_reservation_capacity_reservation_type"] for row in rows} == {""}


def test_savings_plan_columns_project_the_covering_commitment(
    estate: CanonicalEstate, rows: list[dict[str, str]]
) -> None:
    """A covered row names the commitment that covers it, term included."""
    commitments = {commitment.identity.uuid: commitment for commitment in estate.commitments}
    covered = 0
    for line, row in _bound_rows(estate, rows):
        commitment = commitments.get(line.commitment_discount_id or "")
        if commitment is None or commitment.kind != "savings_plan":
            assert row["savings_plan_savings_plan_a_r_n"] == ""
            assert row["savings_plan_start_time"] == ""
            assert row["savings_plan_end_time"] == ""
            assert row["savings_plan_region"] == ""
            continue
        covered += 1
        assert row["savings_plan_savings_plan_a_r_n"] == commitment.identity.uuid
        assert row["savings_plan_start_time"] == commitment.period_start.isoformat()
        assert row["savings_plan_end_time"] == commitment.period_end.isoformat()
        assert row["savings_plan_region"] == line.region_id
    assert covered, "the estate must cover usage with an AWS Savings Plan"


def test_no_aws_row_carries_a_reserved_instance_lease(
    estate: CanonicalEstate, rows: list[dict[str, str]]
) -> None:
    """The reservation group is empty because no AWS line names a reservation.

    ``constants.COMMITMENT_KIND`` gives AWS a Savings Plan, so the reserved-instance
    group has no line to describe. Asserting it here makes the emptiness a measured fact
    of the ESTATE rather than a claim in a docstring -- and it is what would break first
    if a scenario ever emitted an AWS Reserved Instance.
    """
    all_commitments = list(estate.commitments)
    assert all_commitments, "the estate carries commitments"
    assert all(commitment.kind != "reservation" for commitment in all_commitments)
    for row in rows:
        for column in (
            "reservation_reservation_a_r_n",
            "reservation_start_time",
            "reservation_end_time",
            "reservation_total_reserved_units",
            "reservation_unused_quantity",
            "reservation_availability_zone",
        ):
            assert row[column] == "", column


def test_account_columns_are_projected_unmarked(
    estate: CanonicalEstate, rows: list[dict[str, str]]
) -> None:
    billing_accounts = {b.billing_account_id: unmarked_name(b.name) for b in estate.billing_accounts}
    sub_accounts = {a.account_id: unmarked_name(a.name) for org in estate.aws_orgs for a in org.accounts}
    for line, row in _bound_rows(estate, rows):
        assert row["bill_payer_account_id"] == line.billing_account_id
        assert row["bill_payer_account_name"] == billing_accounts[line.billing_account_id]
        assert row["line_item_usage_account_id"] == line.sub_account_id
        assert row["line_item_usage_account_name"] == sub_accounts[line.sub_account_id]
    assert all(row["bill_payer_account_name"] and row["line_item_usage_account_name"] for row in rows)


def test_pricing_rate_id_is_the_price_identity_of_the_sku(
    estate: CanonicalEstate, rows: list[dict[str, str]]
) -> None:
    """The rate id groups rows by price, and is empty for a row with no priced SKU."""
    resources = {resource.identity.uuid: resource for resource in estate.resources}
    priced = {price.sku_id for price in estate.list_prices} | {
        price.sku_id for price in estate.contracted_prices
    }
    populated = 0
    for line, row in _bound_rows(estate, rows):
        if line.resource_uuid is None:
            assert row["pricing_rate_id"] == ""
            assert row["pricing_rate_code"] == ""
            continue
        sku_id = resources[line.resource_uuid].sku_id
        assert row["product_sku"] == sku_id
        if sku_id in priced:
            populated += 1
            assert row["pricing_rate_id"]
            assert row["pricing_rate_id"] != sku_id, "a price identity is not a copy of the SKU id"
        else:
            assert row["pricing_rate_id"] == ""
    assert populated, "no AWS row resolved a priced SKU"
    assert populated < len(rows), "the billing-only rows carry no price identity"


# ── delivery layout ──────────────────────────────────────────────────────────


def test_s3_key_matches_the_documented_create_new_layout() -> None:
    key = cur2_aws.s3_key(
        billing_period="2026-01",
        execution="20260101T000000Z-abcdef01",
        filename="synthetic-cur2-daily-full-00001.snappy.parquet",
    )
    assert key == (
        "cur2-full/synthetic-cur2-daily-full/data/BILLING_PERIOD=2026-01/"
        "20260101T000000Z-abcdef01/synthetic-cur2-daily-full-00001.snappy.parquet"
    )
    assert key.endswith(_DATA_SUFFIXES)


def test_partition_key_matches_in_the_documented_casing() -> None:
    """The spec states ``BILLING_PERIOD``; the reader matches the period case-insensitively."""
    assert cur2_aws.PARTITION_KEY == "BILLING_PERIOD"
    for casing in (cur2_aws.PARTITION_KEY, cur2_aws.PARTITION_KEY.lower()):
        key = cur2_aws.s3_key(
            billing_period="2026-07",
            execution="e",
            filename="part-00001.snappy.parquet",
            partition_key=casing,
        )
        match = _PARTITION_RE.search(key)
        assert match, f"the reader's period regex must match {key!r}"
        assert (match.group("year"), match.group("month")) == ("2026", "07")


def test_the_documented_metadata_prefix_is_not_populated() -> None:
    """O prefixo ``metadata/`` e a forma documentada do layout, e fica VAZIO.

    A spec descreve o manifesto e o CONTEUDO dele em prosa, mas registra que a AWS nao
    publica schema, lista de chaves nem exemplo -- toda chave exceto
    ``additionalOutputFiles`` e nao comprovada. Um manifesto e um DOCUMENTO: escreve-lo
    exige NOMEAR os campos, e os nomes sao exatamente o que a documentacao nao estabelece.
    O ``s3_key`` continua construindo os dois caminhos documentados (o teste os constroi,
    para provar a forma), e o renderer nao grava nada neles.
    """
    execution_scoped = cur2_aws.s3_key(
        billing_period="2026-01",
        execution="20260101T000000Z-abcdef01",
        filename=f"{cur2_aws.EXPORT_NAME}-Manifest.json",
        kind="metadata",
    )
    latest = cur2_aws.s3_key(
        billing_period="2026-01",
        filename=f"{cur2_aws.EXPORT_NAME}-Manifest.json",
        kind="metadata",
    )
    assert "/metadata/BILLING_PERIOD=2026-01/20260101T000000Z-abcdef01/" in execution_scoped
    assert latest == (
        "cur2-full/synthetic-cur2-daily-full/metadata/BILLING_PERIOD=2026-01/"
        "synthetic-cur2-daily-full-Manifest.json"
    )
    assert "/data/" not in latest


def test_tree_is_written_under_the_render_dir(tree: list[Path]) -> None:
    """NFR-4 write boundary: everything lands under out_dir/cur2_aws/."""
    for path in tree:
        assert path.exists()
        assert cur2_aws.RENDER_DIR in path.parts, f"{path} escaped the render dir"
    data = _data_objects(tree)
    assert data, "expected at least one data object"
    assert all(re.search(r"-\d{5}\.snappy\.parquet$", path.name) for path in data)
    assert all(_EXECUTION_RE.fullmatch(path.parent.name) for path in data), "an execution directory"
    assert all(_PERIOD_RE.fullmatch(path.parent.parent.name) for path in data)
    assert not _metadata_objects(tree), "o manifesto nao e entregue"


def test_the_export_tree_carries_data_and_provenance_only(tree: list[Path]) -> None:
    """O JSON que sobra no diretorio e o NOSSO, e so ele: nenhum documento de schema escolhido.

    O nome comecado por ``_`` e a convencao do pacote para um documento nosso, e e o que o
    mantem fora do artefato entregue. Qualquer OUTRO arquivo tem de ser dado do export.
    """
    others = [path for path in tree if path.name != cur2_aws.PROVENANCE_FILE]
    assert all(path.suffix == ".parquet" for path in others), "so dado entregue, alem do provenance"
    assert all("/data/" in path.as_posix() for path in others), "nada fora do prefixo documentado"
    provenance = [path for path in tree if path.name == cur2_aws.PROVENANCE_FILE]
    assert len(provenance) == 1, "um relatorio de proveniencia por exportacao"
    document = json.loads(provenance[0].read_text(encoding="utf-8"))
    assert document["kind"] == "provenance"
    assert document["surface"] == cur2_aws.SURFACE
    assert document["mechanism"]["manifest_delivered"] is False
    assert document["mechanism"]["partition_key"] == "BILLING_PERIOD"
    # A secao da PROPRIA spec, verbatim: a lacuna fica registrada com o texto da evidencia.
    assert document["manifest"]["confirmed_keys"] == ["additionalOutputFiles"]
    assert "UNVERIFIED" in document["manifest"]["notes"]


def test_no_delivered_document_carries_an_undocumented_key(
    estate: CanonicalEstate, tmp_path: Path
) -> None:
    """A regra de ouro no nivel do DOCUMENTO: ou e dado com coluna da spec, ou e o NOSSO proveniencia.

    Se alguem voltar a gravar um manifesto dentro do export, este teste falha por dois
    motivos independentes: o arquivo nao e o ``_provenance.json`` e e um ``.json``; e as
    chaves dele nao sao colunas da especificacao, o que ``check`` acusa como inventado.
    """
    spec = load_spec(_SPEC)
    written = cur2_aws.AwsCur2Renderer().render(estate, tmp_path)
    for path in written:
        if path.name == cur2_aws.PROVENANCE_FILE:
            continue
        assert path.suffix != ".json", f"{path.name}: documento com schema escolhido dentro do export"
        findings = check(spec, columns_of(path))
        assert is_faithful(findings), f"{path.name}: " + "; ".join(str(finding) for finding in findings)


def test_provenance_lists_every_delivered_object_and_they_all_exist(
    estate: CanonicalEstate, tmp_path: Path
) -> None:
    """Sem manifesto, o registro irmao e o unico lugar onde o run fica documentado.

    Ele tem de bater com o disco: cada objeto listado, o tamanho, a contagem de linhas e o
    total -- e a contagem de execucoes por periodo tem de mostrar que uma entrega A04/A06
    aconteceu de fato.
    """
    written = cur2_aws.AwsCur2Renderer().render(estate, tmp_path)
    provenance = next(path for path in written if path.name == cur2_aws.PROVENANCE_FILE)
    document = json.loads(provenance.read_text(encoding="utf-8"))
    parts = [path for path in written if path.suffix == ".parquet"]
    assert document["totals"]["objects"] == len(document["objects"]) == len(parts)
    assert document["columns"]["emitted"] == 131
    assert document["columns"]["schema_fingerprint"] == cur2_aws.schema_fingerprint()
    assert document["manifest"]["status"] == "partial"
    for entry in document["objects"]:
        part = next((path for path in parts if path.as_posix().endswith(entry["key"])), None)
        assert part is not None, f"a proveniencia lista um objeto ausente: {entry['key']}"
        assert part.stat().st_size == entry["bytes"]
        assert entry["key"].endswith(".snappy.parquet") and "/data/" in entry["key"]
    executions = {(_period_of(path), _execution_of(path)) for path in parts}
    periods = {_period_of(path) for path in parts}
    assert len(executions) > len(periods), "A04/A06 must deliver a restated period twice"


def test_render_is_deterministic(estate: CanonicalEstate, tmp_path: Path) -> None:
    first = cur2_aws.AwsCur2Renderer().render(estate, tmp_path / "a")
    second = cur2_aws.AwsCur2Renderer().render(estate, tmp_path / "b")
    assert [p.relative_to(tmp_path / "a") for p in first] == [p.relative_to(tmp_path / "b") for p in second]
    for left, right in zip(first, second, strict=True):
        assert left.read_bytes() == right.read_bytes(), f"{left.name} is not byte-stable"


def test_schema_fingerprint_is_not_synth_prefixed() -> None:
    """``synth:`` marks synthetic DATA; a real schema hash must not carry it."""
    assert not cur2_aws.schema_fingerprint().startswith("synth:")
    assert re.fullmatch(r"[0-9a-f]{64}", cur2_aws.schema_fingerprint())


def _period_of(path: Path) -> str:
    """``…/BILLING_PERIOD=YYYY-MM/<execution>/<file>`` -> ``YYYY-MM``."""
    return path.parent.parent.name.split("=", 1)[1]


def _execution_of(path: Path) -> str:
    return path.parent.name
