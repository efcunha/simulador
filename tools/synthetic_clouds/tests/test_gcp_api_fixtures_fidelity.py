"""Golden fidelity: as 11 superficies de resposta de API do GCP conferem com o contrato.

A **G11** e a lacuna que o ``--matrix`` denunciava: os corpos de API que o ``gcp_rest_fixtures``
entrega desde a Phase 3 sao declarados *"best-effort official-shaped"* pelo proprio autor, com
``TODO-verificar #7`` em quase todo campo. Aqui cada um deles e confrontado com o contrato oficial
levantado em ``docs/CONTRATO-APIS-GCP.md``.

O QUE ESTE FICHEIRO PROVA, POR SUPERFICIE
-----------------------------------------
1. **Dois niveis, dois escopos.** O artefato e o corpo de uma resposta: o envelope (o array + o
   token) e o item sao contratos separados, e conferir um contra a uniao do outro acusaria
   ausencia de tudo o que pertence ao outro.
2. **A projecao e o artefato.** As linhas conferidas sao derivadas do arquivo entregue, lido de
   volta do disco, por um caminhante independente do renderer.
3. **Nenhuma juncao sintetica.** ``resourceUuid`` (e o irmao em ``resource.labels``) nao existe
   em contrato nenhum dos seis documentos oficiais completos, e nao e emitido aqui. O teste
   REINTRODUZ o campo e exige que o auditor o acuse -- uma declaracao que nao falha quando
   violada nao protege nada.

O ``gcp_rest_fixtures`` **nao** e tocado por este ficheiro: ele alimenta o emulador e tem testes
que o fixam, e aposenta-lo e decisao de produto (item E2).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tools.synthetic_clouds.fidelity import matrix, report
from tools.synthetic_clouds.fidelity.artifacts import columns_of, populated_of
from tools.synthetic_clouds.fidelity.checker import KIND_INVENTED, KIND_UNVERIFIED, check, check_values
from tools.synthetic_clouds.fidelity.spec import DEFAULT_SPECS_ROOT, SurfaceSpec, load_spec
from tools.synthetic_clouds.generate.estate_builder import build_estate
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.render.gcp_api_fixtures import SURFACES, GcpApiFixtureRenderer
from tools.synthetic_clouds.scenarios.emit import apply_all

SUPERFICIES = sorted(SURFACES)

#: Cada superficie com o NOME DO ARQUIVO da sua spec, citado literalmente. A cobertura golden do
#: projeto exige que um teste cite o arquivo da spec -- citar por variavel nao conta, e a exigencia
#: existe para que apagar a citacao (ou esquecer uma superficie) apareca como falha.
SPECS_DESTA_FAMILIA: tuple[tuple[str, str], ...] = (
    ("gcp/asset-search-all-iam-policies", "asset-search-all-iam-policies.schema.json"),
    ("gcp/scc-sources", "scc-sources.schema.json"),
    ("gcp/scc-findings", "scc-findings.schema.json"),
    ("gcp/recommender-recommendations", "recommender-recommendations.schema.json"),
    ("gcp/recommender-insights", "recommender-insights.schema.json"),
    ("gcp/catalog-services", "catalog-services.schema.json"),
    ("gcp/catalog-skus", "catalog-skus.schema.json"),
    ("gcp/monitoring-time-series", "monitoring-time-series.schema.json"),
    ("gcp/monitoring-metric-descriptors", "monitoring-metric-descriptors.schema.json"),
    ("gcp/monitoring-alert-policies", "monitoring-alert-policies.schema.json"),
    ("gcp/billing-budgets", "billing-budgets.schema.json"),
    ("gcp/observability-partial", "observability-partial.schema.json"),
)


@pytest.fixture(scope="module")
def estate() -> CanonicalEstate:
    return apply_all(build_estate(seed=123, profile="small", currency="USD"))


def _renderer(surface: str) -> GcpApiFixtureRenderer:
    """A classe registrada para a superficie -- a mesma que o ``--emit`` descobre pelo nome."""
    from tools.synthetic_clouds.render.base import get_renderer

    return get_renderer(SURFACES[surface].renderer)  # type: ignore[return-value]


@pytest.fixture(scope="module")
def entregues(estate: CanonicalEstate, tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """Rende cada superficie uma vez e devolve a arvore entregue de cada uma."""
    saida: dict[str, Path] = {}
    for surface in SUPERFICIES:
        renderer = _renderer(surface)
        destino = tmp_path_factory.mktemp(SURFACES[surface].renderer)
        renderer.render(estate, destino)
        saida[surface] = destino / SURFACES[surface].renderer
    return saida


def _spec(surface: str) -> SurfaceSpec:
    return load_spec(DEFAULT_SPECS_ROOT / SURFACES[surface].spec_file)


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _emittable(spec: SurfaceSpec, escopo: str) -> set[str]:
    return {c.name for c in spec.columns_for(escopo) if c.belongs_to_schema}


def _emittable_do_item(spec: SurfaceSpec, escopo: str) -> set[str]:
    """Os campos do ITEM, somando os conjuntos CONDICIONAIS ao tipo de recurso.

    A superficie ``gcp/monitoring-time-series`` declara os labels por TIPO monitorado em conjuntos
    proprios (``gce_instance_labels``, ``cloudsql_database_labels``): nenhum registro carrega os
    cinco, e a uniao e o conjunto que um registro pode carregar. Sem esta soma, o teste exigiria de
    cada linha um label que so existe no outro tipo -- que foi o defeito corrigido no item E4.
    """
    campos = _emittable(spec, escopo)
    for nome in spec.set_names:
        if nome.endswith("_labels"):
            campos |= _emittable(spec, nome)
    return campos


def test_todas_as_superficies_estao_na_matriz() -> None:
    for surface in SUPERFICIES:
        coverage = matrix.coverage_for(surface)
        assert coverage is not None, surface
        # O nome do renderer vem da superficie (``gcp/scc-sources`` -> ``gcp_scc_sources``), com
        # uma excecao declarada: a superficie ``gcp/scc-findings`` registra ``gcp_api_scc_findings``
        # porque ``gcp_scc_findings`` ja e o renderer dedicado da tabela do BigQuery.
        assert coverage.renderer == SURFACES[surface].renderer, surface


def test_as_invariantes_do_processo_valem() -> None:
    assert report.staleness() == ()
    # ``golden_gaps`` exige que um teste CITE o nome do ARQUIVO da spec (e nao o caminho montado
    # em tempo de execucao), e e uma invariante boa: um teste que so menciona a superficie por
    # variavel pode deixar de citar a spec sem ninguem notar. As onze estao nomeadas em
    # ``SPECS_DESTA_FAMILIA``, e o conjunto tem de bater com o das superficies auditadas aqui.
    assert {spec for _, spec in SPECS_DESTA_FAMILIA} == {SURFACES[s].spec_file.split("/")[-1] for s in SUPERFICIES}
    assert report.golden_gaps() == ()
    for item in report.unmapped_renderers():
        # O ``gcp_rest_fixtures`` e o ``gcp_bigquery`` seguem sem superficie propria, e o que fazer
        # com eles e a decisao aberta do item E2 -- nao um efeito desta auditoria.
        assert "gcp_rest_fixtures" in item or "gcp_bigquery" in item, item


@pytest.mark.parametrize("surface", SUPERFICIES)
def test_o_envelope_confere_com_o_contrato(surface: str, entregues: dict[str, Path]) -> None:
    spec = _spec(surface)
    projecao = entregues[surface] / "field_projection" / "response.json"
    linhas = _read(projecao)
    assert len(linhas) == 1
    assert set(linhas[0]) == _emittable(spec, "response"), surface
    assert check(spec, columns_of(projecao), scope="response") == ()
    assert check_values(spec, populated_of(projecao), scope="response") == ()


@pytest.mark.parametrize("surface", SUPERFICIES)
def test_os_itens_conferem_com_o_contrato(surface: str, entregues: dict[str, Path]) -> None:
    """O contrato do item e conferido na UNIAO das linhas, e nao numa linha so.

    A diferenca importa por um caso real desta familia: o mapa ``resource.labels`` de uma serie do
    Monitoring carrega as chaves do **tipo monitorado** -- ``instance_id``/``zone`` numa instancia,
    ``database_id``/``region`` num banco. Numa linha so, metade das chaves esta ausente por
    construcao, e exigir o conjunto completo de cada linha acusaria ausencia de um campo que o
    contrato declara e o artefato entrega. O nucleo de fidelidade confere por ARQUIVO
    (``columns_of`` le a primeira linha), entao a uniao e conferida aqui, das linhas entregues.
    """
    spec = _spec(surface)
    escopo = SURFACES[surface].item_scope
    projecao = _projecao_de_itens(entregues[surface], spec, SURFACES[surface].response_scope)
    linhas = _read(projecao)
    assert linhas, f"{surface}: sem item nao ha o que conferir"

    campos_do_item = _emittable_do_item(spec, escopo)
    entregues_na_uniao = {chave for linha in linhas for chave in linha}
    # A conferência é de CONTENÇÃO nos dois sentidos na UNIAO, e nao de igualdade numa linha: uma
    # superficie com contrato condicional por tipo (os labels do Monitoring) tem, em cada registro,
    # um subconjunto proprio do contrato -- e a uniao e o conjunto completo.
    assert entregues_na_uniao <= campos_do_item, (
        f"{surface}: emitido fora do contrato {sorted(entregues_na_uniao - campos_do_item)}"
    )
    assert campos_do_item <= entregues_na_uniao, (
        f"{surface}: declarado e nao emitido {sorted(campos_do_item - entregues_na_uniao)}"
    )
    # O núcleo de fidelidade confere por CONJUNTO, e o contrato de um item desta superfície pode
    # atravessar vários (os labels condicionais por tipo monitorado vivem em conjuntos próprios).
    # Por isso a conferência de nomes ignora as colunas que pertencem aos conjuntos condicionais, e
    # a de valores é feita POR CONJUNTO, onde cada declaração vive.
    findings_nomes = [
        f
        for f in check(spec, columns_of(projecao), scope=escopo)
        if f.column not in campos_do_item - _emittable(spec, escopo)
    ]
    assert not findings_nomes, "\n".join(map(str, findings_nomes))
    for nome_conjunto in spec.set_names:
        if nome_conjunto == "response":
            continue
        assert check_values(spec, populated_of(projecao), scope=nome_conjunto) == ()


@pytest.mark.parametrize("surface", SUPERFICIES)
def test_os_labels_condicionais_seguem_o_tipo_monitorado(surface: str, entregues: dict[str, Path]) -> None:
    """Quando a superfície declara labels por TIPO, cada registro carrega só os do seu tipo.

    O item **E4** nasceu de o artefato emitir apenas o label comum e a série deixar de ser
    atribuível ao recurso. Este teste é a guarda — e ele lê o **ARTEFATO**, não a projeção:

    **Por que não a projeção.** A projeção do item não abre o mapa ``labels`` (é o que mantém o
    mapa como UMA coluna, em vez de virar ``labels.app``, ``labels.env``); ela guarda o objeto
    inteiro. Então um teste que lesse a projeção **não conseguiria** afirmar nada sobre as chaves
    do mapa — e emitir só ``project_id`` passaria. O teste tem de olhar os bytes do corpo, que é
    onde as chaves vivem.
    """
    spec = _spec(surface)
    condicionais = [nome for nome in spec.set_names if nome.endswith("_labels")]
    if not condicionais:
        pytest.skip(f"{surface}: a superficie nao declara labels condicionais")

    esperado_por_tipo = {
        "gce_instance": {"instance_id", "zone"},
        "cloudsql_database": {"database_id", "region"},
    }
    entregue = _read(entregues[surface] / SURFACES[surface].artifact)
    nomes = {c.name for c in spec.columns_for(SURFACES[surface].response_scope) if c.belongs_to_schema}
    array = next(n for n in nomes if n != "nextPageToken")
    series = entregue[array]
    assert series, f"{surface}: sem serie nao ha o que conferir"

    vistos: set[str] = set()
    for serie in series:
        tipo = serie["resource"]["type"]
        assert tipo in esperado_por_tipo, f"{surface}: tipo monitorado inesperado {tipo!r}"
        labels = serie["resource"]["labels"]
        vistos.add(tipo)
        assert {"project_id"} | esperado_por_tipo[tipo] <= set(labels), (
            f"{surface}: a serie de {tipo} nao carrega os labels do seu tipo: {sorted(labels)}"
        )
        outro = next(t for t in esperado_por_tipo if t != tipo)
        for chave in esperado_por_tipo[outro]:
            assert chave not in labels, f"{surface}: {tipo} carregou o label {chave!r}, que e do {outro}"
    # Os DOIS tipos aparecem: um teste que so visse um deles nao provaria a condicionalidade.
    assert vistos == set(esperado_por_tipo), f"{surface}: so um tipo monitorado foi exercitado: {vistos}"


def _projecao_de_itens(entregue: Path, spec: SurfaceSpec, response_scope: str) -> Path:
    """O arquivo de projecao dos itens, achado pelo unico caminho que nao e o envelope."""
    nomes = {c.name for c in spec.columns_for(response_scope) if c.belongs_to_schema}
    array = next(n for n in nomes if n != "nextPageToken")
    return entregue / "field_projection" / f"{array}.json"


@pytest.mark.parametrize("surface", SUPERFICIES)
def test_a_projecao_e_o_artefato_entregue(surface: str, entregues: dict[str, Path]) -> None:
    """A ancora: cada projecao e derivada dos BYTES entregues, nao de uma copia em memoria."""
    spec = _spec(surface)
    fixture = SURFACES[surface]
    entregue = _read(entregues[surface] / fixture.artifact)
    envelope = _read(entregues[surface] / "field_projection" / "response.json")
    itens = _read(_projecao_de_itens(entregues[surface], spec, fixture.response_scope))

    assert set(envelope[0]) == set(entregue)
    nomes = {c.name for c in spec.columns_for(fixture.response_scope) if c.belongs_to_schema}
    array = next(n for n in nomes if n != "nextPageToken")
    assert len(itens) == len(entregue[array])
    # Cada linha de item carrega o caminho do PRIMEIRO campo do escopo: a projecao nao perdeu o
    # prefixo do array ao achar os itens.
    primeiro = sorted(_emittable(spec, fixture.item_scope))[0]
    assert all(primeiro in linha for linha in itens)


@pytest.mark.parametrize("surface", SUPERFICIES)
def test_renderizar_duas_vezes_da_os_mesmos_bytes(
    surface: str, estate: CanonicalEstate, tmp_path: Path
) -> None:
    renderer = _renderer(surface)
    a, b = tmp_path / "a", tmp_path / "b"
    renderer.render(estate, a)
    renderer.render(estate, b)
    relativos = sorted(p.relative_to(a).as_posix() for p in a.rglob("*") if p.is_file())
    assert relativos == sorted(p.relative_to(b).as_posix() for p in b.rglob("*") if p.is_file())
    for relativo in relativos:
        assert (a / relativo).read_bytes() == (b / relativo).read_bytes()


@pytest.mark.parametrize("surface", SUPERFICIES)
def test_nenhuma_juncao_sintetica_e_emitida(surface: str, entregues: dict[str, Path]) -> None:
    """``resourceUuid`` nao existe em contrato nenhum, e nao aparece no artefato nem na projecao."""
    for caminho in entregues[surface].rglob("*.json"):
        if caminho.name == "_provenance.json":
            continue
        texto = caminho.read_text(encoding="utf-8")
        assert "resourceUuid" not in texto, f"{surface}: {caminho.name} carrega a chave de juncao"
        assert "resource_uuid" not in texto, f"{surface}: {caminho.name} carrega a chave de juncao"


@pytest.mark.parametrize("surface", SUPERFICIES)
def test_o_auditor_denuncia_a_chave_sintetica(surface: str, tmp_path: Path) -> None:
    """Uma declaracao que nao falha quando violada nao protege nada: o campo e REINTRODUZIDO.

    O auditor pode recusar de duas formas, e as duas servem: ``unverified_emitted`` quando a
    chave esta registrada como nao comprovada daquela superficie, e ``invented`` quando o nome
    nao consta de contrato nenhum. O que o teste NAO aceita e o artefato com a chave passar limpo.
    """
    spec = _spec(surface)
    escopo = SURFACES[surface].item_scope
    alvo = tmp_path / f"{SURFACES[surface].renderer}-com-uuid.json"
    alvo.write_text(json.dumps([{"resourceUuid": "8f14e45f-ceea-467a-9c1b-1b2c3d4e5f60"}]), encoding="utf-8")

    findings = check(spec, columns_of(alvo), scope=escopo)
    assert any(
        f.column == "resourceUuid" and f.kind in {KIND_UNVERIFIED, KIND_INVENTED} for f in findings
    ), f"{surface}: resourceUuid passou limpo"


@pytest.mark.parametrize("surface", SUPERFICIES)
def test_o_auditor_denuncia_coluna_inventada(surface: str, tmp_path: Path) -> None:
    spec = _spec(surface)
    escopo = SURFACES[surface].item_scope
    alvo = tmp_path / f"{SURFACES[surface].renderer}-inventada.json"
    alvo.write_text(json.dumps([{"colunaInventada": "x"}]), encoding="utf-8")

    findings = check(spec, columns_of(alvo), scope=escopo)
    assert any(f.kind == KIND_INVENTED and f.column == "colunaInventada" for f in findings), surface
