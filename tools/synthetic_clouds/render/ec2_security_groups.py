"""AWS EC2 ``DescribeSecurityGroups`` response renderer (os security groups e as SUAS REGRAS).

Projects the canonical estate's AWS security groups into the **40 documented fields** of
``specs/aws/ec2-describe-security-groups.schema.json`` -- os 3 elementos de topo da resposta, os
9 membros de ``SecurityGroup``, os 7 de ``IpPermission``, os 2 de cada um de ``IpRange``,
``Ipv6Range`` e ``PrefixListId``, os 7 de ``UserIdGroupPair``, os 2 de ``Tag`` e os 6
parametros documentados da requisicao.

WHY THIS SURFACE IS NOT THE CONFIG SNAPSHOT
-------------------------------------------
``render/aws_config_snapshot.py`` renders the durable export of CONFIGURATION ITEMS. This one is
a different surface with a different question: it answers "what do the RULES of this security
group say?". The granularity is the rule, and that is what a posture consumer needs -- and it is
the granularity the Azure sibling ``render/azure_nsg_rules.py`` already serves for NSG, over the
same consumer, on the other cloud.

THE REASON THIS SURFACE EXISTS: THE THREE NETWORK RULES OF AWS CONFIG
--------------------------------------------------------------------
The estate already carried fifteen ``security_group`` RESOURCES and not one rule. Because of
that, ``render/config_compliance_by_rule.py`` had to answer three real managed rules
``INSUFFICIENT_DATA`` -- ``restricted-ssh``, ``restricted-common-ports`` and
``vpc-default-security-group-closed`` -- all three of which publish
*Resource Types:* ``AWS::EC2::SecurityGroup`` and all three of which read ingress rules or their
absence. That was a MODEL gap, not a doubt about the rule, and closing it is the Increment 2.

THE MODEL HAS ITS OWN TYPE HERE, ON PURPOSE
-------------------------------------------
``model/network.py`` does NOT reuse ``SecurityRule``/``NetworkSecurityGroup`` for this, and the
reason is domain, not style. Four published facts force the split:

1. **A security group rule is ALLOW-ONLY.** The VPC User Guide says outright: "You can specify
   allow rules, but not deny rules." Blocking is the ABSENCE of a rule. ``SecurityRule`` carries
   an ``access`` field, and there is nothing in an AWS rule for it to point at.
2. **There is no priority.** The Azure NSG publishes ``priority`` 100..4096 with the lowest
   number winning. ``IpPermission`` publishes no member that orders or precedes rules -- every
   rule in a group applies equally.
3. **The protocol domain is different.** ``ipProtocol`` is a String that accepts a NAME
   (``tcp``/``udp``/``icmp``/``icmpv6``), a protocol NUMBER, or ``-1``. ``SECURITY_RULE_PROTOCOLS``
   is the Azure CLOSED six-value list.
4. **The source is a LIST, not a pair of fields.** ``IpPermission`` has one set of possible
   sources (``IpRanges`` OR ``Ipv6Ranges`` OR ``Groups`` OR ``PrefixListIds`` -- the ``IpRange``
   page says a CIDR block and a source security group are mutually exclusive) and one
   ``fromPort``/``toPort`` pair. Azure has a source prefix AND a destination prefix AND a source
   port range AND a destination port range.

WHAT IS DERIVED, AND THE ONE TODO-VERIFICAR
--------------------------------------------
Three things in this artifact are not read straight off the model, and each is declared in
``_provenance.json`` rather than left to look like a fact:

* ``vpcId`` -- **TODO-verificar**. The estate does not link a security group to a VPC: its
  ``vpc`` resources all live in ``sa-east-1`` and its ``security_group`` resources all live in
  ``us-east-1``, so no (account, region) pair holds both, and no ``sg-`` id crosses over. What
  the model does have is the NETWORK SEGMENT: one ``NetworkSegment`` per (account, region),
  whose ``segment_id`` is already the native ``vpc-...`` id. So the association is a function of
  the model's own (account, region) grouping rather than a claim about the provider's semantics.
  It still needs checking against a real account's VPC<->SG relation, and that is pending the
  model carrying that relation. The builder FAILS CLOSED if a group has no segment: a group with
  no VPC would make ``vpc-default-security-group-closed`` answer about a VPC that does not exist.
* ``securityGroupArn`` -- null. The ARN is ``arn:<partition>:ec2:<region>:<account>:...`` and the
  model carries no partition. Writing ``arn:aws:`` would assert a fact the estate does not have,
  and the partition is exactly what differs between commercial, GovCloud and China.
* ``groupDescription`` -- the documented description of the DEFAULT group, and otherwise the
  name the model already gave the resource. No phrase is invented for a field AWS publishes as
  free text.

WHAT STAYS EMPTY, AND WHY
-------------------------
``Ipv6Ranges.N``, ``Groups.N`` and ``PrefixListIds.N`` are emitted as the EMPTY containers the
official Sample Response shows (``<ipv6Ranges/>``, ``<groups/>``, ``<prefixListIds/>``): the
estate declares no IPv6 range, no prefix list and no SG-referencing rule. The whole
``request-parameters`` set is null for the reason ``render/ec2_instances.py`` gives for its own:
those names belong to the REQUEST side of the action and the estate models no captured request.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tools.synthetic_clouds.determinism import identity_for
from tools.synthetic_clouds.fidelity.spec import SurfaceSpec, load_spec
from tools.synthetic_clouds.generate.constants import PROVIDER_KEY_AWS
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.network import AwsIpPermission, AwsSecurityGroup
from tools.synthetic_clouds.model.resource import Resource
from tools.synthetic_clouds.render.base import RenderError

# The surface this renderer produces, as the spec names it.
SURFACE = "aws/ec2-describe-security-groups"

# The cited specification: the source of truth for this surface.
SPEC_PATH = (
    Path(__file__).resolve().parents[3] / "specs" / "aws" / "ec2-describe-security-groups.schema.json"
)

# The rendered directory under ``out_dir``.
RENDER_DIR = "ec2_security_groups"

#: The sibling provenance report, written beside the data (never inside it).
PROVENANCE_PATH = "_provenance.json"

# The sets of the cited specification, by name.
RESPONSE_SCOPE = "describe-security-groups-response"
GROUP_SCOPE = "security-group"
PERMISSION_SCOPE = "ip-permission"
IP_RANGE_SCOPE = "ip-range"
IPV6_RANGE_SCOPE = "ipv6-range"
PREFIX_LIST_SCOPE = "prefix-list-id"
GROUP_PAIR_SCOPE = "user-id-group-pair"
TAG_SCOPE = "tag"
REQUEST_SCOPE = "request-parameters"

#: The page that says a security group rule can only ALLOW. Quoted in the provenance because it
#: is the single fact that decides this model has no decision field.
ALLOW_ONLY_URL = "https://docs.aws.amazon.com/vpc/latest/userguide/security-group-rules.html"

#: The page whose Sample Response identifies the VPC DEFAULT group by ``groupName = "default"``.
#: That is what ``vpc-default-security-group-closed`` evaluates.
GROUP_MEMBER_URL = "https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_SecurityGroup.html"

_spec: SurfaceSpec | None = None


def specification() -> SurfaceSpec:
    """Load (once) the cited specification for ``aws/ec2-describe-security-groups``."""
    global _spec
    if _spec is None:
        _spec = load_spec(SPEC_PATH)
    return _spec


def _names_of(scope: str) -> tuple[str, ...]:
    """Return a set's column names in documentation order, refusing to drop one.

    A column the documentation describes without contracting it must never reach an artifact,
    and a documented column must never be dropped: both are hard errors.
    """
    columns = specification().columns_for(scope)
    refused = tuple(column.name for column in columns if not column.belongs_to_schema)
    if refused:
        raise RenderError(
            f"{RENDER_DIR}: o conjunto {scope!r} da especificacao {SURFACE} marcou colunas "
            f"documentadas como fora do formato: {list(refused)}"
        )
    return tuple(column.name for column in columns)


# The nine sets, in documentation order -- derived, not retyped.
_RESPONSE_COLUMNS: tuple[str, ...] = _names_of(RESPONSE_SCOPE)
_GROUP_COLUMNS: tuple[str, ...] = _names_of(GROUP_SCOPE)
_PERMISSION_COLUMNS: tuple[str, ...] = _names_of(PERMISSION_SCOPE)
_IP_RANGE_COLUMNS: tuple[str, ...] = _names_of(IP_RANGE_SCOPE)
_IPV6_RANGE_COLUMNS: tuple[str, ...] = _names_of(IPV6_RANGE_SCOPE)
_PREFIX_LIST_COLUMNS: tuple[str, ...] = _names_of(PREFIX_LIST_SCOPE)
_GROUP_PAIR_COLUMNS: tuple[str, ...] = _names_of(GROUP_PAIR_SCOPE)
_TAG_COLUMNS: tuple[str, ...] = _names_of(TAG_SCOPE)
_REQUEST_COLUMNS: tuple[str, ...] = _names_of(REQUEST_SCOPE)

#: The model facts each set may project. A non-null value anywhere else is a value the canonical
#: model does not carry -- :func:`_require_projection` fails closed on it. These sets are
#: therefore also the DEFINITIVE list of what this renderer can fill: a name absent from one of
#: them is emitted empty, by construction rather than by discipline.
# ``nextToken`` is absent on purpose even though it is emitted: it is always null, so it never
# reaches the non-empty branch of the check below, and listing it would allow a value there.
_RESPONSE_PROJECTED: frozenset[str] = frozenset({"requestId", "securityGroupInfo"})
_GROUP_PROJECTED: frozenset[str] = frozenset(
    {
        "groupDescription",
        "groupId",
        "groupName",
        "IpPermissions.N",
        "IpPermissionsEgress.N",
        "ownerId",
        "TagSet.N",
        "vpcId",
    }
)
_PERMISSION_PROJECTED: frozenset[str] = frozenset(
    {
        "fromPort",
        "Groups.N",
        "ipProtocol",
        "IpRanges.N",
        "Ipv6Ranges.N",
        "PrefixListIds.N",
        "toPort",
    }
)
_IP_RANGE_PROJECTED: frozenset[str] = frozenset({"cidrIp", "description"})
_IPV6_RANGE_PROJECTED: frozenset[str] = frozenset()
_PREFIX_LIST_PROJECTED: frozenset[str] = frozenset()
_GROUP_PAIR_PROJECTED: frozenset[str] = frozenset()
_TAG_PROJECTED: frozenset[str] = frozenset({"key", "value"})
_REQUEST_PROJECTED: frozenset[str] = frozenset()

#: Columns that belong to the file and may never receive a value (``evidence: null-empty``).
#: Empty for this surface: the nulls this renderer emits are MODEL gaps, argued in the module
#: docstring, not documentation claims.
_NULL_EMPTY: frozenset[str] = specification().null_empty_names


def _is_empty(value: Any) -> bool:
    """True when ``value`` is this fixture's shape for "no value" (never for zero).

    Zero is a REAL value here: ``fromPort``/``toPort`` can legitimately be ``0``, so treating
    zero as empty would hide a real rule.
    """
    return value is None or value == "" or value == {} or value == []


def _require_projection(
    record: dict[str, Any],
    columns: tuple[str, ...],
    projected: frozenset[str],
    where: str,
) -> None:
    """Fail closed when a document is not exactly the set's members, or fills a gap.

    Two failures: a divergent member set (a documented member dropped, or a key no
    documentation defines) and a non-null value outside the model-backed ``projected`` names.
    The second is the fabrication rule of this package expressed in code.
    """
    fields = set(record)
    expected = set(columns)
    if fields != expected:
        raise RenderError(
            f"{RENDER_DIR}: {where} com campos diferentes do conjunto emitido: "
            f"sobram={sorted(fields - expected)} faltam={sorted(expected - fields)}"
        )
    filled = sorted(name for name in _NULL_EMPTY & fields if not _is_empty(record[name]))
    if filled:
        raise RenderError(f"{RENDER_DIR}: colunas null-empty receberam valor: {filled}")
    invented = sorted(name for name in fields if not _is_empty(record[name]) and name not in projected)
    if invented:
        raise RenderError(
            f"{RENDER_DIR}: {where} preencheu colunas sem fonte no modelo canonico "
            f"(lacuna, nao valor): {invented}"
        )


def _ip_range(entry: Any) -> dict[str, Any]:
    """Return the documented 2-member ``IpRange`` of one IPv4 source range."""
    record: dict[str, Any] = {"cidrIp": entry.cidr_ip, "description": entry.description}
    _require_projection(record, _IP_RANGE_COLUMNS, _IP_RANGE_PROJECTED, "IpRange")
    return record


def _permission(permission: AwsIpPermission) -> dict[str, Any]:
    """Return the documented ``IpPermission`` of one ingress or egress rule.

    The four origin containers are emitted ALWAYS, including the empty ones, because the
    official Sample Response publishes them empty: an egress rule with no prefix list comes
    back as ``<ipv6Ranges/>``, ``<groups/>`` and ``<prefixListIds/>``. Omitting them would
    understate the format; filling them would invent a source the estate does not declare.

    ``fromPort``/``toPort`` go out as ``None`` -- not zero -- when the rule publishes no port,
    which is the case for ``-1``. The document says they do not apply there, and the official
    egress sample carries neither member.
    """
    record: dict[str, Any] = {
        "fromPort": permission.from_port,
        "Groups.N": [_group_pair(pair) for pair in permission.group_pairs],
        "ipProtocol": permission.ip_protocol,
        "IpRanges.N": [_ip_range(entry) for entry in permission.ip_ranges],
        "Ipv6Ranges.N": [],
        "PrefixListIds.N": [],
        "toPort": permission.to_port,
    }
    _require_projection(record, _PERMISSION_COLUMNS, _PERMISSION_PROJECTED, "IpPermission")
    return record


def _group_pair(pair: Any) -> dict[str, Any]:
    """Return the documented ``UserIdGroupPair`` of one SG-referencing rule."""
    record: dict[str, Any] = {
        "description": pair.description,
        "groupId": pair.group_id,
        "groupName": pair.group_name,
        "peeringStatus": pair.peering_status,
        "userId": pair.user_id,
        "vpcId": pair.vpc_id,
        "vpcPeeringConnectionId": pair.vpc_peering_connection_id,
    }
    _require_projection(record, _GROUP_PAIR_COLUMNS, _GROUP_PAIR_PROJECTED, "UserIdGroupPair")
    return record


def _tags(resource: Resource) -> list[dict[str, Any]]:
    """Return one documented ``Tag`` object per tag the resource carries.

    The documented constraint is that a tag KEY may not begin with ``aws:``; the estate's keys
    never do, so nothing is filtered here -- the rule is stated so a future estate carrying a
    reserved key is caught rather than silently emitted.
    """
    records: list[dict[str, Any]] = []
    for tag_key, tag_value in resource.tags:
        record: dict[str, Any] = {"key": tag_key, "value": tag_value}
        _require_projection(record, _TAG_COLUMNS, _TAG_PROJECTED, f"Tag {tag_key}")
        records.append(record)
    return records


def _security_group(group: AwsSecurityGroup, resource: Resource) -> dict[str, Any]:
    """Return the documented ``SecurityGroup`` of one group.

    ``securityGroupArn`` is null and this is the reason: the ARN is
    ``arn:<partition>:ec2:<region>:<account>:security-group/<id>`` and the model carries no
    partition. Writing ``arn:aws:`` would assert a fact the estate does not have.
    """
    record: dict[str, Any] = {
        "groupDescription": group.group_description,
        "groupId": group.group_id,
        "groupName": group.group_name,
        "IpPermissions.N": [_permission(rule) for rule in group.ingress],
        "IpPermissionsEgress.N": [_permission(rule) for rule in group.egress],
        "ownerId": group.owner_id,
        "securityGroupArn": None,
        "TagSet.N": _tags(resource),
        "vpcId": group.vpc_id,
    }
    _require_projection(record, _GROUP_COLUMNS, _GROUP_PROJECTED, f"SecurityGroup {group.group_id}")
    return record


def _request_parameters() -> dict[str, Any]:
    """Return the documented request parameters as a SHAPE fixture (all values null).

    These six names belong to the REQUEST side of the action; the estate models no captured
    request, so every value is null. The document exists so the request vocabulary is present
    and the gap is testable rather than silently absent -- exactly as
    ``render/ec2_instances.py`` does for its own request set.
    """
    document: dict[str, Any] = dict.fromkeys(_REQUEST_COLUMNS)
    _require_projection(document, _REQUEST_COLUMNS, _REQUEST_PROJECTED, "parametros de requisicao")
    return document


def _shape_fixture(columns: tuple[str, ...], projected: frozenset[str], scope: str) -> dict[str, Any]:
    """Return one all-null object carrying a set's vocabulary.

    Used for the three sets the estate declares no member of: an IPv6 range, a prefix list and
    a security-group reference. Emitting them empty would make a model gap indistinguishable
    from an omission; emitting them with a null value says "this shape exists, this estate has
    no instance of it".
    """
    document: dict[str, Any] = dict.fromkeys(columns)
    _require_projection(document, columns, projected, f"forma de {scope}")
    return document


def _groups_by_scope(
    estate: CanonicalEstate,
) -> tuple[dict[tuple[str, str], list[AwsSecurityGroup]], dict[str, Resource]]:
    """Group the estate's AWS security groups by (account, region), deterministically.

    One group per (account, region) because that is the scope of an EC2 read call: a security
    group belongs to one VPC in one region, so one account's groups in three regions are three
    answers, not one. This is the same granularity ``render/ec2_instances.py`` uses for the
    same reason.

    The resource index is returned with it because two documented members of ``SecurityGroup``
    are read off the RESOURCE rather than off the group: ``TagSet.N``, and the region the scope
    is keyed on.
    """
    by_uuid = {resource.identity.uuid: resource for resource in estate.resources}
    grouped: dict[tuple[str, str], list[AwsSecurityGroup]] = {}
    for group in estate.aws_security_groups:
        resource = by_uuid.get(group.resource_uuid)
        if resource is None:
            # Fail closed: without the resource there is no tag set and no region, and a tag
            # set is a documented member of SecurityGroup.
            raise RenderError(
                f"{RENDER_DIR}: security group {group.group_id} aponta para "
                f"{group.resource_uuid!r}, que nao e recurso do estate (FK orfa)"
            )
        if resource.identity.provider != PROVIDER_KEY_AWS:
            raise RenderError(
                f"{RENDER_DIR}: security group {group.group_id} pertence a um recurso "
                f"{resource.identity.provider!r}, que nao e AWS"
            )
        grouped.setdefault((group.owner_id, resource.region_id), []).append(group)
    return (
        {
            scope: sorted(items, key=lambda item: item.group_id)
            for scope, items in sorted(grouped.items())
        },
        by_uuid,
    )


def _write_text(path: Path, text: str, written: list[Path]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if path not in written:
        written.append(path)


class Ec2SecurityGroupsRenderer:
    """Renders the canonical estate's AWS security groups, with their RULES."""

    name = "ec2_security_groups"

    def render(self, estate: CanonicalEstate, out_dir: Path) -> list[Path]:
        """Write the fixtures under ``out_dir/ec2_security_groups/``; return written paths."""
        target = out_dir / RENDER_DIR
        written: list[Path] = []
        by_scope, by_uuid = _groups_by_scope(estate)

        responses: list[dict[str, Any]] = []
        groups: list[dict[str, Any]] = []
        permissions: list[dict[str, Any]] = []
        ip_ranges: list[dict[str, Any]] = []
        tags: list[dict[str, Any]] = []

        for (account_id, region), scope_groups in by_scope.items():
            scope_records = [_security_group(group, by_uuid[group.resource_uuid]) for group in scope_groups]
            # Tudo o derivado sai do RECORD, nunca do modelo em paralelo: assim ha um unico
            # caminho de dados e nenhuma chance de o artefato derivado divergir do que esta
            # dentro de ``securityGroupInfo``.
            for record in scope_records:
                groups.append(record)
                rules = [*record["IpPermissions.N"], *record["IpPermissionsEgress.N"]]
                permissions.extend(rules)
                for rule in rules:
                    ip_ranges.extend(rule["IpRanges.N"])
                tags.extend(record["TagSet.N"])
            responses.append(
                {
                    "nextToken": None,
                    "requestId": _request_id(estate, account_id, region),
                    "securityGroupInfo": scope_records,
                }
            )

        for response in responses:
            _require_projection(response, _RESPONSE_COLUMNS, _RESPONSE_PROJECTED, "envelope de resposta")

        # Determinismo byte-a-byte: a ordem das listas derivadas segue a ordem dos escopos.
        permissions.sort(key=_permission_sort_key)
        ip_ranges.sort(key=lambda item: (item["cidrIp"] or "", item["description"] or ""))
        tags.sort(key=lambda item: (item["key"] or "", item["value"] or ""))

        _write_text(
            target / "describe-security-groups-response.json",
            json.dumps(responses, indent=2, ensure_ascii=False) + "\n",
            written,
        )
        _write_text(target / "security-group.json", json.dumps(groups, indent=2, ensure_ascii=False) + "\n", written)
        _write_text(
            target / "ip-permission.json", json.dumps(permissions, indent=2, ensure_ascii=False) + "\n", written
        )
        _write_text(target / "ip-range.json", json.dumps(ip_ranges, indent=2, ensure_ascii=False) + "\n", written)
        _write_text(target / "tag.json", json.dumps(tags, indent=2, ensure_ascii=False) + "\n", written)
        _write_text(
            target / "ipv6-range.json",
            json.dumps(_shape_fixture(_IPV6_RANGE_COLUMNS, _IPV6_RANGE_PROJECTED, "Ipv6Range"), indent=2, ensure_ascii=False)
            + "\n",
            written,
        )
        _write_text(
            target / "prefix-list-id.json",
            json.dumps(_shape_fixture(_PREFIX_LIST_COLUMNS, _PREFIX_LIST_PROJECTED, "PrefixListId"), indent=2, ensure_ascii=False)
            + "\n",
            written,
        )
        _write_text(
            target / "user-id-group-pair.json",
            json.dumps(_shape_fixture(_GROUP_PAIR_COLUMNS, _GROUP_PAIR_PROJECTED, "UserIdGroupPair"), indent=2, ensure_ascii=False)
            + "\n",
            written,
        )
        _write_text(
            target / "request-parameters.json",
            json.dumps(_request_parameters(), indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            written,
        )
        written.append(self._write_provenance(target, estate, by_scope))
        return written

    def _write_provenance(
        self, target: Path, estate: CanonicalEstate, by_scope: dict[tuple[str, str], list[AwsSecurityGroup]]
    ) -> Path:
        """Write the sibling provenance report: the spec, the mechanism, the counts, the gaps.

        The reasons live HERE and not in the artifact: an ingestor of the fixture must not see a
        key no cloud documents. This file is what says which values are derivations and which
        are declared gaps.
        """
        todos = [group for groups in by_scope.values() for group in groups]
        com_ingress = [group for group in todos if group.ingress]
        padroes = [group for group in todos if group.is_default]
        relatorio: dict[str, Any] = {
            "kind": "provenance",
            "surface": SURFACE,
            "spec": "specs/aws/ec2-describe-security-groups.schema.json",
            "artifacts": [
                "describe-security-groups-response.json",
                "security-group.json",
                "ip-permission.json",
                "ip-range.json",
                "tag.json",
                "ipv6-range.json",
                "prefix-list-id.json",
                "user-id-group-pair.json",
                "request-parameters.json",
            ],
            "mechanism": {
                "action": "ec2:DescribeSecurityGroups",
                "granularity": "one SecurityGroup per (account, region) scope, carrying both rule lists",
                "scope": "o agrupamento (conta, regiao) do proprio estate: um grupo de seguranca pertence a uma VPC em uma regiao",
                "allow_only": (
                    "a regra da AWS e de PERMISSAO apenas; a pagina de VPC security group rules diz "
                    "'You can specify allow rules, but not deny rules'. O bloqueio e a AUSENCIA de regra, "
                    "e por isso que esta superficie nao tem coluna de decisao e o modelo nao reusa a "
                    "SecurityRule da Azure (que tem 'access' e 'priority', e nao ha membro da AWS para os quais apontar)"
                ),
                "allow_only_source_url": ALLOW_ONLY_URL,
                "default_group": (
                    "identificado por groupName == 'default', que e como a Sample Response oficial mostra o "
                    "grupo padrao de uma VPC; e o grupo que a regra gerenciada "
                    "vpc-default-security-group-closed avalia"
                ),
                "default_group_source_url": GROUP_MEMBER_URL,
                "direction_is_the_list_name": (
                    "nao existe membro 'direction' em IpPermission: a direcao e o nome da propriedade que "
                    "contem a regra (IpPermissions / IpPermissionsEgress)"
                ),
            },
            "counts": {
                "security_groups": len(todos),
                "scopes": len(by_scope),
                "groups_with_ingress": len(com_ingress),
                "groups_without_ingress": len(todos) - len(com_ingress),
                "default_groups": len(padroes),
                "ingress_rules": sum(len(group.ingress) for group in todos),
                "egress_rules": sum(len(group.egress) for group in todos),
            },
            "derivations": [
                {
                    "field": "vpcId",
                    "status": "TODO-verificar",
                    "reason": (
                        "O estate nao liga um security group a uma VPC: os recursos 'vpc' vivem todos em "
                        "sa-east-1 e os 'security_group' todos em us-east-1, e nenhum par (conta, regiao) tem os "
                        "dois. O valor vem do SEGMENTO de rede do mesmo (conta, regiao), cujo segment_id ja e o id "
                        "nativo vpc-... -- ou seja, e a funcao do agrupamento do proprio modelo, nao uma escolha "
                        "sobre a semantica do provedor. A verificacao pendente e a relacao VPC<->SG de uma conta "
                        "real, e so se resolve quando o modelo carregar essa relacao. A construcao FALHA se um "
                        "grupo nao tiver segmento: um grupo sem VPC faria vpc-default-security-group-closed "
                        "responder sobre uma VPC que nao existe."
                    ),
                    "source_url": GROUP_MEMBER_URL,
                },
                {
                    "field": "groupDescription",
                    "reason": (
                        "Para o grupo PADRAO vale a descricao que a Sample Response oficial publica ('default VPC "
                        "security group'). Nos demais grupos a descricao e o nome que o proprio modelo ja deu ao "
                        "recurso: a AWS publica este campo como texto livre, e inventar uma frase seria afirmar algo "
                        "que nenhuma fonte do estate sustenta."
                    ),
                    "source_url": GROUP_MEMBER_URL,
                },
            ],
            "model_gaps": [
                {
                    "field": "securityGroupArn",
                    "reason": (
                        "O ARN e arn:<partition>:ec2:<region>:<account>:security-group/<id>, e o modelo nao carrega "
                        "a PARTICAO. Escrever arn:aws: afirmaria um fato que o estate nao tem -- e a particao e "
                        "exatamente o que difere entre comercial, GovCloud e China. O campo vai null."
                    ),
                    "source_url": GROUP_MEMBER_URL,
                },
                {
                    "field": "Ipv6Ranges.N",
                    "reason": (
                        "O estate nao declara nenhuma faixa IPv6 de origem em regra de security group. O container e "
                        "emitido VAZIO, que e a forma que a Sample Response oficial publica quando a regra nao usa "
                        "IPv6 (<ipv6Ranges/>)."
                    ),
                    "source_url": GROUP_MEMBER_URL,
                },
                {
                    "field": "PrefixListIds.N",
                    "reason": (
                        "O estate nao declara nenhuma prefix list. O container e emitido vazio, como a Sample "
                        "Response oficial mostra (<prefixListIds/>)."
                    ),
                    "source_url": "https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_PrefixListId.html",
                },
                {
                    "field": "Groups.N",
                    "reason": (
                        "Nenhuma regra deste estado resolve a origem por REFERENCIA a outro security group: todas "
                        "usam faixa IPv4. A pagina de IpRange fecha a exclusividade ('You can either specify a CIDR "
                        "block or a source security group, not both'), entao a lista e emitida vazia como a amostra "
                        "oficial mostra (<groups/>)."
                    ),
                    "source_url": "https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_UserIdGroupPair.html",
                },
                {
                    "field": "request-parameters",
                    "reason": (
                        "DryRun, Filter.N, GroupId.N, GroupName.N, MaxResults e NextToken pertencem ao lado de "
                        "REQUISICAO da acao; o estate nao modela nenhuma requisicao capturada, entao os seis vao "
                        "null. Os membros do tipo Filter NAO sao modelados por essa mesma razao -- nenhum filtro "
                        "foi capturado."
                    ),
                    "source_url": "https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeSecurityGroups.html",
                },
                {
                    "field": f"{RESPONSE_SCOPE}.nextToken",
                    "reason": (
                        "nextToken e null em todo envelope, que e o valor documentado para 'nao ha mais itens a "
                        "devolver': os grupos de cada escopo cabem numa pagina."
                    ),
                    "source_url": "https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeSecurityGroups.html",
                },
            ],
            "not_generated": [
                {
                    "field": "securityGroupRuleId",
                    "reason": (
                        "A Sample Response oficial traz <securityGroupRuleId> dentro de <groups>, mas a pagina de "
                        "UserIdGroupPair publica sete membros e esse NAO e um deles. O nome esta em 'unverified' da "
                        "spec, o que o torna proibido no artefato: exemplo nao e contrato de tipo."
                    ),
                    "source_url": "https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_UserIdGroupPair.html",
                }
            ],
        }
        path = target / PROVENANCE_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(relatorio, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return path


def _permission_sort_key(record: dict[str, Any]) -> tuple[Any, ...]:
    """Sort a projected ``IpPermission`` by its published shape, deterministically.

    ``None`` ports must sort BEFORE real ports rather than crash the comparison, and the
    ``-1`` rule (the egress default) is emitted for every non-closed group, so it needs a
    stable position of its own.
    """
    first_range = record["IpRanges.N"][0] if record["IpRanges.N"] else {}
    return (
        str(record["ipProtocol"]),
        record["fromPort"] is None,
        record["fromPort"] if record["fromPort"] is not None else -1,
        str(first_range.get("cidrIp", "")),
    )


def _request_id(estate: CanonicalEstate, account_id: str, region: str) -> str:
    """Return the ``requestId`` of the ``DescribeSecurityGroups`` call of one (account, region).

    The field identifies the REQUEST, not a resource: the documentation publishes it as an
    opaque id carried by every successful response, and it correlates nothing a consumer holds.
    It is minted the same way every other derived AWS id in this package is minted --
    ``identity_for``, UUIDv5 over a logical path -- which is what makes the only required
    column of this surface carry a value.

    One id per call, and a call here is one (account, region): ``DescribeSecurityGroups`` is a
    regional action, so one account's groups in three regions are three responses with three
    request ids.

    ``TODO-verificar``: DERIVED, NOT an AWS-issued request id. Its shape is the documented one
    (a UUID), the entropy is this package's -- the same trade ``render/ec2_instances.py``
    records for its own surface.
    """
    return identity_for(estate.seed, f"describe-security-groups/{account_id}/{region}")