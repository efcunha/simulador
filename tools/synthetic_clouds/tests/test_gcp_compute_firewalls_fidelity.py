"""Golden tests for ``gcp/compute-firewalls``.

The point of this module is to confront the DELIVERED artifact with
``specs/gcp/compute-firewalls.schema.json`` -- names, values and the empty contract -- and to
hold the judgement calls this surface makes, which are the ones a firewall-rule surface invites
getting quietly wrong:

1. **the rule carries TWO decision lists.** The canonical ``SecurityRule`` (Azure NSG) has one
   rule with an ``access`` and a ``priority``; ``AwsIpPermission`` has neither, because the AWS
   rule is allow-only. The GCP resource publishes ``allowed[]`` AND ``denied[]`` side by side, so
   the model grew its own type. A test that only checked names would never notice a ``denied``
   list missing, or a single ``access`` field being invented;
2. **``direction`` IS a member here.** In AWS the direction is the NAME of the list that holds
   the rule and no member exists; the GCP resource publishes it. Collapsing it into the list name
   would invent a member, and keeping two directions in one rule would invent the opposite;
3. **ports are STRINGS that accept ranges.** ``["22"]`` and ``["12345-12349"]``, never
   ``fromPort``/``toPort``. The range is the whole reason a consumer has to parse the string;
4. **an entry with no ports means "any port"**, and that is what the page says -- so the
   consumer's "todo o trafego" branch is reachable twice, once by protocol ``all`` and once by
   absent ports;
5. **the envelope is per PROJECT and global**;
6. **the posture answers in BOTH directions**, which is what makes this surface useful rather
   than merely present.

The two-sided proof here runs the consumer's OWN logic -- ``GCPSecurityScanner``'s
``_list_open_firewalls`` -- over the delivered artifact, through the googleapiclient attribute
names it reads (``allowed.I_p_protocol``, ``source_ranges``, ``direction``, ``disabled``). That
matters because the artifact carries the OFFICIAL JSON name ``IPProtocol`` while the consumer
reads the mangled proto attribute; the bridge between the two is asserted here rather than
assumed.
"""

from __future__ import annotations

import json
import re
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest

from tools.synthetic_clouds.fidelity.checker import check_artifact, is_faithful
from tools.synthetic_clouds.fidelity.spec import load_spec
from tools.synthetic_clouds.generate.estate_builder import build_estate
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.network import (
    GCP_FIREWALL_ANY_RANGE,
    GCP_FIREWALL_INTERNAL_RANGE,
    GcpFirewallEntry,
    GcpFirewallRule,
)
from tools.synthetic_clouds.render import compute_firewalls as mod
from tools.synthetic_clouds.render.base import RenderError, registered_names

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SPEC_FILE = "gcp/compute-firewalls.schema.json"
_SPEC_PATH = _REPO_ROOT / "specs" / _SPEC_FILE

#: The five sets, in documentation order, with the artifact that carries each.
_SCOPES: tuple[tuple[str, str], ...] = (
    ("firewall-list-response.json", mod.LIST_SCOPE),
    ("firewall.json", mod.FIREWALL_SCOPE),
    ("firewall-protocol-entry.json", mod.ENTRY_SCOPE),
    ("firewall-log-config.json", mod.LOG_SCOPE),
    ("request-parameters.json", mod.REQUEST_SCOPE),
)

#: The critical ports ``GCPSecurityScanner`` evaluates, transcribed from ``_CRITICAL_PORTS``, and
#: the subset it grades CRITICAL rather than HIGH. Held here so a change in the consumer is a
#: visible diff in this file and not a silent drift in what the fixture claims to exercise.
_CRITICAL_PORTS: dict[int, str] = {
    22: "SSH",
    3389: "RDP",
    5432: "PostgreSQL",
    3306: "MySQL",
    1433: "MSSQL",
    27017: "MongoDB",
    6379: "Redis",
    9200: "Elasticsearch",
}
_CRITICAL_SEVERITY = (22, 3389, 5432, 3306)


@pytest.fixture(scope="module")
def estate() -> CanonicalEstate:
    """The base small estate (seed 123): the networks every firewall rule points at."""
    return build_estate(seed=123, profile="small", currency="USD")


@pytest.fixture(scope="module")
def spec() -> Any:
    return load_spec(_SPEC_PATH)


@pytest.fixture(scope="module")
def tree(estate: CanonicalEstate, tmp_path_factory: pytest.TempPathFactory) -> Path:
    written = mod.ComputeFirewallsRenderer().render(estate, tmp_path_factory.mktemp("firewalls"))
    assert written
    return written[0].parent


def _load(tree: Path, name: str) -> Any:
    return json.loads((tree / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def responses(tree: Path) -> list[dict[str, Any]]:
    return cast("list[dict[str, Any]]", _load(tree, "firewall-list-response.json"))


@pytest.fixture(scope="module")
def firewalls(tree: Path) -> list[dict[str, Any]]:
    return cast("list[dict[str, Any]]", _load(tree, "firewall.json"))


@pytest.fixture(scope="module")
def entries(tree: Path) -> list[dict[str, Any]]:
    return cast("list[dict[str, Any]]", _load(tree, "firewall-protocol-entry.json"))


# -- the renderer is wired ----------------------------------------------------


def test_o_renderer_esta_registrado() -> None:
    assert mod.RENDER_DIR in registered_names()
    assert mod.ComputeFirewallsRenderer.name == "compute_firewalls"


def test_a_spec_cita_a_acao_e_a_data_da_consulta(spec: Any) -> None:
    assert spec.surface == mod.SURFACE == "gcp/compute-firewalls"
    assert spec.provider == "gcp"
    assert spec.reference["url"].endswith("/rest/v1/firewalls")
    assert spec.reference["consulted_at"] == "2026-10-18"


def test_a_spec_tem_os_cinco_conjuntos_documentados(spec: Any) -> None:
    assert [s.name for s in spec.sets] == [
        "firewall-list-response",
        "firewall",
        "protocol-entry",
        "firewall-log-config",
        "request-parameters",
    ]
    # 6 + 20 + 2 + 2 + 6
    assert len(spec.names) == 36


def test_a_entrega_e_json_e_read_api(spec: Any) -> None:
    assert spec.delivery["kind"] == "read_api"
    assert spec.delivery["format"] == "json"
    # The scope of the call is the PROJECT and nothing else: no region appears in the path.
    assert spec.delivery["path_template"] == "projects/{project}/global/firewalls"


def test_o_protocolo_all_esta_registrado_como_topico_e_nao_como_campo(spec: Any) -> None:
    """``IPProtocol = "all"`` is a VALUE the API returns, and a gap in the field page's prose.

    It is a topic (``item``), not a ``field``: registering it as a field would put the string
    ``allowed[].IPProtocol = "all"`` in ``forbidden_names`` and forbid the very value Google's
    own ``gcloud compute firewall-rules list`` output carries for ``default-allow-internal``.
    """
    topicos = [topic.name for topic in spec.unverified_topics]
    assert 'allowed[].IPProtocol = "all"' in topicos
    assert not spec.unverified, f"um valor de dominio nao pode virar nome de campo proibido: {spec.unverified}"
    assert not spec.forbidden_names


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

    An ingestor of ``firewall.json`` must not see a key no cloud documents, so the gaps are
    reported in ``_provenance.json``.
    """
    report = _load(tree, mod.PROVENANCE_PATH)
    assert report["kind"] == "provenance"
    assert report["surface"] == mod.SURFACE
    assert report["spec"] == f"specs/{_SPEC_FILE}"
    lacunas = {entry["field"] for entry in report["model_gaps"]}
    assert {"id", "creationTimestamp", "selfLink", "params", "request-parameters"} <= lacunas
    assert all(entry["reason"].strip() for entry in report["model_gaps"])
    assert all(entry["reason"].strip() for entry in report["derivations"])


def test_a_rede_derivada_esta_marcada_como_pendente(tree: Path) -> None:
    """The one shape this estate asserts without carrying the fact must SAY it is derived.

    ``network`` is the segment's own ``segment_id`` verbatim -- a real model fact -- but a GCP VPC
    network is GLOBAL and this estate has one network per (project, region). A silent value would
    read like something GCP produced.
    """
    report = _load(tree, mod.PROVENANCE_PATH)
    derivacoes = {entry["field"]: entry for entry in report["derivations"]}
    assert "network" in derivacoes
    assert derivacoes["network"]["status"] == "TODO-verificar"
    assert "global" in derivacoes["network"]["reason"].lower()


def test_as_regras_implicitas_sao_declaradas_como_nao_geradas(tree: Path) -> None:
    """The two implied rules must be registered as NOT generated, and absent from the artifact.

    Every VPC has an ingress-deny-all and an egress-allow-all at priority 65535 that
    ``firewalls.list`` does not return. Silently omitting them would make the artifact look like a
    complete picture of what protects the network; declaring them is what says otherwise.
    """
    report = _load(tree, mod.PROVENANCE_PATH)
    nao_gerados = {entry["field"] for entry in report["not_generated"]}
    assert any("implicitas" in field for field in nao_gerados)
    nomes = {registro["name"] for registro in _load(tree, "firewall.json")}
    assert not {"implied-allow-all", "implied-deny-all-ingress"} & nomes


# -- the rule shape is the PUBLISHED one --------------------------------------


def test_nenhuma_regra_carrega_membro_de_regra_de_outra_nuvem(firewalls: list[dict[str, Any]]) -> None:
    """No NSG member and no AWS member may appear in a ``Firewall``.

    ``SecurityRule`` (Azure) carries ``access``, ``sourcePortRange``/``destinationPortRange`` and a
    100..4096 ``priority``; ``IpPermission`` (AWS) carries ``fromPort``/``toPort``. Folding the GCP
    rule into either shape would invent a decision member GCP does not publish and erase the
    port list that IS how GCP publishes a range.
    """
    proibidos = {
        "access",
        "fromPort",
        "toPort",
        "protocol",
        "ipProtocol",
        "sourcePortRange",
        "destinationPortRange",
        "IpPermissions.N",
        "IpPermissionsEgress.N",
        "IpRanges.N",
        "cidrIp",
    }
    for registro in firewalls:
        assert not proibidos & set(registro), f"membro de outra nuvem no Firewall: {proibidos & set(registro)}"


def test_a_decisao_sao_duas_listas_e_nao_um_campo(firewalls: list[dict[str, Any]]) -> None:
    """``allowed[]`` AND ``denied[]`` are BOTH present, always.

    A single ``access`` field would be the NSG's shape, which this resource does not have. A
    missing ``denied`` list would understate a format that publishes it, and a rule that fills both
    would publish a combination the page calls impossible.
    """
    for registro in firewalls:
        assert isinstance(registro["allowed"], list), registro["name"]
        assert isinstance(registro["denied"], list), registro["name"]
        assert "access" not in registro
        assert "decision" not in registro
        assert not registro["allowed"] or registro["allowed"], registro["name"]
        # The page closes the two target containers against the service accounts; nothing in this
        # estate fills either, but the exclusivity is stated so a future estate is caught.
        assert not registro["targetServiceAccounts"] or not registro["targetTags"]


def test_o_estado_tem_regras_que_so_negam(firewalls: list[dict[str, Any]]) -> None:
    """At least one rule must exercise ``denied[]``.

    A fixture whose ``denied`` list is empty everywhere would look exactly like a fixture of a
    format that has no such member -- which is the AWS case, and the opposite of this one.
    """
    assert [registro["name"] for registro in firewalls if registro["denied"]]


def test_a_direcao_e_membro_e_uma_regra_tem_uma_somente(firewalls: list[dict[str, Any]]) -> None:
    """``direction`` is a real member here, and a rule is never both ways.

    "A single rule cannot apply to both ingress and egress traffic." Two rules merged into one
    would make the finding point at a rule that does not exist.
    """
    for registro in firewalls:
        assert registro["direction"] in ("INGRESS", "EGRESS"), registro["name"]
    assert any(registro["direction"] == "EGRESS" for registro in firewalls)
    assert any(registro["direction"] == "INGRESS" for registro in firewalls)


def test_regra_de_saida_nao_traz_origem_e_traz_destino(firewalls: list[dict[str, Any]]) -> None:
    """Origin belongs to ingress, destination to egress -- never both on one rule.

    The page says "For EGRESS traffic, you cannot specify the sourceTags fields", and separates
    ``sourceRanges`` from ``destinationRanges``; filling both on one rule would publish a rule the
    source does not describe.
    """
    for registro in firewalls:
        if registro["direction"] == "INGRESS":
            assert not registro["destinationRanges"], registro["name"]
        else:
            assert not registro["sourceRanges"], registro["name"]
            assert not registro["sourceTags"], registro["name"]
            assert registro["destinationRanges"], registro["name"]


def test_as_portas_sao_strings_e_aceitam_faixa(entries: list[dict[str, Any]]) -> None:
    """Each port entry is an integer or a RANGE, as a string -- never a number, never a pair.

    "Each entry must be either an integer or a range." Normalising ``"0-65535"`` into two integers
    would erase the thing the format publishes, and a consumer that reads the string is the reason
    the range is in the contract at all.
    """
    faixa = re.compile(r"^\d+(-\d+)?$")
    for tupla in entries:
        assert isinstance(tupla["ports"], list), tupla
        for porta in tupla["ports"]:
            assert isinstance(porta, str), f"porta nao e string: {porta!r}"
            assert faixa.match(porta), f"fora de 'inteiro ou faixa': {porta!r}"
            if "-" in porta:
                inicio, fim = (int(parte) for parte in porta.split("-"))
                assert inicio <= fim, porta


def test_uma_tupla_sem_portas_significa_qualquer_porta(entries: list[dict[str, Any]]) -> None:
    """No ports means "any port" -- and that is EMPTY, not a zero, a dash or "0-65535".

    "If not specified, this rule applies to connections through any port." The four published
    shapes for the same effect would each be a value the API does not return here.
    """
    sem_porta = [tupla for tupla in entries if not tupla["ports"]]
    assert sem_porta, "o estate nao produz a tupla sem porta que a pagina descreve"
    for tupla in sem_porta:
        assert tupla["ports"] == []
        assert "0-65535" not in tupla["ports"]
    # E a forma PREENCHIDA existe tambem, com faixa -- senao o contrato de faixa nunca seria
    # exercitado e a tupla vazia seria a unica forma do artefato.
    assert any(tupla["ports"] for tupla in entries)


def test_o_nome_do_protocolo_e_o_oficial(entries: list[dict[str, Any]]) -> None:
    """The member is ``IPProtocol`` -- capitals and no separator.

    Not ``protocol``, not ``ip_protocol``. The consumer reads ``allowed.I_p_protocol``, which is
    the ATTRIBUTE googleapiclient derives from this JSON name; writing the attribute name into the
    artifact would be writing the library's spelling instead of the API's.
    """
    assert entries
    for tupla in entries:
        assert "IPProtocol" in tupla
        assert "ip_protocol" not in tupla
        assert "I_p_protocol" not in tupla
        assert isinstance(tupla["IPProtocol"], str) and tupla["IPProtocol"]
    # O dominio e nome-ou-numero: a pagina aceita um nome conhecido OU o numero do protocolo.
    assert {tupla["IPProtocol"] for tupla in entries} & {"tcp", "udp", "icmp", "all"}


def test_o_container_de_entrada_e_de_saida_tem_a_mesma_forma(entries: list[dict[str, Any]]) -> None:
    """Both lists carry the SAME two members -- the GCP publishes no second type for ``denied``.

    Folding ``allowed[]`` and ``denied[]`` into one set is what the API does; giving ``denied`` a
    shape of its own would be a member GCP does not publish.
    """
    assert {frozenset(tupla) for tupla in entries} == {frozenset({"IPProtocol", "ports"})}


def test_as_colunas_de_saida_do_servidor_vao_vazias(firewalls: list[dict[str, Any]]) -> None:
    """``id``, ``selfLink`` and ``creationTimestamp`` are server-defined; ``params`` is request-only.

    All four are emitted -- omitting them would understate the format -- and all four are empty,
    because the estate carries no server id, no resource URL, no creation instant, and a request
    member never appears in a response.
    """
    for registro in firewalls:
        assert registro["id"] is None, registro["name"]
        assert registro["selfLink"] is None, registro["name"]
        assert registro["creationTimestamp"] is None, registro["name"]
        assert registro["params"] == {}, registro["name"]
    # ``kind`` is the one output-only column the page gives a CONSTANT for, so it is filled.
    assert {registro["kind"] for registro in firewalls} == {"compute#firewall"}


def test_o_log_so_carrega_metadado_quando_habilitado(tree: Path) -> None:
    """``metadata`` only has a value when logging is on.

    "This field can only be specified for a particular firewall rule if logging is enabled for
    that rule." Carrying the enum on a rule with logging off would publish a combination the page
    forbids.
    """
    log_configs = cast("list[dict[str, Any]]", _load(tree, "firewall-log-config.json"))
    assert log_configs
    assert any(config["enable"] for config in log_configs)
    assert any(not config["enable"] for config in log_configs)
    for config in log_configs:
        if config["enable"]:
            assert config["metadata"] in ("EXCLUDE_ALL_METADATA", "INCLUDE_ALL_METADATA"), config
        else:
            assert config["metadata"] is None, config


def test_o_envelope_e_por_projeto_e_nao_por_regiao(responses: list[dict[str, Any]], estate: CanonicalEstate) -> None:
    """One envelope per PROJECT, and the items are alphabetical by name.

    The path is ``projects/{project}/global/firewalls``: a firewall rule is a global resource and
    only the subnetwork is regional. The alphabetical order is the one ``orderBy`` declares as the
    default.
    """
    projetos = {regra.scope_id for regra in estate.gcp_firewall_rules}
    assert len(responses) == len(projetos), "um envelope por projeto, nao um por (projeto, regiao)"
    for envelope in responses:
        assert envelope["kind"] == "compute#firewallList"
        assert envelope["nextPageToken"] is None
        assert envelope["id"] is None
        assert envelope["selfLink"] is None
        assert envelope["warning"] == {}
        nomes = [item["name"] for item in envelope["items"]]
        assert nomes == sorted(nomes), nomes
        # Uma rede so por envelope provaria que o recorte por regiao voltou a entrar por outra porta.
        assert len({item["network"] for item in envelope["items"]}) > 1


def test_o_envelope_carrega_exatamente_as_regras_do_projeto(
    responses: list[dict[str, Any]], estate: CanonicalEstate
) -> None:
    """The envelope is the source of truth for the flattened artifact.

    ``firewall.json`` is derived from ``items``, never assembled in parallel; if they ever diverge
    there would be two answers to "which rules does this project have".
    """
    por_projeto: dict[str, set[str]] = {}
    for regra in estate.gcp_firewall_rules:
        por_projeto.setdefault(regra.scope_id, set()).add(regra.rule_name)
    assert len(responses) == len(por_projeto)
    for envelope in responses:
        redes = {item["network"] for item in envelope["items"]}
        projetos = {re.search(r"projects/([^/]+)/global/", rede).group(1) for rede in redes}  # type: ignore[union-attr]
        assert len(projetos) == 1, f"envelope misturou projetos: {projetos}"
        projeto = projetos.pop()
        assert {item["name"] for item in envelope["items"]} == por_projeto[projeto]


def test_o_conjunto_de_request_e_um_documento_de_forma(tree: Path) -> None:
    """The six request-side names are present and null: no request was captured."""
    documento = _load(tree, "request-parameters.json")
    assert set(documento) == {
        "filter",
        "maxResults",
        "orderBy",
        "pageToken",
        "project",
        "returnPartialSuccess",
    }
    assert all(value is None for value in documento.values())


# -- the posture answers the consumer in BOTH directions ----------------------


def _regras_por_projeto(estate: CanonicalEstate) -> dict[str, list[GcpFirewallRule]]:
    por_projeto: dict[str, list[GcpFirewallRule]] = {}
    for regra in estate.gcp_firewall_rules:
        por_projeto.setdefault(regra.scope_id, []).append(regra)
    return {k: sorted(v, key=lambda g: g.rule_name) for k, v in sorted(por_projeto.items())}


def test_o_estado_tem_regras_expostas_e_regras_restritas(estate: CanonicalEstate) -> None:
    """The estate must be able to answer COMPLIANT AND NON-COMPLIANT for the same check.

    An estate that only exposed would prove nothing: a consumer with the ports backwards, or one
    ignoring the source CIDR, would score identically. This is the assertion that keeps the posture
    from collapsing into a single case.
    """
    regras = [r for valores in _regras_por_projeto(estate).values() for r in valores]
    assert regras

    expostas = [r for r in regras if r.exposes_to_anywhere and _portas_criticas(r)]
    restritas = [r for r in regras if not r.exposes_to_anywhere and r.allowed and r.source_ranges]
    assert expostas, "nenhuma regra expoe porta critica: o consumidor nunca seria NON_COMPLIANT"
    assert restritas, "nenhuma regra restringe a origem: so haveria exposicao"

    # As duas metades do par que o consumidor avalia: uma regra com origem aberta e porta critica,
    # e a MESMA forma com origem restrita.
    ssh_exposta = [r for r in expostas if any(e.ip_protocol == "tcp" and ("22" in e.ports) for e in r.allowed)]
    ssh_restrita = [r for r in restritas if any(e.ip_protocol == "tcp" and ("22" in e.ports) for e in r.allowed)]
    assert ssh_exposta, "SSH nunca seria NON_COMPLIANT"
    assert ssh_restrita, "SSH nunca seria COMPLIANT: a origem nao seria distinguida"


def test_o_estado_exercita_cada_ramo_da_verificacao(estate: CanonicalEstate) -> None:
    """Every branch the consumer can take must be reachable from this estate.

    Branch by branch: direction (an EGRESS rule), ``disabled``, the source CIDR, the protocol
    filter, ``protocol == "all"``, ``not ports``, a port range that CONTAINS a critical port, and a
    port that is not critical at all. A branch with no fixture is a branch this state cannot teach.
    """
    regras = [r for valores in _regras_por_projeto(estate).values() for r in valores]
    assert any(r.direction == "EGRESS" for r in regras), "ramo da direcao"
    # ``exposes_to_anywhere`` JA exclui as desabilitadas, entao o ramo do ``disabled`` se prova pela
    # forma bruta: origem aberta E desabilitada. Usar a propriedade aqui seria um assert que nunca
    # pode passar.
    assert any(r.disabled and GCP_FIREWALL_ANY_RANGE in r.source_ranges for r in regras), "ramo do disabled"
    assert any(
        GCP_FIREWALL_INTERNAL_RANGE in r.source_ranges for r in regras
    ), "ramo da origem diferente de 0.0.0.0/0"
    protocolos = {e.ip_protocol for r in regras for e in r.allowed}
    assert {"all", "tcp", "udp", "icmp"} <= protocolos, f"faltam protocolos: {protocolos}"
    assert any(e.ip_protocol == "all" and not e.ports for r in regras for e in r.allowed), "ramo protocol == all"
    assert any(e.ip_protocol == "tcp" and not e.ports for r in regras for e in r.allowed), "ramo not ports"
    assert any("5432" in e.ports for r in regras for e in r.allowed), "porta critica de grau CRITICAL"
    assert any("6379" in e.ports for r in regras for e in r.allowed), "porta critica de grau HIGH"
    assert any(
        e.ip_protocol == "tcp" and e.ports and not {"22", "5432", "6379", "3389", "3306"} & set(e.ports)
        for r in regras
        for e in r.allowed
    ), "origem aberta sem nenhuma porta critica"


def _portas_criticas(regra: GcpFirewallRule) -> set[int]:
    """As portas criticas que a regra expoe, segundo a MESMA conta do consumidor."""
    if not regra.exposes_to_anywhere:
        return set()
    achadas: set[int] = set()
    for entrada in regra.allowed:
        if entrada.ip_protocol not in ("tcp", "udp", "all"):
            continue
        for faixa in entrada.ports:
            for porta in _CRITICAL_PORTS:
                if _port_in_range(porta, faixa):
                    achadas.add(porta)
    return achadas


def _port_in_range(porta: int, faixa: str) -> bool:
    """The consumer's own ``_port_in_range``, transcribed."""
    if "-" in faixa:
        partes = faixa.split("-")
        return int(partes[0]) <= porta <= int(partes[1])
    return int(faixa) == porta


# -- THE TWO-SIDED PART: the consumer's own logic, over the DELIVERED artifact ----
#
# ``<arvore-do-consumidor>`` is the FinOps tree, which this simulator deliberately does NOT depend on
# -- ``conftest.py`` archives the tests that measure it for exactly that reason. So the consumer's
# logic is TRANSCRIBED rather than imported, and the transcription is kept honest by three things:
# it runs over ``firewall-list-response.json`` as DELIVERED (running it over the model would prove
# nothing about the wire), it is a line-for-line copy of ``GCPSecurityScanner._list_open_firewalls``,
# and it reaches the protocol through the same ``I_p_protocol`` attribute the real scanner reads.
#
# That last point needs proof rather than assertion. The artifact carries the OFFICIAL JSON name
# ``IPProtocol`` and the scanner reads the mangled proto attribute; nothing in the fixture would
# fail if those two names drifted apart, because the fixture has no idea the consumer exists. So
# the bridge is asserted here -- including that it is load-bearing, not decorative.


class _ProtoAllowed:
    """One ``allowed[]`` entry as the dynamic message the scanner iterates.

    The two members the scanner reads are declared as ANNOTATIONS, not as class attributes: an
    annotation without a value does not create the attribute, so a member the artifact does not
    carry still raises ``AttributeError`` the way the real dynamic message would -- which is what
    the "load-bearing" test below depends on. A default (``ports: list[str] = []``) would hide it.
    """

    I_p_protocol: str
    ports: list[str]


class _ProtoFirewall:
    """A ``googleapiclient`` dynamic message over one delivered ``Firewall`` JSON.

    googleapiclient exposes each JSON name as an ATTRIBUTE whose spelling is that name mangled
    into a Python identifier, and the scanner reads ``allowed.I_p_protocol`` -- not ``IPProtocol``.
    The artifact has to carry the API's name; this object is the one place the library's spelling
    is allowed to exist, so the translation is a visible line instead of a convention. The rule's
    own members are renamed the same way (``sourceRanges`` -> ``source_ranges``) because that is
    what the real dynamic message does.
    """

    #: JSON name -> the attribute name googleapiclient derives from it.
    ATTRIBUTES = {"IPProtocol": "I_p_protocol", "sourceRanges": "source_ranges"}

    #: The members the scanner reads off the rule itself, declared for the type checker. As with
    #: :class:`_ProtoAllowed`, annotations only -- they must not create attributes.
    name: str
    network: str
    direction: str
    disabled: bool
    source_ranges: list[str]
    allowed: list[_ProtoAllowed]

    def __init__(self, registro: dict[str, Any]) -> None:
        for nome_json, valor in registro.items():
            setattr(self, self.ATTRIBUTES.get(nome_json, nome_json), valor)
        self.allowed = [_ProtoFirewall._allowed(entrada) for entrada in registro.get("allowed") or []]

    @classmethod
    def _allowed(cls, entrada: dict[str, Any]) -> _ProtoAllowed:
        allowed = _ProtoAllowed()
        for nome_json, valor in entrada.items():
            setattr(allowed, cls.ATTRIBUTES.get(nome_json, nome_json), valor)
        return allowed


def _consumer_findings(itens: list[_ProtoFirewall], project_id: str = "proj") -> list[dict[str, Any]]:
    """``GCPSecurityScanner._list_open_firewalls``, transcribed line for line.

    Deliberately literal -- no helpers, no early exits, no simplification -- because the value of
    this proof is that it is recognisably THE SAME function. Every ``continue`` is the scanner's
    own, and so is the port/severity split.
    """
    findings: list[dict[str, Any]] = []
    for rule in itens:
        if rule.direction != "INGRESS" or rule.disabled:
            continue

        # Verifica se permite 0.0.0.0/0
        if "0.0.0.0/0" not in (rule.source_ranges or []):
            continue

        for allowed in rule.allowed or []:
            protocol = allowed.I_p_protocol
            if protocol not in ("tcp", "udp", "all"):
                continue

            ports = allowed.ports or []
            if protocol == "all" or not ports:
                # ALL traffic aberto
                findings.append(
                    {
                        "severity": "CRITICAL",
                        "category": "FIREWALL",
                        "resource_id": f"projects/{project_id}/global/firewalls/{rule.name}",
                        "resource_type": "compute.googleapis.com/Firewall",
                        "region": "global",
                        "branch": "todo-o-trafego",
                    }
                )
                continue

            # Verifica portas específicas
            for port_range in ports:
                for port, name in _CRITICAL_PORTS.items():
                    if _port_in_range(port, port_range):
                        findings.append(
                            {
                                "severity": "CRITICAL" if port in (22, 3389, 5432, 3306) else "HIGH",
                                "category": "FIREWALL",
                                "resource_id": f"projects/{project_id}/global/firewalls/{rule.name}",
                                "resource_type": "compute.googleapis.com/Firewall",
                                "region": "global",
                                "branch": f"porta-{port}-{name}",
                            }
                        )
    return findings


def _itens_do_consumidor(responses: list[dict[str, Any]]) -> list[_ProtoFirewall]:
    """The rules the scanner would iterate, straight out of the delivered envelopes."""
    return [_ProtoFirewall(item) for envelope in responses for item in envelope["items"]]


def test_a_ponte_entre_o_nome_oficial_e_o_atributo_do_consumidor_existe(responses: list[dict[str, Any]]) -> None:
    """``IPProtocol`` on the wire becomes ``I_p_protocol`` on the object the scanner reads.

    This is the assertion the whole surface rests on: the scanner's line is
    ``protocol = allowed.I_p_protocol``. If the artifact spelled the member anything else, the
    scanner would raise on a real project and the fixture would still look perfect.
    """
    assert _ProtoFirewall.ATTRIBUTES["IPProtocol"] == "I_p_protocol"

    item = dict(responses[0]["items"][0])
    regra = _ProtoFirewall(item)
    # A regra inteira atravessa a ponte: origem, direcao, desabilitada e nome.
    assert regra.source_ranges == item["sourceRanges"]
    assert regra.direction == item["direction"]
    assert regra.disabled == item["disabled"]
    assert regra.name == item["name"]
    assert regra.network == item["network"]
    # E cada tupla de ``allowed`` e ``denied`` que a regra carrega.
    for original, traduzida in zip(item["allowed"], regra.allowed, strict=True):
        assert traduzida.I_p_protocol == original["IPProtocol"]
        assert traduzida.ports == original["ports"]


def test_o_consumidor_responde_nao_compliant_no_faixa(responses: list[dict[str, Any]]) -> None:
    """The scanner's logic, over the delivered artifact, must FIND the exposed rules."""
    findings = _consumer_findings(_itens_do_consumidor(responses))
    assert findings, "o consumidor nao produz achado nenhum: o estado nao exercita a postura exposta"

    assert {achado["severity"] for achado in findings} == {"CRITICAL", "HIGH"}
    assert {achado["category"] for achado in findings} == {"FIREWALL"}
    assert {achado["region"] for achado in findings} == {"global"}
    assert all(achado["resource_type"] == "compute.googleapis.com/Firewall" for achado in findings)

    # Os dois ramos de "todo o trafego" tem de aparecer: o do protocolo ``all`` e o das portas
    # ausentes. Sao caminhos diferentes da mesma API, e so um deles presente deixaria o outro
    # ramo sem fixture.
    ramos = {achado["branch"] for achado in findings}
    assert "todo-o-trafego" in ramos
    assert {"porta-22-SSH", "porta-3389-RDP"} <= ramos


def test_o_consumidor_responde_compliant_no_faixa(responses: list[dict[str, Any]]) -> None:
    """And it must stay SILENT on the restricted rules in the SAME artifact.

    Both verdicts in one response is what makes this state teachable: a consumer with the ports
    inverted, or one that ignored ``sourceRanges``, would not produce this split.
    """
    findings = _consumer_findings(_itens_do_consumidor(responses))
    reportados = {achado["resource_id"].rsplit("/", 1)[-1] for achado in findings}

    todos = {item["name"] for envelope in responses for item in envelope["items"]}
    silenciadas = todos - reportados
    assert silenciadas, "toda regra do artefato foi reportada: nao ha caso COMPLIANT"

    # Cada regra silenciada esta silenciada pelo motivo que a pagina sustenta -- e cada motivo e um
    # membro do recurso, nao uma coincidencia da fixture. Sem esta lista, um estado que so
    # expoesse pareceria silencioso por acaso.
    assert any("docs-range" in nome or "office-range" in nome for nome in silenciadas), (
        "nenhuma regra barrada pela origem: o filtro de sourceRanges ficou sem prova"
    )
    assert any("https" in nome or "web-from-anywhere" in nome for nome in silenciadas), (
        "nenhuma regra barrada pela porta: o filtro de portas ficou sem prova"
    )
    assert any("icmp" in nome for nome in silenciadas), (
        "nenhuma regra barrada pelo protocolo: o filtro de IPProtocol ficou sem prova"
    )
    assert any("disabled" in nome for nome in silenciadas), (
        "nenhuma regra barrada por disabled: o filtro de disabled ficou sem prova"
    )
    assert any("deny-all" in nome for nome in silenciadas), (
        "nenhuma regra barrada por so negar: denied[] ficou sem prova"
    )
    assert any(nome.startswith("egress-") for nome in silenciadas), (
        "nenhuma regra barrada pela direcao: o filtro de direction ficou sem prova"
    )
    assert any(nome == "default-allow-internal" for nome in silenciadas), (
        "a origem 10.128.0.0/9 das pre-populadas ficou sem prova"
    )


def test_o_consumidor_nao_pode_ler_uma_regra_com_o_nome_errado(responses: list[dict[str, Any]]) -> None:
    """Renaming the member makes the scanner RAISE -- the bridge is load-bearing.

    A mapping that merely happened to be convenient would pass a "it works" test. This shows the
    dependency is real: take ``IPProtocol`` off the wire and the consumer's own access pattern
    breaks, which is exactly what would happen in production.
    """
    item = next(
        (registro for envelope in responses for registro in envelope["items"] if registro["allowed"]),
        None,
    )
    assert item is not None, "o artefato nao tem regra com allowed[] para provar a ponte"
    # A renomeacao tem de alcancar as tuplas ANINHADAS: o protocolo mora em allowed[], nao no
    # recurso, e um teste que so renomeia o topo passaria sem provar nada.
    renomeado = {
        nome: ([{"protocol": e["IPProtocol"], "ports": e["ports"]} for e in valor] if nome == "allowed" else valor)
        for nome, valor in item.items()
    }
    regra = _ProtoFirewall(renomeado)

    with pytest.raises(AttributeError):
        _ = regra.allowed[0].I_p_protocol  # noqa: B018 - o acesso IS a prova


def test_a_ponte_so_renomeia_o_que_o_consumidor_le_com_outra_grafia(
    responses: list[dict[str, Any]],
) -> None:
    """No OTHER member may be mangled: the mapping is exactly the two the scanner needs.

    ``direction``, ``disabled``, ``name`` and ``network`` are read with their published spelling on
    both sides. Widening the mapping would let the artifact drift toward the library's vocabulary
    unnoticed -- which is the failure this bridge exists to catch.
    """
    assert set(_ProtoFirewall.ATTRIBUTES) == {"IPProtocol", "sourceRanges"}
    item = responses[0]["items"][0]
    regra = _ProtoFirewall(item)
    for nome in ("direction", "disabled", "name", "network"):
        assert getattr(regra, nome) == item[nome]


def test_o_campo_network_aponta_para_a_rede_do_mesmo_projeto(estate: CanonicalEstate) -> None:
    """Every rule's network is the segment's own id, inside the rule's own project.

    The value is a real model fact -- the segment carries the URL verbatim -- so this asserts no
    derivation happened: it is the segment's ``segment_id``, and the segment belongs to the same
    project the rule claims.
    """
    segmentos = {s.segment_uuid: s for s in estate.network_segments}
    for regra in estate.gcp_firewall_rules:
        segmento = segmentos[regra.segment_uuid]
        assert regra.network_url == segmento.segment_id
        assert segmento.provider == "gcp"
        assert segmento.scope_id == regra.scope_id
        assert regra.network_url == f"projects/{regra.scope_id}/global/networks/{segmento.name}"


def test_a_prioridade_de_cada_regra_dentro_da_faixa_publicada(estate: CanonicalEstate) -> None:
    """``priority`` is an integer 0..65535, and the pre-populated ones sit at 65534.

    The page publishes the range and says the default is 1000; the four default-network rules are
    all at 65534. A priority outside the range would be a rule the API rejects.
    """
    for regra in estate.gcp_firewall_rules:
        assert 0 <= regra.priority <= 65535, regra.rule_name
    pre = [r for r in estate.gcp_firewall_rules if r.is_prepopulated]
    assert pre
    assert {r.priority for r in pre} == {65534}
    assert {r.rule_name for r in pre} == {
        "default-allow-internal",
        "default-allow-ssh",
        "default-allow-rdp",
        "default-allow-icmp",
    }
    assert {r.source_ranges for r in pre if r.rule_name != "default-allow-internal"} == {(GCP_FIREWALL_ANY_RANGE,)}


def test_as_regras_pre_populadas_estao_na_mesma_rede_de_cada_projeto(estate: CanonicalEstate) -> None:
    """All four pre-populated rules sit on ONE network PER PROJECT -- the project's "default" one.

    They are the state of a single network, so splitting one project's four rules across its three
    networks would describe three networks each with one default rule, which no project has. The
    count is per project: each project has its own default network.
    """
    por_projeto: dict[str, set[str]] = {}
    for regra in estate.gcp_firewall_rules:
        if regra.is_prepopulated:
            por_projeto.setdefault(regra.scope_id, set()).add(regra.segment_uuid)
    assert len(por_projeto) >= 2, "a prova precisa de mais de um projeto para valer"
    for projeto, redes in por_projeto.items():
        assert len(redes) == 1, f"projeto {projeto} espalhou as pre-populadas em {len(redes)} redes"


# -- determinism and fail-closed projection -----------------------------------


def test_o_render_e_deterministico(estate: CanonicalEstate, tmp_path: Path) -> None:
    primeiro = mod.ComputeFirewallsRenderer().render(estate, tmp_path / "a")
    segundo = mod.ComputeFirewallsRenderer().render(estate, tmp_path / "b")
    assert [p.name for p in primeiro] == [p.name for p in segundo]
    for a, b in zip(primeiro, segundo, strict=True):
        assert a.read_bytes() == b.read_bytes(), a.name


def _firewall_completo(**mudancas: Any) -> dict[str, Any]:
    """A full ``Firewall`` record, differing only in the members under test.

    ``_require_projection`` checks the member SET first, so a proof about one member has to carry
    the other nineteen -- otherwise the call fails for the wrong reason and the test would pass
    without ever reaching the rule it is about.
    """
    registro: dict[str, Any] = {
        "allowed": [],
        "creationTimestamp": None,
        "denied": [],
        "description": "d",
        "destinationRanges": [],
        "direction": "INGRESS",
        "disabled": False,
        "id": None,
        "kind": "compute#firewall",
        "logConfig": {"enable": False, "metadata": None},
        "name": "n",
        "network": "projects/p/global/networks/net",
        "params": {},
        "priority": 1000,
        "selfLink": None,
        "sourceRanges": [],
        "sourceServiceAccounts": [],
        "sourceTags": [],
        "targetServiceAccounts": [],
        "targetTags": [],
    }
    registro.update(mudancas)
    return registro


def test_a_prova_de_projecao_recusa_coluna_sem_fonte_no_modelo() -> None:
    """``_require_projection`` fails closed: a value with no model source is an error.

    ``id`` is the real case. It belongs to the format and is projected by nobody -- the server
    assigns it -- so filling it is rejected by the code path, not merely left undone by convention.
    """
    assert "id" not in mod._FIREWALL_PROJECTED
    with pytest.raises(RenderError, match="sem fonte no modelo canonico"):
        mod._require_projection(_firewall_completo(id="1234567890"), mod._FIREWALL_COLUMNS, mod._FIREWALL_PROJECTED, "Firewall")
    # The documented value the renderer actually writes passes the same proof.
    mod._require_projection(_firewall_completo(), mod._FIREWALL_COLUMNS, mod._FIREWALL_PROJECTED, "Firewall")


def test_a_prova_de_projecao_recusa_membro_faltante() -> None:
    """A documented member that never reaches the artifact is also a hard error."""
    with pytest.raises(RenderError):
        mod._require_projection({"name": "n"}, mod._FIREWALL_COLUMNS, mod._FIREWALL_PROJECTED, "Firewall")


def test_o_renderer_recusa_uma_regra_com_fk_orfa(estate: CanonicalEstate) -> None:
    """A firewall rule pointing at a network that is not in the estate is a hard error.

    ``Firewall.network`` publishes the URL of the network the rule protects. Without the segment
    there is no URL, and a rule that silently lost its network would render as a posture fact with
    nothing behind it.
    """
    orfa = GcpFirewallRule(
        segment_uuid="00000000-0000-0000-0000-00000000ffff",
        scope_id="contoso-prod-99",
        rule_name="allow-ssh-orfa",
        network_url="projects/contoso-prod-99/global/networks/net-orfa",
        direction="INGRESS",
        priority=1000,
        source_ranges=(GCP_FIREWALL_ANY_RANGE,),
        allowed=(GcpFirewallEntry(ip_protocol="tcp", ports=("22",)),),
    )
    adulterado = replace(estate, gcp_firewall_rules=(*estate.gcp_firewall_rules, orfa))
    with pytest.raises(RenderError, match="FK orfa"):
        mod._rules_by_project(adulterado)


def test_o_renderer_recusa_uma_regra_de_outro_projeto_que_a_sua_rede(estate: CanonicalEstate) -> None:
    """A rule whose project disagrees with its network's project is a hard error.

    The envelope is per project, so a rule claiming one project while sitting on another project's
    network would put two projects in one page -- the mistake this surface is most likely to make.
    """
    regra = next(r for r in estate.gcp_firewall_rules if r.is_prepopulated)
    adulterado = replace(regra, scope_id="contoso-prod-99")
    substituido = replace(
        estate, gcp_firewall_rules=tuple(adulterado if r is regra else r for r in estate.gcp_firewall_rules)
    )
    with pytest.raises(RenderError, match="diz projeto"):
        mod._rules_by_project(substituido)