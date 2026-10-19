"""A matriz de cobertura tem de permanecer verdadeira.

A matriz liga cada superficie especificada ao renderer que a produz. Os testes
abaixo impedem os dois modos de ela mentir: uma superficie especificada que
ninguem declarou (trabalho esquecido) e uma superficie declarada que nao existe
mais na especificacao (trabalho fantasma).
"""

from __future__ import annotations

from tools.synthetic_clouds.fidelity import matrix
from tools.synthetic_clouds.fidelity.spec import load_all_specs
from tools.synthetic_clouds.render.base import registered_names


def test_a_matriz_cobre_exatamente_as_superficies_especificadas() -> None:
    especificadas = {spec.surface for spec in load_all_specs()}
    declaradas = set(matrix.declared_surfaces())

    faltando = sorted(especificadas - declaradas)
    fantasma = sorted(declaradas - especificadas)

    assert not faltando, f"superficie especificada sem declaracao na matriz: {faltando}"
    assert not fantasma, f"superficie declarada que nao existe mais em specs/: {fantasma}"


def test_superficie_implementada_aponta_para_renderer_registrado() -> None:
    registrados = set(registered_names())
    for coverage in matrix.by_status(matrix.STATUS_IMPLEMENTED):
        assert coverage.renderer, coverage.surface
        assert coverage.renderer in registrados, (
            f"{coverage.surface} diz ser produzida por {coverage.renderer!r}, "
            f"que nao esta registrado em render/base.py: {sorted(registrados)}"
        )


def test_superficie_nao_implementada_explica_o_motivo() -> None:
    for coverage in matrix.SURFACES:
        if coverage.status == matrix.STATUS_IMPLEMENTED:
            continue
        assert coverage.note.strip(), f"{coverage.surface} sem justificativa"


def test_estado_desconhecido_e_recusado() -> None:
    try:
        matrix.by_status("quase-pronto")
    except ValueError as exc:
        assert "desconhecido" in str(exc)
    else:  # pragma: no cover - o caminho feliz nao deve ocorrer
        raise AssertionError("estado invalido foi aceito")


def test_resumo_conta_todas_as_superficies() -> None:
    resumo = matrix.summary()

    assert sum(resumo.values()) == len(matrix.SURFACES)
    assert set(resumo) == {"implemented", "pending", "blocked"}


def test_superficie_nao_declarada_devolve_nada() -> None:
    assert matrix.coverage_for("aws/inexistente") is None
