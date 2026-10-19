"""AWS VPC Flow Logs -> Amazon S3 renderer (rede).

Projects the canonical estate's NETWORK FLOWS (``model/network.py``) into the **54 record
fields** that ``specs/aws/vpc-flow-logs-s3.schema.json`` documents from *Flow log records*
(``https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html``), laid out as
the delivery *Flow log files* documents
(``https://docs.aws.amazon.com/vpc/latest/userguide/flow-logs-s3-path.html``).

This surface used to be faithful and EMPTY: the canonical model had no traffic, so every
record was the documented ``NODATA`` shape with seven columns filled. The estate now models
segments, interfaces and flows, and this renderer projects them -- so the record carries the
traffic it exists to describe.

WHAT IS DELIVERED, AND WHERE
----------------------------
One FLOW LOG per LOG RESOURCE the model names (``NetworkFlow.log_resource_id``). For AWS the
builder sets that field to the ENI id (``eni-...``), so the delivery is an
interface-level flow log -- one of the three targets AWS documents (VPC, subnet, ENI), and
the one the model's own field points at. A VPC-level log would aggregate several interfaces
per object; choosing that instead would ignore the field that says which resource produces
the log. The flow log's own id is DERIVED (``fl-`` + 17 lowercase hex from the log
resource), because the estate carries no flow-log resource and the published file-name
template needs one: ``TODO-verificar`` -- a derived id **in** the documented shape (the
official example shows ``fl-1234abcd``), NOT an AWS-issued identifier, the same discipline
``model/identity.py::capacity_reservation_id`` follows.

Objects land on the DEFAULT (non-Hive, non-hourly) documented path template, with the
optional prefix this module names (the template's ``bucket-and-optional-prefix`` is the
consumer's)::

    {prefix}/AWSLogs/{account-id}/vpcflowlogs/{region}/{year}/{month}/{day}/
        {account-id}_vpcflowlogs_{region}_{flow-log-id}_{YYYYMMDDTHHmmZ}_{hash}.log.gz
        {account-id}_vpcflowlogs_{region}_{flow-log-id}_{YYYYMMDDTHHmmZ}_{hash}.parquet

``region`` is the region of the INTERFACE the traffic was recorded on -- the documented
meaning of the field -- and ``month``/``day`` are zero-padded. The two official pages publish
placeholder names and no example path for flow logs (the AWS Config page is the one that
shows unpadded ``/2016/9/27/``, for its own surface), so the padding is this renderer's
choice, recorded as such instead of presented as a citation.

ONE OBJECT PER (FLOW LOG, AGGREGATION WINDOW)
---------------------------------------------
The page fixes the cadence: files are published *"at 5-minute intervals"* and each record
covers an aggregation interval of at most 10 minutes. The windows come from the FLOWS
themselves (``NetworkFlow.window_start``/``window_end``) and are never recomputed here, so
the renderer cannot hold a second opinion about when traffic happened; a window with no flow
produces no object. Today the builder covers the final hour of the simulated window (12
five-minute windows, ``generate/estate_builder.py::FLOW_WINDOWS``).

WHAT EACH FIELD PROJECTS
------------------------
Every value below is a model field; nothing is derived from a plausible-looking string.

* ``version`` -- derived from the emitted field set, per the documented rule (*"If you use a
  custom format, the version is the highest version among the specified fields"*). The
  format includes v11 fields, so the value is :data:`_FORMAT_VERSION` = 11.
* ``account-id`` -- ``NetworkFlow.account_id``, the account that owns the traffic.
* ``interface-id`` -- ``NetworkFlow.log_resource_id``, the interface the traffic was recorded
  on.
* ``srcaddr`` / ``dstaddr`` -- ``NetworkFlow.src_ip`` / ``dst_ip``, the interface-level
  addresses the flow carries. ``0.0.0.0`` is the model's own marker for an end outside the
  estate (``FLOW_ABSENT_ADDRESS``), passed through unchanged.
* ``srcport`` / ``dstport`` / ``protocol`` -- the flow's ports and its IANA protocol number,
  which is exactly the unit AWS documents (6 TCP, 17 UDP, 1 ICMP): no conversion.
* ``packets`` / ``bytes`` -- the flow's counters.
* ``start`` / ``end`` -- ``window_start`` / ``window_end`` as Unix seconds, the documented
  unit.
* ``action`` -- the documented literal pair, mapped from the model's own decision
  (``allowed`` -> ``ACCEPT``, ``denied`` -> ``REJECT``, :data:`_ACTION`). An unmapped
  decision fails closed rather than being written out untranslated.
* ``flow-direction`` -- ``NetworkFlow.direction``; the model's canonical literals
  (``ingress``/``egress``) ARE the documented ones, so no mapping is needed.
* ``log-status`` -- ``OK``, the documented literal for an interval whose data is logging
  normally. ``NODATA`` means *"no network traffic ... during the aggregation interval"*, and
  a record exists here only because the model holds a flow in that interval: emitting
  ``NODATA`` beside real counters would contradict the record.
* ``vpc-id`` / ``subnet-id`` -- the segment the flow belongs to
  (``NetworkSegment.segment_id`` / ``subnet_id``; for AWS the native ``vpc-...`` and
  ``subnet-...`` ids).
* ``region`` -- the region of the interface the traffic was recorded on
  (``NetworkInterface.region_id``), not the segment's.
* ``instance-id`` -- the EC2 instance id of the interface's OWNER, when that owner is an
  ``ec2_instance`` (``NetworkInterface.resource_uuid`` -> ``Resource`` ->
  ``model/identity.py::aws_resource_id``). The documented field is *"the ID of the instance
  that's associated with network interface for which the traffic is recorded"*, which is
  exactly this binding; an interface owned by any other type (RDS, NAT gateway, load
  balancer, EKS, ECS -- all requester-managed ENIs) emits nothing, which is the same absence
  AWS itself returns there.
* ``encryption-status`` -- ``NetworkFlow.encryption``, the field the model documents as the
  AWS encryption status, validated against the documented ``0|1|2|3`` domain
  (:data:`_ENCRYPTION_STATUS`). The builder fills it with ``None`` on every AWS row today,
  so the column ships empty; the projection is here so that the day it is filled it cannot
  reach the artifact out of domain or untranslated.

WHAT STAYS EMPTY, AND WHY (35 columns)
--------------------------------------
Each emptiness is a gap in the canonical model, not a formatting choice:

* no packet-level vs interface-level distinction: ``pkt-srcaddr``/``pkt-dstaddr`` would
  duplicate ``srcaddr``/``dstaddr`` while claiming the NAT/pod-level original the model does
  not track; ``pkt-src-aws-service``/``pkt-dst-aws-service`` would classify an address
  against the AWS IP ranges, which no model table holds;
* no address family: ``type`` (``IPv4``/``IPv6``/``EFA``) has no model field, and inferring
  it from the shape of an address string would derive a fact from a format;
* no flags and no path: ``tcp-flags`` and ``traffic-path`` are not modelled;
* no interface-type vocabulary: ``interface-type``/``next-hop-interface-type`` are a closed
  list (``nat_gateway``, ``network_load_balancer``, ...) that neither the catalog nor the
  network model carries -- mapping a resource type onto it would be inventing vocabulary;
* no next hop: the five ``next-hop-*`` columns;
* no zone or sublocation: ``az-id``, ``sublocation-type``, ``sublocation-id``;
* no ECS task and no Auto Scaling group: the nine ``ecs-*`` columns and the two
  ``asg-tag*``;
* no TAG binding at the interface: the model attaches tags to the RESOURCE, not to the
  interface, and the tag fields are defined by the flow log's ``TagFieldSpecifications``
  (which the spec itself registers as an unpublished object schema). The six tag columns
  stay empty rather than projecting the instance's tags as if they were interface tags;
* ``resource-id`` names a REGIONAL NAT GATEWAY, a construct the model does not have;
* ``reject-reason`` accepts only ``BPA`` and ``EC``: a flow the model marks ``denied`` was
  rejected by a security group, which is neither, and the page says any other reason is
  rendered ``-``. Emitting a reason here would claim one the documentation does not define.

MODEL GAPS WORTH NAMING (reported, not worked around)
-----------------------------------------------------
The builder creates ONE segment per (provider, scope) -- one VPC per AWS account -- while
that account's resources sit in three regions. An AWS VPC is regional, so a record whose
interface lives in another region still carries the scope's ``vpc-id``/``subnet-id`` here,
because those are the ids the model attaches to that interface's segment. The renderer
projects the model's own values and does not invent a second VPC; the fix belongs in the
builder (one segment per scope AND region), and this renderer needs no change when it
arrives.

The other named gaps: no per-interface tags, no interface-type vocabulary, no address
family, no AZ, no ECS/ASG and no next hop (all listed above), and ``encryption`` (declared by
the model as the AWS status) is filled with ``None`` on every row.

TWO FORMATS, ONE NAMING DIVERGENCE
----------------------------------
The page documents two formats -- ``Text`` (the default) and ``Parquet`` -- and publishes
**one** file-name template ending in ``.log.gz`` for log files, with no Parquet-specific
extension. Both are emitted: the TEXT object keeps the template verbatim (``.log.gz``,
gzip, fields separated by a single space, no header row -- the documentation never mentions
one), and the PARQUET object is named ``..._{hash}.parquet``, because naming a columnar
payload ``.log.gz`` would make the two deliveries indistinguishable and the page publishes no
Parquet name to follow instead. That is also the reason the fidelity check can read the
artifact at all (``fidelity.artifacts.columns_of`` reads ``.parquet``/``.csv``/``.json``; a
gzipped stream with a ``.log`` suffix is not one of them). The column names are the
documented field names, which is the only mapping that keeps one name per documented field.

``TODO-verificar`` (to be recorded in ``docs/synthetic-clouds/UNVERIFIED.md`` -- the file
``focus_aws`` cites as the registry, which does not exist in this checkout): the Parquet
object's extension, the Arrow schema, the derived flow-log id, and the file-name hash
algorithm (the page publishes the template but not the hash's origin).
"""

from __future__ import annotations

import gzip
import hashlib
import io
from datetime import datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from tools.synthetic_clouds.fidelity.spec import SurfaceSpec, load_spec
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.identity import aws_resource_id
from tools.synthetic_clouds.model.network import (
    DECISION_ALLOWED,
    DECISION_DENIED,
    NetworkFlow,
    NetworkInterface,
    NetworkSegment,
)
from tools.synthetic_clouds.model.resource import Resource
from tools.synthetic_clouds.render.base import RenderError

# The surface this renderer produces, as ``specs/aws/vpc-flow-logs-s3.schema.json`` names it.
SURFACE = "aws/vpc-flow-logs-s3"

# The provider this renderer projects: the operational scope key, not the display name.
_PROVIDER_AWS = "aws"

# The cited specification: the source of truth for this surface.
SPEC_PATH = Path(__file__).resolve().parents[3] / "specs" / "aws" / "vpc-flow-logs-s3.schema.json"

# The rendered tree's directory under ``out_dir`` -- the registered-renderer-name
# convention ``cur2_aws``, ``gcp_rest_fixtures`` and ``gcp_bigquery_topology`` follow.
RENDER_DIR = "vpc_flow_logs"

# The template's leading ``bucket-and-optional-prefix`` is the CONSUMER's choice, like the
# export name and prefix ``focus_aws``/``cur2_aws`` name for the Data Export surface.
S3_PREFIX = "vpc-flow-logs"

# The object suffixes: the text one is the template's own, the Parquet one is this
# renderer's decision (see the module docstring).
TEXT_SUFFIX = ".log.gz"
PARQUET_SUFFIX = ".parquet"

# The documented absent-value marker for the TEXT format: *"If a field is not applicable or
# could not be computed for a specific record, the record displays a '-' symbol for that
# entry."* The Parquet object carries a typed NULL instead, because a column typed INT_32
# cannot hold a hyphen.
ABSENT_MARKER = "-"

# The documented ``log-status`` literal for an interval whose data is logging normally.
LOG_STATUS_OK = "OK"

# The derived ``version`` value: the highest version among the specified fields. The emitted
# custom format contains the v11 tag/next-hop/interface-type fields, so the table rule gives
# 11 (see the module docstring).
_FORMAT_VERSION = 11

#: The model's canonical decision -> the documented ``action`` literal. Both literals of the
#: documented domain (``ACCEPT``/``REJECT``) are reachable, and an unknown decision is an
#: error rather than a value written out untranslated.
_ACTION: dict[str, str] = {
    DECISION_ALLOWED: "ACCEPT",
    DECISION_DENIED: "REJECT",
}

#: The documented ``encryption-status`` domain (0=not encrypted ... 3=nitro+application).
_ENCRYPTION_STATUS: dict[str, int] = {"0": 0, "1": 1, "2": 2, "3": 3}

# The model facts this renderer is allowed to project. Any other populated column would be a
# value the canonical model does not carry -- :func:`_require_columns` fails closed on it.
_PROJECTED: frozenset[str] = frozenset(
    {
        "version",
        "account-id",
        "interface-id",
        "srcaddr",
        "dstaddr",
        "srcport",
        "dstport",
        "protocol",
        "packets",
        "bytes",
        "start",
        "end",
        "action",
        "log-status",
        "vpc-id",
        "subnet-id",
        "region",
        "instance-id",
        "flow-direction",
        "encryption-status",
    }
)

# The documented Parquet data type per spec ``type``. The page fixes a Parquet type per field
# (INT_32 / INT_64 / STRING) and the spec's ``type`` mirrors it; an unmapped type fails
# closed rather than being guessed.
_ARROW_TYPES: dict[str, pa.DataType] = {
    "integer": pa.int32(),
    "long": pa.int64(),
    "string": pa.string(),
}


def specification() -> SurfaceSpec:
    """Load the cited specification for ``aws/vpc-flow-logs-s3``."""
    return load_spec(SPEC_PATH)


#: Colunas OBRIGATORIAS da spec que saem VAZIAS, com o motivo. O teste golden prova que esta
#: declaracao e EXATA nos dois sentidos: uma coluna obrigatoria sem valor em nenhum artefato
#: precisa estar aqui, e um nome aqui nao pode ter valor em lugar nenhum. Vazio nesta
#: superficie: as 14 colunas do formato padrao (as unicas obrigatorias) carregam valor.
REQUIRED_EMPTY_GAPS: dict[str, str] = {}


def _columns_of_spec() -> tuple[str, ...]:
    """Return the spec's column names in documentation order, refusing to drop one.

    Every documented column has a published type, a verified status, the official URL and a
    declarative evidence, so all 54 BELONG to the file. A column the documentation describes
    without contracting it must never reach an artifact, and a documented column must never
    be dropped: both directions are hard errors here.
    """
    spec = specification()
    refused = tuple(column.name for column in spec.columns if not column.belongs_to_schema)
    if refused:
        raise RenderError(
            f"vpc_flow_logs: a especificacao {spec.surface} marcou colunas documentadas como fora do "
            f"formato: {list(refused)}. O registro precisa das {len(spec.columns)} colunas publicadas."
        )
    return tuple(column.name for column in spec.columns)


# The 54 columns, in the documentation's own order -- derived, not retyped.
_COLUMNS: tuple[str, ...] = _columns_of_spec()

# Columns that belong to the file and may never receive a value (``evidence: null-empty``).
# Empty for this surface: every field is generatable, so the emptiness this renderer produces
# is a MODEL gap (documented in the docstring), not a documentation claim.
_NULL_EMPTY: frozenset[str] = specification().null_empty_names


def _arrow_types_of_spec() -> dict[str, pa.DataType]:
    """Return every documented column's Parquet type, failing closed on an unmapped one.

    The page fixes a Parquet data type PER FIELD (INT_32 / INT_64 / STRING) and the spec's
    ``type`` mirrors it; a field whose documented type has no mapping here is an error, not a
    column to guess.
    """
    spec = specification()
    types: dict[str, pa.DataType] = {}
    for column in spec.columns:
        if column.type is None or column.type not in _ARROW_TYPES:
            raise RenderError(
                f"vpc_flow_logs: coluna {column.name!r} sem tipo Parquet documentado ({column.type!r})"
            )
        types[column.name] = _ARROW_TYPES[column.type]
    return types


_ARROW_TYPE_BY_COLUMN: dict[str, pa.DataType] = _arrow_types_of_spec()


class _AwsNetwork:
    """The AWS slice of the network model, with its foreign keys resolved.

    Built once per render. Every lookup fails closed on a missing referent: the gate already
    refuses orphans (P2), and a renderer that silently invented a missing segment or
    interface would hide exactly the defect the gate exists to catch.
    """

    def __init__(self, estate: CanonicalEstate) -> None:
        self.segments: dict[str, NetworkSegment] = {
            segment.segment_uuid: segment for segment in estate.network_segments
        }
        self.segments_by_id: dict[str, NetworkSegment] = {
            segment.segment_id: segment for segment in estate.network_segments
        }
        self.interfaces_by_id: dict[str, NetworkInterface] = {
            interface.interface_id: interface for interface in estate.network_interfaces
        }
        self.resources: dict[str, Resource] = {
            resource.identity.uuid: resource for resource in estate.resources
        }
        self.flows: list[NetworkFlow] = self._aws_flows(estate)

    def _aws_flows(self, estate: CanonicalEstate) -> list[NetworkFlow]:
        """The estate's AWS flows, in deterministic order (log resource, window, flow id)."""
        flows: list[NetworkFlow] = []
        for flow in estate.network_flows:
            segment = self.segments.get(flow.segment_uuid)
            if segment is None:
                raise RenderError(
                    f"vpc_flow_logs: fluxo {flow.flow_id} referencia segmento inexistente "
                    f"({flow.segment_uuid})"
                )
            if segment.provider == _PROVIDER_AWS:
                flows.append(flow)
        return sorted(flows, key=lambda flow: (flow.log_resource_id, flow.window_start, flow.flow_id))

    def segment_of(self, flow: NetworkFlow) -> NetworkSegment:
        """The segment that carries ``flow`` (its VPC and its subnet)."""
        return self.segments[flow.segment_uuid]

    def logged_interface(self, flow: NetworkFlow) -> NetworkInterface | None:
        """The interface the traffic was recorded on, when the model names one.

        ``NetworkFlow.log_resource_id`` is "the id of the resource that produces the log
        (interface or segment)", so an AWS flow whose log resource is not an interface
        returns ``None`` and the caller falls back to the segment.
        """
        return self.interfaces_by_id.get(flow.log_resource_id)

    def region_of(self, flow: NetworkFlow) -> str:
        """The region that contains the interface the traffic was recorded on.

        The documented ``region`` field is about the INTERFACE, not the segment, so the
        interface wins; a flow logged by the segment itself falls back to the segment's
        region, and a log resource that is neither fails closed.
        """
        interface = self.logged_interface(flow)
        if interface is not None:
            return interface.region_id
        segment = self.segments_by_id.get(flow.log_resource_id)
        if segment is not None:
            return segment.region_id
        raise RenderError(
            f"vpc_flow_logs: fluxo {flow.flow_id} tem log_resource_id desconhecido "
            f"({flow.log_resource_id!r}): nao e interface nem segmento do estado"
        )

    def instance_id_of(self, flow: NetworkFlow) -> str | None:
        """The instance id of the interface's owner, when that owner is an EC2 instance.

        The documented field is the id of the instance associated with the interface the
        traffic was recorded on. An interface owned by any other catalogued type is a
        requester-managed ENI (RDS, NAT gateway, load balancer, EKS, ECS), where AWS itself
        returns no instance id -- so only an ``ec2_instance`` owner yields one.
        """
        interface = self.logged_interface(flow)
        if interface is None:
            return None
        resource = self.resources.get(interface.resource_uuid)
        if resource is None or resource.resource_type != "ec2_instance":
            return None
        return aws_resource_id(resource.resource_type, resource.identity.uuid)


def _action(flow: NetworkFlow) -> str:
    """Return the documented ``action`` literal of the model's own decision."""
    try:
        return _ACTION[flow.decision]
    except KeyError:
        raise RenderError(
            f"vpc_flow_logs: fluxo {flow.flow_id} tem decisao fora do dominio canonico: {flow.decision!r}"
        ) from None


def _encryption_status(flow: NetworkFlow) -> int | None:
    """Return ``encryption-status`` from the model field, validated against ``0|1|2|3``.

    The builder fills ``NetworkFlow.encryption`` with ``None`` on every AWS row today, so
    the column ships empty; validating the literal here means the day it is filled it cannot
    reach the artifact out of domain or untranslated.
    """
    if flow.encryption is None:
        return None
    try:
        return _ENCRYPTION_STATUS[flow.encryption]
    except KeyError:
        raise RenderError(
            f"vpc_flow_logs: fluxo {flow.flow_id} tem encryption fora do dominio documentado "
            f"(0-3): {flow.encryption!r}"
        ) from None


def _flow_log_id(seed: int, log_resource_id: str) -> str:
    """Return the derived flow-log id of a log resource, in the documented ``fl-`` shape.

    ``TODO-verificar``: DERIVED, in the documented shape, NOT an AWS-issued identifier -- the
    estate models no flow-log resource and the published file-name template needs one.
    Following ``model/identity.py::capacity_reservation_id``, the value is a function of
    ``(seed, log resource)`` only, so the same interface always yields the same file names.
    """
    digest = hashlib.sha256(f"{seed}:vpc-flow-log:{log_resource_id}".encode()).hexdigest()
    return f"fl-{digest[:17]}"


def _window_stamp(window_start: datetime) -> str:
    """Return the documented ``YYYYMMDDTHHmmZ`` window token of the file name."""
    return window_start.strftime("%Y%m%dT%H%M")


def _hash_suffix(seed: int, flow_log_id: str, window_start: datetime) -> str:
    """Return the file name's trailing hash.

    ``TODO-verificar``: the page publishes the file-name template but not the origin or
    length of ``hash`` (the spec's ``unverified`` list registers the gap). What is emitted is
    this package's own digest of ``(seed, flow log, window)`` -- deterministic, visibly not
    presented as AWS's algorithm.
    """
    payload = f"{seed}:{flow_log_id}:{window_start.isoformat()}"
    return hashlib.sha256(payload.encode()).hexdigest()[:8]


def s3_key(
    *,
    account_id: str,
    region: str,
    window_start: datetime,
    flow_log_id: str,
    digest: str,
    extension: str = TEXT_SUFFIX,
    prefix: str = S3_PREFIX,
) -> str:
    """Return the S3 key of one delivered object.

    The default (non-Hive, non-hourly) path template plus the documented file-name template;
    ``extension`` selects the text (``.log.gz``, the template's own) or the Parquet object
    (see the module docstring for that naming decision).
    """
    name = f"{account_id}_vpcflowlogs_{region}_{flow_log_id}_{_window_stamp(window_start)}Z_{digest}{extension}"
    return (
        f"{prefix}/AWSLogs/{account_id}/vpcflowlogs/{region}/"
        f"{window_start.year:04d}/{window_start.month:02d}/{window_start.day:02d}/{name}"
    )


def _record(flow: NetworkFlow, network: _AwsNetwork) -> dict[str, Any]:
    """Return the 54-field record of one modelled flow.

    The projected columns are the ones the module docstring lists, each with its model
    source; every other column is ``None`` (a typed NULL in Parquet, the documented ``-``
    marker in text). Nothing here is defaulted to a plausible value.
    """
    segment = network.segment_of(flow)
    return {
        "version": _FORMAT_VERSION,
        "account-id": flow.account_id,
        "interface-id": flow.log_resource_id,
        "srcaddr": flow.src_ip,
        "dstaddr": flow.dst_ip,
        "srcport": flow.src_port,
        "dstport": flow.dst_port,
        "protocol": flow.protocol_number,
        "packets": flow.packets,
        "bytes": flow.bytes,
        "start": int(flow.window_start.timestamp()),
        "end": int(flow.window_end.timestamp()),
        "action": _action(flow),
        "log-status": LOG_STATUS_OK,
        "vpc-id": segment.segment_id,
        "subnet-id": segment.subnet_id,
        # The FK resolves to the interface's owner; a non-EC2 owner emits nothing, because a
        # requester-managed ENI has no instance to name.
        "instance-id": network.instance_id_of(flow),
        # GAP: no TCP flag data is modelled.
        "tcp-flags": None,
        # GAP: the model carries no address family, and deriving one from the shape of an
        # address string would derive a fact from a format.
        "type": None,
        # GAP: the model carries one address pair per flow -- the interface-level one -- and
        # does not distinguish a packet-level (original) address behind a NAT or a pod.
        "pkt-srcaddr": None,
        "pkt-dstaddr": None,
        "region": network.region_of(flow),
        # GAP: no Availability Zone id, and no sublocation (Wavelength/Outpost/Local Zone).
        "az-id": None,
        "sublocation-type": None,
        "sublocation-id": None,
        # GAP: no classification of an address against the AWS IP ranges.
        "pkt-src-aws-service": None,
        "pkt-dst-aws-service": None,
        "flow-direction": flow.direction,
        # GAP: the path the egress traffic takes is not modelled.
        "traffic-path": None,
        # GAP: no ECS task construct (the estate's ecs_cluster is a cluster, not a task).
        "ecs-cluster-arn": None,
        "ecs-cluster-name": None,
        "ecs-container-instance-arn": None,
        "ecs-container-instance-id": None,
        "ecs-container-id": None,
        "ecs-second-container-id": None,
        "ecs-service-name": None,
        "ecs-task-definition-arn": None,
        "ecs-task-arn": None,
        "ecs-task-id": None,
        # The documented domain is BPA|EC only, and a flow denied by a security group is
        # neither: the page says any other reason is rendered '-'.
        "reject-reason": None,
        # GAP: this field names a REGIONAL NAT GATEWAY, which the model does not have.
        "resource-id": None,
        "encryption-status": _encryption_status(flow),
        # GAP: tags are attached to the RESOURCE, not to the interface, and the tag fields
        # are defined by the flow log's TagFieldSpecifications (an unpublished object
        # schema). Projecting the instance's tags as interface tags would be a fiction.
        "instance-tag": None,
        "instance-tag-2": None,
        "interface-tag": None,
        "interface-tag-2": None,
        "asg-tag": None,
        "asg-tag-2": None,
        # GAP: the documented interface-type list (nat_gateway, network_load_balancer, ...)
        # exists in neither the catalog nor the network model.
        "interface-type": None,
        "next-hop-interface-id": None,
        "next-hop-subnet-id": None,
        "next-hop-az-id": None,
        "next-hop-vpc-id": None,
        "next-hop-interface-type": None,
    }


def _require_columns(record: dict[str, Any]) -> None:
    """Fail closed when a record is not exactly the emitted column set, or fills a gap.

    ``_record`` returns ONE literal dict, so checking a single record checks every record.
    Three failures are caught here:

    * a divergent field set -- the Parquet writer would silently drop a key that is not a
      column, which is the omission this guard exists to prevent;
    * a value in a column the spec marks ``null-empty`` (a column that belongs to the file
      and may never be filled) -- there is none on this surface, and the check is written
      against the spec's own set so it keeps holding if one appears; and
    * a value in a column OUTSIDE :data:`_PROJECTED` -- i.e. a value the canonical model
      does not carry. That is the fabrication rule of this package expressed in code.
    """
    fields = set(record)
    expected = set(_COLUMNS)
    if fields != expected:
        raise RenderError(
            "vpc_flow_logs: registro com campos diferentes das colunas emitidas: "
            f"sobram={sorted(fields - expected)} faltam={sorted(expected - fields)}"
        )
    filled = sorted(name for name in _NULL_EMPTY & fields if record[name] is not None)
    if filled:
        raise RenderError(f"vpc_flow_logs: colunas null-empty receberam valor: {filled}")
    invented = sorted(name for name in fields if record[name] is not None and name not in _PROJECTED)
    if invented:
        raise RenderError(
            "vpc_flow_logs: colunas preenchidas sem fonte no modelo canonico "
            f"(lacuna, nao valor): {invented}"
        )


def _text_line(record: dict[str, Any]) -> str:
    """Return one text-format record: the fields, space separated, absent as ``-``."""
    return " ".join(ABSENT_MARKER if record[name] is None else str(record[name]) for name in _COLUMNS)


def render_text_bytes(records: list[dict[str, Any]]) -> bytes:
    """Return the gzip of one text-format object: one line per record, no header row."""
    for record in records:
        _require_columns(record)
    body = "".join(_text_line(record) + "\n" for record in records)
    return gzip.compress(body.encode("utf-8"), mtime=0)


def render_parquet_bytes(records: list[dict[str, Any]]) -> bytes:
    """Return the Parquet bytes of ``records``, each column typed as the page documents.

    An absent value is a typed NULL, never a string ``"-"``: the page fixes INT_32/INT_64
    for the numeric fields, so a hyphen could not be stored there at all.
    """
    for record in records:
        _require_columns(record)
    arrays: dict[str, pa.Array] = {
        name: pa.array([record[name] for record in records], type=_ARROW_TYPE_BY_COLUMN[name])
        for name in _COLUMNS
    }
    sink = io.BytesIO()
    pq.write_table(
        pa.table(arrays),
        sink,
        version="2.6",
        compression="snappy",
        write_statistics=False,
    )
    return sink.getvalue()


def _objects_of_delivery(network: _AwsNetwork) -> list[tuple[str, datetime, list[NetworkFlow]]]:
    """Group the AWS flows into the objects the delivery publishes, in deterministic order.

    One object per (flow log, aggregation window): the flow log is the model's own
    ``log_resource_id`` and the window is the flow's own ``window_start``. Nothing is
    recomputed here, so the object boundaries are a projection of the model rather than a
    second opinion about when traffic happened.
    """
    grouped: dict[tuple[str, datetime], list[NetworkFlow]] = {}
    for flow in network.flows:
        grouped.setdefault((flow.log_resource_id, flow.window_start), []).append(flow)
    return [
        (log_resource_id, window_start, grouped[(log_resource_id, window_start)])
        for log_resource_id, window_start in sorted(grouped, key=lambda key: (key[0], key[1]))
    ]


def _write_object(path: Path, payload: bytes, written: list[Path]) -> None:
    """Write ``payload`` at ``path`` and record the object once."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    if path not in written:
        written.append(path)


class VpcFlowLogsRenderer:
    """Renders the canonical estate's AWS network flows to a VPC Flow Logs S3 tree."""

    name = "vpc_flow_logs"

    def render(self, estate: CanonicalEstate, out_dir: Path) -> list[Path]:
        """Write the delivery under ``out_dir/vpc_flow_logs/``; return written paths."""
        target = out_dir / RENDER_DIR
        written: list[Path] = []
        network = _AwsNetwork(estate)
        for log_resource_id, window_start, flows in _objects_of_delivery(network):
            records = [_record(flow, network) for flow in flows]
            flow_log_id = _flow_log_id(estate.seed, log_resource_id)
            digest = _hash_suffix(estate.seed, flow_log_id, window_start)
            account_id = flows[0].account_id
            region = network.region_of(flows[0])
            _write_object(
                target
                / s3_key(
                    account_id=account_id,
                    region=region,
                    window_start=window_start,
                    flow_log_id=flow_log_id,
                    digest=digest,
                    extension=TEXT_SUFFIX,
                ),
                render_text_bytes(records),
                written,
            )
            _write_object(
                target
                / s3_key(
                    account_id=account_id,
                    region=region,
                    window_start=window_start,
                    flow_log_id=flow_log_id,
                    digest=digest,
                    extension=PARQUET_SUFFIX,
                ),
                render_parquet_bytes(records),
                written,
            )
        return written
