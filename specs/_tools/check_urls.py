"""Confere que toda URL citada como evidencia resolve de fato.

Uma citacao que da 404 nao e evidencia. Este script varre as especificacoes,
junta as URLs distintas (ignorando o fragmento, que nao vai ao servidor) e
pergunta a cada uma se ela existe.

Depende de rede, entao NAO entra na suite: e ferramenta de manutencao, rodada
quando as specs mudam ou quando alguem duvida da procedencia.

Uso:
    python specs/_tools/check_urls.py           # checa tudo
    python specs/_tools/check_urls.py --listar  # so lista as URLs
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urldefrag
from urllib.request import Request

SPECS_ROOT = Path(__file__).resolve().parents[1]
TEMPO_LIMITE = 25
AGENTE = "Mozilla/5.0 (compatible; simulador-nuvem evidence check)"


def _colunas(raw: dict[str, object]) -> list[dict[str, object]]:
    sets = raw.get("sets")
    if isinstance(sets, list):
        encontradas: list[dict[str, object]] = []
        for item in sets:
            if isinstance(item, dict) and isinstance(item.get("columns"), list):
                encontradas.extend(item["columns"])
        if encontradas:
            return encontradas
    colunas = raw.get("columns")
    return colunas if isinstance(colunas, list) else []


def coletar_urls() -> list[str]:
    """URLs distintas citadas nas specs, sem fragmento e em ordem estavel."""
    urls: set[str] = set()
    for path in sorted(SPECS_ROOT.glob("*/*.schema.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        for coluna in _colunas(raw):
            if coluna.get("source_url"):
                urls.add(str(coluna["source_url"]))

        referencia = raw.get("reference") or {}
        if isinstance(referencia, dict):
            if referencia.get("url"):
                urls.add(str(referencia["url"]))
            for extra in referencia.get("additional_sources") or []:
                candidato = extra.get("url") if isinstance(extra, dict) else extra
                if candidato:
                    urls.add(str(candidato))

    return sorted({urldefrag(url)[0] for url in urls if url})


def status_de(url: str) -> int | str:
    """Codigo HTTP da URL; ``'ERRO'`` se nem a conexao completar."""
    for metodo in ("HEAD", "GET"):
        requisicao = Request(url, method=metodo, headers={"User-Agent": AGENTE})
        try:
            with urllib.request.urlopen(requisicao, timeout=TEMPO_LIMITE) as resposta:
                return int(resposta.status)
        except urllib.error.HTTPError as exc:
            if metodo == "GET":
                return int(exc.code)
        except Exception:  # noqa: BLE001 - qualquer falha de rede e "nao resolveu"
            if metodo == "GET":
                return "ERRO"
    return "ERRO"


def main(argv: list[str]) -> int:
    urls = coletar_urls()
    if not urls:
        print("nenhuma URL de evidencia encontrada nas especificacoes")
        return 1

    if "--listar" in argv:
        for url in urls:
            print(url)
        print(f"\n{len(urls)} URLs distintas")
        return 0

    falhas: list[tuple[int | str, str]] = []
    for url in urls:
        codigo = status_de(url)
        if codigo != 200:
            falhas.append((codigo, url))

    print(f"URLs de evidencia distintas: {len(urls)}")
    print(f"resolvem (200): {len(urls) - len(falhas)}")
    print(f"nao resolvem  : {len(falhas)}")

    for codigo, url in falhas:
        print(f"  ! {codigo}  {url}")

    if falhas:
        print("\nVEREDITO: ha citacao apontando para pagina que nao existe")
        return 1

    print("\nVEREDITO: toda citacao de evidencia resolve")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
