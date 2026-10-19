"""CLI de auditoria das especificacoes de export.

Le todas as ``specs/<provider>/*.schema.json``, valida a estrutura e a
evidencia, e imprime um relatorio por superficie. Falha (exit 1) se qualquer
especificacao estiver malformada ou sem comprovacao -- uma spec invalida nao
pode virar codigo.

Uso:
    python -m tools.synthetic_clouds.fidelity            # audita as specs
    python -m tools.synthetic_clouds.fidelity --matrix   # o que falta gerar
    python -m tools.synthetic_clouds.fidelity --golden   # o que falta provar
    python -m tools.synthetic_clouds.fidelity --audit    # renderiza e mede tudo
    python -m tools.synthetic_clouds.fidelity --ready    # aceitacao: specs + golden + entrega
    python -m tools.synthetic_clouds.fidelity --state IAM # retrospectivo das regras de IAM
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from tools.synthetic_clouds.fidelity import matrix, report
from tools.synthetic_clouds.fidelity.audit_renderers import audit, render_report
from tools.synthetic_clouds.fidelity.revision import detect_revision
from tools.synthetic_clouds.fidelity.spec import (
    DEFAULT_SPECS_ROOT,
    SpecError,
    load_all_specs,
    load_spec,
    validate_spec,
)


def _print_revision() -> None:
    """Imprime a revisao medida, junto do resultado (D8).

    A revisao vai na SAIDA, e nao num documento: os numeros por superficie mudam a cada
    commit, e um relatorio sem a revisao que o produziu nao e comparavel com o proximo.
    Ver ``fidelity/revision.py`` para o motivo de cada campo.
    """
    print(f"\n{detect_revision().describe()}")


def _surface_files(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(root.glob("*/*.schema.json"))


def _print_matrix() -> int:
    """Imprime o que ja e gerado, o que falta e o que a documentacao nao sustenta."""
    resumo = matrix.summary()
    rotulos = {
        matrix.STATUS_IMPLEMENTED: "GERADO",
        matrix.STATUS_PENDING: "FALTA",
        matrix.STATUS_BLOCKED: "BLOQUEADO PELA DOC",
    }
    for status in (matrix.STATUS_IMPLEMENTED, matrix.STATUS_PENDING, matrix.STATUS_BLOCKED):
        entradas = matrix.by_status(status)
        print(f"\n=== {rotulos[status]} ({len(entradas)}) ===")
        for coverage in entradas:
            origem = f"  <- {coverage.renderer}" if coverage.renderer else ""
            print(f"  {coverage.surface}{origem}")
            print(f"      {coverage.note}")

    print(
        f"\ngerado={resumo[matrix.STATUS_IMPLEMENTED]}  "
        f"falta={resumo[matrix.STATUS_PENDING]}  "
        f"bloqueado={resumo[matrix.STATUS_BLOCKED]}  "
        f"total={len(matrix.SURFACES)}"
    )
    _report_staleness()
    _report_untyped_required()
    _report_unmapped()
    _print_revision()
    return 0


def _report_staleness() -> None:
    """Mostra onde a matriz contradiz as especificacoes de hoje.

    A logica vive em ``fidelity/report.py`` porque a suite tambem a exige: aqui
    ela e informacao, la e invariante.
    """
    problemas = report.staleness()
    if not problemas:
        print("\nmatriz coerente com as especificacoes.")
        return

    print(f"\nmatriz desatualizada em {len(problemas)} superficie(s):")
    for item in problemas:
        print(f"  ! {item}")


def _report_untyped_required() -> None:
    """Nomeia o residual que faz o auditor acusar `missing` num renderer correto."""
    linhas = report.untyped_required()
    if not linhas:
        print("\nnenhuma coluna obrigatoria sem tipo publicado.")
        return

    print(f"\ncolunas obrigatorias sem tipo publicado (residual da spec, nao do gerador): {len(linhas)}")
    for item in linhas:
        print(f"  - {item}")


def _report_unmapped() -> None:
    """Renderers registrados que nenhuma superficie especificada reivindica."""
    linhas = report.unmapped_renderers()
    if not linhas:
        print("todo renderer registrado tem superficie na matriz.")
        return

    print("\nrenderer sem superficie especificada:")
    for item in linhas:
        print(f"  ! {item}")


def _report_golden_coverage() -> None:
    """Mostra superficie declarada como gerada que nenhum teste confronta.

    A logica vive em ``fidelity/report.py`` porque a suite tambem a exige: aqui
    ela e informacao, la e invariante.
    """
    problemas = report.golden_gaps()
    if not problemas:
        print("\ncobertura golden: toda superficie gerada tem teste que confronta o artefato com a spec.")
        return

    print(f"\ncobertura golden incompleta em {len(problemas)} superficie(s) gerada(s):")
    for item in problemas:
        print(f"  ! {item}")


def _run_state_review(argumento: str) -> int:
    """O diagnostico RETROSPECTIVO de um estado: "o que a tela mostraria hoje?".

    ``--state IAM`` e o unico estado com diagnostico por enquanto, porque as tres regras de
    identidade sao as unicas que passaram de ``INSUFFICIENT_DATA`` por LACUNA DE MODELO -- e
    a lacuna de modelo e a causa que so um retrospectivo consegue fechar, porque nao ha
    veredito nenhum para olhar antes de fechar.
    """
    from tools.synthetic_clouds.fidelity import review

    if argumento.upper() != "IAM":
        print(f"estado sem diagnostico: {argumento!r}. Estados disponiveis: IAM")
        return 1

    from tools.synthetic_clouds.generate.estate_builder import build_estate

    estate = build_estate(seed=123, profile="small", currency="USD")
    diagnosticos = review.diagnose_iam(estate)
    print(review.describe(diagnosticos))

    lacunas = sum(1 for item in diagnosticos if item.current_compliance_type == "INSUFFICIENT_DATA")
    mudancas = sum(1 for item in diagnosticos if item.would_change)
    print(f"\nregras IAM={len(diagnosticos)}  ainda INSUFFICIENT_DATA={lacunas}  mudariam de veredito={mudancas}")
    _print_revision()
    return 1 if lacunas else 0


def _run_audit(argv: list[str]) -> int:
    """Renderiza cada superficie gerada e confronta o artefato com a spec."""
    prefixos = [item for item in argv if not item.startswith("-")]
    with tempfile.TemporaryDirectory(prefix="audit-renderers-") as pasta:
        resultados = audit(work_dir=Path(pasta), only=prefixos or None)
        for linha in render_report(resultados):
            print(linha)

    com_erro = [item for item in resultados if item.error]
    vazias = [item for item in resultados if not item.error and not item.records]
    inventadas = [item for item in resultados if item.invented]
    print(
        f"\nsuperficies={len(resultados)}  com erro={len(com_erro)}  "
        f"sem registro={len(vazias)}  com coluna inventada={len(inventadas)}"
    )
    _print_revision()
    return 1 if com_erro or inventadas else 0


def _spec_problems(root: Path) -> list[str]:
    """Problemas de contrato de TODAS as specs, sem imprimir nada.

    Existe separada de ``main`` para o ``--ready`` poder herdar a mesma checagem:
    um aceitador que confere a entrega mas nao o contrato aceitaria um artefato
    fiel a uma especificacao invalida.
    """
    problemas: list[str] = []
    for path in _surface_files(root):
        try:
            spec = load_spec(path)
        except SpecError as exc:
            problemas.append(str(exc))
            continue
        problemas.extend(validate_spec(spec))
    return problemas


def _run_ready(argv: list[str]) -> int:
    """O veredito unico: contrato das specs, cobertura golden e entrega medida."""
    from tools.synthetic_clouds.fidelity.audit_renderers import readiness

    prefixos = [item for item in argv if not item.startswith("-")]
    problemas = [f"spec: {item}" for item in _spec_problems(DEFAULT_SPECS_ROOT)]
    problemas.extend(f"matriz: {item}" for item in report.staleness())
    problemas.extend(report.golden_gaps())
    with tempfile.TemporaryDirectory(prefix="ready-") as pasta:
        resultados = audit(work_dir=Path(pasta), only=prefixos or None)
        for linha in render_report(resultados):
            print(linha)
        problemas.extend(readiness(resultados))

    print(f"\nsuperficies avaliadas: {len(resultados)}")
    if problemas:
        print(f"IMPEDIMENTOS ({len(problemas)}):")
        for item in problemas:
            print(f"  - {item}")
        _print_revision()
        return 1
    print(
        f"PRONTO: {len(resultados)} superficies com registro, sem coluna inventada e com teste "
        f"que confronta a spec; contrato das specs e da matriz sem problema."
    )
    _print_revision()
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--state" in argv:
        restantes = [item for item in argv if item != "--state"]
        if not restantes:
            print("--state exige o estado, ex.: --state IAM")
            return 1
        return _run_state_review(restantes[0])
    if "--matrix" in argv:
        return _print_matrix()
    if "--golden" in argv:
        _report_golden_coverage()
        _print_revision()
        return 0
    if "--ready" in argv:
        return _run_ready([item for item in argv if item != "--ready"])
    if "--audit" in argv:
        return _run_audit([item for item in argv if item != "--audit"])
    root = Path(argv[0]) if argv else DEFAULT_SPECS_ROOT

    files = _surface_files(root)
    if not files:
        print(f"nenhuma especificacao encontrada em {root}")
        return 1

    problems: list[str] = []
    total_columns = 0
    total_generatable = 0
    total_unverified = 0
    total_format_observed = 0

    header = f"{'superficie':<48} {'conj':>4} {'cols':>5} {'gerav':>6} {'obrig':>6} {'n/ver':>6}  status"
    print(header)
    print("-" * len(header))

    for path in files:
        try:
            spec = load_spec(path)
        except SpecError as exc:
            problems.append(str(exc))
            print(f"{path.name:<48} {'-':>4} {'-':>5} {'-':>6} {'-':>6} {'-':>6}  INVALIDA")
            continue

        extra = validate_spec(spec)
        problems.extend(extra)

        columns = len(spec.columns)
        generatable = spec.generatable_count
        required = len(spec.required_names)
        unverified = len(spec.unverified_fields)
        total_columns += columns
        total_generatable += generatable
        total_unverified += unverified
        total_format_observed += sum(
            1 for column in spec.columns if (column.type_source or "") == "format-observed"
        )

        status = "OK" if not extra else "PROBLEMAS"
        print(
            f"{spec.surface:<48} {len(spec.sets):>4} {columns:>5} {generatable:>6} "
            f"{required:>6} {unverified:>6}  {status}"
        )

    print("-" * len(header))
    print(
        f"superficies={len(files)}  colunas={total_columns}  geraVEIS={total_generatable}  "
        f"nao_comprovadas={total_unverified}  problemas={len(problems)}"
    )
    print(
        f"tipo derivado do formato oficial (type_source=format-observed): {total_format_observed}"
    )

    for problem in problems:
        print(f"  ! {problem}")

    _print_revision()

    if problems:
        print("\nVEREDITO: especificacoes invalidas -- corrija antes de gerar codigo")
        return 1

    print("\nVEREDITO: todas as especificacoes estao estruturais e evidenciadas")
    return 0


def all_specs_count(root: Path | None = None) -> int:
    """Quantidade de especificacoes validas (auxiliar para os testes)."""
    return len(load_all_specs(root))


if __name__ == "__main__":
    sys.exit(main())
