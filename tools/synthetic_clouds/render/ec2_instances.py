"""Amazon EC2 ``DescribeInstances`` response renderer (instancias).

Projects the canonical estate's AWS EC2 instances into the **75 documented fields** of
``specs/aws/ec2-describe-instances.schema.json`` -- 3 top-level response elements, 5
members of ``Reservation``, the 61 members of the ``Instance`` object and the 6
documented request parameters.

THE FORMAT DECISION (stated, because the published one cannot be checked)
------------------------------------------------------------------------
``delivery.kind`` for this surface is **``read_api``**, not an export: EC2 publishes no
durable artifact of ``DescribeInstances``, and the API Reference publishes the response
as **XML** only -- no JSON property schema and no JSON example exist (the spec's section
2.2 and its ``unverified`` list both say so).

This renderer emits **JSON fixtures**, and the reasons are explicit:

1. the fidelity core measures an artifact through ``fidelity.artifacts.columns_of``, which
   reads Parquet, CSV and JSON -- not XML. A synthetic XML document could not be checked
   against the specification field by field, which is the whole point of the exercise;
2. the MEMBER NAMES the spec documents are SDK-notation names (``instanceId``,
   ``amiLaunchIndex``, ``TagSet.N``), not XML element names: the spec's section 5.1
   records that the official XML sample writes ``<blockDeviceMapping>`` where the object
   page documents ``BlockDeviceMapping.N``. Emitting JSON under the documented member
   names is therefore the one encoding in which "the artifact's fields == the spec's
   fields" is a meaningful assertion; and
3. the JSON member spelling is a **decision of this module, not a claim about AWS**: this
   is NOT presented as the published response encoding, and the XML divergence stays
   exactly where the spec put it.

What the API does document, and what this module therefore honours, is the STRUCTURE: a
response holds a ``reservationSet`` of reservations, each holding an ``InstancesSet`` of
instances; a container member ends in ``.N``; and ``Reservation.GroupSet.N`` is documented
as *"Not supported."* -- which is why it is emitted as an empty array rather than filled.

No S3 path, object name or partition is invented: a read API has no delivery layout, and
the one documented durable path to "EC2 instances in S3" is indirect (the AWS Config
configuration item), which ``render/aws_config_snapshot.py`` renders and which this
module does not duplicate.

WHAT IS EMITTED, AND WHERE
--------------------------
Four fixtures under ``{render_dir}/``, one per documented set, so each can be compared
against its own contract::

    {render_dir}/describe-instances-response.json   array of response envelopes, one per
                                                    (account, region) call
    {render_dir}/reservation.json                   array of the reservations of those calls
    {render_dir}/instance.json                      array of the Instance objects
    {render_dir}/request-parameters.json            the documented request parameters

A response envelope is per (account, region) because ``DescribeInstances`` is a regional
call: one account's instances in three regions are three responses, not one. Grouping by
``(account, region)`` is therefore a projection of the model's own scope, not a choice
about the provider's semantics.

WHAT EACH FIELD PROJECTS, AND WHAT STAYS EMPTY
----------------------------------------------
Three model sources feed this fixture: the canonical ``Resource`` (identity, account scope,
name, region, tags, catalog SKU, capacity reservation), the network model
(``NetworkInterface``, ``NetworkSegment``) and the compute model
(``model/compute.py::InstanceProfile`` -- the instance's own profile, coherent with the
interface of the same resource).

* ``instanceId`` -- the resource's canonical id,
  ``model/identity.py::aws_resource_id`` (a DERIVED id in the documented shape,
  ``TODO-verificar`` there; the same projection every other AWS surface makes -- see the
  divergence note at the end of this docstring);
* ``capacityReservationId`` -- the reservation the resource carries
  (``Resource.capacity_reservation.reservation_id``), the same fact ``focus_aws`` projects
  into FOCUS's ``CapacityReservationId``;
* ``imageId`` / ``instanceType`` / ``launchTime`` -- ``InstanceProfile.image_id``,
  ``instance_type`` (derived from the catalog SKU; ``None`` when the catalog does not say,
  which is why a non-instance attachment has none) and ``launch_time`` in the documented
  literal form (``ISO 8601 UTC`` with milliseconds, e.g. ``2018-05-08T16:46:19.000Z``);
* ``privateIpAddress`` / ``ipAddress`` -- ``InstanceProfile.private_ip`` and ``public_ip``
  (null for the majority of instances, which have no public address);
* ``instanceState`` -- the model's canonical state mapped onto the documented
  ``InstanceState`` object (``{"code": 16, "name": "running"}`` /
  ``{"code": 80, "name": "stopped"}``, :data:`_INSTANCE_STATE`). Both the codes and the
  names are the ones the ``InstanceState`` page publishes; an unmapped state fails closed;
* ``placement`` -- ``{"availabilityZone": InstanceProfile.zone}``, the AZ the model derives
  from the region (``us-east-1a``);
* ``subnetId`` / ``vpcId`` -- the segment the profile names
  (``NetworkSegment.subnet_id`` / ``segment_id``);
* ``NetworkInterfaceSet.N`` -- one item for the interface the compute profile names, with
  the five members the ``InstanceNetworkInterface`` page publishes
  (``networkInterfaceId``, ``macAddress``, ``privateIpAddress``, ``subnetId``, ``vpcId``);
* ``TagSet.N`` -- the resource's own tags;
* ``ownerId`` (Reservation) -- the account that owns the reservation;
* ``requestId`` -- the identifier of the CALL, minted deterministically per (account, region)
  by :func:`request_id` (UUIDv5 over a logical path, the project's identity primitive). It
  identifies the request, not a resource: the documentation publishes it as an opaque
  response id -- the spec's own example is a UUID -- and it correlates nothing a consumer
  holds, so minting it is the same discipline the other derived AWS ids follow;
  ``TODO-verificar``: the shape is the documented one, the entropy is this package's;
* ``reservationSet`` / ``InstancesSet.N`` -- the model's own grouping: one reservation per
  (account, region) carrying that call's instances;
* ``nextToken`` -- null, which is the documented value for "there are no more items to
  return": the fixture carries the estate's whole inventory in one page.

NESTED MEMBER SPELLING: THE RESPONSE FORM
-----------------------------------------
Every nested member above is spelled the way the EC2 API Reference spells it for a
RESPONSE, which the pages mark explicitly: ``Tag`` prints ``Key (request), key (response)``
and ``Placement`` prints ``AvailabilityZone (request), availabilityZone (response)``. A
``DescribeInstances`` fixture IS a response, so the fixture carries ``key``/``value``,
``code``/``name``, ``availabilityZone``, ``networkInterfaceId``, ``macAddress``,
``privateIpAddress``, ``subnetId`` and ``vpcId`` -- the same lowercase-first notation the
specification's own member names use (``instanceId``, ``amiLaunchIndex``). The spec does not
enumerate these members (its ``instance`` set names the containers ``TagSet.N``,
``instanceState``, ``placement`` and ``NetworkInterfaceSet.N``), so each one is cited to its
own page below rather than presented as a spec column.

REAL GAPS -- the model does not carry these, so the columns ship null
--------------------------------------------------------------------
* **The machine**: ``architecture``, ``virtualizationType``, ``hypervisor``, ``platform``,
  ``platformDetails``, ``bootMode``/``currentInstanceBootMode``, ``instanceLifecycle``,
  ``stateReason``, ``reason``, ``usageOperation``/``usageOperationUpdateTime``,
  ``monitoring``, ``ebsOptimized``, ``enaSupport``, ``sourceDestCheck``, ``tpmSupport``,
  ``sriovNetSupport``, ``cpuOptions``, ``enclaveOptions``, ``hibernationOptions``,
  ``maintenanceOptions``, ``metadataOptions``, ``networkPerformanceOptions``,
  ``privateDnsNameOptions``, ``capacityReservationSpecification``, ``operator``,
  ``clientToken``, ``kernelId``, ``ramdiskId``, ``rootDeviceName``, ``rootDeviceType``,
  ``amiLaunchIndex``, ``capacityBlockId``, ``outpostArn``, ``spotInstanceRequestId``,
  ``keyName``, ``iamInstanceProfile``, ``ElasticGpuAssociationSet.N`` and
  ``ElasticInferenceAcceleratorAssociationSet.N`` (deprecated and empty).
  ``rootDeviceName``/``rootDeviceType`` and ``BlockDeviceMapping.N`` deserve a note: the
  profile carries ``root_volume_size_gb``/``root_volume_type``, but the members that would
  carry them need a DEVICE NAME (and, for ``rootDeviceType``, a mapping from a volume type
  to the documented ``ebs``/``instance-store`` pair) that the model does not have; the size
  and type stay unprojected rather than under a guessed device;
* **the rest of the network**: ``ipv6Address``, ``dnsName``, ``privateDnsName``,
  ``GroupSet.N`` (the estate models ``security_group`` resources but NOT the association
  between an instance and one) and ``association``/``attachment``-style interface members;
* **the whole ``request-parameters`` set**: those six names belong to the REQUEST side of
  the action (the spec's section 3.4), and the estate models no captured request, so the
  fixture carries the documented names with null values. It is emitted rather than omitted so
  the documented request vocabulary is present and the gap is visible. NOTE the difference
  from ``requestId``: the IDENTIFIER of the call is minted (see :func:`request_id`), while the
  request's PARAMETERS are facts about a call nobody captured;
* ``reservationId`` and ``requesterId``: the estate carries no launch grouping and no
  launching principal, so a reservation has no id of its own -- and no ``r-`` id is minted,
  because ``model/identity.py`` gives an id only to types the estate models as objects.

DIVERGENCE TO REPORT: TWO DERIVATIONS FOR ONE INSTANCE ID
---------------------------------------------------------
``InstanceProfile.native_id`` derives the AWS id as ``i-`` + the first 17 hex of the
resource uuid, while ``model/identity.py::aws_resource_id`` -- the function this renderer,
the AWS Config renderer and the ASFF renderer all use -- derives it as ``i-`` + 17 hex of
``sha256("ec2_instance:" + uuid)``. The SAME instance therefore has two different ids in the
model, and the two disagree. This renderer keeps ``aws_resource_id`` so that ONE instance
has ONE id across the three AWS surfaces it emits; the reconciliation belongs in the model
(make ``InstanceProfile.native_id`` call ``aws_resource_id`` for AWS), not here.
"""

from __future__ import annotations

import json
from datetime import UTC
from pathlib import Path
from typing import Any

from tools.synthetic_clouds.determinism import identity_for
from tools.synthetic_clouds.fidelity.spec import SurfaceSpec, load_spec
from tools.synthetic_clouds.generate.constants import PROVIDER_KEY_AWS
from tools.synthetic_clouds.model.compute import STATE_RUNNING, STATE_STOPPED, InstanceProfile
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.identity import aws_resource_id
from tools.synthetic_clouds.model.network import NetworkInterface, NetworkSegment
from tools.synthetic_clouds.model.resource import Resource
from tools.synthetic_clouds.render.base import RenderError

# The surface this renderer produces, as the spec names it.
SURFACE = "aws/ec2-describe-instances"

# The cited specification: the source of truth for this surface.
SPEC_PATH = Path(__file__).resolve().parents[3] / "specs" / "aws" / "ec2-describe-instances.schema.json"

# The rendered directory under ``out_dir``.
RENDER_DIR = "ec2_instances"

# The encoding of the published response, as the spec's ``delivery.format`` states it, and
# the encoding of these fixtures. The two differ BY DECISION -- see the module docstring.
PUBLISHED_ENCODING = "xml"
FIXTURE_ENCODING = "json"

# The sets of the cited specification, by name.
RESPONSE_SCOPE = "describe-instances-response"
RESERVATION_SCOPE = "reservation"
INSTANCE_SCOPE = "instance"
REQUEST_SCOPE = "request-parameters"

#: The model's canonical instance state -> the documented ``InstanceState`` object. The
#: codes and names are the ones the object publishes (0 pending, 16 running, 32
#: shutting-down, 48 terminated, 64 stopping, 80 stopped); an unmapped state fails closed
#: rather than reaching the fixture untranslated.
_INSTANCE_STATE: dict[str, tuple[int, str]] = {
    STATE_RUNNING: (16, "running"),
    STATE_STOPPED: (80, "stopped"),
}

# The model facts each set may project. A non-null value anywhere else is a value the
# canonical model does not carry -- :func:`_require_projection` fails closed on it.
_RESPONSE_PROJECTED: frozenset[str] = frozenset({"requestId", "reservationSet"})
_RESERVATION_PROJECTED: frozenset[str] = frozenset({"ownerId", "InstancesSet.N"})
_INSTANCE_PROJECTED: frozenset[str] = frozenset(
    {
        "instanceId",
        "capacityReservationId",
        "imageId",
        "instanceType",
        "launchTime",
        "privateIpAddress",
        "ipAddress",
        "instanceState",
        "placement",
        "subnetId",
        "vpcId",
        "NetworkInterfaceSet.N",
        "TagSet.N",
    }
)
_REQUEST_PROJECTED: frozenset[str] = frozenset()


def specification() -> SurfaceSpec:
    """Load the cited specification for ``aws/ec2-describe-instances``."""
    return load_spec(SPEC_PATH)


#: Colunas OBRIGATORIAS da spec que saem VAZIAS, com o motivo. O teste golden prova que esta
#: declaracao e EXATA nos dois sentidos: uma coluna obrigatoria sem valor em nenhum artefato
#: precisa estar aqui, e um nome aqui nao pode ter valor em lugar nenhum. Vazio nesta
#: superficie desde que :func:`request_id` passou a cunhar o identificador da requisicao.
REQUIRED_EMPTY_GAPS: dict[str, str] = {}


def request_id(estate: CanonicalEstate, account_id: str, region: str) -> str:
    """Return the ``requestId`` of the ``DescribeInstances`` call of one (account, region).

    The field identifies the REQUEST, not a resource: the documentation publishes it as an
    opaque id carried by every successful response (the spec's own example is a UUID), and it
    correlates nothing a consumer holds. Minting it deterministically -- UUIDv5 over a logical
    path, ``determinism.identity_for``, the primitive every other identifier in this package
    comes from -- is the same discipline ``aws_resource_id`` and ``capacity_reservation_id``
    follow, and it is what makes the ONLY required column of this surface carry a value.

    One id per call, and a call here is one (account, region): ``DescribeInstances`` is a
    regional action, so one account's instances in three regions are three responses with
    three request ids.

    ``TODO-verificar``: DERIVED, NOT an AWS-issued request id. Its shape is the documented one
    (a UUID); its entropy is this package's.
    """
    return identity_for(estate.seed, f"describe-instances/{account_id}/{region}")


def _names_of(scope: str) -> tuple[str, ...]:
    """Return a set's column names in documentation order, refusing to drop one.

    A column the documentation describes without contracting it must never reach an
    artifact, and a documented column must never be dropped: both are hard errors.
    """
    columns = specification().columns_for(scope)
    refused = tuple(column.name for column in columns if not column.belongs_to_schema)
    if refused:
        raise RenderError(
            f"ec2_instances: o conjunto {scope!r} da especificacao {SURFACE} marcou colunas "
            f"documentadas como fora do formato: {list(refused)}"
        )
    return tuple(column.name for column in columns)


# The four sets, in documentation order -- derived, not retyped.
_RESPONSE_COLUMNS: tuple[str, ...] = _names_of(RESPONSE_SCOPE)
_RESERVATION_COLUMNS: tuple[str, ...] = _names_of(RESERVATION_SCOPE)
_INSTANCE_COLUMNS: tuple[str, ...] = _names_of(INSTANCE_SCOPE)
_REQUEST_COLUMNS: tuple[str, ...] = _names_of(REQUEST_SCOPE)

# Columns that belong to the file and may never receive a value (``evidence: null-empty``).
# Empty for this surface: the nulls this renderer emits are MODEL gaps, argued in the
# module docstring, not documentation claims.
_NULL_EMPTY: frozenset[str] = specification().null_empty_names


def _is_empty(value: Any) -> bool:
    """True when ``value`` is this fixture's shape for "no value" (never for zero)."""
    return value is None or value == "" or value == {} or value == []


def _require_projection(record: dict[str, Any], columns: tuple[str, ...], projected: frozenset[str], where: str) -> None:
    """Fail closed when a document is not exactly the set's members, or fills a gap.

    Two failures: a divergent member set (a documented member dropped, or a key no
    documentation defines) and a non-null value outside the model-backed ``projected``
    names. The second is the fabrication rule of this package expressed in code.
    """
    fields = set(record)
    expected = set(columns)
    if fields != expected:
        raise RenderError(
            f"ec2_instances: {where} com campos diferentes do conjunto emitido: "
            f"sobram={sorted(fields - expected)} faltam={sorted(expected - fields)}"
        )
    filled = sorted(name for name in _NULL_EMPTY & fields if not _is_empty(record[name]))
    if filled:
        raise RenderError(f"ec2_instances: colunas null-empty receberam valor: {filled}")
    invented = sorted(name for name in fields if not _is_empty(record[name]) and name not in projected)
    if invented:
        raise RenderError(
            f"ec2_instances: {where} preencheu colunas sem fonte no modelo canonico "
            f"(lacuna, nao valor): {invented}"
        )


class _Ec2Model:
    """The estate lookups one ``Instance`` object needs, resolved by foreign key.

    Every lookup fails closed on a missing referent: the gate already refuses orphans (P2),
    and a renderer that silently invented a missing profile or segment would hide exactly the
    defect the gate exists to catch.
    """

    def __init__(self, estate: CanonicalEstate) -> None:
        self.profiles: dict[str, InstanceProfile] = {
            profile.resource_uuid: profile for profile in estate.instance_profiles
        }
        self.interfaces_by_uuid: dict[str, NetworkInterface] = {
            interface.interface_uuid: interface for interface in estate.network_interfaces
        }
        self.segments: dict[str, NetworkSegment] = {
            segment.segment_uuid: segment for segment in estate.network_segments
        }

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


def tag_set(resource: Resource) -> list[dict[str, str]]:
    """Return the documented ``TagSet.N`` array of the resource's own tags.

    ``key``/``value`` are the EC2 ``Tag`` object's members in the RESPONSE spelling the page
    prints (``Key (request), key (response)`` --
    ``https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Tag.html``); a
    ``DescribeInstances`` fixture is a response. The specification enumerates the container
    only. Values are the model's, in the model's order -- the estate's tag tuple is already a
    stable list of pairs.
    """
    return [{"key": key, "value": value} for key, value in resource.tags]


def _instance_state(profile: InstanceProfile | None) -> dict[str, Any] | None:
    """Return the documented ``InstanceState`` object of the model's canonical state."""
    if profile is None:
        return None
    try:
        code, name = _INSTANCE_STATE[profile.state]
    except KeyError:
        raise RenderError(
            f"ec2_instances: estado de instancia fora do dominio canonico: {profile.state!r}"
        ) from None
    return {"code": code, "name": name}


def _launch_time(profile: InstanceProfile | None) -> str | None:
    """Return ``launchTime`` in the documented literal (ISO 8601 UTC, milliseconds)."""
    if profile is None:
        return None
    return profile.launch_time.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _network_interface_item(
    interface: NetworkInterface, segment: NetworkSegment | None
) -> dict[str, Any]:
    """Return one ``NetworkInterfaceSet.N`` item, in the documented response spelling.

    The five members are the ones the ``InstanceNetworkInterface`` page publishes
    (``networkInterfaceId``, ``macAddress``, ``privateIpAddress``, ``subnetId``, ``vpcId`` --
    ``https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_InstanceNetworkInterface.html``);
    the model carries exactly those facts.
    """
    return {
        "networkInterfaceId": interface.interface_id,
        "macAddress": interface.mac_address,
        "privateIpAddress": interface.private_ip,
        "subnetId": None if segment is None else segment.subnet_id,
        "vpcId": None if segment is None else segment.segment_id,
    }


def _instance(resource: Resource, model: _Ec2Model) -> dict[str, Any]:
    """Return the 61-member ``Instance`` object of one AWS EC2 resource."""
    reservation = resource.capacity_reservation
    profile = model.profile_of(resource)
    interface = None if profile is None else model.interface_of(profile)
    segment = None if profile is None else model.segment_of(profile)
    record: dict[str, Any] = {
        "amiLaunchIndex": None,
        "architecture": None,
        "BlockDeviceMapping.N": None,
        "bootMode": None,
        "capacityBlockId": None,
        "capacityReservationId": None if reservation is None else reservation.reservation_id,
        "capacityReservationSpecification": None,
        "clientToken": None,
        "cpuOptions": None,
        "currentInstanceBootMode": None,
        "dnsName": None,
        "ebsOptimized": None,
        "ElasticGpuAssociationSet.N": None,
        "ElasticInferenceAcceleratorAssociationSet.N": None,
        "enaSupport": None,
        "enclaveOptions": None,
        "GroupSet.N": None,
        "hibernationOptions": None,
        "hypervisor": None,
        "iamInstanceProfile": None,
        "imageId": None if profile is None else profile.image_id,
        "instanceId": aws_resource_id("ec2_instance", resource.identity.uuid),
        "instanceLifecycle": None,
        "instanceState": _instance_state(profile),
        "instanceType": None if profile is None else profile.instance_type,
        "ipAddress": None if profile is None else profile.public_ip,
        "ipv6Address": None,
        "kernelId": None,
        "keyName": None,
        "launchTime": _launch_time(profile),
        "LicenseSet.N": None,
        "maintenanceOptions": None,
        "metadataOptions": None,
        "monitoring": None,
        # The interface of the same resource; a profile without one emits nothing rather than
        # a fabricated interface.
        "NetworkInterfaceSet.N": (
            None if interface is None else [_network_interface_item(interface, segment)]
        ),
        "networkPerformanceOptions": None,
        "operator": None,
        "outpostArn": None,
        "placement": ({"availabilityZone": profile.zone} if profile is not None and profile.zone else None),
        "platform": None,
        "platformDetails": None,
        "privateDnsName": None,
        "privateDnsNameOptions": None,
        "privateIpAddress": None if profile is None else profile.private_ip,
        "ProductCodes.N": None,
        "ramdiskId": None,
        "reason": None,
        "rootDeviceName": None,
        "rootDeviceType": None,
        "SecondaryInterfaceSet.N": None,
        "sourceDestCheck": None,
        "spotInstanceRequestId": None,
        "sriovNetSupport": None,
        "stateReason": None,
        "subnetId": None if segment is None else segment.subnet_id,
        "TagSet.N": tag_set(resource),
        "tpmSupport": None,
        "usageOperation": None,
        "usageOperationUpdateTime": None,
        "virtualizationType": None,
        "vpcId": None if segment is None else segment.segment_id,
    }
    _require_projection(record, _INSTANCE_COLUMNS, _INSTANCE_PROJECTED, f"instancia {resource.identity.uuid}")
    return record


def _reservation(account_id: str, instances: list[dict[str, Any]]) -> dict[str, Any]:
    """Return the 5-member ``Reservation`` object of one (account, region) call."""
    record: dict[str, Any] = {
        # GAP: the estate models no launch grouping, and no ``r-`` id is minted for one.
        "reservationId": None,
        "ownerId": account_id,
        # GAP: no launching principal is modelled.
        "requesterId": None,
        # The object page documents this member as "Not supported.", so an empty array is
        # the documented answer rather than a gap.
        "GroupSet.N": [],
        "InstancesSet.N": instances,
    }
    _require_projection(record, _RESERVATION_COLUMNS, _RESERVATION_PROJECTED, f"reserva de {account_id}")
    return record


def _request_parameters() -> dict[str, Any]:
    """Return the documented request parameters as a SHAPE fixture (all values null).

    These six names belong to the REQUEST side of the action; the estate models no captured
    request, so every value is null. The document exists so the request vocabulary is
    present and the gap is testable rather than silently absent.
    """
    document: dict[str, Any] = dict.fromkeys(_REQUEST_COLUMNS)
    _require_projection(document, _REQUEST_COLUMNS, _REQUEST_PROJECTED, "parametros de requisicao")
    return document


def _calls(estate: CanonicalEstate) -> list[tuple[str, str, list[Resource]]]:
    """Return the estate's EC2 (account, region, instances) calls, in deterministic order."""
    grouped: dict[tuple[str, str], list[Resource]] = {}
    for resource in estate.resources:
        if resource.identity.provider != PROVIDER_KEY_AWS or resource.resource_type != "ec2_instance":
            continue
        grouped.setdefault((resource.parent_scope_id, resource.region_id), []).append(resource)
    return [
        (account_id, region, sorted(grouped[(account_id, region)], key=lambda r: r.identity.logical_path))
        for account_id, region in sorted(grouped)
    ]


def _write_text(path: Path, text: str, written: list[Path]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if path not in written:
        written.append(path)


class Ec2InstancesRenderer:
    """Renders the canonical estate's AWS EC2 inventory as DescribeInstances fixtures."""

    name = "ec2_instances"

    def render(self, estate: CanonicalEstate, out_dir: Path) -> list[Path]:
        """Write the fixtures under ``out_dir/ec2_instances/``; return written paths."""
        target = out_dir / RENDER_DIR
        written: list[Path] = []
        responses: list[dict[str, Any]] = []
        reservations: list[dict[str, Any]] = []
        instances: list[dict[str, Any]] = []
        model = _Ec2Model(estate)

        for account_id, region, resources in _calls(estate):
            call_instances = [_instance(resource, model) for resource in resources]
            reservation = _reservation(account_id, call_instances)
            responses.append(
                {
                    # The identifier of the call -- minted, not modelled as an entity; see
                    # :func:`request_id`. It is the one REQUIRED member of this set.
                    "requestId": request_id(estate, account_id, region),
                    "reservationSet": [reservation],
                    # The documented value for "there are no more items to return": this
                    # fixture carries the estate's whole inventory in one page.
                    "nextToken": None,
                }
            )
            reservations.append(reservation)
            instances.extend(call_instances)

        for response in responses:
            _require_projection(response, _RESPONSE_COLUMNS, _RESPONSE_PROJECTED, "envelope de resposta")

        _write_text(
            target / "describe-instances-response.json",
            json.dumps(responses, indent=2, ensure_ascii=False) + "\n",
            written,
        )
        _write_text(
            target / "reservation.json",
            json.dumps(reservations, indent=2, ensure_ascii=False) + "\n",
            written,
        )
        _write_text(
            target / "instance.json",
            json.dumps(instances, indent=2, ensure_ascii=False) + "\n",
            written,
        )
        _write_text(
            target / "request-parameters.json",
            json.dumps(_request_parameters(), indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            written,
        )
        return written
