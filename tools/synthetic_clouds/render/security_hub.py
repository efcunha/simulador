"""AWS Security Hub ASFF findings renderer (seguranca).

Projects the canonical estate's AWS native findings into the **96 documented ASFF
fields** of ``specs/aws/security-hub-asff.schema.json`` -- 46 top-level attributes,
12 members of ``Resources[]`` and 38 nested attribute paths.

WHAT THIS SURFACE IS, AND WHAT IT IS NOT (read this before trusting the file names)
-----------------------------------------------------------------------------------
The mechanism refutation is documented in the spec and is repeated here because the file
names must not imply otherwise: **AWS does not export ASFF to S3**. The native export
(``StartExportJobV2``) writes ``CSV`` or ``OCSF_JSON`` and nothing else -- ASFF is not a
value ``FindingsOutput.Format`` accepts, and ``SelectedFields`` speaks OCSF field paths,
not ASFF names. The only other documented path (an EventBridge custom action) publishes
no object layout, file name or schema at all. OCSF has no published schema in this spec
either (the spec's ``unverified`` list records both facts), so emitting an "export file"
would mean inventing a format.

What IS fully documented, field by field, is the ASFF finding itself: the format Security
Hub holds internally and accepts from a provider (``BatchImportFindings``). This renderer
therefore emits ASFF finding DOCUMENTS as fixtures -- the payload shape, not an S3
delivery, and no S3 path is invented::

    {render_dir}/findings.json    array of ASFF documents, one per AWS finding
    {render_dir}/resources.json   array of the ``Resources[]`` objects of those findings
    {render_dir}/nested.json      array of the findings' nested attributes, FLATTENED onto
                                  the specification's own dotted names (``Severity.Label``,
                                  ``Resources[].Details.AwsEc2Instance.ImageId``, ...)

The three files are three views of ONE document set: ``resources.json`` is the
concatenation of the findings' own ``Resources[]`` arrays and ``nested.json`` is the
projection of their nested values onto the documented paths, so neither can carry a fact
the finding does not -- and the test proves that by rebuilding both from ``findings.json``
rather than by trusting this module.

WHAT EACH FIELD PROJECTS, AND WHAT STAYS EMPTY
----------------------------------------------
The native finding (``model/native.py::NativeFinding``) carries: the product's own
finding id, the resource it is bound to, the provider, a native category, an UPPERCASE
severity, a native status, the day it was raised, the literal ``synthetic`` source and an
evidence map. Everything below is a projection of exactly that; a documented column with
no model source is emitted ``null`` -- never a plausible-looking string.

* ``Id`` -- the finding's own id (a deterministic UUIDv5, the model's product-specific
  identifier).
* ``AwsAccountId`` / ``AwsAccountName`` / ``Region`` -- the owning account of the resource
  the finding names (the finding's FK), the estate's account name WITHOUT the FinOps
  ``[SYNTH] `` storage marker (no Security Hub document carries it), and the resource's
  region.
* ``CreatedAt`` / ``UpdatedAt`` -- the day the finding was raised, at ``00:00:00.000Z``;
  the documented literal is ISO 8601 UTC with milliseconds and the model carries a DATE,
  so the time of day is the day boundary (the same convention ``cur2_aws._stamp_date``
  uses for a date-shaped model fact). The model has one date per finding, so both
  attributes carry it; ``TODO-verificar``: ASFF can distinguish the two instants and this
  estate cannot.
* ``SchemaVersion`` -- ``2018-10-08``, the only value the spec publishes.
* ``Severity`` -- ``Label`` and ``Original`` are the model's own severity (the native vocabulary
  is exactly ASFF's published literals, confirmed as a formal enum in ``API_Severity.html`` on
  2026-10-15); ``Normalized`` is the number **AWS publishes** for that label (LOW=1, MEDIUM=40,
  HIGH=70, CRITICAL=90), which is what the API returns after filling the field in.
  ``FindingProviderFields.Severity`` carries the same two facts: the model's severity IS
  what the provider supplied, and ASFF keeps the provider's copy beside the normalized one.
* ``RecordState`` -- ``ACTIVE`` for the model's ``status = "open"`` (the documented
  literal for a finding that is live), the closed-domain mapping ``cur2_aws`` also makes
  for its own two-literal column. ``Workflow.Status`` stays null: the native status
  vocabulary (``open``) does not intersect ASFF's (``NEW``/``NOTIFIED``/``RESOLVED``/
  ``SUPPRESSED``).
* ``Resources`` -- ONE item, the resource the finding's FK names. ``Id`` is the model's
  canonical resource id (``model/identity.py::aws_resource_id``, a DERIVED id in the
  documented shape -- ``TODO-verificar`` there), ``Region`` and ``Tags`` are the
  resource's own, ``Provider``/``Partition`` are the documented literals of the
  provider the model records (``aws`` -> ``AWS``/``aws``), ``Type`` comes from
  ``generate/type_catalog.py`` (the two examples the ASFF page names, and its own
  documented escape ``Other`` for every other token), and ``Tags`` is empty for the
  untagged subset. ``Id`` is null for the one AWS type the estate models as a cost line
  (``data_transfer``) because it has no object id to project.
* ``Resources[].Details.AwsEc2Instance`` -- the block the spec's ``asff-nested`` set
  enumerates, emitted for an EC2 instance the estate profiles with SEVEN of its fifteen
  members filled from the compute and network models: ``ImageId`` and ``LaunchedAt`` and
  ``Type`` (the AMI, the launch instant in the example's ``...T01:25:54Z`` form, and the
  instance type the catalog derives from the SKU), ``IpV4Addresses`` (the profile's private
  address, plus its public one when it has one), ``SubnetId``/``VpcId`` (the segment the
  profile names) and ``NetworkInterfaces`` -- whose ASFF object publishes EXACTLY ONE
  member, ``NetworkInterfaceId``, so the interface's MAC and address are not forced into it.
  The other eight members stay null (see the gaps).
* ``ProductFields`` -- the finding's own ``evidence_json`` map, stringified (a boolean
  becomes ``"true"``/``"false"``), which is where the model's ``synthetic``/
  ``rule`` markers live: ASFF defines this column as the solution-specific details that
  are not part of ASFF, which is exactly what the evidence map is.
* ``Title`` / ``Description`` / ``Types`` / ``GeneratorId`` / ``ProductName`` /
  ``CompanyName`` / ``FirstObservedAt`` / ``Confidence`` / ``Criticality`` -- the nine
  top-level attributes the canonical finding now carries. ``Title``/``Description`` and the
  two provenance strings are the model's own text (a model string that is empty is emitted
  as null, so absence is one thing in this file); ``Types`` is the model's documented
  ``namespace/category/classifier`` tuple; ``FirstObservedAt`` is the model's instant in the
  documented millisecond form (``2017-03-22T13:22:13.933Z``); and ``Confidence``/
  ``Criticality`` are the model's 0-100 integers, refused here if they ever fall outside the
  documented scale. ``Confidence``, ``Criticality`` and ``Types`` are ALSO projected into
  ``FindingProviderFields``: this estate IS the finding provider, so the values it holds are
  the provider-supplied ones ASFF keeps beside the normalized copies.

REAL GAPS -- the model does not carry these, so the columns ship null
--------------------------------------------------------------------
* ``ProductArn``: the ASFF ARN is built from ``product/company-id/product-id`` IDENTIFIERS,
  and the model carries the product and company NAMES and no ARN machinery
  (``model/identity.py`` records that AWS ARNs live in the external ``aws_sim.arns``).
  Minting ids out of display names would invent the identity the ARN has to state, so the
  one required attribute of this document that stays empty is this one.
* ``VerificationState`` and ``Workflow``/``WorkflowState``: the ASFF enums have no canonical
  counterpart in the model (its status vocabulary is ``open``), and ``WorkflowState`` and
  ``Network`` are retired in the ASFF anyway -- the spec says a retired key should appear only
  if historical data is modelled, and it is not.
* ``Resources[].Details.AwsEc2Instance``'s other EIGHT members: ``IamInstanceProfileArn``
  and ``KeyName`` and ``VirtualizationType`` and ``IpV6Addresses`` have no model field, and
  the four ``MetadataOptions.*`` paths belong to an object the model does not carry at all
  (``MetadataOptions`` itself is emitted null, which is why its four documented subpaths are
  null). The same facts are the gaps ``ec2_instances`` reports for its own surface.
* ``Resources[].Details`` for any resource that is NOT an EC2 instance: the spec enumerates
  members of ``AwsEc2Instance`` only, so the details object of another type would be a shape
  with no contract. Such a finding carries ``Type`` (from the catalog) and a null ``Details``.
* ``Owner``: ``ResourceOwner``'s members are not enumerated by the spec's nested set (the
  spec says its subobject enumeration is deliberately not exhaustive), so populating it
  would mean emitting names no consulted page enumerates.
* every remaining optional block -- ``Action``, ``Compliance``, ``Detection``,
  ``LastObservedAt``, ``Malware``, ``Network``, ``NetworkPath``, ``Note``, ``PatchSummary``,
  ``Process``, ``ProcessedAt``, ``RelatedFindings``, ``Remediation``, ``RiskAssessment``,
  ``Sample``, ``SourceUrl``, ``ThreatIntelIndicators``, ``Threats``,
  ``Vulnerabilities``, ``GeneratorDetails``: no construct in the estate corresponds to them.

``UserDefinedFields`` is the one exception, and it stopped being empty in 2026-10-15. The ASFF
publishes it as free-form "name-value pairs you can use to add your own data", and the consumer
of this artifact requires four facts the ASFF message has no member for -- ``evidence``,
``exposure``, ``impact`` and ``fingerprint``, all NOT NULL on its side. Rather than leave the
consumer to invent them, the producer carries them here under the consumer's own names, with the
content spelled out in :func:`_user_defined_fields`. The evidence itself was never missing: the
model's ``evidence_json`` already ships in ``ProductFields``.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any

from tools.synthetic_clouds.fidelity.spec import SurfaceSpec, load_spec
from tools.synthetic_clouds.generate.constants import PROVIDER_KEY_AWS
from tools.synthetic_clouds.generate.type_catalog import asff_type
from tools.synthetic_clouds.model.compute import InstanceProfile
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.identity import AWS_ID_PREFIXES, aws_resource_id
from tools.synthetic_clouds.model.native import NativeFinding
from tools.synthetic_clouds.model.network import NetworkInterface, NetworkSegment
from tools.synthetic_clouds.model.resource import Resource
from tools.synthetic_clouds.render.base import RenderError
from tools.synthetic_clouds.render.markers import unmarked_name

# The surface this renderer produces, as the spec names it.
SURFACE = "aws/security-hub-asff"

# The cited specification: the source of truth for this surface.
SPEC_PATH = Path(__file__).resolve().parents[3] / "specs" / "aws" / "security-hub-asff.schema.json"

# The rendered directory under ``out_dir``.
RENDER_DIR = "security_hub"

# The formats the documented S3 export accepts. ASFF is NOT among them, which is why this
# renderer emits ASFF documents as fixtures instead of claiming an object layout: see the
# module docstring and the spec's `delivery.format` (``CSV|OCSF_JSON``).
DOCUMENTED_EXPORT_FORMATS: tuple[str, ...] = ("CSV", "OCSF_JSON")

# The single published ASFF schema version.
SCHEMA_VERSION = "2018-10-08"

# The documented literals of the provider the model records (``aws``).
_PROVIDER_LITERAL = "AWS"
_PARTITION_LITERAL = "aws"

# The model's native status -> the documented ``RecordState`` literal. The native
# vocabulary carries ``open`` only (``model/native.py``), which is a live record.
_RECORD_STATE: dict[str, str] = {"open": "ACTIVE"}

# The sets of the cited specification, by name.
TOP_LEVEL_SCOPE = "asff-top-level"
RESOURCES_SCOPE = "asff-resources"
NESTED_SCOPE = "asff-nested"

# The model facts each set may project. A non-null value anywhere else is a value the
# canonical model does not carry -- :func:`_require_projection` fails closed on it.
_TOP_LEVEL_PROJECTED: frozenset[str] = frozenset(
    {
        "AwsAccountId",
        "AwsAccountName",
        "CompanyName",
        "Confidence",
        "CreatedAt",
        "Criticality",
        "Description",
        "FindingProviderFields",
        "FirstObservedAt",
        "GeneratorId",
        "Id",
        "ProductFields",
        "ProductName",
        "RecordState",
        "Region",
        "Resources",
        "SchemaVersion",
        "Severity",
        "Title",
        "Types",
        "UpdatedAt",
        # Entered this set on 2026-10-15, with a reason rather than by opening the gate:
        # ``UserDefinedFields`` is the ASFF's own free-form map, and every key it carries here is
        # a model fact -- ``category``, ``evidence_json``, ``types``, ``severity`` and the scales
        # ``confidence``/``criticality``. The consumer names differ from the model's field names
        # (``evidence`` vs ``evidence_json``), and that renaming is a NAMING decision, not a new
        # value: :func:`_user_defined_fields` says what each key holds.
        "UserDefinedFields",
    }
)
_RESOURCES_PROJECTED: frozenset[str] = frozenset(
    {"Id", "Type", "Details", "Partition", "Provider", "Region", "Tags"}
)
_NESTED_PROJECTED: frozenset[str] = frozenset(
    {
        "Severity.Label",
        "Severity.Original",
        "Severity.Normalized",
        "FindingProviderFields.Severity",
        # The provider-supplied scales and types: this estate IS the provider, so the same
        # model facts are projected into the block ASFF keeps beside the normalized ones.
        "FindingProviderFields.Confidence",
        "FindingProviderFields.Criticality",
        "FindingProviderFields.Types",
        # The seven members of ``Resources[].Details.AwsEc2Instance`` the compute and
        # network models back; the other eight paths of that block stay null.
        "Resources[].Details.AwsEc2Instance.ImageId",
        "Resources[].Details.AwsEc2Instance.IpV4Addresses",
        "Resources[].Details.AwsEc2Instance.LaunchedAt",
        "Resources[].Details.AwsEc2Instance.NetworkInterfaces",
        "Resources[].Details.AwsEc2Instance.SubnetId",
        "Resources[].Details.AwsEc2Instance.Type",
        "Resources[].Details.AwsEc2Instance.VpcId",
    }
)


def specification() -> SurfaceSpec:
    """Load the cited specification for ``aws/security-hub-asff``."""
    return load_spec(SPEC_PATH)


#: Colunas OBRIGATORIAS da spec que saem VAZIAS, com o motivo. O teste golden prova que esta
#: declaracao e EXATA nos dois sentidos: uma coluna obrigatoria sem valor em nenhum artefato
#: precisa estar aqui, e um nome aqui nao pode ter valor em lugar nenhum.
REQUIRED_EMPTY_GAPS: dict[str, str] = {
    "ProductArn": (
        "o ARN do ASFF e montado com os IDENTIFICADORES "
        "arn:partition:securityhub:region:account-id:product/company-id/product-id; o modelo "
        "carrega os NOMES do produto e da empresa e nenhuma maquinaria de ARN "
        "(model/identity.py registra que ARNs da AWS vivem no aws_sim.arns externo), e cunhar "
        "ids a partir de nomes de exibicao inventaria a identidade que o ARN afirma"
    ),
}


def _names_of(scope: str) -> tuple[str, ...]:
    """Return a set's column names in documentation order, refusing to drop one.

    A column the documentation describes without contracting it must never reach an
    artifact, and a documented column must never be dropped: both are hard errors.
    """
    columns = specification().columns_for(scope)
    refused = tuple(column.name for column in columns if not column.belongs_to_schema)
    if refused:
        raise RenderError(
            f"security_hub: o conjunto {scope!r} da especificacao {SURFACE} marcou colunas "
            f"documentadas como fora do formato: {list(refused)}"
        )
    return tuple(column.name for column in columns)


# The three sets, in documentation order -- derived, not retyped.
_TOP_LEVEL_COLUMNS: tuple[str, ...] = _names_of(TOP_LEVEL_SCOPE)
_RESOURCES_COLUMNS: tuple[str, ...] = _names_of(RESOURCES_SCOPE)
_NESTED_COLUMNS: tuple[str, ...] = _names_of(NESTED_SCOPE)

# Columns that belong to the file and may never receive a value (``evidence: null-empty``).
# Empty for this surface: the nulls this renderer emits are MODEL gaps, argued in the
# module docstring, not documentation claims.
_NULL_EMPTY: frozenset[str] = specification().null_empty_names


def _is_empty(value: Any) -> bool:
    """True when ``value`` is this artifact's shape for "no value" (never for zero)."""
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
            f"security_hub: {where} com campos diferentes do conjunto emitido: "
            f"sobram={sorted(fields - expected)} faltam={sorted(expected - fields)}"
        )
    filled = sorted(name for name in _NULL_EMPTY & fields if not _is_empty(record[name]))
    if filled:
        raise RenderError(f"security_hub: colunas null-empty receberam valor: {filled}")
    invented = sorted(name for name in fields if not _is_empty(record[name]) and name not in projected)
    if invented:
        raise RenderError(
            f"security_hub: {where} preencheu colunas sem fonte no modelo canonico "
            f"(lacuna, nao valor): {invented}"
        )


class _AsffModel:
    """The estate lookups one ASFF document needs, resolved by foreign key.

    Built once per render. Every lookup fails closed on a missing referent: the gate already
    refuses orphans (P2), and a renderer that silently invented a missing profile or segment
    would hide exactly the defect the gate exists to catch.
    """

    def __init__(self, estate: CanonicalEstate) -> None:
        self.resources: dict[str, Resource] = {
            resource.identity.uuid: resource for resource in estate.resources
        }
        self.profiles: dict[str, InstanceProfile] = {
            profile.resource_uuid: profile for profile in estate.instance_profiles
        }
        self.interfaces_by_uuid: dict[str, NetworkInterface] = {
            interface.interface_uuid: interface for interface in estate.network_interfaces
        }
        self.segments: dict[str, NetworkSegment] = {
            segment.segment_uuid: segment for segment in estate.network_segments
        }
        self.account_name: dict[str, str] = {
            account.account_id: unmarked_name(account.name)
            for org in estate.aws_orgs
            for account in org.accounts
        }

    def resource_of(self, finding: NativeFinding) -> Resource:
        """The resource a finding names; an orphan finding is an error, not a null."""
        resource = self.resources.get(finding.resource_uuid)
        if resource is None:
            raise RenderError(
                f"security_hub: finding {finding.finding_id} referencia recurso inexistente "
                f"({finding.resource_uuid})"
            )
        return resource

    def profile_of(self, resource: Resource) -> InstanceProfile | None:
        """The compute profile of ``resource``, when the estate models one."""
        return self.profiles.get(resource.identity.uuid)

    def interface_of(self, profile: InstanceProfile) -> NetworkInterface | None:
        """The interface the profile names, when the model resolves it."""
        if profile.interface_uuid is None:
            return None
        return self.interfaces_by_uuid.get(profile.interface_uuid)

    def segment_of(self, profile: InstanceProfile) -> NetworkSegment | None:
        """The segment the profile names, when the model resolves it."""
        if profile.segment_uuid is None:
            return None
        return self.segments.get(profile.segment_uuid)


def _millis(moment: datetime) -> str:
    """Return the documented ASFF instant: ISO 8601 UTC with milliseconds.

    The model's instants have second resolution, so the millisecond field is always
    ``000`` -- the exact representation of the value, not a rounded one.
    """
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _raised_at(raised_on: date) -> str:
    """Return the finding's day in the documented ASFF literal (ISO 8601 UTC, milliseconds).

    The model carries a DATE (``NativeFinding.raised_on``), so the time of day is the day
    boundary -- the same convention ``cur2_aws._stamp_date`` uses for a date-shaped model
    fact. ``TODO-verificar``: the real instant is not modelled.
    """
    return _millis(datetime.combine(raised_on, time(0, 0), tzinfo=UTC))


def _observed_at(moment: datetime | None) -> str | None:
    """Return ``FirstObservedAt`` from the model's instant, or null when there is none."""
    return None if moment is None else _millis(moment)


def _scale(value: int | None, field: str) -> int | None:
    """Return a 0-100 scale value from the model, refusing one out of the documented range.

    The gate already validates the model side; failing closed here too means a value outside
    the documented scale cannot reach an artifact even if it is built directly.
    """
    if value is None:
        return None
    if not 0 <= value <= 100:
        raise RenderError(f"security_hub: {field} fora da escala documentada 0-100: {value!r}")
    return value


def _text(value: str) -> str | None:
    """Return a model string, or null when the model has none.

    The model's text fields default to ``""``, which is the model's own "no text" -- an
    artifact column carries null for it rather than an empty string, so "absence" is one
    thing in this file instead of two.
    """
    return value or None


def _product_fields(evidence: dict[str, Any]) -> dict[str, str]:

    """Stringify the finding's evidence map into the documented ``map<string,string>``.

    ASFF's ``ProductFields`` is "solution-specific details that are not part of the
    defined ASFF", which is exactly what ``NativeFinding.evidence_json`` holds. A boolean
    becomes ``"true"``/``"false"`` (an ASFF map value is a string, and ``str(True)`` would
    write Python's spelling into a provider-shaped document); every other non-string value
    is serialized as compact JSON. Keys are sorted so the document is byte-stable.
    """
    fields: dict[str, str] = {}
    for key, value in evidence.items():
        if isinstance(value, bool):
            fields[str(key)] = "true" if value else "false"
        elif isinstance(value, str):
            fields[str(key)] = value
        else:
            fields[str(key)] = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return dict(sorted(fields.items()))


def _native_resource_id(resource: Resource | None) -> str | None:
    """Return the provider-native resource id, or ``None`` for the one modelled as a cost line.

    Extracted because TWO places must agree on it: the ``Resources[].Id`` the document publishes,
    and the ``fingerprint`` that identifies the finding. If the two expressions ever drifted, the
    fingerprint would key on an id the artifact does not show -- and nothing would catch it.
    """
    if resource is None:
        return None
    return (
        aws_resource_id(resource.resource_type, resource.identity.uuid)
        if resource.resource_type in AWS_ID_PREFIXES
        else None
    )


def _fingerprint(finding: NativeFinding, resource_id: str | None) -> str:
    """Return the content fingerprint a consumer keys its deduplication on.

    A consumer that lands one row per finding needs a value that means "the same finding, on the
    same resource" -- NOT the finding's own id, which would make the uniqueness constraint say
    "a row per emission" and create a duplicate every day for the same open finding.

    So it is a SHA-256 over the three facts that make a finding what it is: the resource it is
    about, the classification the provider gave it, and its severity. Status is deliberately NOT
    in the input -- an ARCHIVED finding must not hash differently from the ACTIVE one it was, or
    resolving it would silently create a second row. 64 hex characters, matching the
    ``String(64)`` the consumer's column declares.
    """
    entrada = "|".join(
        (
            resource_id or finding.resource_uuid,
            "/".join(finding.types),
            finding.severity,
        )
    )
    return hashlib.sha256(entrada.encode()).hexdigest()


def _user_defined_fields(finding: NativeFinding, resource_id: str | None) -> dict[str, str]:
    """Carry, under the consumer's own vocabulary, the four facts ASFF has no member for.

    ASFF publishes ``UserDefinedFields`` as "name-value pairs you can use to add your own data",
    with a published ceiling of 50 pairs, a 128-character key and a 1024-character value. It is
    the one place in the format where a producer may carry facts the schema does not model.

    That matters because the FinOps ``findings`` table requires ``evidence``, ``exposure``,
    ``impact`` and ``fingerprint`` as NOT NULL, and the ``AwsSecurityFinding`` message has no
    member that carries any of them. Without them, the only ways to land a row are to have the
    consumer invent the content or to change its schema -- and the producer is the one that knows
    the facts. So the producer names them here, in the consumer's words, and says exactly what
    each one is:

    * ``category`` -- the model's own native category, verbatim (``NETWORK``, ``IAM``, ``CONFIG``).
    * ``evidence`` -- the model's ``evidence_json``, the same content ``ProductFields`` carries.
    * ``exposure`` -- WHAT is exposed: the resource and the classification naming the exposure.
    * ``impact`` -- the IMPACT SCALE the model carries: severity, its documented normalized value,
      and the confidence/criticality the provider supplied. It is a scale, not a business impact
      estimate, and it is named that way on purpose.
    * ``fingerprint`` -- see :func:`_fingerprint`.

    Values are ``str``: an ASFF map value is a string. The two ceiling checks are the document's
    own limits, enforced here so a longer type list fails at render time instead of silently
    producing an artifact the consumer will reject.
    """
    exposicao = {
        "resource": resource_id or finding.resource_uuid,
        "types": list(finding.types),
    }
    impacto = {
        "severity": finding.severity,
        "severity_normalized": _SEVERITY_NORMALIZED_ASFF.get(finding.severity),
        "criticality": finding.criticality,
        "confidence": finding.confidence,
    }
    campos = {
        "category": finding.category,
        "evidence": json.dumps(finding.evidence_json, sort_keys=True, separators=(",", ":")),
        "exposure": json.dumps(exposicao, sort_keys=True, separators=(",", ":")),
        "impact": json.dumps(impacto, sort_keys=True, separators=(",", ":")),
        "fingerprint": _fingerprint(finding, resource_id),
    }
    for chave, valor in campos.items():
        if len(chave) > 128:
            raise RenderError(f"security_hub: chave de UserDefinedFields acima de 128: {chave!r}")
        if len(valor) > 1024:
            raise RenderError(f"security_hub: valor de UserDefinedFields acima de 1024 em {chave!r}")
    return dict(sorted(campos.items()))


#: ``Severity.Normalized`` -- os valores que a AWS publica para o preenchimento automatico
#: ("If you provide ``Label`` and don't provide ``Normalized``, then ``Normalized`` is set
#: automatically as follows"), lidos em ``API_Severity.html`` em 2026-10-15. Sao os numeros que o
#: proprio Security Hub escreve, nao uma escolha nossa dentro da faixa 0-100.
_SEVERITY_NORMALIZED_ASFF: dict[str, int] = {
    "INFORMATIONAL": 0,
    "LOW": 1,
    "MEDIUM": 40,
    "HIGH": 70,
    "CRITICAL": 90,
}


def _severity(severity: str) -> dict[str, Any]:
    """Return the ASFF ``Severity`` object projected from the model's own severity literal.

    ``Label`` and ``Original`` are the model's value: the native vocabulary is exactly ASFF's
    published literals, and it is what the provider reported.

    ``Normalized`` comes from AWS's own table (see ``_SEVERITY_NORMALIZED_ASFF``). It used to be
    null because the bands were not in any consulted page; they are now, and this surface
    describes the API's **answer**, in which Security Hub populates the field from ``Label``.
    Emitting the number AWS publishes is more faithful than emitting null.
    """
    return {
        "Label": severity,
        "Original": severity,
        "Normalized": _SEVERITY_NORMALIZED_ASFF.get(severity),
    }


def _launched_at(moment: datetime) -> str:
    """Return ``Details.AwsEc2Instance.LaunchedAt`` in the form the official example shows.

    The ASFF example writes ``"LaunchedAt": "2018-09-29T01:25:54Z"`` -- ISO 8601 UTC WITHOUT
    milliseconds, unlike the finding's own ``CreatedAt``/``UpdatedAt``.
    """
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ec2_details(resource: Resource, model: _AsffModel) -> dict[str, Any] | None:
    """Return the documented ``Details.AwsEc2Instance`` block, or ``None`` when there is none.

    The block exists only for an ``ec2_instance`` whose compute profile the estate models:
    for any other resource type the spec enumerates no member of the corresponding details
    object (it names ``AwsEc2Instance`` only), and emitting an empty object of a type whose
    members are unpublished would be a shape without a contract.

    The 15 members the spec's ``asff-nested`` set enumerates are ALL present; the seven with
    a model source are filled and the other eight stay null (see the module docstring).
    """
    if resource.resource_type != "ec2_instance":
        return None
    profile = model.profile_of(resource)
    if profile is None:
        return None
    interface = model.interface_of(profile)
    segment = model.segment_of(profile)
    addresses = [profile.private_ip] if profile.private_ip else []
    if profile.public_ip:
        addresses.append(profile.public_ip)
    return {
        "AwsEc2Instance": {
            # GAP: no IAM instance profile is modelled.
            "IamInstanceProfileArn": None,
            "ImageId": profile.image_id,
            "IpV4Addresses": addresses,
            # GAP: no IPv6 address is modelled.
            "IpV6Addresses": None,
            # GAP: no key pair is modelled.
            "KeyName": None,
            "LaunchedAt": _launched_at(profile.launch_time),
            # GAP: no metadata options are modelled (the four documented subfields stay null).
            "MetadataOptions": None,
            # The ASFF object publishes EXACTLY ONE member here -- ``NetworkInterfaceId``:
            # its API page (AwsEc2InstanceNetworkInterfacesDetails) lists no other, so the
            # interface's MAC and address are not forced into it.
            "NetworkInterfaces": (
                None if interface is None else [{"NetworkInterfaceId": interface.interface_id}]
            ),
            "SubnetId": None if segment is None else segment.subnet_id,
            "Type": profile.instance_type,
            # GAP: no virtualization type is modelled.
            "VirtualizationType": None,
            "VpcId": None if segment is None else segment.segment_id,
        }
    }


def _resource_item(resource: Resource | None, model: _AsffModel) -> dict[str, Any]:
    """Return the 12-field ASFF ``Resources[]`` item for the resource a finding names."""
    if resource is None:
        item: dict[str, Any] = {
            "Id": None,
            "Type": None,
            "ApplicationArn": None,
            "ApplicationName": None,
            "DataClassification": None,
            "Details": None,
            "Owner": None,
            "Partition": None,
            "Provider": None,
            "Region": None,
            "ResourceRole": None,
            "Tags": {},
        }
    else:
        item = {
            # The model's canonical id; null for the one type the estate models as a cost
            # line (``data_transfer``), which has no object id to project. Shared with the
            # ``fingerprint`` via ``_native_resource_id`` on purpose.
            "Id": _native_resource_id(resource),
            # The native type, in the vocabulary the ASFF page publishes: the two examples
            # it names, and its own documented escape ``Other`` for everything else
            # (``generate/type_catalog.py``). No name is deduced from the pattern.
            "Type": asff_type(resource.resource_type),
            "ApplicationArn": None,
            "ApplicationName": None,
            "DataClassification": None,
            # The ``AwsEc2Instance`` block the spec's nested set enumerates, for an EC2
            # instance the estate profiles; ``None`` for every other resource type, whose
            # details object members this spec does not publish.
            "Details": _ec2_details(resource, model),
            # GAP: ``ResourceOwner``'s members are not enumerated by the spec's nested set.
            "Owner": None,
            "Partition": _PARTITION_LITERAL,
            "Provider": _PROVIDER_LITERAL,
            "Region": resource.region_id,
            "ResourceRole": None,
            # Empty map for the untagged subset (FR-D2): the spec says to include the field
            # only for resources that have tags, and a fabricated entry is not an option.
            "Tags": dict(resource.tags),
        }
    _require_projection(item, _RESOURCES_COLUMNS, _RESOURCES_PROJECTED, "objeto Resources[]")
    return item


def _finding(
    finding: NativeFinding,
    resource: Resource | None,
    *,
    account_name: str,
    model: _AsffModel,
) -> dict[str, Any]:
    """Return the 46-field ASFF document for one AWS native finding."""
    record: dict[str, Any] = {
        "AwsAccountId": resource.parent_scope_id if resource is not None else None,
        "CreatedAt": _raised_at(finding.raised_on),
        "Description": _text(finding.description),
        "GeneratorId": _text(finding.generator_id),
        "Id": finding.finding_id,
        # GAP: no product/company IDENTITY (and no ARN) is modelled -- the model carries the
        # product and company NAMES, not the ``product/company-id/product-id`` segments the
        # ARN is built from, and minting ids from display names would invent them.
        "ProductArn": None,
        "Resources": [_resource_item(resource, model)],
        "SchemaVersion": SCHEMA_VERSION,
        "Severity": _severity(finding.severity),
        "Title": _text(finding.title),
        "Types": list(finding.types) or None,
        "UpdatedAt": _raised_at(finding.raised_on),
        "Action": None,
        "AwsAccountName": account_name,
        "CompanyName": _text(finding.company_name),
        "Compliance": None,
        "Confidence": _scale(finding.confidence, "Confidence"),
        "Criticality": _scale(finding.criticality, "Criticality"),
        "Detection": None,
        # The model's severity, confidence, criticality and types ARE what the provider
        # supplied -- this estate IS the provider -- so the same facts are projected into the
        # provider block ASFF keeps beside the normalized ones. ``RelatedFindings`` has no
        # model source.
        "FindingProviderFields": {
            "Confidence": _scale(finding.confidence, "FindingProviderFields.Confidence"),
            "Criticality": _scale(finding.criticality, "FindingProviderFields.Criticality"),
            "RelatedFindings": None,
            "Severity": _severity(finding.severity),
            "Types": list(finding.types) or None,
        },
        "FirstObservedAt": _observed_at(finding.first_observed_at),
        "GeneratorDetails": None,
        "LastObservedAt": None,
        "Malware": None,
        "Network": None,
        "NetworkPath": None,
        "Note": None,
        "PatchSummary": None,
        "Process": None,
        "ProcessedAt": None,
        "ProductFields": _product_fields(finding.evidence_json),
        "ProductName": _text(finding.product_name),
        "RecordState": _RECORD_STATE.get(finding.status, ""),
        "Region": resource.region_id if resource is not None else None,
        "RelatedFindings": None,
        "Remediation": None,
        "RiskAssessment": None,
        "Sample": None,
        "SourceUrl": None,
        "ThreatIntelIndicators": None,
        "Threats": None,
        "UserDefinedFields": _user_defined_fields(
            finding, _native_resource_id(resource)
        ),
        "VerificationState": None,
        "Vulnerabilities": None,
        # GAP: the native status vocabulary does not intersect ASFF's Workflow.Status.
        "Workflow": None,
        "WorkflowState": None,
    }
    _require_projection(record, _TOP_LEVEL_COLUMNS, _TOP_LEVEL_PROJECTED, f"finding {finding.finding_id}")
    return record


def nested_value(document: dict[str, Any], path: str) -> Any:
    """Return the value at a documented nested path, or ``None`` when the block is absent.

    ``Resources[]`` is the specification's own spelling for "the first item of the
    ``Resources`` array"; a finding here carries exactly one, because the model binds one
    resource to one finding (``NativeFinding.resource_uuid`` is a single FK).
    """
    current: Any = document
    for segment in path.split("."):
        if current is None:
            return None
        if segment == "Resources[]":
            items = current.get("Resources") if isinstance(current, dict) else None
            current = items[0] if items else None
            continue
        if not isinstance(current, dict):
            return None
        current = current.get(segment)
    return current


def _nested(finding_document: dict[str, Any]) -> dict[str, Any]:
    """Return one finding's nested attributes, flattened onto the documented paths."""
    record = {path: nested_value(finding_document, path) for path in _NESTED_COLUMNS}
    _require_projection(record, _NESTED_COLUMNS, _NESTED_PROJECTED, "atributos aninhados")
    return record


def _aws_findings(estate: CanonicalEstate) -> list[NativeFinding]:
    """The estate's AWS findings, in deterministic order."""
    return sorted(
        (finding for finding in estate.findings if finding.provider == PROVIDER_KEY_AWS),
        key=lambda finding: finding.finding_id,
    )


def _write_text(path: Path, text: str, written: list[Path]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if path not in written:
        written.append(path)


class SecurityHubAsffRenderer:
    """Renders the canonical estate's AWS findings as ASFF documents (API payload shape)."""

    name = "security_hub"

    def render(self, estate: CanonicalEstate, out_dir: Path) -> list[Path]:
        """Write the ASFF fixtures under ``out_dir/security_hub/``; return written paths."""
        target = out_dir / RENDER_DIR
        written: list[Path] = []
        model = _AsffModel(estate)

        findings: list[dict[str, Any]] = []
        resources: list[dict[str, Any]] = []
        nested: list[dict[str, Any]] = []
        for finding in _aws_findings(estate):
            resource = model.resource_of(finding)
            document = _finding(
                finding,
                resource,
                account_name=model.account_name.get(resource.parent_scope_id, ""),
                model=model,
            )
            findings.append(document)
            # The other two files are VIEWS of this one document set: the resource items it
            # already carries, and its nested attributes on the documented paths. Both are
            # accumulated in the same pass, so neither can drift from the finding.
            resources.extend(document["Resources"])
            nested.append(_nested(document))

        _write_text(
            target / "findings.json",
            json.dumps(findings, indent=2, ensure_ascii=False) + "\n",
            written,
        )
        _write_text(
            target / "resources.json",
            json.dumps(resources, indent=2, ensure_ascii=False) + "\n",
            written,
        )
        _write_text(
            target / "nested.json",
            json.dumps(nested, indent=2, ensure_ascii=False) + "\n",
            written,
        )
        return written
