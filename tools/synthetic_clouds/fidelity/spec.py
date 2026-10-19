"""Leitura e validacao das especificacoes de export documentadas.

A especificacao e a fonte da verdade: nenhum campo pode ser gerado sem que a
documentacao oficial o defina. Por isso este modulo falha FECHADO -- uma
especificacao sem evidencia e um erro, nunca um aviso.

Tres ideias sustentam o modelo:

``status``
    ``verified`` ou ``unverified``. O eixo binario: a documentacao afirma ou
    nao afirma.

``evidence``
    Qualidade da afirmacao, quando ela existe. Uma coluna documentada apenas em
    um exemplo de resultado nao e um contrato. Por isso so ``declared`` (ou a
    ausencia do campo, tratada como ``declared``) autoriza a geracao; qualquer
    outro qualificador torna a coluna NAO geraVEL, mesmo marcada como
    verificada. Um qualificador desconhecido tambem nao gera -- falha fechada.

``sets``
    Uma superficie pode ter MAIS DE UM esquema. O dataset classico de custo da
    Microsoft, por exemplo, tem um conjunto de colunas por tipo de contrato
    (EA, MCA, MPA, CSP, PAYG), com grafias divergentes entre eles. Achatar isso
    num unico conjunto destruiria a informacao; por isso os conjuntos sao
    preservados e cada coluna herda o nome do seu conjunto como ``scope``.

Regra final: uma coluna so e geraVEL se tiver nome, TIPO documentado, status
verificado, URL de origem e afirmacao declarativa. Sem tipo publicado, o campo
nao e gerado -- nao se inventa tipo.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

STATUS_VERIFIED = "verified"
STATUS_UNVERIFIED = "unverified"
_KNOWN_STATUSES = frozenset({STATUS_VERIFIED, STATUS_UNVERIFIED})

# Qualificadores que autorizam geracao de VALOR. Ausencia de ``evidence``
# equivale a ``declared``. Qualquer outro valor (ex.: "example-only",
# "name-only") descreve documentacao real, porem insuficiente para virar
# contrato.
EVIDENCE_DECLARED = "declared"
EVIDENCE_NULL_EMPTY = "null-empty"
_GENERATABLE_EVIDENCE = frozenset({EVIDENCE_DECLARED, None, ""})

# Qualificadores que autorizam a COLUNA a existir no artefato. `null-empty`
# entra aqui e nao em `_GENERATABLE_EVIDENCE`: a documentacao afirma que a
# coluna FAZ PARTE do arquivo, e afirma tambem que ela nunca tem valor. Omitir a
# coluna seria infiel ao formato; preenche-la seria infiel ao contrato. O unico
# resultado correto e emiti-la vazia.
_EMITTABLE_EVIDENCE = frozenset({EVIDENCE_DECLARED, EVIDENCE_NULL_EMPTY, None, ""})

# De onde veio o TIPO da coluna:
#   documented       -- o provedor publica o tipo (tabela de campos, schema, DDL).
#   format-observed  -- o provedor NAO publica tabela de tipos, mas documenta o
#                       campo normativamente E o formato oficial (exemplo de
#                       payload) fixa a representacao: aspas => string, numeral
#                       nu => numero, {}/[] => objeto/array.
# Ausencia equivale a "documented", o que mantem as specs antigas validas.
# `format-observed` NAO e licenca para adivinhar: exige que o CAMPO seja
# declarado (evidence declarativa), senao seria derivar a forma de um exemplo
# para um campo que so existe no exemplo.
TYPE_SOURCE_DOCUMENTED = "documented"
TYPE_SOURCE_FORMAT_OBSERVED = "format-observed"
_GENERATABLE_TYPE_SOURCES = frozenset(
    {TYPE_SOURCE_DOCUMENTED, TYPE_SOURCE_FORMAT_OBSERVED, None, ""}
)

# <repo>/tools/synthetic_clouds/fidelity/spec.py -> parents[3] e a raiz do repo.
DEFAULT_SPECS_ROOT = Path(__file__).resolve().parents[3] / "specs"


class SpecError(ValueError):
    """Especificacao malformada ou sem a evidencia exigida."""


@dataclass(frozen=True, slots=True)
class Column:
    """Uma coluna como a documentacao oficial a define."""

    name: str
    type: str | None
    required: bool
    status: str
    unit: str | None = None
    source_url: str | None = None
    evidence: str | None = None
    scope: str | None = None
    type_source: str | None = None
    type_note: str | None = None

    @property
    def has_contract(self) -> bool:
        """A documentacao estabelece o CAMPO como parte do export.

        Diferente de ``belongs_to_schema``: aqui o TIPO nao entra. Serve para
        julgar ``required``, que fala de PRESENCA. Uma coluna como ``source_id``
        da tabela de findings do SCC esta sempre presente mesmo sem a Microsoft
        publicar o tipo dela -- exigir tipo aqui acusaria uma contradicao que nao
        existe.
        """
        return (
            self.status == STATUS_VERIFIED
            and bool(self.source_url)
            and (self.evidence or "").lower() in _EMITTABLE_EVIDENCE
        )

    @property
    def belongs_to_schema(self) -> bool:
        """A coluna FAZ PARTE do artefato, mesmo que nunca receba valor.

        Distinto de ``is_generatable``: uma coluna documentada como sempre vazia
        pertence ao formato (tem de ser emitida) e nao pode ser preenchida.

        O tipo continua obrigatorio aqui. Num alvo tipado -- Parquet, DDL do
        BigQuery -- escrever uma coluna cujo tipo o provedor nao publica obrigaria
        a inventar o tipo, que e exatamente o que o projeto proibe. O que a
        evidencia ``null-empty`` muda e apenas isto: a coluna existe no arquivo e
        nunca tem valor.
        """
        return (
            self.status == STATUS_VERIFIED
            and bool(self.type)
            and bool(self.source_url)
            and (self.evidence or "").lower() in _EMITTABLE_EVIDENCE
        )

    @property
    def is_generatable(self) -> bool:
        """A coluna pode receber VALOR: pertence ao formato e a evidencia e declarativa."""
        return (
            self.belongs_to_schema
            and (self.evidence or "").lower() in _GENERATABLE_EVIDENCE
            and (self.type_source or "").lower() in _GENERATABLE_TYPE_SOURCES
        )

    @property
    def key(self) -> tuple[str | None, str]:
        """Identidade da coluna: o ``scope`` permite o mesmo nome em contextos distintos."""
        return (self.scope, self.name)


@dataclass(frozen=True, slots=True)
class UnverifiedField:
    """Registro de algo nao comprovado, com o motivo quando houver.

    Duas naturezas, e a distincao evita poluir o espaco de nomes de campo:

    ``field``
        O nome de um CAMPO que a documentacao nao comprova. Entra em
        ``forbidden_names``: emitir esse nome e falha.
    ``topic``
        Uma LACUNA sobre a superficie sem ser um campo -- particionamento,
        clustering, formato de arquivo. Nao e nome de campo, entao nao pode
        tornar um nome de coluna proibido por coincidencia.

    Preservar o MOTIVO importa: e ele que distingue "a documentacao nao publica
    isso" de "eu nao procurei".
    """

    name: str
    reason: str | None = None
    kind: str = "field"


UNVERIFIED_FIELD = "field"
UNVERIFIED_TOPIC = "topic"
_FIELD_KEYS = ("name", "field", "column")
_TOPIC_KEYS = ("item", "topic", "gap")


@dataclass(frozen=True, slots=True)
class ColumnSet:
    """Um conjunto de colunas dentro de uma superficie (ex.: o esquema EA)."""

    name: str
    description: str | None
    columns: tuple[Column, ...]


@dataclass(frozen=True, slots=True)
class SurfaceSpec:
    """Uma superficie de export de um provedor (ex.: FOCUS 1.2 da AWS)."""

    surface: str
    provider: str
    reference: dict[str, Any]
    delivery: dict[str, Any]
    sets: tuple[ColumnSet, ...]
    unverified_fields: tuple[UnverifiedField, ...]
    path: Path | None = None
    extra: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @property
    def unverified(self) -> tuple[str, ...]:
        """Nomes de CAMPO registrados como nao comprovados (lacunas de topico nao entram)."""
        return tuple(item.name for item in self.unverified_fields if item.kind == UNVERIFIED_FIELD)

    @property
    def unverified_topics(self) -> tuple[UnverifiedField, ...]:
        """Lacunas registradas que nao sao nomes de campo (particionamento, formato)."""
        return tuple(item for item in self.unverified_fields if item.kind == UNVERIFIED_TOPIC)

    @property
    def columns(self) -> tuple[Column, ...]:
        return tuple(column for column_set in self.sets for column in column_set.columns)

    @property
    def set_names(self) -> tuple[str, ...]:
        """Nomes dos conjuntos nomeados (um conjunto anonimo unico nao entra)."""
        return tuple(column_set.name for column_set in self.sets if column_set.name)

    def columns_for(self, scope: str) -> tuple[Column, ...]:
        """Colunas de um conjunto nomeado.

        Existe porque contratos diferentes podem ser DISJUNTOS: no dataset
        classico de custo da Microsoft, nenhum dos 132 nomes distintos aparece
        nos cinco contratos ao mesmo tempo. Conferir um artefato gerado para um
        contrato contra a uniao dos cinco acusaria ausencia de tudo o que os
        outros quatro declaram.
        """
        for column_set in self.sets:
            if column_set.name == scope:
                return column_set.columns
        raise KeyError(scope)

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(column.name for column in self.columns)

    @property
    def required_names(self) -> tuple[str, ...]:
        return tuple(column.name for column in self.columns if column.required)

    @property
    def generatable_names(self) -> frozenset[str]:
        """Nomes emitíveis: basta UMA ocorrência gerável, ainda que em outro `set`.

        O mesmo nome pode ser gerável num conjunto e não-gerável em outro (ex.:
        ``Id`` no topo do ASFF versus ``Id`` dentro de ``Resources[]``). Como o
        artefato é conferido por NOME, um nome é emitível se qualquer conjunto o
        autorizar; o contrário produziria falso positivo.
        """
        return frozenset(column.name for column in self.columns if column.is_generatable)

    @property
    def non_generatable_names(self) -> frozenset[str]:
        """Nomes que NENHUMA ocorrência autoriza a PREENCHER."""
        generatable = self.generatable_names
        return frozenset(
            column.name for column in self.columns if column.name not in generatable
        )

    @property
    def emittable_names(self) -> frozenset[str]:
        """Nomes que podem EXISTIR no artefato (inclui colunas sempre vazias)."""
        return frozenset(column.name for column in self.columns if column.belongs_to_schema)

    @property
    def non_emittable_names(self) -> frozenset[str]:
        """Nomes que NENHUMA ocorrência autoriza a existir no artefato."""
        emittable = self.emittable_names
        return frozenset(
            column.name for column in self.columns if column.name not in emittable
        )

    @property
    def null_empty_names(self) -> frozenset[str]:
        """Colunas que pertencem ao formato mas nao podem receber valor.

        Emiti-las e obrigatorio; preenche-las e violacao. Sao coisas diferentes e
        o modelo precisa das duas.
        """
        return frozenset(
            column.name
            for column in self.columns
            if column.belongs_to_schema and not column.is_generatable
        )

    @property
    def forbidden_names(self) -> frozenset[str]:
        """Nomes que o gerador nao pode emitir: sem evidencia documental suficiente."""
        return self.non_emittable_names | frozenset(self.unverified)

    @property
    def generatable_count(self) -> int:
        """Quantidade de COLUNAS geraveis (nao de nomes distintos)."""
        return sum(1 for column in self.columns if column.is_generatable)

    @property
    def non_generatable_count(self) -> int:
        """Quantidade de COLUNAS descritas sem contrato suficiente."""
        return sum(1 for column in self.columns if not column.is_generatable)

    @property
    def emittable_count(self) -> int:
        """Quantidade de COLUNAS que pertencem ao formato."""
        return sum(1 for column in self.columns if column.belongs_to_schema)

    @property
    def schema_published(self) -> bool:
        """Falso quando a propria especificacao registra que o provedor nao publica schema."""
        return bool(self.columns)


def _require(mapping: dict[str, Any], key: str, where: str) -> Any:
    if key not in mapping or mapping[key] in (None, "", [], {}):
        raise SpecError(f"{where}: campo obrigatorio ausente ou vazio: {key!r}")
    return mapping[key]


def _parse_column(raw: Any, where: str, scope: str | None = None) -> Column:
    if not isinstance(raw, dict):
        raise SpecError(f"{where}: cada coluna precisa ser um objeto JSON")
    name = str(_require(raw, "name", where))
    # ``type`` NAO e obrigatorio: quando o provedor nao publica o tipo, a
    # ausencia e a informacao correta. A coluna fica apenas nao geraVEL.
    type_name = raw.get("type")
    status = str(raw.get("status", STATUS_VERIFIED)).strip().lower()
    if status not in _KNOWN_STATUSES:
        raise SpecError(
            f"{where}: coluna {name!r} tem status invalido: {status!r}. "
            f"Use {' ou '.join(sorted(_KNOWN_STATUSES))}; qualifique a nuance em 'evidence'."
        )
    source_url = raw.get("source_url")
    if status == STATUS_VERIFIED and not source_url:
        raise SpecError(
            f"{where}: coluna {name!r} esta marcada como verificada mas nao cita "
            "source_url -- sem a URL da documentacao oficial a coluna nao entra"
        )
    evidence = raw.get("evidence")
    type_source = str(raw["type_source"]).strip().lower() if raw.get("type_source") else None
    if type_source == TYPE_SOURCE_FORMAT_OBSERVED and (evidence or "").lower() not in _GENERATABLE_EVIDENCE:
        raise SpecError(
            f"{where}: coluna {name!r} declara type_source='format-observed', mas o proprio "
            f"campo nao esta declarado (evidence={evidence!r}). Nao se deriva a forma de um "
            "exemplo para um campo que so existe no exemplo."
        )
    return Column(
        name=name,
        type=str(type_name) if type_name else None,
        required=bool(raw.get("required", False)),
        status=status,
        unit=raw.get("unit"),
        source_url=str(source_url) if source_url else None,
        evidence=str(evidence) if evidence else None,
        scope=str(raw["scope"]) if raw.get("scope") else scope,
        type_source=type_source,
        type_note=str(raw["type_note"]) if raw.get("type_note") else None,
    )


def _parse_set(raw: Any, where: str) -> ColumnSet:
    if not isinstance(raw, dict):
        raise SpecError(f"{where}: cada conjunto precisa ser um objeto JSON")
    name = str(raw.get("name", "")).strip()
    columns_raw = raw.get("columns")
    if not isinstance(columns_raw, list) or not columns_raw:
        raise SpecError(f"{where}: o conjunto {name!r} precisa de 'columns' nao vazio")
    columns = tuple(_parse_column(item, f"{where}[{name}]", scope=name or None) for item in columns_raw)
    return ColumnSet(
        name=name,
        description=raw.get("description"),
        columns=columns,
    )


def _check_duplicates(columns: tuple[Column, ...], where: str) -> None:
    duplicated = sorted(key for key, count in Counter(column.key for column in columns).items() if count > 1)
    if duplicated:
        rendered = ", ".join(f"{name!r}" + (f" (scope={scope!r})" if scope else "") for scope, name in duplicated)
        raise SpecError(
            f"{where}: colunas duplicadas: {rendered}. "
            "Se o mesmo nome existe em contextos distintos, agrupe em 'sets' "
            "ou qualifique a coluna com 'scope'."
        )


def _parse_unverified(raw: Any, where: str) -> UnverifiedField:
    """Aceita string ou objeto, distinguindo campo de lacuna de topico.

    Achatamento com ``str()`` seria um defeito silencioso: o nome do campo se
    perderia dentro do ``repr`` do dicionario, e o campo registrado como nao
    comprovado passaria a ser acusado como INVENTADO -- acusacao mais grave e
    errada -- alem de escapar da checagem de sobreposicao.
    """
    if isinstance(raw, str):
        name = raw.strip()
        if not name:
            raise SpecError(f"{where}: entrada vazia em 'unverified'")
        return UnverifiedField(name=name, reason=None)

    if isinstance(raw, dict):
        reason = raw.get("reason") or raw.get("note") or raw.get("detail")
        reason_text = str(reason) if reason else None

        for key in _FIELD_KEYS:
            value = raw.get(key)
            if isinstance(value, str) and value.strip():
                return UnverifiedField(name=value.strip(), reason=reason_text, kind=UNVERIFIED_FIELD)

        for key in _TOPIC_KEYS:
            value = raw.get(key)
            if isinstance(value, str) and value.strip():
                alvo = raw.get("target")
                detalhe = f"{value.strip()} [{alvo}]" if isinstance(alvo, str) and alvo else value.strip()
                return UnverifiedField(name=detalhe, reason=reason_text, kind=UNVERIFIED_TOPIC)

        raise SpecError(
            f"{where}: entrada de 'unverified' sem nome de campo "
            f"({'/'.join(_FIELD_KEYS)}) nem topico ({'/'.join(_TOPIC_KEYS)}): {raw!r}"
        )

    raise SpecError(
        f"{where}: 'unverified' aceita string ou objeto com nome; "
        f"veio {type(raw).__name__}"
    )


def load_spec(path: Path) -> SurfaceSpec:
    """Carrega e valida uma especificacao ``*.schema.json``."""
    if not path.is_file():
        raise SpecError(f"especificacao nao encontrada: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SpecError(f"{path}: JSON invalido: {exc}") from exc
    if not isinstance(raw, dict):
        raise SpecError(f"{path}: a raiz da especificacao precisa ser um objeto JSON")

    sets_raw = raw.get("sets")
    columns_raw = raw.get("columns")

    if sets_raw is None and columns_raw is None:
        raise SpecError(
            f"{path}: informe 'columns' (esquema unico) ou 'sets' (varios esquemas); "
            "use [] se o provedor nao publica schema."
        )

    sets: list[ColumnSet] = []
    if sets_raw is not None:
        if not isinstance(sets_raw, list):
            raise SpecError(f"{path}: 'sets' precisa ser uma lista")
        sets = [_parse_set(item, str(path)) for item in sets_raw]
    elif columns_raw is not None:
        if not isinstance(columns_raw, list):
            raise SpecError(f"{path}: 'columns' precisa ser uma lista")
        columns = tuple(_parse_column(item, str(path)) for item in columns_raw)
        sets = [ColumnSet(name="", description=None, columns=columns)]

    for column_set in sets:
        _check_duplicates(column_set.columns, str(path))
    # O mesmo nome pode reaparecer em conjuntos diferentes: e o que 'sets' existe
    # para representar. Dentro de um conjunto, a unicidade e obrigatoria.

    unverified_raw = raw.get("unverified", [])
    if not isinstance(unverified_raw, list):
        raise SpecError(f"{path}: 'unverified' precisa ser uma lista")

    spec = SurfaceSpec(
        surface=str(_require(raw, "surface", str(path))),
        provider=str(_require(raw, "provider", str(path))),
        reference=dict(raw.get("reference") or {}),
        delivery=dict(raw.get("delivery") or {}),
        sets=tuple(sets),
        unverified_fields=tuple(_parse_unverified(item, str(path)) for item in unverified_raw),
        path=path,
    )
    for problem in validate_spec(spec):
        raise SpecError(problem)
    return spec


def validate_spec(spec: SurfaceSpec) -> list[str]:
    """Devolve os problemas estruturais da especificacao (vazio = valida)."""
    problems: list[str] = []
    where = spec.surface or "<sem surface>"

    reference = spec.reference
    for key in ("title", "url", "consulted_at"):
        if not reference.get(key):
            problems.append(f"{where}: 'reference.{key}' e obrigatorio (evidencia da doc oficial)")

    overlapping = sorted(set(spec.names) & set(spec.unverified))
    if overlapping:
        problems.append(f"{where}: nomes em 'sets/columns' e em 'unverified' ao mesmo tempo: {overlapping}")

    # Coluna obrigatoria PRECISA de status verificado. `required` significa
    # "sempre presente no export", e presenca e o que `status: verified` afirma --
    # nao o tipo, que uma coluna pode nao ter publicado (a tabela de findings do
    # SCC tem `source_id` sempre presente sem tipo divulgado). O que NAO pode
    # existir e exigir presenca de um campo que a propria spec registra como nao
    # comprovado: emitir viraria "campo nao comprovado" e omitir viraria "coluna
    # obrigatoria ausente", deixando qualquer artefato irremediavelmente invalido.
    # Aconteceu com x_InvoiceIssuerId e x_SkuTerm.
    for column in spec.columns:
        if column.required and column.status != STATUS_VERIFIED:
            problems.append(
                f"{where}: coluna {column.name!r} e obrigatoria mas tem status "
                f"{column.status!r} -- presenca exigida de campo nao comprovado. Nenhum artefato "
                "pode satisfazer as duas exigencias."
            )

    if not spec.columns and not spec.unverified_fields:
        problems.append(
            f"{where}: especificacao vazia. Se o provedor nao publica schema, registre o "
            "motivo em 'unverified'; caso contrario, liste as colunas."
        )

    return problems


def load_all_specs(specs_root: Path | None = None) -> tuple[SurfaceSpec, ...]:
    """Carrega todas as especificacoes sob ``specs/<provider>/``."""
    root = specs_root or DEFAULT_SPECS_ROOT
    if not root.is_dir():
        return ()
    specs: list[SurfaceSpec] = []
    for path in sorted(root.glob("*/*.schema.json")):
        specs.append(load_spec(path))
    return tuple(specs)
