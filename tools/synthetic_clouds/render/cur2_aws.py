"""AWS CUR 2.0 (``COST_AND_USAGE_REPORT``) Data Export renderer.

Projects ``BillingLine`` rows into the **131 columns** that
``specs/aws/bcm-data-exports-cur2.schema.json`` documents for the
``COST_AND_USAGE_REPORT`` table, laid out as an AWS BCM Data Export in **create-new**
delivery mode (``CREATE_NEW_REPORT``), which is the mode whose layout the spec fixes:

    {prefix}/{export_name}/data/BILLING_PERIOD=YYYY-MM/<execution>/<name>-00001.snappy.parquet
    {prefix}/{export_name}/_provenance.json

The partition key is the UPPERCASE ``BILLING_PERIOD=YYYY-MM`` the spec documents for
this surface (``delivery.partition_key``), unlike FOCUS 1.2, for which AWS never states
a partition and ``focus_aws`` therefore emits the lowercase form its reader matches.
The prefix, export name and file names are the CONSUMER's own choice -- the spec's path
template has ``<prefix>``/``<export-name>`` as variables -- so this module names an
export that does not exist in AWS, exactly like ``focus_aws`` does.

NO MANIFEST IS DELIVERED, the same deliberate decision ``focus_aws`` records rather than
an omission. The spec documents that a create-new delivery writes a manifest under
``metadata/BILLING_PERIOD=YYYY-MM/[<timestamp>-<execution-id>/]<export-name>-Manifest.json``
and describes its CONTENTS in prose (all the columns included, the list of data files
and their paths, the period covered, and a section called ``additionalOutputFiles``) --
and it records in its own unverified list that AWS publishes no JSON schema, no key list
and no example, so every key except ``additionalOutputFiles`` would be a name we chose.
A manifest is a DOCUMENT: writing one means naming its fields, and a file whose schema we
chose is indistinguishable, to a consumer, from an invented field inside a column. The
run is therefore recorded in the sibling ``_provenance.json`` (ours by name and by
construction, excluded from the artifact audit by the package's ``_`` convention), which
carries the mechanism, the counts, the delivered objects and the spec's own ``manifest``
section verbatim -- including the file-name divergence the spec records
(``<export-name>-Manifest.json`` in the "Metadata" section versus ``Manifest.json`` in
"Summary"/"create new"/"overwrite"), so nothing is chosen in silence.

THE COLUMN SET IS DERIVED, NOT RETYPED
--------------------------------------
``_COLUMNS`` IS the specification's column list, in the specification's order, filtered
to the columns that BELONG to the schema (``belongs_to_schema``: a name, a documented
type, a verified status, the official URL, and an ``evidence`` of ``declared`` or
``null-empty``). Nothing here is a second copy that could drift: if the spec gains or
loses a column, this renderer emits the new set.

Belonging to the schema and being able to receive a VALUE are two different things, and
this module keeps them apart: a column with ``evidence: null-empty`` exists in the file
and may never be filled, so it is emitted EMPTY -- omitting it would be unfaithful to the
format and filling it unfaithful to the contract (``_require_columns`` refuses a value in
one). This surface has no ``null-empty`` column: all 131 CUR 2.0 columns are generatable,
so all 131 may carry a value. A column the documentation describes without contracting
it at all never reaches an artifact, and :func:`_columns_of_spec` fails closed if such a
column ever appears, so an ordinary spec update cannot quietly shrink the export.

Table configurations. The export definition this renderer models enables the optional
groups whose columns the surface still declares (``INCLUDE_RESOURCES``,
``INCLUDE_SPLIT_COST_ALLOCATION_DATA``, ``INCLUDE_CAPACITY_RESERVATION_DATA``,
``INCLUDE_IAM_PRINCIPAL_DATA``) and leaves ``INCLUDE_MANUAL_DISCOUNT_COMPATIBILITY``
unset -- which is the configuration in which ``discount`` and
``discount_total_discount`` exist at all (that parameter REMOVES them). The 131 columns
are therefore the schema of one self-consistent definition, not a union of mutually
exclusive ones.

WHAT EACH GROUP PROJECTS, AND FROM WHERE
----------------------------------------
Everything below is a projection of a model field; no value is minted in this module.
The columns with NO modelled source stay EMPTY and are named here, one by one, with the
reason -- absence is absence, and a plausible-looking default would be the fabricated
fidelity the field rules forbid.

* **Bill.** ``bill_bill_type`` is the model's ``charge_category`` mapped onto the three
  documented bill types (:data:`_BILL_TYPE`); ``bill_billing_entity`` is ``AWS
  Marketplace`` for the A10 Marketplace line and ``AWS`` otherwise, which is the
  distinction the column documents; the period dates are the line's own
  ``billing_period_start``/``_end`` at ``00:00:00Z`` (the documented literal format);
  ``bill_invoice_id`` is the line's ``invoice_id`` (empty until the period is issued --
  the same window-conditional fact ``focus_aws`` records); ``bill_invoicing_entity`` and
  ``line_item_legal_entity`` are the documented Seller-of-Record literal for AWS
  services, and ``line_item_legal_entity`` is EMPTY for the Marketplace row because the
  third-party seller of record is not modelled anywhere.
* **Cost category.** ``cost_category`` is EMPTY (``{}``): the estate models resource
  tags, not the cost-category RULES the column is populated from, so the emptiness comes
  from a construct the model does not carry rather than from a value it could project.
* **Capacity reservation.** ARN and status are the reservation the row's resource
  carries (``Resource.capacity_reservation``), the same two facts ``focus_aws`` projects
  into the FOCUS pair. The ARN column carries the reservation's own modelled identifier
  -- the ``cr-`` + 17 hex value ``model/identity.py`` derives -- which is a DERIVED id in
  the documented shape, NOT an official ARN; that difference is ``TODO-verificar``, the
  same way ``focus_aws`` flags its derived ``SkuPriceId``. ``..._type`` is EMPTY: the
  documented domain is ``ODCR`` / ``EC2 Capacity Blocks for ML`` and the model does not
  distinguish them.
* **Discount.** ``discount`` carries the SAME document ``focus_aws`` derives for its
  ``x_Discounts`` extension (reduction, the two costs it was measured between, and the
  commitment the line names), so the two AWS FinOps exports cannot disagree about a
  row's discount; a line with no discount carries ``{}``, which for a map column is the
  honest empty map. ``discount_total_discount`` is the same reduction as a number.
  ``discount_bundled_discount`` is EMPTY: a bundled discount is a discount granted by
  ANOTHER service's usage, and nothing in the model ties one line's charge to another
  service's usage.
* **Identity.** ``identity_line_item_id`` is the line's own deterministic natural key
  (``line_id``, a UUIDv5) -- the model's only per-line identity -- and
  ``identity_time_interval`` is its charge period in the documented
  ``<start>/<end>`` form.
* **Line item.** Costs and rates project ``billed_cost`` (unblended),
  ``effective_cost`` (net, i.e. after every discount) and ``list_cost`` (public
  on-demand); quantities, unit and currency are the row's own; the account is the
  sub-account; ``line_item_product_code`` and ``line_item_operation`` reuse the
  ``focus_aws`` catalog maps, so a service's product code is one value in both exports;
  the resource id is the line's ``resource_uuid`` (empty for the FR-D5 / A01 / A10
  billing-only rows, exactly as in FOCUS); ``line_item_line_item_type`` is
  :func:`_line_item_type`.
  EMPTY: ``line_item_blended_cost``/``_rate`` (a blended rate is an organization-level
  average the model does not carry -- the estate prices one SKU per catalog entry, not
  an org-aggregated rate), ``line_item_iam_principal`` and ``line_item_user_identifier``
  (no IAM principal or Identity Center user is modelled anywhere),
  ``line_item_normalization_factor``/``_normalized_usage_amount`` (size-flexible RI
  normalization is not modelled), ``line_item_tax_type`` (the ``Tax`` entity carries an
  amount, not a tax type), ``line_item_usage_type`` (the service-specific usage-type
  vocabulary is not modelled; ``product_sku`` carries the catalog SKU instead), and
  ``line_item_line_item_description`` for a service no catalog entry describes (the
  resource-less Marketplace/Support lines), which is the same absence ``focus_aws``
  records for ``ChargeDescription``.
* **Pricing.** ``pricing_currency``/``pricing_unit`` are the row's own;
  ``pricing_public_on_demand_cost``/``_rate`` project the list price;
  ``pricing_rate_id`` is the derived price identity of ``(sku, currency, tier)`` -- the
  same value ``focus_aws`` emits as ``SkuPriceId``, because it identifies the same price
  row; ``pricing_term`` is the documented two-literal domain derived from whether the
  line is commitment-covered or committed-priced.
  EMPTY: ``pricing_lease_contract_length``, ``pricing_offering_class`` and
  ``pricing_purchase_option`` (the model carries no RI lease length, offering class or
  ``All/Partial/No Upfront`` option) and ``pricing_rate_code`` (a ``RateCode`` is a
  provider-assigned code, not the identity this package derives; emitting the UUID there
  would claim a code AWS never issued).
* **Product.** ``product_location``, ``product_operation``, ``product_product_family``,
  ``product_region_code``, ``product_sku``, ``product_servicecode`` and
  ``product_pricing_unit`` project the row's own region, catalog operation/product code,
  service category, SKU and unit. ``product`` is the documented map of the attributes
  that are not static columns: it carries exactly those same facts under the legacy CUR
  key names (:data:`_PRODUCT_MAP_KEYS`), omitting every key whose value is empty, which
  is what the column's own description requires.
  EMPTY: ``product_comment``, ``product_fee_code``, ``product_fee_description``,
  ``product_from_location``, ``product_from_location_type``, ``product_from_region_code``,
  ``product_instanceSKU``, ``product_instance_family``, ``product_instance_type``,
  ``product_location_type``, ``product_to _location_type``, ``product_to_location``,
  ``product_to_region_code`` and ``product_usagetype``. None of those facts exists in the
  model: there is no comment, fee code, origin/destination location, second SKU,
  instance family/type field, endpoint type or usage-type vocabulary. Two shapes deserve
  naming because they look derivable and are not: the instance family/type would have to
  be parsed out of the simulator's own ``sku_id`` (``aws-ec2-m5-large`` is a catalog key,
  not an AWS instance-type field), and duplicating ``sku_id`` into ``product_instanceSKU``
  would claim a second SKU where the estate models exactly one.
* **Reservation (27 columns).** These describe a RESERVED-INSTANCE lease. The model's
  ``Commitment`` carries a lease's identity, its term, the metered quantity it covers and
  its ``Used``/``Unused`` status, so a line covered by a commitment of kind
  ``reservation`` projects ``..._reservation_a_r_n`` (the commitment's own id --
  ``TODO-verificar``: a UUIDv5, not an ARN), ``reservation_start_time``/``_end_time``,
  ``reservation_total_reserved_units``, ``reservation_unused_quantity`` and
  ``reservation_availability_zone``. The rest of the group is EMPTY, and deliberately so:
  the estate does not model the lease's FEE accounting (the upfront-versus-recurring
  split, its amortization, normalized units, the number of reservations in a
  subscription, payment option or modification status), and computing any of it here
  would be inventing a billing model, not projecting one. NOTE the estate's AWS
  commitment is a SAVINGS PLAN (``constants.COMMITMENT_KIND``), so on today's AWS rows
  this whole group is empty -- the projection exists because the model's ``kind`` domain
  allows a reserved instance, and a reservation-kind commitment would populate it.
* **Savings plan (17 columns).** The mirror image: a line covered by a commitment of
  kind ``savings_plan`` projects ``savings_plan_savings_plan_a_r_n`` (the commitment's
  id, ``TODO-verificar`` for the same reason), ``savings_plan_start_time``/``_end_time``
  (the commitment's period) and ``savings_plan_region``. EMPTY: the commitment's fee
  accounting and its rate -- ``amortized_upfront_commitment_for_billing_period``,
  ``recurring_commitment_for_billing_period``, ``total_commitment_to_date``,
  ``used_commitment``, ``savings_plan_rate``, ``savings_plan_effective_cost``, the three
  net columns, ``offering_type``, ``payment_option``, ``purchase_term`` and
  ``instance_type_family``. The model says WHAT a commitment covers and for HOW LONG; it
  never says how the money is split between an upfront payment and a recurring fee, nor
  which plan flavour was bought.
* **Resource tags and tags.** ``resource_tags`` is the line's own tags as a map
  document; ``tags`` is the CUR 2.0 unified map, and the only documented prefix the
  estate can back is ``resourceTags/`` (the others -- ``userAttribute/``,
  ``accountTag/``, ``costCategory/``, ``iamPrincipal/`` -- have no modelled source, so
  no key carries them). A key with an empty value is dropped from both, which is what
  the columns' own descriptions require. The spec conditions a key's presence on the tag
  being ENABLED as a cost allocation tag in the Billing console: that enablement is an
  account setting the model does not carry, and assuming "not enabled" for every row
  would be as unbacked as assuming "enabled" -- what the export carries is the tag
  itself, which the estate does model.
* **Split line item (11 columns).** EMPTY, every one. They describe the Amazon ECS task /
  Kubernetes pod cost split (parent resource, split/actual/reserved usage, ratios and
  the unused halves), and the model carries no split-allocation construct: the line's
  ``k8s_namespace`` is a share label, not a split of a parent's resources and costs.
  This group is behind ``INCLUDE_SPLIT_COST_ALLOCATION_DATA``; the modelled definition
  enables it, so the columns are present and empty rather than absent.

ENCODING
--------
Every column is written as a UTF-8 string, the same decision ``focus_aws`` records: the
money, timestamps and ``map`` documents are formatted text, and a typed column would add
a second place for a representation contract to drift. ``map`` columns therefore carry a
JSON **object** string -- never a dict, which pyarrow would materialise as a struct and
the reader would decode as garbage (the trap ``focus_aws`` records for ``Tags`` and
``SkuPriceDetails``).

Timestamps use the literal format the CUR 2.0 spec publishes per field -- ``UTC,
YYYY-MM-DDTHH:mm:ssZ`` -- unlike the FOCUS 1.2 surface, for which AWS states no literal
format at all.

Provider parity: this renderer emits AWS lines ONLY, for the reason ``focus_azure``
records (rendering the whole multi-cloud estate leaked foreign scope labels and foreign
cost into an export). Azure's nearest surface is the cost-details export the coverage
matrix records as BLOCKED (names without types), and GCP's is the BigQuery billing
export, which is a table, not an S3 object tree -- so there is no second CUR-shaped
projection to keep in step.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from tools.synthetic_clouds.fidelity.spec import SurfaceSpec, load_spec
from tools.synthetic_clouds.model.billing import BillingLine
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.render.base import RenderError

# Reused from ``focus_aws`` ON PURPOSE. The two AWS FinOps exports are projections of
# the SAME model facts, and a second copy of a money formatter, of the service-code
# map or of the delivery rule is exactly how two exports start disagreeing about one
# fact. ``focus_aws`` is the older surface and owns these definitions; this module
# imports them instead of forking them.
from tools.synthetic_clouds.render.focus_aws import (
    _OPERATION,
    _SERVICE_CODE,
    MAX_ROWS_PER_PART,
    _availability_zone,
    _aws_lines,
    _descriptor,
    _execution_id,
    _Lookups,
    _money,
    _periods,
    _q,
    _sku_price_id,
    _unit_price,
    _views,
    _x_discounts,
)
from tools.synthetic_clouds.render.markers import unmarked_name

# The surface this renderer produces, as ``specs/aws/bcm-data-exports-cur2.schema.json``
# names it.
SURFACE = "aws/bcm-data-exports-cur2"

# From the spec's delivery section: the export name and prefix are the CONSUMER's (the
# path template has them as variables); the partition key, format and file names are
# the provider's.
EXPORT_NAME = "synthetic-cur2-daily-full"
S3_PREFIX = "cur2-full"
PARTITION_KEY = "BILLING_PERIOD"
DATA_SUFFIX = ".snappy.parquet"

# The sibling provenance report (see ``provenance_record``). The leading ``_`` is the
# package's convention for a document that is OURS -- scaffolding, never presented as a
# provider artifact -- and it is what keeps this file out of the artifact audit while the
# record it carries stays readable beside the export.
PROVENANCE_FILE = "_provenance.json"

# The cited specification: the source of truth for this surface.
SPEC_PATH = Path(__file__).resolve().parents[3] / "specs" / "aws" / "bcm-data-exports-cur2.schema.json"

# The rendered tree's directory under ``out_dir``. Unlike ``focus_aws``'s legacy
# ``aws_focus``, the directory IS the registered renderer name -- the convention
# ``gcp_rest_fixtures`` and ``gcp_bigquery_topology`` already follow.
RENDER_DIR = "cur2_aws"

# The Seller of Record literal for AWS services, quoted from the description of
# ``line_item_legal_entity`` itself. The Marketplace line carries no legal entity: a
# third-party Marketplace transaction's seller of record is the third-party seller, and
# the estate models no seller.
_AWS_LEGAL_ENTITY = "Amazon Web Services, Inc."
_MARKETPLACE_SERVICE = "AWS Marketplace"
_MARKETPLACE_ENTITY = "AWS Marketplace"
_AWS_ENTITY = "AWS"

# The model's ``charge_category`` -> the three documented bill types. Usage and Tax are
# line items for services used during the month; Purchase is an upfront/recurring fee;
# Credit and Adjustment are the two corrective categories, and ``Refund`` ("the negative
# charges that AWS refunded money for") is the only documented literal that describes a
# correction. TODO-verificar: CUR 2.0 documents no bill type for a RESTATEMENT (FOCUS
# names it ``ChargeClass=Correction``), so this mapping is derived, not copied.
_BILL_TYPE: dict[str, str] = {
    "Usage": "Anniversary",
    "Tax": "Anniversary",
    "Purchase": "Purchase",
    "Credit": "Refund",
    "Adjustment": "Refund",
}

# The literal a corrective or non-usage category carries in ``line_item_line_item_type``.
# The other literals depend on the row's own commitment signal and are resolved by
# ``_line_item_type``.
_LINE_ITEM_TYPE_BY_CATEGORY: dict[str, str] = {
    "Tax": "Tax",
    "Credit": "Credit",
    "Adjustment": "Refund",
}

# The legacy CUR product-attribute keys, paired with the fact this module projects into
# them. ``product`` is documented as the map that carries "any product column that
# appeared in legacy CUR but is not part of the CUR 2.0 static schema", so the keys are
# the legacy spelling of the static columns beside it. TODO-verificar: the CUR 2.0 page
# does not publish the legacy key list, so the key SPELLING comes from legacy CUR's own
# naming, while every VALUE is the same projection the static column carries.
_PRODUCT_MAP_KEYS: tuple[tuple[str, str], ...] = (
    ("location", "product_location"),
    ("operation", "product_operation"),
    ("productFamily", "product_product_family"),
    ("regionCode", "product_region_code"),
    ("servicecode", "product_servicecode"),
    ("sku", "product_sku"),
)


def specification() -> SurfaceSpec:
    """Load the cited specification for ``aws/bcm-data-exports-cur2``."""
    return load_spec(SPEC_PATH)


def _columns_of_spec() -> tuple[str, ...]:
    """Return the spec's ``emittable`` column names, refusing to drop a documented one.

    Two rules, both from ``specs/README.md``:

    * the export carries EXACTLY the columns that BELONG to the schema
      (``belongs_to_schema``: a name, a published type, a verified status, the official
      URL and an ``evidence`` of ``declared`` or ``null-empty``). A column the
      documentation describes without contracting it must NEVER reach an artifact, and a
      documented column must never be dropped -- so both directions are hard errors here
      rather than a silently shorter or longer file; and
    * a ``null-empty`` column belongs to the file and may never carry a value. It is
      emitted empty; :func:`_require_columns` enforces that on every record.

    This surface has 131 emittable columns and 0 refusals; the guard is what keeps that
    true instead of assumed.
    """
    spec = specification()
    refused = tuple(column.name for column in spec.columns if not column.belongs_to_schema)
    if refused:
        raise RenderError(
            f"cur2_aws: a especificacao {spec.surface} marcou colunas documentadas como fora do "
            f"formato: {list(refused)}. A exportacao precisa das {len(spec.columns)} colunas; "
            "nenhuma pode ser omitida em silencio e nenhuma pode ser emitida sem contrato."
        )
    return tuple(column.name for column in spec.columns)


# The 131 columns, in the specification's own order -- derived, not retyped.
_COLUMNS: tuple[str, ...] = _columns_of_spec()

# Columns that belong to the file and may never receive a value (``evidence:
# null-empty``). Empty for this surface: every CUR 2.0 column is generatable. The set is
# read from the spec rather than hard-coded so a future ``null-empty`` column is emitted
# empty instead of being filled by accident.
_NULL_EMPTY: frozenset[str] = specification().null_empty_names


def _stamp(value: datetime) -> str:
    """Return an instant in the documented ``YYYY-MM-DDTHH:mm:ssZ`` UTC form."""
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _stamp_date(value: date) -> str:
    """Return a billing-period bound at midnight UTC in the documented literal form."""
    return f"{value.isoformat()}T00:00:00Z"


def _map_document(entries: dict[str, str]) -> str:
    """Return a ``map`` column as a JSON **object** string, empty values dropped.

    Dropping an empty value is the columns' own documented rule ("a key only appears in
    the map column if it has a value that applies to the specific line item"), and it is
    also what keeps an empty map an honest ``{}`` rather than a key pointing at nothing.
    """
    return json.dumps({key: value for key, value in entries.items() if value}, sort_keys=True, separators=(",", ":"))


def _line_item_type(line: BillingLine) -> str:
    """Return the documented ``line_item_line_item_type`` literal for ``line``.

    The mapping uses the row's OWN signals, never a renderer default:

    * ``Usage`` covered by a commitment (or priced in the ``Committed`` tier) is
      ``DiscountedUsage`` -- the documented literal for "the rate of any instances for
      which you had Reserved Instance (RI) benefits", which is exactly a covered row;
    * an uncovered ``Usage`` row is ``Usage``;
    * a ``Purchase`` naming a commitment is ``RIFee`` ("the monthly recurring fee for
      subscriptions" -- A01's unused Savings Plan half is that line), and one naming no
      commitment is ``Fee`` (A10's Marketplace subscription);
    * the remaining categories are in :data:`_LINE_ITEM_TYPE_BY_CATEGORY`.
    """
    if line.charge_category == "Usage":
        committed = line.commitment_discount_id is not None or line.pricing_category == "Committed"
        return "DiscountedUsage" if committed else "Usage"
    if line.charge_category == "Purchase":
        return "RIFee" if line.commitment_discount_id else "Fee"
    return _LINE_ITEM_TYPE_BY_CATEGORY.get(line.charge_category, "")


def _pricing_term(line: BillingLine) -> str:
    """Return the documented closed domain ``Reserved`` / ``On-Demand`` for ``line``.

    ``pricing_term`` states "whether your AWS usage is Reserved or On-Demand", and the
    row itself says which: a line a commitment covers, or one already priced in the
    ``Committed`` tier, is the reserved half of the estate; every other line is
    on-demand. The domain is closed, so both literals are always reachable and no row
    leaves the column empty.
    """
    if line.commitment_discount_id is not None or line.pricing_category == "Committed":
        return "Reserved"
    return "On-Demand"


def _record(line: BillingLine, lookups: _Lookups) -> dict[str, Any]:
    """Return the 131-column CUR 2.0 record for ``line``."""
    resource = lookups.resource_by_uuid.get(line.resource_uuid) if line.resource_uuid else None
    resource_type = resource.resource_type if resource is not None else ""
    sku_id = resource.sku_id if resource is not None else ""
    reservation = resource.capacity_reservation if resource is not None else None

    service_code = _SERVICE_CODE.get(resource_type, "")
    operation = _OPERATION.get(resource_type, "")
    _, description_template = _descriptor(resource_type)
    description = (
        description_template.format(service_name=line.service_name, sku_id=sku_id)
        if description_template and sku_id
        else ""
    )

    # The commitment the line NAMES, and its kind: the kind is what selects the
    # reserved-instance group from the savings-plan group, so a line is described by the
    # instrument that actually covers it rather than by both.
    commitment = lookups.commitment_by_id.get(line.commitment_discount_id or "")
    commitment_kind = commitment.kind if commitment is not None else ""
    reservation_covered = commitment_kind == "reservation"
    savings_plan_covered = commitment_kind == "savings_plan"

    marketplace = line.service_name == _MARKETPLACE_SERVICE
    reduction = _q(line.list_cost - line.billed_cost)

    list_price = lookups.list_price_by_sku.get(sku_id)
    contracted_price = lookups.contracted_price_by_sku.get(sku_id)
    priced_sku = bool(sku_id) and (list_price is not None or contracted_price is not None)

    # ``tags`` is the unified map: the ONE prefix the estate can back is ``resourceTags/``
    # (the spec documents four more; nothing in the model produces them).
    resource_tags = _map_document(dict(line.tags))
    tags = _map_document({f"resourceTags/{key}": value for key, value in line.tags})

    # The product map carries exactly the facts the static ``product_*`` columns carry,
    # under their legacy CUR key names -- one source, two shapes.
    product = _map_document(
        {
            "location": line.region_name,
            "operation": operation,
            "productFamily": line.service_category,
            "regionCode": line.region_id,
            "servicecode": service_code,
            "sku": sku_id,
        }
    )

    return {
        "bill_bill_type": _BILL_TYPE.get(line.charge_category, ""),
        "bill_billing_entity": _MARKETPLACE_ENTITY if marketplace else _AWS_ENTITY,
        "bill_billing_period_end_date": _stamp_date(line.billing_period_end),
        "bill_billing_period_start_date": _stamp_date(line.billing_period_start),
        "bill_invoice_id": line.invoice_id or "",
        "bill_invoicing_entity": _AWS_LEGAL_ENTITY,
        "bill_payer_account_name": unmarked_name(lookups.billing_account_name.get(line.billing_account_id, "")),
        "bill_payer_account_id": line.billing_account_id,
        "cost_category": "{}",
        "capacity_reservation_capacity_reservation_arn": "" if reservation is None else reservation.reservation_id,
        "capacity_reservation_capacity_reservation_status": "" if reservation is None else reservation.status,
        "capacity_reservation_capacity_reservation_type": "",
        "discount": _x_discounts(line) or "{}",
        "discount_bundled_discount": "",
        "discount_total_discount": _money(reduction) if reduction > 0 else "",
        "identity_line_item_id": line.line_id,
        "identity_time_interval": f"{_stamp(line.charge_period_start)}/{_stamp(line.charge_period_end)}",
        "line_item_usage_account_name": unmarked_name(lookups.sub_account_name.get(line.sub_account_id, "")),
        "line_item_availability_zone": _availability_zone(line.region_id),
        "line_item_blended_cost": "",
        "line_item_blended_rate": "",
        "line_item_currency_code": line.currency,
        "line_item_iam_principal": "",
        # EMPTY for the Marketplace row: a third-party transaction's seller of record is
        # the third-party seller, and the estate models no seller.
        "line_item_legal_entity": "" if marketplace else _AWS_LEGAL_ENTITY,
        "line_item_line_item_description": description,
        "line_item_line_item_type": _line_item_type(line),
        "line_item_net_unblended_cost": _money(line.effective_cost),
        "line_item_net_unblended_rate": _unit_price(line.effective_cost, line.pricing_quantity),
        "line_item_normalization_factor": "",
        "line_item_normalized_usage_amount": "",
        "line_item_operation": operation,
        "line_item_product_code": service_code,
        "line_item_resource_id": "" if line.resource_uuid is None else line.resource_uuid,
        "line_item_tax_type": "",
        "line_item_unblended_cost": _money(line.billed_cost),
        "line_item_unblended_rate": _unit_price(line.billed_cost, line.pricing_quantity),
        "line_item_usage_account_id": line.sub_account_id,
        "line_item_usage_amount": _money(line.pricing_quantity),
        "line_item_usage_end_date": _stamp(line.charge_period_end),
        "line_item_usage_start_date": _stamp(line.charge_period_start),
        "line_item_usage_type": "",
        "line_item_user_identifier": "",
        "pricing_currency": line.currency,
        "pricing_lease_contract_length": "",
        "pricing_offering_class": "",
        "pricing_public_on_demand_cost": _money(line.list_cost),
        "pricing_public_on_demand_rate": _unit_price(line.list_cost, line.pricing_quantity),
        "pricing_purchase_option": "",
        "pricing_rate_code": "",
        "pricing_rate_id": (
            _sku_price_id(lookups.seed, sku_id, line.currency, line.pricing_category) if priced_sku else ""
        ),
        "pricing_term": _pricing_term(line),
        "pricing_unit": line.pricing_unit,
        "product": product,
        "product_comment": "",
        "product_fee_code": "",
        "product_fee_description": "",
        "product_from_location": "",
        "product_from_location_type": "",
        "product_from_region_code": "",
        "product_instanceSKU": "",
        "product_instance_family": "",
        "product_instance_type": "",
        "product_location": line.region_name,
        "product_location_type": "",
        "product_operation": operation,
        "product_pricing_unit": line.pricing_unit,
        "product_product_family": line.service_category,
        "product_region_code": line.region_id,
        "product_sku": sku_id,
        "product_servicecode": service_code,
        # The DOCUMENTED spelling, space included (spec divergence 3): the official page
        # publishes ``product_to _location_type``, which is not a valid SQL identifier.
        # The spec preserves the documentation's own text, so the artifact does too.
        "product_to _location_type": "",
        "product_to_location": "",
        "product_to_region_code": "",
        "product_usagetype": "",
        # The reserved-instance group: projected from the lease's own modelled facts,
        # empty on a line no reserved instance covers.
        "reservation_amortized_upfront_cost_for_usage": "",
        "reservation_amortized_upfront_fee_for_billing_period": "",
        "reservation_availability_zone": _availability_zone(line.region_id) if reservation_covered else "",
        "reservation_effective_cost": "",
        "reservation_end_time": commitment.period_end.isoformat() if reservation_covered and commitment else "",
        "reservation_modification_status": "",
        "reservation_net_amortized_upfront_cost_for_usage": "",
        "reservation_net_amortized_upfront_fee_for_billing_period": "",
        "reservation_net_effective_cost": "",
        "reservation_net_recurring_fee_for_usage": "",
        "reservation_net_unused_amortized_upfront_fee_for_billing_period": "",
        "reservation_net_unused_recurring_fee": "",
        "reservation_net_upfront_value": "",
        "reservation_normalized_units_per_reservation": "",
        "reservation_number_of_reservations": "",
        "reservation_recurring_fee_for_usage": "",
        "reservation_reservation_a_r_n": commitment.identity.uuid if reservation_covered and commitment else "",
        "reservation_start_time": commitment.period_start.isoformat() if reservation_covered and commitment else "",
        "reservation_subscription_id": "",
        "reservation_total_reserved_normalized_units": "",
        "reservation_total_reserved_units": (
            _money(commitment.quantity) if reservation_covered and commitment else ""
        ),
        "reservation_units_per_reservation": "",
        "reservation_unused_amortized_upfront_fee_for_billing_period": "",
        "reservation_unused_normalized_unit_quantity": "",
        "reservation_unused_quantity": (
            _money(commitment.quantity)
            if reservation_covered and commitment and line.commitment_discount_status == "Unused"
            else ""
        ),
        "reservation_unused_recurring_fee": "",
        "reservation_upfront_value": "",
        "resource_tags": resource_tags,
        # The savings-plan group: the mirror image, projected from the same commitment.
        "savings_plan_amortized_upfront_commitment_for_billing_period": "",
        "savings_plan_end_time": commitment.period_end.isoformat() if savings_plan_covered and commitment else "",
        "savings_plan_instance_type_family": "",
        "savings_plan_net_amortized_upfront_commitment_for_billing_period": "",
        "savings_plan_net_recurring_commitment_for_billing_period": "",
        "savings_plan_net_savings_plan_effective_cost": "",
        "savings_plan_offering_type": "",
        "savings_plan_payment_option": "",
        "savings_plan_purchase_term": "",
        "savings_plan_recurring_commitment_for_billing_period": "",
        "savings_plan_region": line.region_id if savings_plan_covered else "",
        "savings_plan_savings_plan_a_r_n": commitment.identity.uuid if savings_plan_covered and commitment else "",
        "savings_plan_savings_plan_effective_cost": "",
        "savings_plan_savings_plan_rate": "",
        "savings_plan_start_time": commitment.period_start.isoformat() if savings_plan_covered and commitment else "",
        "savings_plan_total_commitment_to_date": "",
        "savings_plan_used_commitment": "",
        "split_line_item_actual_usage": "",
        "split_line_item_net_split_cost": "",
        "split_line_item_net_unused_cost": "",
        "split_line_item_parent_resource_id": "",
        "split_line_item_public_on_demand_split_cost": "",
        "split_line_item_public_on_demand_unused_cost": "",
        "split_line_item_reserved_usage": "",
        "split_line_item_split_cost": "",
        "split_line_item_split_usage": "",
        "split_line_item_split_usage_ratio": "",
        "split_line_item_unused_cost": "",
        "tags": tags,
    }


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
      contract is. Emitting it empty is the only faithful answer, so a value is an error
      rather than a surprise.
    """
    fields = set(record)
    expected = set(_COLUMNS)
    if fields != expected:
        raise RenderError(
            "cur2_aws: registro com campos diferentes das colunas emitidas: "
            f"sobram={sorted(fields - expected)} faltam={sorted(expected - fields)}"
        )
    filled = sorted(name for name in _NULL_EMPTY & fields if record[name])
    if filled:
        raise RenderError(f"cur2_aws: colunas null-empty receberam valor: {filled}")


def _rows(estate: CanonicalEstate, lines: list[BillingLine]) -> list[dict[str, Any]]:
    lookups = _Lookups(estate)
    rows: list[dict[str, Any]] = []
    checked = False
    for line in lines:
        record = _record(line, lookups)
        if not checked:
            _require_columns(record)
            checked = True
        rows.append(record)
    return rows


def render_csv_bytes(estate: CanonicalEstate) -> bytes:
    """Return the CUR 2.0 CSV bytes for every AWS line."""
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(_COLUMNS), extrasaction="raise", lineterminator="\n")
    writer.writeheader()
    for record in _rows(estate, _aws_lines(estate)):
        writer.writerow(record)
    return buffer.getvalue().encode("utf-8")


def render_csv_gz_bytes(estate: CanonicalEstate) -> bytes:
    """Return the gzip of :func:`render_csv_bytes` (the documented ``.csv.gz`` name)."""
    return gzip.compress(render_csv_bytes(estate), mtime=0)


def render_parquet_bytes(estate: CanonicalEstate) -> bytes:
    """Return the CUR 2.0 Parquet bytes for every AWS line.

    Every column is typed ``string``: the money is already 6-dp text, the timestamps are
    in the documented literal form, and the ``map`` columns are JSON object strings. See
    the module docstring's ENCODING section.
    """
    return _parquet_bytes(_rows(estate, _aws_lines(estate)))


def _parquet_bytes(rows: list[dict[str, Any]]) -> bytes:
    """Encode ``rows`` (already 131-column records) as one snappy Parquet file."""
    columns: dict[str, list[str]] = {col: [str(row[col]) for row in rows] for col in _COLUMNS}
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


# ── S3 layout (BCM Data Export, create-new mode) ──────────────────────────────


def s3_key(
    *,
    billing_period: str,
    filename: str,
    execution: str | None = None,
    kind: str = "data",
    partition_key: str = PARTITION_KEY,
    prefix: str = S3_PREFIX,
    export_name: str = EXPORT_NAME,
) -> str:
    """Return the S3 key for one exported object.

    ``kind`` is ``"data"`` or ``"metadata"``. ``execution`` is the
    ``<timestamp>-<execution-id>`` directory of a create-new delivery.

    Only the ``data`` prefix is POPULATED. The ``metadata`` prefix and its two manifests
    are part of the documented layout, and neither is written: the manifest's field names
    are exactly what the documentation does not establish, so the run is recorded in the
    sibling ``_provenance.json`` instead (see :func:`provenance_record`). The parameters
    stay because the layout they name is the documented contract, and a test asserts that
    whatever this renderer writes stays out of it.

    The partition key defaults to the UPPERCASE ``BILLING_PERIOD`` this surface's
    documentation states literally. The parameter exists so a contract test can build the
    other casing too.
    """
    head = f"{prefix}/{export_name}/{kind}/{partition_key}={billing_period}"
    if execution:
        head = f"{head}/{execution}"
    return f"{head}/{filename}"


def schema_fingerprint() -> str:
    """Return a stable digest of the emitted column set (sorted, so order is not a factor).

    Deliberately NOT ``synth:``-prefixed: that prefix marks synthetic DATA
    (``render/markers.py``). This is a real hash of a real schema, and conflating the two
    would break the provenance marker's meaning.
    """
    return hashlib.sha256("\n".join(sorted(_COLUMNS)).encode()).hexdigest()


def manifest_section() -> dict[str, Any]:
    """Return the spec's OWN ``manifest`` section, verbatim.

    Read from the cited specification rather than paraphrased, so the record below cannot
    drift from the evidence: the section states the manifest's ``status`` (``partial``),
    its ``file_name``, the ONE key the documentation confirms
    (``additionalOutputFiles``), and -- in its own ``notes`` -- that "AWS documents the
    manifest by prose description only. No JSON schema, key list or example is published;
    every key except additionalOutputFiles is UNVERIFIED."
    """
    raw = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    section = raw.get("manifest")
    return dict(section) if isinstance(section, dict) else {}


def provenance_record(*, estate: CanonicalEstate, objects: list[dict[str, Any]]) -> dict[str, Any]:
    """Return the export run's provenance record -- the manifest's place, and why.

    A manifest is a DOCUMENT: writing one means NAMING its fields, and the CUR 2.0 pages
    publish no JSON schema, no key list and no example -- every key except
    ``additionalOutputFiles`` is registered as unverified in the cited spec. A file whose
    schema we chose would be indistinguishable, to a consumer, from an invented field
    inside a column, so this renderer delivers the DATA only and records the run here, in
    the sibling ``_provenance.json``: ours by name (the leading ``_``) and by
    construction, never presented as an AWS artifact. ``focus_aws``, ``focus_azure`` and
    ``aws_config_snapshot`` record the same decision for the same reason.

    The record carries the mechanism (prefixes, partition key, format, compression), the
    column counts, the objects delivered with their sizes and row counts, and the spec's
    own ``manifest`` section verbatim -- including the file-name divergence the spec
    registers, so the reader sees both sides instead of a silent choice.
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
            "partition_key": PARTITION_KEY,
            "partition_format": "YYYY-MM",
            "format": "parquet",
            "compression": "snappy",
            "delivery_mode": "CREATE_NEW_REPORT",
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
            "manifest file name: <export-name>-Manifest.json vs Manifest.json (spec divergence 2)",
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


def _write_object(path: Path, payload: bytes, written: list[Path]) -> None:
    """Write ``payload`` at ``path`` and record the object once."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    if path not in written:
        written.append(path)


def _write_execution(
    *,
    target: Path,
    estate: CanonicalEstate,
    billing_period: str,
    view: list[BillingLine],
    written: list[Path],
    objects: list[dict[str, Any]],
) -> None:
    """Write one execution's DATA parts (see :func:`provenance_record` for the manifest)."""
    if not view:
        return
    export_time = max(line.export_time for line in view)
    execution = _execution_id(estate, billing_period, export_time)
    rows = _rows(estate, view)

    for start in range(0, len(rows), MAX_ROWS_PER_PART):
        chunk = rows[start : start + MAX_ROWS_PER_PART]
        index = start // MAX_ROWS_PER_PART + 1
        filename = f"{EXPORT_NAME}-{index:05d}{DATA_SUFFIX}"
        payload = _parquet_bytes(chunk)
        key = s3_key(billing_period=billing_period, execution=execution, filename=filename)
        _write_object(target / key, payload, written)
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


class AwsCur2Renderer:
    """Renders the canonical estate to an AWS CUR 2.0 BCM Data Export tree."""

    name = "cur2_aws"

    def render(self, estate: CanonicalEstate, out_dir: Path) -> list[Path]:
        """Write the export tree under ``out_dir/cur2_aws/``; return written paths.

        The tree is the delivered DATA plus the sibling ``_provenance.json``: the manifest
        the create-new delivery also documents is deliberately absent, for the reason
        :func:`provenance_record` records.
        """
        target = out_dir / RENDER_DIR
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
