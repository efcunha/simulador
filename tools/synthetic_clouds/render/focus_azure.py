"""Azure Cost Management FOCUS 1.2-preview export renderer (CSV + Parquet).

Projects ``BillingLine`` rows into the ``FocusCost 1.2-preview`` schema Microsoft
publishes. Verified against ``parser.py (modulo do consumidor)``: emitting ``BilledCost`` +
``BillingPeriodStart`` makes ``_detect_dialect`` select ``focus``.

THE COLUMN SET IS DERIVED FROM THE SPECIFICATION, NOT RETYPED
-------------------------------------------------------------
``_COLUMNS`` IS the cited specification's column list, in the specification's own order,
filtered to the columns that BELONG to the schema (``belongs_to_schema``: a name, a
documented type, a verified status, the official URL, and an ``evidence`` of ``declared``
or ``null-empty``). There is no second copy to drift: if
``specs/azure/cost-management-export-focus12.schema.json`` gains or loses a column, this
renderer emits the new set. The former hand-written 86-name tuple was the mirror image of
that failure -- it carried 13 names Microsoft does not publish and omitted 31 that it does.

BELONGING TO THE SCHEMA AND RECEIVING A VALUE ARE TWO CONTRACTS
---------------------------------------------------------------
The specification separates them, and so does this module:

* ``evidence: null-empty`` -- six columns (``CapacityReservationId``,
  ``CapacityReservationStatus``, ``CommitmentDiscountQuantity``,
  ``CommitmentDiscountStatus``, ``CommitmentDiscountUnit``, ``SkuPriceDetails``) are
  documented as PRESENT in the 1.2-preview file and never populated
  (``cost-management-export-focus12.md`` §3.1). Omitting one breaks the format; filling
  one breaks the contract. They are emitted EMPTY and ``_require_columns`` refuses a
  value in any of them. This is why ``CommitmentDiscountQuantity``/``Status``/``Unit``
  no longer project the ``Commitment`` the row names while ``CommitmentDiscountId`` and
  ``CommitmentDiscountName`` (both ``declared``) still do.
* two documented names -- ``x_InvoiceIssuerId`` and ``x_SkuTerm`` -- are registered
  UNVERIFIED: the schema page enumerates 105 columns and the official
  ``FocusCost_1.2-preview.json`` metadata 106, so presence and type are disputed between
  two official Microsoft sources (§4). Only a verified column may reach an artifact, so
  neither is emitted. ``_columns_of_spec`` pins that refusal set and fails closed if the
  specification ever resolves it, because the file width would change.

WHAT WAS REMOVED, AND ON WHICH EVIDENCE
---------------------------------------
Thirteen names the previous tuple emitted are absent from the 1.2-preview schema and are
gone. No spec amendment was needed for any of them: the specification's §5 records that
the two official enumerations disagree about exactly three items (``x_InvoiceIssuerId``
and ``x_SkuTerm`` present in the metadata JSON only, ``x_PricingCurrency`` on the schema
page only, and ``x_SkuPlanName``/``x_SkuPartNumber`` swapped at 101/102), so a name
missing from the 106-column metadata JSON is also missing from the 105-column page.

* ``AvailabilityZone`` -- the schema page states the column "não existe no dataset de
  custos e a coluna não está incluída"; the FOCUS 1.2 core column is deliberately not
  part of this dataset.
* ``PricingCurrencyContractedUnitPrice`` / ``PricingCurrencyEffectiveCost`` /
  ``PricingCurrencyListUnitPrice`` -- the FOCUS 1.2 ``PricingCurrency*`` trio is not in
  either official enumeration of this surface (Microsoft declares 94% FOCUS 1.2
  conformance; the gap is published).
* ``x_ChargeId``, ``x_MeterId``, ``x_MeterName``, ``x_OnDemandCost``, ``x_ResourceGroup``
  -- absent from both enumerations. Where 1.2-preview renamed the concept, the CONTRACTED
  spelling is what this renderer emits (``x_SkuMeterId``, ``x_SkuMeterName``,
  ``x_ResourceGroupName``), derived from the spec and left empty because the canonical
  estate models no meter id or resource-group name.
* ``x_SubscriptionId``, ``x_UsageQuantity``, ``x_UsageUnit`` -- absent from both
  enumerations; the contracted spellings are ``SubAccountId`` (already emitted from the
  Azure subscription GUID) plus ``PricingQuantity``/``ConsumedQuantity`` and
  ``PricingUnit``/``x_PricingUnitDescription``.
* ``x_PricingCurrency`` -- registered UNVERIFIED (§4): the schema page lists it as column
  79 while the metadata JSON omits it. Emitting it is ``unverified_emitted``, so the
  renderer stops choosing a side.

EVERY COLUMN THAT COMES OUT EMPTY IS A DECLARED DECISION
--------------------------------------------------------
``required`` in FOCUS means the COLUMN must exist; the VALUE may be absent when it does not
apply. So "61 of 104 required columns are blank in every row" is a question, not a verdict.
Every one of them is now classified and declared in :data:`NOT_GENERATED` (groups ``B``
legitimately not applicable, ``C`` applicable but not modelled, ``D`` documented but not
verified, therefore not allowed to exist), with the reason attached to each. The declaration
ships INSIDE the delivery as ``_provenance.json``, next to the data, and
``tests/test_focus_azure_spec_fidelity.py`` enforces the invariant: a required column of the
spec is either populated on a delivered row or declared -- a new column that arrives blank
fails by name rather than shipping as an unexplained hole.

Where a value IS derivable it is projected instead of declared: the resource the line names
supplies ``ResourceType``/``SkuId``/``x_CostCenter``, the commitment supplies
``CommitmentDiscountName``/``Category``/``Type``, the line supplies
``ChargeFrequency``/``InvoiceIssuerName``/``PublisherName``/``PricingCurrency``/
``SubAccountType``, and the billing account supplies ``x_BillingAccountId``/
``x_BillingAccountName``. The columns that are filled only on PART of the rows carry their
condition in :data:`CONDITIONAL_COLUMNS`.

Tags encoding (verified against ``parse_cur_cost_dataframe_with_resources``): BOTH
formats write ``Tags`` as a JSON string of a list of ``[key, value]`` pairs. The
resource-grain parser's only branch that fires after ``pd.read_parquet`` is the
``isinstance(val, str)`` one (an arrow list column materializes as a numpy ``ndarray``,
so the native-list branch never matches); using the same encoding in both writers keeps
the tag contract observable and identical. The official Azure Parquet tag encoding stays
``TODO-verificar``.

Every column the specification contracts is emitted; no column is filled with a plausible
default: absence is absence, and the reason for every absence is declared.
"""

from __future__ import annotations

import csv
import io
import json
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from tools.synthetic_clouds.fidelity.spec import SurfaceSpec, load_spec
from tools.synthetic_clouds.model.billing import BillingLine
from tools.synthetic_clouds.model.commitments import Commitment
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.identity import azure_subscription_guid
from tools.synthetic_clouds.model.resource import Resource
from tools.synthetic_clouds.render.base import RenderError
from tools.synthetic_clouds.render.markers import unmarked_name

_SIX = Decimal("0.000001")

# FOCUS ServiceProviderName value that identifies this renderer's own provider.
_AZURE_PROVIDER = "Microsoft Azure"

# <repo>/tools/synthetic_clouds/render/focus_azure.py -> parents[3] is the repo root.
_SPECS_ROOT: Path = Path(__file__).resolve().parents[3] / "specs"
FOCUS12_SPEC_PATH: Path = _SPECS_ROOT / "azure" / "cost-management-export-focus12.schema.json"
MANIFEST_SPEC_PATH: Path = _SPECS_ROOT / "azure" / "cost-management-export-manifest.schema.json"


def specification() -> SurfaceSpec:
    """Load the cited ``azure/cost-management-export-focus12`` specification."""
    return load_spec(FOCUS12_SPEC_PATH)


def manifest_specification() -> SurfaceSpec:
    """Load the manifest specification of the SAME delivery (``delivery.manifest``)."""
    return load_spec(MANIFEST_SPEC_PATH)


# Names the specification DESCRIBES but does not verify: present in the official metadata
# JSON, absent from the schema page that documents the same 1.2-preview dataset, so their
# presence/type is disputed between two official Microsoft sources
# (``cost-management-export-focus12.md`` §4). Only a verified column may exist, so they
# are not emitted -- and pinning the set here makes a spec edit that resolves the dispute
# fail loudly instead of changing the file width in silence.
_REFUSED_COLUMNS: tuple[str, ...] = ("x_InvoiceIssuerId", "x_SkuTerm")


def _columns_of_spec() -> tuple[str, ...]:
    """Return the spec's schema columns, in the spec's order -- derived, never retyped."""
    spec = specification()
    refused = tuple(column.name for column in spec.columns if not column.belongs_to_schema)
    if refused != _REFUSED_COLUMNS:
        raise RenderError(
            f"focus_azure: {spec.surface} passou a descrever {len(refused)} colunas fora do "
            f"formato: {list(refused)}; as esperadas sao {list(_REFUSED_COLUMNS)}. Reconcilie "
            "specs/azure/cost-management-export-focus12.md (§4) com este renderer antes de "
            "mudar a largura do arquivo."
        )
    return tuple(column.name for column in spec.columns if column.belongs_to_schema)


# The emitted columns, in the specification's own order (104 of the 106 documented names:
# the 98 generatable ones plus the 6 null-empty ones). Derived at import; the module
# cannot disagree with the cited specification without failing here.
_COLUMNS: tuple[str, ...] = _columns_of_spec()

# Columns that belong to the file and may never receive a value (``evidence: null-empty``).
_NULL_EMPTY: frozenset[str] = specification().null_empty_names

# FOCUS 1.2 ``ChargeFrequencyLiteral`` -- the domain the Azure schema page publishes for this
# column (``One-Time`` | ``Recurring`` | ``Usage-Based``) -- derived from the charge category,
# which is the only frequency signal the canonical model carries. Same derivation the sibling
# AWS renderer documents (``focus_aws._CHARGE_FREQUENCY``): this is FOCUS vocabulary, not
# provider vocabulary, so projecting it for Azure is not a provider-boundary crossing.
_CHARGE_FREQUENCY: dict[str, str] = {
    "Usage": "Usage-Based",
    "Purchase": "Recurring",
    "Tax": "Recurring",
    "Credit": "One-Time",
    "Adjustment": "One-Time",
}

# FOCUS 1.2 ``CommitmentDiscountCategoryLiteral`` (``Spend`` | ``Usage`` -- the Azure schema
# page publishes both), keyed by the canonical ``Commitment.kind``: a Savings Plan commits an
# AMOUNT, a reservation/CUD commits measured capacity. Provider-neutral derivation.
_COMMITMENT_CATEGORY: dict[str, str] = {
    "savings_plan": "Spend",
    "reservation": "Usage",
    "cud": "Usage",
}

#: A column that is EMPTY in every row of the delivered artifact, because it is either
#: legitimately not applicable to this estate (``B``), applicable but not modelled (``C``), or
#: documented yet not verified by the specification (``D``), in which case it may not exist at
#: all. Every entry carries the reason it is empty: "the documentation does not publish this
#: value" must read differently from "the model does not carry it", and an empty column nobody
#: explained is indistinguishable from a bug.
GROUP_NOT_APPLICABLE = "B"
GROUP_MODEL_GAP = "C"
GROUP_SPEC_UNVERIFIED = "D"

_NOT_GENERATED_GROUPS: tuple[tuple[str, tuple[str, ...], str], ...] = (
    # -- D: documented, but the specification itself declares it unverified --------------
    (
        GROUP_SPEC_UNVERIFIED,
        ("x_InvoiceIssuerId", "x_SkuTerm"),
        "obrigatoria na spec E marcada unverified (a pagina de schema enumera 105 colunas e o "
        "metadata JSON oficial 106, e as duas divergem): emitir e unverified_emitted, omitir e "
        "missing, e nenhum artefato satisfaz as duas. O renderer so emite coluna verificada "
        "(spec secao 4).",
    ),
    # -- B: belongs to the format, never has a value in this dataset ---------------------
    (
        GROUP_NOT_APPLICABLE,
        ("CapacityReservationId", "CapacityReservationStatus"),
        "a spec marca as duas como 'Currently null/empty' na 1.2-preview (evidence=null-empty): "
        "a coluna existe sempre no arquivo e nunca tem valor. A estate tambem nao modela reserva "
        "de capacidade Azure (CAPACITY_RESERVATION_TYPES nao tem chave azure), entao nao haveria "
        "o que projetar nem se o contrato permitisse.",
    ),
    (
        GROUP_NOT_APPLICABLE,
        ("CommitmentDiscountQuantity", "CommitmentDiscountStatus", "CommitmentDiscountUnit"),
        "a spec marca as tres como 'Currently null/empty' na 1.2-preview (evidence=null-empty): o "
        "arquivo carrega as colunas e nunca as preenche. As linhas C05 do modelo TEM status "
        "Unused, quantidade e unidade, mas o contrato proibe o valor -- e' o caso em que a "
        "fidelidade manda deixar vazio um dado que existe (spec secao 3.1).",
    ),
    (
        GROUP_NOT_APPLICABLE,
        ("SkuPriceDetails",),
        "a spec marca como 'Currently null/empty' e o resumo de conformidade da Microsoft manda "
        "usar x_SkuDetails; e o proprio x_SkuDetails e' lacuna de modelo (C).",
    ),
    (
        GROUP_NOT_APPLICABLE,
        ("ChargeClass",),
        "o unico valor permitido e 'Correction' e so uma linha de correcao o carrega. A unica "
        "correcao da estate (C17) reafirma uma cobranca GCP, e um export Azure nao carrega "
        "cobranca GCP: a coluna sai vazia em todas as linhas. O renderer projeta o literal no dia "
        "em que uma linha de correcao Azure existir.",
    ),
    # -- C: applicable, the canonical model does not carry the data ----------------------
    (
        GROUP_MODEL_GAP,
        ("BillingAccountType",),
        "o BillingAccount canonico carrega id, nome e moeda -- nao o tipo de contrato "
        "(EA/MCA/MOSA) que a coluna rotula, e o rotulo varia por contrato.",
    ),
    (
        GROUP_MODEL_GAP,
        ("ChargeDescription", "ServiceSubcategory"),
        "a tabela de descricoes do catalogo (generate/constants.py::FOCUS_SERVICE_DESCRIPTIONS) "
        "so tem a chave 'aws'; preencher a Azure exigiria um segundo vocabulario nao auditado "
        "keyed por MeterCategory, que e' a fabricacao que a regra de ouro proibe.",
    ),
    (
        GROUP_MODEL_GAP,
        ("SkuMeter", "x_SkuMeterName"),
        "o modelo nao guarda nome de medidor: SkuMeter/x_SkuMeterName descrevem o medidor do SKU "
        "e o catalogo so tem sku_id, unidade e preco. (focus_aws projeta a unidade de preco em "
        "SkuMeter; unidade nao e' medidor, e copiar isso para a Azure apresentaria um palpite de "
        "outro provedor como confirmado.)",
    ),
    (
        GROUP_MODEL_GAP,
        ("SkuPriceId",),
        "a identidade de preco nao existe no modelo: o price book tem UMA linha por sku_id "
        "(ListPrice/ContractedPrice), sem id de preco. A derivacao de focus_aws e' TODO-verificar, "
        "e a propria spec da Azure registra que SkuPriceId nao identifica um preco unico nem tem "
        "equivalente no price sheet.",
    ),
    (
        GROUP_MODEL_GAP,
        ("x_AccountId", "x_AccountName", "x_AccountOwnerId"),
        "o modelo nao tem a identidade responsavel pelo faturamento da assinatura (dono da conta "
        "de inscricao EA / admin MOSA).",
    ),
    (
        GROUP_MODEL_GAP,
        ("x_AmortizationClass",),
        "o modelo nao classifica a linha em Principal/Amortized Charge: a amortizacao entra como "
        "VALOR (EffectiveCost), nao como classe da linha.",
    ),
    (
        GROUP_MODEL_GAP,
        ("x_BillingExchangeRateDate",),
        "o modelo nao guarda a data da taxa de cambio; a taxa e' o literal 1.0 do simulador "
        "(estate denominada em uma unica moeda), sem data associada.",
    ),
    (
        GROUP_MODEL_GAP,
        ("x_BillingProfileId", "x_BillingProfileName", "x_InvoiceSectionId", "x_InvoiceSectionName"),
        "o modelo nao tem perfil de faturamento nem secao de fatura (MCA) / departamento (EA): a "
        "hierarquia para em conta de faturamento -> assinatura.",
    ),
    (
        GROUP_MODEL_GAP,
        ("x_CostAllocationRuleName",),
        "o modelo nao tem regras de alocacao de custo (rateio de cobranca compartilhada).",
    ),
    (
        GROUP_MODEL_GAP,
        (
            "x_CustomerId",
            "x_CustomerName",
            "x_ResellerId",
            "x_ResellerName",
            "x_PartnerCreditApplied",
            "x_PartnerCreditRate",
        ),
        "o modelo nao tem o canal CSP (cliente, revendedor, Partner Earned Credit): a estate e' "
        "de faturamento direto, entao esses campos nao tem sujeito.",
    ),
    (
        GROUP_MODEL_GAP,
        ("x_PricingBlockSize",),
        "o catalogo nao tem preco em bloco; sem bloco nao ha tamanho de bloco, e a spec define a "
        "coluna como parte da unidade de preco.",
    ),
    (
        GROUP_MODEL_GAP,
        ("x_PricingSubcategory",),
        "o modelo nao tem o vocabulario de subcategoria de preco dentro de uma PricingCategory; "
        "PricingCategory (Standard/Committed) e' outra coluna e ja sai preenchida.",
    ),
    (
        GROUP_MODEL_GAP,
        ("x_PublisherCategory",),
        "a spec nao publica o dominio e o modelo nao distingue provedor de marketplace: a Azure "
        "desta estate e' 100% primeira parte, e um rotulo inventado seria pior que o vazio.",
    ),
    (
        GROUP_MODEL_GAP,
        ("x_PublisherId",),
        "o modelo nao tem identificador de publicador (nem um id Microsoft), so o nome do "
        "provedor, que sai em PublisherName/InvoiceIssuerName.",
    ),
    (
        GROUP_MODEL_GAP,
        ("x_ResourceGroupName",),
        "o Resource canonico NAO carrega resource group. O unico vestigio e' o logical_path da "
        "identidade ('azure/sub-01/rg-prod/vm/web-01'), que e' um id de modelagem e nao metadado "
        "do recurso -- parsea-lo derivaria um campo de provedor de um artefato interno. Mesma "
        "lacuna registrada em render/azure_arm_instances.py::_model_gaps.",
    ),
    (
        GROUP_MODEL_GAP,
        ("x_ResourceType",),
        "a coluna pede o tipo ARM ('Microsoft.Compute/virtualMachines'); o modelo so tem o token "
        "resource_type ('virtual_machine') e nao ha mapa para o tipo ARM. Mesma lacuna registrada "
        "em render/azure_arm_instances.py::_model_gaps. ResourceType (FOCUS) e' outra coluna e "
        "sai preenchida com o token do modelo.",
    ),
    (
        GROUP_MODEL_GAP,
        ("x_ServiceModel",),
        "o modelo nao classifica o servico em IaaS/PaaS/SaaS.",
    ),
    (
        GROUP_MODEL_GAP,
        ("x_SkuDescription", "x_SkuDetails"),
        "o catalogo nao guarda descricao do SKU nem as propriedades que x_SkuDetails carrega como "
        "objeto JSON (a spec diz que x_SkuDetails esta para ser removida quando SkuPriceDetails "
        "ficar pronta).",
    ),
    (
        GROUP_MODEL_GAP,
        ("x_SkuIsCreditEligible",),
        "o modelo tem Credit por ESCOPO, nao elegibilidade de credito por SKU.",
    ),
    (
        GROUP_MODEL_GAP,
        ("x_SkuMeterCategory", "x_SkuMeterSubcategory"),
        "nao ha vocabulario de categoria/subcategoria de medidor no modelo. service_name e "
        "service_category sao colunas FOCUS distintas; projeta-las aqui afirmaria que os dois "
        "vocabularios coincidem, que e' exatamente a inferencia que a regra de ouro recusa.",
    ),
    (
        GROUP_MODEL_GAP,
        ("x_SkuMeterId",),
        "o modelo nao tem id de medidor, e a Azure nao publica a forma ('sometimes a GUID, but "
        "not always'): cunhar um id sem forma documentada seria inventar identificador de "
        "provedor. O token do catalogo sai em SkuId, que e' a coluna que se define como o "
        "construto de SKU suportado pelo provedor.",
    ),
    (
        GROUP_MODEL_GAP,
        ("x_SkuOfferId",),
        "o modelo nao tem o tipo de assinatura Microsoft (offer id).",
    ),
    (
        GROUP_MODEL_GAP,
        ("x_SkuOrderId", "x_SkuOrderName", "x_SkuPlanName"),
        "o modelo nao tem produto de direito (order) nem plano de Marketplace; a Azure desta "
        "estate e' EA/direta, nao Marketplace.",
    ),
    (
        GROUP_MODEL_GAP,
        ("x_SkuPartNumber",),
        "o modelo nao tem part number (o identificador que quebra medidores). O token do catalogo "
        "ja sai em SkuId, e repeti-lo aqui diria que os dois ids sao o mesmo, que a spec nao "
        "afirma.",
    ),
    (
        GROUP_MODEL_GAP,
        ("x_SkuServiceFamily", "x_SkuTier"),
        "o modelo nao tem familia de SKU nem tier de preco graduado; service_category e' a coluna "
        "FOCUS ServiceCategory, e projeta-la aqui afirmaria uma equivalencia de vocabularios que "
        "a documentacao nao publica.",
    ),
)

#: The single declaration the artifact and the tests read: every column of the spec this
#: renderer does not fill, with the group explaining WHY (see the group constants above).
NOT_GENERATED: dict[str, tuple[str, str]] = {
    name: (group, reason) for group, names, reason in _NOT_GENERATED_GROUPS for name in names
}

#: Columns the renderer CAN fill but that are empty on PART of the rows, with the condition.
#: Not a gap: a value that exists only sometimes, declared so the empty cell is readable.
CONDITIONAL_COLUMNS: dict[str, str] = {
    "PublisherName": "vazio nas linhas de compromisso NAO usado (CommitmentDiscountStatus "
    "'Unused'), que o resumo de conformidade da Microsoft documenta como nulas para esta coluna.",
    "ResourceType": "vazio na linha FR-D5 sem recurso (nao ha tipo de recurso a nomear).",
    "SkuId": "vazio na linha FR-D5 sem recurso (nao ha SKU a nomear).",
    "CommitmentDiscountCategory": "vazio em linha que nao nomeia compromisso nenhum.",
    "CommitmentDiscountType": "vazio em linha que nao nomeia compromisso nenhum.",
    "x_CostCenter": "vazio em recurso sem a tag 'cost_center' (a estate tem ~15% de recursos sem "
    "tags, e o valor e' sempre o do cliente, nunca um default).",
}


def _validate_declaration() -> None:
    """Fail closed when the empty-column declaration stops describing this specification.

    Two ways the declaration can rot, both fatal at import: naming a column the spec does not
    have, and failing to name exactly the documented-but-unverified columns (group ``D``) --
    those may not be emitted, so an undeclared one would be an outage with no explanation.
    """
    spec = specification()
    unknown = sorted(set(NOT_GENERATED) - set(spec.names))
    if unknown:
        raise RenderError(
            f"focus_azure: a declaracao de colunas vazias nomeia colunas que {spec.surface} nao "
            f"tem: {unknown}"
        )
    unverified = tuple(column.name for column in spec.columns if not column.belongs_to_schema)
    declared_unverified = tuple(
        name for name, (group, _reason) in NOT_GENERATED.items() if group == GROUP_SPEC_UNVERIFIED
    )
    if declared_unverified != unverified:
        raise RenderError(
            "focus_azure: as colunas que a spec descreve e nao verifica mudaram: "
            f"spec={list(unverified)} declaradas={list(declared_unverified)}"
        )
    conditional_unknown = sorted(set(CONDITIONAL_COLUMNS) - set(_COLUMNS))
    if conditional_unknown:
        raise RenderError(
            f"focus_azure: CONDITIONAL_COLUMNS nomeia colunas que nao sao emitidas: {conditional_unknown}"
        )


_validate_declaration()


def _export_run_columns() -> tuple[str, ...]:
    """The sibling manifest surface's CONTRACTED fields -- the 12 the REST API documents.

    ``azure/cost-management-export-manifest`` has 41 columns: 12 whose name, type and
    presence the official REST pages establish, and 29 that exist only inside the single
    official ``_manifest.json`` example (``evidence: example-only``). An example is not a
    contract, so the 29 can never be emitted; the guard below fails closed if that
    boundary moves -- in either direction.
    """
    spec = manifest_specification()
    uncontractable = tuple(
        column.name
        for column in spec.columns
        if not column.belongs_to_schema and (column.evidence or "").lower() != "example-only"
    )
    if uncontractable:
        raise RenderError(
            f"focus_azure: {spec.surface} tem colunas fora do formato que nao sao "
            f"'example-only': {list(uncontractable)}; o documento de execucao so pode emitir "
            "os campos com contrato publicado."
        )
    contracted = tuple(column.name for column in spec.columns if column.belongs_to_schema)
    if not contracted:
        raise RenderError(
            f"focus_azure: {spec.surface} nao tem nenhum campo com contrato publicado; "
            "o documento de execucao nao pode ser emitido."
        )
    return contracted


# The 12 contracted fields of the manifest surface, in the spec's order. Derived, so the
# 29 example-only names cannot leak in and a newly contracted field cannot be forgotten.
_EXPORT_RUN_COLUMNS: tuple[str, ...] = _export_run_columns()

#: The run document's OWN empty fields, declared one by one for the same reason the FOCUS
#: columns are: ``required`` says the field must exist, not that it must carry a value. All
#: eleven need an export DEFINITION (the user-owned object the REST API creates), which the
#: canonical estate does not model -- so they are group ``C`` gaps, not oversights.
MANIFEST_NOT_GENERATED: dict[str, tuple[str, str]] = {
    "manifestFile": (
        GROUP_MODEL_GAP,
        "o caminho do manifesto e' definido pelo export que o usuario criou "
        "(StorageContainer/StorageDirectory/ExportName/[periodo]/[RunID]); a estate nao modela "
        "export nenhum, entao nao ha caminho a citar.",
    ),
    "properties.partitionData": (
        GROUP_MODEL_GAP,
        "e' configuracao do export (a propriedade que CRIA o manifesto). O simulador escreve um "
        "arquivo por formato, nao particiona por tamanho, e escolher true/false afirmaria uma "
        "configuracao que ninguem definiu.",
    ),
    "fileName": (
        GROUP_MODEL_GAP,
        "o nome do arquivo entregue e' derivado por Azure de ExportName+RunId; sem export "
        "modelado nao ha nome unico -- e este renderer escreve csv E parquet.",
    ),
    "runSettings.partitionData": (
        GROUP_MODEL_GAP,
        "configuracao de particionamento em vigor na run: nao ha export nem run modelados.",
    ),
    "runSettings.format": (
        GROUP_MODEL_GAP,
        "formato em vigor na run: o renderer entrega CSV e Parquet, entao nao existe UM valor "
        "verdadeiro para esta run, e escolher um afirmaria uma configuracao inexistente.",
    ),
    "runSettings.compressionMode": (
        GROUP_MODEL_GAP,
        "compressao em vigor na run: CSV sai sem compressao e Parquet sai snappy, entao tambem "
        "nao ha um valor unico.",
    ),
    "runSettings.dataOverwriteBehavior": (
        GROUP_MODEL_GAP,
        "OverwritePreviousReport/CreateNewReport e' configuracao do export, nao modelada.",
    ),
    "executionType": (
        GROUP_MODEL_GAP,
        "OnDemand/Scheduled e' propriedade da run; a estate nao modela agendamento de export.",
    ),
    "submittedBy": (
        GROUP_MODEL_GAP,
        "a identidade que disparou o export (email do usuario em run on-demand, 'System' em "
        "agendada) nao existe no modelo: nao ha usuario nem scheduler a nomear.",
    ),
    "processingStartTime": (
        GROUP_MODEL_GAP,
        "instante em que o processamento da run comecou; o modelo tem janela de simulacao "
        "(sim_start/sim_now) e export_time por linha, nao o processamento de um export.",
    ),
    "processingEndTime": (
        GROUP_MODEL_GAP,
        "instante em que o processamento da run terminou: mesma lacuna de processingStartTime.",
    ),
}


def _export_run_record() -> dict[str, Any]:
    """The run document's fields: the contracted set, with the ONE fact this run establishes.

    A run that produced this document completed, which is the state the official run-history
    examples spell ``Completed``. Every other field is empty for the declared reasons in
    :data:`MANIFEST_NOT_GENERATED`.
    """
    record: dict[str, Any] = dict.fromkeys(_EXPORT_RUN_COLUMNS, "")
    record["status"] = "Completed"
    return record


def _export_run_populated() -> tuple[str, ...]:
    """The run document's fields that carry a value -- measured on the document itself."""
    record = _export_run_record()
    return tuple(name for name in _EXPORT_RUN_COLUMNS if record[name])


def _validate_manifest_declaration() -> None:
    """Fail closed when the run document's declaration stops matching its contract."""
    declared = set(MANIFEST_NOT_GENERATED)
    unknown = sorted(declared - set(_EXPORT_RUN_COLUMNS))
    if unknown:
        raise RenderError(
            f"focus_azure: a declaracao do documento de execucao nomeia campos que "
            f"{manifest_specification().surface} nao contrata: {unknown}"
        )
    undeclared_empty = sorted(set(_EXPORT_RUN_COLUMNS) - set(_export_run_populated()) - declared)
    if undeclared_empty:
        raise RenderError(
            "focus_azure: campos contratados do documento de execucao vazios e sem declaracao: "
            f"{undeclared_empty}. Declare o motivo (MANIFEST_NOT_GENERATED) ou preencha o campo."
        )


_validate_manifest_declaration()


def _money(value: Decimal) -> str:
    return str(value.quantize(_SIX, ROUND_HALF_EVEN))


def _resource_id(line: BillingLine) -> str:
    """Return the FOCUS ResourceId: empty for the FR-D5 null line (OA-4)."""
    return "" if line.resource_uuid is None else line.resource_uuid


def _tag_json(line: BillingLine) -> str:
    """``Tags`` in the ONE encoding both writers use: a JSON list of ``[key, value]``."""
    return json.dumps([[key, value] for key, value in line.tags], sort_keys=False)


def _unit_price(cost: Decimal, quantity: Decimal) -> str:
    """Unit price implied by a cost and its quantity, or empty when unquotable.

    A tax or fully-credited line legitimately carries zero quantity; the
    official schema allows null there, and a division would raise.
    """
    if not quantity:
        return ""
    return _money(cost / quantity)


class _AccountNames:
    """Estate-wide names a single billing line cannot resolve by itself.

    The FOCUS schema names the billing account and the sub account, and the estate
    models both: ``BillingAccount.name`` and ``AzureSubscription.name``
    (``model/hierarchy.py:24,35``). Both carry the FinOps ``[SYNTH] `` storage
    marker (``generate/estate_builder.py:193,217``), which is a FinOps-side
    discriminator no Azure export carries -- so the lookup resolves them and
    ``markers.unmarked_name`` strips the prefix. A line whose billing account or
    subscription the estate does not carry keeps the empty column (absence is absence)
    instead of an invented name.
    """

    def __init__(self, estate: CanonicalEstate) -> None:
        self.billing_account: dict[str, str] = {
            account.billing_account_id: account.name for account in estate.billing_accounts
        }
        self.subscription: dict[str, str] = {
            subscription.subscription_id: subscription.name
            for group in estate.azure_mgmt_groups
            for subscription in group.subscriptions
        }


class _Commitments:
    """The estate's commitments, keyed by the id a covered billing line carries.

    Mirrors ``focus_aws._Lookups.commitment_by_id``: both FOCUS renderers project the
    same ``Commitment`` rows, so a line the estate covers must describe its commitment
    the same way in either export. ``Name`` and the ``kind`` behind
    ``CommitmentDiscountCategory``/``Type`` are projected from the referenced row, so the
    columns that describe a commitment cannot disagree with each other.

    ``CommitmentDiscountQuantity``/``Status``/``Unit`` are ``evidence: null-empty`` in this
    surface: the 1.2-preview file carries the columns and never populates them, so
    ``_require_columns`` refuses the value the estate could supply -- even on the C05 rows,
    which DO carry a status, a quantity and a unit. That refusal is declared in
    ``NOT_GENERATED`` (group B) with its citation; it is not an oversight.
    """

    def __init__(self, estate: CanonicalEstate) -> None:
        self.by_id: dict[str, Commitment] = {
            commitment.identity.uuid: commitment for commitment in estate.commitments
        }


class _Resources:
    """The estate's resources, keyed by the identity a billing line names.

    A ``BillingLine`` carries the resource's uuid; the ``Resource`` carries the two
    provider-facing facts the FOCUS row needs -- ``resource_type`` (the FOCUS
    ``ResourceType``) and the catalog's own ``sku_id`` (the FOCUS ``SkuId``) -- plus the
    tags an Azure export reads the cost center from. A line with no resource (the FR-D5
    billing-only construct) resolves to nothing and keeps those columns empty: absence is
    absence, and defaulting them would attribute a resource to a row that has none.
    """

    def __init__(self, estate: CanonicalEstate) -> None:
        self.by_uuid: dict[str, Resource] = {
            resource.identity.uuid: resource for resource in estate.resources
        }


def _record(
    line: BillingLine,
    *,
    seed: int,
    names: _AccountNames,
    commitments: _Commitments,
    resources: _Resources,
) -> dict[str, Any]:
    """Return one FOCUS row: every emitted column, empty unless it has a source.

    Built as ``dict.fromkeys(_COLUMNS, "")`` plus the projected values, so a column the
    specification adds starts EMPTY instead of being dropped from the record, and a
    misspelled projection key is caught by :func:`_require_columns` rather than silently
    dropped by the Parquet writer (``extrasaction="raise"`` only protects the CSV one).

    The projections, and why each is a projection and not a guess:

    * ``BillingAccountId``/``BillingAccountName`` (:func:`_AccountNames`) and
      ``SubAccountId``/``SubAccountName`` -- the line's own billing account, and its Azure
      subscription GUID/name.
    * the money columns -- ``BillingLine`` carries ``billed_cost``, ``effective_cost``,
      ``list_cost`` and ``contracted_cost`` at FOCUS ``numeric(18,6)``; the ``x_*InUsd``
      mirrors restate three of them because the simulator is USD-denominated end to end
      (rate 1.0, which is what ``x_BillingExchangeRate`` states).
    * the unit prices -- ``ContractedUnitPrice``, ``ListUnitPrice`` and Azure's
      ``x_BilledUnitPrice``/``x_EffectiveUnitPrice`` are the documented quotient of one
      cost by ``PricingQuantity`` ("for a single Pricing Unit").
    * ``CommitmentDiscountId`` (the line's own id) plus ``CommitmentDiscountName``/
      ``Category``/``Type`` (the commitment that id names, see :class:`_Commitments`).
    * ``ResourceType``/``SkuId``/``x_CostCenter`` -- the resource the line names
      (:class:`_Resources`): its ``resource_type``, the catalog's ``sku_id`` token (unique
      per SKU and stable, which is what FOCUS asks of ``SkuId``), and the customer's own
      ``cost_center`` tag, never a default.
    * ``InvoiceIssuerName``/``PublisherName`` -- the entity that produced and invoiced the
      service, which the line already carries as its FOCUS ``ServiceProviderName``. Empty
      only on the rows the Microsoft conformance summary documents as null for
      ``PublisherName`` (unused commitment), so ``PublisherName`` says nothing on a row the
      provider itself leaves blank.
    * ``ChargeFrequency`` -- the FOCUS literal domain keyed by the charge category, the
      only frequency signal the model carries (:data:`_CHARGE_FREQUENCY`).
    * ``ChargeClass`` -- the one allowed literal, on the rows that carry it.
    * ``PricingCurrency``/``SubAccountType``/``x_BillingAccountId``/``x_BillingAccountName``
      -- the estate's single currency (the price book is built in the run currency, so the
      pricing and billing currencies coincide), the model's own name for the scope kind
      (``AzureSubscription``), and the billing account the row is billed to.
    * everything else projected is a field of ``BillingLine`` under its own name.
      ``ResourceName`` deserves the note that it projects the resource UUID, as it did
      before this slice; changing it is a data decision (``Resource.resource_name``), not a
      column-fidelity one.

    Every OTHER emitted column is EMPTY in this estate, and each one is declared with its
    group (B = legitimately not applicable, C = applicable but not modelled, D = documented
    but not verified) and its reason in :data:`NOT_GENERATED`; the columns that are filled
    only on part of the rows are declared in :data:`CONDITIONAL_COLUMNS`. That declaration
    is the artifact of the classification, it ships inside the delivery
    (``_provenance.json``), and ``tests/test_focus_azure_spec_fidelity.py`` fails if a
    required column is neither populated nor declared.
    """
    subscription = azure_subscription_guid(seed, line.sub_account_id)
    commitment = commitments.by_id.get(line.commitment_discount_id or "")
    resource = resources.by_uuid.get(line.resource_uuid) if line.resource_uuid else None
    billing_account_name = unmarked_name(names.billing_account.get(line.billing_account_id, ""))
    has_commitment = line.commitment_discount_id is not None
    commitment_kind = "" if commitment is None else commitment.kind
    record: dict[str, Any] = dict.fromkeys(_COLUMNS, "")
    record.update(
        {
            # -- FOCUS 1.2 core ------------------------------------------------
            "BilledCost": _money(line.billed_cost),
            "BillingAccountId": line.billing_account_id,
            # The estate's name, minus the FinOps ``[SYNTH] `` marker (see _AccountNames).
            "BillingAccountName": billing_account_name,
            "BillingCurrency": line.currency,
            "BillingPeriodEnd": line.billing_period_end.isoformat(),
            "BillingPeriodStart": line.billing_period_start.isoformat(),
            "ChargeCategory": line.charge_category,
            # The one allowed literal, on the rows that carry it (none in an Azure export
            # today: the estate's only correction line restates a GCP charge).
            "ChargeClass": "Correction" if line.is_restatement else "",
            "ChargeFrequency": _CHARGE_FREQUENCY.get(line.charge_category, ""),
            "ChargePeriodEnd": line.charge_period_end.isoformat(),
            "ChargePeriodStart": line.charge_period_start.isoformat(),
            "CommitmentDiscountCategory": (
                _COMMITMENT_CATEGORY.get(commitment_kind, "") if has_commitment else ""
            ),
            "CommitmentDiscountId": line.commitment_discount_id or "",
            "CommitmentDiscountName": "" if commitment is None else unmarked_name(commitment.name),
            "CommitmentDiscountType": commitment_kind if has_commitment else "",
            "ConsumedQuantity": _money(line.pricing_quantity),
            "ConsumedUnit": line.pricing_unit,
            "ContractedCost": _money(line.contracted_cost),
            "ContractedUnitPrice": _unit_price(line.contracted_cost, line.pricing_quantity),
            "EffectiveCost": _money(line.effective_cost),
            "InvoiceId": line.invoice_id or "",
            # The entity responsible for invoicing, which is the provider the line carries.
            "InvoiceIssuerName": line.service_provider_name,
            "ListCost": _money(line.list_cost),
            "ListUnitPrice": _unit_price(line.list_cost, line.pricing_quantity),
            # The estate prices in ONE currency, so the pricing currency is the billing one.
            "PricingCurrency": line.currency,
            "PricingCategory": line.pricing_category,
            "PricingQuantity": _money(line.pricing_quantity),
            "PricingUnit": line.pricing_unit,
            "ProviderName": line.service_provider_name,
            # Null on exactly the rows the conformance summary documents as null for this
            # column: the unused part of a commitment.
            "PublisherName": (
                "" if line.commitment_discount_status == "Unused" else line.service_provider_name
            ),
            "RegionId": line.region_id,
            "RegionName": line.region_name,
            "ResourceId": _resource_id(line),
            "ResourceName": "" if line.resource_uuid is None else line.resource_uuid,
            "ResourceType": "" if resource is None else resource.resource_type,
            "ServiceCategory": line.service_category,
            "ServiceName": line.service_name,
            "SkuId": "" if resource is None else resource.sku_id,
            "SubAccountId": subscription,
            "SubAccountName": unmarked_name(names.subscription.get(line.sub_account_id, "")),
            # The kind of entity SubAccountId names: the model's own AzureSubscription.
            "SubAccountType": "Subscription",
            # -- Azure x_* ------------------------------------------------------
            "x_BilledCostInUsd": _money(line.billed_cost),
            "x_BilledUnitPrice": _unit_price(line.billed_cost, line.pricing_quantity),
            # The Microsoft billing account the row is billed to (FOCUS documents this as
            # "Same as BillingAccountId for EA"; the estate models the billing account, and
            # the row's id IS that account's id here).
            "x_BillingAccountId": line.billing_account_id,
            "x_BillingAccountName": billing_account_name,
            "x_BillingExchangeRate": "1.0",
            "x_ContractedCostInUsd": _money(line.contracted_cost),
            # The customer's own chargeback value: the resource's ``cost_center`` tag, never
            # a default. Untagged resources leave it empty, like every other absent value.
            "x_CostCenter": dict(line.tags).get("cost_center", ""),
            "x_EffectiveCostInUsd": _money(line.effective_cost),
            "x_EffectiveUnitPrice": _unit_price(line.effective_cost, line.pricing_quantity),
            "x_ListCostInUsd": _money(line.list_cost),
            "x_PricingUnitDescription": line.pricing_unit,
            "x_ServicePeriodEnd": line.charge_period_end.isoformat(),
            "x_ServicePeriodStart": line.charge_period_start.isoformat(),
            "x_SkuRegion": line.region_name,
        }
    )
    return record


def _require_columns(record: dict[str, Any]) -> None:
    """Fail closed when a record is not exactly the emitted column set, or fills a refusal.

    ``_record`` returns ONE dict, so checking a single record checks every record. Two
    failures are caught here:

    * a divergent field set. The two writers disagree about that: a MISSING key raises in
      both, but an EXTRA key raises in the CSV writer (``extrasaction="raise"``) and is
      silently DROPPED by the Parquet writer -- the silent omission this guard exists to
      prevent; and
    * a value in a column the spec marks ``null-empty`` -- a column that belongs to the
      file and may never be filled. Omit it and the format is broken; fill it and the
      contract is. Emitting it empty is the only faithful answer.
    """
    fields = set(record)
    expected = set(_COLUMNS)
    if fields != expected:
        raise RenderError(
            "focus_azure: registro com campos diferentes das colunas emitidas: "
            f"sobram={sorted(fields - expected)} faltam={sorted(expected - fields)}"
        )
    filled = sorted(name for name in _NULL_EMPTY & fields if record[name])
    if filled:
        raise RenderError(f"focus_azure: colunas null-empty receberam valor: {filled}")


def _sorted_lines(estate: CanonicalEstate) -> list[BillingLine]:
    """This renderer's own rows, in deterministic order.

    An Azure Cost Management export carries Azure charges ONLY. Rendering every
    ``BillingLine`` of the multi-cloud estate put GCP scope labels -- and GCP cost --
    into the Azure export, which the Azure promoter then stamped
    ``service_provider_name='Microsoft Azure'``, hiding the mixture from every
    downstream screen.
    """
    return sorted(
        (line for line in estate.billing_lines if line.service_provider_name == _AZURE_PROVIDER),
        key=lambda line: line.line_id,
    )


def _rows(estate: CanonicalEstate) -> list[dict[str, Any]]:
    """Every emitted row, each one exactly the emitted column set (checked once)."""
    names = _AccountNames(estate)
    commitments = _Commitments(estate)
    resources = _Resources(estate)
    rows: list[dict[str, Any]] = []
    checked = False
    for line in _sorted_lines(estate):
        record = _record(
            line, seed=estate.seed, names=names, commitments=commitments, resources=resources
        )
        record["Tags"] = _tag_json(line)
        if not checked:
            _require_columns(record)
            checked = True
        rows.append(record)
    return rows


def _populated_columns(rows: list[dict[str, Any]]) -> tuple[str, ...]:
    """The emitted columns that carry a value in AT LEAST ONE row of ``rows``.

    Deliberately measured on the records that are about to be written, not on the
    projection code: the report has to say what the file says.
    """
    return tuple(name for name in _COLUMNS if any(row[name] for row in rows))


def _csv_bytes(rows: list[dict[str, Any]]) -> bytes:
    """Encode ``rows`` (already complete records) as the FOCUS CSV."""
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer, fieldnames=list(_COLUMNS), extrasaction="raise", lineterminator="\n"
    )
    writer.writeheader()
    for record in rows:
        writer.writerow(record)
    return buffer.getvalue().encode("utf-8")


def _parquet_bytes(rows: list[dict[str, Any]]) -> bytes:
    """Encode ``rows`` (already complete records) as one snappy Parquet file."""
    columns: dict[str, list[Any]] = {col: [row[col] for row in rows] for col in _COLUMNS}
    arrays: dict[str, pa.Array] = {col: pa.array(columns[col], type=pa.string()) for col in _COLUMNS}
    table = pa.table(arrays)
    sink = io.BytesIO()
    pq.write_table(
        table,
        sink,
        version="2.6",
        compression="snappy",
        write_statistics=False,
        store_schema=True,
    )
    return sink.getvalue()


def render_csv_bytes(estate: CanonicalEstate) -> bytes:
    """Return the FOCUS CSV bytes (``Tags`` = JSON string of list-of-pairs)."""
    return _csv_bytes(_rows(estate))


def render_parquet_bytes(estate: CanonicalEstate) -> bytes:
    """Return the FOCUS Parquet bytes (``Tags`` = JSON string of list-of-pairs).

    Encoding note (verified against the real parser + pandas, not assumed): the design
    round-2 assumed a *native* arrow ``list<list<string>>`` ``Tags`` column for Parquet.
    Empirically, ``pd.read_parquet`` (what ``parser.parse_cur_bytes`` uses) materializes
    any arrow list column as a numpy ``ndarray``, so the parser's ``isinstance(val, list)``
    native branch never matches and tags silently decode to ``{}``. The parser's ONLY
    branch that fires after ``pd.read_parquet`` is the JSON-string branch
    (``isinstance(val, str)`` -> ``json.loads`` -> list-of-pairs). Per the design's own
    binding rule -- "the chosen encoding is justified by what the real resource-grain
    parser accepts" (sec. 8.2) -- Parquet therefore uses the SAME JSON-string-of-list-of-
    pairs encoding as CSV. This preserves the binding tag fidelity contract (tags decode
    to the correct ``dict[str, str]``); the official Azure Parquet tag encoding stays
    ``TODO-verificar``. Every column is typed ``string`` for the reason ``focus_aws``
    records: money is already 6-dp text and a typed column would only add a second place
    for the precision contract to drift.
    """
    return _parquet_bytes(_rows(estate))


def _provenance_document(populated: tuple[str, ...]) -> dict[str, Any]:
    """The sibling report: what this delivery carries, and what it refuses to carry.

    Every column of the specification is accounted for in exactly one way: POPULATED
    (observed on at least one row of this very run), or declared in :data:`NOT_GENERATED`
    with its group and its reason. A column that is neither would be an unexplained empty
    cell -- indistinguishable from a bug -- and the golden test fails on exactly that.

    The file name starts with ``_`` on purpose: ``audit_renderers._export_artifacts`` treats
    that as the sibling report and skips it, so provenance keys can never be read as export
    fields (the package learned that the hard way; see that function's docstring).
    """
    spec = specification()
    populated_set = set(populated)
    empty = tuple(name for name in _COLUMNS if name not in populated_set)
    return {
        "surface": spec.surface,
        "spec": f"specs/{spec.surface}.schema.json",
        "mechanism": (
            "Azure Cost Management export -> Azure Blob Storage "
            "(StorageContainer/StorageDirectory/ExportName/[YYYYMMDD-YYYYMMDD]/[RunID]/); "
            "CSV + Parquet, UTF-8, header in every partition; one folder per run, with the run "
            "document and this report beside the data"
        ),
        "columns": list(_COLUMNS),
        "counts": {
            "spec_columns": len(spec.columns),
            "spec_required": len(spec.required_names),
            "emitted": len(_COLUMNS),
            "populated": len(populated),
            "empty": len(empty),
            "null_empty": len(_NULL_EMPTY),
            "not_generated": len(NOT_GENERATED),
            "not_emittable": len(spec.columns) - len(_COLUMNS),
        },
        "not_generated": {
            name: {"group": group, "reason": reason}
            for name, (group, reason) in NOT_GENERATED.items()
        },
        "model_gaps": {
            name: reason
            for name, (group, reason) in NOT_GENERATED.items()
            if group == GROUP_MODEL_GAP
        },
        "conditional": dict(CONDITIONAL_COLUMNS),
        "populated_columns": list(populated),
        "empty_columns": list(empty),
        # The sibling surface of the SAME delivery (the run document beside the data), held to
        # the same rule: every contracted field is filled or declared, never silently blank.
        "sibling_surface": {
            "surface": manifest_specification().surface,
            "spec": f"specs/{manifest_specification().surface}.schema.json",
            "artifact": "export_run.json",
            "columns": list(_EXPORT_RUN_COLUMNS),
            "counts": {
                "contracted": len(_EXPORT_RUN_COLUMNS),
                "populated": len(_export_run_populated()),
                "declared_empty": len(MANIFEST_NOT_GENERATED),
            },
            "populated_columns": list(_export_run_populated()),
            "not_generated": {
                name: {"group": group, "reason": reason}
                for name, (group, reason) in MANIFEST_NOT_GENERATED.items()
            },
        },
    }


def render_export_run_bytes() -> bytes:
    """Return the export-run document: EXACTLY the manifest surface's 12 contracted fields.

    ``specs/azure/cost-management-export-manifest.schema.json`` covers one delivery: the
    partitioned data files plus the ``_manifest.json`` that accompanies them. Microsoft
    publishes NO schema for that file -- 29 of the spec's 41 columns exist only inside the
    single official example -- so the only fields with a contract are the 12 the REST pages
    document (``ExportRun``/get-execution-history plus ``properties.partitionData``).
    This document is that contract, and it is deliberately NOT a ``_manifest.json``: the
    file fields (``manifestVersion``, ``byteCount``, ``blobs``, ``runInfo``, ...) are all
    ``example-only`` and emitting them would be exactly the fabrication the fidelity core
    denounces. ``AzureFocusRenderer.render`` writes these bytes as ``export_run.json``,
    beside the data files of the same delivery, so the surface's contracted fields are part
    of the delivered artifact set. ``_EXPORT_RUN_COLUMNS`` is derived from the spec, so none
    of the 29 can leak in and a newly contracted field cannot be forgotten.

    The names are the SPEC's own spelling, including the dotted paths
    (``runSettings.format``, ``properties.partitionData``): the fidelity checker compares
    field NAMES, and these are the names the specification declares.

    Values: only ``status`` is filled (see :func:`_export_run_record`). Every other field is
    empty because the canonical estate models no export definition to project from -- no export
    name, container URI, root folder, run id, submitting identity, or chosen source format (this
    renderer deliberately writes BOTH csv and parquet) -- and each one says so, field by field,
    in :data:`MANIFEST_NOT_GENERATED`. Absence is absence; a plausible-looking default would be
    the fabricated fidelity the field rules forbid.
    """
    return (json.dumps(_export_run_record(), indent=2) + "\n").encode("utf-8")


class AzureFocusRenderer:
    """Renders the canonical estate to Azure FOCUS 1.2 CSV + Parquet."""

    name = "focus_azure"

    def render(self, estate: CanonicalEstate, out_dir: Path) -> list[Path]:
        """Write the FOCUS data, the run document and the report under ``out_dir/azure_focus/``.

        Four artifacts in ONE delivery folder -- the path template the manifest spec
        documents puts that document beside the data files:

        * ``focus.csv`` / ``focus.parquet`` -- the FocusCost 1.2-preview line items, built
          from ONE projection pass so the two encodings cannot disagree;
        * ``export_run.json`` -- the run's 12 contracted manifest-surface fields
          (:func:`render_export_run_bytes`), so the surface's own fields are DELIVERED
          rather than only described;
        * ``_provenance.json`` -- the sibling report (:func:`_provenance_document`): the
          emitted columns, the populated/empty split observed on this run, and the declared
          group+reason for every column that is empty in all rows. ``_``-prefixed on
          purpose, so the package's artifact audit reads it as provenance.

        Deliberately no ``_manifest.json``: every field of that file is ``example-only`` in
        the cited specification, so writing one would mean naming 29 fields the
        documentation does not publish. The 12 fields the REST pages DO contract are the
        document above instead.
        """
        target = out_dir / "azure_focus"
        target.mkdir(parents=True, exist_ok=True)
        rows = _rows(estate)
        csv_path = target / "focus.csv"
        parquet_path = target / "focus.parquet"
        export_run_path = target / "export_run.json"
        provenance_path = target / "_provenance.json"
        csv_path.write_bytes(_csv_bytes(rows))
        parquet_path.write_bytes(_parquet_bytes(rows))
        export_run_path.write_bytes(render_export_run_bytes())
        provenance_path.write_text(
            json.dumps(_provenance_document(_populated_columns(rows)), indent=2) + "\n",
            encoding="utf-8",
        )
        return [csv_path, parquet_path, export_run_path, provenance_path]
