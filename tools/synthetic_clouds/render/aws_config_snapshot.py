"""AWS Config snapshot delivery -> Amazon S3 renderer (seguranca/inventario).

Projects the canonical estate into the **36 fields** that
``specs/aws/aws-config-snapshot-s3.schema.json`` documents -- in four sets, because the
delivered snapshot is one JSON document with two levels of nested objects plus the SNS
notification that announces it:

===============================  =====  ==================================================
``configuration-file-envelope``     3  the delivered ``.json.gz`` object's top level
``configuration-item``             21  each object of ``configurationItems[]``
``relationship``                    6  each object of ``configurationItems[].relationships[]``
``sns-delivery-notification``       6  the ``Message`` payload of the delivery notification
===============================  =====  ==================================================

WHAT IS DELIVERED, AND WHERE
----------------------------
The S3 tree is the documented layout, derived from the official notification examples
(the page publishes literal ``s3ObjectKey`` values, not a placeholder template -- the
spec records that difference and the unpadded ``month``/``day`` it exposes)::

    AWSLogs/{accountId}/Config/{region}/{year}/{month}/{day}/ConfigSnapshot/
        {accountId}_Config_{region}_ConfigSnapshot_{YYYYMMDDTHHmmssZ}_{snapshotId}.json.gz

One snapshot per (account, region) pair the estate models resources in, taken at the
start of ``sim_now`` (the day the estate is current) and covering that pair's resources.
No manifest is emitted: the official pages describe none and the spec registers the
absence as a finding (``unverified`` topic), so inventing an index would be a mechanism
that does not exist.

Field spellings are the FILE's, not the API's, wherever the two diverge -- the spec's
section 5 records all four cases and the S3 example is the artifact under test:
``configurationItemVersion`` (API ``version``), ``configurationStateID`` next to the API
``configurationStateId``, ``availibilityZone`` with the official example's own typo, and
``relationships[].name`` beside the API's ``relationshipName``.

The bucket name is the CONSUMER's choice (the delivery channel's bucket is configured by
the customer), so this module names one and says so; the object key inside it is the
documented one.

WHAT EACH FIELD PROJECTS, AND WHAT STAYS EMPTY
----------------------------------------------
Absence is emitted in the artifact's OWN shape, the shapes the official example itself
uses: an empty string for a string field, ``{}`` for a map or object, ``[]`` for an
array (the example publishes ``"configurationItemMD5Hash": ""``, ``"relatedEvents": []``
and ``"tags": {}``). A documented column with no model source is emitted that empty --
never a plausible value.

* ``fileVersion`` / ``configurationItemVersion`` / ``recordVersion`` -- the versions the
  official example and the spec's reference state (``"1.0"``, ``"1.0"``, ``"1.1"``).
* ``configurationItems`` -- one configuration item per AWS resource the estate models in
  that (account, region), EXCEPT ``data_transfer``: the estate models that type as a cost
  line rather than a live resource (``model/identity.py`` gives it no id, and
  ``aws_resource_id`` refuses it), so it has no object to record.
* ``resourceId`` -- the resource's canonical id, ``model/identity.py::aws_resource_id``,
  the same projection the other AWS surfaces make (a DERIVED id in the documented shape,
  ``TODO-verificar`` there).
* ``resourceName``, ``accountId``, ``awsRegion``, ``tags`` -- the resource's own name, its
  owning account (``parent_scope_id`` is the 12-digit account id), its region and its tag
  map (empty for the untagged subset, FR-D2).
* ``availibilityZone`` -- the same derivation ``focus_aws`` already emits for the FOCUS
  ``AvailabilityZone`` column (``<region><letter>``, ``TODO-verificar`` there): the estate
  models one AZ per region, and two AWS exports of one estate must not disagree.
* ``configurationItemStatus`` -- ``OK``, the literal the official example carries and the
  documented value for a resource whose configuration was recorded: the snapshot exists
  precisely because these resources are being recorded.
* ``resourceType`` -- the native type in the vocabulary the AWS Config page publishes, read
  from ``generate/type_catalog.py`` (``ec2_instance`` -> ``AWS::EC2::Instance``,
  ``ebs_volume`` -> ``AWS::EC2::Volume``). That table is deliberately PARTIAL: the page
  exemplifies those two and declares the supported list dynamic, so every other type stays
  EMPTY -- the renderer never deduces ``AWS::Servico::Recurso`` from the simulator's own
  token. Widening it is a catalog change with a citation, not a renderer guess.
* ``configurationItemMD5Hash`` and ``relatedEvents`` -- emitted EMPTY, which is not a
  model gap but a documented fact: the page states both have been empty since version 1.3
  of the configuration item. The KEYS are present, as the spec's section 5.7 requires
  ("O simulador deve emitir as chaves presentes e vazias, não omiti-las").
* ``s3ObjectKey`` / ``s3Bucket`` / ``notificationCreationTime`` / ``messageType`` /
  ``configSnapshotId`` -- the notification is derived from the delivery this renderer just
  wrote: the key is the object's real key, the bucket the one named above, the creation
  time the snapshot instant, the message type the documented literal for a SNAPSHOT
  delivery (the other published literal belongs to a history delivery), and the snapshot
  id the id in the file name. The notification is NOT an S3 object: it is the SQS/SNS
  ``Message`` body, stored here under ``notifications/`` -- a path this module chose.
* ``requestId`` -- the identifier of the ``DeliverConfigSnapshot`` CALL, minted
  deterministically per (account, region, instant) by :func:`request_id` (UUIDv5 over a
  logical path, the project's identity primitive). It identifies the request, not a
  resource, so it is not an entity the estate has to model: the documentation publishes it
  as an opaque UUID carried by the response, and minting it is what makes the envelope's
  required column carry a value. ``TODO-verificar``: the shape is the documented one, the
  entropy is this package's.

REAL GAPS -- the model does not carry these, so the columns ship EMPTY
---------------------------------------------------------------------
* ``resourceType`` for every type the catalog does not exemplify: the AWS Config page
  publishes two examples and calls the supported list dynamic, so the other tokens have no
  documented name. A type with no catalog entry emits an empty column instead of a name
  deduced from the pattern.
* ``arn``: no ARN is modelled anywhere (``model/identity.py`` records that the external
  ``aws_sim.arns`` is where AWS ARNs live), so no ARN can be projected.
* ``configuration`` / ``supplementaryConfiguration``: the CI's ``configuration`` is the
  resource's Describe/List API response, and the spec's section 0 establishes that AWS
  Config publishes NO per-resource property schema. Emitting ``{}`` is the honest empty
  document; emitting a plausible-looking resource body would invent unpublished names.
* ``relationships`` (and therefore the whole ``relationship`` set): the estate models no
  resource-to-resource relationship. The set is still proved, deliberately, by
  ``shape/relationship.json`` -- a fixture carrying the six documented names with empty
  values, so the gap is visible and testable instead of silently absent. It is NOT a
  delivery: the delivered ``relationships`` arrays are empty.
* the three timestamps (``configurationItemCaptureTime``,
  ``configurationItemDeliveryTime``, ``resourceCreationTime``), ``recordingFrequency``
  (documented as an API-response-only field, absent from the S3 example) and
  ``configurationStateID``/``configurationStateId``: the estate carries no
  configuration-event timeline. ``requestId`` is NOT in this list: the request's identity is
  minted by :func:`request_id` -- what the model lacks is the request as an entity, not the
  identifier the format requires.
WHY THERE ARE ``extracted/`` FILES AT ALL
-----------------------------------------
The delivered object is gzipped JSON, and the fidelity core reads a JSON artifact as text
(``fidelity/artifacts._json_columns`` calls ``read_text``), so it cannot open the delivered
``.json.gz`` directly. Two of this surface's four sets are also NESTED inside the delivered
document (``configurationItems[]`` and ``configurationItems[].relationships[]``), so no
single top-level key set could describe them even if it could.

Both problems have the same answer: ``extracted/<set>.json`` carries the set's objects
VERBATIM -- the envelopes of every delivered object, and the concatenation of their
``configurationItems`` arrays. They are files the package writes for verification, NOT S3
objects of the delivery (the delivered tree is exactly ``AWSLogs/...``), and the test
proves each one equals the delivered document rather than trusting this module.
"""

from __future__ import annotations

import gzip
import json
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any

from tools.synthetic_clouds.determinism import identity_for
from tools.synthetic_clouds.fidelity.spec import SurfaceSpec, load_spec
from tools.synthetic_clouds.generate.constants import PROVIDER_KEY_AWS
from tools.synthetic_clouds.generate.type_catalog import config_type
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.identity import AWS_ID_PREFIXES, aws_resource_id
from tools.synthetic_clouds.model.resource import Resource
from tools.synthetic_clouds.render.base import RenderError

# Reused from ``focus_aws`` ON PURPOSE: the availability-zone derivation is the same
# projection of the same model fact, and a second copy is how two AWS exports start
# disagreeing about one resource.
from tools.synthetic_clouds.render.focus_aws import _availability_zone

# The surface this renderer produces, as the spec names it.
SURFACE = "aws/aws-config-snapshot-s3"

# The cited specification: the source of truth for this surface.
SPEC_PATH = Path(__file__).resolve().parents[3] / "specs" / "aws" / "aws-config-snapshot-s3.schema.json"

# The rendered tree's directory under ``out_dir``.
RENDER_DIR = "aws_config_snapshot"

# The delivered tree, plus the two directories that are NOT S3 objects and are named here
# so no reader mistakes them for a delivered layout.
S3_ROOT = "AWSLogs"
NOTIFICATION_DIR = "notifications"
EXTRACTION_DIR = "extracted"
SHAPE_DIR = "shape"

# The delivery channel's bucket is configured by the customer; this module names its own
# (the official example's bucket is `config-bucket-123456789012-ohio`, likewise a choice).
BUCKET_BASE = "synthetic-config-delivery"

# The versions and literals the official example and the spec's reference publish.
FILE_VERSION = "1.0"
CONFIGURATION_ITEM_VERSION = "1.0"
RECORD_VERSION = "1.1"
MESSAGE_TYPE = "ConfigurationSnapshotDeliveryCompleted"
CONFIGURATION_ITEM_STATUS = "OK"

# The sets of the cited specification, by name.
ENVELOPE_SCOPE = "configuration-file-envelope"
ITEM_SCOPE = "configuration-item"
RELATIONSHIP_SCOPE = "relationship"
NOTIFICATION_SCOPE = "sns-delivery-notification"

# The model facts each set is allowed to project. A non-empty value anywhere else would be
# a value the canonical model does not carry -- :func:`_require_projection` fails closed.
_ENVELOPE_PROJECTED: frozenset[str] = frozenset({"fileVersion", "requestId", "configurationItems"})
_ITEM_PROJECTED: frozenset[str] = frozenset(
    {
        "configurationItemVersion",
        "resourceId",
        "resourceName",
        "accountId",
        "awsRegion",
        "availibilityZone",
        "configurationItemStatus",
        "resourceType",
        "tags",
    }
)
_NOTIFICATION_PROJECTED: frozenset[str] = frozenset(
    {"s3ObjectKey", "s3Bucket", "notificationCreationTime", "messageType", "recordVersion", "configSnapshotId"}
)


def specification() -> SurfaceSpec:
    """Load the cited specification for ``aws/aws-config-snapshot-s3``."""
    return load_spec(SPEC_PATH)


#: Colunas OBRIGATORIAS da spec que saem VAZIAS, com o motivo. O teste golden prova que esta
#: declaracao e EXATA nos dois sentidos: uma coluna obrigatoria sem valor em nenhum artefato
#: precisa estar aqui, e um nome aqui nao pode ter valor em lugar nenhum. Vazio nesta
#: superficie desde que :func:`request_id` passou a cunhar o identificador da requisicao.
REQUIRED_EMPTY_GAPS: dict[str, str] = {}


def _names_of(scope: str) -> tuple[str, ...]:
    """Return a set's column names in documentation order, refusing to drop one.

    Every column of this surface is verified, typed and URL-cited, so all 36 BELONG to the
    artifact. A column the documentation describes without contracting it must never reach
    a file, and a documented column must never be dropped: both are hard errors.
    """
    columns = specification().columns_for(scope)
    refused = tuple(column.name for column in columns if not column.belongs_to_schema)
    if refused:
        raise RenderError(
            f"aws_config_snapshot: o conjunto {scope!r} da especificacao {SURFACE} marcou colunas "
            f"documentadas como fora do formato: {list(refused)}"
        )
    return tuple(column.name for column in columns)


# The four sets, in documentation order -- derived, not retyped.
_ENVELOPE_COLUMNS: tuple[str, ...] = _names_of(ENVELOPE_SCOPE)
_ITEM_COLUMNS: tuple[str, ...] = _names_of(ITEM_SCOPE)
_RELATIONSHIP_COLUMNS: tuple[str, ...] = _names_of(RELATIONSHIP_SCOPE)
_NOTIFICATION_COLUMNS: tuple[str, ...] = _names_of(NOTIFICATION_SCOPE)

# Columns that belong to the file and may never receive a value (``evidence: null-empty``).
# Empty across the four sets: the emptiness this renderer uses is either a MODEL gap or a
# documented "empty since version 1.3", both argued in the module docstring.
_NULL_EMPTY: frozenset[str] = specification().null_empty_names

# The types of the spec that have a documented empty shape in this artifact.
_EMPTY_BY_TYPE: dict[str, Any] = {"string": "", "array": [], "map": {}, "object": {}}


def _empty_value(column_type: str | None) -> Any:
    """Return the empty value of a documented type, or fail closed on an unmapped one."""
    if column_type is None or column_type not in _EMPTY_BY_TYPE:
        raise RenderError(
            f"aws_config_snapshot: tipo documentado sem forma vazia definida: {column_type!r}"
        )
    return _EMPTY_BY_TYPE[column_type]


def _is_empty(value: Any) -> bool:
    """True when ``value`` is the artifact's shape for "no value" (never for zero)."""
    return value is None or value == "" or value == {} or value == []


def _require_projection(record: dict[str, Any], columns: tuple[str, ...], projected: frozenset[str], where: str) -> None:
    """Fail closed when a document is not exactly the set's columns, or fills a gap.

    Two failures: a divergent key set (a documented column dropped, or a key no
    documentation defines) and a non-empty value outside the model-backed ``projected``
    names. The second is the fabrication rule of this package expressed in code.
    """
    fields = set(record)
    expected = set(columns)
    if fields != expected:
        raise RenderError(
            f"aws_config_snapshot: {where} com campos diferentes do conjunto emitido: "
            f"sobram={sorted(fields - expected)} faltam={sorted(expected - fields)}"
        )
    filled = sorted(name for name in _NULL_EMPTY & fields if not _is_empty(record[name]))
    if filled:
        raise RenderError(f"aws_config_snapshot: colunas null-empty receberam valor: {filled}")
    invented = sorted(
        name for name in fields if not _is_empty(record[name]) and name not in projected
    )
    if invented:
        raise RenderError(
            f"aws_config_snapshot: {where} preencheu colunas sem fonte no modelo canonico "
            f"(lacuna, nao valor): {invented}"
        )


def _stamp(moment: datetime) -> str:
    """Return the documented ``YYYYMMDDTHHmmssZ`` object-name token."""
    return moment.strftime("%Y%m%dT%H%M%SZ")


def _millis(moment: datetime) -> str:
    """Return an instant in the notification's documented form (ISO 8601, milliseconds, UTC)."""
    return moment.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def snapshot_moment(sim_now: date) -> datetime:
    """Return the instant a snapshot is taken: the start of the day the estate is current."""
    return datetime.combine(sim_now, time(0, 0), tzinfo=UTC)


def snapshot_id(estate: CanonicalEstate, account_id: str, region: str, moment: datetime) -> str:
    """Return the derived ``configSnapshotId`` (a UUID, the shape the template names).

    ``TODO-verificar``: DERIVED, not an AWS-issued id. The estate models no snapshot
    resource, and the published ``s3ObjectKey`` example carries a UUID in this position;
    the value is a function of ``(seed, account, region, instant)`` only.
    """
    return identity_for(estate.seed, f"config-snapshot/{account_id}/{region}/{_stamp(moment)}")


def s3_key(*, account_id: str, region: str, moment: datetime, config_snapshot_id: str) -> str:
    """Return the documented ``s3ObjectKey`` of a snapshot object.

    ``month`` and ``day`` are NOT zero-padded, which is what the official example
    publishes literally (``/2016/9/27/``) and the spec records as a fidelity note.
    """
    name = (
        f"{account_id}_Config_{region}_ConfigSnapshot_{_stamp(moment)}_{config_snapshot_id}.json.gz"
    )
    return (
        f"{S3_ROOT}/{account_id}/Config/{region}/{moment.year}/{moment.month}/{moment.day}/"
        f"ConfigSnapshot/{name}"
    )


def bucket_name(account_id: str, region: str) -> str:
    """Return this simulator's delivery-channel bucket name for a (account, region) pair."""
    return f"{BUCKET_BASE}-{account_id}-{region}"


def _recordable(resource: Resource) -> bool:
    """True when the estate models this resource as an OBJECT (and not as a cost line).

    ``data_transfer`` is the one AWS catalog type with no object: the estate prices it as a
    cost line, ``model/identity.py`` gives it no id, and a configuration item for a thing
    that does not exist would be a claim the model cannot back.
    """
    return resource.resource_type in AWS_ID_PREFIXES


def _configuration_item(resource: Resource) -> dict[str, Any]:
    """Return the 21-field configuration item of ``resource`` (file spelling)."""
    record = {
        "configurationItemVersion": CONFIGURATION_ITEM_VERSION,
        "resourceId": aws_resource_id(resource.resource_type, resource.identity.uuid),
        "resourceName": resource.resource_name,
        # No ARN is modelled anywhere in the estate -- see the module docstring.
        "arn": "",
        "accountId": resource.parent_scope_id,
        "awsRegion": resource.region_id,
        "availibilityZone": _availability_zone(resource.region_id),
        # No configuration-event timeline is modelled; the request's IDENTIFIER is minted by
        # :func:`request_id`, so it is not a gap.
        "configurationItemCaptureTime": "",
        "configurationItemDeliveryTime": "",
        # Both spellings belong to the file's vocabulary (spec divergence 1); the API one
        # stays empty because this artifact is the S3 file.
        "configurationStateID": "",
        "configurationStateId": "",
        "configurationItemStatus": CONFIGURATION_ITEM_STATUS,
        # Documented EMPTY since version 1.3 of the configuration item: the key is present
        # and carries no value, exactly as the official example shows.
        "configurationItemMD5Hash": "",
        "relatedEvents": [],
        # Documented as an API-response-only field; the S3 example does not carry it.
        "recordingFrequency": "",
        "resourceCreationTime": "",
        # The native type, in the vocabulary the AWS Config page publishes. The table is
        # deliberately partial (``generate/type_catalog.py``): the page exemplifies
        # ``AWS::EC2::Instance`` and ``AWS::EC2::Volume`` and declares the list dynamic, so a
        # type it does not name stays EMPTY instead of a name deduced from the pattern.
        "resourceType": config_type(resource.resource_type) or "",
        "tags": dict(resource.tags),
        # GAP: the estate models no resource-to-resource relationship.
        "relationships": [],
        # GAP: AWS Config publishes no per-resource property schema (spec section 0), so an
        # empty document is the honest value -- never a plausible-looking resource body.
        "configuration": {},
        "supplementaryConfiguration": {},
    }
    _require_projection(record, _ITEM_COLUMNS, _ITEM_PROJECTED, f"configuration item de {resource.identity.uuid}")
    return record


def request_id(estate: CanonicalEstate, account_id: str, region: str, moment: datetime) -> str:
    """Return the ``requestId`` of the ``DeliverConfigSnapshot`` call that produced a snapshot.

    The field is the identifier of the REQUEST, not of a resource: it correlates nothing the
    consumer holds, and the documentation publishes it as an opaque id carried by the response
    (the official snapshot example carries a UUID). Minting it deterministically -- UUIDv5 over
    a logical path, ``determinism.identity_for``, the primitive every other identifier in this
    package comes from -- is therefore the same discipline ``snapshot_id`` and
    ``model/identity.py``'s ids follow, and it is what makes the envelope's required column
    carry a value.

    ``TODO-verificar``: DERIVED, NOT an AWS-issued request id. Its shape is the documented one
    (a UUID); its entropy is this package's.
    """
    return identity_for(estate.seed, f"config-snapshot-request/{account_id}/{region}/{_stamp(moment)}")


def _envelope(configuration_items: list[dict[str, Any]], request: str) -> dict[str, Any]:
    """Return the 3-field snapshot document that wraps ``configuration_items``."""
    record = {
        "fileVersion": FILE_VERSION,
        # The request that triggered the snapshot is not modelled as an entity; its IDENTIFIER
        # is minted (see :func:`request_id`), which is what makes this required column carry a
        # value instead of an empty string.
        "requestId": request,
        "configurationItems": configuration_items,
    }
    _require_projection(record, _ENVELOPE_COLUMNS, _ENVELOPE_PROJECTED, "envelope do snapshot")
    return record


def _notification(
    *, account_id: str, region: str, moment: datetime, key: str, config_snapshot_id: str
) -> dict[str, Any]:
    """Return the 6-field ``Message`` payload of the snapshot delivery notification."""
    record = {
        "s3ObjectKey": key,
        "s3Bucket": bucket_name(account_id, region),
        "notificationCreationTime": _millis(moment),
        "messageType": MESSAGE_TYPE,
        "recordVersion": RECORD_VERSION,
        # Present on a SNAPSHOT notification only, which is the delivery emitted here.
        "configSnapshotId": config_snapshot_id,
    }
    _require_projection(record, _NOTIFICATION_COLUMNS, _NOTIFICATION_PROJECTED, "notificacao SNS")
    return record


def relationship_shape() -> dict[str, Any]:
    """Return the documented ``relationship`` set as a SHAPE fixture (all values empty).

    The estate models no relationship, so no delivered object carries one and the six
    documented names would otherwise never be exercised. This fixture carries exactly those
    six names with the empty value of each documented type, so the gap is visible and the
    test can prove that (a) the names are the documented ones and (b) not one value was
    invented to fill them. It is NOT a delivered artifact.
    """
    document = {
        column.name: _empty_value(column.type)
        for column in specification().columns_for(RELATIONSHIP_SCOPE)
    }
    _require_projection(document, _RELATIONSHIP_COLUMNS, frozenset(), "fixture de forma de relationship")
    return document


def _pairs(estate: CanonicalEstate) -> list[tuple[str, str, list[Resource]]]:
    """Return the estate's (account, region, resources) pairs, in deterministic order.

    Grouped by the pair because a snapshot describes the resources of ONE region in ONE
    account, and sorted by the resources' logical paths so two renders of a seed produce
    the same documents in the same order.
    """
    grouped: dict[tuple[str, str], list[Resource]] = {}
    for resource in estate.resources:
        if resource.identity.provider != PROVIDER_KEY_AWS or not _recordable(resource):
            continue
        grouped.setdefault((resource.parent_scope_id, resource.region_id), []).append(resource)
    return [
        (account_id, region, sorted(grouped[(account_id, region)], key=lambda r: r.identity.logical_path))
        for account_id, region in sorted(grouped)
    ]


def _write_bytes(path: Path, payload: bytes, written: list[Path]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    if path not in written:
        written.append(path)


def _write_text(path: Path, text: str, written: list[Path]) -> None:
    _write_bytes(path, text.encode("utf-8"), written)


class AwsConfigSnapshotRenderer:
    """Renders the canonical estate to an AWS Config snapshot delivery tree."""

    name = "aws_config_snapshot"

    def render(self, estate: CanonicalEstate, out_dir: Path) -> list[Path]:
        """Write the delivery under ``out_dir/aws_config_snapshot/``; return written paths."""
        target = out_dir / RENDER_DIR
        written: list[Path] = []
        moment = snapshot_moment(estate.sim_now)
        delivered_items: list[dict[str, Any]] = []
        delivered_envelopes: list[dict[str, Any]] = []

        for account_id, region, resources in _pairs(estate):
            items = [_configuration_item(resource) for resource in resources]
            delivered_items.extend(items)
            envelope = _envelope(items, request_id(estate, account_id, region, moment))
            delivered_envelopes.append(envelope)
            config_snapshot_id = snapshot_id(estate, account_id, region, moment)
            key = s3_key(
                account_id=account_id,
                region=region,
                moment=moment,
                config_snapshot_id=config_snapshot_id,
            )
            # The delivered object: the documented one, gzipped JSON, at the documented key.
            _write_bytes(
                target / key,
                gzip.compress(json.dumps(envelope).encode("utf-8"), mtime=0),
                written,
            )
            # The SNS Message payload is NOT an S3 object; it is stored beside the tree.
            _write_text(
                target
                / NOTIFICATION_DIR
                / (
                    f"{account_id}_Config_{region}_ConfigSnapshot_{_stamp(moment)}_"
                    f"{config_snapshot_id}.json"
                ),
                json.dumps(
                    _notification(
                        account_id=account_id,
                        region=region,
                        moment=moment,
                        key=key,
                        config_snapshot_id=config_snapshot_id,
                    ),
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                written,
            )

        # The sets of the delivered document, extracted VERBATIM from the objects just
        # written: the arrays below are the delivered envelopes and the concatenation of
        # their `configurationItems`, so neither can claim a field the delivery does not
        # carry. They exist because the fidelity core reads a JSON artifact as text and the
        # delivered object is gzipped, and because two sets are nested -- see the docstring.
        _write_text(
            target / EXTRACTION_DIR / f"{ENVELOPE_SCOPE}.json",
            json.dumps(delivered_envelopes, indent=2, sort_keys=False) + "\n",
            written,
        )
        _write_text(
            target / EXTRACTION_DIR / f"{ITEM_SCOPE}.json",
            json.dumps(delivered_items, indent=2, sort_keys=False) + "\n",
            written,
        )
        # The relationship set has no delivered instance -- see `relationship_shape`.
        _write_text(
            target / SHAPE_DIR / f"{RELATIONSHIP_SCOPE}.json",
            json.dumps(relationship_shape(), indent=2, sort_keys=True) + "\n",
            written,
        )
        return written
