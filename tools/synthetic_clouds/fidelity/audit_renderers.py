"""Auditoria ponta a ponta: renderiza cada superficie e confronta com a spec.

Os testes golden provam a fidelidade superficie a superficie, cada um no seu
arquivo. Isto prova o CONJUNTO: percorre a matriz, renderiza o que esta declarado
como gerado e mede duas coisas que nenhum teste isolado enxerga --

* **coluna inventada**, na uniao dos artefatos de uma superficie; e
* **registro existente**, porque um artefato pode trazer os 181 nomes
  documentados e nenhum fluxo. Foi assim que a rede passou despercebida: fiel ao
  formato e vazia.

Nao entra na suite: renderiza tudo, e a suite precisa ser rapida. E a ferramenta
de manutencao que responde "o simulador entrega o que promete?".
"""

from __future__ import annotations

import csv
import gzip
import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tools.synthetic_clouds.fidelity import matrix
from tools.synthetic_clouds.fidelity.artifacts import (
    ArtifactError,
    columns_of,
    populated_of,
    populated_paths,
)
from tools.synthetic_clouds.fidelity.spec import DEFAULT_SPECS_ROOT, load_spec
from tools.synthetic_clouds.generate.estate_builder import build_estate
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.render.base import get_renderer

#: Chaves que carregam lista de registros num documento JSON.
_RECORD_KEYS = ("records", "rows", "assets", "instances", "findings", "items", "data", "blobs")

_SUFIXOS = ("**/*.parquet", "**/*.csv", "**/*.json", "**/*.jsonl", "**/*.ndjson", "**/*.log")


@dataclass(frozen=True, slots=True)
class SurfaceAudit:
    """O que a auditoria de UMA superficie mediu."""

    surface: str
    renderer: str
    artifacts: int
    records: int
    invented: tuple[str, ...]
    per_set: tuple[tuple[str, int, int], ...]  # (conjunto, presentes, total)
    populated: int = 0  # nomes de TOPO com valor -- subconta superficie aninhada
    documented: int = 0  # CAMINHOS da spec com valor: a taxa honesta
    #: Colunas que a spec marca ``required`` e que estao vazias em TODAS as linhas.
    #: NAO e prova de defeito -- no FOCUS, ``required`` significa que a COLUNA deve
    #: existir, e o valor pode ser nulo quando nao se aplica (``ChargeClass`` so vale
    #: em linha de correcao). E prova de que algo precisa ser EXPLICADO: ou o dado
    #: tem fonte e falta, ou a ausencia tem motivo declarado. Foi assim que a Azure
    #: apareceu com 61 de 104 enquanto AWS e GCP tinham zero.
    required_empty: tuple[str, ...] = ()
    error: str | None = None


def _export_artifacts(directory: Path) -> list[Path]:
    """Artefatos de export, fora a proveniencia.

    Arquivo comecado por ``_`` e o relatorio irmao (``_provenance.json``): carrega
    `spec`, `mechanism`, `model_gaps` e contagens. Unir as chaves dele com as do
    export acusaria invencao onde ha proveniencia bem separada -- ja aconteceu.
    """
    encontrados: list[Path] = []
    for padrao in _SUFIXOS:
        encontrados.extend(
            caminho
            for caminho in sorted(directory.glob(padrao))
            if caminho.is_file() and caminho.stat().st_size and not caminho.name.startswith("_")
        )
    return encontrados


def _abrir(caminho: Path) -> Any:
    return gzip.open(caminho, "rt", encoding="utf-8") if caminho.suffix == ".gz" else caminho.open(
        "r", encoding="utf-8", errors="replace"
    )


def _records_of(caminho: Path) -> int:
    """Registros do artefato, ou 0 quando ele nao carrega registro nenhum."""
    nome = caminho.name.lower()
    try:
        if nome.endswith(".parquet"):
            import pyarrow.parquet as pq

            return int(pq.read_metadata(caminho).num_rows)
        if nome.endswith((".csv", ".csv.gz")):
            with _abrir(caminho) as handle:
                return max(0, sum(1 for _ in csv.reader(handle)) - 1)
        if nome.endswith((".log", ".log.gz", ".jsonl", ".jsonl.gz", ".ndjson")):
            with _abrir(caminho) as handle:
                return sum(1 for linha in handle if linha.strip())
        if nome.endswith((".json", ".json.gz")):
            with _abrir(caminho) as handle:
                payload = json.load(handle)
            if isinstance(payload, list):
                return len(payload)
            if isinstance(payload, dict):
                for chave in _RECORD_KEYS:
                    valor = payload.get(chave)
                    if isinstance(valor, list):
                        return len(valor)
                return 1  # documento unico (um envelope, por exemplo)
    except Exception:  # noqa: BLE001 - artefato ilegivel nao derruba a auditoria
        return 0
    return 0


def _spec_names_for_renderer(renderer_name: str) -> frozenset[str]:
    """Nomes de TODAS as superficies que um renderer serve.

    Um renderer pode servir mais de uma superficie: ``focus_azure`` entrega o
    FOCUS e o manifesto do MESMO export, e ``gcp_bigquery_topology`` entrega as
    tres tabelas de billing. Comparar o artefato de uma contra a spec da outra
    acusaria as colunas da irma como inventadas -- e foi o que aconteceu.

    A cobertura por superficie continua sendo medida separadamente; o que passa a
    ser a uniao e apenas a barreira de invencao.
    """
    nomes: set[str] = set()
    for coverage in matrix.SURFACES:
        if coverage.renderer != renderer_name:
            continue
        nomes.update(load_spec(DEFAULT_SPECS_ROOT / f"{coverage.surface}.schema.json").names)
    return frozenset(nomes)


def _is_structural_container(nome: str, especiais: frozenset[str]) -> bool:
    """Verdadeiro quando o nome e so o container de um caminho documentado.

    A spec lista os CAMINHOS FOLHA (``properties.networkProfile.networkInterfaces``);
    o documento entregue precisa do container ``properties`` para que esses
    caminhos existam. Marcar o container como campo inventado seria falso
    positivo. O limite e obrigatorio para nao confundir ``line_item`` com
    ``line_item_usage_amount``.
    """
    return any(
        especial.startswith(nome + ".") or especial.startswith(nome + "[") for especial in especiais
    )


def _audit_surface(surface: str, renderer_name: str, estate: CanonicalEstate, work_dir: Path) -> SurfaceAudit:
    destino = work_dir / renderer_name
    destino.mkdir(parents=True, exist_ok=True)
    try:
        renderer = get_renderer(renderer_name)
        renderer.render(estate, destino)
    except Exception as exc:  # noqa: BLE001 - auditar e o objetivo
        return SurfaceAudit(surface, renderer_name, 0, 0, (), (), error=f"{type(exc).__name__}: {exc}")

    arquivos = _export_artifacts(destino)
    spec = load_spec(DEFAULT_SPECS_ROOT / f"{surface}.schema.json")

    emitidas: list[str] = []
    preenchidas: list[str] = []
    caminhos: list[str] = []
    registros = 0
    for arquivo in arquivos:
        try:
            for nome in columns_of(arquivo):
                if nome not in emitidas:
                    emitidas.append(nome)
        except ArtifactError:
            continue
        registros += _records_of(arquivo)
        try:
            for nome in populated_of(arquivo):
                if nome not in preenchidas:
                    preenchidas.append(nome)
        except ArtifactError:
            continue
        try:
            for nome in populated_paths(arquivo, spec.names):
                if nome not in caminhos:
                    caminhos.append(nome)
        except ArtifactError:
            continue

    # Um renderer pode servir varias superficies (o FOCUS e o manifesto saem do
    # mesmo export). A barreira de invencao e a uniao das specs que ele serve,
    # mais os containers estruturais que a propria spec exige.
    servidas = _spec_names_for_renderer(renderer_name)
    inventadas = tuple(
        sorted(
            nome
            for nome in set(emitidas) - set(spec.names)
            if nome not in servidas and not _is_structural_container(nome, servidas)
        )
    )
    por_conjunto = tuple(
        (
            conjunto.name or "<unico>",
            len({coluna.name for coluna in conjunto.columns} & set(emitidas)),
            len(conjunto.columns),
        )
        for conjunto in spec.sets
    )
    return SurfaceAudit(
        surface,
        renderer_name,
        len(arquivos),
        registros,
        inventadas,
        por_conjunto,
        len(set(preenchidas) & set(spec.names)),
        len(caminhos),
        tuple(nome for nome in (c.name for c in spec.columns if c.required) if nome not in set(caminhos)),
    )


def readiness(resultados: Iterable[SurfaceAudit]) -> tuple[str, ...]:
    """O veredito: o que impede o simulador de estar funcional.

    Quatro condicoes OBJETIVAS, e nenhuma delas e "quanto preencheu" -- taxa de
    preenchimento e medida honesta, mas nao serve de criterio, porque depende do
    que o modelo tem fonte para afirmar e isso muda por superficie:

    1. a superficie renderiza sem erro;
    2. entrega ao menos um registro (formato sem dado nao e dado);
    3. entrega ao menos um artefato que carregue ALGUM nome proprio -- sem isto,
       uma superficie que divide renderer com outra passa no criterio 2 lendo o
       artefato da IRMA e o veredito abencoa quem nao entrega nada seu;
    4. nao entrega coluna que spec nenhuma autoriza;
    5. existe teste que CONFRONTA o artefato com a spec (``report.golden_gaps``).

    Devolve a lista de impedimentos; vazia significa pronto.
    """
    impedimentos: list[str] = []
    for item in resultados:
        if item.error:
            impedimentos.append(f"{item.surface}: render falhou ({item.error[:60]})")
            continue
        if not item.records:
            impedimentos.append(f"{item.surface}: nenhum registro no artefato")
        if item.per_set and all(presentes == 0 for _, presentes, _ in item.per_set):
            impedimentos.append(
                f"{item.surface}: nenhum artefato carrega campo proprio "
                f"(o renderer entrega so o artefato de outra superficie)"
            )
        if item.invented:
            impedimentos.append(
                f"{item.surface}: coluna fora de qualquer spec ({', '.join(item.invented[:3])})"
            )
    return tuple(impedimentos)


def audit(
    *,
    seed: int = 123,
    profile: str = "small",
    currency: str = "USD",
    work_dir: Path,
    only: Iterable[str] | None = None,
) -> tuple[SurfaceAudit, ...]:
    """Renderiza cada superficie declarada como gerada e mede o artefato."""
    filtro = tuple(only) if only else None
    estate = build_estate(seed=seed, profile=profile, currency=currency)

    resultados: list[SurfaceAudit] = []
    for coverage in matrix.by_status(matrix.STATUS_IMPLEMENTED):
        if filtro and not coverage.surface.startswith(filtro):
            continue
        if coverage.renderer is None:
            continue
        resultados.append(_audit_surface(coverage.surface, coverage.renderer, estate, work_dir))
    return tuple(resultados)


def render_report(resultados: Iterable[SurfaceAudit]) -> Iterator[str]:
    """Linhas do relatorio, prontas para imprimir.

    ``caminhos`` e o numero que separa "fiel ao formato" de "gera o dado": uma
    superficie pode emitir as 181 colunas documentadas e preencher uma. Ele conta
    os CAMINHOS que a spec enumera com valor no artefato -- ``preenchidas`` conta
    nomes de TOPO e subconta superficie aninhada (no billing do GCP, 17 contra 58).
    """
    yield (
        f"{'superficie':<52} {'arqs':>5} {'registros':>10} {'caminhos':>9} "
        f"{'topo':>6} {'invent':>7} {'obrig.vazias':>13}"
    )
    yield "-" * 116
    for item in resultados:
        if item.error:
            yield f"{item.surface:<52} {'-':>5} {'-':>10} {'-':>9} {'-':>6} {'-':>7}  FALHOU: {item.error[:24]}"
            continue
        marca = "" if item.records else "  <-- SEM REGISTRO"
        vazio = "  <-- SEM VALOR" if not item.documented else ""
        obrig = f"{len(item.required_empty)}" if item.required_empty else "-"
        yield (
            f"{item.surface:<52} {item.artifacts:>5} {item.records:>10} "
            f"{item.documented:>9} {item.populated:>6} {len(item.invented):>7} {obrig:>13}"
            f"{marca}{vazio}"
        )
        for nome, presentes, total in item.per_set:
            if presentes != total:
                yield f"      conjunto {nome!r}: {presentes}/{total} campos presentes"
        if item.invented:
            yield f"      inventadas: {', '.join(item.invented[:8])}"
        if len(item.required_empty) > 6:
            yield f"      obrigatorias vazias: {', '.join(item.required_empty[:6])}, ..."
        if item.required_empty and len(item.per_set) > 1:
            # Ressalva necessaria: uma spec com varios conjuntos pode descrever as
            # POSICOES de um campo como caminhos proprios (o NSG publica as 13
            # posicoes do flowTuples) enquanto o artefato entrega o campo como UMA
            # string separada por virgula. Comparar as duas representacoes acusa
            # ausencia onde ha valor -- o numero acima superestima neste caso.
            yield (
                f"      (spec com {len(item.per_set)} conjuntos: parte da contagem pode "
                f"ser posicional, nao ausencia real)"
            )
