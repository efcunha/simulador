"""AWS FOCUS 1.2 + AWS ``x_*`` Data Export renderer (Phase 6, FR-2/FR-3).

Projects ``BillingLine`` rows into the **60-column** schema that
``specs/aws/bcm-data-exports-focus12.schema.json`` documents for the
``FOCUS_1_2_AWS`` table (export ``synthetic-focus12-daily-full``), laid out as an
AWS BCM Data Export:

    {prefix}/{export_name}/data/billing_period=YYYY-MM/<execution>/<name>-00001.snappy.parquet
    {prefix}/{export_name}/_provenance.json

The column set is not a copy of anything: ``_validate_columns`` compares
``_COLUMNS`` against the cited specification at import and fails closed on any
divergence, and the delivery is verified per ARTIFACT -- the emitted file's own
schema is read back with ``fidelity.artifacts.columns_of`` and compared with
``fidelity.checker.check`` -- rather than by trusting this module's list.

NO MANIFEST IS DELIVERED, and that is a deliberate fidelity decision rather than an
omission. AWS documents that a Data Export delivers a ``Manifest.json`` and describes
its contents in prose, but publishes no schema, no key list and no example: the spec's
``manifest`` section is ``partial`` and registers every key except
``additionalOutputFiles`` as unverified. A manifest is a document, so writing one means
naming its fields -- and the names are exactly what the documentation does not
establish. A file whose schema we chose would be indistinguishable, to a consumer, from
an invented field inside a column. The run is therefore recorded in the sibling
``_provenance.json`` (ours by name and by construction, and excluded from the artifact
audit by the package's ``_`` convention), which carries the mechanism, the counts, the
delivered objects and the spec's own ``manifest`` section verbatim. The same refusal is
recorded in ``focus_azure.py`` (no ``_manifest.json``: every field of that file is
``example-only``) and in ``aws_config_snapshot.py`` (no manifest at all).

Verified against ``parser.py (modulo do consumidor)``: emitting ``BilledCost`` +
``BillingPeriodStart`` makes ``_detect_dialect`` select ``focus``. Verified against
``s3_reader.py (modulo do consumidor)``: the reader matches ``billing_period=`` case-
insensitively, recognises ``.parquet`` / ``.snappy.parquet`` / ``.csv`` /
``.csv.gz``, pins **only the newest execution per period**, and ignores objects whose
key carries no period — which is also why nothing but data ever lands under the
export's own prefixes.

Deliberately AWS lines ONLY. ``focus_azure`` records why (``focus_azure.py:110-122``):
rendering every line of the multi-cloud estate leaked foreign scope labels and
foreign cost into an export, and the downstream promoter then stamped its own
provider name over the mixture, hiding it from every screen.

Two version axes, not to be conflated: the internal store target is FOCUS **1.4**
(``focus.py (modulo do consumidor)``); what AWS actually delivers, and what this
renderer emits, is FOCUS **1.2 + AWS x_*** — the shape ``kind='cur_focus_1_2'`` names.

Tags encoding (the same empirically verified trap ``focus_azure.py:137-152`` records):
BOTH csv and parquet emit ``Tags`` as a JSON string of ``[key, value]`` pairs.
``pd.read_parquet`` materialises an arrow list column as a numpy ``ndarray``, so the
parser's native ``isinstance(val, list)`` branch never fires and tags would silently
decode to ``{}``. The JSON-string branch is the only one reachable after ingestion
reads the file, so parquet uses it too. A test asserts the DECODED ``dict[str, str]``,
never the encoding.

Columns emitted EMPTY because no canonical source exists, and inventing one would be
fabricated fidelity rather than data: **NONE**. That list held 16 columns when Phase 7
opened — ``CapacityReservationId, CapacityReservationStatus, ChargeClass,
ChargeDescription, CommitmentDiscountCategory, CommitmentDiscountId,
CommitmentDiscountName, CommitmentDiscountQuantity, CommitmentDiscountStatus,
CommitmentDiscountType, CommitmentDiscountUnit, InvoiceId, ServiceSubcategory,
SkuPriceDetails, SkuPriceId, x_Discounts`` — and slices 1-5 gave every one of them a
source in the model or in the catalog. The last of the sixteen, ``x_Discounts``, is
DERIVED by this renderer from the line's own costs (its own paragraph below). None was
filled by minting a value here.

TWO of the sixteen are empty on every row of a month-to-date base export, and their
emptiness is the WINDOW's rather than a missing source. Neither may be "fixed" by
inventing a value:

* ``ChargeClass`` is ``Correction`` only on a RESTATEMENT row (``BillingLine.is_restatement``).
  A restatement exists in this package only because a scenario appends one
  (``scenarios/emit.py`` gives A06 and C17 their signed ``Adjustment`` delta, which is
  what makes A06 observable at all) and ``daily/engine.py`` deliberately applies no
  scenarios — the daily export is the base estate, so it carries no restatement row and
  the column is empty on every one of them. Such a row DOES populate the column: the
  scenario-applied estate renders a ``Correction`` row whose model line carries
  ``is_restatement=True``, and ``test_charge_class_is_a_projection_of_is_restatement``
  asserts that projection row by row rather than taking this paragraph's word for it.
  Emptying the column outright would erase the only in-export signal that a row is a
  correction.
* ``InvoiceId`` is stamped only once a period is ISSUED: ``estate_builder._stamp_invoice_ids``
  writes it on a line whose ``billing_period_start`` month precedes ``sim_now``'s month.
  A month-to-date window lies entirely INSIDE the current, still-open period, so every
  line carries ``invoice_id = None`` and the column is empty; a window that spans a month
  boundary populates it on the closed period's rows. The id itself is the builder's own
  UUIDv5 of ``(billing account, period)`` — not a number this renderer may manufacture.

``SkuPriceId`` and ``SkuPriceDetails`` are NOT in that list: the estate prices its
SKUs itself, so both columns are pure projections of ``ListPrice``/``ContractedPrice``
rows. ``_Lookups`` keys those rows by ``sku_id`` and ``_sku_price_id`` derives the id
from ``(sku_id, the row's currency, the row's pricing_category)`` through
``determinism.identity_for`` — the UUIDv5 primitive every other identifier in this
package uses, so the id is stable for a seed and is a function of model fields only.
``SkuPriceDetails`` is a JSON **string**: FOCUS 1.2 types the column as a string
containing JSON, so emitting an object would land in the column as garbage — the same
trap the AWS CFN simulator records for ``ExpectedProperties``. Its keys are the price
rows' own fields (unit, unit price, currency, one key per row the estate holds), money
at the same 6 dp as every other money column.

Both columns share ONE precondition (``_record``'s ``priced_sku``): a SKU the estate
prices nowhere emits ``""`` for the id AND the details, because a price identity naming
a price no model row holds would be an id for nothing. Two shapes are flagged
``TODO-verificar`` in the code below, neither being verifiable offline: AWS's real
``SkuPriceId`` is an opaque provider-assigned code (this emits a UUIDv5, which is
visibly not one) and the official ``SkuPriceDetails`` key set (the four keys used are
the model's own price fields, named after the FOCUS columns they mirror).

``ServiceSubcategory`` and ``ChargeDescription`` are NOT in that list: the CATALOG
describes them, per service, in ``generate/constants.py::FOCUS_SERVICE_DESCRIPTIONS``.
This renderer only projects the entry for the row's own ``resource_type``, filling the
catalog's description template with the row's own ``service_name`` and the resource's
``sku_id`` — no string is minted here. The subcategory literals reuse the vocabulary
FinOps own AWS FOCUS normalizer already maps a CUR product family to, so the
export and the ingestion path agree about a service; the ones that map has no literal
for are flagged there as ``TODO-verificar``. A row whose service the table does not
name (the resource-less Marketplace/Support and reservation-fee lines, whose service
names no catalog entry carries) emits ``""`` for both, which is absence, not a gap.

The seven ``CommitmentDiscount*`` columns are NOT in that list: the estate models
both halves of them. ``generate/estate_builder.py`` covers a realistic fraction of
the base estate's eligible usage with the scope's own ``Commitment``
(``commitment_discount_id`` + status on the line), and ``Commitment`` carries the
name/quantity/unit the remaining columns project. ``CommitmentDiscountType`` and
``CommitmentDiscountCategory`` keep the kind -> literal mapping
(``_COMMITMENT_CATEGORY``) keyed by the referenced commitment's ``kind``.

``x_Discounts`` is NOT in that list either: it is a derived DOCUMENT, not a stored
value. AWS ships the column as an ``x_`` extension, so FOCUS does not define it and
nothing in the canonical model is called a discount; what the model does carry is the
difference between the list price and what was charged (``BillingLine.list_cost`` vs
``billed_cost``) and the commitment a covered line names (``commitment_discount_id``).
``_x_discounts`` emits those facts as a JSON **string** — the same trap this module
records twice already for ``Tags`` and ``SkuPriceDetails``, where handing a column an
object lands in it as garbage — with sorted keys, compact separators and money at the
same 6 dp as every other money value here. A line with NO discount emits ``""``, never
``"{}"``: an empty document would claim a discount that is not there. The keys are the
MODEL's own facts (``DiscountAmount`` plus the two costs it was measured between,
``ListCost`` and ``BilledCost``, plus ``CommitmentDiscountId`` when the line names one),
which is what makes the document checkable against the row's own columns instead of a
second source of truth. ``TODO-verificar``: the official ``x_Discounts`` key set is an
AWS extension with no offline-verifiable definition, so the emitted keys are DERIVED
FROM THE MODEL, NOT copied from an official schema — the same row is registered as
``TODO-verificar`` in ``docs/synthetic-clouds/UNVERIFIED.md``.

``CapacityReservationId`` and ``CapacityReservationStatus`` are NOT in that list either:
the estate models a capacity reservation on a deterministic fraction of its ELIGIBLE
compute (``generate/constants.py::CAPACITY_RESERVATION_TYPES`` — the AWS catalog's
``ec2_instance``, since an AWS capacity reservation is an EC2 construct, so the catalog's
other Compute services are not eligible), and EACH reservation carries both values
(``model/capacity.py::CapacityReservation``). This renderer projects them from the
reservation the row's own resource carries: the id string, and the ``Used``/``Unused``
literal the model holds. A row whose resource carries no reservation emits ``""`` for
both — absence is absence, and the empty pair is also the honest answer for the
resource-less billing-only rows (A01/A10, the FR-D5 constructs), which have no resource
to reserve capacity on.

The id is derived (``model/identity.py::capacity_reservation_id``) in the documented
``cr-`` + 17 lowercase hex shape, and that shape is the only part of it that mirrors AWS:
it is a DERIVED id in the documented shape, NOT an official AWS identifier, and it is
flagged ``TODO-verificar`` there. ``CapacityReservationStatus`` reuses the literal pair
the package already emits for ``CommitmentDiscountStatus``
(``constants.CAPACITY_RESERVATION_STATUSES``), FOCUS 1.2's own domain for the column;
the exact per-column definition wording is flagged ``TODO-verificar`` in
``model/capacity.py`` because it is not verifiable offline.

Provider parity: Azure's FOCUS schema DOES carry both columns, and they stay empty
there — the reason is recorded in ``focus_azure.py``'s docstring (an Azure-shaped
reservation id is an ARM resource path this estate does not model anywhere, so
projecting the AWS-shaped id under an Azure column would be worse than an empty one).
GCP's native BigQuery export carries no column of either name, so there is no third
projection to keep in step. ``x_Discounts`` has no counterpart to keep in step either:
it is an AWS-only extension name — Azure's ``x_*`` block is its own list
(``focus_azure.py:137-145``) and carries no ``x_Discounts``, and the GCP BigQuery export
has no such column.

``BillingAccountName``/``SubAccountName`` project the estate's account names
**without** the ``[SYNTH] `` marker (``unmarked_name``): that prefix is FinOps
storage discriminator (``seed/cleanup.py`` matches ``cloud_accounts.name LIKE
'[SYNTH] %'``) and no real AWS export carries it.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
from datetime import UTC, datetime
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from tools.synthetic_clouds.determinism import identity_for
from tools.synthetic_clouds.fidelity.spec import SurfaceSpec, load_spec
from tools.synthetic_clouds.generate.constants import FOCUS_SERVICE_DESCRIPTIONS, PROVIDER_KEY_AWS
from tools.synthetic_clouds.model.billing import BillingLine, ContractedPrice, ListPrice
from tools.synthetic_clouds.model.commitments import Commitment
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.resource import Resource
from tools.synthetic_clouds.render.base import RenderError
from tools.synthetic_clouds.render.markers import unmarked_name

_SIX = Decimal("0.000001")

# The FOCUS ServiceProviderName this renderer emits, and filters on.
_AWS_PROVIDER = "Amazon Web Services"

# The surface this renderer produces, as
# ``specs/aws/bcm-data-exports-focus12.schema.json`` names it.
SURFACE = "aws/bcm-data-exports-focus12"

# The export name and S3 prefix the Data Exports definition declares. Both are the
# CONSUMER's choice (the spec's path template has ``<prefix>``/``<export-name>`` as
# variables), which is why the simulator's own names are honest here.
EXPORT_NAME = "synthetic-focus12-daily-full"
S3_PREFIX = "focus12-full"

# The sibling provenance report (see ``provenance_record``). The leading ``_`` is the
# package's convention for a document that is OURS -- a scaffolding file, never
# presented as a provider artifact -- and it is what keeps this file out of the
# artifact audit while the record it carries stays readable beside the export.
PROVENANCE_FILE = "_provenance.json"

# Parts are chunked so a period's data never lands in one unbounded file. This
# mirrors azure-sim's MAX_ROWS_PER_PART knob.
MAX_ROWS_PER_PART = 100_000

# The 60 columns, in the EMITTED order (the CSV header order). The order is not
# contractual -- AWS defines a Data Export's column order by the export definition's
# own ``SELECT`` -- so the fidelity check compares the SET.
#
# The list is not allowed to drift from the cited specification: ``_validate_columns``
# runs at import and fails closed if this tuple and
# ``specs/aws/bcm-data-exports-focus12.schema.json`` disagree about ANY name, if the
# tuple carries a duplicate, or if the spec ever marks one of these columns
# non-generatable (a name the documentation describes but does not contract). A column
# added to the spec therefore fails loudly here instead of silently shipping 60 of 61.
_COLUMNS: tuple[str, ...] = (
    "AvailabilityZone",
    "BilledCost",
    "BillingAccountId",
    "BillingAccountName",
    "BillingAccountType",
    "BillingCurrency",
    "BillingPeriodEnd",
    "BillingPeriodStart",
    "CapacityReservationId",
    "CapacityReservationStatus",
    "ChargeCategory",
    "ChargeClass",
    "ChargeDescription",
    "ChargeFrequency",
    "ChargePeriodEnd",
    "ChargePeriodStart",
    "CommitmentDiscountCategory",
    "CommitmentDiscountId",
    "CommitmentDiscountName",
    "CommitmentDiscountQuantity",
    "CommitmentDiscountType",
    "CommitmentDiscountStatus",
    "CommitmentDiscountUnit",
    "ConsumedQuantity",
    "ConsumedUnit",
    "ContractedCost",
    "ContractedUnitPrice",
    "EffectiveCost",
    "InvoiceId",
    "InvoiceIssuerName",
    "ListCost",
    "ListUnitPrice",
    "PricingCategory",
    "PricingCurrency",
    "PricingCurrencyContractedUnitPrice",
    "PricingCurrencyEffectiveCost",
    "PricingCurrencyListUnitPrice",
    "PricingQuantity",
    "PricingUnit",
    "ProviderName",
    "PublisherName",
    "RegionId",
    "RegionName",
    "ResourceId",
    "ResourceName",
    "ResourceType",
    "ServiceCategory",
    "ServiceName",
    "ServiceSubcategory",
    "SkuId",
    "SkuPriceDetails",
    "SkuPriceId",
    "SkuMeter",
    "SubAccountId",
    "SubAccountName",
    "SubAccountType",
    "Tags",
    "x_Discounts",
    "x_Operation",
    "x_ServiceCode",
)

# The cited specification this renderer is verified against. It is the SOURCE OF TRUTH
# for the surface: ``specs/README.md`` fixes the contract and
# ``fidelity/spec.py`` is its normative implementation.
SPEC_PATH = Path(__file__).resolve().parents[3] / "specs" / "aws" / "bcm-data-exports-focus12.schema.json"


def specification() -> SurfaceSpec:
    """Load the cited specification for ``aws/bcm-data-exports-focus12``."""
    return load_spec(SPEC_PATH)


def _validate_columns() -> None:
    """Fail closed when ``_COLUMNS`` and the cited specification disagree.

    Three ways to diverge, all fatal at import:

    * a name in one and not the other -- the export would ship a column the
      documentation does not define, or omit one it does;
    * a duplicate in ``_COLUMNS`` -- a column list is a set of names;
    * a documented column that does not BELONG to the schema (``belongs_to_schema``: no
      published type, no URL, an ``evidence`` that is neither ``declared`` nor
      ``null-empty``) -- such a name may never reach an artifact, and dropping it
      silently would be the other infidelity.

    The order is deliberately NOT compared: in an AWS Data Export the order comes from
    the export definition's own ``SELECT``, not from the provider, so only the set is a
    contract (``specs/README.md``, "Ordem das colunas").

    ``null-empty`` columns belong to the file and may never carry a value; that half is
    enforced per record by :func:`_require_columns`, which is where a value could
    actually appear.
    """
    spec = specification()
    documented = spec.names
    emitted = set(_COLUMNS)
    if len(_COLUMNS) != len(emitted):
        duplicated = sorted(name for name in emitted if _COLUMNS.count(name) > 1)
        raise RenderError(f"focus_aws: colunas duplicadas em _COLUMNS: {duplicated}")
    missing = sorted(set(documented) - emitted)
    invented = sorted(emitted - set(documented))
    if missing or invented:
        raise RenderError(
            f"focus_aws: _COLUMNS divergiu de {spec.surface}: "
            f"ausentes na emissao={missing} inventadas={invented}"
        )
    forbidden = sorted(emitted & spec.forbidden_names)
    if forbidden:
        raise RenderError(
            f"focus_aws: colunas sem contrato documental suficiente nao podem ser emitidas: {forbidden}"
        )
    outside_schema = sorted(emitted - spec.emittable_names)
    if outside_schema:
        raise RenderError(
            f"focus_aws: colunas descritas mas fora do formato documentado: {outside_schema}"
        )


_validate_columns()

# Columns that belong to the file and may never receive a value (``evidence:
# null-empty``). Empty for this surface: all 60 FOCUS 1.2 + AWS columns are generatable.
# Read from the spec rather than hard-coded, so a future ``null-empty`` column is emitted
# empty instead of being filled by accident.
_NULL_EMPTY: frozenset[str] = specification().null_empty_names

# FOCUS 1.2 ChargeFrequencyLiteral: One-Time | Recurring | Usage-Based. Derived from
# the charge category, which is the only signal the canonical model carries.
_CHARGE_FREQUENCY: dict[str, str] = {
    "Usage": "Usage-Based",
    "Purchase": "Recurring",
    "Tax": "Recurring",
    "Credit": "One-Time",
    "Adjustment": "One-Time",
}

# FOCUS 1.2 CommitmentDiscountCategoryLiteral for AWS: "Spend" for Savings Plans,
# "Usage" for reservations. Keyed by the canonical Commitment.kind.
_COMMITMENT_CATEGORY: dict[str, str] = {
    "savings_plan": "Spend",
    "reservation": "Usage",
    "cud": "Usage",
}

# AWS service code and operation per resource type. Best-effort and registered as
# TODO-verificar: the column set is authoritative, these VALUES are illustrative.
#
# The key set covers every resource type the AWS catalog models
# (``generate/constants.py::AWS_SERVICES``) — a type with no entry would emit an
# EMPTY ``x_ServiceCode``/``x_Operation`` even though the estate does model the
# service, which is the "absence" a later reader cannot tell apart from a gap in the
# simulator. ``vpc`` and ``security_group`` are in the map even though the catalog
# prices them at zero (so they have no billing line and never emit a value): the map
# describes the catalog, and inventing a *missing* entry to match the row count would
# be the same mistake in the other direction.
_SERVICE_CODE: dict[str, str] = {
    "ec2_instance": "AmazonEC2",
    "ebs_volume": "AmazonEC2",
    "nat_gateway": "AmazonVPC",
    "data_transfer": "AmazonVPC",
    "rds_instance": "AmazonRDS",
    "s3_bucket": "AmazonS3",
    "eks_cluster": "AmazonEKS",
    "cloudwatch_logs": "AmazonCloudWatch",
    "lambda_function": "AWSLambda",
    "elastic_ip": "AmazonEC2",
    "application_lb": "AWSELB",
    "vpc": "AmazonVPC",
    "security_group": "AmazonVPC",
    "dynamodb_table": "AmazonDynamoDB",
    "ecs_cluster": "AmazonECS",
}
_OPERATION: dict[str, str] = {
    "ec2_instance": "RunInstances",
    "ebs_volume": "CreateVolume",
    "nat_gateway": "CreateNatGateway",
    "data_transfer": "DataTransfer-Regional-Bytes",
    "rds_instance": "CreateDBInstance",
    "s3_bucket": "PutObject",
    "eks_cluster": "CreateCluster",
    "cloudwatch_logs": "PutLogEvents",
    "lambda_function": "Invoke",
    "elastic_ip": "AllocateAddress",
    "application_lb": "CreateLoadBalancer",
    "vpc": "CreateVpc",
    "security_group": "CreateSecurityGroup",
    "dynamodb_table": "CreateTable",
    "ecs_cluster": "CreateCluster",
}

# The FOCUS ServiceSubcategory and ChargeDescription of every catalogued AWS resource
# type, read from the CATALOG (``generate/constants.py::FOCUS_SERVICE_DESCRIPTIONS``) --
# never a string minted in this module. The renderer resolves the row's own
# ``resource_type`` in the table and fills the template with the row's own
# ``service_name``/``sku_id``, so both columns are projections of data that exists
# elsewhere; an unknown service yields an empty column (see ``_descriptor``). The
# tests assert every value against the table itself, so a literal cannot drift in here
# unnoticed.
_DESCRIPTIONS = FOCUS_SERVICE_DESCRIPTIONS[PROVIDER_KEY_AWS]


def _q(value: Decimal) -> Decimal:
    return value.quantize(_SIX, ROUND_HALF_EVEN)


def _money(value: Decimal) -> str:
    return str(_q(value))


def _unit_price(total: Decimal, quantity: Decimal) -> str:
    """Return ``total / quantity`` at 6dp, or ``""`` when quantity is zero."""
    if quantity == 0:
        return ""
    return str(_q(total / quantity))


def _sku_price_id(seed: int, sku_id: str, currency: str, tier: str) -> str:
    """Return the price identity of ``(sku_id, currency, pricing tier)`` for ``seed``.

    FOCUS 1.2 types ``SkuPriceId`` as an opaque, **provider-assigned** string
    identifying which price of a SKU a line is billed at, which is why the id is
    derived from exactly the three model fields that select a price: the resource's
    ``sku_id``, the line's ``currency``, and the line's ``pricing_category`` (the
    ``Standard`` / ``Committed`` tier, which C16 moves mid-period). Two lines billed at
    two tiers of one SKU therefore carry two ids, which is what makes the column read
    as a price identity rather than a second ``SkuId``.

    The value is a UUIDv5 over a logical path — ``determinism.identity_for``, the same
    primitive every identity in this package comes from — so it is byte-stable for a
    seed and carries no ordering dependence.

    ``TODO-verificar``: AWS's real ``SkuPriceId`` is an opaque provider-assigned code
    (16-ish alphanumerics), NOT a UUID. That format is not verifiable offline, and
    minting a lookalike would be fabricating a provider code, so this emits the UUID
    the package can actually back: visibly not an AWS code, honest about being assigned
    by the simulator.
    """
    return identity_for(seed, f"sku-price/{sku_id}/{currency}/{tier}")


def _sku_price_details(
    list_price: ListPrice | None, contracted_price: ContractedPrice | None
) -> str:
    """Return ``SkuPriceDetails`` as a JSON **string** built from the estate's prices.

    FOCUS 1.2 defines this column as a string CONTAINING JSON, so the object is
    serialized (``json.dumps``, sorted keys, compact separators) and never handed to the
    column as a dict — the encoding trap the AWS CFN simulator records for
    ``ExpectedProperties``.

    Every key is a field of a ``ListPrice``/``ContractedPrice`` row the estate holds,
    and only rows that exist contribute keys: a SKU whose estate carries only a list
    price emits three keys, not a defaulted contracted one. Money keeps the 6-dp format
    the rest of this renderer uses. A SKU with no price row at all returns ``""`` —
    absence, never ``"{}"`` (an empty document would claim a price identity with no
    facts behind it).

    ``TODO-verificar``: the official FOCUS 1.2 ``SkuPriceDetails`` key set is not
    verifiable offline. The four keys below are the model's own price fields, named
    after the FOCUS columns they mirror (``ListUnitPrice`` / ``ContractedUnitPrice`` /
    ``PricingUnit`` / ``PricingCurrency``), which keeps every value traceable to a model
    field instead of to a plausible-looking name.
    """
    details: dict[str, str] = {}
    if contracted_price is not None:
        details["ContractedUnitPrice"] = _money(contracted_price.unit_price)
    if list_price is not None:
        details["ListUnitPrice"] = _money(list_price.unit_price)
    # Unit and currency describe the SKU's price in either tier; the contracted row is
    # the one the estate writes its negotiated terms on, so it wins when both exist.
    price_row = contracted_price if contracted_price is not None else list_price
    if price_row is not None:
        details["PricingCurrency"] = price_row.currency
        details["PricingUnit"] = price_row.unit
    return json.dumps(details, sort_keys=True, separators=(",", ":"))


def _x_discounts(line: BillingLine) -> str:
    """Return ``x_Discounts`` as a JSON **string** DERIVED from the line's own costs.

    Nothing in the canonical model is called a discount, so the document is not a copy
    of a stored value: it is the two facts the line already carries, projected.

    * the reduction the customer received, ``list_cost - billed_cost``, emitted with the
      two costs it was measured between (``ListCost`` and ``BilledCost``) so the amount
      can be checked against the row's own columns rather than trusted; and
    * the commitment the line names (``commitment_discount_id``), which is the other way
      a line can be discounted — a covered row whose list and charged amounts happen to
      coincide still documents the instrument that covers it.

    A line that carries neither emits ``""`` — absence, never ``"{}"`` and never a
    zero-valued document: an empty document would claim a discount that is not there.
    Only the facts that exist contribute keys, the same rule :func:`_sku_price_details`
    follows.

    FOCUS types a ``Details`` extension as a string CONTAINING JSON, so the object is
    serialized and never handed to the column as a dict — the trap this module records
    twice already, for ``Tags`` and for ``SkuPriceDetails``. Money keeps the renderer's
    6-dp format.

    ``TODO-verificar``: ``x_Discounts`` is an AWS extension and its official key set is
    not verifiable offline. The keys below are DERIVED FROM THE MODEL — named after the
    model facts they carry — and are NOT copied from an official schema; the row is
    registered as ``TODO-verificar`` in ``docs/synthetic-clouds/UNVERIFIED.md``.
    """
    charged = line.billed_cost
    reduction = _q(line.list_cost - charged)
    document: dict[str, str] = {}
    if reduction > 0:
        document["BilledCost"] = _money(charged)
        document["DiscountAmount"] = _money(reduction)
        document["ListCost"] = _money(line.list_cost)
    if line.commitment_discount_id:
        document["CommitmentDiscountId"] = line.commitment_discount_id
    if not document:
        return ""
    return json.dumps(document, sort_keys=True, separators=(",", ":"))


def _descriptor(resource_type: str) -> tuple[str, str]:
    """Return the catalog's ``(ServiceSubcategory, ChargeDescription template)``.

    An unknown ``resource_type`` returns two empty strings, and that is what the
    columns emit: a service no data table describes is absence, not a gap a default
    may fill. The empty ``resource_type`` of a resource-less line (the billing-only
    FR-D5 / A01 / A10 constructs, and the scenario emitters' own service names) lands
    on the same branch, so those rows stay honest rather than half-described.
    """
    return _DESCRIPTIONS.get(resource_type, ("", ""))


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _availability_zone(region_id: str) -> str:
    """Derive an AZ from the region; ``global`` scopes (the FR-D5 tax line) have none."""
    if not region_id or region_id == "global":
        return ""
    return f"{region_id}a"


def _aws_lines(estate: CanonicalEstate) -> list[BillingLine]:
    """This renderer's own rows, in deterministic order (see the module docstring)."""
    return sorted(
        (line for line in estate.billing_lines if line.service_provider_name == _AWS_PROVIDER),
        key=lambda line: line.line_id,
    )


class _Lookups:
    """Estate-wide lookups a single billing line cannot resolve by itself."""

    def __init__(self, estate: CanonicalEstate) -> None:
        self.seed = estate.seed
        self.resource_by_uuid: dict[str, Resource] = {r.identity.uuid: r for r in estate.resources}
        # The estate's price book, keyed by ``sku_id``: ``ListPrice``/``ContractedPrice``
        # are built one row per SKU (``estate_builder._build_prices`` de-duplicates by
        # ``sku_id``), so these are lookups and not lists — a second row for one SKU would
        # be an ambiguous price, not a richer one.
        self.list_price_by_sku: dict[str, ListPrice] = {p.sku_id: p for p in estate.list_prices}
        self.contracted_price_by_sku: dict[str, ContractedPrice] = {
            p.sku_id: p for p in estate.contracted_prices
        }
        self.billing_account_name: dict[str, str] = {
            b.billing_account_id: b.name for b in estate.billing_accounts
        }
        self.sub_account_name: dict[str, str] = {
            a.account_id: a.name for org in estate.aws_orgs for a in org.accounts
        }
        self.commitment_by_id: dict[str, Commitment] = {
            commitment.identity.uuid: commitment for commitment in estate.commitments
        }
        self.commitment_kind_by_scope: dict[str, str] = {}
        for commitment in estate.commitments:
            self.commitment_kind_by_scope.setdefault(commitment.scope_id, commitment.kind)


def _record(line: BillingLine, lookups: _Lookups) -> dict[str, Any]:
    """Return the 60-column record for ``line``; ``Tags`` is the caller's to set."""
    resource = lookups.resource_by_uuid.get(line.resource_uuid) if line.resource_uuid else None
    resource_type = resource.resource_type if resource is not None else ""
    sku_id = resource.sku_id if resource is not None else ""

    # The two capacity-reservation columns are a projection of the reservation the
    # line's own resource carries (``Resource.capacity_reservation``, modelled by
    # ``estate_builder._capacity_reservation``). A resource with none — every
    # non-eligible type, the ~70% of eligible compute that lost the coverage draw, and
    # the resource-less billing-only rows — emits ``""`` for both: no reservation means
    # no id and no status, never a placeholder for the pair.
    reservation = resource.capacity_reservation if resource is not None else None

    # The two SKU-price columns are projections of the price book, not of the line's own
    # costs: the estate's ``ListPrice``/``ContractedPrice`` rows ARE the prices, so the
    # values come from them rather than from a unit price re-derived from this row's
    # totals. A row whose SKU the estate prices nowhere (the resource-less billing-only
    # constructs; the zero-priced catalog SKUs, which never bill) leaves both columns
    # empty — see ``_sku_price_details``.
    list_price = lookups.list_price_by_sku.get(sku_id)
    contracted_price = lookups.contracted_price_by_sku.get(sku_id)
    priced_sku = bool(sku_id) and (list_price is not None or contracted_price is not None)

    subcategory, description_template = _descriptor(resource_type)
    # The description is the CATALOG template for this resource type, filled with the
    # row's OWN values: the line's service_name and the resource's sku_id. Requiring the
    # sku keeps a half-filled string ("... usage ()") out of an export column — a
    # resource the catalog describes always carries the sku its price is keyed by, so
    # the column empties only for a row with no catalogued service at all.
    charge_description = (
        description_template.format(service_name=line.service_name, sku_id=sku_id)
        if description_template and sku_id
        else ""
    )

    has_commitment = line.commitment_discount_id is not None
    # The id names a commitment in the estate, and that commitment is the source of
    # every other CommitmentDiscount column — name, quantity, unit and type all come
    # from the ONE row the id points at, so the seven columns cannot disagree with each
    # other. The scope-keyed kind stays as the fallback for an id the estate's
    # commitments do not name (the scenario emitters build such ids — C05's Azure
    # reservation), so those rows keep the type/category they carried before rather than
    # losing it.
    commitment = lookups.commitment_by_id.get(line.commitment_discount_id or "")
    commitment_kind = (
        commitment.kind
        if commitment is not None
        else lookups.commitment_kind_by_scope.get(line.sub_account_id, "")
    )

    return {
        "AvailabilityZone": _availability_zone(line.region_id),
        "BilledCost": _money(line.billed_cost),
        "BillingAccountId": line.billing_account_id,
        # The estate's account names carry the FinOps ``[SYNTH] `` marker; an
        # export column does not (see ``unmarked_name``).
        "BillingAccountName": unmarked_name(lookups.billing_account_name.get(line.billing_account_id, "")),
        # The estate models one AWS payer billing account, so its type is Payer.
        "BillingAccountType": "Payer",
        "BillingCurrency": line.currency,
        "BillingPeriodEnd": line.billing_period_end.isoformat(),
        "BillingPeriodStart": line.billing_period_start.isoformat(),
        # ``CapacityReservationId`` is the reservation's own provider-shaped id
        # (``cr-`` + 17 hex, see ``identity.capacity_reservation_id``) and
        # ``CapacityReservationStatus`` its ``Used``/``Unused`` literal, both read off
        # the modelled reservation rather than chosen here.
        "CapacityReservationId": "" if reservation is None else reservation.reservation_id,
        "CapacityReservationStatus": "" if reservation is None else reservation.status,
        "ChargeCategory": line.charge_category,
        "ChargeClass": "Correction" if line.is_restatement else "",
        "ChargeDescription": charge_description,
        "ChargeFrequency": _CHARGE_FREQUENCY.get(line.charge_category, ""),
        "ChargePeriodEnd": _iso(line.charge_period_end),
        "ChargePeriodStart": _iso(line.charge_period_start),
        "CommitmentDiscountCategory": _COMMITMENT_CATEGORY.get(commitment_kind, "") if has_commitment else "",
        "CommitmentDiscountId": line.commitment_discount_id or "",
        # Projected from the referenced Commitment, so the three columns describe the
        # commitment the id names rather than a plausible-looking string invented here.
        # ``name`` carries the FinOps marker on the estate and is unmarked on the
        # way out, like every other name in an export column (see the docstring).
        # ``Quantity`` is the commitment's own metered amount: the model carries ONE
        # quantity per commitment, so an ``Unused`` row reports the commitment's
        # quantity rather than an unused remainder — the remainder is not modelled
        # anywhere, and computing one here would be inventing it.
        "CommitmentDiscountName": "" if commitment is None else unmarked_name(commitment.name),
        "CommitmentDiscountQuantity": "" if commitment is None else _money(commitment.quantity),
        "CommitmentDiscountType": commitment_kind if has_commitment else "",
        "CommitmentDiscountStatus": line.commitment_discount_status or "",
        "CommitmentDiscountUnit": "" if commitment is None else commitment.unit,
        "ConsumedQuantity": _money(line.pricing_quantity),
        "ConsumedUnit": line.pricing_unit,
        "ContractedCost": _money(line.contracted_cost),
        "ContractedUnitPrice": _unit_price(line.contracted_cost, line.pricing_quantity),
        "EffectiveCost": _money(line.effective_cost),
        "InvoiceId": line.invoice_id or "",
        "InvoiceIssuerName": _AWS_PROVIDER,
        "ListCost": _money(line.list_cost),
        "ListUnitPrice": _unit_price(line.list_cost, line.pricing_quantity),
        "PricingCategory": line.pricing_category,
        "PricingCurrency": line.currency,
        # The estate carries ONE currency, so the pricing-currency measures mirror
        # the billing-currency ones rather than being converted.
        "PricingCurrencyContractedUnitPrice": _unit_price(line.contracted_cost, line.pricing_quantity),
        "PricingCurrencyEffectiveCost": _money(line.effective_cost),
        "PricingCurrencyListUnitPrice": _unit_price(line.list_cost, line.pricing_quantity),
        "PricingQuantity": _money(line.pricing_quantity),
        "PricingUnit": line.pricing_unit,
        "ProviderName": "AWS",
        "PublisherName": _AWS_PROVIDER,
        "RegionId": line.region_id,
        "RegionName": line.region_name,
        # FR-D5 null-resource line -> empty ResourceId (ingestion owns the sentinel).
        "ResourceId": "" if line.resource_uuid is None else line.resource_uuid,
        "ResourceName": resource.resource_name if resource is not None else "",
        "ResourceType": resource_type,
        "ServiceCategory": line.service_category,
        "ServiceName": line.service_name,
        "ServiceSubcategory": subcategory,
        "SkuId": sku_id,
        "SkuPriceDetails": _sku_price_details(list_price, contracted_price) if priced_sku else "",
        "SkuPriceId": (
            _sku_price_id(lookups.seed, sku_id, line.currency, line.pricing_category) if priced_sku else ""
        ),
        "SkuMeter": line.pricing_unit,
        "SubAccountId": line.sub_account_id,
        "SubAccountName": unmarked_name(lookups.sub_account_name.get(line.sub_account_id, "")),
        "SubAccountType": "Account",
        # The AWS ``x_Discounts`` extension, derived from this line's own costs and the
        # commitment it names — see ``_x_discounts``. The daily base export is priced with
        # a negotiated contracted rate below list for every billable SKU, so a base row
        # carries a document; a row whose charge equals its list price and which names no
        # commitment (the Tax/Purchase billing-only rows) emits ``""``.
        "x_Discounts": _x_discounts(line),
        "x_Operation": _OPERATION.get(resource_type, ""),
        "x_ServiceCode": _SERVICE_CODE.get(resource_type, ""),
    }


def _tag_json(line: BillingLine) -> str:
    """``Tags`` in the ONE encoding both csv and parquet use (see the docstring)."""
    return json.dumps([[k, v] for k, v in line.tags], sort_keys=False)


def _require_columns(record: dict[str, Any]) -> None:
    """Fail closed when a record is not exactly the emitted column set, or fills a refusal.

    ``_record`` returns ONE literal dict, so checking a single record checks every
    record. Two failures are caught here:

    * a divergent field set. The two writers disagree about that: a MISSING key raises
      ``KeyError`` in both, but an EXTRA key raises in the CSV writer
      (``extrasaction="raise"``) and is silently DROPPED by ``_parquet_bytes`` -- the
      silent omission this guard exists to prevent; and
    * a value in a column the spec marks ``null-empty`` -- a column that belongs to the
      file and may never be filled. Omit it and the format is broken; fill it and the
      contract is. Emitting it empty is the only faithful answer.
    """
    fields = set(record)
    expected = set(_COLUMNS)
    if fields != expected:
        raise RenderError(
            "focus_aws: registro com campos diferentes das colunas emitidas: "
            f"sobram={sorted(fields - expected)} faltam={sorted(expected - fields)}"
        )
    filled = sorted(name for name in _NULL_EMPTY & fields if record[name])
    if filled:
        raise RenderError(f"focus_aws: colunas null-empty receberam valor: {filled}")


def _rows(estate: CanonicalEstate, lines: list[BillingLine]) -> list[dict[str, Any]]:
    lookups = _Lookups(estate)
    rows: list[dict[str, Any]] = []
    checked = False
    for line in lines:
        record = _record(line, lookups)
        record["Tags"] = _tag_json(line)
        if not checked:
            _require_columns(record)
            checked = True
        rows.append(record)
    return rows


def render_csv_bytes(estate: CanonicalEstate) -> bytes:
    """Return the FOCUS CSV bytes for every AWS line (Tags = JSON string)."""
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(_COLUMNS), extrasaction="raise", lineterminator="\n")
    writer.writeheader()
    for record in _rows(estate, _aws_lines(estate)):
        writer.writerow(record)
    return buffer.getvalue().encode("utf-8")


def render_csv_gz_bytes(estate: CanonicalEstate) -> bytes:
    """Return the gzip of :func:`render_csv_bytes` (the ``.csv.gz`` contract)."""
    return gzip.compress(render_csv_bytes(estate), mtime=0)


def render_parquet_bytes(estate: CanonicalEstate) -> bytes:
    """Return the FOCUS Parquet bytes for every AWS line (Tags = JSON string).

    All 60 columns are typed ``string``. That is deliberate and matches
    ``focus_azure``: every column this renderer emits is a formatted string, money
    is already 6-dp text, and a typed column would only add a second place for the
    precision contract to drift. ``Tags`` is a string for the reason the module
    docstring records.
    """
    return _parquet_bytes(_rows(estate, _aws_lines(estate)))


def _parquet_bytes(rows: list[dict[str, Any]]) -> bytes:
    """Encode ``rows`` (already 60-column records) as one snappy Parquet file."""
    columns: dict[str, list[str]] = {col: [row[col] for row in rows] for col in _COLUMNS}
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


# ── S3 layout (BCM Data Export) ───────────────────────────────────────────────


def s3_key(
    *,
    billing_period: str,
    execution: str,
    filename: str,
    kind: str = "data",
    partition_key: str = "billing_period",
    prefix: str = S3_PREFIX,
    export_name: str = EXPORT_NAME,
) -> str:
    """Return the S3 key for one exported object.

    ``kind`` is ``"data"`` or ``"metadata"``. The partition key defaults to the
    lowercase ``billing_period`` that AWS actually delivers — ``s3_reader`` matches
    it case-insensitively while the public docs show uppercase. The parameter exists
    so the contract test can build the uppercase fixture too.

    Only the ``data`` prefix is POPULATED: the ``metadata`` prefix is part of the
    documented layout, and the manifest that would live under it is deliberately not
    written (see the module docstring and :func:`provenance_record`). The parameter
    stays because the layout it names is the documented contract, and a test asserts
    that whatever this renderer writes stays out of it.
    """
    return f"{prefix}/{export_name}/{kind}/{partition_key}={billing_period}/{execution}/{filename}"


def _execution_id(estate: CanonicalEstate, billing_period: str, export_time: datetime) -> str:
    """Return the deterministic execution directory name for a period.

    Real AWS uses a delivery timestamp plus a unique suffix; both halves are derived
    here so a given ``(seed, period)`` always yields the same directory. The reader
    pins the newest execution by ``LastModified`` first and by directory path second,
    so a stable, sortable name keeps that tie-break meaningful (scenario A04).
    """
    stamp = export_time.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    digest = hashlib.sha256(f"{estate.seed}:{billing_period}".encode()).hexdigest()[:8]
    return f"{stamp}-{digest}"


def _periods(lines: list[BillingLine]) -> dict[str, list[BillingLine]]:
    """Group lines by ``YYYY-MM`` billing period, each group deterministically ordered."""
    grouped: dict[str, list[BillingLine]] = {}
    for line in lines:
        key = f"{line.billing_period_start.year:04d}-{line.billing_period_start.month:02d}"
        grouped.setdefault(key, []).append(line)
    return {key: sorted(grouped[key], key=lambda line: line.line_id) for key in sorted(grouped)}


def schema_fingerprint() -> str:
    """Return a stable digest of the emitted column set (sorted, so order is not a factor).

    Deliberately NOT ``synth:``-prefixed: that prefix marks synthetic DATA
    (``render/markers.py:15``). This is a real hash of a real schema, and conflating
    the two would break the provenance marker's meaning.
    """
    return hashlib.sha256("\n".join(sorted(_COLUMNS)).encode()).hexdigest()


def manifest_section() -> dict[str, Any]:
    """Return the spec's OWN ``manifest`` section, verbatim.

    Read from the cited specification rather than paraphrased, so the record below can
    never drift from the evidence: the section states the manifest's ``status``
    (``partial``), its ``file_name``, the ONE key the documentation confirms
    (``additionalOutputFiles``), the contents AWS describes in prose, and -- in its own
    ``notes`` -- that "AWS documents the manifest by prose description only. No JSON
    schema, key list or example is published; every key except additionalOutputFiles is
    UNVERIFIED."
    """
    raw = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    section = raw.get("manifest")
    return dict(section) if isinstance(section, dict) else {}


def provenance_record(*, estate: CanonicalEstate, objects: list[dict[str, Any]]) -> dict[str, Any]:
    """Return the export run's provenance record -- the manifest's place, and why.

    AWS documents that a Data Export delivers a manifest beside the data, and describes
    that manifest's CONTENTS in prose: the columns included, the list of data files and
    their paths, the covered period, and a section called ``additionalOutputFiles``. It
    publishes NO JSON schema, NO key list and NO example -- the spec's own ``manifest``
    section is ``partial`` and registers every key except ``additionalOutputFiles`` as
    unverified.

    A manifest is a DOCUMENT: writing one means NAMING its fields, and those names are
    exactly what the documentation does not establish. A file whose schema we chose is
    indistinguishable, to a consumer, from an invented field inside a column -- which is
    why this renderer delivers the DATA only and records the run here, in the sibling
    ``_provenance.json``: a document that is OURS by name (the leading ``_``) and by
    construction, never presented as an AWS artifact.

    The same decision, for the same reason, is already recorded in ``focus_azure.py``
    (which writes no ``_manifest.json``: every field of that file is ``example-only`` in
    the Microsoft spec) and in ``aws_config_snapshot.py`` (which writes no manifest at
    all). Nothing is lost to the ingestion path: ``s3_reader`` lists and gets objects and
    never reads a manifest.

    What the record carries is everything the documentation establishes plus the facts of
    THIS run: the mechanism (prefixes, partition key, format, compression), the column
    counts, the objects delivered with their sizes and row counts, and the spec's own
    ``manifest`` section verbatim -- including ``additionalOutputFiles``, the one key the
    spec confirms, which stays visible here as the documentation's fact rather than as a
    field of a document AWS never described.
    """
    return {
        "kind": "provenance",
        "surface": SURFACE,
        "spec": f"specs/aws/{SPEC_PATH.name}",
        "seed": estate.seed,
        "profile": estate.profile,
        "currency": estate.currency,
        "mechanism": {
            "kind": "s3",
            "export_name": EXPORT_NAME,
            "prefix": S3_PREFIX,
            "data_prefix": "data/",
            "metadata_prefix": "metadata/",
            "partition_key": "billing_period",
            "format": "parquet",
            "compression": "snappy",
            "manifest_delivered": False,
            "manifest_note": (
                "AWS publishes no manifest schema, key list or example; every key except "
                "additionalOutputFiles is unverified, and a document whose field names we "
                "chose is the same fabrication as an invented column. The run is recorded "
                "here instead."
            ),
        },
        "columns": {
            "documented": len(specification().columns),
            "emitted": len(_COLUMNS),
            "null_empty": len(_NULL_EMPTY),
            "schema_fingerprint": schema_fingerprint(),
        },
        "totals": {
            "objects": len(objects),
            "records": sum(int(entry["recordCount"]) for entry in objects),
            "bytes": sum(int(entry["bytes"]) for entry in objects),
        },
        "objects": objects,
        "manifest": manifest_section(),
        "todo_verificar": [
            "manifest key names other than additionalOutputFiles (prose-only documentation)",
            "manifest file name (<export-name>-Manifest.json vs Manifest.json)",
            "ETag algorithm",
        ],
    }


def _write_provenance(*, target: Path, estate: CanonicalEstate, objects: list[dict[str, Any]]) -> Path:
    """Write the sibling ``_provenance.json`` beside the export tree."""
    path = target / PROVENANCE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(provenance_record(estate=estate, objects=objects), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _views(lines: list[BillingLine]) -> list[list[BillingLine]]:
    """Split a period's rows into the deliveries AWS would have made, oldest first.

    A restatement corrects an earlier usage_date, so it arrives in a LATER delivery of
    the period it belongs to. The period therefore has (at least) two deliveries: the
    one before the correction arrived, which does not contain it, and the current one,
    which does. Emitting both is what makes the reader's execution pinning observable
    (scenario A04) and what makes a restatement read as a replacement rather than a sum
    (A06).

    The prior view is bounded by the correction's own ``export_time`` — NOT by the
    period's last daily export. The two are different orders: daily rows carry
    ``D+1`` export times, so a period's last regular export is typically LATER than a
    restatement that arrived mid-period. Stamping the prior view from the period's max
    would give both views the same execution id, and the second write would silently
    overwrite the first. Bounding it by ``< correction_time`` keeps the prior delivery
    strictly earlier, which is also what makes the view a strict subset.

    A period with no restatement is delivered once.
    """
    restated = [line for line in lines if line.is_restatement]
    if not restated:
        return [lines]
    correction_time = min(line.export_time for line in restated)
    prior = [line for line in lines if not line.is_restatement and line.export_time < correction_time]
    if not prior:
        return [lines]
    return [prior, lines]


def _write_execution(
    *,
    target: Path,
    estate: CanonicalEstate,
    billing_period: str,
    view: list[BillingLine],
    written: list[Path],
    objects: list[dict[str, Any]],
) -> None:
    """Write one execution's DATA parts (see :func:`provenance_record` for the manifest).

    The execution directory is written exactly as the delivery documents it; the
    manifest that AWS also delivers is NOT written, and that refusal is recorded in the
    sibling provenance report instead of in a document whose field names we would have
    had to invent.
    """
    if not view:
        return
    export_time = max(line.export_time for line in view)
    execution = _execution_id(estate, billing_period, export_time)
    rows = _rows(estate, view)

    for start in range(0, len(rows), MAX_ROWS_PER_PART):
        chunk = rows[start : start + MAX_ROWS_PER_PART]
        index = start // MAX_ROWS_PER_PART + 1
        filename = f"{EXPORT_NAME}-{index:05d}.snappy.parquet"
        payload = _parquet_bytes(chunk)
        key = s3_key(billing_period=billing_period, execution=execution, filename=filename)
        path = target / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        written.append(path)
        objects.append(
            {
                "key": key,
                "billing_period": billing_period,
                "execution": execution,
                "bytes": len(payload),
                "recordCount": len(chunk),
                "md5": hashlib.md5(payload, usedforsecurity=False).hexdigest(),  # noqa: S324
            }
        )


class AwsFocusRenderer:
    """Renders the canonical estate to an AWS FOCUS 1.2 BCM Data Export tree."""

    name = "focus_aws"

    def render(self, estate: CanonicalEstate, out_dir: Path) -> list[Path]:
        """Write the export tree under ``out_dir/aws_focus/``; return written paths.

        The tree is the delivered DATA plus the sibling ``_provenance.json``: the
        manifest AWS also delivers is deliberately absent, for the reason
        :func:`provenance_record` records.
        """
        target = out_dir / "aws_focus"
        written: list[Path] = []
        objects: list[dict[str, Any]] = []
        for billing_period, lines in _periods(_aws_lines(estate)).items():
            for view in _views(lines):
                _write_execution(
                    target=target,
                    estate=estate,
                    billing_period=billing_period,
                    view=view,
                    written=written,
                    objects=objects,
                )
        written.append(_write_provenance(target=target, estate=estate, objects=objects))
        return written
