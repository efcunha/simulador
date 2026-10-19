"""Procedencia: de onde a evidencia pode vir.

A regra do projeto e que todo campo se apoia em documentacao oficial do
provedor. "Oficial" nao e uma impressao -- e uma lista fechada de dominios, e
esta aqui para poder ser testada. Um campo citando dominio fora desta lista e um
defeito de fidelidade, mesmo que o texto pareca plausivel.

Ficam de fora, deliberadamente, buscadores, wikis, blogs, repositorios de
terceiros e sites de consultoria: nenhum deles e o provedor afirmando o que o
provedor faz.
"""

from __future__ import annotations

from urllib.parse import urlparse

# Dominios aceitos como documentacao oficial.
OFFICIAL_DOMAINS: tuple[str, ...] = (
    # AWS
    "docs.aws.amazon.com",
    "aws.amazon.com",
    # Google Cloud
    "cloud.google.com",
    "docs.cloud.google.com",
    # Microsoft Azure
    "learn.microsoft.com",
    # O standard FOCUS: site do projeto e o repositorio normativo.
    "focus.finops.org",
    "github.com",
    "raw.githubusercontent.com",
)


def domain_of(url: str) -> str:
    """Hostname normalizado de ``url`` (vazio se nao for URL utilizavel)."""
    try:
        return (urlparse(str(url)).hostname or "").lower()
    except ValueError:
        return ""


def is_official_url(url: str) -> bool:
    """Verdadeiro se ``url`` pertence a um dominio de documentacao oficial."""
    domain = domain_of(url)
    if not domain:
        return False
    return any(domain == official or domain.endswith("." + official) for official in OFFICIAL_DOMAINS)
