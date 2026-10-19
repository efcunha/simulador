"""Lista colunas de uma especificacao filtradas por trecho da URL de origem.

Serve para a verificacao hostil: pega-se uma amostra de colunas de uma pagina da
documentacao e confere-se, na propria pagina, que aqueles nomes existem mesmo.

Uso:  python specs/_tools/list_columns.py aws/bcm-data-exports-cur2 line-item [limite]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SPECS_ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("uso: list_columns.py <provider/superficie> <trecho-da-url> [limite]")
        return 2

    surface, needle = argv[0], argv[1]
    limit = int(argv[2]) if len(argv) > 2 else 20

    path = SPECS_ROOT / f"{surface}.schema.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    columns = [
        column
        for column in (raw.get("columns") or [])
        if needle in str(column.get("source_url") or "")
    ]

    print(f"{surface}: {len(columns)} colunas cuja origem contem {needle!r}")
    for column in columns[:limit]:
        print(f"  {column['name']:<46} {column.get('type', ''):<12} {column.get('status', '')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
