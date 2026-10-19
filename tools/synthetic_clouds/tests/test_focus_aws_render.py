"""Phase 6 / AC-3, AC-4, AC-5, AC-6: the ``focus_aws`` renderer.

Five axes:
  * **Column fidelity (AC-3):** the emitted columns are the 60 the cited specification
    declares — measured on the file the renderer actually wrote (``columns_of`` over the
    Parquet and the CSV), compared with ``check`` against ``spec.emittable_names``, never
    against the list in memory.
  * **Artifact vs provenance:** the delivered tree holds DATA plus the sibling
    ``_provenance.json``, and NOT the manifest AWS also documents: its key names are the
    one thing the documentation does not establish. The tests below fail if a key the
    spec does not document ever returns to a delivered artifact.
  * **Ingestion acceptance (AC-4):** the emitted Parquet and CSV feed the REAL
    ``parser.py (modulo do consumidor)`` -> dialect ``focus``, and all three aggregate entry
    points parse them.
  * **Tags (AC-5):** both encodings decode to the expected ``dict[str, str]`` through
    the only parser function that reads Tags.
  * **S3 layout (AC-6):** the BCM key shape, both partition-key casings, the five-digit
    chunk names, and every object the provenance lists existing on disk.

The estate is built once per module: each build is ~15s and the renderer is pure, so
rebuilding per test would cost minutes for no coverage.
"""

from __future__ import annotations

import json
import re
import string
from dataclasses import replace
from datetime import UTC, date
from decimal import Decimal
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from tools.synthetic_clouds.determinism import identity_for
from tools.synthetic_clouds.fidelity import check, columns_of, is_faithful
from tools.synthetic_clouds.fidelity.spec import load_spec
from tools.synthetic_clouds.generate import constants as const
from tools.synthetic_clouds.generate.estate_builder import build_estate
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.identity import IdentityFactory, capacity_reservation_id
from tools.synthetic_clouds.render import focus_aws
from tools.synthetic_clouds.render.base import get_renderer, registered_names
from tools.synthetic_clouds.render.markers import SYNTH_NAME_PREFIX, unmarked_name
from tools.synthetic_clouds.scenarios.emit import apply_all

_REPO_ROOT = Path(__file__).resolve().parents[3]
# O contrato de colunas vem da especificacao citada, nao de uma copia da lista.
# Substitui o antigo arquivo ancora ``scripts/aws/focus12-full-export.json``, que
# vivia na arvore do produto FinOps: assim o renderer e conferido contra a
# documentacao oficial em vez de contra uma copia de si mesmo.
_SPEC = _REPO_ROOT / "specs" / "aws" / "bcm-data-exports-focus12.schema.json"

# Mirrors the patterns in s3_reader.py (modulo do consumidor):41-48. The reader matches the
# period partition case-insensitively and accepts exactly these suffixes.
_PARTITION_RE = re.compile(r"billing_period=(\d{4})-(\d{2})", re.IGNORECASE)
_DATA_SUFFIXES = (".parquet", ".snappy.parquet", ".csv", ".csv.gz")


@pytest.fixture(scope="module")
def estate() -> CanonicalEstate:
    """The fully scenario-applied small estate (AWS scopes included)."""
    return apply_all(build_estate(seed=123, profile="small", currency="USD"))


def _documented_columns() -> tuple[str, ...]:
    """Nomes das colunas na ordem em que a documentacao oficial os declara."""
    return load_spec(_SPEC).names


# ── AC-3 column fidelity ─────────────────────────────────────────────────────


def test_column_set_matches_the_export_definition() -> None:
    """The emitted columns ARE the documented columns — read from the spec itself.

    Compara CONJUNTO, nao ordem. Na AWS a ordem das colunas de um Data Export e
    definida pela propria definicao do export (o ``SELECT``), nao pelo provedor:
    a tabela da documentacao lista as colunas em ordem propria, que nao e um
    contrato de entrega. Exigir essa ordem seria inventar um contrato que a AWS
    nao publica. Onde a ordem E contratual (CSV com ordem fixa publicada), a
    verificacao usa ``check(..., ordered=True)``.

    O conjunto e o ``emittable`` da spec -- a coluna PERTENCE ao artefato --, nao o
    ``generatable``: uma coluna que a documentacao declara existir e nunca ter valor tem
    de ser emitida VAZIA, e omiti-la seria tao infiel quanto preenche-la.
    """
    spec = load_spec(_SPEC)
    documented = _documented_columns()
    assert len(documented) == 60, f"spec declares {len(documented)} columns, expected 60"
    assert set(focus_aws._COLUMNS) == set(documented)
    assert set(focus_aws._COLUMNS) == spec.emittable_names
    assert len(focus_aws._COLUMNS) == 60
    assert len(set(focus_aws._COLUMNS)) == 60, "no duplicates"


# ── artifact fidelity: the emitted FILE, not the list in memory ──────────────


def test_parquet_artifact_carries_exactly_the_documented_columns(
    estate: CanonicalEstate, tmp_path: Path
) -> None:
    """O schema do Parquet ENTREGUE e o da especificacao citada, medido no arquivo.

    Nomes vindos de ``columns_of`` (o rodape do Parquet), comparados com ``check``
    contra a spec. Nao ha como este teste passar por concordar com o renderer: a lista
    em memoria nao entra na medicao.
    """
    spec = load_spec(_SPEC)
    written = focus_aws.AwsFocusRenderer().render(estate, tmp_path)
    parts = [path for path in written if "/data/" in path.as_posix()]
    assert parts, "expected at least one data object"
    for part in parts:
        observed = columns_of(part)
        findings = check(spec, observed)
        assert is_faithful(findings), "\n".join(str(finding) for finding in findings)
        assert set(observed) == spec.emittable_names
        assert len(observed) == 60, f"{part.name} carries {len(observed)} columns"
        assert len(set(observed)) == 60, "a column emitted twice is not the same schema"


def test_csv_artifact_carries_exactly_the_documented_columns(
    estate: CanonicalEstate, tmp_path: Path
) -> None:
    """O cabecalho do CSV e o mesmo contrato, medido no arquivo escrito."""
    spec = load_spec(_SPEC)
    path = tmp_path / "focus_aws.csv"
    path.write_bytes(focus_aws.render_csv_bytes(estate))
    observed = columns_of(path)
    findings = check(spec, observed)
    assert is_faithful(findings), "\n".join(str(finding) for finding in findings)
    assert set(observed) == spec.emittable_names
    assert len(observed) == 60


def test_no_column_of_the_null_empty_set_is_filled(estate: CanonicalEstate) -> None:
    """Coluna que pertence ao arquivo e nunca pode ter valor sai VAZIA.

    Nesta superficie nao ha nenhuma (as 60 sao geraveis), e a afirmacao e feita contra o
    conjunto da propria spec: emitir uma coluna ``null-empty`` PREENCHIDA e a violacao de
    contrato que o nucleo de fidelidade separa da simples emissao.
    """
    spec = load_spec(_SPEC)
    rows = _csv_rows(estate)
    for name in sorted(spec.null_empty_names):
        assert name in focus_aws._COLUMNS, f"{name} pertence ao arquivo e tem de ser emitida"
        assert all(row[name] == "" for row in rows), f"{name} must be emitted empty"


def test_aws_extension_columns_are_present() -> None:
    for column in ("x_Discounts", "x_Operation", "x_ServiceCode"):
        assert column in focus_aws._COLUMNS


def test_renderer_is_registered() -> None:
    assert "focus_aws" in registered_names()
    assert get_renderer("focus_aws").name == "focus_aws"


# ── AWS-lines-only ───────────────────────────────────────────────────────────


def test_emits_aws_lines_only(estate: CanonicalEstate) -> None:
    """No foreign provider may leak into the AWS export (focus_azure's precedent)."""
    raw = focus_aws.render_csv_bytes(estate)
    header, *lines = raw.decode("utf-8").splitlines()
    assert header.split(",")[0] == "AvailabilityZone"
    aws_lines = [line for line in estate.billing_lines if line.service_provider_name == "Amazon Web Services"]
    assert len(lines) == len(aws_lines), "row count must equal the AWS billing lines exactly"
    assert "Microsoft Azure" not in raw.decode("utf-8")
    assert "Google Cloud" not in raw.decode("utf-8")
    assert "contoso-prod" not in raw.decode("utf-8"), "no GCP project scope label may appear"


def test_null_resource_line_has_empty_resource_id(estate: CanonicalEstate) -> None:
    """FR-D5: the resource-less lines emit an empty FOCUS ResourceId, not a sentinel.

    Scoped to the AWS resource-less lines on purpose. The estate's 181 resource-less
    rows include 46 that are NOT AWS (Azure's FR-D5 tax line plus its 45 C05 unused
    commitment lines); asserting against the estate-wide count would be asserting
    that the export leaks another provider, which is the opposite of the contract.
    """
    aws_none = [
        line
        for line in estate.billing_lines
        if line.resource_uuid is None and line.service_provider_name == "Amazon Web Services"
    ]
    assert aws_none, "the AWS estate must carry its A01/A10 billing-only lines"
    assert len(aws_none) < len([b for b in estate.billing_lines if b.resource_uuid is None])
    rows = [row for row in _csv_rows(estate) if row["ResourceId"] == ""]
    assert len(rows) == len(aws_none)


def test_money_and_dates_are_formatted(estate: CanonicalEstate) -> None:
    row = next(row for row in _csv_rows(estate) if row["BilledCost"])
    assert re.fullmatch(r"-?\d+\.\d{6}", row["BilledCost"]), row["BilledCost"]
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", row["BillingPeriodStart"])
    assert "T" in row["ChargePeriodStart"]


# ── export fidelity: no FinOps marker in an export column ─────────────────


def test_export_columns_carry_no_synth_marker(estate: CanonicalEstate) -> None:
    """``[SYNTH] `` is FinOps storage discriminator, not an AWS export value.

    ``seed/cleanup.py`` recognises the seed's own rows by
    ``cloud_accounts.name LIKE '[SYNTH] %'``, so the prefix has to stay on the estate
    (see ``test_seed_side_names_keep_the_marker``) — and must never reach a FOCUS
    column, where no real AWS export could produce it.
    """
    raw = focus_aws.render_csv_bytes(estate).decode("utf-8")
    assert SYNTH_NAME_PREFIX.strip() not in raw
    for row in _csv_rows(estate):
        assert not row["BillingAccountName"].startswith(SYNTH_NAME_PREFIX)
        assert not row["SubAccountName"].startswith(SYNTH_NAME_PREFIX)


def test_account_name_columns_are_populated_and_unmarked(estate: CanonicalEstate) -> None:
    """The fix must not be "empty the column": the estate DOES model both names."""
    aws_lines = [
        line for line in estate.billing_lines if line.service_provider_name == "Amazon Web Services"
    ]
    billing_accounts = {b.billing_account_id: unmarked_name(b.name) for b in estate.billing_accounts}
    sub_accounts = {
        a.account_id: unmarked_name(a.name) for org in estate.aws_orgs for a in org.accounts
    }
    rows = _csv_rows(estate)
    assert rows
    assert {row["BillingAccountName"] for row in rows} == {
        billing_accounts[line.billing_account_id] for line in aws_lines
    }
    assert {row["SubAccountName"] for row in rows} == {
        sub_accounts[line.sub_account_id] for line in aws_lines
    }
    assert all(row["BillingAccountName"] and row["SubAccountName"] for row in rows)


def test_seed_side_names_keep_the_marker(estate: CanonicalEstate) -> None:
    """The cleanup discriminator is load-bearing: the estate keeps ``[SYNTH] ``."""
    assert all(b.name.startswith(SYNTH_NAME_PREFIX) for b in estate.billing_accounts)
    assert all(
        a.name.startswith(SYNTH_NAME_PREFIX) for org in estate.aws_orgs for a in org.accounts
    )


def test_service_code_and_operation_cover_the_aws_catalog() -> None:
    """Every catalogued AWS resource type resolves both ``x_*`` columns.

    The maps covered 8 of the catalog's 15 types, so LAMBDA/EIP/ALB/VPC/SG/DynamoDB/ECS
    rows shipped an EMPTY ``x_ServiceCode``/``x_Operation`` — an absence a reader cannot
    tell apart from a gap in the simulator.
    """
    catalogued = {entry[0] for entry in const.AWS_SERVICES}
    assert catalogued - focus_aws._SERVICE_CODE.keys() == set()
    assert catalogued - focus_aws._OPERATION.keys() == set()
    assert set(focus_aws._SERVICE_CODE) == set(focus_aws._OPERATION), "the two maps must key alike"


def test_no_column_of_the_sixty_stays_empty(estate: CanonicalEstate) -> None:
    """Absence is absence — and after Phase 7 there is no column left to be absent.

    This test carried a WHITELIST until slice 5: ``test_columns_with_no_canonical_source_stay_empty``
    asserted a shrinking tuple of columns the estate did not model (sixteen when the
    phase opened; ``x_Discounts`` alone by slice 4). Slice 5 gave the last one a derived
    source, so the whitelist is now empty and asserting it would assert nothing. The
    invariant is therefore stated directly, which is the stronger claim and the one the
    whitelist existed to protect: NO column of the 60 ships empty on every row of this
    estate. A future slice that empties a column instead of modelling it fails here.

    ``ChargeClass`` and ``InvoiceId`` are populated in THIS estate — a scenario-applied
    one with a month-spanning window — and the two tests named in the module's Slice 6
    section prove that the rows carrying them are exactly the modelled ones, and that a
    month-to-date window is why the daily export leaves both empty.
    """
    rows = _csv_rows(estate)
    assert rows
    all_empty = sorted(column for column in focus_aws._COLUMNS if not any(row[column] for row in rows))
    assert all_empty == [], f"columns empty on every row, with no modelled reason: {all_empty}"


# ── Slice 1: commitment coverage on the base estate ──────────────────────────


def test_commitment_columns_are_populated_from_the_commitment(estate: CanonicalEstate) -> None:
    """A covered row describes the commitment its id names, field for field.

    The seven ``CommitmentDiscount*`` columns are one projection of ONE
    ``Commitment``, so this asserts them against that model row instead of against a
    literal: id, status, name, quantity, unit and type/category all come from it.
    """
    commitments = {c.identity.uuid: c for c in estate.commitments}
    covered = [
        row
        for row in _csv_rows(estate)
        if row["CommitmentDiscountId"] and row["CommitmentDiscountId"] in commitments
    ]
    assert covered, "no row carried a commitment the estate models"
    for row in covered:
        commitment = commitments[row["CommitmentDiscountId"]]
        assert row["CommitmentDiscountName"] == unmarked_name(commitment.name)
        assert row["CommitmentDiscountQuantity"] == str(commitment.quantity)
        assert row["CommitmentDiscountUnit"] == commitment.unit
        assert row["CommitmentDiscountType"] == commitment.kind
        assert row["CommitmentDiscountCategory"] == focus_aws._COMMITMENT_CATEGORY[commitment.kind]
        assert not row["CommitmentDiscountName"].startswith(SYNTH_NAME_PREFIX)
        # The covered usage is what a savings plan actually pays for; the Unused rows
        # beside it are the scenario emitter's RIFee lines (A01), which is exactly the
        # partially-used commitment the scenario declares.
        expected = "Used" if row["ChargeCategory"] == "Usage" else "Unused"
        assert row["CommitmentDiscountStatus"] == expected
    assert any(row["CommitmentDiscountStatus"] == "Unused" for row in covered), "A01's unused half"


def test_uncovered_rows_carry_no_commitment_columns(estate: CanonicalEstate) -> None:
    """The uncovered half of the estate stays empty — coverage is partial, not total."""
    rows = _csv_rows(estate)
    uncovered = [row for row in rows if not row["CommitmentDiscountId"]]
    assert uncovered, "every line covered would be as unfaithful as none covered"
    for row in uncovered:
        for column in (
            "CommitmentDiscountName",
            "CommitmentDiscountQuantity",
            "CommitmentDiscountStatus",
            "CommitmentDiscountType",
            "CommitmentDiscountCategory",
            "CommitmentDiscountUnit",
        ):
            assert row[column] == "", f"{column} must be empty when no commitment covers the line"


def test_base_estate_usage_coverage_is_partial_and_derived() -> None:
    """The BASE (pre-scenario) estate: realistic coverage, every id a real commitment.

    ``derive, never invent`` — so every non-empty id must name a ``Commitment`` the
    estate carries (A01/C05's rows are appended by the scenario emitter and are not
    part of the base estate this test builds).
    """
    base = build_estate(seed=123, profile="small", currency="USD")
    by_id = {c.identity.uuid: c for c in base.commitments}
    usage = [line for line in base.billing_lines if line.charge_category == "Usage"]
    covered = [line for line in usage if line.commitment_discount_id]
    assert covered, "the base estate must carry covered usage"
    assert len(covered) < len(usage), "not every usage line may be covered"
    for line in covered:
        assert line.commitment_discount_id in by_id
        assert line.commitment_discount_status == "Used"
        # Coverage never reaches outside the set the commitment can cover: the line's
        # metered unit is the unit the commitment is expressed in.
        assert line.pricing_unit == by_id[line.commitment_discount_id].unit
    for line in usage:
        if line.commitment_discount_id is None:
            assert line.commitment_discount_status is None, "no id, no status"
    # The commitment's quantity is the metered amount it covers, in its own unit —
    # a projection of the covered lines, not a second independent number. FR-D4's
    # benign duplicate copies are excluded: they restate usage the commitment already
    # counted, and the builder sizes each commitment before the duplicates are made.
    for commitment in base.commitments:
        covered_quantity = sum(
            (
                line.pricing_quantity
                for line in covered
                if line.commitment_discount_id == commitment.identity.uuid and not line.is_duplicate
            ),
            Decimal("0"),
        )
        assert commitment.quantity == covered_quantity.quantize(const.SIX_DP)
        assert commitment.status == ("Used" if commitment.quantity > 0 else "Unused")
        assert commitment.unit == const.COMMITMENT_UNIT[commitment.kind]
        assert commitment.name


def test_coverage_is_byte_stable_per_seed() -> None:
    """Same seed => same covered set, so a re-run cannot shuffle which lines are covered."""
    first = build_estate(seed=123, profile="small", currency="USD")
    second = build_estate(seed=123, profile="small", currency="USD")
    assert [(b.line_id, b.commitment_discount_id, b.commitment_discount_status) for b in first.billing_lines] == [
        (b.line_id, b.commitment_discount_id, b.commitment_discount_status) for b in second.billing_lines
    ]
    assert [(c.identity.uuid, c.quantity) for c in first.commitments] == [
        (c.identity.uuid, c.quantity) for c in second.commitments
    ]


# ── Slice 2: descriptive columns from the catalog, never from the renderer ───


def test_descriptive_catalog_covers_the_aws_catalog_exactly() -> None:
    """Every catalogued AWS service is described, and nothing outside it is.

    A missing entry would emit an empty column for a service the estate DOES model —
    the absence a reader cannot tell apart from a gap in the simulator.
    """
    table = const.FOCUS_SERVICE_DESCRIPTIONS[const.PROVIDER_KEY_AWS]
    catalogued = {entry[0] for entry in const.AWS_SERVICES}
    assert catalogued - table.keys() == set(), "a catalogued AWS resource type has no description"
    assert table.keys() == catalogued, "a description names a resource type the catalog does not model"


def test_descriptive_templates_reference_model_values_only() -> None:
    """A template may only be filled from the row's OWN values.

    This is the guard that keeps a renderer string from creeping into the catalog: the
    only fields a template may name are the line's ``service_name`` and the resource's
    ``sku_id``. ``resource_type`` is excluded on purpose — it is the simulator's own
    snake_case token and has no place in an export column.
    """
    table = const.FOCUS_SERVICE_DESCRIPTIONS[const.PROVIDER_KEY_AWS]
    for subcategory, template in table.values():
        assert subcategory, "an entry with no ServiceSubcategory describes nothing"
        fields = {name for _, name, _, _ in string.Formatter().parse(template) if name}
        assert fields, f"{template!r} uses no model value"
        assert fields <= {"service_name", "sku_id"}, f"{template!r} names {sorted(fields - {'service_name', 'sku_id'})}"


def test_descriptive_columns_are_projected_from_the_catalog(estate: CanonicalEstate) -> None:
    """A catalogued row carries the catalog's subcategory and its filled description.

    The expectation is rebuilt from the MODEL and the catalog table — the resource's
    ``resource_type``/``sku_id`` plus the row's own emitted ``ServiceName`` — so the test
    cannot pass by agreeing with the renderer's own lookup.
    """
    table = const.FOCUS_SERVICE_DESCRIPTIONS[const.PROVIDER_KEY_AWS]
    resources = {resource.identity.uuid: resource for resource in estate.resources}
    rows = _csv_rows(estate)
    assert rows
    described = 0
    for row in rows:
        if not row["ResourceId"]:
            # No resource -> no catalogued service -> both columns empty (asserted by
            # test_unlisted_service_emits_empty_descriptive_columns too).
            assert row["ServiceSubcategory"] == ""
            assert row["ChargeDescription"] == ""
            continue
        resource = resources[row["ResourceId"]]
        subcategory, template = table[resource.resource_type]
        assert row["ServiceSubcategory"] == subcategory
        assert row["ChargeDescription"] == template.format(service_name=row["ServiceName"], sku_id=resource.sku_id)
        assert row["ServiceSubcategory"], "a catalogued row must not ship an empty subcategory"
        described += 1
    assert described, "no AWS row resolved a catalogued resource"
    # Exactly the resource-backed rows are described: a row with a resource always found
    # its catalog entry, and no resource-less row was described by accident.
    assert described == len(rows) - len([row for row in rows if not row["ResourceId"]])


def test_unlisted_service_emits_empty_descriptive_columns(estate: CanonicalEstate) -> None:
    """Absence is absence: a service the catalog does not describe gets no string.

    Two ways in, both asserted: a resource whose type is not a catalog entry, and the
    resource-less billing-only constructs (A01's reservation fee, A10's Marketplace and
    Support lines) whose service names no catalog entry carries.
    """
    lookups = focus_aws._Lookups(estate)
    line = next(
        line
        for line in estate.billing_lines
        if line.resource_uuid and line.service_provider_name == "Amazon Web Services"
    )
    assert line.resource_uuid is not None
    catalogued = lookups.resource_by_uuid[line.resource_uuid]
    lookups.resource_by_uuid[line.resource_uuid] = replace(catalogued, resource_type="not_a_catalog_service")
    unlisted = focus_aws._record(line, lookups)
    assert unlisted["ServiceSubcategory"] == ""
    assert unlisted["ChargeDescription"] == ""

    resource_less = next(
        line
        for line in estate.billing_lines
        if line.resource_uuid is None and line.service_provider_name == "Amazon Web Services"
    )
    record = focus_aws._record(resource_less, lookups)
    assert record["ServiceSubcategory"] == ""
    assert record["ChargeDescription"] == ""


# ── Slice 3: the SKU price identity, projected from the estate's price book ──


def _price_book(estate: CanonicalEstate) -> tuple[dict[str, Any], dict[str, Any]]:
    """The estate's own prices, keyed by ``sku_id`` (one row per SKU)."""
    return (
        {price.sku_id: price for price in estate.list_prices},
        {price.sku_id: price for price in estate.contracted_prices},
    )


def test_sku_price_columns_are_projected_from_the_estate_price_book(estate: CanonicalEstate) -> None:
    """Both columns are rebuilt here from MODEL rows, so this cannot agree by accident.

    ``SkuPriceId`` is the UUIDv5 of ``(sku_id, the row's currency, its pricing tier)``
    and ``SkuPriceDetails`` is the JSON string of the ``ListPrice``/``ContractedPrice``
    the estate holds for that SKU. Neither value is asserted against a literal.
    """
    resources = {resource.identity.uuid: resource for resource in estate.resources}
    list_prices, contracted_prices = _price_book(estate)
    rows = _csv_rows(estate)
    assert rows
    populated = 0
    for row in rows:
        if not row["SkuId"]:
            assert row["SkuPriceId"] == "", "no SKU priced means no price identity"
            assert row["SkuPriceDetails"] == ""
            continue
        resource = resources[row["ResourceId"]]
        assert resource.sku_id == row["SkuId"]
        expected_id = identity_for(
            estate.seed,
            f"sku-price/{resource.sku_id}/{row['BillingCurrency']}/{row['PricingCategory']}",
        )
        assert row["SkuPriceId"] == expected_id
        assert row["SkuPriceId"] != row["SkuId"], "a price identity is not a copy of the SKU id"
        # A JSON *string*, never an object: the column would carry garbage if the
        # renderer handed pyarrow a dict (the CFN simulator's ExpectedProperties trap).
        details = json.loads(row["SkuPriceDetails"])
        assert isinstance(details, dict)
        assert all(isinstance(value, str) for value in details.values())
        assert details == {
            "ListUnitPrice": str(list_prices[resource.sku_id].unit_price),
            "ContractedUnitPrice": str(contracted_prices[resource.sku_id].unit_price),
            "PricingUnit": contracted_prices[resource.sku_id].unit,
            "PricingCurrency": contracted_prices[resource.sku_id].currency,
        }
        populated += 1
    assert populated, "no AWS row resolved a priced SKU"
    assert populated < len(rows), "the resource-less lines must not carry a price identity"


def test_unpriced_sku_emits_empty_price_identity(estate: CanonicalEstate) -> None:
    """Absence is absence: a SKU the estate prices nowhere gets neither value.

    Two ways in, both asserted: a resource whose ``sku_id`` no price row names, and the
    resource-less billing-only constructs. ``SkuPriceDetails`` must be ``""``, never
    ``"{}"`` — an empty document would claim a price identity with no facts behind it.
    """
    lookups = focus_aws._Lookups(estate)
    line = next(
        line
        for line in estate.billing_lines
        if line.resource_uuid and line.service_provider_name == "Amazon Web Services"
    )
    assert line.resource_uuid is not None
    catalogued = lookups.resource_by_uuid[line.resource_uuid]
    lookups.resource_by_uuid[line.resource_uuid] = replace(catalogued, sku_id="not_a_priced_sku")
    unpriced = focus_aws._record(line, lookups)
    assert unpriced["SkuId"] == "not_a_priced_sku"
    assert unpriced["SkuPriceId"] == ""
    assert unpriced["SkuPriceDetails"] == ""

    resource_less = next(
        line
        for line in estate.billing_lines
        if line.resource_uuid is None and line.service_provider_name == "Amazon Web Services"
    )
    record = focus_aws._record(resource_less, lookups)
    assert record["SkuPriceId"] == ""
    assert record["SkuPriceDetails"] == ""

    # And the price book really does hold the priced SKUs, so the two assertions above
    # are about the lookup rather than about an empty estate-wide price table.
    list_prices, contracted_prices = _price_book(estate)
    assert catalogued.sku_id in list_prices and catalogued.sku_id in contracted_prices
    assert not any(row["SkuPriceDetails"] == "{}" for row in _csv_rows(estate))


def test_sku_price_id_is_a_function_of_sku_currency_and_tier() -> None:
    """One price, one id: each of the three inputs moves the id, nothing else does."""
    same = focus_aws._sku_price_id(123, "aws-ec2-m5-large", "USD", "Standard")
    assert same == focus_aws._sku_price_id(123, "aws-ec2-m5-large", "USD", "Standard")
    others = {
        focus_aws._sku_price_id(123, "aws-ec2-m5-large", "USD", "Committed"),
        focus_aws._sku_price_id(123, "aws-ec2-m5-large", "BRL", "Standard"),
        focus_aws._sku_price_id(123, "aws-s3-standard", "USD", "Standard"),
        focus_aws._sku_price_id(124, "aws-ec2-m5-large", "USD", "Standard"),
    }
    assert same not in others, "different prices must not share an id"
    assert len(others) == 4, "each differing input must yield a distinct id"


def test_rows_of_one_price_share_one_id(estate: CanonicalEstate) -> None:
    """The id groups rows by price, so the column is injective over (sku, currency, tier)."""
    by_price: dict[tuple[str, str, str], set[str]] = {}
    for row in _csv_rows(estate):
        if not row["SkuPriceId"]:
            continue
        key = (row["SkuId"], row["BillingCurrency"], row["PricingCategory"])
        by_price.setdefault(key, set()).add(row["SkuPriceId"])
    assert by_price
    assert all(len(ids) == 1 for ids in by_price.values()), "one price, one id"
    ids = [next(iter(found)) for found in by_price.values()]
    assert len(set(ids)) == len(ids), "two prices must not collide on one id"


# ── Slice 4: capacity reservations, modelled on the estate ───────────────────


def _reservation_of(estate: CanonicalEstate, resource_uuid: str) -> Any:
    """The reservation the estate puts on ``resource_uuid``, or ``None``."""
    resource = next(r for r in estate.resources if r.identity.uuid == resource_uuid)
    return resource.capacity_reservation


def test_capacity_reservation_columns_are_projected_from_the_resource(estate: CanonicalEstate) -> None:
    """A reserving row carries exactly what the reservation on its resource holds.

    The expectation is rebuilt from the MODEL (``Resource.capacity_reservation``) rather
    than from a literal, so this cannot pass by agreeing with the renderer's own lookup:
    the id and the status are the two fields that reservation carries.
    """
    rows = _csv_rows(estate)
    assert rows
    populated = 0
    for row in rows:
        reservation = _reservation_of(estate, row["ResourceId"]) if row["ResourceId"] else None
        if reservation is None:
            assert row["CapacityReservationId"] == "", "no reservation means no id"
            assert row["CapacityReservationStatus"] == ""
            continue
        assert row["CapacityReservationId"] == reservation.reservation_id
        assert row["CapacityReservationStatus"] == reservation.status
        populated += 1
    assert populated, "no AWS row carried a capacity reservation"
    assert populated < len(rows), "the non-reserving rows must not carry one"


def test_capacity_reservations_sit_on_eligible_compute_only() -> None:
    """Eligibility is the provider's own table, not "every resource".

    An AWS capacity reservation is an EC2 construct, so the catalog's storage, network
    and other Compute services must carry none — a reservation on a bucket would be a
    value no model fact backs.
    """
    eligible = const.CAPACITY_RESERVATION_TYPES[const.PROVIDER_KEY_AWS]
    base = build_estate(seed=123, profile="small", currency="USD")
    reserving = [r for r in base.resources if r.capacity_reservation is not None]
    assert reserving, "the base estate must carry capacity reservations"
    for resource in reserving:
        assert resource.resource_type in eligible
        assert resource.capacity_reservation is not None
        assert resource.capacity_reservation.resource_uuid == resource.identity.uuid
        assert resource.capacity_reservation.scope_id == resource.parent_scope_id
    # Partial: the eligible set is larger than the reserving subset, and no eligible
    # type outside the table exists among the reserving resources.
    from_catalog = {entry[0] for entry in const.AWS_SERVICES}
    assert set(eligible) <= from_catalog, "an eligible type the catalog does not model"
    assert len(reserving) < len([r for r in base.resources if r.resource_type in eligible])
    # Neither eligible nor non-eligible is empty, so the assertion above is about
    # coverage rather than about an estate with no EC2 in it.
    assert [r for r in base.resources if r.resource_type not in eligible]


def test_both_reservation_statuses_are_reachable() -> None:
    """``Used`` and ``Unused`` are BOTH modelled, in the FOCUS literal domain.

    A renderer that only ever saw one literal would make the other unobservable, and a
    model carrying a third would emit a value no FOCUS reader accepts. The tuple's ORDER
    is pinned too: ``_capacity_reservation`` unpacks it as ``(used, unused)``, so a
    reorder must fail here rather than silently swap the two literals.
    """
    assert const.CAPACITY_RESERVATION_STATUSES == ("Used", "Unused")
    base = build_estate(seed=123, profile="small", currency="USD")
    statuses = {
        r.capacity_reservation.status for r in base.resources if r.capacity_reservation is not None
    }
    assert statuses == set(const.CAPACITY_RESERVATION_STATUSES), "both literals must be reachable"


def test_capacity_reservation_id_is_derived_in_the_documented_shape() -> None:
    """``cr-`` + 17 lowercase hex, a function of ``(seed, resource)`` and of nothing else."""
    factory = IdentityFactory(seed=123)
    uuid = factory.for_path("aws/123456789012/ec2_instance/0000", "aws").uuid
    first = capacity_reservation_id(123, uuid)
    assert re.fullmatch(r"cr-[0-9a-f]{17}", first), first
    assert first == capacity_reservation_id(123, uuid), "the id must be stable"
    others = {
        capacity_reservation_id(123, factory.for_path("aws/123456789012/ec2_instance/0001", "aws").uuid),
        capacity_reservation_id(124, uuid),
    }
    assert len(others) == 2
    assert first not in others, "a different resource or seed must not share the id"


def test_reservations_are_window_independent_per_resource() -> None:
    """The daily and the one-shot surface must agree about a resource.

    Both streams are keyed by the resource, so a month-to-date window and a 45-day one
    put the SAME reservation on the same resource; only the reservation's period follows
    the window, like ``Commitment``'s. This is what makes coverage independent of visit
    order and of window length.
    """
    default_window = build_estate(seed=123, profile="small", currency="USD")
    month_to_date = build_estate(
        seed=123, profile="small", currency="USD", sim_start=date(2026, 3, 1), window_days=18
    )

    def by_resource(estate: CanonicalEstate) -> dict[str, tuple[str, str]]:
        return {
            r.identity.uuid: (r.capacity_reservation.reservation_id, r.capacity_reservation.status)
            for r in estate.resources
            if r.capacity_reservation is not None
        }

    first, second = by_resource(default_window), by_resource(month_to_date)
    assert first, "no resource carried a reservation"
    assert first == second, "the reservation must follow the RESOURCE, not the window"
    assert month_to_date.sim_start != default_window.sim_start, "the two windows must differ"


def test_non_reserving_resource_emits_empty_capacity_reservation_columns(estate: CanonicalEstate) -> None:
    """Absence is absence: no reservation on the resource means neither column.

    Three ways in, all asserted: an ELIGIBLE resource that lost the coverage draw, an
    ineligible resource type, and the resource-less billing-only rows (A01/A10), which
    have no resource to reserve capacity on at all.
    """
    lookups = focus_aws._Lookups(estate)
    eligible = const.CAPACITY_RESERVATION_TYPES[const.PROVIDER_KEY_AWS]

    reserving = next(
        line
        for line in estate.billing_lines
        if line.resource_uuid
        and line.service_provider_name == "Amazon Web Services"
        and (lookups.resource_by_uuid[line.resource_uuid].capacity_reservation is not None)
    )
    assert reserving.resource_uuid is not None
    resource = lookups.resource_by_uuid[reserving.resource_uuid]
    assert resource.capacity_reservation is not None
    assert resource.resource_type in eligible
    lookups.resource_by_uuid[reserving.resource_uuid] = replace(resource, capacity_reservation=None)
    without = focus_aws._record(reserving, lookups)
    assert without["CapacityReservationId"] == ""
    assert without["CapacityReservationStatus"] == ""

    ineligible_line = next(
        line
        for line in estate.billing_lines
        if line.resource_uuid
        and line.service_provider_name == "Amazon Web Services"
        and lookups.resource_by_uuid[line.resource_uuid].resource_type not in eligible
    )
    ineligible = focus_aws._record(ineligible_line, lookups)
    assert ineligible["CapacityReservationId"] == ""
    assert ineligible["CapacityReservationStatus"] == ""

    resource_less = next(
        line
        for line in estate.billing_lines
        if line.resource_uuid is None and line.service_provider_name == "Amazon Web Services"
    )
    record = focus_aws._record(resource_less, lookups)
    assert record["CapacityReservationId"] == ""
    assert record["CapacityReservationStatus"] == ""


# ── Slice 5: the x_Discounts document, derived from the line's own costs ─────


def _aws_model_lines(estate: CanonicalEstate) -> list[Any]:
    """The AWS billing lines in the order the renderer emits them (``line_id``)."""
    return sorted(
        (line for line in estate.billing_lines if line.service_provider_name == "Amazon Web Services"),
        key=lambda line: line.line_id,
    )


def _bound_rows(estate: CanonicalEstate) -> list[tuple[Any, dict[str, str]]]:
    """Pair each emitted row with its own ``BillingLine``.

    The export carries no line id, so the pairing rests on the ordering ``_aws_lines``
    documents. The charge start is asserted to match, so a future reordering fails here
    instead of silently comparing one row against another line's costs.
    """
    aws = _aws_model_lines(estate)
    rows = _csv_rows(estate)
    assert len(rows) == len(aws)
    for line, row in zip(aws, rows, strict=True):
        assert row["ChargePeriodStart"] == line.charge_period_start.astimezone(UTC).isoformat()
    return list(zip(aws, rows, strict=True))


def test_x_discounts_are_derived_from_the_line_costs(estate: CanonicalEstate) -> None:
    """The document is REBUILT here from model rows, so agreement cannot be accidental.

    ``x_Discounts`` is a projection of facts the line already carries: the reduction
    ``list_cost - billed_cost`` (with the two costs it was measured between) and the
    commitment the line names. Nothing is asserted against a literal document.
    """
    populated = 0
    for line, row in _bound_rows(estate):
        reduction = line.list_cost - line.billed_cost
        if reduction <= 0 and not line.commitment_discount_id:
            assert row["x_Discounts"] == "", "no reduction and no commitment means no document"
            continue
        document = json.loads(row["x_Discounts"])
        assert isinstance(document, dict), "the column carries a JSON string, never an object"
        assert all(isinstance(value, str) for value in document.values())
        expected: dict[str, str] = {}
        if reduction > 0:
            expected = {
                "BilledCost": str(line.billed_cost.quantize(const.SIX_DP)),
                "DiscountAmount": str(reduction.quantize(const.SIX_DP)),
                "ListCost": str(line.list_cost.quantize(const.SIX_DP)),
            }
        if line.commitment_discount_id:
            expected["CommitmentDiscountId"] = line.commitment_discount_id
        assert document == expected
        # The document's money is the ROW's own money: the amount is the gap between the
        # two cost columns the same row emits, at the same 6 dp, so a reader can check it
        # against the export instead of trusting the extension.
        if reduction > 0:
            assert document["ListCost"] == row["ListCost"]
            assert document["BilledCost"] == row["BilledCost"]
            assert Decimal(document["DiscountAmount"]) == Decimal(row["ListCost"]) - Decimal(
                row["BilledCost"]
            )
        populated += 1
    assert populated, "no AWS row carried a discount document"
    assert populated < len(_csv_rows(estate)), "the undiscounted rows must not carry one"


def test_x_discounts_are_empty_when_the_line_carries_no_discount(estate: CanonicalEstate) -> None:
    """Absence is absence: ``""`` for a line with no discount — and never ``"{}"``.

    Every empty document is checked against the row's own columns, so this asserts the
    rule rather than the presence of empties: a line charged its full list price and
    naming no commitment has nothing to document, and ``"{}"`` would claim a discount
    that is not there.
    """
    rows = _csv_rows(estate)
    empty = [row for row in rows if not row["x_Discounts"]]
    assert empty, "the estate carries undiscounted rows (the Tax/Purchase billing-only constructs)"
    for row in empty:
        assert Decimal(row["ListCost"]) <= Decimal(row["BilledCost"]), (
            "a line charged below its list price must carry a discount document"
        )
        assert row["CommitmentDiscountId"] == "", "a covered line must name its commitment in the document"
    assert not any(row["x_Discounts"] == "{}" for row in rows), "an empty document is never emitted"


def test_x_discounts_is_a_string_column_in_the_parquet(estate: CanonicalEstate) -> None:
    """The trap the module records twice: a JSON document must land as a STRING.

    A dict handed to pyarrow would make the column a struct and the parser would read
    garbage — the same failure the AWS CFN simulator records for ``ExpectedProperties``.
    The assertion is on the emitted TYPE, which is what the trap is about.
    """
    import io

    import pyarrow as pa
    import pyarrow.parquet as pq

    table = pq.read_table(io.BytesIO(focus_aws.render_parquet_bytes(estate)), columns=["x_Discounts"])
    assert table.schema.field("x_Discounts").type == pa.string()
    values = table.column("x_Discounts").to_pylist()
    assert any(values), "the column must not be empty on every row"
    for value in values:
        if value:
            assert json.loads(value), "a non-empty value must be a JSON document"


# ── Slice 6: the two columns that are legitimately empty in a window ─────────


def test_charge_class_is_a_projection_of_is_restatement(estate: CanonicalEstate) -> None:
    """Slice 6: ``ChargeClass`` is populated WHERE THE MODEL SAYS, not merely somewhere.

    The column is empty in the daily month-to-date export because a restatement exists
    only when a scenario emits one, and the daily surface applies no scenarios. It is NOT
    a column without a source — so this asserts the projection row by row against
    ``BillingLine.is_restatement``, and that the A06 correction really is in the export
    (the scenario-applied estate is what puts it there).
    """
    corrections = 0
    for line, row in _bound_rows(estate):
        assert row["ChargeClass"] == ("Correction" if line.is_restatement else "")
        if line.is_restatement:
            corrections += 1
            # A06's correction is a signed Adjustment delta that restates an earlier
            # usage_date, so the row is an Adjustment rather than the Usage it corrects.
            assert row["ChargeCategory"] == "Adjustment"
            assert row["ChargeClass"] == "Correction"
    assert corrections >= 1, "the A06 restatement must reach the export"


def test_a_month_to_date_window_empties_exactly_the_two_window_conditional_columns() -> None:
    """Slice 6's claim, machine-checked: those two are empty because of the WINDOW.

    Builds the estate the daily surface builds for 2026-03-18 (``daily/window.py`` derives
    the month-to-date window from the day alone). No scenario is applied, so no row
    restates anything and ``ChargeClass`` is empty; no period in the window has been
    issued yet, so ``InvoiceId`` is empty — and BOTH are empty on every row while every
    other column of the 60 carries a value. The same seed on a month-spanning window
    populates ``InvoiceId``, which is what makes the emptiness the window's rather than a
    missing source: a column without a source would be empty in both.
    """
    month_to_date = build_estate(
        seed=123, profile="small", currency="USD", sim_start=date(2026, 3, 1), window_days=18
    )
    rows = _csv_rows(month_to_date)
    assert rows
    assert not any(line.is_restatement for line in month_to_date.billing_lines), "no scenario, no restatement"
    assert not any(line.invoice_id for line in month_to_date.billing_lines), "the period is not issued yet"
    assert {row["ChargeClass"] for row in rows} == {""}
    assert {row["InvoiceId"] for row in rows} == {""}
    all_empty = sorted(column for column in focus_aws._COLUMNS if not any(row[column] for row in rows))
    assert all_empty == ["ChargeClass", "InvoiceId"], (
        f"a month-to-date export must empty exactly those two, got {all_empty}"
    )

    # The same seed over a month-spanning window DOES carry invoice ids, on the rows of
    # the period that closed — so the emptiness above is the window's, not the model's.
    month_spanning = build_estate(seed=123, profile="small", currency="USD")
    issued = [line for line in month_spanning.billing_lines if line.invoice_id]
    assert issued, "a closed period must carry its invoice id"
    assert any(row["InvoiceId"] for row in _csv_rows(month_spanning))


# ── AC-4 ingestion acceptance ────────────────────────────────────────────────

def test_parquet_detects_focus_and_aggregates(estate: CanonicalEstate, real_parser: ModuleType) -> None:
    df = real_parser.parse_cur_bytes(focus_aws.render_parquet_bytes(estate), "focus.parquet")
    assert real_parser._detect_dialect(set(df.columns))[0] == "focus"
    assert real_parser.parse_cur_dataframe(df)
    assert real_parser.parse_cur_cost_dataframe(df)
    assert real_parser.parse_cur_cost_dataframe_with_resources(df)


def test_csv_detects_focus_and_aggregates(estate: CanonicalEstate, real_parser: ModuleType) -> None:
    df = real_parser.parse_cur_bytes(focus_aws.render_csv_bytes(estate), "focus.csv")
    assert real_parser._detect_dialect(set(df.columns))[0] == "focus"
    assert real_parser.parse_cur_dataframe(df)
    assert real_parser.parse_cur_cost_dataframe(df)


def test_csv_gz_detects_focus_and_aggregates(estate: CanonicalEstate, real_parser: ModuleType) -> None:
    df = real_parser.parse_cur_bytes(focus_aws.render_csv_gz_bytes(estate), "focus.csv.gz")
    assert real_parser._detect_dialect(set(df.columns))[0] == "focus"
    assert real_parser.parse_cur_cost_dataframe(df)


# ── AC-5 tags ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("encoding", ["csv", "parquet"])
def test_tags_decode_to_the_expected_dict(estate: CanonicalEstate, real_parser: ModuleType, encoding: str) -> None:
    """Both encodings use the JSON-string form and must decode to the same dict.

    The assertion is on the DECODED dict, never on the encoding: a future parser that
    makes the native arrow-list branch reachable would not require redoing this.
    """
    if encoding == "csv":
        df = real_parser.parse_cur_bytes(focus_aws.render_csv_bytes(estate), "focus.csv")
    else:
        df = real_parser.parse_cur_bytes(focus_aws.render_parquet_bytes(estate), "focus.parquet")
    rows = real_parser.parse_cur_cost_dataframe_with_resources(df)
    tagged = next(r for r in estate.resources if r.tags and r.identity.provider == "aws")
    expected = {k: v for k, v in tagged.tags}
    assert [row for row in rows if row.tags == expected], f"no AWS row carried {expected}"


# ── AC-6 S3 layout ───────────────────────────────────────────────────────────


def test_s3_key_matches_the_bcm_layout() -> None:
    key = focus_aws.s3_key(billing_period="2026-01", execution="20260101T000000Z-abcdef01", filename="part-00001.snappy.parquet")
    assert key == (
        "focus12-full/synthetic-focus12-daily-full/data/"
        "billing_period=2026-01/20260101T000000Z-abcdef01/part-00001.snappy.parquet"
    )
    assert key.endswith(_DATA_SUFFIXES)


def test_partition_key_is_matched_in_both_casings() -> None:
    """AWS delivers lowercase while the public docs show uppercase; both parse."""
    for casing in ("billing_period", "BILLING_PERIOD"):
        key = focus_aws.s3_key(
            billing_period="2026-07",
            execution="e",
            filename="part-00001.snappy.parquet",
            partition_key=casing,
        )
        match = _PARTITION_RE.search(key)
        assert match, f"the reader's partition regex must match {key!r}"
        assert (match.group(1), match.group(2)) == ("2026", "07")


def test_the_documented_metadata_prefix_is_not_populated() -> None:
    """O prefixo ``metadata/`` e a forma documentada do layout, e fica VAZIO.

    A AWS descreve um ``Manifest.json`` e o CONTEUDO dele em prosa, mas nao publica
    schema, lista de chaves nem exemplo: a propria spec registra que toda chave exceto
    ``additionalOutputFiles`` e nao comprovada. Um manifesto e um DOCUMENTO -- escreve-lo
    exige NOMEAR os campos, e os nomes sao exatamente o que a documentacao nao estabelece.
    O ``s3_key`` continua capaz de construir o caminho documentado (e o teste o constroi,
    para provar a forma), mas o renderer nao grava nada ali.
    """
    key = focus_aws.s3_key(
        billing_period="2026-01",
        execution="e",
        filename="synthetic-focus12-daily-full-Manifest.json",
        kind="metadata",
    )
    assert key == (
        "focus12-full/synthetic-focus12-daily-full/metadata/"
        "billing_period=2026-01/e/synthetic-focus12-daily-full-Manifest.json"
    )
    assert "/metadata/billing_period=" in key


def test_the_export_tree_carries_data_and_provenance_only(
    estate: CanonicalEstate, tmp_path: Path
) -> None:
    """O JSON que sobra no diretorio e o NOSSO, e so ele: nenhum documento de schema escolhido.

    O nome comecado por ``_`` e a convencao do pacote para um documento nosso (o relatorio
    de proveniencia irmao), e e o que o mantem fora do artefato entregue. Qualquer OUTRO
    arquivo tem de ser dado do export, com as colunas da especificacao.
    """
    written = focus_aws.AwsFocusRenderer().render(estate, tmp_path)
    others = [p for p in written if p.name != focus_aws.PROVENANCE_FILE]
    assert all(p.suffix == ".parquet" for p in others), "so dado entregue, alem do provenance"
    assert all("/data/" in p.as_posix() for p in others), "nada fora do prefixo documentado"
    assert not [p for p in written if "/metadata/" in p.as_posix()], "o manifesto nao e entregue"
    provenance = [p for p in written if p.name == focus_aws.PROVENANCE_FILE]
    assert len(provenance) == 1, "um relatorio de proveniencia por exportacao"
    document = json.loads(provenance[0].read_text(encoding="utf-8"))
    assert document["kind"] == "provenance"
    assert document["mechanism"]["manifest_delivered"] is False
    # A secao da PROPRIA spec, verbatim: a lacuna fica registrada pelo texto da evidencia.
    assert document["manifest"]["confirmed_keys"] == ["additionalOutputFiles"]
    assert "UNVERIFIED" in document["manifest"]["notes"]


def test_no_delivered_document_carries_an_undocumented_key(
    estate: CanonicalEstate, tmp_path: Path
) -> None:
    """A regra de ouro no nivel do DOCUMENTO: ou e dado com coluna da spec, ou e o NOSSO proveniencia.

    Se alguem voltar a gravar um ``Manifest.json`` -- ou qualquer documento cujo schema
    tenhamos escolhido -- dentro do export, este teste falha por dois motivos
    independentes: o arquivo nao e o ``_provenance.json`` e e um ``.json``; e as chaves
    dele nao sao colunas da especificacao, o que ``check`` acusa como inventado. E o mesmo
    defeito que o auditor do pacote mede na uniao dos artefatos de cada superficie.
    """
    spec = load_spec(_SPEC)
    written = focus_aws.AwsFocusRenderer().render(estate, tmp_path)
    for path in written:
        if path.name == focus_aws.PROVENANCE_FILE:
            continue
        assert path.suffix != ".json", f"{path.name}: documento com schema escolhido dentro do export"
        findings = check(spec, columns_of(path))
        assert is_faithful(findings), f"{path.name}: " + "; ".join(str(finding) for finding in findings)


def test_tree_is_written_under_the_render_dir(estate: CanonicalEstate, tmp_path: Path) -> None:
    """NFR-4 write boundary: everything lands under out_dir/aws_focus/."""
    written = focus_aws.AwsFocusRenderer().render(estate, tmp_path)
    assert written
    root = (tmp_path / "aws_focus").resolve()
    for path in written:
        assert path.resolve().is_relative_to(root), f"{path} escaped the render dir"
    data = [p for p in written if "/data/" in p.as_posix()]
    assert data, "expected at least one data object"
    assert all(path.name.endswith(".snappy.parquet") for path in data)
    assert all(re.search(r"-\d{5}\.snappy\.parquet$", path.name) for path in data)
    # One execution per delivery: a restated period is delivered more than once (A04).
    executions = {(_period_of(p), _execution_of(p)) for p in data}
    assert len(executions) > len({_period_of(p) for p in data})


# ── A04 / A06 execution pinning and restatement ──────────────────────────────


def test_restated_period_is_delivered_in_several_executions(estate: CanonicalEstate, tmp_path: Path) -> None:
    """A04: the period carrying the A06 restatement was delivered more than once."""
    written = focus_aws.AwsFocusRenderer().render(estate, tmp_path)
    by_period = _executions_by_period(written)
    multi = {period: execs for period, execs in by_period.items() if len(execs) > 1}
    assert multi, "expected at least one period delivered in more than one execution"
    assert _restated_period(estate) in multi


def test_execution_pinning_takes_newest_and_never_sums(estate: CanonicalEstate, tmp_path: Path) -> None:
    """Mirrors ``s3_reader.py:154-168``: newest execution per period, never the union.

    The pin is replicated here (newest by ``(mtime, dir name)``) because the renderer
    test has no S3. Both criteria must agree, which is why each view is stamped from
    its own max ``export_time`` and the names sort oldest-first.
    """
    written = focus_aws.AwsFocusRenderer().render(estate, tmp_path)
    by_period = _executions_by_period(written)

    checked = 0
    for period, executions in by_period.items():
        if len(executions) < 2:
            continue
        checked += 1
        # the reader's own criteria: newest LastModified first, directory path second
        newest = max(executions, key=lambda name: (executions[name][0].parent.stat().st_mtime, name))
        pinned_rows = sum(_part_row_count(part) for part in executions[newest])
        all_rows = sum(_part_row_count(part) for parts in executions.values() for part in parts)
        assert pinned_rows < all_rows, (
            f"period {period}: pinned rows {pinned_rows} must be LESS than the sum {all_rows}; "
            "equality would mean the executions were combined rather than pinned"
        )
    assert checked, "no period had more than one execution to pin"


def test_restatement_lands_only_in_the_newest_execution(estate: CanonicalEstate, tmp_path: Path) -> None:
    """A06: the correction arrives in the later execution; the original stays intact."""
    written = focus_aws.AwsFocusRenderer().render(estate, tmp_path)
    by_period = _executions_by_period(written)

    checked = 0
    for period, executions in by_period.items():
        if len(executions) < 2:
            continue
        checked += 1
        ordered = sorted(executions)
        older, newest = ordered[0], ordered[-1]
        older_corrections = sum(_correction_rows(part) for part in executions[older])
        newest_corrections = sum(_correction_rows(part) for part in executions[newest])
        assert older_corrections == 0, f"period {period}: the older execution must not carry the correction"
        assert newest_corrections >= 1, f"period {period}: the newest execution must carry the correction"
    assert checked, "no period had more than one execution to compare"


def _executions_by_period(written: list[Path]) -> dict[str, dict[str, list[Path]]]:
    """``period -> {execution name -> [data part paths]}``."""
    out: dict[str, dict[str, list[Path]]] = {}
    for path in _data_objects(written):
        out.setdefault(_period_of(path), {}).setdefault(_execution_of(path), []).append(path)
    return out


def _restated_period(estate: CanonicalEstate) -> str:
    restated = [
        line
        for line in estate.billing_lines
        if line.is_restatement and line.service_provider_name == "Amazon Web Services"
    ]
    assert restated, "A06 must have emitted an AWS restatement for A04 to be observable"
    first = restated[0]
    return f"{first.billing_period_start.year:04d}-{first.billing_period_start.month:02d}"


def _data_objects(written: list[Path]) -> list[Path]:
    return [path for path in written if "/data/" in path.as_posix()]


def _period_of(path: Path) -> str:
    """``…/billing_period=YYYY-MM/<execution>/<file>`` -> ``YYYY-MM``."""
    return path.parent.parent.name.split("=", 1)[1]


def _execution_of(path: Path) -> str:
    return path.parent.name


def _part_row_count(path: Path) -> int:
    import pyarrow.parquet as pq

    return int(pq.read_table(path, columns=["x_ServiceCode"]).num_rows)


def _correction_rows(part_path: Path) -> int:
    """Count rows this part marks as a correction (ChargeClass = Correction)."""
    import pyarrow.parquet as pq

    table = pq.read_table(part_path, columns=["ChargeClass"])
    return sum(1 for value in table.column("ChargeClass").to_pylist() if value == "Correction")


def test_provenance_lists_every_delivered_object_and_they_all_exist(
    estate: CanonicalEstate, tmp_path: Path
) -> None:
    """O registro de proveniencia descreve o que foi entregue, e o que ele lista EXISTE.

    Sem manifesto, o registro irmao e o unico lugar onde o run fica documentado; entao ele
    tem de bater com o disco: cada objeto listado, o tamanho, a contagem de linhas e o
    total. Um registro que nao corresponde ao diretorio seria pior que nenhum.
    """
    written = focus_aws.AwsFocusRenderer().render(estate, tmp_path)
    provenance = next(p for p in written if p.name == focus_aws.PROVENANCE_FILE)
    doc = json.loads(provenance.read_text(encoding="utf-8"))
    assert doc["totals"]["objects"] == len(doc["objects"]) == len([p for p in written if p.suffix == ".parquet"])
    assert doc["columns"]["emitted"] == 60
    assert doc["columns"]["schema_fingerprint"] == focus_aws.schema_fingerprint()
    assert doc["manifest"]["status"] == "partial"
    assert doc["totals"]["records"] == sum(_part_row_count(p) for p in written if p.suffix == ".parquet")
    for entry in doc["objects"]:
        object_path = tmp_path / "aws_focus" / entry["key"]
        assert object_path.is_file(), f"a proveniencia lista um objeto ausente: {entry['key']}"
        assert object_path.stat().st_size == entry["bytes"]
        assert "/data/" in entry["key"] and entry["key"].endswith(".snappy.parquet")


def test_render_is_deterministic(estate: CanonicalEstate, tmp_path: Path) -> None:
    first = focus_aws.AwsFocusRenderer().render(estate, tmp_path / "a")
    second = focus_aws.AwsFocusRenderer().render(estate, tmp_path / "b")
    assert [p.relative_to(tmp_path / "a") for p in first] == [p.relative_to(tmp_path / "b") for p in second]
    for left, right in zip(first, second, strict=True):
        assert left.read_bytes() == right.read_bytes(), f"{left.name} is not byte-stable"


def test_schema_fingerprint_is_not_synth_prefixed() -> None:
    """``synth:`` marks synthetic DATA; a real schema hash must not carry it."""
    assert not focus_aws.schema_fingerprint().startswith("synth:")


def _csv_rows(estate: CanonicalEstate) -> list[dict[str, str]]:
    import csv
    import io

    text = focus_aws.render_csv_bytes(estate).decode("utf-8")
    return list(csv.DictReader(io.StringIO(text)))
