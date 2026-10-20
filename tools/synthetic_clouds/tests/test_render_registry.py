"""O registro de renderers e UM snapshot: as passagens de descoberta concordam.

Regressao do ``KeyError: 'gcp_scc_findings'`` do gerador one-shot.

O CLI monta o ``--emit`` default numa PASSAGEM de descoberta
(:func:`registered_names`) e resolve cada nome do default numa NOVA PASSAGEM,
dentro do laco de render (:func:`get_renderer`). Sao varreduras independentes
e nada obrigava as duas a concordar: um modulo que importava na primeira e
falhava na segunda (import nao-determinista, recurso consumido, estado entre
passagens) sumia do registro, e o ``get_renderer`` levantava ``KeyError``
sobre um nome que o proprio CLI tinha acabado de listar.

O teste reproduz esse modo de falha de forma DETERMINISTICA: o modulo deixa
de ser importavel depois da primeira passagem, e o registro tem de continuar
servindo o renderer que ja registrou.
"""

from __future__ import annotations

import sys
from types import ModuleType
from typing import cast

from tools.synthetic_clouds.render import base

#: O renderer do defeito reportado e o modulo que o define.
_CULPRIT = "gcp_scc_findings"
_CULPRIT_MODULE = "tools.synthetic_clouds.render.gcp_scc_findings"


def _break_import(module: str) -> ModuleType | None:
    """Torna o modulo nao importavel e devolve o valor anterior de ``sys.modules``.

    ``sys.modules[nome] = None`` e a forma oficial de o importador recusar o
    modulo (``ModuleNotFoundError: import of X halted; None in sys.modules``) --
    e e exatamente o modo de falha reportado: o modulo importava numa passagem e
    falhava na seguinte.
    """
    anterior = sys.modules.get(module)
    # O ``None`` e o que o importador interpreta como "recusado"; o ``cast`` e
    # porque o tipo declarado de ``sys.modules`` nao admite esse valor.
    sys.modules[module] = cast("ModuleType", None)
    return anterior


def _restore_import(module: str, anterior: ModuleType | None) -> None:
    """Devolve ``sys.modules`` ao estado anterior."""
    if anterior is None:
        sys.modules.pop(module, None)
    else:
        sys.modules[module] = anterior


def test_registro_estavel_entre_passagens() -> None:
    """O nome listado por ``registered_names`` continua resolvendo em ``get_renderer``.

    Sem o registro memoizado, a segunda passagem revarre o pacote, o modulo
    quebrado cai em ``_BROKEN`` e ``get_renderer`` levanta ``KeyError`` sobre um
    nome que a primeira passagem acabou de listar.
    """
    nomes = base.registered_names()
    assert _CULPRIT in nomes, f"o renderer do defeito sumiu do registro: {nomes}"

    anterior = _break_import(_CULPRIT_MODULE)
    try:
        for nome in nomes:
            assert base.get_renderer(nome).name == nome
    finally:
        _restore_import(_CULPRIT_MODULE, anterior)


def test_emit_default_do_cli_resolve_inteiro() -> None:
    """O ``--emit`` default do CLI resolve nome por nome, sem levantar KeyError.

    Reproduz o caminho real do ``cli.py`` (argparse -> default -> validacao ->
    laco de render) sem construir o estado: o que o CLI precisa e que o default
    que ele mesmo montou seja resolvivel.
    """
    from tools.synthetic_clouds import cli

    args = cli._parse_args(["--seed", "123", "--profile", "small"])
    nomes = cli._emit_names(args.emit)
    assert _CULPRIT in nomes
    for nome in nomes:
        assert base.get_renderer(nome).name == nome


def test_nome_desconhecido_levanta_keyerror() -> None:
    """O registro ainda recusa um nome que nao existe (fail-closed, nao silencioso)."""
    try:
        base.get_renderer("renderer_que_nao_existe")
    except KeyError:
        return
    raise AssertionError("get_renderer aceitou um nome inexistente")


def test_broken_modules_relata_o_motivo() -> None:
    """``broken_modules`` diz o motivo literal de um modulo que nao importou."""
    modulo = "tools.synthetic_clouds.render.gcp_scc_findings"
    nome_modulo = modulo.rsplit(".", 1)[-1]
    anterior = _break_import(modulo)
    try:
        # Um modulo quebrado nao pode entrar no registro; o motivo e publicado.
        base._REGISTRY = None  # força a revarredura que vai enxergar a quebra
        base._discover_renderers()
        assert nome_modulo in base.broken_modules()
        assert "ModuleNotFoundError" in base.broken_modules()[nome_modulo]
    finally:
        _restore_import(modulo, anterior)
        base._REGISTRY = None
        base._discover_renderers()
