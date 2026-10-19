"""Regenerate docs/NAO-COMPROVADOS.md from the specs' own ``unverified`` lists.

AVISO IMPORTANTE
================
Este arquivo SUBSTITUIU o gerador canonico do repo com o mesmo nome. O original nao esta
versionado (``.artifacts/`` esta no ``.gitignore``) e nao pode ser recuperado pelo git --
ver a secao de HANDOFF do Incremento 3. A versao original produzia o documento inteiro a
partir do zero, incluindo um preambulo longo que nao pode ser derivado das specs.

Por isso esta versao e **nao destrutiva por construcao**:

* o preambulo existente e lido do arquivo e preservado **byte a byte** -- nada aqui reescreve
  texto que nao vem das specs;
* as secoes ja existentes tem o CORPO reconciliado com a spec: um item declarado que a secao
  nao listava e acrescentado (ver :func:`_reconcilar`);
* os tres numeros do bloco "Numeros" sao recalculados a partir das specs, porque numero escrito
  a mao envelhece em silencio assim que uma lacuna e fechada por evidencia;
* rodar duas vezes nao muda nada (idempotente).

O que este script **nao** faz: reescrever o preambulo do documento. Um clone novo ja nasce
com o ``docs/NAO-COMPROVADOS.md`` versionado, entao nao ha preambulo a preservar -- o
preambulo do clone e o do commit. Se um dia o documento precisar ser reconstruido do zero,
este script nao serve para isso: o gerador original se foi com a branch.

Uso: ``python specs/_tools/gerar-registro-nao-comprovados.py`` (a partir da raiz do
pacote ``simulador-nuvem``)
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


def _itens(spec) -> list[tuple[str, str]]:
    """The declared items of one surface as ``(name, row)``, in spec order.

    ``row`` is the markdown line the document spells, built by the same expression
    :func:`_sections_from_specs` uses, so an appended row is indistinguishable from a row
    rendered from scratch.
    """
    linhas = []
    for row in spec.unverified_fields:
        kind = "campo" if row.kind == UNVERIFIED_FIELD else "tema"
        linhas.append((row.name, f"| {kind} | `{row.name}` | {row.reason or ''} |"))
    return linhas


def _reconcilar(texto: str, specs: dict[str, object]) -> tuple[str, list[str]]:
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
        ja_no_doc = {nome for _tipo, nome in RE_ITEM.findall(corpo)}
        faltando = [linha for nome, linha in _itens(spec) if nome not in ja_no_doc]
        novo_corpo = corpo + "\n" + "\n".join(faltando) if faltando else corpo
        # O cabecalho e normalizado para a forma canonica e para a contagem de linhas que a
        # secao REALMENTE mostra. Medido: nas 44 secoes a contagem ja bate com as linhas, entao
        # normalizar so reescreve cabecalho cujo TEXTO estava fora da forma -- e nada mais.
        linhas = len(RE_ITEM.findall(novo_corpo))
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


def _sections_from_specs(specs: dict[str, SurfaceSpec]) -> dict[str, str]:
    """Render one markdown section per surface that declares unproven names."""
    secoes: dict[str, str] = {}
    for path in sorted(SPECS.glob("*/*.schema.json")):
        spec = load_spec(path)
        if spec.surface not in specs:
            continue
        linhas = [
            f"\n## `{spec.surface}` — {len(list(spec.unverified_fields))} item(ns)\n",
            f"\nSpec: [`{(path.relative_to(REPO).as_posix())}`]"
            f"](../{path.relative_to(REPO).as_posix()})\n",
            "\n| tipo | item | motivo declarado |\n|---|---|---|",
        ]
        for _nome, linha in _itens(spec):
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


def main() -> int:
    if not DOC.exists():
        print(f"aviso: {DOC} nao existe; nada a preservar.", flush=True)
        return 1
    texto = DOC.read_text(encoding="utf-8")
    original = texto

    # Lida UMA vez: numeros, reconciliacao e acrescimo precisam ver a mesma coisa.
    specs_por_superficie = _specs_com_lacunas()
    total, superficies, por_provedor = _counts(specs_por_superficie)

    texto = RE_TOTAL.sub(
        f"* **{total} itens não comprovados** em **{superficies} de {superficies} superfícies** "
        "(ou seja: **nenhuma** superfície está sem lacuna declarada).",
        texto,
    )
    texto = RE_JUNTOS.sub(f"juntos dão {total} itens em **{superficies}** superfícies", texto)
    texto = RE_PROVEDOR.sub(
        "* Por provedor: "
        + ", ".join(f"**{name}** {count}" for name, count in sorted(por_provedor.items()))
        + ".",
        texto,
    )

    # Reconcilia o CORPO das secoes existentes com as specs, e so depois acrescenta as
    # superficies que ainda nao tem secao. Reconciliar antes mantem as secoes novas no fim,
    # como sempre -- e a reconciliacao so depende de cabecalhos, que o acrescimo nao move.
    texto, reconciliadas = _reconcilar(texto, specs_por_superficie)
    secoes = _sections_from_specs(specs_por_superficie)
    faltando = [s for s in secoes if f"## `{s}`" not in texto]
    if faltando:
        novas = "\n".join(secoes[superficie] for superficie in faltando)
        texto = texto.rstrip() + "\n" + novas + "\n"

    if texto == original:
        print(f"ok: sem mudanca ({total} itens em {superficies} superficies)")
        return 0
    DOC.write_text(texto, encoding="utf-8")
    print(
        f"ok: {total} itens em {superficies} superficies; "
        f"{len(reconciliadas)} secao(oes) reconciliada(s) "
        f"({', '.join(reconciliadas) or 'nenhuma'}); "
        f"{len(faltando)} secao(oes) acrescentada(s) -> {DOC.relative_to(REPO)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
