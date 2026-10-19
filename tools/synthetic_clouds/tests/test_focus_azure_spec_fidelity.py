"""Golden fidelity: the Azure FinOps artifacts carry EXACTLY the documented columns.

The specification is the source of truth (``specs/README.md``) and its normative reader is
``fidelity.spec.load_spec``. These tests RENDER the artifacts to a temporary directory and
compare the DELIVERED FILES with that specification -- never an in-memory column list,
which would only prove that two copies of the same mistake agree. ``columns_of`` (the
fidelity core's real-artifact reader) supplies the fields, ``check``/``check_artifact``
supplies the verdict.

Which artifact proves which claim
---------------------------------
* ``focus.csv`` and ``focus.parquet`` are checked against
  ``azure/cost-management-export-focus12`` (FocusCost 1.2-preview). Both formats carry the
  same 104 contracted columns: belonging to the schema and being allowed to receive a
  VALUE are two different contracts, and this surface exercises both halves -- 98
  ``declared`` columns plus 6 ``null-empty`` ones that are present and must stay empty.
* ``export_run.json`` -- DELIVERED by ``focus_azure.AzureFocusRenderer.render`` from
  ``render_export_run_bytes`` -- is checked against
  ``azure/cost-management-export-manifest``. That surface has 41 columns and only
  12 are contracted: the other 29 exist solely inside ONE official ``_manifest.json``
  example (``evidence: example-only``). The test proves both directions: the delivered
  document carries exactly the 12, and the official EXAMPLE (the only manifest artifact
  Microsoft publishes) is faithfully rejected when compared as if it were a contract.

Why the fidelity claim here is a SET, not a sequence
----------------------------------------------------
The Azure CSV header order is a real part of the published format, so ``ordered=True``
looks appropriate. It is not: the spec's ``delivery`` block fixes the formats (csv +
parquet), the UTF-8 encoding, the blob path template and the manifest beside the data --
and NO column order; and §4 of the spec registers the order itself as UNVERIFIED (the
schema page enumerates 105 columns, the official metadata JSON 106, and the two disagree
from index 73 onward). Asserting that order would assert an order the documentation
refuses to cite. What this file does assert is the weaker, true invariant: the artifact's
sequence is the SEQUENCE THE RENDERER DERIVES FROM THE SPEC, which is why a hand-edit
cannot silently reorder the file (``test_the_emitted_order_is_the_specs_own_and_never_drifts``).

The claim this file did NOT have before: empty is a decision
------------------------------------------------------------
``required`` in FOCUS means the COLUMN must exist; the VALUE may be absent when it does not
apply. That makes "61 of 104 required columns are blank in every row" a question, not a
verdict -- so every one of them is now classified and DECLARED, and the delivery carries the
declaration (``_provenance.json``):

* ``B`` -- legitimately not applicable (e.g. ``CapacityReservation*``/``CommitmentDiscount*``,
  which the spec marks ``null-empty``: present in the file, never populated; and
  ``ChargeClass``, whose only literal is ``Correction``);
* ``C`` -- applicable, but the canonical model does not carry the data (e.g.
  ``x_ResourceGroupName``, ``SkuMeter``, ``ServiceSubcategory``);
* ``D`` -- the spec documents the name but marks it unverified (``x_InvoiceIssuerId``,
  ``x_SkuTerm``), so it may not exist at all.

``test_every_required_column_is_populated_or_declared`` is the invariant: a required column
is either observed populated in a delivered row, or declared with a group and a reason. A new
column that arrives blank fails by name instead of shipping as an unexplained hole. Two
companion tests keep the declaration honest in both directions (nothing declared is populated,
everything declared as partial is populated somewhere), and the counts in the report are
re-measured from the artifact rather than trusted.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tools.synthetic_clouds.fidelity.artifacts import columns_of, populated_of
from tools.synthetic_clouds.fidelity.checker import (
    KIND_INVENTED,
    KIND_MISSING,
    KIND_ORDER,
    KIND_POPULATED_EMPTY,
    KIND_UNVERIFIED,
    check,
    check_artifact,
    check_values,
    is_faithful,
)
from tools.synthetic_clouds.fidelity.spec import SurfaceSpec, load_spec
from tools.synthetic_clouds.generate.estate_builder import build_estate
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.render import focus_azure
from tools.synthetic_clouds.render.focus_azure import AzureFocusRenderer, render_export_run_bytes
from tools.synthetic_clouds.scenarios.emit import apply_all

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SPEC_DIR = _REPO_ROOT / "specs" / "azure"
_FOCUS12_SPEC = _SPEC_DIR / "cost-management-export-focus12.schema.json"
_MANIFEST_SPEC = _SPEC_DIR / "cost-management-export-manifest.schema.json"

#: Golden sizes of the cited documentation. A spec edit that changes one is exactly the
#: event this file exists to surface.
_FOCUS12_COLUMNS = 106
_FOCUS12_GENERATABLE = 98
_FOCUS12_EMITTABLE = 104  # generatable + the 6 null-empty columns
_FOCUS12_NULL_EMPTY = (
    "CapacityReservationId",
    "CapacityReservationStatus",
    "CommitmentDiscountQuantity",
    "CommitmentDiscountStatus",
    "CommitmentDiscountUnit",
    "SkuPriceDetails",
)
#: Documented names the spec does NOT verify (metadata JSON vs schema page, spec §4).
_FOCUS12_REFUSED = ("x_InvoiceIssuerId", "x_SkuTerm")

_MANIFEST_COLUMNS = 41
_MANIFEST_CONTRACTED = 12
_MANIFEST_EXAMPLE_ONLY = 29

#: The 12 names the hand-written tuple used to emit that NO official source enumerates for
#: this dataset, plus ``x_PricingCurrency`` (spec §4: listed as column 79 of the schema page,
#: absent from the 106-column metadata JSON, registered UNVERIFIED). All 13 are gone.
#: Pinned so re-introducing one is a NAMED failure instead of a silent extra column.
#: None of them needed a spec amendment: §5 records that the two official enumerations
#: disagree about only ``x_InvoiceIssuerId``, ``x_SkuTerm``, ``x_PricingCurrency`` and the
#: ``x_SkuPlanName``/``x_SkuPartNumber`` swap, so a name missing from the metadata JSON is
#: also missing from the schema page.
_REMOVED_COLUMNS = (
    "AvailabilityZone",  # spec §3.2: "não está incluída -- não deve ser gerada"
    "PricingCurrencyContractedUnitPrice",  # FOCUS 1.2 trio absent from this dataset
    "PricingCurrencyEffectiveCost",
    "PricingCurrencyListUnitPrice",
    "x_ChargeId",
    "x_MeterId",  # 1.2-preview contracts x_SkuMeterId instead
    "x_MeterName",  # 1.2-preview contracts x_SkuMeterName instead
    "x_OnDemandCost",
    "x_PricingCurrency",  # registered UNVERIFIED: page only, absent from the metadata JSON
    "x_ResourceGroup",  # 1.2-preview contracts x_ResourceGroupName instead
    "x_SubscriptionId",  # FOCUS carries the subscription as SubAccountId
    "x_UsageQuantity",  # FOCUS carries it as PricingQuantity/ConsumedQuantity
    "x_UsageUnit",  # FOCUS carries it as PricingUnit/x_PricingUnitDescription
)

#: The official ``_manifest.json`` example, reproduced from
#: ``specs/azure/cost-management-export-manifest.md`` §3.1 (Microsoft's tutorial). It is the
#: ONLY manifest artifact Microsoft publishes, and the whole reason 29 of the surface's 41
#: columns are ``example-only``.
_OFFICIAL_MANIFEST_EXAMPLE: dict[str, Any] = {
    "manifestVersion": "2024-04-01",
    "byteCount": 8032,
    "blobCount": 1,
    "dataRowCount": 36,
    "exportConfig": {
        "exportName": "sample",
        "resourceId": (
            "/providers/Microsoft.Billing/billingAccounts/1234567"
            "/providers/Microsoft.CostManagement/exports/sample"
        ),
        "dataVersion": "2023-05-01",
        "apiVersion": "2023-07-01-preview",
        "type": "ReservationRecommendations",
        "timeFrame": "MonthToDate",
        "granularity": None,
    },
    "deliveryConfig": {
        "partitionData": True,
        "dataOverwriteBehavior": "OverwritePreviousReport",
        "fileFormat": "Csv",
        "compressionMode": "None",
        "containerUri": (
            "/subscriptions/ 00000000-0000-0000-0000-000000000000/resourceGroups/samplerg"
            "/providers/Microsoft.Storage/storageAccounts/samplestorage"
        ),
        "rootFolderPath": "folder",
    },
    "runInfo": {
        "executionType": "OnDemand",
        "submittedTime": "2025-03-21T21:04:06.5234447Z",
        "runId": "bbac73f1-9a05-4de6-84ab-c72b568a03b4",
        "startDate": "2025-03-01T00:00:00",
        "endDate": "2025-03-21T00:00:00Z",
    },
    "blobs": [
        {
            "blobName": " folder/sample/ 00000000-0000-0000-0000-000000000000/part0.csv",
            "byteCount": 8032,
            "dataRowCount": 36,
        }
    ],
}

_FOCUS_ARTIFACTS = ("focus.csv", "focus.parquet")


# -- fixtures -----------------------------------------------------------------------


@pytest.fixture(scope="module")
def estate() -> CanonicalEstate:
    return apply_all(build_estate(seed=123, profile="small", currency="USD"))


@pytest.fixture(scope="module")
def focus_dir(tmp_path_factory: pytest.TempPathFactory, estate: CanonicalEstate) -> Path:
    """The DELIVERED directory, written by the renderer's own ``render``."""
    out = tmp_path_factory.mktemp("fidelity_focus_azure")
    AzureFocusRenderer().render(estate, out)
    return out / "azure_focus"


@pytest.fixture(scope="module")
def export_run_file(focus_dir: Path) -> Path:
    """The DELIVERED artifact of the sibling manifest surface, beside the data files."""
    path = focus_dir / "export_run.json"
    assert path.is_file(), "o renderer nao entregou export_run.json na pasta da entrega"
    return path


@pytest.fixture(scope="module")
def focus12_spec() -> SurfaceSpec:
    return load_spec(_FOCUS12_SPEC)


@pytest.fixture(scope="module")
def manifest_spec() -> SurfaceSpec:
    return load_spec(_MANIFEST_SPEC)


# -- helpers ------------------------------------------------------------------------


def _spec_internal_missing(spec: SurfaceSpec) -> tuple[str, ...]:
    """Columns the spec marks required AND outside the format: a spec-internal contradiction.

    Emitting one is ``unverified_emitted``; omitting it is ``missing``. The expectation is
    read from the spec, not hard-coded, so a spec fix moves both sides at once.
    """
    return tuple(column.name for column in spec.columns if column.required and not column.belongs_to_schema)


def _by_kind(findings: Any) -> dict[str, set[str]]:
    grouped: dict[str, set[str]] = {}
    for finding in findings:
        grouped.setdefault(finding.kind, set()).add(finding.column)
    return grouped


def _flatten_example(value: Any, prefix: str = "") -> dict[str, Any]:
    """Project the official example onto the spec's OWN field spelling.

    The spec names a nested field by its dotted path (``exportConfig.exportName``,
    ``blobs[].blobName``), so the example is flattened to that level before it is compared;
    comparing the nested document would only ever read its 8 top-level keys.
    """
    flat: dict[str, Any] = {}
    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}{key}"
            flat[path] = item
            flat.update(_flatten_example(item, f"{path}."))
    elif isinstance(value, list):
        # The spec spells an array element as ``blobs[]`` (and the array itself as a column
        # of its own), so the item prefix drops the dot the dict pass added and gains brackets.
        item_prefix = f"{prefix.rstrip('.')}[]."
        for item in value:
            flat.update(_flatten_example(item, item_prefix))
    return flat


# -- the focus12 spec itself --------------------------------------------------------


def test_the_focus12_spec_has_the_documented_size(focus12_spec: SurfaceSpec) -> None:
    assert len(focus12_spec.columns) == _FOCUS12_COLUMNS
    assert focus12_spec.generatable_count == _FOCUS12_GENERATABLE
    assert focus12_spec.emittable_count == _FOCUS12_EMITTABLE
    assert focus12_spec.null_empty_names == frozenset(_FOCUS12_NULL_EMPTY)
    assert set(focus12_spec.non_emittable_names) == set(_FOCUS12_REFUSED)
    assert "x_PricingCurrency" in focus12_spec.unverified


def test_delivery_documents_the_format_and_not_the_column_order(focus12_spec: SurfaceSpec) -> None:
    """Why every fidelity claim below compares SETS: the order is not a citable contract.

    The delivery block fixes the artifact formats, the encoding, the blob path template and
    the manifest beside the data -- and no column order. §4 of the spec registers the order
    itself as UNVERIFIED, because the schema page enumerates 105 columns and the official
    metadata JSON 106 with a divergence from index 73 onward.
    """
    delivery = focus12_spec.delivery
    assert set(delivery["formats"]) == {"csv", "parquet"}
    assert delivery["manifest"]
    assert "order" not in json.dumps(delivery).lower()
    assert any("order" in item.lower() for item in focus12_spec.unverified)


def test_no_spec_internal_contradiction_remains(focus12_spec: SurfaceSpec) -> None:
    """A spec nao pode exigir presenca de campo que ela mesma nao comprova.

    Enquanto ``x_InvoiceIssuerId`` e ``x_SkuTerm`` eram ``required: true`` E
    ``unverified``, NENHUM artefato passava em ``check``: emitir virava campo nao
    comprovado e omitir virava coluna obrigatoria ausente. O validador passou a
    recusar esse estado, e as duas deixaram de ser obrigatorias -- omiti-las virou
    correto em vez de impossivel.

    O helper le a spec em vez de fixar nomes, entao uma recaida move este teste
    de volta sozinha.
    """
    assert _spec_internal_missing(focus12_spec) == ()


def test_the_renderer_derives_its_columns_from_the_spec(focus12_spec: SurfaceSpec) -> None:
    """No second copy of the column list exists to drift from the cited specification."""
    derived = tuple(column.name for column in focus12_spec.columns if column.belongs_to_schema)
    assert focus_azure._COLUMNS == derived
    assert set(focus_azure._NULL_EMPTY) == set(_FOCUS12_NULL_EMPTY)


# -- the delivered focus12 artifacts ------------------------------------------------


@pytest.mark.parametrize("name", _FOCUS_ARTIFACTS)
def test_artifact_carries_exactly_the_emittable_columns(
    focus_dir: Path, focus12_spec: SurfaceSpec, name: str
) -> None:
    """The delivered file's own fields ARE the spec's schema fields -- no more, no fewer."""
    path = focus_dir / name
    names = columns_of(path)

    assert len(names) == len(set(names)), f"{name}: duplicate column in the artifact"
    assert len(names) == _FOCUS12_EMITTABLE
    assert set(names) == set(focus12_spec.emittable_names), (
        f"{name}: field/documentation mismatch; "
        f"missing={sorted(set(focus12_spec.emittable_names) - set(names))} "
        f"invented={sorted(set(names) - set(focus12_spec.emittable_names))}"
    )

    findings = check(focus12_spec, names)
    assert is_faithful(findings), "\n".join(str(finding) for finding in findings)


@pytest.mark.parametrize("name", _FOCUS_ARTIFACTS)
def test_artifact_has_no_invented_or_uncontracted_field(
    focus_dir: Path, focus12_spec: SurfaceSpec, name: str
) -> None:
    """The anti-fabrication half: nothing the documentation does not contract may appear."""
    emitted = set(columns_of(focus_dir / name))

    assert emitted & focus12_spec.forbidden_names == set()
    assert emitted & set(_REMOVED_COLUMNS) == set(), (
        "a column the 1.2-preview schema does not publish came back: "
        f"{sorted(emitted & set(_REMOVED_COLUMNS))}"
    )
    kinds = _by_kind(check(focus12_spec, sorted(emitted)))
    assert KIND_INVENTED not in kinds
    assert KIND_UNVERIFIED not in kinds


@pytest.mark.parametrize("name", _FOCUS_ARTIFACTS)
def test_null_empty_columns_are_delivered_and_stay_empty(
    focus_dir: Path, focus12_spec: SurfaceSpec, name: str
) -> None:
    """``null-empty`` belongs to the file and may never carry a value."""
    path = focus_dir / name
    names = set(columns_of(path))
    populated = set(populated_of(path))

    assert focus12_spec.null_empty_names <= names, "a null-empty column was omitted from the format"
    assert populated & focus12_spec.null_empty_names == set()
    assert is_faithful(check_values(focus12_spec, sorted(populated)))


@pytest.mark.parametrize("name", _FOCUS_ARTIFACTS)
def test_artifact_is_faithful_on_names_and_values(
    focus_dir: Path, focus12_spec: SurfaceSpec, name: str
) -> None:
    """The golden verdict, names AND values, read from the delivered file.

    ``check_artifact`` adds the value axis (``check_values``) to the name axis, so a column
    declared correct and written with a fabricated value is caught here too. Nothing is
    expected: every documented column is present and (where the spec allows a value) only
    contracted values are written.
    """
    findings = check_artifact(focus12_spec, focus_dir / name)
    assert is_faithful(findings), "\n".join(str(finding) for finding in findings)


@pytest.mark.parametrize("name", _FOCUS_ARTIFACTS)
def test_the_emitted_order_is_the_specs_own_and_never_drifts(
    focus_dir: Path, focus12_spec: SurfaceSpec, name: str
) -> None:
    """A DERIVATION invariant, not a documentation contract (see the module docstring).

    The renderer derives the order from the spec, so the file's sequence is the sequence the
    renderer declares and a hand-edit cannot reorder it silently. ``ordered=True`` is used
    only to prove there is no positional divergence from that declared sequence.
    """
    names = columns_of(focus_dir / name)
    expected = tuple(column.name for column in focus12_spec.columns if column.belongs_to_schema)

    assert names == expected
    order_findings = [finding for finding in check(focus12_spec, names, ordered=True) if finding.kind == KIND_ORDER]
    assert order_findings == []


def test_both_formats_carry_the_same_schema(focus_dir: Path) -> None:
    """CSV and Parquet are one schema in two encodings -- not two different exports."""
    assert columns_of(focus_dir / "focus.csv") == columns_of(focus_dir / "focus.parquet")


def test_the_delivery_writes_the_data_the_run_document_and_the_report(focus_dir: Path) -> None:
    """The delivery is the two data files, the run document and the report -- no ``_manifest.json``.

    ``_manifest.json`` has no contracted field set: 29 of its 41 documented names are
    ``example-only``, so writing one would mean naming 29 fields Microsoft does not publish.
    The 12 fields the REST pages DO contract are delivered as ``export_run.json`` instead, in
    the same folder (the path template the manifest spec documents), and ``_provenance.json``
    carries the empty-column declaration. The leading ``_`` is the package's convention for a
    sibling report: the artifact audit skips it, so its keys are never read as export fields.
    """
    assert {path.name for path in focus_dir.iterdir()} == {
        *_FOCUS_ARTIFACTS,
        "export_run.json",
        "_provenance.json",
    }
    assert not (focus_dir / "_manifest.json").exists()


def test_the_delivered_run_document_is_the_renderers_own_bytes(export_run_file: Path) -> None:
    """The file on disk is what the module produces -- no drift between render and document."""
    assert export_run_file.read_bytes() == render_export_run_bytes()
    assert export_run_file.read_bytes().endswith(b"\n")


# -- the empty-column declaration: no required column is blank without a reason -----


@pytest.fixture(scope="module")
def provenance(focus_dir: Path) -> dict[str, Any]:
    """The declaration the DELIVERY carries, read from the file (not from the module)."""
    payload = json.loads((focus_dir / "_provenance.json").read_text(encoding="utf-8"))
    # Validar em vez de silenciar: o teste inteiro assume um OBJETO, entao um JSON
    # que nao seja objeto tem de reprovar aqui, e nao virar um dict vazio depois.
    assert isinstance(payload, dict), "a proveniencia da entrega tem de ser um objeto JSON"
    return payload


def _artifact_populated(focus_dir: Path) -> set[str]:
    """Columns with a value in at least one row, on EITHER delivered encoding."""
    return set(populated_of(focus_dir / "focus.csv")) | set(populated_of(focus_dir / "focus.parquet"))


def test_every_required_column_is_populated_or_declared(
    focus_dir: Path, focus12_spec: SurfaceSpec, provenance: dict[str, Any]
) -> None:
    """The invariant that stops the blank list from growing in silence.

    Every ``required`` column of the spec is either POPULATED in at least one row of the
    delivered artifact, or DECLARED in ``not_generated`` with the group that explains it
    (``B`` legitimately not applicable, ``C`` the model does not carry the data, ``D`` the
    spec itself declares it unverified). A new required column that arrives empty therefore
    fails here BY NAME instead of shipping as an unexplained blank.
    """
    undeclared = sorted(
        set(focus12_spec.required_names) - _artifact_populated(focus_dir) - set(provenance["not_generated"])
    )
    assert not undeclared, (
        "coluna obrigatoria vazia em todas as linhas e sem declaracao em _provenance.json: "
        f"{undeclared}"
    )


def test_the_declaration_matches_the_module_and_names_real_columns(
    focus12_spec: SurfaceSpec, provenance: dict[str, Any]
) -> None:
    """The shipped declaration cannot drift from the code, and declares only spec columns."""
    assert set(provenance["not_generated"]) == set(focus_azure.NOT_GENERATED)
    assert provenance["conditional"] == focus_azure.CONDITIONAL_COLUMNS
    assert set(provenance["not_generated"]) <= set(focus12_spec.names)


def test_every_declared_column_carries_a_group_and_a_reason(provenance: dict[str, Any]) -> None:
    allowed = {
        focus_azure.GROUP_NOT_APPLICABLE,
        focus_azure.GROUP_MODEL_GAP,
        focus_azure.GROUP_SPEC_UNVERIFIED,
    }
    for name, entry in provenance["not_generated"].items():
        assert entry["group"] in allowed, name
        assert len(entry["reason"].strip()) > 40, f"{name}: motivo ausente ou curto demais"


def test_declared_columns_are_empty_in_the_artifact(focus_dir: Path, provenance: dict[str, Any]) -> None:
    """A declaration that hid a populated column would be worse than no declaration."""
    lying = sorted(set(provenance["not_generated"]) & _artifact_populated(focus_dir))
    assert not lying, f"declaradas como vazias mas com valor no artefato: {lying}"


def test_conditional_columns_are_populated_somewhere(
    focus_dir: Path, provenance: dict[str, Any]
) -> None:
    """A column declared as partially filled must actually be filled somewhere."""
    never = sorted(set(provenance["conditional"]) - _artifact_populated(focus_dir))
    assert not never, f"declaradas como parciais mas ausentes no artefato: {never}"


def test_the_provenance_counts_agree_with_the_delivered_artifact(
    focus_dir: Path, provenance: dict[str, Any]
) -> None:
    """The report is measured on the records that were written, and this proves it."""
    emitted = set(columns_of(focus_dir / "focus.csv"))
    populated = set(populated_of(focus_dir / "focus.csv"))

    assert set(provenance["columns"]) == emitted
    assert provenance["counts"]["emitted"] == len(emitted)
    assert provenance["counts"]["populated"] == len(populated)
    assert provenance["counts"]["empty"] == len(emitted) - len(populated)
    assert set(provenance["populated_columns"]) == populated
    assert set(provenance["empty_columns"]) == emitted - populated


def test_the_unverified_columns_are_declared_and_never_emitted(
    focus_dir: Path, provenance: dict[str, Any]
) -> None:
    """The two names the spec describes but does not verify: declared, and absent from the file.

    They are why group ``D`` exists. The spec no longer makes them ``required`` -- a required
    column the documentation does not verify made a clean artifact impossible -- so omitting
    them is the faithful answer instead of a missing-column finding.
    """
    declared = {
        name
        for name, entry in provenance["not_generated"].items()
        if entry["group"] == focus_azure.GROUP_SPEC_UNVERIFIED
    }
    assert declared == set(_FOCUS12_REFUSED)
    for name in _FOCUS_ARTIFACTS:
        assert declared & set(columns_of(focus_dir / name)) == set()


def test_the_run_document_declares_every_unfilled_contracted_field(
    export_run_file: Path, manifest_spec: SurfaceSpec, provenance: dict[str, Any]
) -> None:
    """The sibling surface obeys the SAME rule: filled, or declared with a reason.

    Eleven of the run document's twelve contracted fields need an export DEFINITION the
    canonical estate does not model, so they are empty -- and each one names its gap instead of
    leaving a blank the reader has to interpret. The declaration lives in the same delivered
    report, under ``sibling_surface``.
    """
    sibling = provenance["sibling_surface"]
    populated = set(populated_of(export_run_file))

    assert set(sibling["columns"]) == set(manifest_spec.emittable_names)
    assert set(sibling["not_generated"]) == set(focus_azure.MANIFEST_NOT_GENERATED)
    assert set(sibling["not_generated"]) <= set(manifest_spec.names)
    assert set(sibling["populated_columns"]) == populated

    undeclared = sorted(set(sibling["columns"]) - populated - set(sibling["not_generated"]))
    assert not undeclared, f"campo contratado vazio e sem declaracao: {undeclared}"
    for name, entry in sibling["not_generated"].items():
        assert entry["group"] == focus_azure.GROUP_MODEL_GAP, name
        assert len(entry["reason"].strip()) > 40, f"{name}: motivo ausente ou curto demais"

    # Declaring the gap must not become an excuse for an unfaithful document.
    assert is_faithful(check_artifact(manifest_spec, export_run_file))


# -- falsification: the comparison must be able to fail -----------------------------


def test_a_fabricated_column_would_be_denounced(focus_dir: Path, focus12_spec: SurfaceSpec) -> None:
    """Anti-vacuity: a name the documentation does not define cannot pass the audit."""
    names = [*columns_of(focus_dir / "focus.csv"), "x_OnDemandCost"]
    findings = check(focus12_spec, names)
    assert any(finding.kind == KIND_INVENTED and finding.column == "x_OnDemandCost" for finding in findings)


def test_a_registered_unverified_column_would_be_denounced(
    focus_dir: Path, focus12_spec: SurfaceSpec
) -> None:
    """Anti-vacuity: the name the spec registers UNVERIFIED is refused, not silently kept."""
    names = [*columns_of(focus_dir / "focus.csv"), "x_PricingCurrency"]
    findings = check(focus12_spec, names)
    assert any(finding.kind == KIND_UNVERIFIED and finding.column == "x_PricingCurrency" for finding in findings)


def test_a_missing_required_column_would_be_denounced(focus_dir: Path, focus12_spec: SurfaceSpec) -> None:
    """Anti-vacuity: dropping a documented required column cannot pass the audit."""
    names = [column for column in columns_of(focus_dir / "focus.csv") if column != "BilledCost"]
    findings = check(focus12_spec, names)
    assert any(finding.kind == KIND_MISSING and finding.column == "BilledCost" for finding in findings)


def test_a_filled_null_empty_column_would_be_denounced(focus12_spec: SurfaceSpec) -> None:
    """Anti-vacuity: the value axis bites when a null-empty column is populated."""
    findings = check_values(focus12_spec, ["SkuPriceDetails"])
    assert any(finding.kind == KIND_POPULATED_EMPTY and finding.column == "SkuPriceDetails" for finding in findings)


# -- the sibling manifest surface ---------------------------------------------------


def test_the_manifest_spec_contracts_only_the_twelve_api_fields(manifest_spec: SurfaceSpec) -> None:
    assert len(manifest_spec.columns) == _MANIFEST_COLUMNS
    assert manifest_spec.emittable_count == _MANIFEST_CONTRACTED
    assert manifest_spec.generatable_count == _MANIFEST_CONTRACTED
    assert manifest_spec.null_empty_names == frozenset()
    assert len(manifest_spec.non_emittable_names) == _MANIFEST_EXAMPLE_ONLY
    # One single documented reason keeps the other 29 out of every artifact.
    assert {column.evidence for column in manifest_spec.columns if not column.belongs_to_schema} == {
        "example-only"
    }


def test_the_renderer_derives_the_export_run_fields_from_that_spec(manifest_spec: SurfaceSpec) -> None:
    derived = tuple(column.name for column in manifest_spec.columns if column.belongs_to_schema)
    assert focus_azure._EXPORT_RUN_COLUMNS == derived
    assert len(focus_azure._EXPORT_RUN_COLUMNS) == _MANIFEST_CONTRACTED


def test_the_export_run_document_carries_exactly_the_contracted_fields(
    export_run_file: Path, manifest_spec: SurfaceSpec
) -> None:
    """Only the 12 API-documented fields come out -- and none of the 29 example-only ones."""
    names = columns_of(export_run_file)

    assert len(names) == _MANIFEST_CONTRACTED
    assert set(names) == set(manifest_spec.emittable_names)
    assert set(names) & manifest_spec.forbidden_names == set()
    assert is_faithful(check_artifact(manifest_spec, export_run_file))


def test_the_official_manifest_example_is_faithfully_rejected(
    manifest_spec: SurfaceSpec, tmp_path: Path
) -> None:
    """The other direction: the ONE official manifest artifact is not a contract.

    Flattened onto the spec's own field spelling, the official example is refused in full:
    every one of its 29 ``example-only`` fields is ``unverified_emitted`` and every one of
    the 12 contracted fields is ``missing``. This is what "the manifest file cannot be
    emitted" means executably.
    """
    example_path = tmp_path / "official_manifest_example.json"
    example_path.write_text(json.dumps(_flatten_example(_OFFICIAL_MANIFEST_EXAMPLE)), encoding="utf-8")

    findings = check(manifest_spec, columns_of(example_path))
    grouped = _by_kind(findings)

    assert grouped[KIND_UNVERIFIED] == set(manifest_spec.non_emittable_names)
    assert grouped[KIND_MISSING] == set(manifest_spec.emittable_names)
    assert set(grouped) == {KIND_UNVERIFIED, KIND_MISSING}
    assert not is_faithful(findings)
