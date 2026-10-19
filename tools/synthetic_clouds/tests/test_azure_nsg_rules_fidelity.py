"""Golden fidelity: as regras de NSG da Azure carregam EXATAMENTE as colunas documentadas.

Superfície ``azure/arm-network-security-group-rules`` — a metade deste repositório da lacuna
G1. Ela existe por um motivo que o teste tem de provar três vezes, e não uma:

1. **O contrato.** O artefato entregue (a resposta ARM por NSG) carrega as colunas que a spec
   enumera, e nenhuma a mais. A expectativa vem da spec, nunca de uma lista literal aqui —
   uma edição da spec move os dois lados de uma vez.
2. **A postura.** O consumidor do FinOps varre as regras e filtra
   ``direction == "Inbound" and access == "Allow"``. Este ficheiro aplica **o mesmo filtro,
   sobre os BYTES entregues**, e afirma que ele encontra a regra que deve — e que o NSG
   também carrega uma regra ``Deny``. Sem a segunda metade, um filtro invertido passaria.
3. **A ancoragem.** A projeção conferida é o achatamento do arquivo REAL lido de volta do
   disco, por um caminhante independente do renderer. Conferir uma lista em memória provaria
   apenas que duas cópias do mesmo erro concordam.

Incremento 7: o filtro do consumidor deixou de ser uma transcrição do ``direction``/``access``
e passou a ser a lógica INTEIRA dele — ``_parse_ports`` (singular E plural, ``*`` e faixa
``a-b``) sobre as portas que ele classifica como CRITICAL. Medido antes da mudança: a postura
anterior (443 ``Allow`` + 3389 ``Deny``) produzia **zero** achados em 6/6 NSGs, porque 443 não
está no dicionário de portas críticas do consumidor. Um check que nunca dispara sobre o
artefato não treina nada, então o estado ganhou a exposição que o consumidor classifica como
CRITICAL — e ela usa o service tag ``Internet``, cobrindo o terceiro ramo das origens abertas.

O que **não** é emitido, e por quê: as formas plurais dos prefixos/portas (a regra usa a
singular; preenchê-las duplicaria o valor) e as listas de Application Security Group (nenhuma
regra deste estado aponta para uma ASG).
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from tools.synthetic_clouds.fidelity.artifacts import populated_of
from tools.synthetic_clouds.fidelity.checker import (
    KIND_INVENTED,
    KIND_MISSING,
    KIND_POPULATED_EMPTY,
    KIND_UNVERIFIED,
    Finding,
    check_artifact,
    is_faithful,
)
from tools.synthetic_clouds.fidelity.spec import DEFAULT_SPECS_ROOT, SurfaceSpec, load_spec
from tools.synthetic_clouds.generate import constants as const
from tools.synthetic_clouds.generate.estate_builder import build_estate
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.network import SECURITY_RULE_PRIORITY_RANGE, NetworkSecurityGroup, NetworkSegment
from tools.synthetic_clouds.render.azure_nsg_rules import AzureNetworkSecurityGroupRenderer
from tools.synthetic_clouds.scenarios.emit import apply_all

_SPEC_FILE = "arm-network-security-group-rules.schema.json"

#: Os dois conjuntos nomeados da superfície. O escopo NÃO é opcional aqui: a spec tem dois
#: contratos disjuntos (a regra e o envelope) e conferir um artefato contra a união dos dois
#: acusaria ausência de tudo o que pertence ao outro.
_RULE_SCOPE = "rule"
_NSG_SCOPE = "networkSecurityGroup"

#: Os literais e a logica do CONSUMIDOR, transcritos de
#: ``security.py (modulo do consumidor)``:
#: ``AzureSecurityScanner._parse_ports`` (security.py:176-196) e o filtro de
#: ``_list_open_nsgs`` (security.py:107-127). Sao transcritos, nao importados -- o consumidor
#: esta em outro repo, e um import acoplar a suite a um path que nao existe aqui. Este bloco
#: existe para responder uma unica pergunta, a mesma que o inc.6 (GCP firewall) respondeu:
#: "o dado que o consumidor procura esta no artefato ENTREGUE?" -- e a resposta tem de ser
#: medida, nao presumida.
_CONSUMER_DIRECTION = "Inbound"
_CONSUMER_ACCESS = "Allow"
#: As tres origens que o consumidor trata como ABERTAS (security.py:111).
_CONSUMER_OPEN_SOURCES = ("*", "0.0.0.0/0", "Internet")
#: As portas que o consumidor classifica como CRITICAL (security.py:20-28).
_CONSUMER_CRITICAL_PORTS = {
    22: "SSH",
    3389: "RDP",
    5432: "PostgreSQL",
    3306: "MySQL",
    1433: "MSSQL",
    27017: "MongoDB",
    6379: "Redis",
}


def _parse_ports(single: str | None, ranges: list[str] | None) -> list[int]:
    """Transcricao de ``AzureSecurityScanner._parse_ports``: singular E plural, ``*`` e faixa ``a-b``."""
    ports: list[int] = []
    items: list[str] = []
    if single:
        items.append(single)
    if ranges:
        items.extend(ranges)
    for item in items:
        if item == "*":
            return list(_CONSUMER_CRITICAL_PORTS)
        if "-" in item:
            inicio, fim = item.split("-")[0], item.split("-")[1]
            ports.extend(p for p in _CONSUMER_CRITICAL_PORTS if int(inicio) <= p <= int(fim))
        else:
            try:
                ports.append(int(item))
            except ValueError:
                pass
    return ports


def _achados_do_consumidor(documento: dict[str, Any]) -> list[dict[str, Any]]:
    """Os achados que ``_list_open_nsgs`` produziria sobre UM corpo de NSG entregue.

    Reproduz o filtro inteiro -- direcao, acesso, origem aberta e porta critica -- e devolve o
    par (regra, porta) para cada achado, para que o teste afirme o ramo E a severidade.
    """
    achados: list[dict[str, Any]] = []
    for regra in documento["properties"]["securityRules"]:
        props = regra["properties"]
        if props["direction"] != _CONSUMER_DIRECTION or props["access"] != _CONSUMER_ACCESS:
            continue
        if props["sourceAddressPrefix"] not in _CONSUMER_OPEN_SOURCES:
            continue
        for porta in _parse_ports(props.get("destinationPortRange"), props.get("destinationPortRanges")):
            if porta in _CONSUMER_CRITICAL_PORTS:
                achados.append({"regra": regra["name"], "porta": porta, "nsg": documento["name"]})
    return achados


@pytest.fixture(scope="module")
def estate() -> CanonicalEstate:
    return apply_all(build_estate(seed=123, profile="small", currency="USD"))


@pytest.fixture(scope="module")
def nsg_rules_dir(estate: CanonicalEstate, tmp_path_factory: pytest.TempPathFactory) -> Path:
    renderer = AzureNetworkSecurityGroupRenderer()
    out = tmp_path_factory.mktemp(renderer.name)
    renderer.render(estate, out)
    return out / renderer.name


def _spec() -> SurfaceSpec:
    return load_spec(DEFAULT_SPECS_ROOT / "azure" / _SPEC_FILE)


def _scope_columns(spec: SurfaceSpec, scope: str | None) -> tuple[Any, ...]:
    return spec.columns if scope is None else spec.columns_for(scope)


def _emittable(spec: SurfaceSpec, scope: str | None) -> set[str]:
    return {column.name for column in _scope_columns(spec, scope) if column.belongs_to_schema}


def _generatable(spec: SurfaceSpec, scope: str | None) -> set[str]:
    return {column.name for column in _scope_columns(spec, scope) if column.is_generatable}


def _required_not_emittable(spec: SurfaceSpec, scope: str | None) -> set[str]:
    return {column.name for column in _scope_columns(spec, scope) if column.required} - _emittable(spec, scope)


def _of(findings: tuple[Finding, ...], kind: str) -> set[str]:
    return {finding.column for finding in findings if finding.kind == kind}


def _assert_only_the_specs_own_gaps(findings: tuple[Finding, ...], spec: SurfaceSpec, scope: str | None) -> None:
    assert _of(findings, KIND_INVENTED) == set(), "\n".join(map(str, findings))
    assert _of(findings, KIND_MISSING) == _required_not_emittable(spec, scope), "\n".join(map(str, findings))
    assert _of(findings, KIND_UNVERIFIED) == set(), "\n".join(map(str, findings))
    assert Counter(finding.kind for finding in findings)[KIND_POPULATED_EMPTY] == 0, "\n".join(map(str, findings))


# -- leitura do artefato entregue (caminhante independente do renderer) ----------------


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _delivered(nsg_rules_dir: Path) -> list[Path]:
    """Os corpos de NSG entregues, em ordem determinística (exclui projeção e proveniência)."""
    return sorted(
        path
        for path in nsg_rules_dir.rglob("*.json")
        if "field_projection" not in path.parts and path.name != "_provenance.json"
    )


def _projections(nsg_rules_dir: Path) -> list[Path]:
    return sorted((nsg_rules_dir / "field_projection").glob("*.json"))


def _walk(node: Any, prefix: str, fields: dict[str, Any]) -> None:
    """Achata UM objeto: cada chave é um caminho; a lista continua o caminho do pai com ``[]``.

    É a convenção do núcleo (``fidelity/artifacts``): uma lista não acrescenta caminho próprio.
    Por isso o envelope do NSG produz UMA linha, com os caminhos das regras dentro dela.
    """
    if not isinstance(node, dict):
        return
    for key, value in node.items():
        path = f"{prefix}{key}"
        fields[path] = value
        if isinstance(value, list):
            for item in value:
                _walk(item, f"{path}[].", fields)
        else:
            _walk(value, f"{path}.", fields)


def _flatten(payload: Any) -> list[dict[str, Any]]:
    """Uma linha por objeto de topo do payload (o corpo do NSG é um objeto: uma linha)."""
    rows = payload if isinstance(payload, list) else [payload]
    flat: list[dict[str, Any]] = []
    for row in rows:
        fields: dict[str, Any] = {}
        _walk(row, "", fields)
        flat.append(fields)
    return flat


def _item_rows(payload: Any, item_path: str) -> list[dict[str, Any]]:
    """Uma linha por POSIÇÃO de ``item_path[]`` — o nível em que uma regra vive.

    A projeção ENTREGUE achata as regras numa única linha (as chaves são os caminhos e os
    valores são as subárvores), então o nível "campos de UMA regra" é lido da posição da lista
    no documento — e é ele que o escopo ``rule`` da spec descreve.
    """
    documento = payload if isinstance(payload, dict) else payload[0]
    items: Any = documento
    for segmento in item_path.split("."):
        items = items[segmento]
    linhas: list[dict[str, Any]] = []
    for item in items:
        fields: dict[str, Any] = {}
        _walk(item, f"{item_path}[].", fields)
        linhas.append(fields)
    return linhas


def _rule_rows_of(payload: Any) -> list[dict[str, Any]]:
    return _item_rows(payload, "properties.securityRules")


def _rule_rows_das_projecoes(nsg_rules_dir: Path, destino: Path) -> Path:
    """As linhas de regra materializadas num arquivo, lidas do que foi ENTREGUE.

    O núcleo de fidelidade confere um ARQUIVO (é essa a promessa: o artefato entregue), e o
    escopo ``rule`` descreve uma linha de ``securityRules[]``. A matéria-prima são os corpos de
    NSG gravados em disco — e a igualdade entre eles e a projeção é afirmada por um teste
    próprio, então conferir a linha daqui é conferir o artefato.
    """
    linhas: list[dict[str, Any]] = []
    for path in _delivered(nsg_rules_dir):
        linhas.extend(_rule_rows_of(_read(path)))
    destino.write_text(json.dumps(linhas), encoding="utf-8")
    return destino


def _azure_nsgs(estate: CanonicalEstate) -> list[NetworkSegment]:
    """Os segmentos Azure com NSG — lidos do modelo, não do ajudante do renderer."""
    return sorted(
        (
            segment
            for segment in estate.network_segments
            if segment.provider == "azure" and segment.network_security_group is not None
        ),
        key=lambda segment: segment.segment_uuid,
    )


def _rules_of(path: Path) -> list[dict[str, Any]]:
    """As posições de ``properties.securityRules[]`` do documento entregue."""
    regras: list[dict[str, Any]] = _read(path)["properties"]["securityRules"]
    return regras


# -- o contrato --------------------------------------------------------------------------


def test_a_superficie_esta_na_matriz_e_a_spec_confere(nsg_rules_dir: Path) -> None:
    """A superfície declarada como gerada tem de estar na matriz, e a matriz na spec."""
    from tools.synthetic_clouds.fidelity import matrix, report

    coverage = matrix.coverage_for("azure/arm-network-security-group-rules")
    assert coverage is not None
    assert coverage.renderer == "azure_nsg_rules"
    assert report.staleness() == ()
    assert report.golden_gaps() == ()


def test_um_corpo_por_nsg_azure_do_estado(nsg_rules_dir: Path, estate: CanonicalEstate) -> None:
    entregues = _delivered(nsg_rules_dir)
    assert len(entregues) == len(_azure_nsgs(estate))
    assert {path.name for path in entregues} == {
        f"{segment.network_security_group.name}.json"  # type: ignore[union-attr]
        for segment in _azure_nsgs(estate)
    }


def test_o_caminho_e_o_do_get_do_recurso(nsg_rules_dir: Path, estate: CanonicalEstate) -> None:
    """subscriptions/<guid>/resourceGroups/<rg>/providers/Microsoft.Network/networkSecurityGroups/<nsg>/"""
    for path in _delivered(nsg_rules_dir):
        relativo = path.relative_to(nsg_rules_dir).as_posix()
        assert relativo.startswith("subscriptions/")
        partes = relativo.split("/")
        assert partes[2] == "resourceGroups"
        assert partes[4:7] == ["providers", "Microsoft.Network", "networkSecurityGroups"]
        # O token de assinatura é o GUID, nunca o rótulo de escopo do modelo.
        assert not partes[1].startswith("sub-")
        assert partes[1].count("-") == 4


def test_o_envelope_carrega_exatamente_as_colunas_do_conjunto(nsg_rules_dir: Path) -> None:
    spec = _spec()
    for path in _delivered(nsg_rules_dir):
        documento = _read(path)
        caminhos = {nome for linha in _flatten(documento) for nome in linha}
        # O envelope e a linha da PROJEÇÃO são o mesmo nível: os dois conjuntos da spec.
        emitivel = _emittable(spec, None)
        assert emitivel <= caminhos
        # E nenhum contêiner a mais: nesta spec os contêineres são COLUNAS declaradas.
        assert caminhos - emitivel == set()


def test_a_projecao_e_o_documento_entregue_achatado(nsg_rules_dir: Path) -> None:
    """A âncora: a projeção conferida é o arquivo REAL achatado, não uma cópia em memória.

    O par é formado pelo NOME do arquivo, e não pela posição em duas listas ordenadas: o corpo
    do NSG está no caminho ``.../networkSecurityGroups/<nsg>/<nsg>.json`` e a projeção em
    ``field_projection/<nsg>.json``, então ordenar as duas listas por caminho dá ordens
    diferentes — parear por índice compararia o NSG de um com a projeção de outro.
    """
    spec = _spec()
    entregues = {path.name: path for path in _delivered(nsg_rules_dir)}
    projecoes = {path.name: path for path in _projections(nsg_rules_dir)}
    assert entregues.keys() == projecoes.keys()

    for nome, entregue in sorted(entregues.items()):
        achatado = _flatten(_read(entregue))
        esperado = [{campo: valor for campo, valor in linha.items() if campo in _emittable(spec, None)} for linha in achatado]
        assert _read(projecoes[nome]) == esperado


@pytest.fixture(scope="module")
def rule_rows(nsg_rules_dir: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """As LINHAS de regra da projeção entregue, materializadas num arquivo para o auditor ler.

    O núcleo de fidelidade confere um ARQUIVO (é essa a promessa: o artefato entregue), e o
    escopo ``rule`` descreve uma linha de ``securityRules[]``. O arquivo é montado a partir dos
    BYTES entregues -- a projeção de cada NSG --, e nunca de uma segunda cópia em memória.
    """
    destino = tmp_path_factory.mktemp("nsg-rule-rows") / "rules.json"
    return _rule_rows_das_projecoes(nsg_rules_dir, destino)


def test_as_regras_conferem_com_a_spec_e_nao_tem_coluna_a_mais(rule_rows: Path) -> None:
    spec = _spec()
    linhas = _read(rule_rows)
    assert linhas, "sem linha de regra nao ha o que conferir"

    _assert_only_the_specs_own_gaps(check_artifact(spec, rule_rows, scope=_RULE_SCOPE), spec, _RULE_SCOPE)
    # O nível de uma regra é o ITEM de ``securityRules[]``: o container que a hospeda
    # (``properties.securityRules``) pertence ao envelope e não aparece aqui.
    assert set(linhas[0]) == _emittable(spec, _RULE_SCOPE)
    # ``populated_of`` responde por ARQUIVO (é o artefato que ele mede), e não por lista.
    assert set(populated_of(rule_rows)) <= _generatable(spec, _RULE_SCOPE)


def test_o_envelope_conferido_tem_o_nome_do_nsg(nsg_rules_dir: Path, estate: CanonicalEstate) -> None:
    """O envelope conferido carrega o nome do NSG do modelo, e só as colunas dos dois conjuntos.

    A projeção é o nível DOCUMENTO: a linha carrega o envelope e, dentro dela, os caminhos das
    regras. Por isso a conferência aqui usa a união dos conjuntos — e o nível de item, que é o
    que o escopo ``rule`` descreve sozinho, é conferido nos testes de regra.
    """
    spec = _spec()
    nomes = {segment.network_security_group.name for segment in _azure_nsgs(estate)}  # type: ignore[union-attr]
    for projecao in _projections(nsg_rules_dir):
        primeira = _read(projecao)[0]
        assert "name" in primeira
        assert primeira["name"] in nomes
        assert set(primeira) == _emittable(spec, None)
        assert set(populated_of(projecao)) <= _generatable(spec, None)


def test_o_id_do_recurso_e_da_regra_sao_emitidos_e_coerentes_com_o_caminho(nsg_rules_dir: Path) -> None:
    """Os dois ``id`` que a doc publica, e a coerencia com o caminho do arquivo.

    A forma e ``/subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.Network/
    networkSecurityGroups/{nsg}`` e a da regra acrescenta ``/securityRules/{regra}``. O
    consumidor le ``nsg.id`` e faz ``nsg.id.split('/')[4]`` para montar o ``--resource-group``
    do comando de remediacao. Como o id canonico comeca com ``/``, o ``split`` produz um
    primeiro elemento vazio e o indice 4 cai no NOME do resource group -- e este teste fixa
    esse indice, porque e o que o consumidor le, nao o que a doc escreve.
    """
    for path in _delivered(nsg_rules_dir):
        documento = _read(path)
        nsg_id = documento["id"]
        partes = nsg_id.split("/")
        assert partes[1] == "subscriptions"
        assert partes[3] == "resourceGroups"
        # O indice 4 e o QUE o consumidor le (security.py:125): precisa ser o resource group.
        assert partes[4] not in {"", "providers", "resourceGroups"}
        assert partes[5:8] == ["providers", "Microsoft.Network", "networkSecurityGroups"]
        assert partes[8] == documento["name"]
        for regra in documento["properties"]["securityRules"]:
            assert regra["id"] == f"{nsg_id}/securityRules/{regra['name']}"


def test_o_id_do_nsg_e_o_mesmo_que_o_caminho_do_arquivo(nsg_rules_dir: Path) -> None:
    """O id emitido e o caminho do arquivo ate ``networkSecurityGroups/{nsg}`` -- uma so grafia.

    O caminho em disco acrescenta a pasta e o sufixo de arquivo da propria entrega
    (``.../networkSecurityGroups/{nsg}/{nsg}.json``); o id ARM e o mesmo caminho SEM esse
    sufixo de entrega, porque e o id do recurso e nao o do blob. Nenhum dos dois e reescrito
    aqui: sao a mesma composicao.
    """
    for path in _delivered(nsg_rules_dir):
        documento = _read(path)
        caminho = path.relative_to(nsg_rules_dir).as_posix()
        # O caminho de entrega tem a pasta {nsg}/ E o arquivo {nsg}.json (o mesmo nome duas
        # vezes); o id ARM do recurso aparece uma vez. Como sao identicos, o id e o caminho
        # sem o ultimo componente -- nenhuma das duas grafias e reescrita aqui.
        assert documento["id"] == "/" + caminho.rsplit("/", 1)[0]
        assert caminho.endswith(f"networkSecurityGroups/{documento['name']}/{documento['name']}.json")


def test_o_id_da_regra_nao_e_mais_nao_comprovado(nsg_rules_dir: Path) -> None:
    """O nome saiu de ``unverified`` -- a doc publica a forma, entao ele PROIBIDO vira coluna."""
    spec = _spec()
    assert "properties.securityRules[].id" not in spec.unverified
    # E, sendo agora uma coluna verificada, ele e geravel e aparece em todo artefato.
    assert "properties.securityRules[].id" in {c.name for c in spec.columns_for(_RULE_SCOPE)}


# -- a postura: o filtro do consumidor, aplicado sobre os bytes entregues -----------------


def test_o_filtro_do_consumidor_encontra_a_regra_que_deve(nsg_rules_dir: Path) -> None:
    """``direction == Inbound and access == Allow`` sobre o ARTEFATO — e o Deny também existe."""
    for path in _delivered(nsg_rules_dir):
        regras = _rules_of(path)
        abertas = [
            regra
            for regra in regras
            if regra["properties"]["direction"] == _CONSUMER_DIRECTION
            and regra["properties"]["access"] == _CONSUMER_ACCESS
        ]
        assert abertas, f"{path.name}: o consumidor nao encontraria nada -- nao haveria achado"
        negadas = [regra for regra in regras if regra["properties"]["access"] == "Deny"]
        assert negadas, f"{path.name}: sem regra Deny o teste nao prova que o filtro distingue"


def test_as_regras_deste_estado_sao_as_que_a_constante_declara(nsg_rules_dir: Path) -> None:
    """O artefato nomeia a postura declarada em ``constants`` — e o teste e os dois lados citam a mesma fonte."""
    for path in _delivered(nsg_rules_dir):
        nomes = [regra["name"] for regra in _rules_of(path)]
        assert const.NSG_EXPECTED_INBOUND_ALLOW_CRITICAL in nomes
        assert const.NSG_EXPECTED_INBOUND_ALLOW in nomes
        assert const.NSG_EXPECTED_INBOUND_DENY in nomes


def test_a_prioridade_e_unica_e_a_ordem_e_a_da_avaliacao(nsg_rules_dir: Path) -> None:
    """A Azure exige prioridade única e avalia do menor para o maior: o arquivo respeita as duas."""
    minimo, maximo = SECURITY_RULE_PRIORITY_RANGE
    for path in _delivered(nsg_rules_dir):
        prioridades = [regra["properties"]["priority"] for regra in _rules_of(path)]
        assert len(set(prioridades)) == len(prioridades)
        assert prioridades == sorted(prioridades)
        assert all(minimo <= valor <= maximo for valor in prioridades)


def test_o_consumidor_real_encontra_o_achado_critical(nsg_rules_dir: Path) -> None:
    """A logica REAL de ``_list_open_nsgs``, aplicada aos BYTES entregues, produz achado.

    Este e o teste que faltava antes do incremento 7. Medido: com a postura anterior
    (443 Allow + 3389 Deny) o consumidor produzia **zero** achados, porque 443 nao esta em
    ``_CRITICAL_PORTS`` e a unica regra com porta critica era uma ``Deny``. Um estado que o
    check nunca sinaliza nao treina o check.
    """
    for path in _delivered(nsg_rules_dir):
        achados = _achados_do_consumidor(_read(path))
        assert achados, f"{path.name}: o consumidor nao produziria achado nenhum -- nao ha o que learns"
        assert {a["regra"] for a in achados} == {const.NSG_EXPECTED_INBOUND_ALLOW_CRITICAL}
        assert {a["porta"] for a in achados} == {22}
        assert achados[0]["porta"] in _CONSUMER_CRITICAL_PORTS


def test_o_filtro_descarta_o_que_nao_deve_gerar_achado(nsg_rules_dir: Path) -> None:
    """Os dois lados: o que o consumidor REJEITA, com a mesma postura no MESMO NSG.

    Uma regra ``Allow`` de entrada com origem aberta mas porta NAO critica (443) nao pode
    gerar achado -- senao o estado nao provaria que a classificacao de porta funciona. Uma
    regra ``Deny`` com origem aberta e porta critica (3389) tambem nao: o consumidor filtra
    ``access == "Allow"`` antes de olhar a porta.
    """
    for path in _delivered(nsg_rules_dir):
        documento = _read(path)
        por_nome = {r["name"]: r for r in documento["properties"]["securityRules"]}
        allow_nao_critica = por_nome[const.NSG_EXPECTED_INBOUND_ALLOW]
        deny_critica = por_nome[const.NSG_EXPECTED_INBOUND_DENY]

        # As duas existem e tem a origem aberta -- o que as separa do achado e o resto.
        assert allow_nao_critica["properties"]["sourceAddressPrefix"] in _CONSUMER_OPEN_SOURCES
        assert deny_critica["properties"]["sourceAddressPrefix"] in _CONSUMER_OPEN_SOURCES
        # A porta 3389 E critica e a 443 NAO: a diferenca nao esta no dicionario do consumidor.
        assert 3389 in _CONSUMER_CRITICAL_PORTS
        assert 443 not in _CONSUMER_CRITICAL_PORTS
        # E o consumidor descarta as duas pelo motivo certo.
        assert [a for a in _achados_do_consumidor({"name": documento["name"], "id": documento["id"],
            "properties": {"securityRules": [allow_nao_critica]}})] == []
        assert [a for a in _achados_do_consumidor({"name": documento["name"], "id": documento["id"],
            "properties": {"securityRules": [deny_critica]}})] == []


def test_o_ramo_do_service_tag_internet_e_exercitado(nsg_rules_dir: Path) -> None:
    """O consumidor aceita TRES origens abertas; o estado usa ``Internet``, e nao so ``*``.

    O ramo ``Internet`` so e coberto se alguma regra tiver esse prefixo. Com o valor ``*`` (ou
    uma CIDR) nos dois lados, esse ramo do filtro nunca seria executado contra o artefato.
    """
    prefixes = {
        r["properties"]["sourceAddressPrefix"]
        for path in _delivered(nsg_rules_dir)
        for r in _read(path)["properties"]["securityRules"]
    }
    assert "Internet" in prefixes
    assert prefixes <= set(_CONSUMER_OPEN_SOURCES) | {"VirtualNetwork", "AzureLoadBalancer"}


def test_a_exposicao_critica_e_a_de_maior_prioridade(nsg_rules_dir: Path) -> None:
    """Prioridade menor = avaliada antes: o SSH aberto vence a TLS, entao a exposicao e real."""
    for path in _delivered(nsg_rules_dir):
        regras = {r["name"]: r["properties"]["priority"] for r in _read(path)["properties"]["securityRules"]}
        assert regras[const.NSG_EXPECTED_INBOUND_ALLOW_CRITICAL] < regras[const.NSG_EXPECTED_INBOUND_ALLOW]
        assert regras[const.NSG_EXPECTED_INBOUND_ALLOW] < regras[const.NSG_EXPECTED_INBOUND_DENY]


def test_o_modelo_sustenta_os_dois_casos_no_mesmo_nsg(estate: CanonicalEstate) -> None:
    """A postura existe no ESTADO, não só no artefato: um NSG com Allow e sem Deny seria um estado limpo."""
    for segment in _azure_nsgs(estate):
        nsg = segment.network_security_group
        assert isinstance(nsg, NetworkSecurityGroup)
        acessos = {rule.access for rule in nsg.rules}
        assert {"allowed", "denied"} <= acessos
        direcoes = {rule.direction for rule in nsg.rules}
        assert "ingress" in direcoes


# -- determinismo e falsificação ----------------------------------------------------------


def test_renderizar_duas_vezes_da_os_mesmos_bytes(estate: CanonicalEstate, tmp_path: Path) -> None:
    renderer = AzureNetworkSecurityGroupRenderer()
    primeira = tmp_path / "a"
    segunda = tmp_path / "b"
    renderer.render(estate, primeira)
    renderer.render(estate, segunda)
    arquivos_a = sorted(path.relative_to(primeira).as_posix() for path in primeira.rglob("*") if path.is_file())
    arquivos_b = sorted(path.relative_to(segunda).as_posix() for path in segunda.rglob("*") if path.is_file())
    assert arquivos_a == arquivos_b
    for relativo in arquivos_a:
        assert (primeira / relativo).read_bytes() == (segunda / relativo).read_bytes()


def test_o_auditor_denuncia_uma_coluna_inventada(nsg_rules_dir: Path, tmp_path: Path) -> None:
    """A invariante sabe FALHAR: uma coluna fora da spec não passa em silêncio.

    A mutação é na PRIMEIRA linha de propósito, e isso é um limite do núcleo, não uma
    preferência: ``columns_of`` lê o primeiro objeto da lista (é o contrato de um artefato de
    colunas fixas), então uma coluna que só existisse numa linha posterior não seria vista.
    """
    spec = _spec()
    linhas = _read(_rule_rows_das_projecoes(nsg_rules_dir, tmp_path / "base.json"))
    linhas[0] = {**linhas[0], "properties.securityRules[].properties.colunaInventada": "x"}
    alvo = tmp_path / "inventada.json"
    alvo.write_text(json.dumps(linhas), encoding="utf-8")

    findings = check_artifact(spec, alvo, scope=_RULE_SCOPE)
    assert "properties.securityRules[].properties.colunaInventada" in _of(findings, KIND_INVENTED)
    assert not is_faithful(findings)


def test_o_auditor_denuncia_a_ausencia_de_uma_coluna_do_formato(nsg_rules_dir: Path, tmp_path: Path) -> None:
    """A outra direção: entregar MENOS do que a spec descreve também é divergência."""
    spec = _spec()
    linhas = _read(_rule_rows_das_projecoes(nsg_rules_dir, tmp_path / "base.json"))
    linhas[0] = {chave: valor for chave, valor in linhas[0].items() if chave != "properties.securityRules[].properties.protocol"}
    alvo = tmp_path / "sem-protocolo.json"
    alvo.write_text(json.dumps(linhas), encoding="utf-8")

    findings = check_artifact(spec, alvo, scope=_RULE_SCOPE)
    assert "properties.securityRules[].properties.protocol" in _of(findings, KIND_MISSING)
    assert not is_faithful(findings)


def test_a_proveniencia_registra_a_postura_e_as_lacunas(nsg_rules_dir: Path, estate: CanonicalEstate) -> None:
    """O relatório irmão conta as regras por direção e por acesso -- o número conferível.

    As contagens são por REGRA, não por NSG: cada NSG deste estado entrega as três posturas
    (a ``allowed`` CRITICAL, a ``allowed`` não-crítica e a ``denied``, todas de entrada), então
    o total é o triplo dos NSGs.
    """
    relatorio = _read(nsg_rules_dir / "_provenance.json")
    nsgs = _azure_nsgs(estate)
    regras_por_nsg = {len(segment.network_security_group.rules) for segment in nsgs}  # type: ignore[union-attr]
    assert regras_por_nsg == {3}
    assert relatorio["counts"]["rules"] == 3 * len(nsgs)
    assert relatorio["counts"]["by_access"] == {"allowed": 2 * len(nsgs), "denied": len(nsgs)}
    assert relatorio["counts"]["by_direction"] == {"ingress": 3 * len(nsgs)}
    assert relatorio["spec"].endswith(_SPEC_FILE)
    assert relatorio["not_generated"] == []
