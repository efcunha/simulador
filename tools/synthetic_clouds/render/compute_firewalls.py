"""Golden fixture for ``gcp/compute-firewalls``.

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
   ``fromPort``/``toPort``. The range is the whole reason a consumer has to parse the string, so a
   renderer that normalised ``"0-65535"`` into two integers would erase the thing being modelled;
4. **an entry with no ports means "any port"**, and that is what the page says. Writing an empty
   string, a zero or the string ``"0-65535"`` would each be a different value than the API
   publishes for the same effect;
5. **the envelope is per PROJECT and global.** ``projects/<p>/global/firewalls`` has no region, so
   an envelope per (project, region) would be a partition the API never performs;
6. **the posture answers in BOTH directions**, which is what makes this surface useful rather
   than merely present.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tools.synthetic_clouds.fidelity.spec import DEFAULT_SPECS_ROOT, SurfaceSpec, load_spec
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.network import (
    GCP_FIREWALL_KIND,
    GCP_FIREWALL_LIST_KIND,
    GcpFirewallEntry,
    GcpFirewallRule,
)
from tools.synthetic_clouds.render.base import RenderError

#: A spec de origem, sob ``specs/`` (nunca editada aqui).
_SPEC_FILE = "gcp/compute-firewalls.schema.json"

#: A superficie que este renderer produz, como a spec a nomeia.
SURFACE = "gcp/compute-firewalls"

#: O diretorio renderizado sob ``out_dir``.
RENDER_DIR = "compute_firewalls"

#: O relatorio de proveniencia, escrito ao lado dos dados (nunca dentro deles).
PROVENANCE_PATH = "_provenance.json"

# Os conjuntos da spec citada, pelo nome.
LIST_SCOPE = "firewall-list-response"
FIREWALL_SCOPE = "firewall"
ENTRY_SCOPE = "protocol-entry"
LOG_SCOPE = "firewall-log-config"
REQUEST_SCOPE = "request-parameters"

#: A pagina que publica a ordem PADRAO da lista: "Sorts list results by a certain order. By
#: default, results are returned in alpha[betical order]". E ela que decide a ordem dos itens de
#: cada envelope -- e uma afirmacao do provedor, nao uma convencao de iteracao.
ORDER_SOURCE_URL = "https://docs.cloud.google.com/compute/docs/reference/rest/v1/firewalls/list"

#: A tabela que declara as quatro regras pre-populadas da rede default, com nome, direcao,
#: prioridade, origem e o par protocolo:porta de cada uma.
PREPOPULATED_URL = "https://docs.cloud.google.com/firewall/docs/firewalls"

#: A saida oficial de ``gcloud compute firewall-rules list`` de um projeto recem-criado, que e o
#: que mostra ``default-allow-internal`` com a coluna ALLOW igual a ``all``.
ALL_PROTOCOL_URL = "https://docs.cloud.google.com/firewall/docs/using-firewalls"

#: A pagina que diz que toda rede VPC tem DUAS regras implicitas (uma de ingress que nega tudo e
#: uma de egress que libera tudo, prioridade 65535) que ``firewalls.list`` nao devolve.
IMPLIED_RULES_URL = "https://docs.cloud.google.com/firewall/docs/firewalls"

_spec: SurfaceSpec | None = None


def specification() -> SurfaceSpec:
    """Load (once) the cited specification for ``gcp/compute-firewalls``."""
    global _spec
    if _spec is None:
        _spec = load_spec(DEFAULT_SPECS_ROOT / _SPEC_FILE)
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


# The five sets, in documentation order -- derived, not retyped.
_LIST_COLUMNS: tuple[str, ...] = _names_of(LIST_SCOPE)
_FIREWALL_COLUMNS: tuple[str, ...] = _names_of(FIREWALL_SCOPE)
_ENTRY_COLUMNS: tuple[str, ...] = _names_of(ENTRY_SCOPE)
_LOG_COLUMNS: tuple[str, ...] = _names_of(LOG_SCOPE)
_REQUEST_COLUMNS: tuple[str, ...] = _names_of(REQUEST_SCOPE)

#: The columns each set can actually carry a VALUE in, derived from the model and not from a
#: literal. Everything else belongs to the format and must be emitted EMPTY -- a documented member
#: that never reaches the artifact is as unfaithful as one that carries a value nothing in the
#: model supports. The three output-only members (``id``, ``selfLink``, ``creationTimestamp``) and
#: the input-only ``params`` are absent here on purpose, and the provenance says why.
_LIST_PROJECTED: frozenset[str] = frozenset({"items", "kind"})
_FIREWALL_PROJECTED: frozenset[str] = frozenset(
    {
        "allowed",
        "denied",
        "description",
        "destinationRanges",
        "direction",
        "disabled",
        "kind",
        "logConfig",
        "name",
        "network",
        "priority",
        "sourceRanges",
    }
)
_ENTRY_PROJECTED: frozenset[str] = frozenset({"IPProtocol", "ports"})
_LOG_PROJECTED: frozenset[str] = frozenset({"enable", "metadata"})
_REQUEST_PROJECTED: frozenset[str] = frozenset()

#: The ``null-empty`` columns of the spec, by their own word rather than this module's docstring.
_NULL_EMPTY: frozenset[str] = specification().null_empty_names


def _is_empty(value: Any) -> bool:
    """True when ``value`` is this fixture's shape for "no value" (never for zero).

    Zero and ``False`` are REAL values here: ``priority`` is legitimately ``0`` and ``disabled``
    is legitimately ``false``, so treating them as empty would hide a rule that the API applies.
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


def _entry(entry: GcpFirewallEntry) -> dict[str, Any]:
    """Return the documented inline object of one ``allowed[]``/``denied[]`` tuple.

    ``ports`` keeps the PUBLISHED form: a list of strings, each one an integer or a range
    (``["12345-12349"]``), and EMPTY when the rule applies to any port. Empty here is the API's
    own representation of "through any port" -- not an absent member, and not ``"0-65535"``.
    """
    record: dict[str, Any] = {"IPProtocol": entry.ip_protocol, "ports": list(entry.ports)}
    _require_projection(record, _ENTRY_COLUMNS, _ENTRY_PROJECTED, f"tupla {entry.ip_protocol}")
    return record


def _log_config(rule: GcpFirewallRule) -> dict[str, Any]:
    """Return the documented ``FirewallLogConfig`` of one rule.

    ``metadata`` only carries a value when logging is on: the page says the field "can only be
    specified for a particular firewall rule if logging is enabled for that rule". A rule with
    logging off emits ``metadata`` empty rather than carrying the enum anyway.
    """
    record: dict[str, Any] = {"enable": rule.log_enabled, "metadata": rule.log_metadata}
    _require_projection(record, _LOG_COLUMNS, _LOG_PROJECTED, f"logConfig {rule.rule_name}")
    return record


def _firewall(rule: GcpFirewallRule) -> dict[str, Any]:
    """Return the documented ``Firewall`` of one rule.

    Three members are emitted empty on purpose:

    * ``creationTimestamp``/``id``/``selfLink`` are ``[Output Only]`` and server-defined, and the
      model carries no firewall id, no resource URL and no creation instant;
    * ``params`` is ``[Input Only]``: it belongs to the request, never to a response;
    * the four target containers (``targetTags``, ``sourceTags``, ``targetServiceAccounts``,
      ``sourceServiceAccounts``) are empty by construction -- no rule of this estate selects its
      target by tag or by service account. Omitting them would understate the format; filling
      them would invent a targeting rule nothing declares.
    """
    record: dict[str, Any] = {
        "allowed": [_entry(entry) for entry in rule.allowed],
        "creationTimestamp": None,
        "denied": [_entry(entry) for entry in rule.denied],
        "description": rule.description,
        "destinationRanges": list(rule.destination_ranges),
        "direction": rule.direction,
        "disabled": rule.disabled,
        "id": None,
        "kind": GCP_FIREWALL_KIND,
        "logConfig": _log_config(rule),
        "name": rule.rule_name,
        "network": rule.network_url,
        "params": {},
        "priority": rule.priority,
        "selfLink": None,
        "sourceRanges": list(rule.source_ranges),
        "sourceServiceAccounts": list(rule.source_service_accounts),
        "sourceTags": list(rule.source_tags),
        "targetServiceAccounts": list(rule.target_service_accounts),
        "targetTags": list(rule.target_tags),
    }
    _require_projection(record, _FIREWALL_COLUMNS, _FIREWALL_PROJECTED, f"Firewall {rule.rule_name}")
    return record


def _request_parameters() -> dict[str, Any]:
    """Return the documented request parameters as a SHAPE fixture (all values null).

    These six names belong to the REQUEST side of the action; the estate models no captured
    request, so every value is null. The document exists so the request vocabulary is present
    and the gap is testable rather than silently absent.
    """
    document: dict[str, Any] = dict.fromkeys(_REQUEST_COLUMNS)
    _require_projection(document, _REQUEST_COLUMNS, _REQUEST_PROJECTED, "parametros de requisicao")
    return document


def _rules_by_project(estate: CanonicalEstate) -> dict[str, list[GcpFirewallRule]]:
    """Group the estate's firewall rules by PROJECT, deterministically.

    One envelope per project because that is the scope of the call:
    ``projects/{project}/global/firewalls`` names one project and no region. A firewall rule is a
    global resource -- only the subnetwork inside a network is regional -- so an envelope per
    (project, region) would be a partition the API never performs.

    Within a project the rules come out in the order the page declares as the default for
    ``orderBy``: alphabetical by name.
    """
    por_uuid = {segment.segment_uuid: segment for segment in estate.network_segments}
    grouped: dict[str, list[GcpFirewallRule]] = {}
    for rule in estate.gcp_firewall_rules:
        segment = por_uuid.get(rule.segment_uuid)
        if segment is None:
            # Fail closed: ``Firewall.network`` publishes the URL of the network the rule
            # protects, so a rule pointing at a network the estate does not have would render a
            # documented member with nothing behind it.
            raise RenderError(
                f"{RENDER_DIR}: regra de firewall {rule.rule_name} aponta para "
                f"{rule.segment_uuid!r}, que nao e segmento do estate (FK orfa)"
            )
        if segment.provider != "gcp":
            raise RenderError(
                f"{RENDER_DIR}: regra de firewall {rule.rule_name} pertence a um segmento "
                f"{segment.provider!r}, que nao e GCP"
            )
        if segment.scope_id != rule.scope_id:
            raise RenderError(
                f"{RENDER_DIR}: regra de firewall {rule.rule_name} diz projeto {rule.scope_id!r} "
                f"e sua rede e do projeto {segment.scope_id!r}"
            )
        grouped.setdefault(rule.scope_id, []).append(rule)
    return {
        project: sorted(rules, key=lambda item: item.rule_name)
        for project, rules in sorted(grouped.items())
    }


def _write_text(path: Path, text: str, written: list[Path]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if path not in written:
        written.append(path)


class ComputeFirewallsRenderer:
    """Renders the canonical estate's GCP firewall rules, as ``compute.firewalls.list`` returns them."""

    name = "compute_firewalls"

    def render(self, estate: CanonicalEstate, out_dir: Path) -> list[Path]:
        """Write the fixtures under ``out_dir/compute_firewalls/``; return written paths."""
        target = out_dir / RENDER_DIR
        written: list[Path] = []
        by_project = _rules_by_project(estate)

        responses: list[dict[str, Any]] = []
        firewalls: list[dict[str, Any]] = []
        entries: list[dict[str, Any]] = []
        log_configs: list[dict[str, Any]] = []

        for scope_rules in by_project.values():
            scope_records = [_firewall(rule) for rule in scope_rules]
            # Everything derived comes out of the RECORD, never from the model in parallel: that
            # is what makes it impossible for the flattened artifacts to disagree with what is
            # inside the envelope's ``items``.
            for record in scope_records:
                firewalls.append(record)
                entries.extend(record["allowed"])
                entries.extend(record["denied"])
                log_configs.append(record["logConfig"])
            responses.append(
                {
                    "id": None,
                    "items": scope_records,
                    "kind": GCP_FIREWALL_LIST_KIND,
                    "nextPageToken": None,
                    "selfLink": None,
                    "warning": {},
                }
            )
            _require_projection(responses[-1], _LIST_COLUMNS, _LIST_PROJECTED, "envelope de resposta")

        # Determinism byte-for-byte: the flattened artifacts follow the envelope order, and the
        # protocol entries keep the order they appear in inside their rule.
        for entry in entries:
            _require_projection(entry, _ENTRY_COLUMNS, _ENTRY_PROJECTED, "tupla de protocolo")
        log_configs.sort(key=lambda item: (not item["enable"], str(item["metadata"] or "")))

        _write_text(
            target / "firewall-list-response.json",
            json.dumps(responses, indent=2, ensure_ascii=False) + "\n",
            written,
        )
        _write_text(target / "firewall.json", json.dumps(firewalls, indent=2, ensure_ascii=False) + "\n", written)
        _write_text(
            target / "firewall-protocol-entry.json",
            json.dumps(entries, indent=2, ensure_ascii=False) + "\n",
            written,
        )
        _write_text(
            target / "firewall-log-config.json",
            json.dumps(log_configs, indent=2, ensure_ascii=False) + "\n",
            written,
        )
        _write_text(
            target / "request-parameters.json",
            json.dumps(_request_parameters(), indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            written,
        )
        written.append(self._write_provenance(target, by_project))
        return written

    def _write_provenance(self, target: Path, by_project: dict[str, list[GcpFirewallRule]]) -> Path:
        """Write the sibling provenance report: the spec, the mechanism, the counts, the gaps.

        The reasons live HERE and not in the artifact: an ingestor of the fixture must not see a
        key no cloud documents. This file is what says which values are derivations and which
        are declared gaps.
        """
        todas = [rule for rules in by_project.values() for rule in rules]
        pre_populadas = [rule for rule in todas if rule.is_prepopulated]
        com_log = [rule for rule in todas if rule.log_enabled]
        relatorio: dict[str, Any] = {
            "kind": "provenance",
            "surface": SURFACE,
            "spec": f"specs/{_SPEC_FILE}",
            "artifacts": [
                "firewall-list-response.json",
                "firewall.json",
                "firewall-protocol-entry.json",
                "firewall-log-config.json",
                "request-parameters.json",
            ],
            "mechanism": {
                "action": "compute.firewalls.list",
                "path": "projects/{project}/global/firewalls",
                "granularity": "one FirewallList envelope per PROJECT, carrying every rule of the project",
                "scope": (
                    "o PROJETO, e nao (projeto, regiao): o caminho da acao tem 'global' e nao tem "
                    "regiao. A regra de firewall e um recurso global; so a sub-rede dentro da rede e "
                    "regional. Um envelope por regiao seria um recorte que a API nao faz."
                ),
                "item_order": (
                    "alfabetico pelo nome, que e o que o parametro orderBy declara como padrao "
                    "('By default, results are returned in alpha[betical order]')"
                ),
                "item_order_source_url": ORDER_SOURCE_URL,
                "two_decision_lists": (
                    "a regra publica DUAS listas, allowed[] e denied[], e nao um campo de decisao: "
                    "e o oposto do security group da AWS (so de permissao) e do NSG da Azure (uma "
                    "regra com 'access'). E por isso que o modelo tem o proprio tipo, e nao reuso "
                    "de nenhum dos dois."
                ),
                "direction_is_a_member": (
                    "a GCP publica direction como membro real (INGRESS/EGRESS, default INGRESS), ao "
                    "contrario da AWS, onde a direcao e o NOME da lista que contem a regra. A pagina "
                    "fecha que 'For EGRESS traffic, you cannot specify the sourceTags fields', e por "
                    "isso uma regra de SAIDA nao recebe sourceRanges: o destino vai em "
                    "destinationRanges."
                ),
                "ports_are_strings": (
                    "ports e uma lista de strings em que cada entrada e um inteiro ou uma FAIXA "
                    "([\"12345-12349\"]), nao o par fromPort/toPort da AWS. Vazio significa "
                    "'connections through any port', que e o que a pagina declara."
                ),
                "prepopulated_rules": (
                    "as quatro regras com que a rede DEFAULT nasce, com nome, direcao ingress, "
                    "prioridade 65534, origem e o par protocolo:porta que a tabela publica. A saida "
                    "de 'gcloud compute firewall-rules list' de um projeto recem-criado traz "
                    "default-allow-internal com a coluna ALLOW igual a 'all', e e dela que vem esse "
                    "valor: o CLI so colapsa assim o que a API guarda como uma unica tupla."
                ),
                "prepopulated_source_url": PREPOPULATED_URL,
                "all_protocol": (
                    "IPProtocol = 'all' e o valor que a API devolve na regra que libera todo o "
                    "trafego. A prosa do campo lista tcp/udp/icmp/esp/ah/ipip/sctp e NAO inclui "
                    "'all', enquanto o guia de VPC firewall diz que a regra vale para 'all traffic "
                    "on any protocol and any destination port' quando protocolo e portas sao "
                    "omitidos. A divergencia esta registrada em 'unverified' da spec."
                ),
                "all_protocol_source_url": ALL_PROTOCOL_URL,
                "implied_rules_not_in_the_list": (
                    "toda rede VPC tem DUAS regras IMPLICITAS -- ingress que nega tudo e egress que "
                    "libera tudo, ambas em 65535 -- que firewalls.list NAO devolve, porque sao "
                    "comportamento e nao recurso. Nao ha coluna para elas e o artefato nao as "
                    "carrega. Um consumidor que inferisse 'sem regra = fechado' a partir de uma "
                    "lista vazia estaria lendo a implicacao como ausencia de fato."
                ),
                "implied_rules_source_url": IMPLIED_RULES_URL,
            },
            "counts": {
                "projects": len(by_project),
                "firewall_rules": len(todas),
                "prepopulated_rules": len(pre_populadas),
                "rules_with_logging": len(com_log),
                "rules_exposing_anywhere": sum(1 for rule in todas if rule.exposes_to_anywhere),
                "ingress_rules": sum(1 for rule in todas if rule.direction == "INGRESS"),
                "egress_rules": sum(1 for rule in todas if rule.direction == "EGRESS"),
                "disabled_rules": sum(1 for rule in todas if rule.disabled),
                "deny_rules": sum(1 for rule in todas if rule.denied),
            },
            "derivations": [
                {
                    "field": "network",
                    "status": "TODO-verificar",
                    "reason": (
                        "O valor e o segment_id do segmento VERBATIM, e portanto um FATO do modelo, "
                        "nao uma derivacao de conteudo -- diferente do vpcId do security group da AWS, "
                        "que precisa ser derivado do segmento. A divergencia pendente e de FORMA: na "
                        "GCP uma rede VPC e GLOBAL e tem sub-redes em varias regioes, e o modelo da "
                        "este estate uma rede por (projeto, regiao), como se fosse a VPC da AWS. O "
                        "valor escrito aqui e o que o modelo tem, e nao a forma que um projeto real "
                        "produz. A verificacao so se resolve quando o modelo passar a carregar uma "
                        "rede por projeto."
                    ),
                    "source_url": PREPOPULATED_URL,
                },
                {
                    "field": "items[].name das regras pre-populadas",
                    "status": "TODO-verificar",
                    "reason": (
                        "A tabela de regras pre-populadas diz que essas regras existem na rede "
                        "'default'; o modelo nao tem uma rede default. Elas vao para a PRIMEIRA rede "
                        "do projeto na ordem por segment_id, e essa escolha e uma convencao do "
                        "gerador, nao um fato da GCP. Sem ela nao haveria rede onde colocar as "
                        "regras que a documentacao descreve."
                    ),
                    "source_url": PREPOPULATED_URL,
                },
                {
                    "field": "items[].description",
                    "status": "TODO-verificar",
                    "reason": (
                        "Nas quatro regras pre-populadas a descricao e o TEXTO que a tabela da "
                        "documentacao publica para cada uma. Nas regras criadas pelo operador a GCP "
                        "publica description como texto livre e nenhuma fonte do estate afirma uma "
                        "frase, entao o valor e o nome que a propria regra tem -- inventar uma "
                        "descricao seria afirmar algo que nenhuma fonte sustenta."
                    ),
                    "source_url": PREPOPULATED_URL,
                },
            ],
            "model_gaps": [
                {
                    "field": "id",
                    "reason": (
                        "id e [Output Only] e definido pelo servidor ('This identifier is defined by "
                        "the server'); o estado nao carrega o identificador numerico que a GCP atribui "
                        "a regra. Vai vazio em vez de receber um numero inventado."
                    ),
                    "source_url": PREPOPULATED_URL,
                },
                {
                    "field": "creationTimestamp",
                    "reason": (
                        "creationTimestamp e [Output Only] em RFC3339 e definido pelo servidor; o "
                        "estado nao carrega o instante de criacao de uma regra de firewall. Vai "
                        "vazio: um instante inventado seria uma data que a GCP nunca affirmou."
                    ),
                    "source_url": PREPOPULATED_URL,
                },
                {
                    "field": "selfLink",
                    "reason": (
                        "selfLink e [Output Only], a URL do recurso definida pelo servidor. O modelo "
                        "carrega a URL da REDE (segment_id) e o nome da regra, mas nao a URL da "
                        "propria regra, entao o campo vai vazio."
                    ),
                    "source_url": PREPOPULATED_URL,
                },
                {
                    "field": "params",
                    "reason": (
                        "params e [Input Only]: 'Additional params passed with the request, but not "
                        "persisted as part of resource payload'. Faz parte da estrutura documentada "
                        "do recurso mas nunca aparece numa resposta, entao sai vazio."
                    ),
                    "source_url": PREPOPULATED_URL,
                },
                {
                    "field": "firewall-list-response.warning",
                    "reason": (
                        "O discovery declara warning como 'Informational warning message' com tipo "
                        "object e NAO publica os membros dele. Sai {}: um objeto sem campos "
                        "publicados nao vira estrutura inventada."
                    ),
                    "source_url": ORDER_SOURCE_URL,
                },
                {
                    "field": f"{FIREWALL_SCOPE}.targetTags / sourceTags / targetServiceAccounts / sourceServiceAccounts",
                    "reason": (
                        "Nenhuma regra deste estate seleciona o alvo por TAG ou por CONTA DE SERVICO: "
                        "todas valem para as instancias da rede. Os quatro containers sao emitidos "
                        "VAZIOS -- omiti-los subestimaria o formato e preenche-los inventaria uma "
                        "regra de selecao que nada declara. Vale a exclusividade que a propria pagina "
                        "declara: targetServiceAccounts 'cannot be used at the same time as "
                        "targetTags or sourceTags'."
                    ),
                    "source_url": PREPOPULATED_URL,
                },
                {
                    "field": f"{FIREWALL_SCOPE}.sourceServiceAccounts em regra de saida",
                    "reason": (
                        "A pagina fecha que 'For EGRESS traffic, you cannot specify the sourceTags "
                        "fields', e a mesma logica vale para as contas de servico de origem: uma "
                        "regra de saida nao recebe origem, recebe destinoRanges. Por isso nenhuma "
                        "regra deste estate combina direcao EGRESS com sourceRanges."
                    ),
                    "source_url": PREPOPULATED_URL,
                },
                {
                    "field": "request-parameters",
                    "reason": (
                        "filter, maxResults, orderBy, pageToken, project e returnPartialSuccess "
                        "pertencem ao lado de REQUISICAO da acao; o estate nao modela nenhuma "
                        "requisicao capturada, entao os seis vao null."
                    ),
                    "source_url": ORDER_SOURCE_URL,
                },
                {
                    "field": f"{LIST_SCOPE}.nextPageToken",
                    "reason": (
                        "nextPageToken e null em todo envelope, que e o valor que a pagina da para "
                        "'a proxima pagina': as regras de cada projeto cabem numa pagina."
                    ),
                    "source_url": ORDER_SOURCE_URL,
                },
            ],
            "not_generated": [
                {
                    "field": "as duas regras implicitas de toda rede VPC",
                    "reason": (
                        "Ingress que nega tudo e egress que libera tudo, ambas em prioridade 65535. "
                        "Sao implicadas pela existencia da rede, nao sao recursos, e firewalls.list "
                        "nao as devolve -- por isso nao ha coluna e o artefato nao as carrega. Esta e "
                        "a lacuna que um consumidor que varre a lista nao consegue ver: a regra que "
                        "protege a rede nunca aparece na resposta."
                    ),
                    "source_url": IMPLIED_RULES_URL,
                },
            ],
        }
        path = target / PROVENANCE_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(relatorio, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return path


__all__ = ["SURFACE", "RENDER_DIR", "ComputeFirewallsRenderer"]