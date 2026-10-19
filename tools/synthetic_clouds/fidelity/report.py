"""Relatorios de coerencia do proprio processo de fidelidade.

Duas coisas envelhecem sozinhas neste projeto, e as duas sao invisiveis ate
alguem tropecar nelas:

* a **matriz de cobertura** diz que uma superficie esta bloqueada pela
  documentacao quando ela ja nao esta (basta alguem aplicar `format-observed`);
* uma superficie declarada como **gerada** pode nao ter nenhum teste que a
  confronte com a especificacao -- fidelidade presumida, nao verificada.

As funcoes aqui devolvem a lista de problemas; quem chama decide se imprime (o
CLI) ou se falha (a suite). A suite exige: um projeto que se diz fiel sem provar
nao esta fiel.
"""

from __future__ import annotations

from pathlib import Path

from tools.synthetic_clouds.fidelity import matrix
from tools.synthetic_clouds.fidelity.spec import DEFAULT_SPECS_ROOT, SpecError, load_all_specs

DEFAULT_TESTS_DIR = DEFAULT_SPECS_ROOT.parent / "tools" / "synthetic_clouds" / "tests"


def untyped_required(specs_root: Path | None = None) -> tuple[str, ...]:
    """Colunas obrigatorias cujo TIPO o provedor nao publica, por superficie.

    Esta e a lacuna que faz o auditor acusar `missing` num renderer correto: a
    coluna esta sempre presente no arquivo real (a spec a marca obrigatoria), mas
    num alvo tipado ela nao pode ser escrita sem inventar o tipo. O residual e
    irredutivel enquanto a documentacao nao publicar o tipo -- e o lugar de
    nomea-lo e aqui, nao no contrato do gerador.
    """
    root = specs_root or DEFAULT_SPECS_ROOT
    try:
        specs = load_all_specs(root)
    except SpecError as exc:
        return (f"nao foi possivel conferir: {exc}",)

    linhas: list[str] = []
    for spec in specs:
        sem_tipo = [column.name for column in spec.columns if column.required and not column.belongs_to_schema]
        if sem_tipo:
            linhas.append(
                f"{spec.surface}: {len(sem_tipo)} coluna(s) obrigatoria(s) sem tipo publicado "
                f"({', '.join(sem_tipo[:4])}{', ...' if len(sem_tipo) > 4 else ''})"
            )
    return tuple(linhas)


def unmapped_renderers() -> tuple[str, ...]:
    """Renderers que nenhuma superficie especificada reivindica.

    Um renderer sem spec produz artefato que ninguem confronta com documentacao
    nenhuma -- exatamente o que o projeto existe para nao ter. Pode ser legitimo
    (um plano de API, e nao um formato de export), mas tem de ser uma decisao
    declarada, nao um esquecimento.
    """
    from tools.synthetic_clouds.render.base import broken_modules, registered_names

    mapeados = {coverage.renderer for coverage in matrix.SURFACES if coverage.renderer}
    problemas = [f"{nome}: registrado e sem superficie na matriz" for nome in registered_names() if nome not in mapeados]
    problemas.extend(
        f"{nome}: modulo nao importa ({motivo})" for nome, motivo in sorted(broken_modules().items())
    )
    return tuple(problemas)


def staleness(specs_root: Path | None = None) -> tuple[str, ...]:
    """Superficies cuja declaracao na matriz contradiz as especificacoes de hoje."""
    root = specs_root or DEFAULT_SPECS_ROOT
    try:
        specs = {spec.surface: spec for spec in load_all_specs(root)}
    except SpecError as exc:
        return (f"nao foi possivel conferir a matriz: {exc}",)

    problemas: list[str] = []
    for coverage in matrix.SURFACES:
        spec = specs.get(coverage.surface)
        if spec is None:
            problemas.append(f"{coverage.surface}: declarada na matriz e ausente em specs/")
            continue

        geraveis = spec.generatable_count
        if coverage.status == matrix.STATUS_BLOCKED and geraveis:
            problemas.append(
                f"{coverage.surface}: marcada como bloqueada, mas a spec ja autoriza "
                f"{geraveis} colunas"
            )
        elif coverage.status != matrix.STATUS_BLOCKED and geraveis == 0:
            problemas.append(
                f"{coverage.surface}: marcada como {coverage.status}, mas nenhuma coluna e geravel"
            )

    return tuple(problemas)


def golden_gaps(
    specs_root: Path | None = None,
    tests_dir: Path | None = None,
) -> tuple[str, ...]:
    """Superficies declaradas como geradas sem teste que CONFRONTE o artefato.

    Duas exigencias, e a segunda e a que importa:

    1. existe teste que cita o arquivo da especificacao;
    2. esse mesmo teste chama ``check_artifact``/``check``/``columns_of`` -- ou
       seja, olha para o ARTEFATO entregue.

    Sem a segunda, um teste que apenas carrega a spec e afirma contagens passaria
    como "cobertura golden" sem nunca comparar o arquivo gerado com o contrato.
    Comparar o artefato e o que o projeto promete; citar a spec e o minimo.
    """
    root = specs_root or DEFAULT_SPECS_ROOT
    pasta = tests_dir or DEFAULT_TESTS_DIR
    if not pasta.is_dir():
        return (f"pasta de testes ausente: {pasta}",)

    conteudo = {
        arquivo.name: arquivo.read_text(encoding="utf-8", errors="replace")
        for arquivo in sorted(pasta.glob("*.py"))
    }
    tudo = "\n".join(conteudo.values())
    marcadores = ("check_artifact(", "columns_of(", "populated_of(", "check(")

    problemas: list[str] = []
    for coverage in matrix.by_status(matrix.STATUS_IMPLEMENTED):
        spec = root / f"{coverage.surface}.schema.json"
        if spec.name not in tudo:
            problemas.append(
                f"{coverage.surface}: gerada por {coverage.renderer}, mas nenhum teste cita {spec.name}"
            )
            continue
        confere = any(
            spec.name in texto and any(marcador in texto for marcador in marcadores)
            for texto in conteudo.values()
        )
        if not confere:
            problemas.append(
                f"{coverage.surface}: o teste cita {spec.name} mas nunca confronta o artefato "
                f"(esperado um de {marcadores})"
            )
    return tuple(problemas)
