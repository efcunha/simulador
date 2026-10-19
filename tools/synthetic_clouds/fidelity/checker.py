"""Comparacao entre a especificacao documentada e o que foi realmente emitido.

Os quatro modos de falha que interessam, em ordem de gravidade:

* ``invented``           -- o gerador emitiu um campo que a documentacao nao define.
* ``unverified_emitted`` -- o gerador emitiu um campo que a propria spec marca como
                            nao comprovado. E o mesmo pecado, com agravante.
* ``missing``            -- a documentacao exige o campo e o gerador nao emitiu.
* ``order``              -- a ordem das colunas difere de um layout posicional
                            (CSV), onde a ordem faz parte do formato.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from tools.synthetic_clouds.fidelity.artifacts import columns_of, populated_of
from tools.synthetic_clouds.fidelity.spec import Column, SurfaceSpec

KIND_INVENTED = "invented"
KIND_UNVERIFIED = "unverified_emitted"
KIND_MISSING = "missing"
KIND_ORDER = "order"
KIND_POPULATED_EMPTY = "populated_declared_empty"

_SEVERITY = (
    KIND_INVENTED,
    KIND_UNVERIFIED,
    KIND_POPULATED_EMPTY,
    KIND_MISSING,
    KIND_ORDER,
)


class ScopeError(ValueError):
    """Escopo ausente ou desconhecido numa superficie com varios conjuntos."""


@dataclass(frozen=True, slots=True)
class Finding:
    """Uma divergencia entre a documentacao e o artefato."""

    kind: str
    column: str
    detail: str

    def __str__(self) -> str:
        return f"[{self.kind}] {self.column}: {self.detail}"


def _resolve_columns(spec: SurfaceSpec, scope: str | None) -> tuple[Column, ...]:
    """Decide contra qual conjunto comparar, recusando a comparacao ambigua.

    Comparar contra a UNIAO de conjuntos disjuntos nao e uma aproximacao
    conservadora: num artefato gerado para um contrato, tudo o que os outros
    contratos declaram aparece como 'ausente'. Por isso, com mais de um
    conjunto nomeado, o escopo e obrigatorio.
    """
    if scope is None:
        named = spec.set_names
        if len(named) > 1:
            raise ScopeError(
                f"{spec.surface}: a superficie tem {len(named)} conjuntos "
                f"({', '.join(named)}); informe scope= para comparar contra o conjunto certo"
            )
        return spec.columns
    try:
        return spec.columns_for(scope)
    except KeyError:
        raise ScopeError(f"{spec.surface}: conjunto desconhecido: {scope!r}") from None


def check(
    spec: SurfaceSpec,
    observed: Sequence[str],
    *,
    scope: str | None = None,
    ordered: bool = False,
) -> tuple[Finding, ...]:
    """Compara ``observed`` contra a especificacao e devolve as divergencias.

    ``scope`` seleciona o conjunto quando a superficie tem varios contratos.
    Sem ele, uma superficie com mais de um conjunto nomeado e recusada em vez de
    comparada contra a uniao -- essa uniao acusaria ausencia de tudo o que os
    outros contratos declaram.
    """
    columns = _resolve_columns(spec, scope)
    seen = list(dict.fromkeys(observed))
    known = {column.name for column in columns}
    explicitly_unverified = set(spec.unverified)
    # Um nome so entra em "sem contrato" se NENHUMA ocorrencia no conjunto o
    # autorizar: o artefato e conferido por nome, entao um nome geravel torna a
    # emissao legitima.
    emittable = {column.name for column in columns if column.belongs_to_schema}
    # Uma coluna documentada como SEMPRE VAZIA pertence ao formato: emiti-la e
    # correto (o valor e que nao pode ser preenchido). Por isso a barreira aqui e
    # "pertence ao schema", nao "pode receber valor".
    without_contract = {
        column.name: column
        for column in columns
        if not column.belongs_to_schema and column.name not in emittable
    }

    findings: list[Finding] = []

    # Todo campo emitido passa por exatamente um destes ramos. A ordem importa:
    # um nome sem contrato nao pode escapar por tambem constar de 'columns'.
    for name in seen:
        if name in explicitly_unverified:
            findings.append(
                Finding(
                    KIND_UNVERIFIED,
                    name,
                    "emitido sem comprovacao em documentacao oficial (consta em 'unverified')",
                )
            )
        elif name in without_contract:
            column = without_contract[name]
            reason = column.evidence or ("sem tipo documentado" if not column.type else "sem evidencia")
            findings.append(
                Finding(
                    KIND_UNVERIFIED,
                    name,
                    f"descrito mas sem contrato suficiente para gerar ({reason})",
                )
            )
        elif name not in known:
            findings.append(
                Finding(KIND_INVENTED, name, "nao consta da especificacao; campo inventado")
            )

    for column in columns:
        # `missing` continua valendo para TODA coluna obrigatoria, inclusive a que
        # nao pode ser emitida por falta de tipo publicado. Nao e acusacao ao
        # renderer: e o residual aparecendo. Silenciar aqui esconderia uma lacuna
        # da PROPRIA spec (a coluna esta sempre presente no arquivo real, so nao
        # pode ser tipada), e essa lacuna tem de ficar visivel. Quem a nomeia e o
        # relatorio `--matrix`, em `untyped_required`.
        if column.required and column.name not in seen:
            findings.append(Finding(KIND_MISSING, column.name, "coluna obrigatoria ausente no artefato"))

    if ordered:
        expected = [name for name in (column.name for column in columns) if name in set(seen)]
        actual = [name for name in seen if name in known]
        if expected != actual:
            first = next(
                (i for i, (a, b) in enumerate(zip(expected, actual, strict=False)) if a != b),
                min(len(expected), len(actual)),
            )
            findings.append(
                Finding(
                    KIND_ORDER,
                    actual[first] if first < len(actual) else "<fim>",
                    f"ordem posicional divergente na posicao {first}: "
                    f"esperado {expected[first] if first < len(expected) else '<fim>'!r}",
                )
            )

    return tuple(findings)


def check_values(
    spec: SurfaceSpec,
    populated: Sequence[str],
    *,
    scope: str | None = None,
) -> tuple[Finding, ...]:
    """Acusa coluna que a documentacao marca como sempre vazia e saiu preenchida.

    Conferir so o nome da coluna deixa passar o defeito simetrico: o renderer
    declara a coluna correta e escreve um valor inventado nela. As duas coisas
    precisam ser verificadas.
    """
    columns = _resolve_columns(spec, scope)
    must_stay_empty = {
        column.name: column for column in columns if column.belongs_to_schema and not column.is_generatable
    }

    return tuple(
        Finding(
            KIND_POPULATED_EMPTY,
            name,
            f"a documentacao declara esta coluna sempre vazia "
            f"(evidence={must_stay_empty[name].evidence!r}), mas ela saiu preenchida",
        )
        for name in dict.fromkeys(populated)
        if name in must_stay_empty
    )


def check_artifact(
    spec: SurfaceSpec,
    path: Path | str,
    *,
    scope: str | None = None,
    ordered: bool = False,
    delimiter: str = ",",
) -> tuple[Finding, ...]:
    """Confere nomes E valores de um artefato real contra a especificacao.

    Atalho para os testes golden: le o arquivo entregue (Parquet, CSV, JSON),
    compara o conjunto de campos e verifica que as colunas declaradas como
    sempre vazias continuam vazias.
    """
    names = columns_of(path, delimiter=delimiter)
    findings = list(check(spec, names, scope=scope, ordered=ordered))
    findings.extend(check_values(spec, populated_of(path, delimiter=delimiter), scope=scope))
    return tuple(findings)


def is_faithful(findings: Sequence[Finding]) -> bool:
    """Verdadeiro somente quando nao ha nenhuma divergencia."""
    return not findings


def summarize(spec: SurfaceSpec, observed: Sequence[str]) -> str:
    """Resumo legivel, para o log de auditoria."""
    return (
        f"{spec.provider}/{spec.surface}: "
        f"especificado={len(spec.names)} emitido={len(set(observed))} "
        f"obrigatorias={len(spec.required_names)}"
    )
