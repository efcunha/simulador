"""A revisao que a medicao mediu (D8).

O problema que isto resolve nao e de conveniencia: ``--audit`` e ``--matrix`` produzem
numeros por superficie (arquivos, registros, caminhos), e esses numeros mudam a cada
commit. Um relatorio sem a revisao que o produziu nao e comparavel com o proximo -- duas
medicoes em revisoes diferentes viram uma discussao sobre qual delas "esta certa".

Por isso a revisao e IMPRESSA junto do resultado, em vez de anotada a mao em algum
documento: um numero escrito a mao envelhece no primeiro commit seguinte, e um documento
que afirma a revisao errada e pior do que um que nao a afirma.

Duas propriedades deliberadas:

* **Nao levanta.** Fora de um repositorio git (uma copia exportada, um tarball) a
  auditoria continua valendo -- ela mede artefatos, nao o git. A revisao vira
  ``desconhecida``, que e a verdade, em vez de um erro que impede a medicao.
* **A arvore suja e dita.** Um commit limpo e uma medicao reproduzivel; uma arvore com
  alteracoes nao commitadas mede algo que nenhum commit contem. O campo ``dirty`` existe
  para essa diferenca aparecer na propria saida, e nao ser descoberta depois.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

#: Onde o git procura o repositorio. O modulo vive em ``fidelity/``, entao o pacote esta
#: um nivel acima -- a mesma raiz que ``pyproject.toml`` e ``daily/`` usam.
_REPO_ROOT = Path(__file__).resolve().parents[2]

#: O executavel do git, resolvido uma vez. ``None`` significa "nao ha git aqui", que e
#: resposta legitima: a auditoria mede artefatos e nao depende do git para valer.
RESOLVED_GIT = shutil.which("git")

#: Segundos. Um ``git`` travado (indice sob lock, disco de rede) nao pode travar a
#: auditoria inteira: sem resposta a tempo, a revisao e desconhecida e a medicao segue.
_GIT_TIMEOUT_SECONDS = 10.0

UNKNOWN_REVISION = "desconhecida"

Runner = Callable[[Sequence[str]], "subprocess.CompletedProcess[str]"]


@dataclass(frozen=True, slots=True)
class Revision:
    """Uma revisao do simulador, como o git a descreve.

    ``dirty`` e tri-estado por necessidade: ``None`` significa "nao foi possivel saber"
    (sem git, sem resposta), que nao e o mesmo que "limpa". Dizer "limpa" sem ter olhado
    seria afirmar reproducibilidade que ninguem checou.
    """

    commit: str
    branch: str
    dirty: bool | None

    def describe(self) -> str:
        """Uma linha, no formato que a auditoria imprime."""
        estado = {True: "com alteracoes nao commitadas", False: "limpa", None: "estado desconhecido"}[self.dirty]
        return f"revisao={self.commit}  branch={self.branch}  arvore={estado}"


def _git_command(arguments: Sequence[str]) -> list[str]:
    """Build the argv for one git call, or refuse when there is no git to call.

    The executable is the one ``shutil.which`` resolved -- an absolute path -- rather than
    the bare name ``git``: the name would be looked up in ``PATH`` a second time, which is
    both a lint finding (S607) and a real difference, since ``PATH`` can change between
    the import and the call.
    """
    if RESOLVED_GIT is None:
        raise FileNotFoundError("git is not on PATH")
    return [RESOLVED_GIT, *arguments]


def _run_git(arguments: Sequence[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run one git command, never raising for a non-zero exit.

    ``check=False`` because "no git here" and "not a repository" are answers this module
    handles, not failures to propagate.
    """
    return subprocess.run(  # noqa: S603 - resolved absolute binary, argument list, shell=False
        _git_command(arguments),
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=_GIT_TIMEOUT_SECONDS,
    )


def _text(result: subprocess.CompletedProcess[str]) -> str:
    return (result.stdout or "").strip()


def detect_revision(repo_root: Path | None = None, runner: Runner | None = None) -> Revision:
    """Return the revision of ``repo_root`` (default: this repository).

    ``runner`` is injectable so the suite can prove the three outcomes -- clean, dirty,
    absent -- without needing a git repository in each of those states.
    """
    root = _REPO_ROOT if repo_root is None else repo_root

    def run(arguments: Sequence[str]) -> subprocess.CompletedProcess[str]:
        return _run_git(arguments, cwd=root)

    call_runner: Runner = run if runner is None else runner

    def call(arguments: Sequence[str]) -> subprocess.CompletedProcess[str] | None:
        try:
            return call_runner(arguments)
        except (OSError, subprocess.SubprocessError):
            # Sem git instalado (FileNotFoundError), sem permissao ou estouro do
            # timeout: em todos, a revisao e desconhecida e a medicao continua.
            return None

    commit_result = call(["rev-parse", "--short", "HEAD"])
    if commit_result is None or commit_result.returncode != 0:
        return Revision(commit=UNKNOWN_REVISION, branch=UNKNOWN_REVISION, dirty=None)
    commit = _text(commit_result) or UNKNOWN_REVISION

    branch_result = call(["rev-parse", "--abbrev-ref", "HEAD"])
    branch = _text(branch_result) if branch_result is not None and branch_result.returncode == 0 else ""
    if not branch:
        branch = UNKNOWN_REVISION

    # ``diff-index --quiet HEAD`` sai 1 quando a arvore difere do commit. E o teste que
    # cobre arquivos RASTREADOS: um arquivo nao versionado nao invalida a medicao do que
    # esta versionado, e tratalo como sujeira faria o campo nunca ficar limpo neste
    # repositorio, onde a saida diaria nasce dentro do pacote.
    dirty_result = call(["diff-index", "--quiet", "HEAD"])
    dirty = None if dirty_result is None else dirty_result.returncode != 0

    return Revision(commit=commit, branch=branch, dirty=dirty)


__all__ = ["RESOLVED_GIT", "UNKNOWN_REVISION", "Revision", "detect_revision"]
