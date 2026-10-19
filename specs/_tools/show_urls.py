"""Mostra as URLs de evidencia distintas de uma especificacao, com contagem.

Ajuda a distinguir "a coluna cita a pagina que a documenta" de "a coluna cita
uma pagina que nunca foi lida". Uma spec inteira apontando para uma unica URL
generica e sinal de alerta.

Uso:  python specs/_tools/show_urls.py aws/bcm-data-exports-cur2
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

SPECS_ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str]) -> int:
    if not argv:
        print("informe a superficie, ex.: aws/bcm-data-exports-cur2")
        return 2

    target = SPECS_ROOT / argv[0]
    path = target if target.suffix == ".json" else target.with_suffix(".schema.json")
    if not path.is_file():
        print(f"nao encontrado: {path}")
        return 2

    raw = json.loads(path.read_text(encoding="utf-8"))
    columns = raw.get("columns") or []
    urls = Counter(str(column.get("source_url") or "<vazio>") for column in columns)

    reference = raw.get("reference") or {}
    print(f"superficie : {raw.get('surface')}")
    print(f"provider   : {raw.get('provider')}")
    print(f"reference  : {reference.get('title')}")
    print(f"             {reference.get('url')}")
    print(f"             consultado em {reference.get('consulted_at')}")
    print(f"colunas    : {len(columns)}  URLs distintas: {len(urls)}")
    print(f"nao comprovadas: {len(raw.get('unverified') or [])}")
    print()
    for url, count in urls.most_common():
        print(f"  {count:>4}  {url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
