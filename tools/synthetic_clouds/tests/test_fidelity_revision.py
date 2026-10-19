"""D8: a medicao diz QUAL revisao ela mediu.

Estes testes existem por um modo especifico de o relatorio mentir sem ninguem notar: os
numeros por superficie (arquivos, registros, caminhos) so valem para o commit que os
produziu, e um relatorio sem a revisao nao e comparavel com o proximo. A invariante aqui e
que a revisao sai junto do resultado -- e que ela sabe dizer "nao sei" em vez de inventar.
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence

import pytest

from tools.synthetic_clouds.fidelity import __main__ as fidelity_cli
from tools.synthetic_clouds.fidelity import revision as revision_module
from tools.synthetic_clouds.fidelity.revision import UNKNOWN_REVISION, Revision, detect_revision

_COMMIT = "d44624c"


def _result(returncode: int = 0, stdout: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["git"], returncode=returncode, stdout=stdout, stderr="")


def _git(commit: str = _COMMIT, branch: str = "master", dirty: bool = False) -> revision_module.Runner:
    """Um git de mentira: responde por subcomando, nao por ordem de chamada."""

    def runner(arguments: Sequence[str]) -> subprocess.CompletedProcess[str]:
        if arguments[:2] == ["rev-parse", "--short"]:
            return _result(0, f"{commit}\n")
        if arguments[:2] == ["rev-parse", "--abbrev-ref"]:
            return _result(0, f"{branch}\n")
        if arguments[0] == "diff-index":
            return _result(1 if dirty else 0)
        raise AssertionError(f"comando git inesperado: {arguments}")

    return runner


def test_arvore_limpa_e_revisao_dita() -> None:
    detectada = detect_revision(runner=_git())

    assert detectada.commit == _COMMIT
    assert detectada.branch == "master"
    assert detectada.dirty is False


def test_arvore_suja_e_dita_como_suja() -> None:
    """Um commit e uma arvore alterada medem coisas diferentes; a saida tem que dizer."""
    detectada = detect_revision(runner=_git(dirty=True))

    assert detectada.dirty is True
    assert "com alteracoes nao commitadas" in detectada.describe()


def test_sem_git_a_revisao_e_desconhecida_e_nao_um_erro() -> None:
    """Fora de um repositorio a auditoria continua valendo: ela mede artefatos, nao git."""

    def ausente(arguments: Sequence[str]) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("git nao instalado")

    detectada = detect_revision(runner=ausente)

    assert detectada.commit == UNKNOWN_REVISION
    assert detectada.dirty is None
    assert "estado desconhecido" in detectada.describe()


def test_repositorio_inexistente_tambem_e_desconhecido() -> None:
    """``rev-parse`` fora de um repo sai != 0; isso e resposta, nao excecao."""
    detectada = detect_revision(runner=lambda arguments: _result(128, ""))

    assert detectada.commit == UNKNOWN_REVISION
    assert detectada.dirty is None


def test_sem_git_no_path_a_constante_declara_isso() -> None:
    """A ausencia de git e um fato do modulo, nao uma excecao a ser capturada no meio."""
    assert revision_module.RESOLVED_GIT is None or "git" in revision_module.RESOLVED_GIT.lower()


def test_sem_git_no_path_a_revisao_e_desconhecida(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(revision_module, "RESOLVED_GIT", None)

    detectada = detect_revision()

    assert detectada.commit == UNKNOWN_REVISION
    assert detectada.branch == UNKNOWN_REVISION
    assert detectada.dirty is None


def test_o_cli_imprime_a_revisao_junto_do_resultado(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A revisao vai na SAIDA -- um documento afirmando a revisao envelhece no commit seguinte."""
    monkeypatch.setattr(
        fidelity_cli,
        "detect_revision",
        lambda: Revision(commit=_COMMIT, branch="master", dirty=False),
    )

    codigo = fidelity_cli.main(["--golden"])
    saida = capsys.readouterr().out

    assert codigo == 0
    assert f"revisao={_COMMIT}" in saida
    assert "arvore=limpa" in saida


def test_a_revisao_real_do_repositorio_e_legivel() -> None:
    """Sem runner falso: prova que a deteccao funciona neste repositorio, nao so no mock."""
    detectada = detect_revision()

    assert detectada.commit != UNKNOWN_REVISION
    assert len(detectada.commit) >= 7
    assert detectada.branch
    assert detectada.dirty is not None
