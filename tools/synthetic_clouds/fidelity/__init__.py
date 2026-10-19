"""Fidelidade de export: das especificacoes citadas para o artefato gerado.

Este pacote e o que transforma a regra "nenhum campo inventado" em algo
executavel. Ele le as especificacoes de ``specs/`` -- cada coluna com a URL da
documentacao oficial que a define -- e compara com o que o gerador realmente
emite, falhando fechado em qualquer divergencia.
"""

from __future__ import annotations

from tools.synthetic_clouds.fidelity.artifacts import columns_of, is_empty_value, populated_of
from tools.synthetic_clouds.fidelity.checker import (
    KIND_INVENTED,
    KIND_MISSING,
    KIND_ORDER,
    KIND_POPULATED_EMPTY,
    KIND_UNVERIFIED,
    Finding,
    ScopeError,
    check,
    check_artifact,
    check_values,
    is_faithful,
)
from tools.synthetic_clouds.fidelity.matrix import (
    STATUS_BLOCKED,
    STATUS_IMPLEMENTED,
    STATUS_PENDING,
    SurfaceCoverage,
    coverage_for,
    summary,
)
from tools.synthetic_clouds.fidelity.sources import OFFICIAL_DOMAINS, is_official_url
from tools.synthetic_clouds.fidelity.spec import (
    DEFAULT_SPECS_ROOT,
    Column,
    SpecError,
    SurfaceSpec,
    UnverifiedField,
    load_all_specs,
    load_spec,
    validate_spec,
)

__all__ = [
    "DEFAULT_SPECS_ROOT",
    "KIND_INVENTED",
    "KIND_MISSING",
    "KIND_ORDER",
    "KIND_POPULATED_EMPTY",
    "KIND_UNVERIFIED",
    "OFFICIAL_DOMAINS",
    "STATUS_BLOCKED",
    "STATUS_IMPLEMENTED",
    "STATUS_PENDING",
    "Column",
    "Finding",
    "ScopeError",
    "SpecError",
    "SurfaceCoverage",
    "SurfaceSpec",
    "UnverifiedField",
    "check",
    "check_artifact",
    "check_values",
    "columns_of",
    "coverage_for",
    "is_empty_value",
    "is_faithful",
    "is_official_url",
    "load_all_specs",
    "load_spec",
    "populated_of",
    "summary",
    "validate_spec",
]
