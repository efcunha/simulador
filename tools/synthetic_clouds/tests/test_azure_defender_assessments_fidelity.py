"""Golden fidelity: os assessments do Defender carregam EXATAMENTE as colunas documentadas.

Superfície ``azure/security-assessments-list`` — o Incremento 8. Ela existe por um motivo que o
teste tem de provar três vezes, e não uma:

1. **O contrato.** O artefato entregue (o envelope ``SecurityAssessmentList`` por assinatura)
   carrega as colunas que a spec enumera, e nenhuma a mais. A expectativa vem da spec, nunca de
   uma lista literal aqui — uma edição da spec move os dois lados de uma vez.

2. **A postura.** O consumidor do FinOps varre os assessments da assinatura e descarta o que
   tem ``properties.status.code == "Healthy"``. Este ficheiro aplica **o mesmo filtro, sobre os
   BYTES entregues**, e afirma que ele encontra assessments que viram achado **e** assessments
   que ele descarta. Sem a segunda metade, um filtro invertido passaria.

3. **A ancoragem.** A projeção conferida é o achatamento do arquivo REAL lido de volta do disco,
   por um caminhante independente do renderer. Conferir uma lista em memória provaria apenas que
   duas cópias do mesmo erro concordam.

O achado que mudou a postura, medido antes de escrever o teste
--------------------------------------------------------------
A primeira versão desta superfície derivava o estado de saúde dos ACHADOS (``NativeFinding`` de
categoria REDE no mesmo escopo → ``Unhealthy``). Rodada no perfil ``small``/seed 123, ela
produziu ``Counter({'Unhealthy': 6, 'NotApplicable': 6})`` — **nenhum ``Healthy``**. Como o
consumidor descarta só ``Healthy``, o artefato **nunca exercitava o descarte**: um check que
nunca vê o ramo que ele tem de decidir não treina nada. Daí a alternância por índice de escopo.

E há um segundo desvio, medido contra o SDK real do consumidor (``azure-mgmt-security`` 7.0.0):
``SecurityCenter(cred, sub).assessments`` resolve para a api 2021-06-01 e devolve
``SecurityAssessmentResponse``, que **achata** ``properties.*`` em atributos de topo. Esse modelo
**não tem atributo ``properties``**, então ``assessment.properties.severity`` — a linha que o
consumidor usa para a severidade — levanta ``AttributeError``, é engolida pelo ``except
Exception`` externo, e o check inteiro devolve ``[]`` registrando ``azure_defender_scan_failed``.
O fallback ``"MEDIUM"`` é código morto: o atributo é avaliado *antes* do ``getattr``.

Este teste não conserta o FinOps (repo somente-leitura). Ele fixa o que o artefato entrega no
caminho DOCUMENTADO (``properties.metadata.severity``) e afirma que ``properties.severity`` não
existe na resposta — a divergência é do consumidor, e a prova é que a severidade está onde a
documentação publica.
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
from tools.synthetic_clouds.fidelity.matrix import coverage_for
from tools.synthetic_clouds.fidelity.spec import DEFAULT_SPECS_ROOT, SurfaceSpec, load_spec
from tools.synthetic_clouds.generate import constants as const
from tools.synthetic_clouds.generate.estate_builder import build_estate
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.native import (
    ASSESSMENT_HEALTH_CODES,
    ASSESSMENT_HEALTH_HEALTHY,
    ASSESSMENT_HEALTH_NOT_APPLICABLE,
    ASSESSMENT_HEALTH_UNHEALTHY,
    ASSESSMENT_SEVERITIES,
)
from tools.synthetic_clouds.model.network import NetworkSegment
from tools.synthetic_clouds.render.azure_arm_instances import (
    arm_id_token,
    documented_projection,
    is_blank,
)
from tools.synthetic_clouds.render.azure_defender_assessments import (
    ASSESSMENT_LIST_SCOPE,
    ASSESSMENT_SCOPE,
    AzureDefenderAssessmentsRenderer,
)
from tools.synthetic_clouds.scenarios.emit import apply_all

_SPEC_FILE = "security-assessments-list.schema.json"
_SURFACE = "azure/security-assessments-list"
_RENDERER = "azure_defender_assessments"

#: Os dois conjuntos nomeados da superfície. O escopo NÃO é opcional aqui: a spec tem dois
#: contratos disjuntos (o registro e o envelope) e conferir o envelope contra a união dos dois
#: acusaria ausência de tudo o que pertence ao registro.
_ASSESSMENT_SCOPE = ASSESSMENT_SCOPE
_LIST_SCOPE = ASSESSMENT_LIST_SCOPE

#: O prefixo que a spec da a cada coluna do registro — é onde o registro mora no corpo entregue
#: (o envelope tem uma colecao ``value[]``). Repetido aqui para que o teste confronte a spec,
#: e nao a constante do renderer.
_ENVELOPE_PREFIX = "value[]."

#: O literal que o consumidor DESCARTA — transcrito de
#: ``security.py (modulo do consumidor)``
#: (``AzureSecurityScanner._list_defender_findings``):
#: ``if not status or status.code == "Healthy": continue``.
_CONSUMER_DISCARDED = ASSESSMENT_HEALTH_HEALTHY

#: Os literais e a lógica do CONSUMIDOR, transcritos — não importados. O consumidor está em outro
#: repositório e um import acoplaria a suíte a um caminho que não existe aqui. Este bloco existe
#: para responder uma única pergunta, a mesma que os incrementos 6 e 7 responderam: "o dado que
#: o consumidor procura está no artefato ENTREGUE?" — e a resposta tem de ser medida, não
#: presumida.


class _SdkAssessment:
    """Um ``SecurityAssessmentResponse`` como o SDK achata: sem atributo ``properties``.

    Reproduz a forma que o medidor de 2026-10-18 observou no ``azure-mgmt-security`` 7.0.0 — o
    modelo ACHATA ``properties.*`` em atributos de topo. Reproduzir isso aqui é o que permite
    afirmar o comportamento do consumidor sem depender do SDK instalado, e sem que o teste
    passe a parecer "a severidade foi lida e saiu MEDIUM".
    """

    __slots__ = ("id", "display_name", "metadata", "status", "type")

    def __init__(self, registro: dict[str, Any]) -> None:
        propriedades = registro.get("properties") or {}
        self.id = registro.get("id")
        self.type = registro.get("type")
        self.display_name = propriedades.get("displayName")
        self.status = propriedades.get("status") or None
        self.metadata = propriedades.get("metadata") or None

    def tem_atributo_properties(self) -> bool:
        """Este modelo NAO tem atributo ``properties`` — e é exatamente por isso que a linha do
        consumidor levanta ``AttributeError``."""
        return False


def _achados_do_consumidor(envelope: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    """Os achados que ``_list_defender_findings`` produziria sobre UM envelope entregue.

    Reproduz o filtro inteiro e devolve ``(viram achado, foram descartados)``, para que o teste
    afirme os DOIS ramos: sem o par, um filtro que nunca descarta pareceria correto.
    """
    achados: list[dict[str, Any]] = []
    descartados: list[str] = []
    for registro in envelope.get("value", []):
        assessment = _SdkAssessment(registro)
        status = assessment.status
        if status is None or status.get("code") == _CONSUMER_DISCARDED:
            descartados.append((status or {}).get("code", "<sem status>"))
            continue
        achados.append(
            {
                "assessment_id": assessment.id,
                "title": assessment.display_name,
                # A severidade e lida no caminho que o SDK publica (metadata.severity), e
                # maiuscula como o consumidor faz ao montar o achado.
                "severity": (assessment.metadata or {}).get("severity", "MEDIUM"),
                "resource_id": (registro.get("properties") or {}).get("resourceDetails", {}).get("id"),
            }
        )
    return achados, descartados


def _envelopes(diretorio: Path) -> list[Path]:
    """Os envelopes de verdade, lidos do disco — nunca a lista que o renderer montou."""
    return sorted(diretorio.glob("subscriptions/*/providers/Microsoft.Security/assessments/assessments.json"))


@pytest.fixture(scope="module")
def estate() -> CanonicalEstate:
    return apply_all(build_estate(seed=123, profile="small", currency="USD"))


@pytest.fixture(scope="module")
def spec() -> SurfaceSpec:
    return load_spec(DEFAULT_SPECS_ROOT / "azure" / _SPEC_FILE)


@pytest.fixture(scope="module")
def renderizado(estate: CanonicalEstate, tmp_path_factory: pytest.TempPathFactory) -> Path:
    renderer = AzureDefenderAssessmentsRenderer()
    out = tmp_path_factory.mktemp(renderer.name)
    renderer.render(estate, out)
    return out / renderer.name


@pytest.fixture(scope="module")
def envelopes(renderizado: Path) -> list[Path]:
    return _envelopes(renderizado)


@pytest.fixture(scope="module")
def registros(envelopes: list[Path]) -> list[dict[str, Any]]:
    """Todos os assessments entregues, vindos dos bytes em disco."""
    return [registro for envelope in envelopes for registro in json.loads(envelope.read_text(encoding="utf-8"))["value"]]


# -- 1. o contrato ---------------------------------------------------------------------------


def test_a_superficie_esta_na_matriz_e_a_spec_confere(spec: SurfaceSpec) -> None:
    coverage = coverage_for(_SURFACE)
    assert coverage is not None, f"{_SURFACE} ausente da matriz de fidelidade"
    assert coverage.renderer == _RENDERER
    assert spec.surface == _SURFACE
    assert set(spec.set_names) == {_ASSESSMENT_SCOPE, _LIST_SCOPE}


def test_o_envelope_carrega_exatamente_as_colunas_do_conjunto_da_lista(
    envelopes: list[Path], spec: SurfaceSpec
) -> None:
    for envelope in envelopes:
        achados = check_artifact(spec, envelope, scope=_LIST_SCOPE)
        assert is_faithful(achados), [str(item) for item in achados]


def test_o_registro_carrega_exatamente_as_colunas_do_conjunto_do_assessment(
    envelopes: list[Path], spec: SurfaceSpec, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """A projeção é o achatamento do ENVELOPE REAL contra os caminhos do conjunto ``assessment``.

    Os caminhos da spec levam o prefixo ``value[]`` (é onde o registro mora no corpo entregue),
    então o confronto é feito sobre o envelope inteiro — é assim que o auditor de fidelidade
    resolve caminho, e confrontar o registro solto acusaria ausência de tudo.
    """
    colunas = spec.columns_for(_ASSESSMENT_SCOPE)
    destino = tmp_path_factory.mktemp("assessments-projection")
    for indice, envelope in enumerate(envelopes):
        projetado = destino / f"{indice}.json"
        projetado.write_text(
            json.dumps(
                documented_projection(json.loads(envelope.read_text(encoding="utf-8")), colunas),
                indent=2,
            ),
            encoding="utf-8",
        )
        achados = check_artifact(spec, projetado, scope=_ASSESSMENT_SCOPE)
        assert is_faithful(achados), [str(item) for item in achados]


def test_nenhuma_coluna_preenchida_e_uma_coluna_que_a_spec_declara_vazia(
    envelopes: list[Path], spec: SurfaceSpec, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """O defeito simétrico: declarar o nome certo e escrever um valor inventado nele."""
    colunas = spec.columns_for(_ASSESSMENT_SCOPE)
    destino = tmp_path_factory.mktemp("assessments-values")
    for indice, envelope in enumerate(envelopes):
        projetado = destino / f"{indice}.json"
        projetado.write_text(
            json.dumps(
                documented_projection(json.loads(envelope.read_text(encoding="utf-8")), colunas),
                indent=2,
            ),
            encoding="utf-8",
        )
        vazias = spec.null_empty_names
        for nome in populated_of(projetado):
            assert nome not in vazias, f"{nome} saiu preenchida e a spec a declara sempre vazia"


def test_a_spec_nao_declera_ausente_nada_que_o_envelope_publique(spec: SurfaceSpec, registros: list[dict[str, Any]]) -> None:
    """Nenhum nome de TOPO do registro pode estar fora da spec (seria campo inventado).

    A spec prefixa cada coluna do registro com ``value[]`` -- e onde o registro mora no corpo
    entregue --, entao o confronto e contra o prefixo.
    """
    conhecidos = {nome[len(_ENVELOPE_PREFIX) :] for nome in spec.names if nome.startswith(_ENVELOPE_PREFIX)}
    for registro in registros:
        for nome in registro:
            assert nome in conhecidos, f"campo {nome!r} fora da spec"


# -- 2. a postura: os DOIS lados do filtro do consumidor ---------------------------------------


def test_o_consumidor_descarta_e_o_consumidor_faz_achado(envelopes: list[Path]) -> None:
    """A prova dois-lados: sobre os BYTES entregues, o filtro produz achado E descarta.

    Sem a metade do descarte, um filtro invertido (``!= "Healthy"``) passaria.
    """
    total_achados = 0
    total_descartados = 0
    for envelope in envelopes:
        achados, descartados = _achados_do_consumidor(json.loads(envelope.read_text(encoding="utf-8")))
        total_achados += len(achados)
        total_descartados += len(descartados)
    assert total_achados > 0, "o consumidor nao produz nenhum achado sobre o artefato"
    assert total_descartados > 0, "o consumidor nao descarta nada: o ramo Healthy nunca foi exercido"


def test_o_artefato_traz_os_tres_literais_publicados(registros: list[dict[str, Any]]) -> None:
    """Os três valores de ``AssessmentStatusCode`` aparecem — e ``NotApplicable`` é o que
    mostra que ele NÃO é o ramo descartado: o consumidor só descarta ``Healthy``."""
    vistos = Counter(registro["properties"]["status"]["code"] for registro in registros)
    assert set(vistos) == set(ASSESSMENT_HEALTH_CODES), vistos
    assert vistos[ASSESSMENT_HEALTH_HEALTHY] > 0
    assert vistos[ASSESSMENT_HEALTH_UNHEALTHY] > 0
    assert vistos[ASSESSMENT_HEALTH_NOT_APPLICABLE] > 0


def test_saude_fora_do_vocabulario_publicado_e_um_defeito_do_artefato(registros: list[dict[str, Any]]) -> None:
    for registro in registros:
        codigo = registro["properties"]["status"]["code"]
        assert codigo in ASSESSMENT_HEALTH_CODES, codigo


def test_a_severidade_so_aparece_no_ramo_unhealthy(registros: list[dict[str, Any]]) -> None:
    """Não há severidade de achado para projetar sobre um assessment saudável ou não aplicável."""
    for registro in registros:
        severidade = registro["properties"]["metadata"].get("severity")
        codigo = registro["properties"]["status"]["code"]
        if codigo == ASSESSMENT_HEALTH_UNHEALTHY:
            assert severidade in ASSESSMENT_SEVERITIES, severidade
        else:
            assert not severidade, f"{codigo} carrega severidade {severidade!r}"


def test_a_severidade_esta_no_caminho_documentado_e_nao_em_properties_severity(
    registros: list[dict[str, Any]]
) -> None:
    """O desvio medido contra o SDK real do consumidor.

    ``properties.severity`` NÃO existe nesta resposta — a severidade é publicada em
    ``properties.metadata.severity``. Se algum dia o artefato passar a escrever em
    ``properties.severity``, este teste quebra, e é para isso que ele existe.
    """
    com_severidade = [
        registro for registro in registros if registro["properties"]["metadata"].get("severity")
    ]
    assert com_severidade, "nenhum assessment Unhealthy com severidade: o consumidor nao teria o que ler"
    for registro in com_severidade:
        assert "severity" not in registro["properties"], "properties.severity nao e caminho publicado"
        assert registro["properties"]["metadata"]["severity"] in ASSESSMENT_SEVERITIES


# -- 3. a ancoragem ao modelo -----------------------------------------------------------------


def test_o_id_do_assessment_e_o_id_do_recurso_avaliado_mais_o_provider(
    registros: list[dict[str, Any]], estate: CanonicalEstate
) -> None:
    """A FORMA do id vem do exemplo de resposta: ``<id-do-recurso>/providers/Microsoft.Security/
    assessments/<guid>``, com ``name`` = o guid e ``type`` = ``Microsoft.Security/assessments``."""
    segmentos = {segment.segment_uuid: segment for segment in estate.network_segments}
    por_id = {registro["properties"]["resourceDetails"]["id"]: registro for registro in registros}
    assert por_id, "nenhum assessment com id de recurso avaliado"
    for recurso_id, registro in por_id.items():
        assert registro["id"] == f"{recurso_id}/providers/Microsoft.Security/assessments/{registro['name']}"
        assert registro["type"] == "Microsoft.Security/assessments"
        assert registro["properties"]["resourceDetails"]["source"] == "Azure"
        segmento = next((item for item in segmentos.values() if item.segment_id == recurso_id), None)
        assert segmento is not None, f"{recurso_id} nao e o id ARM de nenhum segmento do estado"


def test_o_id_do_recurso_avaliado_e_o_mesmo_que_o_segmento_o_publica(
    registros: list[dict[str, Any]], estate: CanonicalEstate
) -> None:
    """Não há duas grafias do mesmo id: o assessment usa o ``segment_id`` VERBATIM."""
    ids_do_estado = {segment.segment_id for segment in estate.network_segments if segment.provider == "azure"}
    for registro in registros:
        assert registro["properties"]["resourceDetails"]["id"] in ids_do_estado


def test_o_caminho_do_arquivo_nomeia_a_mesma_assinatura_que_o_id_publicado(
    envelopes: list[Path], registros: list[dict[str, Any]]
) -> None:
    """O caminho e o id não podem discordar sobre a assinatura — por isso o token vem do id."""
    for envelope in envelopes:
        assinatura = envelope.parts[-5]
        for registro in json.loads(envelope.read_text(encoding="utf-8"))["value"]:
            assert arm_id_token(registro["id"], "subscriptions") == assinatura, registro["id"]


def test_o_nome_do_assessment_e_um_guid_e_nunca_se_repete(
    registros: list[dict[str, Any]], estate: CanonicalEstate
) -> None:
    nomes = [registro["name"] for registro in registros]
    assert len(nomes) == len(set(nomes)), "dois assessments com o mesmo nome no mesmo escopo"
    for nome in nomes:
        assert len(nome) == 36 and nome.count("-") == 4, nome
    # e a MESMA grafia do modelo: o renderer compõe o id com este `assessment_id`
    ids_do_estado = {item.assessment_id for item in estate.azure_defender_assessments}
    assert set(nomes) == ids_do_estado


def test_as_datas_sao_instantes_fixos_e_em_utc(registros: list[dict[str, Any]]) -> None:
    """``status.firstEvaluationDate``/``statusChangeDate`` em UTC ISO 8601, e nunca ``now()``.

    A forma é a do exemplo de resposta (``...Z``). Um instante que mudasse entre execuções
    tornaria a postura de segurança irreprodutível.
    """
    for registro in registros:
        for membro in ("firstEvaluationDate", "statusChangeDate"):
            valor = registro["properties"]["status"][membro]
            assert valor is not None, membro
            assert valor.endswith("Z"), valor
            assert "T" in valor, valor


def test_a_postura_vem_da_constante_declarada_e_nao_de_um_sorteio(
    estate: CanonicalEstate, registros: list[dict[str, Any]]
) -> None:
    """O renderer publica os literais do estado, e o estado os tira de uma tabela declarada."""
    sensiveis = {
        postura for postura, saude, _ in const.AZURE_DEFENDER_ASSESSMENT_POSTURES if saude == const.SAUDE_ALTERNADA
    }
    assert sensiveis, "a constante nao declara nenhuma postura sensivel a saude"
    por_id = {assessment.assessment_id: assessment.health for assessment in estate.azure_defender_assessments}
    for registro in registros:
        assert registro["properties"]["status"]["code"] == por_id[registro["name"]]


def test_a_adicao_ao_modelo_e_opt_in(estate: CanonicalEstate) -> None:
    """A coleção nova entra com default vazio: nenhuma construção existente foi migrada.

    É o que sustenta a decisão de não pedir checkpoint -- ``Resource`` e ``NetworkSegment``
    não mudaram, e a coleção vive na raiz com default.
    """
    import dataclasses

    from tools.synthetic_clouds.model.estate import CanonicalEstate as _CanonicalEstate

    campo = next(
        item for item in dataclasses.fields(_CanonicalEstate) if item.name == "azure_defender_assessments"
    )
    assert campo.default == ()
    assert estate.azure_defender_assessments, "a colecao esta vazia: a superficie nao teria o que entregar"


def test_o_gate_rejeita_um_assessment_sem_segmento(estate: CanonicalEstate) -> None:
    """O gate de integridade confere a FK — um assessment orfao quebraria o id que ele publica."""
    from dataclasses import replace

    from tools.synthetic_clouds.validate.integrity import IntegrityError, check_no_orphans

    orfao = replace(
        estate.azure_defender_assessments[0],
        segment_uuid="00000000-0000-0000-0000-000000000000",
    )
    adulterado = replace(
        estate, azure_defender_assessments=(orfao, *estate.azure_defender_assessments[1:])
    )
    with pytest.raises(IntegrityError, match="orphan azure defender assessment"):
        check_no_orphans(adulterado)


# -- 4. o que NÃO é gerado, e por quê ---------------------------------------------------------


def test_o_catalogo_do_defender_nao_e_inventado(registros: list[dict[str, Any]]) -> None:
    """``displayName``/``description`` e o resto do catálogo saem vazios, e é uma lacuna NOMEADA.

    O texto de uma avaliação é do catálogo do Defender for Cloud, que o estado canônico não
    modela. Escrever um nome de avaliação seria afirmar sobre o provedor algo que nenhuma página
    consultada sustenta. O consumidor usa ``display_name`` como título do achado, então o título
    vazio é uma lacuna real — e é o que este teste impede que seja disfarçada.
    """
    for registro in registros:
        propriedades = registro["properties"]
        assert is_blank(propriedades["displayName"]), propriedades["displayName"]
        assert is_blank(propriedades["metadata"]["displayName"])
        assert is_blank(propriedades["metadata"]["description"])
        assert propriedades["metadata"]["categories"] == []
        assert propriedades["metadata"]["threats"] == []
        assert is_blank(propriedades["metadata"]["policyDefinitionId"])
        assert is_blank(propriedades["links"]["azurePortalUri"])
        assert propriedades["additionalData"] == {}
        # o exemplo de resposta traz "cause": "OffByPolicy" -- um exemplo de payload nao
        # publica vocabulario, entao o membro fica vazio
        assert is_blank(propriedades["status"]["cause"])
        assert is_blank(propriedades["status"]["description"])


def test_o_envelope_entrega_a_pagina_como_unica_e_o_nextlink_vazio(envelopes: list[Path]) -> None:
    """A página não publica tamanho de página nem cursor — um ``nextLink`` seria transporte inventado."""
    for envelope in envelopes:
        documento = json.loads(envelope.read_text(encoding="utf-8"))
        assert documento["nextLink"] is None
        assert documento["value"], "formato sem dado nao e dado"


def test_a_especificacao_registra_as_lacunas_como_topicos(spec: SurfaceSpec) -> None:
    """As lacunas são TOPICOS, não campos: um campo em ``unverified`` que também estivesse em
    ``sets`` tornaria qualquer artefato irremediavelmente inválido."""
    assert spec.unverified == (), "campo não comprovado em 'sets' tornaria o artefato inválido"
    topicos = {item.name for item in spec.unverified_topics}
    assert len(topicos) >= 8, topicos
    assert any("OffByPolicy" in nome for nome in topicos), "o valor exemplificado de 'cause' precisa ficar registrado"


def test_a_especificacao_nao_declura_que_o_consumidor_esta_certo(spec: SurfaceSpec) -> None:
    """A divergência SDK-vs-wire fica escrita na spec — é o entregável deste incremento para o
    lado do FinOps, e um teste que não a citasse deixaria o achado só na conversa."""
    texto = (DEFAULT_SPECS_ROOT / "azure" / _SPEC_FILE).read_text(encoding="utf-8")
    assert spec.reference["url"].endswith("view=rest-defenderforcloud-composite-stable")
    assert spec.delivery["api_version"] == "2021-06-01"
    # A divergencia fica na FONTE (o arquivo da spec), nao numa copia em memoria.
    assert "properties.metadata.severity" in texto
    assert "AttributeError" in texto
    assert "NotApplicable" in texto


def test_nenhum_marcador_do_simulador_vaza_para_o_artefato(registros: list[dict[str, Any]]) -> None:
    """Nenhum marcador do simulador aparece no JSON: a chave de postura é vocabulário nosso."""
    bruto = json.dumps(registros, ensure_ascii=False)
    for marcador in ("network-exposure", "endpoint-protection", "SAUDE_ALTERNADA", "not-applicable"):
        assert marcador not in bruto, marcador


def test_a_constante_de_postura_declara_o_que_o_renderer_publica() -> None:
    """Toda severidade declarada na constante é do domínio publicado."""
    for _, _, severidade in const.AZURE_DEFENDER_ASSESSMENT_POSTURES:
        assert severidade == "" or severidade in ASSESSMENT_SEVERITIES, severidade


# -- 5. a proveniência é a do entregável, e não parte do artefato ------------------------------


def test_a_proveniencia_registra_a_divergencia_do_consumidor_e_as_lacunas(renderizado: Path) -> None:
    arquivo = renderizado / "_provenance.json"
    assert arquivo.is_file()
    relatorio = json.loads(arquivo.read_text(encoding="utf-8"))
    divergencia = relatorio["consumer_divergence"]
    assert divergencia["read_by_consumer"] == "assessment.properties.severity"
    assert divergencia["published_by_provider"] == "properties.metadata.severity"
    assert divergencia["fixed_here"] is False, "esta superficie nao pode corrigir o consumidor"
    assert "AttributeError" in divergencia["measured"]
    assert set(relatorio["counts"]["saude"]) <= set(ASSESSMENT_HEALTH_CODES)


def test_a_proveniencia_conta_os_assessments_por_saude(renderizado: Path, registros: list[dict[str, Any]]) -> None:
    relatorio = json.loads((renderizado / "_provenance.json").read_text(encoding="utf-8"))
    assert relatorio["counts"]["assessments"] == len(registros)
    assert relatorio["counts"]["saude"] == dict(
        sorted(Counter(registro["properties"]["status"]["code"] for registro in registros).items())
    )
    assert len(relatorio["model_gaps"]) >= 8


def test_a_superficie_divide_renderizador_com_ninguem() -> None:
    """Um renderer que serve duas superfícies faz a auditoria acusar a IRMÃ como inventada."""
    from tools.synthetic_clouds.fidelity.matrix import SURFACES

    compartilhados = [c for c in SURFACES if c.renderer == _RENDERER]
    assert len(compartilhados) == 1
    assert compartilhados[0].surface == _SURFACE


def test_a_colecao_do_modelo_esta_ligada_aos_segmentos_azure(estate: CanonicalEstate) -> None:
    """Cada assessment pertence a um segmento Azure que existe, e a postura cobre cada segmento."""
    segmentos: dict[str, NetworkSegment] = {
        segment.segment_uuid: segment
        for segment in estate.network_segments
        if segment.provider == "azure"
    }
    assert estate.azure_defender_assessments
    for assessment in estate.azure_defender_assessments:
        assert assessment.segment_uuid in segmentos
    assert {a.segment_uuid for a in estate.azure_defender_assessments} == set(segmentos)
    assert len(estate.azure_defender_assessments) == len(segmentos) * len(const.AZURE_DEFENDER_ASSESSMENT_POSTURES)


def test_o_estado_reproduz_a_postura_entre_duas_execucoes() -> None:
    """Dado de segurança é EXATAMENTE repetível: mesma seed, mesmos assessments."""

    def chave(estado: CanonicalEstate) -> list[tuple[Any, ...]]:
        return [
            (
                item.posture,
                item.segment_uuid,
                item.assessment_id,
                item.health,
                item.severity,
                item.first_evaluated_at,
                item.status_changed_at,
            )
            for item in estado.azure_defender_assessments
        ]

    primeiro = build_estate(seed=123, profile="small", currency="USD")
    segundo = build_estate(seed=123, profile="small", currency="USD")
    assert chave(primeiro) == chave(segundo)


def test_a_especificacao_tem_as_colunas_que_o_consumidor_le(spec: SurfaceSpec) -> None:
    """``properties.status.code`` e ``id`` estao na spec e sao geráveis: um consumidor que
    precisa de uma coluna ausente da spec receberia um artefato invalido."""
    por_nome = {column.name: column for column in spec.columns}
    assert por_nome["value[].properties.status.code"].is_generatable
    assert por_nome["value[].id"].is_generatable
    assert por_nome["value[].name"].is_generatable
    assert por_nome["value[].properties.metadata.severity"].is_generatable
    # o caminho que o consumidor USA nao esta na spec: e ele que esta errado
    assert "value[].properties.severity" not in por_nome


def test_o_achado_do_consumidor_e_reproduzido_aqui_como_achado_de_artefato(
    envelopes: list[Path]
) -> None:
    """A leitura que o consumidor FAZ e a leitura que este teste faz: mesmo par, mesmas contagens.

    Se o renderer mudasse o estado publicado, o par (achado, descartado) mudaria junto e este
    teste acusaria.
    """
    achados_por_envelope: list[int] = []
    descartados_por_envelope: list[int] = []
    for envelope in envelopes:
        achados, descartados = _achados_do_consumidor(json.loads(envelope.read_text(encoding="utf-8")))
        achados_por_envelope.append(len(achados))
        descartados_por_envelope.append(len(descartados))
    assert all(achados_por_envelope), achados_por_envelope
    assert all(descartados_por_envelope), descartados_por_envelope
    # e nenhum envelope é de um só lado: um escopo inteiramente saudável esconderia o achado
    assert all(a > 0 and d > 0 for a, d in zip(achados_por_envelope, descartados_por_envelope, strict=True))


def test_nenhuma_constante_de_achado_do_consumidor_foi_inventada(registros: list[dict[str, Any]]) -> None:
    """O titulo do achado sai vazio — e a spec diz que ``displayName`` e o catalogo do Defender.

    Sem esta afirmacao, um dia alguem poderia preencher o titulo com o nome da postura do
    simulador (``network-exposure``) e o artefato passaria a afirmar sobre a Azure algo que
    nenhuma pagina consultada diz.
    """
    assert all(registro["properties"]["displayName"] is None for registro in registros)


def test_a_spec_nao_tem_coluna_inventada_nem_ausente(spec: SurfaceSpec, envelopes: list[Path]) -> None:
    """A barreira final: nenhuma divergência de nenhum tipo, nos dois conjuntos."""
    todos: list[Finding] = []
    for envelope in envelopes:
        todos.extend(check_artifact(spec, envelope, scope=_LIST_SCOPE))
    assert not [item for item in todos if item.kind in {KIND_INVENTED, KIND_UNVERIFIED, KIND_MISSING, KIND_POPULATED_EMPTY}]


def test_a_especificacao_publica_o_escopo_do_consumidor(spec: SurfaceSpec) -> None:
    """O consumidor consulta a ASSINATURA, e um envelope por assinatura e o recorte correto."""
    assert spec.delivery["partitioning"].startswith("subscriptions/")
    assert "/providers/Microsoft.Security/assessments/" in spec.delivery["partitioning"]
    assert "grupo de gerenciamento" in json.dumps(spec.delivery, ensure_ascii=False)