"""Golden tests for ``aws/ec2-describe-security-groups``.

The point of this module is to confront the DELIVERED artifact with
``specs/aws/ec2-describe-security-groups.schema.json`` -- names, values and the empty contract
-- and to hold the judgement calls this surface makes, which are the ones a rules-shaped surface
invites getting quietly wrong:

1. **a security group rule is ALLOW-ONLY.** The canonical model has ``SecurityRule`` for the
   Azure NSG carrying an ``access`` and a ``priority``; neither has anything to point at here,
   so the model grew its own type. A test that only checked names would never notice a ``denied``
   rule sneaking in, or a priority inventing an evaluation order AWS does not publish;
2. **the all-protocol rule publishes no ports.** ``-1`` carries neither ``fromPort`` nor
   ``toPort`` -- the official egress sample proves it -- and ``None`` is not ``0``;
3. **the undeclared sets are emitted as shape, not as absence.** An IPv6 range, a prefix list
   and a security-group reference belong to the format and this estate has no instance of any;
4. **the posture answers the three network rules in BOTH directions**, which is what makes the
   Increment 2 useful rather than merely present.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest

from tools.synthetic_clouds.fidelity.checker import check_artifact, is_faithful
from tools.synthetic_clouds.fidelity.spec import load_spec
from tools.synthetic_clouds.generate.constants import PROVIDER_KEY_AWS
from tools.synthetic_clouds.generate.estate_builder import build_estate
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.network import AwsIpPermission, AwsIpRange, AwsSecurityGroup
from tools.synthetic_clouds.render import ec2_security_groups as mod
from tools.synthetic_clouds.render.base import RenderError, registered_names

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SPEC_FILE = "ec2-describe-security-groups.schema.json"
_SPEC_PATH = _REPO_ROOT / "specs" / "aws" / _SPEC_FILE

#: The nine sets, in documentation order, with the artifact that carries each.
_SCOPES: tuple[tuple[str, str], ...] = (
    ("describe-security-groups-response.json", mod.RESPONSE_SCOPE),
    ("security-group.json", mod.GROUP_SCOPE),
    ("ip-permission.json", mod.PERMISSION_SCOPE),
    ("ip-range.json", mod.IP_RANGE_SCOPE),
    ("tag.json", mod.TAG_SCOPE),
    ("ipv6-range.json", mod.IPV6_RANGE_SCOPE),
    ("prefix-list-id.json", mod.PREFIX_LIST_SCOPE),
    ("user-id-group-pair.json", mod.GROUP_PAIR_SCOPE),
    ("request-parameters.json", mod.REQUEST_SCOPE),
)


@pytest.fixture(scope="module")
def estate() -> CanonicalEstate:
    """The base small estate (seed 123): the resources and the security groups every rule reads."""
    return build_estate(seed=123, profile="small", currency="USD")


@pytest.fixture(scope="module")
def spec() -> Any:
    return load_spec(_SPEC_PATH)


@pytest.fixture(scope="module")
def tree(estate: CanonicalEstate, tmp_path_factory: pytest.TempPathFactory) -> Path:
    written = mod.Ec2SecurityGroupsRenderer().render(estate, tmp_path_factory.mktemp("secgroups"))
    assert written
    return written[0].parent


def _load(tree: Path, name: str) -> Any:
    return json.loads((tree / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def groups(tree: Path) -> list[dict[str, Any]]:
    return cast("list[dict[str, Any]]", _load(tree, "security-group.json"))


@pytest.fixture(scope="module")
def responses(tree: Path) -> list[dict[str, Any]]:
    return cast("list[dict[str, Any]]", _load(tree, "describe-security-groups-response.json"))


@pytest.fixture(scope="module")
def permissions(tree: Path) -> list[dict[str, Any]]:
    return cast("list[dict[str, Any]]", _load(tree, "ip-permission.json"))


# -- the renderer is wired ----------------------------------------------------


def test_o_renderer_esta_registrado() -> None:
    assert mod.RENDER_DIR in registered_names()
    assert mod.Ec2SecurityGroupsRenderer.name == "ec2_security_groups"


def test_a_spec_cita_a_acao_e_a_data_da_consulta(spec: Any) -> None:
    assert spec.surface == mod.SURFACE == "aws/ec2-describe-security-groups"
    assert spec.provider == "aws"
    assert spec.reference["url"].endswith("API_DescribeSecurityGroups.html")
    assert spec.reference["consulted_at"] == "2026-10-16"


def test_a_spec_tem_os_nove_conjuntos_documentados(spec: Any) -> None:
    assert [s.name for s in spec.sets] == [
        "describe-security-groups-response",
        "security-group",
        "ip-permission",
        "ip-range",
        "ipv6-range",
        "prefix-list-id",
        "user-id-group-pair",
        "tag",
        "request-parameters",
    ]
    # 3 + 9 + 7 + 2 + 2 + 2 + 7 + 2 + 6
    assert len(spec.names) == 40


def test_a_entrega_e_json_e_read_api(spec: Any) -> None:
    assert spec.delivery["kind"] == "read_api"
    # The EC2 API Reference publishes XML only -- same divergence as ec2-describe-instances,
    # and for the same reason: the Reference has no JSON property list.
    assert spec.delivery["format"] == "xml"


def test_o_membro_da_amostra_que_a_pagina_nao_documenta_e_proibido(spec: Any) -> None:
    """``securityGroupRuleId`` is in the official Sample Response and in NO type page.

    A member the documentation does not define must never reach the artifact, so it lands in
    ``forbidden_names``. This is the assertion that keeps "the example showed it" from turning
    into "the contract says it".
    """
    assert "securityGroupRuleId" in spec.forbidden_names
    assert "securityGroupRuleId" in spec.unverified


# -- THE GOLDEN PART: artifact fields against the spec ------------------------


@pytest.mark.parametrize(("file_name", "scope"), _SCOPES)
def test_cada_artefato_carrega_exatamente_os_campos_do_seu_conjunto(
    spec: Any, tree: Path, file_name: str, scope: str
) -> None:
    """The artifact, not the renderer's intent, has to match the specification."""
    findings = check_artifact(spec, tree / file_name, scope=scope)
    assert is_faithful(findings), [f"{f.kind}: {f.detail}" for f in findings]


def test_a_proveniencia_registra_as_lacunas_que_os_itens_nao_conseguem(tree: Path) -> None:
    """The reasons live beside the data -- never inside it.

    An ingestor of ``security-group.json`` must not see a key no cloud documents, so the gaps
    are reported in ``_provenance.json``.
    """
    report = _load(tree, mod.PROVENANCE_PATH)
    assert report["kind"] == "provenance"
    assert report["surface"] == mod.SURFACE
    assert report["spec"] == f"specs/aws/{_SPEC_FILE}"
    campos = {entry["field"] for entry in report["model_gaps"]}
    assert {"securityGroupArn", "Ipv6Ranges.N", "PrefixListIds.N", "Groups.N", "request-parameters"} <= campos
    assert all(entry["reason"].strip() for entry in report["model_gaps"])
    assert all(entry["reason"].strip() for entry in report["derivations"])


def test_o_vpcid_esta_marcado_como_derivacao_pendente(tree: Path) -> None:
    """The one value this estate asserts without carrying the fact must SAY it is derived.

    The estate does not link a security group to a VPC -- its ``vpc`` resources and its
    ``security_group`` resources live in different regions -- so ``vpcId`` is derived from the
    network segment. A silent derivation would read like a fact.
    """
    report = _load(tree, mod.PROVENANCE_PATH)
    derivacoes = {entry["field"]: entry for entry in report["derivations"]}
    assert "vpcId" in derivacoes
    assert derivacoes["vpcId"]["status"] == "TODO-verificar"
    assert "segmento" in derivacoes["vpcId"]["reason"].lower()


# -- the rule shape is the PUBLISHED one --------------------------------------


def test_nenhuma_regra_carrega_decisao_ou_prioridade(
    groups: list[dict[str, Any]], permissions: list[dict[str, Any]]
) -> None:
    """The AWS rule is ALLOW-ONLY and has NO priority. Neither may appear.

    The Azure ``SecurityRule`` carries ``access`` (``allowed``/``denied``) and ``priority``
    100..4096. Folding the AWS rule into that shape would invent a deny AWS cannot express and
    an evaluation order it does not publish -- so the model grew its own type, and this asserts
    the artifact did not drift back.
    """
    proibidos = {"access", "decision", "priority", "direction", "name"}
    for registro in groups:
        assert not proibidos & set(registro), f"membro de NSG da Azure no SecurityGroup: {proibidos & set(registro)}"
    for regra in permissions:
        assert not proibidos & set(regra), f"membro de NSG da Azure no IpPermission: {proibidos & set(regra)}"


def test_a_direcao_e_o_nome_da_lista_e_nao_um_membro(
    groups: list[dict[str, Any]]
) -> None:
    """A direction has no member to live in: ``IpPermissions`` / ``IpPermissionsEgress`` say it.

    A renderer that added ``direction`` would be inventing a field, and one that reused a single
    ``permissions`` list would be publishing a name the API does not have.
    """
    for grupo in groups:
        assert set(grupo) >= {"IpPermissions.N", "IpPermissionsEgress.N"}
        assert "IpPermissions" not in grupo
        assert "permissions" not in grupo


def test_a_regra_de_todos_os_protocolos_nao_publica_porta(permissions: list[dict[str, Any]]) -> None:
    """``-1`` carries neither ``fromPort`` nor ``toPort`` -- and absence is ``None``, not zero.

    The official Sample Response brings the default egress rule as ``<ipProtocol>-1</ipProtocol>``
    with no port members at all. Writing ``0`` would put a number in the artifact that the API
    never returns.
    """
    todos_protocolos = [regra for regra in permissions if regra["ipProtocol"] == "-1"]
    assert todos_protocolos, "o estate nao produz a regra de egress padrao que a AWS documenta"
    for regra in todos_protocolos:
        assert regra["fromPort"] is None
        assert regra["toPort"] is None


def test_toda_regra_tem_exatamente_um_par_de_portas_ou_nenhum(
    permissions: list[dict[str, Any]]
) -> None:
    """``fromPort``/``toPort`` are a PAIR, and the pair is all-or-nothing.

    The page publishes both as ``Required: No``, but a rule with only one bound would be a
    shape the documentation does not describe.
    """
    for regra in permissions:
        assert (regra["fromPort"] is None) == (regra["toPort"] is None), regra
        if regra["fromPort"] is not None:
            assert regra["fromPort"] <= regra["toPort"]


def test_os_containers_de_origem_vazios_sao_publicados(permissions: list[dict[str, Any]]) -> None:
    """The unused origin containers are emitted EMPTY, as the official sample shows.

    The Sample Response brings ``<ipv6Ranges/>``, ``<groups/>`` and ``<prefixListIds/>`` as empty
    containers on a rule that resolves its source as a CIDR. Omitting them would understate the
    format; filling them would invent a source this estate does not declare.
    """
    for regra in permissions:
        for nome in ("Groups.N", "Ipv6Ranges.N", "PrefixListIds.N"):
            assert isinstance(regra[nome], list), regra
            assert regra[nome] == [], f"{nome} preenchido sem fonte no modelo"


def test_o_conjunto_de_request_e_um_documento_de_forma(tree: Path) -> None:
    """The six request-side names are present and null: no request was captured.

    They belong to the REQUEST side of the action, and the estate models no captured request.
    The document exists so the request vocabulary is testable rather than silently absent.
    """
    documento = _load(tree, "request-parameters.json")
    assert set(documento) == {"DryRun", "Filter.N", "GroupId.N", "GroupName.N", "MaxResults", "NextToken"}
    assert all(value is None for value in documento.values())


def test_o_arn_fica_nulo_porque_a_particao_nao_e_fato_do_modelo(groups: list[dict[str, Any]]) -> None:
    """``securityGroupArn`` is ``arn:<partition>:...`` and the model carries no partition.

    Writing ``arn:aws:`` would assert a fact the estate does not have -- and the partition is
    exactly what differs between commercial, GovCloud and China.
    """
    assert groups, "nenhum security group renderizado"
    assert all(grupo["securityGroupArn"] is None for grupo in groups)


def test_o_token_de_continuidade_e_nulo(responses: list[dict[str, Any]]) -> None:
    """``nextToken`` is null in every envelope: each scope's groups fit in one page."""
    assert responses
    for envelope in responses:
        assert envelope["nextToken"] is None


# -- the posture answers the network rules in BOTH directions -----------------


def _grupos_por_conta(estate: CanonicalEstate) -> dict[tuple[str, str], list[AwsSecurityGroup]]:
    por_conta: dict[tuple[str, str], list[AwsSecurityGroup]] = {}
    por_uuid = {r.identity.uuid: r for r in estate.resources}
    for grupo in estate.aws_security_groups:
        recurso = por_uuid[grupo.resource_uuid]
        por_conta.setdefault((recurso.parent_scope_id, recurso.region_id), []).append(grupo)
    return {k: sorted(v, key=lambda g: g.group_id) for k, v in sorted(por_conta.items())}


def _ssh(grupo: AwsSecurityGroup) -> list[AwsIpPermission]:
    return [regra for regra in grupo.ingress if regra.ip_protocol == "tcp" and regra.from_port == 22]


def test_o_estado_tem_grupos_padrao_e_nao_padrao_em_posturas_opostas(estate: CanonicalEstate) -> None:
    """The estate must be able to answer COMPLIANT AND NON_COMPLIANT for the network rules.

    An estate that only exposed would prove nothing: a consumer with the ports backwards, or one
    ignoring the source CIDR, would score identically. This is the assertion that keeps the
    posture from collapsing into a single case.
    """
    grupos = [g for valores in _grupos_por_conta(estate).values() for g in valores]
    assert grupos

    expostos = [
        g for g in grupos if any(entrada.cidr_ip == "0.0.0.0/0" for regra in _ssh(g) for entrada in regra.ip_ranges)
    ]
    restritos = [
        g for g in grupos if _ssh(g) and g not in expostos
    ]
    assert expostos, "nenhum grupo expoe SSH: restricted-ssh nunca seria NON_COMPLIANT"
    assert restritos, "nenhum grupo restringe SSH a uma origem: so haveria exposicao"

    padroes = [g for g in grupos if g.is_default]
    assert padroes, "nenhum grupo padrao: vpc-default-security-group-closed nao teria o que avaliar"
    assert any(not g.ingress and not g.egress for g in padroes), "nenhum grupo padrao fechado"
    assert any(g.ingress or g.egress for g in padroes), "nenhum grupo padrao com regra"


def test_cada_conta_carrega_somente_grupos_aws(estate: CanonicalEstate) -> None:
    """The collection is AWS-only, and every group points at a real resource (no orphan FK)."""
    uuids = {grupo.resource_uuid for grupo in estate.aws_security_groups}
    assert uuids <= {r.identity.uuid for r in estate.resources}
    por_uuid = {r.identity.uuid: r for r in estate.resources}
    assert all(por_uuid[u].identity.provider == PROVIDER_KEY_AWS for u in uuids)
    assert all(por_uuid[u].resource_type == "security_group" for u in uuids)


def test_o_vpcid_aponta_para_o_segmento_do_mesmo_escopo(estate: CanonicalEstate) -> None:
    """The derived ``vpcId`` must be the model's OWN VPC for that (account, region).

    Derived, yes -- but still a function of the model, not a free choice. This asserts it is the
    segment's native ``vpc-`` id and that the region is the group's own.
    """
    segmentos = {
        (s.scope_id, s.region_id): s.segment_id
        for s in estate.network_segments
        if s.provider == PROVIDER_KEY_AWS
    }
    por_uuid = {r.identity.uuid: r for r in estate.resources}
    for grupo in estate.aws_security_groups:
        recurso = por_uuid[grupo.resource_uuid]
        assert grupo.vpc_id == segmentos[(recurso.parent_scope_id, recurso.region_id)]
        assert grupo.vpc_id.startswith("vpc-")


def test_todo_grupo_tem_descricao_e_dono(groups: list[dict[str, Any]]) -> None:
    """``groupDescription`` and ``ownerId`` are free text in the format, and the model has both.

    ``ownerId`` is the account that owns the group -- a real model fact. The description is the
    documented one for the default group and the model's own resource name otherwise, never an
    invented phrase.
    """
    for grupo in groups:
        assert grupo["groupDescription"], grupo["groupId"]
        assert grupo["ownerId"].isdigit(), grupo["groupId"]
    padroes = [g for g in groups if g["groupName"] == "default"]
    assert padroes
    assert all(g["groupDescription"] == "default VPC security group" for g in padroes)


# -- determinism and fail-closed projection -----------------------------------


def test_o_render_e_deterministico(estate: CanonicalEstate, tmp_path: Path) -> None:
    primeiro = mod.Ec2SecurityGroupsRenderer().render(estate, tmp_path / "a")
    segundo = mod.Ec2SecurityGroupsRenderer().render(estate, tmp_path / "b")
    assert [p.name for p in primeiro] == [p.name for p in segundo]
    for a, b in zip(primeiro, segundo, strict=True):
        assert a.read_bytes() == b.read_bytes(), a.name


def _grupo_completo(arn: str | None) -> dict[str, Any]:
    """A full ``SecurityGroup`` record, differing only in ``securityGroupArn``.

    ``_require_projection`` checks the member SET first, so a proof about one member has to
    carry the other eight -- otherwise the call fails for the wrong reason and the test would
    pass without ever reaching the rule it is about.
    """
    return {
        "groupDescription": "d",
        "groupId": "sg-1",
        "groupName": "n",
        "IpPermissions.N": [],
        "IpPermissionsEgress.N": [],
        "ownerId": "1",
        "securityGroupArn": arn,
        "TagSet.N": [],
        "vpcId": "vpc-1",
    }


def test_a_prova_de_projecao_recusa_coluna_sem_fonte_no_modelo() -> None:
    """``_require_projection`` fails closed: a value with no model source is an error.

    ``securityGroupArn`` is the real case. It belongs to the format and is projected by nobody
    -- the ARN needs a partition the estate does not carry -- so filling it is rejected by the
    code path, not merely left undone by convention.
    """
    assert "securityGroupArn" not in mod._GROUP_PROJECTED
    with pytest.raises(RenderError, match="sem fonte no modelo canonico"):
        mod._require_projection(
            _grupo_completo("arn:aws:ec2:us-east-1:123456789012:security-group/sg-1"),
            mod._GROUP_COLUMNS,
            mod._GROUP_PROJECTED,
            "SecurityGroup",
        )
    # The documented value the renderer actually writes passes the same proof.
    mod._require_projection(
        _grupo_completo(None), mod._GROUP_COLUMNS, mod._GROUP_PROJECTED, "SecurityGroup"
    )


def test_a_prova_de_projecao_recusa_membro_faltante() -> None:
    """A documented member that never reaches the artifact is also a hard error."""
    with pytest.raises(RenderError):
        mod._require_projection({"groupId": "sg-1"}, mod._GROUP_COLUMNS, mod._GROUP_PROJECTED, "SecurityGroup")


def test_o_renderer_recusa_um_grupo_com_fk_orfa(estate: CanonicalEstate) -> None:
    """A security group pointing at a resource that is not in the estate is a hard error.

    Without the resource there is no tag set and no region, and both are documented -- the tag
    set is a member of ``SecurityGroup`` and the region is what the envelope is scoped by. A
    group that silently lost its resource would render as a posture fact with nothing behind it.
    """
    orfa = AwsSecurityGroup(
        resource_uuid="00000000-0000-0000-0000-00000000ffff",
        group_id="sg-orfa",
        group_name="security_group-orfa",
        group_description="security_group-orfa",
        owner_id="000000000000",
        vpc_id="vpc-0000000000000000",
        ingress=(
            AwsIpPermission(
                ip_protocol="tcp", from_port=22, to_port=22, ip_ranges=(AwsIpRange("0.0.0.0/0"),)
            ),
        ),
    )
    adulterado = replace(estate, aws_security_groups=(*estate.aws_security_groups, orfa))
    with pytest.raises(RenderError, match="FK orfa"):
        mod._groups_by_scope(adulterado)