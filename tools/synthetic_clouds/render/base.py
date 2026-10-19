"""Renderer protocol and registry — the Phase 2-4 plug-in point (FR-G3).

A renderer is a PURE projection: it reads a validated ``CanonicalEstate`` and
writes wire artifacts. It holds no scenario logic and no estate construction. New
renderers register by implementing the protocol and adding themselves to the
registry; the CLI ``--emit`` selects which run. Phase 1 shipped ``focus_azure`` and
``gcp_bigquery``; Phase 3 added the two GCP container renderers and Phase 6 added
``focus_aws``, all plugging in here without touching the canonical model. The AWS CUR 2.0
renderer (``cur2_aws``) joins them the same way: one entry, no model change.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, cast, runtime_checkable

from tools.synthetic_clouds.model.estate import CanonicalEstate


class RenderError(Exception):
    """Raised when a renderer cannot project a required canonical field."""


@runtime_checkable
class Renderer(Protocol):
    """A pure projection from the canonical estate to wire artifacts."""

    name: str

    def render(self, estate: CanonicalEstate, out_dir: Path) -> list[Path]:
        """Project ``estate`` into wire artifacts under ``out_dir``; return paths."""
        ...


def _discover_renderers() -> dict[str, Renderer]:
    """Descobre os renderers varrendo o pacote (a lista de nomes vem daqui, NIT-3).

    O registro explicito num arquivo unico virou gargalo: cada onda nova precisa
    editar o MESMO arquivo, e dois trabalhos em paralelo colidem nele. A
    descoberta elimina o gargalo -- criar o modulo passa a bastar.

    A varredura e conservadora: so aceita classe DEFINIDA no modulo (nao
    reexportada), instanciavel sem argumentos, com ``name`` textual e um
    ``render`` chamavel. Nome duplicado e erro, nao desempate silencioso.

    Um modulo que nao importa (edicao a meio, por exemplo) NAO derruba o
    registro: ele e anotado em :func:`broken_modules` e o resto continua
    utilizavel. Ignorar em silencio seria pior -- a superficie que depende dele
    falha na invariante que exige renderer registrado.
    """
    import importlib
    import inspect
    import pkgutil

    pacote = importlib.import_module("tools.synthetic_clouds.render")
    encontrados: dict[str, Renderer] = {}
    _BROKEN.clear()

    for info in sorted(pkgutil.iter_modules(pacote.__path__), key=lambda item: item.name):
        try:
            modulo = importlib.import_module(f"{pacote.__name__}.{info.name}")
        except Exception as exc:  # noqa: BLE001 - modulo quebrado nao derruba o registro
            _BROKEN[info.name] = f"{type(exc).__name__}: {exc}"
            continue
        for objeto in vars(modulo).values():
            if not inspect.isclass(objeto) or objeto.__module__ != modulo.__name__:
                continue
            if not isinstance(getattr(objeto, "name", None), str):
                continue
            if not callable(getattr(objeto, "render", None)):
                continue
            try:
                instancia = objeto()
            except TypeError:
                continue  # nao e renderer: exige argumentos para existir
            chave = getattr(instancia, "name", None)
            if not isinstance(chave, str):
                continue
            if chave in encontrados:
                raise RenderError(
                    f"dois renderers disputam o nome {chave!r}: {type(encontrados[chave]).__name__} "
                    f"e {type(instancia).__name__}"
                )
            encontrados[chave] = cast("Renderer", instancia)

    return encontrados


_BROKEN: dict[str, str] = {}


def broken_modules() -> dict[str, str]:
    """Modulos do pacote que nao importaram na ultima varredura, com o motivo."""
    _discover_renderers()
    return dict(_BROKEN)


def get_renderer(name: str) -> Renderer:
    """Return the registered renderer named ``name`` (raises ``KeyError`` if absent)."""
    return _discover_renderers()[name]


def registered_names() -> tuple[str, ...]:
    """Return the names of all registered renderers (derived from the registry, NIT-3)."""
    return tuple(_discover_renderers())
