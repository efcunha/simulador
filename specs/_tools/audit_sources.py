"""Auditoria de procedencia: de quais dominios cada especificacao tira evidencia.

Uma especificacao pode estar estruturalmente valida e ainda assim se apoiar em
fonte que nao e documentacao oficial. Este script responde a pergunta que
importa: cada coluna cita de fato uma pagina do provedor?

A lista de dominios oficiais vive em ``tools/synthetic_clouds/fidelity/sources.py``,
para que a mesma regra valha no script e na suite de testes.

Uso:  python specs/_tools/audit_sources.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from tools.synthetic_clouds.fidelity.sources import domain_of, is_official_url  # noqa: E402

SPECS_ROOT = Path(__file__).resolve().parents[1]


def _columns(raw: dict[str, object]) -> list[dict[str, object]]:
    sets = raw.get("sets")
    if isinstance(sets, list):
        found: list[dict[str, object]] = []
        for item in sets:
            if isinstance(item, dict) and isinstance(item.get("columns"), list):
                found.extend(item["columns"])
        if found:
            return found
    columns = raw.get("columns")
    return columns if isinstance(columns, list) else []


def main() -> int:
    problems = 0
    for path in sorted(SPECS_ROOT.glob("*/*.schema.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        columns = _columns(raw)
        urls = [str(column.get("source_url") or "") for column in columns]

        missing = sum(1 for url in urls if not url)
        non_official = [url for url in urls if url and not is_official_url(url)]
        domains = Counter(domain_of(url) for url in urls if url)

        label = f"{path.parent.name}/{path.name.replace('.schema.json', '')}"
        print(f"\n{label}")
        print(f"  colunas={len(columns)}  sem_source_url={missing}  nao_oficiais={len(non_official)}")
        for domain, count in domains.most_common():
            print(f"    {count:>4}  {domain}")

        if missing or non_official:
            problems += 1
            for url in non_official[:5]:
                print(f"    ! fora da doc oficial: {url}")

    print(f"\nespecificacoes com problema de procedencia: {problems}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
