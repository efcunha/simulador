"""Regenerate docs/NAO-COMPROVADOS.md and docs/NAO-COMPROVADOS.en.md from the specs.

Este e o gerador **versionado** do registro: vive em ``specs/_tools/``. Uma variante anterior
ficava em ``.artifacts/`` (fora do git) e produzia o documento inteiro a partir do zero; o que
ela tinha de insubstituivel -- o preambulo longo, escrito a mao, que nao pode ser derivado das
specs -- esta no proprio documento versionado, e por isso este script e **nao destrutivo por
construcao**:

* o preambulo de cada documento e preservado **byte a byte**, com UMA excecao textual: a
  citacao do proprio gerador, que ainda aponta para ``.artifacts/`` e passa a apontar para
  ``specs/_tools/`` (ver :data:`RE_GERADOR_ANTIGO`). Nada mais do texto escrito a mao e
  reescrito;
* as secoes ja existentes tem o CORPO reconciliado com a spec: um item declarado que a secao
  nao listava e acrescentado (ver :func:`_reconcilar`);
* os tres numeros do bloco "Numeros" sao recalculados a partir das specs, porque numero escrito
  a mao envelhece em silencio assim que uma lacuna e fechada por evidencia -- nenhum total e
  fixado no codigo;
* rodar duas vezes nao muda nada (idempotente).

Os DOIS documentos vem das MESMAS specs e tem os MESMOS itens; o que muda e a moldura -- o
preambulo, o bloco de numeros, o cabecalho da tabela e o rotulo do tipo ("campo"/"tema" em pt,
"field"/"topic" em en).

Uso: ``python specs/_tools/gerar-registro-nao-comprovados.py`` (a partir da raiz do repositorio)
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from tools.synthetic_clouds.fidelity.spec import (  # noqa: E402
    UNVERIFIED_FIELD,
    SurfaceSpec,
    load_spec,
)

SPECS = REPO / "specs"
DOC = REPO / "docs" / "NAO-COMPROVADOS.md"
DOC_EN = REPO / "docs" / "NAO-COMPROVADOS.en.md"

#: Citacao do gerador no preambulo, escrita quando ele ainda vivia em ``.artifacts/`` (fora do
#: git). O preambulo e preservado byte a byte, com esta unica excecao textual: o caminho citado
#: passa a ser o do arquivo versionado. E uma troca de texto, nao de conteudo -- nada mais do
#: preambulo e tocado.
RE_GERADOR_ANTIGO = re.compile(r"\.artifacts/gerar-registro-nao-comprovados\.py")
GERADOR_VERSIONADO = "specs/_tools/gerar-registro-nao-comprovados.py"

#: As tres linhas do bloco "Numeros" que este script recalcula.
#: ``RE_TOTAL`` casa a LINHA INTEIRA (``.*$``), e nao so o prefixo: casando so o prefixo, o
#: ``sub`` reescreve a cabeca e DEIXA o sufixo que ja estava la -- de modo que cada execucao
#: acrescentava mais uma copia de "(ou seja: nenhuma superficie esta sem lacuna declarada)", e
#: a linha acumulava uma por vez. O sintoma e uma frase repetida que ninguem escrevera assim.
RE_TOTAL = re.compile(r"^\* \*\*\d+ itens não comprovados\*\* em \*\*\d+ de \d+ superfícies\*\*.*$", re.M)
RE_JUNTOS = re.compile(r"juntos dão \d+ itens em \*\*\d+\*\* superfícies", re.M)
RE_PROVEDOR = re.compile(r"^\* Por provedor: .*$", re.M)

#: A cabecalho de uma secao -- a superficie e a contagem que a secao declara. Casa ate o FIM
#: da linha (``[^\n]*$``) e nao so o prefixo ``... item``: casando so o prefixo, o ``sub``
#: reescreve a cabeca e DEIXA o ``(ns)`` que ja estava la, produzindo "4 item(ns)(ns)".
RE_SECAO = re.compile(r"^## `(?P<surface>[^`]+)` — (?P<n>\d+) item[^\n]*$", re.M)
#: Uma linha de item dentro de uma secao: o TIPO (campo/tema) e o NOME. O motivo contem
#: crases e pipes, entao o nome e lido ate a primeira crase em vez de ate o proximo pipe.
RE_ITEM = re.compile(r"^\| (campo|tema) \| `(?P<item>.*?)` \|", re.M)

#: The English twin: the SAME specs, the SAME items, an English framing.
#:
#: The section header (``## `surface` -- N item(ns)``) is already
#: language-neutral, so RE_SECAO serves both documents. What differs is the
#: kind labels, the table header and the three count lines -- and the
#: preamble, which is hand-written and preserved byte-for-byte, exactly as in
#: the PT document. That is why the twin's preamble lives in the file itself:
#: a new clone already carries it.
RE_ITEM_EN = re.compile(r"^\| (field|topic) \| `(?P<item>.*?)` \|", re.M)
RE_TOTAL_EN = re.compile(r"^\* \*\*\d+ unproven items\*\* in \*\*\d+ of \d+ surfaces\*\*.*$", re.M)
RE_JUNTOS_EN = re.compile(r"together they give \d+ items in \*\*\d+\*\* surfaces", re.M)
RE_PROVEDOR_EN = re.compile(r"^\* By provider: .*$", re.M)

#: Per-language rendering. ``kind`` maps the two kinds of declared gap to the
#: label each document uses: a name that does not belong to the contract
#: ("campo"/"field") and a topic that exists but whose proof is missing
#: ("tema"/"topic").
LINGUAGENS: dict[str, dict[str, object]] = {
    "pt": {
        "path": DOC,
        "kind": {"campo": "campo", "tema": "tema"},
        "re_item": RE_ITEM,
        "re_total": RE_TOTAL,
        "re_juntos": RE_JUNTOS,
        "re_provedor": RE_PROVEDOR,
        "tabela": "\n| tipo | item | motivo declarado |\n|---|---|---|",
        "total": (
            lambda t, s: f"* **{t} itens não comprovados** em **{s} de {s} superfícies** "
            "(ou seja: **nenhuma** superfície está sem lacuna declarada)."
        ),
        "juntos": lambda t, s: f"juntos dão {t} itens em **{s}** superfícies",
        "provedor": lambda pp: "* Por provedor: "
        + ", ".join(f"**{n}** {c}" for n, c in sorted(pp.items()))
        + ".",
    },
    "en": {
        "path": DOC_EN,
        "kind": {"campo": "field", "tema": "topic"},
        "re_item": RE_ITEM_EN,
        "re_total": RE_TOTAL_EN,
        "re_juntos": RE_JUNTOS_EN,
        "re_provedor": RE_PROVEDOR_EN,
        "tabela": "\n| kind | item | declared reason |\n|---|---|---|",
        "total": (
            lambda t, s: f"* **{t} unproven items** in **{s} of {s} surfaces** "
            "(that is: **no** surface is without a declared gap)."
        ),
        "juntos": lambda t, s: f"together they give {t} items in **{s}** surfaces",
        "provedor": lambda pp: "* By provider: "
        + ", ".join(f"**{n}** {c}" for n, c in sorted(pp.items()))
        + ".",
    },
}


def _itens(spec, lang: str = "pt") -> list[tuple[str, str]]:
    """The declared items of one surface as ``(name, row)``, in spec order.

    ``row`` is the markdown line the document spells, built by the same expression
    :func:`_sections_from_specs` uses, so an appended row is indistinguishable from a row
    rendered from scratch. ``lang`` picks the kind label each document uses
    ("campo"/"field", "tema"/"topic").
    """
    kinds = LINGUAGENS[lang]["kind"]
    linhas = []
    for row in spec.unverified_fields:
        kind = kinds["campo"] if row.kind == UNVERIFIED_FIELD else kinds["tema"]
        linhas.append((row.name, f"| {kind} | `{row.name}` | {row.reason or ''} |"))
    return linhas


def _reconcilar(texto: str, specs: dict[str, object], lang: str = "pt") -> tuple[str, list[str]]:
    """Add DECLARED items missing from an existing section. Never remove a row.

    This generator used to append a section only when the surface had NO section at all, so a
    spec that gained an ``unverified`` item AFTER its section was written kept an incomplete
    body -- while the totals, which are computed from the specs, already counted the new item.
    That is the shape of the bug this closes: a section declaring fewer items than its spec.

    Measured before the fix: exactly ONE section in the document was missing a declared item
    (``aws/s3-get-public-access-block``, which listed 3 of the 4 its spec declares).

    Appending-only is deliberate. Eleven sections legitimately carry MORE rows than the spec
    renders -- the same item recorded once as ``campo`` and once as ``tema`` -- and dropping
    those would delete content this script does not own. This function therefore never
    shortens a section, and the header is recomputed as the number of item rows the section
    shows, so it keeps describing what is on screen.

    Idempotent: a second run finds every declared item already present and changes nothing.
    """
    re_item = LINGUAGENS[lang]["re_item"]
    inicios = list(RE_SECAO.finditer(texto))
    mudancas: list[str] = []
    # De tras para frente: assim os offsets das secoes ainda nao visitadas continuam valendo.
    for indice in range(len(inicios) - 1, -1, -1):
        marca = inicios[indice]
        superficie = marca.group("surface")
        spec = specs.get(superficie)
        if spec is None:
            continue
        fim = inicios[indice + 1].start() if indice + 1 < len(inicios) else len(texto)
        secao = texto[marca.start():fim]
        corpo = secao.rstrip("\n")
        cauda = secao[len(corpo):]  # exatamente a corrida de \n que ja estava depois do corpo
        ja_no_doc = {nome for _tipo, nome in re_item.findall(corpo)}
        faltando = [linha for nome, linha in _itens(spec, lang) if nome not in ja_no_doc]
        novo_corpo = corpo + "\n" + "\n".join(faltando) if faltando else corpo
        # O cabecalho e normalizado para a forma canonica e para a contagem de linhas que a
        # secao REALMENTE mostra. Medido: nas 44 secoes a contagem ja bate com as linhas, entao
        # normalizar so reescreve cabecalho cujo TEXTO estava fora da forma -- e nada mais.
        linhas = len(re_item.findall(novo_corpo))
        novo_corpo = RE_SECAO.sub(
            lambda _m: f"## `{superficie}` — {linhas} item(ns)", novo_corpo, count=1
        )
        if novo_corpo == corpo:
            continue
        texto = texto[:marca.start()] + novo_corpo + cauda + texto[fim:]
        mudancas.append(
            f"{superficie} (+{len(faltando)} item(ns))"
            if faltando
            else f"{superficie} (cabecalho normalizado)"
        )
    mudancas.reverse()
    return texto, mudancas


def _specs_com_lacunas() -> dict[str, SurfaceSpec]:
    """Every spec that declares at least one unproven name, keyed by surface.

    Loaded ONCE and shared: :func:`_sections_from_specs` and :func:`_reconcilar` must agree
    on what each surface declares, and reading the specs twice invites them to disagree.
    """
    specs: dict[str, SurfaceSpec] = {}
    for path in sorted(SPECS.glob("*/*.schema.json")):
        spec = load_spec(path)
        if not list(spec.unverified_fields):
            continue
        specs[spec.surface] = spec
    return specs


def _sections_from_specs(specs: dict[str, SurfaceSpec], lang: str = "pt") -> dict[str, str]:
    """Render one markdown section per surface that declares unproven names."""
    cfg = LINGUAGENS[lang]
    secoes: dict[str, str] = {}
    for path in sorted(SPECS.glob("*/*.schema.json")):
        spec = load_spec(path)
        if spec.surface not in specs:
            continue
        linhas = [
            f"\n## `{spec.surface}` — {len(list(spec.unverified_fields))} item(ns)\n",
            f"\nSpec: [`{(path.relative_to(REPO).as_posix())}`]"
            f"](../{path.relative_to(REPO).as_posix()})\n",
            cfg["tabela"],
        ]
        for _nome, linha in _itens(spec, lang):
            linhas.append(linha)
        secoes[spec.surface] = "\n".join(linhas)
    return secoes


def _counts(specs: dict[str, SurfaceSpec]) -> tuple[int, int, Counter[str]]:
    """Compute the totals from the specs -- never from the existing document.

    Takes the SAME spec map the sections are rendered from, so the header totals and the
    bodies cannot be computed from two different views of the specs.
    """
    por_provedor: Counter[str] = Counter()
    total = 0
    for spec in specs.values():
        n = len(list(spec.unverified_fields))
        total += n
        por_provedor[spec.provider] += n
    return total, len(specs), por_provedor


def _manter(
    lang: str,
    specs_por_superficie: dict[str, SurfaceSpec],
    total: int,
    superficies: int,
    por_provedor: Counter[str],
) -> tuple[bool, str]:
    """Mantem UM documento: o original pt-BR ou o gemeo em ingles.

    Devolve ``(mudou, relatorio)``. O caminho pt-BR e byte a byte o que este
    script fazia antes de existir o gemeo -- a unica diferenca e de onde vem
    o rotulo (kind, cabecalho da tabela e as tres linhas de numeros).
    """
    cfg = LINGUAGENS[lang]
    doc = cfg["path"]
    if not doc.exists():
        return False, f"aviso: {doc} nao existe; nada a preservar."
    # Le a terminacao de linha do arquivo antes de normaliza-la na leitura: o
    # ``Path.write_text`` sem ``newline`` explicito grava ``os.linesep`` no Windows, o que
    # reescreveria TODO o documento quando a unica mudanca fosse uma linha de cabecalho.
    # Os documentos versionados usam LF.
    terminacao = "\r\n" if b"\r\n" in doc.read_bytes() else "\n"
    texto = doc.read_text(encoding="utf-8")
    original = texto

    texto = RE_GERADOR_ANTIGO.sub(GERADOR_VERSIONADO, texto)
    texto = cfg["re_total"].sub(cfg["total"](total, superficies), texto)
    texto = cfg["re_juntos"].sub(cfg["juntos"](total, superficies), texto)
    texto = cfg["re_provedor"].sub(cfg["provedor"](por_provedor), texto)

    # Reconcilia o CORPO das secoes existentes com as specs, e so depois acrescenta as
    # superficies que ainda nao tem secao. Reconciliar antes mantem as secoes novas no fim,
    # como sempre -- e a reconciliacao so depende de cabecalhos, que o acrescimo nao move.
    texto, reconciliadas = _reconcilar(texto, specs_por_superficie, lang)
    secoes = _sections_from_specs(specs_por_superficie, lang)
    faltando = [s for s in secoes if f"## `{s}`" not in texto]
    if faltando:
        novas = "\n".join(secoes[superficie] for superficie in faltando)
        texto = texto.rstrip() + "\n" + novas + "\n"

    if texto == original:
        return False, f"ok: sem mudanca ({total} itens em {superficies} superficies)"
    with doc.open("w", encoding="utf-8", newline=terminacao) as saida:
        saida.write(texto)
    return True, (
        f"ok: {total} itens em {superficies} superficies; "
        f"{len(reconciliadas)} secao(oes) reconciliada(s) "
        f"({', '.join(reconciliadas) or 'nenhuma'}); "
        f"{len(faltando)} secao(oes) acrescentada(s) -> {doc.relative_to(REPO)}"
    )


def main() -> int:
    # Lida UMA vez: numeros, reconciliacao e acrescimo precisam ver a mesma coisa.
    specs_por_superficie = _specs_com_lacunas()
    total, superficies, por_provedor = _counts(specs_por_superficie)

    rc = 0
    for lang in ("pt", "en"):
        doc = LINGUAGENS[lang]["path"]
        if not doc.exists():
            rc = 1
        mudou, relatorio = _manter(lang, specs_por_superficie, total, superficies, por_provedor)
        print(relatorio, flush=True)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
