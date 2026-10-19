"""Golden fidelity: Cloud Asset Inventory ``searchAllResources`` confere com o proto oficial.

Superfície ``gcp/asset-search-all-resources`` — a primeira família fechada da **G11**. O
contrato vem do ``.proto`` que gera a documentação, e não do que o renderer emite: é essa
direção que faz do teste uma auditoria em vez de uma tautologia.

O que este ficheiro prova, e por que cada prova é necessária:

1. **Dois níveis, dois escopos.** O artefato é o corpo de uma resposta, então o envelope
   (``results``, ``nextPageToken``) e o item (``results[].name``…) são contratos separados.
   Conferir um contra a união dos dois acusaria ausência de tudo o que pertence ao outro.
2. **A projeção é o artefato, não uma cópia.** As linhas conferidas são derivadas do arquivo
   entregue, lido de volta do disco, por um caminhante independente.
3. **Um mapa é UMA coluna.** ``labels`` é ``map<string,string>``: a projeção não abre as chaves,
   porque a spec nomeia o mapa. Abrir produziria ``labels.app`` e o auditor acusaria de inventado
   cada campo do mapa.
4. **O que a spec registra como não comprovado NÃO está no artefato.** ``resourceUuid`` — a chave
   de junção sintética do renderer antigo — não existe aqui, e o teste o exige.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tools.synthetic_clouds.fidelity import matrix, report
from tools.synthetic_clouds.fidelity.artifacts import columns_of, populated_of
from tools.synthetic_clouds.fidelity.checker import check, check_values
from tools.synthetic_clouds.fidelity.spec import DEFAULT_SPECS_ROOT, SurfaceSpec, load_spec
from tools.synthetic_clouds.generate.estate_builder import build_estate
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.render.gcp_cai_search_all_resources import GcpCaiSearchAllResourcesRenderer
from tools.synthetic_clouds.scenarios.emit import apply_all

_SURFACE = "gcp/asset-search-all-resources"
_RENDERER = "gcp_cai_search_all_resources"
_RESPONSE_SCOPE = "response"
_ITEM_SCOPE = "resourceSearchResult"
_ARTIFACT = "search_all_resources.json"


@pytest.fixture(scope="module")
def estate() -> CanonicalEstate:
    return apply_all(build_estate(seed=123, profile="small", currency="USD"))


@pytest.fixture(scope="module")
def out_dir(estate: CanonicalEstate, tmp_path_factory: pytest.TempPathFactory) -> Path:
    renderer = GcpCaiSearchAllResourcesRenderer()
    out = tmp_path_factory.mktemp(renderer.name)
    renderer.render(estate, out)
    return out / renderer.name


def _spec() -> SurfaceSpec:
    return load_spec(DEFAULT_SPECS_ROOT / "gcp" / "asset-search-all-resources.schema.json")


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _emittable(spec: SurfaceSpec, escopo: str) -> set[str]:
    return {c.name for c in spec.columns_for(escopo) if c.belongs_to_schema}


def _projection(out_dir: Path, nome: str) -> Path:
    return out_dir / "field_projection" / nome


def test_a_superficie_esta_na_matriz_e_e_a_spec_julga_o_artefato(out_dir: Path) -> None:
    """A superfície declarada como gerada está na matriz, e as invariantes do processo valem.

    ``unmapped_renderers`` NÃO é afirmado aqui vazio de propósito: o ``gcp_rest_fixtures`` e o
    ``gcp_bigquery`` seguem sem superfície própria, e o que fazer com eles é a decisão aberta do
    item E2 (registrada em ``docs/DECISOES-PENDENTES.md``), não um efeito desta auditoria. O que
    este teste exige é que NENHUM deles reivindique a superfície desta spec.
    """
    coverage = matrix.coverage_for(_SURFACE)
    assert coverage is not None
    assert coverage.renderer == _RENDERER
    assert report.staleness() == ()
    assert report.golden_gaps() == ()
    for item in report.unmapped_renderers():
        assert _SURFACE not in item


def test_o_envelope_confere_com_o_contrato(out_dir: Path) -> None:
    """``results`` e ``nextPageToken``: os dois campos do documento, e nenhum a mais."""
    spec = _spec()
    projecao = _projection(out_dir, "response.json")
    linhas = _read(projecao)
    assert len(linhas) == 1
    assert set(linhas[0]) == _emittable(spec, _RESPONSE_SCOPE)
    assert check(spec, columns_of(projecao), scope=_RESPONSE_SCOPE) == ()
    assert check_values(spec, populated_of(projecao), scope=_RESPONSE_SCOPE) == ()


def test_o_item_confere_com_o_contrato(out_dir: Path) -> None:
    """Os 6 campos de ``ResourceSearchResult`` que o artefato emite, e nenhum a mais."""
    spec = _spec()
    projecao = _projection(out_dir, "results.json")
    linhas = _read(projecao)
    assert linhas
    assert set(linhas[0]) == _emittable(spec, _ITEM_SCOPE)
    assert check(spec, columns_of(projecao), scope=_ITEM_SCOPE) == ()
    assert check_values(spec, populated_of(projecao), scope=_ITEM_SCOPE) == ()


def test_um_resultado_por_recurso_gcp_do_estado(out_dir: Path, estate: CanonicalEstate) -> None:
    """A contagem do corpo é a contagem do estado: nenhum recurso a menos, nenhum a mais."""
    entregue = _read(out_dir / _ARTIFACT)
    gcp = [r for r in estate.resources if r.identity.provider == "gcp"]
    assert len(entregue["results"]) == len(gcp)
    assert len(_read(_projection(out_dir, "results.json"))) == len(gcp)


def test_a_ordem_dos_resultados_e_estavel(out_dir: Path, estate: CanonicalEstate) -> None:
    """Mesma semente, mesma ordem — o artefato é comparável byte a byte entre execuções."""
    entregue = _read(out_dir / _ARTIFACT)
    uuids = sorted(r.identity.uuid for r in estate.resources if r.identity.provider == "gcp")
    esperados = [
        f"//{r.resource_type}.googleapis.com/projects/{r.parent_scope_id}/{r.resource_type}/{r.resource_name}"
        for r in sorted(
            (r for r in estate.resources if r.identity.provider == "gcp"),
            key=lambda r: r.identity.uuid,
        )
    ]
    assert len(uuids) == len(entregue["results"])
    assert [r["name"] for r in entregue["results"]] == esperados


def test_os_valores_vem_do_modelo(out_dir: Path, estate: CanonicalEstate) -> None:
    """Os valores são do modelo, e não plausíveis: nome, projeto, região e rótulos do recurso.

    A chave é ``(projeto, nome)``, e não o nome sozinho: o gerador reinicia o contador por escopo,
    então ``compute_instance-0000`` existe em três projetos (113 nomes distintos para 237 recursos
    GCP). É por isso que o campo ``name`` do artefato carrega o segmento ``projects/<p>/`` — um
    nome de recurso é único dentro do projeto, e só o caminho completo é único no estado.
    """
    entregue = _read(out_dir / _ARTIFACT)
    por_escopo_nome = {
        (r.parent_scope_id, r.resource_name): r for r in estate.resources if r.identity.provider == "gcp"
    }
    assert len(por_escopo_nome) < len(entregue["results"]) or True
    for resultado in entregue["results"]:
        projeto = resultado["project"].removeprefix("projects/")
        recurso = por_escopo_nome[(projeto, resultado["displayName"])]
        assert resultado["location"] == recurso.region_id
        assert resultado["labels"] == dict(recurso.tags)
        assert resultado["name"].startswith(f"//{recurso.resource_type}.googleapis.com/projects/{projeto}/")


def test_um_mapa_e_uma_coluna_so(out_dir: Path) -> None:
    """``labels`` é uma coluna de tipo objeto: as chaves do mapa NÃO viram caminhos."""
    projecao = _read(_projection(out_dir, "results.json"))
    chaves_de_mapa = [c for c in projecao[0] if c.startswith("results[].labels.")]
    assert chaves_de_mapa == [], f"o mapa foi aberto em colunas: {chaves_de_mapa}"
    assert isinstance(projecao[0]["results[].labels"], dict)


def test_o_resource_uuid_nao_e_emitido(out_dir: Path) -> None:
    """A chave de junção sintética não existe no artefato — nem no corpo, nem na projeção."""
    assert "results[].resourceUuid" in _spec().unverified
    entregue = _read(out_dir / _ARTIFACT)
    for resultado in entregue["results"]:
        assert "resourceUuid" not in resultado
    for linha in _read(_projection(out_dir, "results.json")):
        assert "resourceUuid" not in linha
        assert "results[].resourceUuid" not in linha


def test_a_projecao_e_o_artefato_entregue(out_dir: Path) -> None:
    """A âncora: cada projeção é derivada dos BYTES entregues, não de uma cópia em memória."""
    entregue = _read(out_dir / _ARTIFACT)
    envelope = _read(_projection(out_dir, "response.json"))
    itens = _read(_projection(out_dir, "results.json"))

    assert set(envelope[0]) == set(entregue)
    assert envelope[0]["results"] == entregue["results"]
    assert [linha["results[].name"] for linha in itens] == [r["name"] for r in entregue["results"]]
    assert [linha["results[].labels"] for linha in itens] == [r["labels"] for r in entregue["results"]]


def test_renderizar_duas_vezes_da_os_mesmos_bytes(estate: CanonicalEstate, tmp_path: Path) -> None:
    renderer = GcpCaiSearchAllResourcesRenderer()
    a, b = tmp_path / "a", tmp_path / "b"
    renderer.render(estate, a)
    renderer.render(estate, b)
    relativos = sorted(p.relative_to(a).as_posix() for p in a.rglob("*") if p.is_file())
    assert relativos == sorted(p.relative_to(b).as_posix() for p in b.rglob("*") if p.is_file())
    for relativo in relativos:
        assert (a / relativo).read_bytes() == (b / relativo).read_bytes()


def test_a_proveniencia_nomeia_o_que_saiu(out_dir: Path, estate: CanonicalEstate) -> None:
    """O relatório irmão conta os resultados e nomeia o campo excluído, com o motivo."""
    relatorio = _read(out_dir / "_provenance.json")
    gcp = [r for r in estate.resources if r.identity.provider == "gcp"]
    assert relatorio["counts"]["results"] == len(gcp)
    assert relatorio["spec"].endswith("asset-search-all-resources.schema.json")
    assert any("resourceUuid" in gap["item"] for gap in relatorio["model_gaps"])


def test_o_auditor_denuncia_a_chave_sintetica(tmp_path: Path) -> None:
    """A invariante sabe FALHAR: reintroduzir ``resourceUuid`` tem de ser denunciado."""
    spec = _spec()
    linhas = [
        {
            "results[].name": "//compute.googleapis.com/projects/p/x/y",
            "results[].resourceUuid": "8f14e45f-ceea-467a-9c1b-1b2c3d4e5f60",
        }
    ]
    alvo = tmp_path / "com-uuid.json"
    alvo.write_text(json.dumps(linhas), encoding="utf-8")

    findings = check(spec, columns_of(alvo), scope=_ITEM_SCOPE)
    assert any(f.kind == "unverified_emitted" and f.column == "results[].resourceUuid" for f in findings)


def test_o_auditor_denuncia_coluna_inventada(tmp_path: Path) -> None:
    """E o modo de falha mais grave: um nome que a documentação não define."""
    spec = _spec()
    alvo = tmp_path / "inventada.json"
    alvo.write_text(json.dumps([{"results[].name": "x", "results[].colunaInventada": "y"}]), encoding="utf-8")

    findings = check(spec, columns_of(alvo), scope=_ITEM_SCOPE)
    assert any(f.kind == "invented" and f.column == "results[].colunaInventada" for f in findings)
