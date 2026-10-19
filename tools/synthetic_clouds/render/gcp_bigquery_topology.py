"""GCP official BigQuery billing-export TOPOLOGY renderer (Phase 3, design sec. 4).

Projects the ``CanonicalEstate`` into the full official GCP billing-export topology
as DDL ``CREATE SCHEMA`` / ``CREATE TABLE ... ARRAY<STRUCT<...>>`` + ``INSERT``
scripts plus a ``_provenance.json`` sibling report the Phase-3 provisioner consumes
(``PROVENANCE_FILENAME``: the leading ``_`` keeps metadata keys out of the export's
invention barrier). This supersedes the Phase-1 single-table ``gcp_bigquery`` probe
for container use; that renderer is left untouched (its golden tests pin it).

Hard constraints realized here (DISCOVERY Spike + design sec. 4.2):
  * every REPEATED column is declared ``ARRAY<STRUCT<...>>``; every record column
    is ``STRUCT<...>`` -- the spike proved the goccy emulator only exposes
    ``UNNEST``-able arrays when provisioned via DDL, never ``--data-from-yaml``.
  * ``credits``/``labels``/``system_labels``/``project.labels`` -> ``ARRAY<STRUCT>``.
  * ``service``/``sku``/``project``/``location``/``usage``/``invoice``/
    ``adjustment_info``/``price``/``resource`` -> ``STRUCT``.
  * timestamps -> ``TIMESTAMP``; ``cost``/``cost_at_list``/
    ``currency_conversion_rate`` -> ``FLOAT64``; ``invoice.month`` -> STRING YYYYMM.

Schema provenance -- spec-driven, never hand-written:
  * the column set of each documented GCP billing table is DERIVED from
    ``specs/gcp/*.schema.json`` through ``fidelity.spec.load_spec`` (the normative
    reader): ``gcp_billing_export_v1_*`` from ``billing-export-standard`` (71
    fields), ``gcp_billing_export_resource_v1_*`` from ``billing-export-detailed``
    (77), ``cloud_pricing_export`` from ``billing-export-pricing`` (37). A column
    block can no longer drift from the documentation by hand, and the row shape is
    built from the same tree, so a row carries exactly the documented field names.
  * the DOTTED SPEC PATH is the compared level: ``project`` AND
    ``project.labels.key`` are both columns, which is why the standard table has
    71 documented fields over 26 top-level names. The fidelity test parses the
    DELIVERED ``02_tables.sql`` back into those dotted paths and compares the set
    with ``spec.emittable_names``; it also checks the nested path set of
    ``08_rows_standard.json`` / ``09_rows_resource.json`` is a subset of the spec
    and every required path is present.
  * a record the spec documents only through its SUBFIELDS (``service.id``
    without a ``service`` row: service, sku, invoice, usage, location on the usage
    tables; service, sku on the pricing table) is a STRUCTURAL CONTAINER: BigQuery
    cannot declare the subfields without declaring the record that hosts them, so
    the container is synthesized (``SpecField.documented is False``) and never
    invents a subfield. The fidelity test asserts the declared-but-undocumented
    set is EXACTLY the minimal prefix closure of the documented paths.
  * the spec's ``type`` vocabulary does not distinguish a REPEATED record from a
    nullable one, so the repeated records are pinned in :data:`_REPEATED_RECORDS`
    (spec gap, reported) and asserted against the spec by the fidelity test; a
    record the spec lists WITHOUT subfields stays an opaque leaf, never an
    invented ``STRUCT<...>`` (see :data:`_OPAQUE_RECORD_BQ_TYPE`).
  * ``sku.id`` carries the IDENTIFIER of the resource's SKU on all three tables --
    the same :func:`~tools.synthetic_clouds.model.identity.gcp_sku_id` mint for the
    usage rows and for ``cloud_pricing_export`` -- because the pricing spec documents
    ``sku.id`` as the JOIN KEY between them. The service CATEGORY (``Compute``) is not
    an identifier: it collapsed ``gcp-ce-e2-standard-2`` and ``gcp-ce-n2-standard-4``
    into one value and left the join open.
  * value absence is ``None``/``NULL`` for numbers and booleans (``""``/``[]`` for text
    and lists): zero is a legitimate value in the fidelity core, so writing ``0.0`` into
    a price nobody modelled would assert it is free.

Row sourcing (design sec. 4.3):
  * ``BillingLine`` Usage/Purchase -> ``cost_type="regular"`` with ``credits[]``.
  * ``BillingLine`` Adjustment (C17) -> ``cost_type="adjustment"``, ``credits=[]``,
    later ``export_time`` (already set in the estate).
  * ``estate.taxes`` -> dedicated ``cost_type="tax"`` rows (NOT a charge_category).
  * M1 defensive rule: any GCP line whose ``charge_category`` is not in
    ``{Usage, Purchase, Adjustment}`` raises ``RenderError`` (fail loud).

Credits projection (design sec. 4.3.1): per-scope ``Credit`` joined to its
Usage/Purchase lines, allocated pro-rata by ``billed_cost`` as a NEGATIVE share
(6-dp ROUND_HALF_EVEN, last line absorbs the remainder so
``sum(credits[].amount) == -Credit.amount`` exactly); ``credits[].type`` derived
from the matched ``Commitment.kind`` (GCP is always ``cud``).

GKE label injection (design sec. 4.5, F4/NIT-2): every row where
``k8s_namespace is not None`` gets ``labels[] += {goog-k8s-cluster-name:
<Resource.resource_name>}``, resolved from the line's ``resource_uuid``.

Byte-determinism: GCP lines sorted by ``line_id``; Decimal->FLOAT64 via 6-dp
ROUND_HALF_EVEN then ``float()``; JSON/SQL literals emitted with stable float repr.

``TODO-verificar`` (design sec. 9), never fabricated: the offline-unverifiable
official details are flagged at the point of emission and listed in the
``_provenance.json`` sibling report (``PROVENANCE_FILENAME``).
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from decimal import ROUND_HALF_EVEN, Decimal
from functools import cache
from pathlib import Path
from typing import Any

from tools.synthetic_clouds.fidelity.spec import (
    DEFAULT_SPECS_ROOT,
    EVIDENCE_NULL_EMPTY,
    SpecError,
    SurfaceSpec,
    load_spec,
)
from tools.synthetic_clouds.model.billing import BillingLine
from tools.synthetic_clouds.model.commitments import Credit
from tools.synthetic_clouds.model.compute import InstanceProfile
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.identity import gcp_sku_id
from tools.synthetic_clouds.render.base import RenderError
from tools.synthetic_clouds.render.markers import unmarked_name

_SIX = Decimal("0.000001")
_GCP_PROVIDER = "Google Cloud"
# M1: the only charge_category values a GCP provider line ever carries. A GCP line
# outside this set is a bug (Tax/Credit are side collections, not categories).
_ALLOWED_GCP_CATEGORIES = frozenset({"Usage", "Purchase", "Adjustment"})
# Deterministic UUIDv5 namespace for synthetic row/credit keys (fixed, seedless;
# the inputs already carry the seed via line_id/credit uuid).
_NS = uuid.UUID("1b4e28ba-2fa1-11d2-883f-0016d3cca427")
# Default billing multi-region, used ONLY as the last fallback for a line that carries no
# region at all (every GCP line in the estate does carry one). location.location is the
# USAGE location -- the line's zone when it is zonal, else its region (spec: "global or
# multi-region/country/region/zone"); location.country stays best-effort (TODO-verificar #8).
_DEFAULT_LOCATION = "us"
# INSERT chunk size. Measured against the goccy emulator (v0.3.1) with a 282-day
# small-profile estate: 100 rows of the then-smaller row shape (~166 KB) is accepted, 200
# rows (~333 KB) makes googlesqlite panic with "slice bounds out of range" and the job
# fails closed with jobInternalError. The row tuple grew when the schema became
# spec-derived (every documented field is emitted, ~2.0 KB/row measured): 50 rows is now
# ~100 KB, still under the accepted 166 KB, while 100 rows would be ~197 KB and cross it.
# The provisioner streams the JSON bulk payload instead of these scripts (see
# ``manifest.provision_scripts``); they remain the human-readable record of the same rows.
_INSERT_CHUNK = 50

#: Report-file name, started by ``_`` on purpose: the fidelity auditor
#: (``fidelity.audit_renderers._export_artifacts``) treats a ``_``-prefixed file as a
#: SIBLING REPORT and keeps it out of the invention barrier. The manifest is metadata
#: ABOUT the export (spec provenance, row counts, TODOs) -- no cloud documents those keys
#: as columns -- so inside the export tree they were, correctly, reported as invented.
PROVENANCE_FILENAME = "_provenance.json"


def _to_float(value: Decimal) -> float:
    """Quantize to 6-dp (banker's rounding) then cast to FLOAT64 (byte-determinism)."""
    return float(value.quantize(_SIX, ROUND_HALF_EVEN))


def _q(value: Decimal) -> Decimal:
    """Quantize a Decimal to FOCUS 6-dp (banker's rounding)."""
    return value.quantize(_SIX, ROUND_HALF_EVEN)


def _month(day: date) -> str:
    """Return the ``YYYYMM`` invoice-month string for ``day``."""
    return f"{day.year:04d}{day.month:02d}"


def _next_month_first(day: date) -> date:
    """Return the first day of the month following ``day``."""
    if day.month == 12:
        return date(day.year + 1, 1, 1)
    return date(day.year, day.month + 1, 1)


def _row_uuid(key: str) -> str:
    """Return a deterministic UUIDv5 string for ``key`` (byte-stable row keys)."""
    return str(uuid.uuid5(_NS, key))


def _labels(pairs: tuple[tuple[str, str], ...]) -> list[dict[str, str]]:
    """Project a FOCUS list-of-(key,value) into ARRAY<STRUCT<key,value>> dicts."""
    return [{"key": k, "value": v} for k, v in pairs]


def _country_from_region(region_id: str) -> str:
    """Best-effort country from a GCP region prefix (TODO-verificar #8).

    The official country mapping table is offline-unverifiable; this derives a
    plausible ISO-ish country from the region's leading segment (e.g.
    ``us-central1`` -> ``US``, ``europe-west1`` -> ``EU``,
    ``southamerica-east1`` -> ``BR``). No current consumer reads this field.
    """
    prefix = region_id.split("-", 1)[0].lower()
    mapping = {
        "us": "US",
        "europe": "EU",
        "asia": "AS",
        "southamerica": "BR",
        "northamerica": "CA",
        "australia": "AU",
        "me": "ME",
        "africa": "ZA",
    }
    return mapping.get(prefix, "")


# -- spec-derived schema -----------------------------------------------------------
#
# specs/ is the source of truth (specs/README.md) and this module never edits it. Each
# documented table is derived from ONE surface spec through ``fidelity.spec.load_spec``,
# so a hand-written column block cannot drift from the documentation in silence. The
# compared level is the DOTTED SPEC PATH (see the module docstring).

#: Surface -> spec file, relative to ``specs/``.
_SPEC_FILE_BY_SURFACE: dict[str, str] = {
    "standard": "gcp/billing-export-standard.schema.json",
    "detailed": "gcp/billing-export-detailed.schema.json",
    "pricing": "gcp/billing-export-pricing.schema.json",
}

#: Spec ``type`` -> BigQuery DDL type, for the scalar (non-record) types the three GCP
#: billing surfaces declare. Records and arrays are structural: see :func:`_ddl_type`.
_BQ_SCALAR_TYPES: dict[str, str] = {
    "String": "STRING",
    "Timestamp": "TIMESTAMP",
    "Float": "FLOAT64",
    "Numeric": "NUMERIC",
    "Boolean": "BOOL",
    "Date": "DATE",
}
_ARRAY_OF_STRINGS = "Array of Strings"
_LIST_OF_STRUCTS = "List of structs"
_RECORD_TYPES = frozenset({"Struct", _LIST_OF_STRUCTS})

#: A record the spec lists WITHOUT subfields cannot become ``STRUCT<>`` (BigQuery
#: refuses a fieldless record) and this project does not invent subfields -- the spec
#: marks exactly those subfields UNVERIFIED. Such a column is declared as an opaque
#: leaf, keeping the documented NAME without asserting a structure the documentation
#: does not state. All four occurrences are in ``cloud_pricing_export``
#: (``list_price``, ``billing_account_price``, ``consumption_model_prices.list_price``,
#: ``consumption_model_prices.billing_account_price``); the fidelity test asserts the
#: set is exactly the spec's fieldless records.
_OPAQUE_RECORD_BQ_TYPE = "STRING"

#: Record columns the official BigQuery schema declares REPEATED (``ARRAY<STRUCT<...>>``).
#: The spec's ``type`` vocabulary records these as plain ``Struct``: it does not
#: distinguish a REPEATED record from a nullable one (a spec gap, reported). Pinned here
#: explicitly -- never inferred -- and the fidelity test asserts every member is a spec
#: record with documented subfields. The pricing surface needs no entry: its repeated
#: fields are declared "Array of Strings" / "List of structs".
_REPEATED_RECORDS: frozenset[str] = frozenset(
    {"labels", "system_labels", "project.labels", "project.ancestors", "credits", "tags"}
)

#: Field names zetasql reserves: declared/aliased backtick-quoted. ``resource`` is a real
#: column of the detailed export AND a reserved word, so it keeps its name only quoted.
_RESERVED_FIELD_NAMES: frozenset[str] = frozenset({"resource"})

# ``_PARTITIONTIME`` is a BigQuery pseudo-column auto-provided for partitioned tables; it
# is NOT declarable in DDL (the emulator's go-zetasql rejects it, matching real BigQuery),
# so the tables are emitted non-partitioned. TODO-verificar #6 stands: the spec records the
# partitioning of the standard/detailed tables as UNVERIFIED, so no partitioning clause is
# derived from it (the pricing spec states ``_PARTITIONTIME`` in ``delivery``, which is a
# delivery fact, not a column of the documented schema).


@dataclass(frozen=True, slots=True)
class SpecField:
    """Um campo da tabela derivado da spec: caminho pontuado, tipo, filhos, repetição.

    ``documented`` distingue o campo que a spec LISTA como coluna própria do CONTÊINER
    ESTRUTURAL que o formato exige. A spec documenta ``service.id``/``service.description``
    sem uma linha própria para ``service``; um DDL do BigQuery, porém, não tem como
    declarar os subcampos sem declarar o record que os hospeda. Um contêiner desses é
    sintetizado (``documented=False``) e nunca inventa subcampo: os filhos continuam sendo
    exatamente os caminhos que a spec documenta.

    ``null_empty`` é o outro lado da mesma distinção do núcleo: uma coluna com
    ``evidence: null-empty`` PERTENCE ao formato e nunca tem valor. Ela é declarada no DDL
    (``belongs_to_schema``) e emitida como ``None`` -- preenchê-la seria infiel ao
    contrato, omiti-la seria infiel ao formato.
    """

    name: str
    type: str
    children: tuple[SpecField, ...]
    repeated: bool
    documented: bool
    null_empty: bool = False

    @property
    def leaf(self) -> str:
        """Nome no nível em que o campo é declarado (último segmento do caminho)."""
        return self.name.rsplit(".", 1)[-1]

    @property
    def is_opaque_record(self) -> bool:
        """Record cujos subcampos a spec NÃO enumera: não se inventa estrutura."""
        return not self.children and self.type in _RECORD_TYPES

    @property
    def ddl_type(self) -> str:
        """Tipo DDL BigQuery derivado do ``type`` documentado."""
        return _ddl_type(self)


def _load_billing_spec(surface: str) -> SurfaceSpec:
    """Carrega a spec normativa da superfície; falha FECHADO se ela não servir."""
    filename = _SPEC_FILE_BY_SURFACE.get(surface)
    if filename is None:
        raise RenderError(f"unknown billing surface {surface!r}; known: {sorted(_SPEC_FILE_BY_SURFACE)}")
    path = DEFAULT_SPECS_ROOT / filename
    try:
        return load_spec(path)
    except SpecError as exc:
        raise RenderError(f"{path}: {exc}") from exc


@cache
def fields_for(surface: str) -> tuple[SpecField, ...]:
    """Campos de topo da superfície (com os filhos da spec), na ordem da documentação.

    A árvore é derivada dos CAMINHOS da spec. Um caminho cujo pai a spec não lista (ex.:
    ``service.id`` sem uma linha ``service``) não é descartado: o pai é sintetizado como
    contêiner estrutural, senão o campo documentado sumiria da tabela em silêncio.
    """
    spec = _load_billing_spec(surface)
    by_name = {column.name: column for column in spec.columns}
    children_of: dict[str, list[str]] = {}
    for name in spec.names:
        children_of.setdefault(name.rpartition(".")[0], []).append(name)
    # Ordem de topo = ordem de primeira aparição do primeiro segmento (a ordem da spec).
    top_level: list[str] = []
    for name in spec.names:
        first = name.split(".", 1)[0]
        if first not in top_level:
            top_level.append(first)

    def build(name: str) -> SpecField:
        column = by_name.get(name)
        return SpecField(
            name=name,
            # Um contêiner sintetizado é um record por construção (ele hospeda filhos).
            type=column.type if column is not None and column.type else "Struct",
            children=tuple(build(child) for child in children_of.get(name, [])),
            repeated=(column is not None and column.type in {_ARRAY_OF_STRINGS, _LIST_OF_STRUCTS})
            or name in _REPEATED_RECORDS,
            documented=column is not None,
            null_empty=column is not None and (column.evidence or "").lower() == EVIDENCE_NULL_EMPTY,
        )

    return tuple(build(name) for name in top_level)


def field_paths(fields: Sequence[SpecField]) -> tuple[str, ...]:
    """Caminhos pontuados de todos os campos, pai antes dos filhos (ordem da spec)."""
    paths: list[str] = []
    for field in fields:
        paths.append(field.name)
        paths.extend(field_paths(field.children))
    return tuple(paths)


def _quote(name: str) -> str:
    return f"`{name}`" if name in _RESERVED_FIELD_NAMES else name


def _ddl_type(field: SpecField) -> str:
    """Tipo DDL BigQuery do campo, derivado do ``type`` da spec (nunca adivinhado)."""
    if field.children:
        struct = "STRUCT<" + ", ".join(f"{_quote(child.leaf)} {_ddl_type(child)}" for child in field.children) + ">"
        return f"ARRAY<{struct}>" if field.repeated else struct
    if field.type == _ARRAY_OF_STRINGS:
        base = "STRING"
    elif field.type in _RECORD_TYPES:
        base = _OPAQUE_RECORD_BQ_TYPE  # subcampos não enumerados pela spec
    elif field.type in _BQ_SCALAR_TYPES:
        base = _BQ_SCALAR_TYPES[field.type]
    else:
        raise RenderError(f"{field.name}: spec type {field.type!r} has no BigQuery DDL mapping")
    return f"ARRAY<{base}>" if field.repeated else base


def ddl_columns(fields: Sequence[SpecField], *, indent: str = "  ") -> str:
    """Bloco de colunas DDL derivado da spec, na ordem da documentação."""
    return ",\n".join(f"{indent}{_quote(field.leaf)} {_ddl_type(field)}" for field in fields)


def insert_column_list(fields: Sequence[SpecField]) -> str:
    """Colunas de um INSERT, na ordem do DDL (a MESMA sequência que os VALUES)."""
    return ", ".join(_quote(field.leaf) for field in fields)


def schema_provenance(surface: str) -> dict[str, Any]:
    """Proveniência da superfície: spec, nível comparado e contagens de colunas.

    ``columns`` conta os CAMINHOS pontuados DOCUMENTADOS (o nível comparado, igual a
    ``len(spec.columns)``); ``top_level`` conta nomes de topo. As duas contagens diferem
    (71 x 26 na standard): um renderer pode acertar o topo e errar o aninhado, então as
    duas ficam visíveis. ``structural_containers`` nomeia os records que a spec documenta
    apenas pelos subcampos e o formato obriga a declarar.
    """
    fields = fields_for(surface)
    spec = _load_billing_spec(surface)
    declared = field_paths(fields)
    documented = tuple(path for path in declared if path in spec.emittable_names)
    return {
        "spec": f"specs/{_SPEC_FILE_BY_SURFACE[surface]}",
        "comparable_level": "dotted spec path (a nested field is a column of its own)",
        "columns": len(documented),
        "top_level": len(fields),
        "structural_containers": sorted(set(declared) - set(documented)),
    }


def _leaf_default(field: SpecField) -> Any:
    """Valor de ausência de um campo sem projeção no estado: ausência é ausência.

    Numérico e booleano sem fonte saem ``None`` (``NULL`` no SQL, ``null`` no payload),
    NUNCA ``0.0``/``False``: o próprio núcleo de fidelidade registra que zero é um valor
    legítimo e distinto de ausência (``artifacts.is_empty_value``), então escrever zero num
    preço sem fonte afirma que ele é zero -- e um consumidor que soma preços lê "de graça".
    Texto continua ``""`` (convenção do projeto para string ausente) e lista, ``[]``. Onde
    zero/um É o valor real (faixa única começa em 0; preço por 1 unidade), o chamador projeta
    o valor explicitamente.
    """
    ddl_type = _ddl_type(field)
    if ddl_type == "STRING":
        return ""
    if ddl_type in {"FLOAT64", "NUMERIC", "BOOL", "DATE"}:
        return None
    if ddl_type == "ARRAY<STRING>":
        return []
    raise RenderError(f"{field.name}: no value projected for a {ddl_type} column; refusing to invent one")


def build_row(fields: Sequence[SpecField], values: Mapping[str, Any]) -> dict[str, Any]:
    """Monta uma linha com EXATAMENTE os campos da spec.

    ``values`` é indexado pelo caminho pontuado da spec (``invoice.month``,
    ``project.labels``). Um caminho sem projeção no estado vira ausência
    (``""``/``0.0``/``False``/``[]``) em vez de sumir da linha: uma linha que omitisse a
    coluna deixaria de espelhar a tabela documentada. Um TIMESTAMP sem valor levanta --
    não se inventa timestamp. Uma coluna ``null-empty`` pertence ao formato e é emitida
    como ``None``; projetar um valor nela levanta, porque a documentação afirma que ela
    nunca tem valor.
    """
    row: dict[str, Any] = {}
    for field in fields:
        if field.null_empty:
            if field.name in values:
                raise RenderError(
                    f"{field.name}: a spec registra a coluna como null-empty (pertence ao "
                    "formato, nunca tem valor); preenchê-la seria infiel ao contrato"
                )
            row[field.leaf] = None
        elif field.name in values:
            row[field.leaf] = values[field.name]
        elif field.children:
            # Um record repetido sem valor é uma lista vazia; um record simples é um
            # objeto aninhado com os filhos da spec (nunca um dict onde cabe uma lista).
            row[field.leaf] = [] if field.repeated else build_row(field.children, values)
        else:
            row[field.leaf] = _leaf_default(field)
    return row


# -- value sources: what the canonical model CAN fill --------------------------------
#
# A column set derived from the spec says which columns exist; it says nothing about which
# of them the state can fill. These are the modelled sources for the optional value
# columns, indexed once per render. Everything NOT sourced here is emitted as absence --
# never as a plausible number -- and is named, with its reason, in ``MODEL_GAPS`` (which
# travels in the ``_provenance.json`` sibling report).

#: Prefixo das system labels geradas pela nuvem. Só a que o modelo sustenta é projetada:
#: o machine type do recurso é exatamente o valor que ``compute.googleapis.com/machine_spec``
#: carrega (a chave consta de ``allowed_values`` da spec).
_MACHINE_SPEC_LABEL = "compute.googleapis.com/machine_spec"


@dataclass(frozen=True, slots=True)
class _ValueSources:
    """Índices do estado para os campos de valor opcionais."""

    sku_by_resource: Mapping[str, str | None]
    list_price_by_sku: Mapping[str, Decimal]
    contracted_price_by_sku: Mapping[str, Decimal]
    profile_by_resource: Mapping[str, InstanceProfile]
    ancestry_by_project: Mapping[str, str]
    service_by_sku: Mapping[str, str]
    sku_unit_by_sku: Mapping[str, str]


def _value_sources(estate: CanonicalEstate) -> _ValueSources:
    """Indexa catálogos, perfis de instância e a hierarquia GCP, uma vez por render."""
    ancestry: dict[str, str] = {}
    for org in estate.gcp_orgs:
        org_number = org.org_id.rpartition("/")[2] or org.org_id
        for folder in org.folders:
            folder_number = folder.folder_id.rpartition("/")[2] or folder.folder_id
            for project in folder.projects:
                # Formato documentado de project.ancestry_numbers: /orgNumber/folderNumber/.
                ancestry[project.project_id] = f"/{org_number}/{folder_number}/"
    # SKU -> serviço, a partir dos recursos GCP (o catálogo de preços não carrega serviço).
    service_by_sku: dict[str, str] = {}
    for resource in estate.resources:
        if resource.identity.provider != "gcp" or not resource.sku_id:
            continue
        service_by_sku.setdefault(resource.sku_id, resource.service_name)
    return _ValueSources(
        sku_by_resource={resource.identity.uuid: resource.sku_id for resource in estate.resources},
        list_price_by_sku={price.sku_id: price.unit_price for price in estate.list_prices},
        contracted_price_by_sku={price.sku_id: price.unit_price for price in estate.contracted_prices},
        profile_by_resource={
            profile.resource_uuid: profile for profile in estate.instance_profiles if profile.provider == "gcp"
        },
        ancestry_by_project=ancestry,
        service_by_sku=service_by_sku,
        sku_unit_by_sku={price.sku_id: price.unit for price in estate.list_prices},
    )


def _conversion_rate(estate: CanonicalEstate) -> float | None:
    """Taxa USD -> moeda da conta, ou ``None`` quando o estado não a modela.

    O estado só a preenche quando a moeda não é USD (``model/estate.py``). Para uma conta
    em USD a taxa é 1.0 POR DEFINIÇÃO -- a própria spec de pricing declara "``1.0`` quando
    ``account_currency_code`` = ``USD``" --, então esse 1.0 é valor real, não ausência.
    Para qualquer outra moeda sem taxa modelada, a resposta honesta é ausência (``None``).
    """
    if estate.currency_conversion_rate is not None:
        return _to_float(estate.currency_conversion_rate)
    if estate.currency == "USD":
        return 1.0
    return None


def _zone_for(line: BillingLine, sources: _ValueSources) -> str:
    """Zona da linha, quando o recurso é zonal E a zona pertence à região da linha.

    A doc condiciona ``location.zone`` a ``location.location`` ser uma zona. Uma zona de
    OUTRA região não é a localização desta linha, então não é afirmada (ausência).
    """
    profile = sources.profile_by_resource.get(line.resource_uuid or "")
    if profile is None or not profile.zone:
        return ""
    if line.region_id and profile.zone.startswith(f"{line.region_id}-"):
        return profile.zone
    return ""


def _machine_spec_for(line: BillingLine, sources: _ValueSources) -> str:
    """Machine type do recurso da linha (valor de ``compute.googleapis.com/machine_spec``)."""
    profile = sources.profile_by_resource.get(line.resource_uuid or "")
    if profile is None or not profile.instance_type:
        return ""
    return profile.instance_type


#: Motivo, por caminho documentado, de o renderer NUNCA preencher a coluna. O teste de
#: fidelidade confronta esta lista com os artefatos nos DOIS sentidos (toda coluna vazia em
#: todas as linhas está aqui; toda coluna aqui está vazia), então ela não envelhece em
#: silêncio quando o modelo ganhar uma fonte. Coluna vazia apenas por FALTA DE DADO na
#: execução (ex.: ``adjustment_info.*`` sem linha de ajuste) não entra: a fonte existe.
_GAP_REASONS: dict[str, str] = {
    "project.number": "o estado modela project_id, não o number interno do projeto",
    "project.ancestors": (
        "o formato exige resourceType/resourceNumber por ancestral e um display_name por pasta/org; "
        "o number do projeto e os nomes de pasta/org não são modelados"
    ),
    "project.ancestors.resource_name": "idem project.ancestors (o number do projeto não é modelado)",
    "project.ancestors.display_name": "idem project.ancestors (o nome de pasta/org não é modelado)",
    "sku.description": (
        "a doc pede a descrição do tipo de recurso (ex.: 'Standard Storage US'); o estado modela o token "
        "do SKU (identificador), o nome do serviço (que descreve o serviço) e a categoria (que não é "
        "descrição) -- nenhum é a descrição do tipo de recurso"
    ),
    "tags": (
        "GCP tags (namespace + herança) são um conceito próprio; o estado modela FOCUS Tags, "
        "já projetados em labels/project.labels"
    ),
    "tags.key": "idem tags",
    "tags.value": "idem tags",
    "tags.inherited": "idem tags",
    "tags.namespace": "idem tags",
    "transaction_type": "o estado não modela venda por revendedor/agência, e a doc não fixa o literal da coluna",
    "seller_name": "o estado não modela vendedor de Marketplace",
    "consumption_model.id": "a doc não publica a lista de ids de consumption model e o estado não modela um",
    "consumption_model.description": "idem consumption_model.id",
    "subscription.instance_id": "o estado não modela subscriptions (Commitment é um CUD, não uma subscription)",
    "consumption_model.applied_subscription_instance_id": "idem subscription.instance_id",
    # -- cloud_pricing_export ---------------------------------------------------------
    "sku.destination_migration_mappings": "o estado não modela SKUs migrando para outro SKU",
    "product_taxonomy": "o estado não modela a taxonomia de produto (Beta na doc)",
    "geo_taxonomy.type": "o estado não modela a topologia geográfica do SKU (Beta na doc)",
    "geo_taxonomy.regions": "idem geo_taxonomy.type",
    "pricing_unit_description": (
        "a doc pede a forma legível da unidade (ex.: 'gibibyte month'); o catálogo do estado carrega o "
        "token da unidade ('GB-Month'), não uma descrição"
    ),
    "list_price": (
        "a doc diz que este Struct contém aggregation_info e tiered_rates, mas a spec NÃO enumera os "
        "subcampos (registrado como UNVERIFIED) e o BigQuery não declara STRUCT<>; a coluna sai como folha "
        "opaca e o preço de lista é emitido em tiered_rates.usd_amount"
    ),
    "billing_account_price": (
        "idem list_price: Struct sem subcampos enumerados pela spec; o preço contratual do estado não tem "
        "onde ser afirmado sem inventar a estrutura"
    ),
    "consumption_model_prices": "o estado não modela preço por modelo de consumo",
    "consumption_model_prices.consumption_model_id": "idem consumption_model_prices",
    "consumption_model_prices.consumption_model_display_name": "idem consumption_model_prices",
    "consumption_model_prices.list_price": "idem consumption_model_prices",
    "consumption_model_prices.billing_account_price": "idem consumption_model_prices",
    "price_info.price_reason": "a doc só define price_reason para preço contratual tipado; o estado não modela a origem",
    "price_info.discount_percent": (
        "a doc condiciona este campo a preço contratual resultante de desconto PERCENTUAL "
        "(FIXED_DISCOUNT/FLOATING_DISCOUNT); o preço contratual do estado é um preço fixo por unidade"
    ),
    "price_info.discount_percent_fixed_date": "idem price_info.discount_percent",
    "price_info.discount_migrated_from": "idem price_info.price_reason (o estado não modela migração)",
}
_GAP_DEFAULT = "o estado canônico não modela este dado"


def model_gaps(surface: str) -> dict[str, str]:
    """Colunas documentadas SEM fonte no modelo, com o motivo (vai para a proveniência)."""
    spec = _load_billing_spec(surface)
    return {name: _GAP_REASONS.get(name, _GAP_DEFAULT) for name in spec.names if name in _GAP_REASONS}


def _create_schema(dataset: str, project: str) -> str:
    return f"CREATE SCHEMA IF NOT EXISTS `{project}.{dataset}`;"


def _create_table(fqtn: str, fields: Sequence[SpecField], *, note: str) -> str:
    """``CREATE TABLE`` com o bloco de colunas DERIVADO da spec, precedido de ``note``.

    ``note`` é comentário ``--`` de linha própria: o provisioner remove comentários antes
    de submeter, e um comentário no fim de uma linha de coluna engoliria a vírgula
    seguinte.
    """
    return f"{note}CREATE TABLE `{fqtn}` (\n{ddl_columns(fields)}\n);"


def _create_standard_table(fqtn: str) -> str:
    return _create_table(
        fqtn,
        fields_for("standard"),
        note=(
            "-- gcp_billing_export_v1_*: 71 fields derived from "
            "specs/gcp/billing-export-standard.schema.json\n"
            "-- (dotted paths: nested levels are columns of the same comparison).\n"
        ),
    )


def _create_resource_table(fqtn: str) -> str:
    # gcp_billing_export_resource_v1_* = the DETAILED surface (77 fields). The spec
    # declares itself a superset of the standard one, so it is used standalone rather
    # than concatenated to a hand-written standard block. ``resource`` is a zetasql
    # reserved word and stays backtick-quoted (the column is literally named `resource`).
    return _create_table(
        fqtn,
        fields_for("detailed"),
        note=(
            "-- gcp_billing_export_resource_v1_*: 77 fields derived from "
            "specs/gcp/billing-export-detailed.schema.json\n"
            "-- (6 exclusive of the detailed export: resource*, subscription*, "
            "consumption_model.applied_subscription_instance_id).\n"
        ),
    )


def _create_pricing_table(fqtn: str) -> str:
    return _create_table(
        fqtn,
        fields_for("pricing"),
        note=(
            "-- cloud_pricing_export: 37 fields derived from "
            "specs/gcp/billing-export-pricing.schema.json. ROWS come from the estate's SKU\n"
            "-- catalogue (one per GCP SKU), with the SAME sku.id minted for the usage tables, so\n"
            "-- the documented join (sku.id, tier_start_amount = start_usage_amount) closes\n"
            "-- (TODO-verificar #5 now covers the CUD schema only).\n"
        ),
    )


def _create_cud_table(fqtn: str) -> str:
    # TODO-verificar #5: cud_subscriptions_export exact schema is offline-unverifiable.
    return (
        f"CREATE TABLE `{fqtn}` (\n"
        "  commitment_id STRING,\n"
        "  subscription STRUCT<name STRING, plan STRING, status STRING>,\n"
        "  scope_id STRING,\n"
        "  plan STRING,\n"
        "  start_time TIMESTAMP,\n"
        "  end_time TIMESTAMP,\n"
        "  status STRING\n"
        ");"
    )


def _create_focus_table(fqtn: str) -> str:
    # TODO-verificar #4: GCP FOCUS billing-export column set is offline-unverifiable.
    # Emitted best-effort with a minimal FOCUS 1.x-shaped column block; left empty.
    return (
        f"CREATE TABLE `{fqtn}` (\n"
        "  BilledCost FLOAT64,\n"
        "  BillingAccountId STRING,\n"
        "  BillingCurrency STRING,\n"
        "  ChargeCategory STRING,\n"
        "  ServiceName STRING,\n"
        "  BillingPeriodStart TIMESTAMP,\n"
        "  BillingPeriodEnd TIMESTAMP\n"
        ");"
    )


def _create_invoice_table(fqtn: str) -> str:
    """DDL for the official ``invoice`` table (invoice side of the export).

    Cloud Billing provisions this table alongside the usage tables: one row
    per issued invoice per billing account. Without it a billing simulator
    can reproduce usage but has nowhere to express the **invoice** -- the
    very thing an app reconciles against.

    ``cost`` is a STRUCT in the official schema (amount + currency), not a
    bare FLOAT64; kept as-is so a consumer written against the real table
    parses these rows unchanged.
    """
    return (
        f"CREATE TABLE `{fqtn}` (\n"
        "  billing_account_id STRING,\n"
        "  service STRUCT<description STRING>,\n"
        "  sku STRUCT<description STRING>,\n"
        "  invoice_id STRING,\n"
        "  invoice_month STRING,\n"
        "  invoice_date TIMESTAMP,\n"
        "  due_date TIMESTAMP,\n"
        "  total_amount FLOAT64,\n"
        "  currency STRING,\n"
        "  cost STRUCT<amount FLOAT64, currency STRING>,\n"
        "  status STRING,\n"
        "  name STRING\n"
        ");"
    )


def _create_invoice_line_item_table(fqtn: str) -> str:
    """DDL for the official ``invoice_line_item`` table.

    One row per charge that appears on an invoice -- the detailed, invoiced
    counterpart of the usage tables. ``item_type`` is the documented
    discriminator ('SKU', 'Tax', 'Adjustment', 'Rounding') and is what lets a
    consumer roll a line item up into an invoice total without re-deriving it.
    """
    return (
        f"CREATE TABLE `{fqtn}` (\n"
        "  billing_account_id STRING,\n"
        "  service STRUCT<id STRING, description STRING>,\n"
        "  sku STRUCT<id STRING, description STRING>,\n"
        "  id STRING,\n"
        "  invoice_id STRING,\n"
        "  invoice_month STRING,\n"
        "  cost_type STRING,\n"
        "  usage_start_time TIMESTAMP,\n"
        "  usage_end_time TIMESTAMP,\n"
        "  description STRING,\n"
        "  currency STRING,\n"
        "  amount FLOAT64,\n"
        "  tax_amount FLOAT64,\n"
        "  pricing_unit STRING,\n"
        "  pricing_amount FLOAT64,\n"
        "  pricing_rate FLOAT64,\n"
        "  credits ARRAY<STRUCT<name STRING, amount FLOAT64>>,\n"
        "  cost FLOAT64,\n"
        "  item_type STRING,\n"
        "  adjustment_id STRING,\n"
        "  adjustment_type STRING,\n"
        "  adjustment_description STRING\n"
        ");"
    )


# -- SQL literal emission (deterministic) ------------------------------------------


def _sql_str(value: str) -> str:
    """Return a single-quoted SQL string literal with quotes/backslashes escaped."""
    escaped = value.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"


def _sql_ts(value: datetime) -> str:
    """Return a ``TIMESTAMP('...')`` literal in UTC ISO form."""
    return f"TIMESTAMP({_sql_str(value.astimezone(UTC).isoformat())})"


def _sql_float(value: float) -> str:
    """Return a stable FLOAT64 literal (CPython stable float repr)."""
    return repr(value)


def _sql_struct(children: Sequence[SpecField], mapping: Mapping[str, Any]) -> str:
    """Return a ``STRUCT(... AS field)`` literal for one record value."""
    parts = [f"{_sql_literal(child, mapping[child.leaf])} AS {_quote(child.leaf)}" for child in children]
    return "STRUCT(" + ", ".join(parts) + ")"


def _sql_literal(field: SpecField, value: Any) -> str:
    """Return the SQL literal of ``value`` for ``field``, driven by the SPEC type.

    Every branch is keyed on the documented ``type`` (through :func:`_ddl_type`), so a
    column whose documentation changes type cannot keep being emitted the old way: an
    unmapped type raises instead of being coerced into a plausible literal.
    """
    if field.null_empty:
        # Pertence ao formato e nunca tem valor: NULL, nunca um literal preenchido.
        return "NULL"
    if value is None:
        # Ausência explícita (fonte opcional sem valor para ESTA linha): NULL.
        return "NULL"
    if field.children:
        if field.repeated:
            items = list(value or [])
            if not items:
                return f"CAST([] AS {_ddl_type(field)})"
            return "[" + ", ".join(_sql_struct(field.children, item) for item in items) + "]"
        return _sql_struct(field.children, value)
    if field.type == _ARRAY_OF_STRINGS:
        items = [str(item) for item in (value or [])]
        if not items:
            return "CAST([] AS ARRAY<STRING>)"
        return "[" + ", ".join(_sql_str(item) for item in items) + "]"
    if field.type in _RECORD_TYPES:
        # Opaque record: declared as a leaf by _ddl_type (spec does not enumerate it).
        return _sql_str(str(value or ""))
    if field.type == "String":
        return _sql_str(str(value))
    if field.type == "Timestamp":
        return _sql_ts(value)
    if field.type == "Float":
        return _sql_float(float(value))
    if field.type == "Numeric":
        return f"NUMERIC '{value}'"
    if field.type == "Boolean":
        return "TRUE" if value else "FALSE"
    if field.type == "Date":
        return f"DATE({_sql_str(str(value))})"
    raise RenderError(f"{field.name}: spec type {field.type!r} has no SQL literal emission")


def row_values(row: Mapping[str, Any], fields: Sequence[SpecField]) -> str:
    """Return the ``(...)`` VALUES tuple for one row, in ``fields`` order."""
    parts = [_sql_literal(field, row[field.leaf]) for field in fields]
    return "(" + ", ".join(parts) + ")"


# -- projection --------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class _Names:
    """Resolved official dataset/table names from the estate's GCP billing account."""

    project: str
    user_dataset: str
    focus_dataset: str
    billing_account_id: str
    standard_table: str
    resource_table: str
    pricing_table: str
    cud_table: str
    focus_table: str
    invoice_table: str
    invoice_line_item_table: str


def _resolve_names(estate: CanonicalEstate, project: str, user_dataset: str, location: str) -> _Names:
    """Resolve official ``_<BILLING_ACCOUNT_ID>`` dataset/table names.

    The billing account id comes from the estate's GCP ``BillingAccount`` (synthetic,
    fictional). The USER dataset name is configurable; the IMMUTABLE FOCUS dataset
    is ``gcp_billing_immutable_<BA>_<Location>``.
    """
    gcp_ba = next((b for b in estate.billing_accounts if b.provider == "gcp"), None)
    if gcp_ba is None:  # pragma: no cover - the base estate always has a GCP BA
        raise RenderError("no GCP BillingAccount in estate; cannot derive official table names")
    ba = gcp_ba.billing_account_id
    # Sanitize to BigQuery identifier chars (letters/digits/underscore).
    ba_token = "".join(ch if (ch.isalnum() or ch == "_") else "_" for ch in ba)
    focus_dataset = f"gcp_billing_immutable_{ba_token}_{location}"
    return _Names(
        project=project,
        user_dataset=user_dataset,
        focus_dataset=focus_dataset,
        billing_account_id=ba,
        standard_table=f"{project}.{user_dataset}.gcp_billing_export_v1_{ba_token}",
        resource_table=f"{project}.{user_dataset}.gcp_billing_export_resource_v1_{ba_token}",
        pricing_table=f"{project}.{user_dataset}.cloud_pricing_export",
        cud_table=f"{project}.{user_dataset}.cud_subscriptions_export",
        focus_table=f"{project}.{focus_dataset}.gcp_billing_export_focus_{ba_token}",
        # The invoice tables live in the USER dataset, next to the usage
        # tables -- that is where Cloud Billing provisions them.
        invoice_table=f"{project}.{user_dataset}.invoice",
        invoice_line_item_table=f"{project}.{user_dataset}.invoice_line_item",
    )


def _gcp_lines(estate: CanonicalEstate) -> list[BillingLine]:
    """GCP-provider billing lines sorted by line_id; raise on illegal category (M1)."""
    gcp = [line for line in estate.billing_lines if line.service_provider_name == _GCP_PROVIDER]
    for line in gcp:
        if line.charge_category not in _ALLOWED_GCP_CATEGORIES:
            # M1 defensive rule: fail loud instead of silently dropping a future
            # GCP Tax/Credit line that the renderer does not know how to project.
            raise RenderError(
                f"GCP billing line {line.line_id} has charge_category "
                f"{line.charge_category!r} not in {sorted(_ALLOWED_GCP_CATEGORIES)} "
                "(GCP tax rows come from estate.taxes; credits from estate.credits)"
            )
    return sorted(gcp, key=lambda line: line.line_id)


def _resource_name_by_uuid(estate: CanonicalEstate) -> dict[str, str]:
    """Map ``ResourceIdentity.uuid`` -> ``Resource.resource_name`` (may be mangled)."""
    return {r.identity.uuid: r.resource_name for r in estate.resources}


def _commitment_kind_by_scope(estate: CanonicalEstate) -> dict[str, str]:
    """Map ``Commitment.scope_id`` -> ``Commitment.kind`` (one commitment per scope)."""
    out: dict[str, str] = {}
    for c in estate.commitments:
        out.setdefault(c.scope_id, c.kind)
    return out


def _credit_type(kind: str | None) -> str:
    """Derive ``credits[].type`` from the matched ``Commitment.kind`` (F3).

    ``cud`` -> ``COMMITTED_USAGE_DISCOUNT`` else ``SUSTAINED_USAGE_DISCOUNT``. The
    official literal casing stays TODO-verificar #3; the value source is pinned.
    """
    if kind == "cud":
        return "COMMITTED_USAGE_DISCOUNT"  # TODO-verificar #3: official literal casing
    return "SUSTAINED_USAGE_DISCOUNT"  # TODO-verificar #3


def _credit_matches(gcp_lines: list[BillingLine], credit: Credit) -> list[BillingLine]:
    """Return the Usage/Purchase lines a ``Credit`` attaches to, sorted by line_id."""
    matches = [
        line
        for line in gcp_lines
        if line.charge_category in {"Usage", "Purchase"}
        and line.sub_account_id == credit.scope_id
        and credit.period_start <= line.charge_period_start.date() <= credit.period_end
    ]
    return sorted(matches, key=lambda line: line.line_id)


def _pro_rata_negative(lines: list[BillingLine], amount: Decimal) -> list[Decimal]:
    """Allocate ``amount`` across ``lines`` pro-rata by billed_cost, as negatives.

    6-dp ROUND_HALF_EVEN; the last line absorbs the rounding remainder so the sum
    equals ``-amount`` exactly.
    """
    total_cost = sum((line.billed_cost for line in lines), Decimal("0"))
    shares: list[Decimal] = []
    allocated = Decimal("0")
    for i, line in enumerate(lines):
        if i == len(lines) - 1:
            share = (-amount) - allocated  # last absorbs remainder; sum == -amount
        elif total_cost > 0:
            share = _q(-amount * (line.billed_cost / total_cost))
            allocated += share
        else:  # degenerate: all-zero costs -> equal split
            share = _q(-amount / Decimal(len(lines)))
            allocated += share
        shares.append(share)
    return shares


def _allocate_credits(
    estate: CanonicalEstate, gcp_lines: list[BillingLine], names: _Names
) -> dict[str, list[dict[str, Any]]]:
    """Return a map ``line_id -> credits[]`` per the sec. 4.3.1 join + allocation.

    For each GCP ``Credit`` (one per scope), join to Usage/Purchase lines where
    ``L.sub_account_id == Credit.scope_id`` and ``L.charge_period_start.date()``
    is within ``[period_start, period_end]``; allocate ``Credit.amount`` pro-rata
    by ``billed_cost`` as a NEGATIVE share, 6-dp ROUND_HALF_EVEN, with the last
    matching line (by line_id) absorbing the remainder so the per-credit sum equals
    ``-Credit.amount`` exactly.

    NIT-4: ``Credit.period_start/period_end`` currently span the whole sim window,
    so the date predicate matches all in-scope GCP Usage lines -- it is kept for
    correctness if a future builder narrows the period, NOT presented as a
    discriminating filter.
    """
    kind_by_scope = _commitment_kind_by_scope(estate)
    gcp_scopes = {line.sub_account_id for line in gcp_lines}
    out: dict[str, list[dict[str, Any]]] = {}
    for credit in sorted(estate.credits, key=lambda c: c.identity.uuid):
        if credit.scope_id not in gcp_scopes:
            continue  # not a GCP-scope credit
        matches = _credit_matches(gcp_lines, credit)
        if not matches:
            continue
        shares = _pro_rata_negative(matches, credit.amount)
        ctype = _credit_type(kind_by_scope.get(credit.scope_id))
        for line, share in zip(matches, shares, strict=True):
            credit_id = _row_uuid(f"gcp/credit/{credit.identity.uuid}/{line.line_id}")
            element = {
                # ``Credit.name`` is a FinOps-side name and carries the
                # ``[SYNTH] `` marker; ``credits[].name`` is a cloud export column
                # (see ``unmarked_name``).
                "name": unmarked_name(credit.name),
                "amount": _to_float(share),
                "full_name": f"billingAccounts/{names.billing_account_id}/credits/{credit_id}",  # TODO-verificar #3
                "id": credit_id,
                "type": ctype,
            }
            out.setdefault(line.line_id, []).append(element)
    return out


def _standard_values(
    line: BillingLine,
    estate: CanonicalEstate,
    credits_by_line: dict[str, list[dict[str, Any]]],
    resource_names: dict[str, str],
    location: str,
    sources: _ValueSources,
) -> dict[str, Any]:
    """Project one GCP ``BillingLine`` into the standard surface's dotted-value map.

    Indexado pelo CAMINHO da spec. Só os campos que o estado realmente modela aparecem
    aqui; ``build_row`` preenche o resto com ausência (``""``/``0.0``/``[]``), de modo que
    a linha carregue exatamente os nomes documentados sem inventar valor. As fontes
    opcionais vêm de ``_ValueSources``; o que não tem fonte está nomeado em ``MODEL_GAPS``.
    """
    is_adjustment = line.charge_category == "Adjustment"
    cost_type = "adjustment" if is_adjustment else "regular"  # TODO-verificar #2 literals
    labels = _labels(line.tags)
    # F4/NIT-2: inject goog-k8s-cluster-name on every k8s-namespace row, using the
    # backing GKE cluster Resource.resource_name resolved via resource_uuid.
    if line.k8s_namespace is not None and line.resource_uuid is not None:
        cluster_name = resource_names.get(line.resource_uuid, "")
        labels = [*labels, {"key": "goog-k8s-cluster-name", "value": cluster_name}]
    credits = [] if is_adjustment else credits_by_line.get(line.line_id, [])
    rate = _conversion_rate(estate)
    adjustment = (
        {
            "id": line.line_id,
            # The estate models the restatement (``BillingLine.is_restatement``), so
            # the description is a real projection of it — but without a marker: an
            # ``adjustment_info.description`` is a cloud export column.
            "description": "restatement adjustment",
            # C17 anexa um delta positivo para uma data de uso anterior e NUNCA altera a
            # linha original: é a correção de uso do valor documentado (USAGE_CORRECTION)
            # aplicada parcialmente (PARTIAL_CORRECTION), não uma negação. Os literais vêm
            # de allowed_values da própria spec.
            "type": "USAGE_CORRECTION",
            "mode": "PARTIAL_CORRECTION",
        }
        if is_adjustment
        else {"id": "", "description": "", "type": "", "mode": ""}
    )
    zone = _zone_for(line, sources)
    machine_spec = _machine_spec_for(line, sources)
    sku_id = sources.sku_by_resource.get(line.resource_uuid or "")
    list_price = sources.list_price_by_sku.get(sku_id) if sku_id else None
    contracted_price = sources.contracted_price_by_sku.get(sku_id) if sku_id else None
    values: dict[str, Any] = {
        "billing_account_id": line.billing_account_id,
        "service.id": line.service_name,
        "service.description": line.service_name,
        # sku.id é o IDENTIFICADOR do SKU do recurso, na forma publicada pela doc
        # (``2E27-4F75-95CD``), derivado do Resource.sku_id -- não a CATEGORIA de serviço
        # (``Compute``), que fundia SKUs distintos numa única linha de preço e abria a
        # junção documentada com cloud_pricing_export.sku.id. O mesmo canho nas três tabelas.
        "sku.id": gcp_sku_id(estate.seed, sku_id) if sku_id else "",
        # sku.description fica AUSENTE: a doc pede a descrição do tipo de recurso (ex.:
        # "Standard Storage US"), e o estado modela o token do SKU (identificador), o nome
        # do serviço (que descreve o serviço, não o SKU) e a categoria (que não é descrição)
        # -- nenhum é a descrição do tipo de recurso. Ver MODEL_GAPS.
        "usage_start_time": line.charge_period_start,
        "usage_end_time": line.charge_period_end,
        "project.id": line.sub_account_id,
        "project.name": line.sub_account_id,
        "project.labels": labels,
        # project.number/ancestors e tags ficam ausentes: o estado não os modela (nenhum
        # sentinela é escrito numa coluna real); ver MODEL_GAPS.
        "labels": labels,
        "location.location": zone or line.region_id or location,
        "location.country": _country_from_region(line.region_id),  # TODO-verificar #8
        "location.region": line.region_id,  # M1: direct projection (production REGION consumer)
        "usage.amount": _to_float(line.pricing_quantity),
        "usage.unit": line.pricing_unit,
        "usage.amount_in_pricing_units": _to_float(line.pricing_quantity),
        "usage.pricing_unit": line.pricing_unit,
        "cost": _to_float(line.billed_cost),
        "currency": line.currency,
        "currency_conversion_rate": rate,
        "credits": credits,
        "invoice.month": _month(line.billing_period_start),
        "invoice.publisher_type": "GOOGLE",
        "cost_type": cost_type,
        "adjustment_info": adjustment,
        "cost_at_list": _to_float(line.list_cost),
        # Custo com os descontos negociados do contrato (modelo padrão) = contracted_cost;
        # no estado o modelo aplicável coincide com o padrão, então o custo a preço de
        # lista do modelo aplicável é o próprio list_cost da linha.
        "cost_at_effective_price_default": _to_float(line.contracted_cost),
        "cost_at_list_consumption_model": _to_float(line.list_cost),
        "price.unit": line.pricing_unit,
        # ZERO e UM REAIS, não ausência: o SKU do estado tem UMA faixa de preço, e a spec de
        # pricing declara ``aggregation_level = UNKNOWN_AGGREGATION_LEVEL`` como "preço de
        # faixa única"; a faixa única começa em 0, e o preço do catálogo é por 1 unidade.
        # É isso que fecha a segunda chave da junção documentada
        # (``price.tier_start_amount`` = ``tiered_rates.start_usage_amount``).
        "price.tier_start_amount": 0.0,
        "price.pricing_unit_quantity": 1.0,
        "export_time": line.export_time,
    }
    if machine_spec:
        # Só a system label que o modelo sustenta (machine_spec do recurso): as demais
        # chaves documentadas (cores, memory, object_state, reservation_*) não têm fonte.
        values["system_labels"] = [{"key": _MACHINE_SPEC_LABEL, "value": machine_spec}]
    if line.sub_account_id in sources.ancestry_by_project:
        values["project.ancestry_numbers"] = sources.ancestry_by_project[line.sub_account_id]
    if zone:
        values["location.zone"] = zone
    if list_price is not None:
        # Preço de tabela do SKU do recurso, na MESMA unidade que price.unit (o catálogo
        # do estado casa 1:1: 14107/14107 linhas GCP com preço na unidade da linha).
        values["price.list_price"] = _to_float(list_price)
        values["price.list_price_consumption_model"] = _to_float(list_price)
    if contracted_price is not None:
        # Preço com desconto negociado. O estado não tem preço por modelo comprometido
        # (nenhum ContractedPrice tem commitment_id, e o preço implícito de
        # contracted_cost/pricing_quantity é o do contrato padrão), então o modelo
        # APLICÁVEL é o padrão: as duas colunas recebem a mesma fonte.
        values["price.effective_price_default"] = _to_float(contracted_price)
        values["price.effective_price"] = _to_float(contracted_price)
    return values


def _standard_row(
    line: BillingLine,
    estate: CanonicalEstate,
    credits_by_line: dict[str, list[dict[str, Any]]],
    resource_names: dict[str, str],
    location: str,
    sources: _ValueSources | None = None,
) -> dict[str, Any]:
    """Project one GCP ``BillingLine`` into a standard-export row (all 71 spec fields)."""
    values = _standard_values(
        line,
        estate,
        credits_by_line,
        resource_names,
        location,
        sources if sources is not None else _value_sources(estate),
    )
    return build_row(fields_for("standard"), values)


def _tax_values(
    estate: CanonicalEstate,
    gcp_lines: list[BillingLine],
    location: str,
    sources: _ValueSources,
) -> list[dict[str, Any]]:
    """Project ``estate.taxes`` into ``cost_type="tax"`` dotted-value maps (sec. 4.3b).

    One entry per GCP-scope ``Tax`` (``t.scope_id`` matches a GCP line's
    ``sub_account_id``). The row is identified by ``cost_type="tax"``, which is the
    official discriminator, plus ``project.id``/``project.name`` from the taxed scope —
    all three modelled by the estate. ``service``/``sku`` stay EMPTY: this estate has no
    tax service or SKU, and the previous sentinels (``SYNTH-TAX`` / ``SYNTH-TAX-SKU`` /
    ``[SYNTH] Tax``) wrote a synthetic marker into two real cloud columns. Absence is
    absence (see ``focus_aws``'s empty-column note).
    """
    gcp_scopes = {line.sub_account_id for line in gcp_lines}
    gcp_ba = next((b.billing_account_id for b in estate.billing_accounts if b.provider == "gcp"), "")
    values: list[dict[str, Any]] = []
    for tax in sorted(estate.taxes, key=lambda t: (t.scope_id, t.period_start)):
        if tax.scope_id not in gcp_scopes:
            continue
        start_dt = datetime.combine(tax.period_start, time(0, 0, 0), tzinfo=UTC)
        end_dt = datetime.combine(_next_month_first(tax.period_start), time(0, 0, 0), tzinfo=UTC)
        values.append(
            {
                "billing_account_id": gcp_ba,
                "usage_start_time": start_dt,
                "usage_end_time": end_dt,
                "project.id": tax.scope_id,
                "project.name": tax.scope_id,
                "project.ancestry_numbers": sources.ancestry_by_project.get(tax.scope_id, ""),
                "location.location": location,
                "cost": _to_float(tax.amount),
                "currency": tax.currency,
                "currency_conversion_rate": _conversion_rate(estate),
                "invoice.month": _month(tax.period_start),
                "invoice.publisher_type": "GOOGLE",
                "cost_type": "tax",  # TODO-verificar #2 literal
                "cost_at_list": _to_float(tax.amount),
                "export_time": start_dt,
            }
        )
    return values


def _tax_rows_from(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build the standard-export tax rows from ``_tax_values`` (deterministic row key)."""
    rows: list[dict[str, Any]] = []
    for entry in values:
        row = build_row(fields_for("standard"), entry)
        row["_row_key"] = _row_uuid(f"gcp/tax/{entry['project.id']}/{entry['invoice.month']}")
        rows.append(row)
    return rows


def _tax_rows(estate: CanonicalEstate, gcp_lines: list[BillingLine], location: str) -> list[dict[str, Any]]:
    """Tax rows for the standard table (see :func:`_tax_values`)."""
    return _tax_rows_from(_tax_values(estate, gcp_lines, location, _value_sources(estate)))


# -- pricing rows (cloud_pricing_export) --------------------------------------------


def _pricing_values(
    estate: CanonicalEstate,
    sku_id: str,
    unit: str,
    list_price: Decimal,
    service_name: str,
    billing_account_id: str,
    pricing_as_of: datetime,
) -> dict[str, Any]:
    """Valores de UMA linha de ``cloud_pricing_export`` para ``sku_id``.

    A tabela de preços é a outra ponta da junção documentada: ``sku.id`` é a chave
    (o MESMO canho das tabelas de uso) e ``tiered_rates.start_usage_amount`` casa com
    ``price.tier_start_amount``. O preço do SKU vive em ``tiered_rates.usd_amount`` (o
    catálogo do estado é um preço por unidade, em USD) e em
    ``tiered_rates.account_currency_amount`` pela fórmula documentada
    (``usd_amount * currency_conversion_rate``). O que o estado NÃO modela (topologia
    geográfica, taxonomia, modelos de consumo, preço contratual por faixa, descrição do
    SKU/unidade) sai ausente e está nomeado em ``MODEL_GAPS``.
    """
    rate = _conversion_rate(estate)
    usd_amount = _to_float(list_price)
    if rate is None:
        account_amount: float | None = None  # sem taxa modelada: ausência, não o preço em USD
    elif estate.currency_conversion_rate is not None:
        account_amount = _to_float(list_price * estate.currency_conversion_rate)
    else:
        account_amount = usd_amount  # taxa 1.0 (conta em USD, valor de definição)
    tier_fields = next(field for field in fields_for("pricing") if field.name == "tiered_rates").children
    # Faixa ÚNICA: a spec declara UNKNOWN_AGGREGATION_LEVEL/UNKNOWN_AGGREGATION_INTERVAL
    # como "preço de faixa única" (default para SKUs sem faixas), que é o que o catálogo do
    # estado é: um preço por SKU/unidade. Logo a faixa começa em 0 e vale por 1 unidade.
    tier = build_row(
        tier_fields,
        {
            "tiered_rates.pricing_unit_quantity": 1.0,
            "tiered_rates.start_usage_amount": 0.0,
            "tiered_rates.usd_amount": usd_amount,
            "tiered_rates.account_currency_amount": account_amount,
        },
    )
    return {
        "export_time": pricing_as_of,
        "pricing_as_of_time": pricing_as_of,
        "billing_account_id": billing_account_id,
        "business_entity_name": "GCP",  # allowed_values: GCP | Maps
        "service.id": service_name,
        "service.description": service_name,
        "sku.id": gcp_sku_id(estate.seed, sku_id),
        # sku.description ausente (ver MODEL_GAPS): a doc pede a descrição do tipo de
        # recurso e nenhuma fonte modelada a carrega -- a categoria NÃO é descrição.
        "pricing_unit": unit,
        "account_currency_code": estate.currency,  # ISO 4217
        # Nesta tabela o tipo documentado é String (divergência registrada na spec).
        "currency_conversion_rate": None if rate is None else str(rate),
        "aggregation_info.aggregation_level": "UNKNOWN_AGGREGATION_LEVEL",
        "aggregation_info.aggregation_interval": "UNKNOWN_AGGREGATION_INTERVAL",
        "tiered_rates": [tier],
    }


def _pricing_rows(estate: CanonicalEstate, names: _Names, sources: _ValueSources) -> list[dict[str, Any]]:
    """Uma linha por SKU GCP do catálogo, com o MESMO ``sku.id`` das tabelas de uso.

    O conjunto de SKUs é o dos recursos GCP do estado (o que a export de preços precisa
    cobrir: todo SKU que uma linha de uso referencia). Ordenado por ``sku_id`` para
    determinismo.
    """
    pricing_as_of = datetime.combine(estate.sim_now, time(0, 0, 0), tzinfo=UTC)
    rows: list[dict[str, Any]] = []
    for sku_id in sorted(sources.service_by_sku):
        list_price = sources.list_price_by_sku.get(sku_id)
        if list_price is None:
            continue  # SKU referenciado sem preço no catálogo: nada a afirmar
        rows.append(
            build_row(
                fields_for("pricing"),
                _pricing_values(
                    estate,
                    sku_id,
                    sources.sku_unit_by_sku.get(sku_id, ""),
                    list_price,
                    sources.service_by_sku[sku_id],
                    names.billing_account_id,
                    pricing_as_of,
                ),
            )
        )
    return rows


# -- INSERT emission ---------------------------------------------------------------


def _insert_statements(fqtn: str, fields: Sequence[SpecField], rows: list[dict[str, Any]]) -> list[str]:
    """Return chunked multi-row INSERT statements for ``rows`` into ``fqtn``.

    ``fields`` is the SAME sequence that produced ``rows`` (``build_row``/``ddl_columns``),
    so the column list and the VALUES tuple cannot drift apart: both iterate the spec tree.
    """
    cols = insert_column_list(fields)
    statements: list[str] = []
    for start in range(0, len(rows), _INSERT_CHUNK):
        chunk = rows[start : start + _INSERT_CHUNK]
        values = ",\n  ".join(row_values(r, fields) for r in chunk)
        # S608: this emits a DDL/INSERT *script file* (not an executed query) from
        # the tool's own synthetic, fictional values; no untrusted input, nothing
        # hits a live database here.
        statements.append(f"INSERT INTO `{fqtn}` ({cols}) VALUES\n  {values};")  # noqa: S608
    return statements


def json_rows(rows: list[dict[str, Any]]) -> str:
    """Serialise projected rows as the ``tabledata.insertAll`` payload (bulk load).

    The SQL INSERT path is capped by the emulator's parser (see :data:`_INSERT_CHUNK`),
    so the rows go over the streaming-insert API instead. Two adjustments are required
    for that API: datetimes become ISO strings, and renderer-internal keys are dropped
    (``insertAll`` rejects any field the table does not declare -- ``_row_key`` on the
    tax rows is exactly that). ``sort_keys`` + fixed separators keep the output
    byte-deterministic, the same property the SQL scripts hold.
    """
    payload = [
        {
            key: (value.isoformat() if isinstance(value, (date, datetime)) else value)
            for key, value in row.items()
            if not key.startswith("_")
        }
        for row in rows
    ]
    return json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"


def _cud_rows(estate: CanonicalEstate, gcp_lines: list[BillingLine]) -> list[dict[str, Any]]:
    """Project GCP ``Commitment`` rows for the cud_subscriptions_export table (sec. 4.4)."""
    gcp_scopes = {line.sub_account_id for line in gcp_lines}
    rows: list[dict[str, Any]] = []
    for c in sorted(estate.commitments, key=lambda c: c.identity.uuid):
        if c.kind != "cud" or c.scope_id not in gcp_scopes:
            continue
        rows.append(
            {
                "commitment_id": c.identity.uuid,
                "subscription_name": c.identity.uuid,
                "plan": c.kind,
                "status": c.status,
                "scope_id": c.scope_id,
                "start_time": datetime.combine(c.period_start, time(0, 0, 0), tzinfo=UTC),
                "end_time": datetime.combine(c.period_end, time(0, 0, 0), tzinfo=UTC),
            }
        )
    return rows


def _rate(cost: Decimal, quantity: Decimal) -> float | None:
    """Unit price implied by a charge, or ``None`` when the row carries no quantity.

    Guarded because a tax or fully-credited line carries no usage quantity at all, and
    dividing by it would raise during render. ``None`` (absence), not ``0.0``: a unit price
    of zero is a claim, and the column is nullable.
    """
    if not quantity:
        return None
    return _to_float(cost / quantity)


def _item_type(row: dict[str, Any]) -> str:
    """Map ``cost_type`` onto the official ``invoice_line_item.item_type``."""
    return {"tax": "Tax", "adjustment": "Adjustment", "rounding": "Rounding"}.get(
        row["cost_type"], "SKU"
    )


def _invoice_id(row: dict[str, Any]) -> str:
    """Deterministic invoice id for a line, matching the official shape.

    Google exposes the invoice id as an opaque string scoped to the billing
    account. Derived from (billing account, invoice month) so every line of
    one month rolls up to exactly one invoice -- which is what makes the
    invoice table reconcilable against the line items.
    """
    return f"{row['billing_account_id']}-{row['invoice']['month']}"


def _invoice_line_item_rows(std_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Project the standard-export rows onto the official ``invoice_line_item``.

    Derived from the rows already built for the usage tables rather than
    recomputed, so an invoice line can never disagree with the usage line it
    came from -- the two are the same charge seen from two sides.

    ``amount`` is the pre-tax charge and ``tax_amount`` stays 0 because tax is
    emitted as its own line item with ``item_type='Tax'``, matching how Cloud
    Billing actually invoices: summing ``amount + tax_amount`` across the table
    reproduces ``invoice.total_amount``.
    """
    rows: list[dict[str, Any]] = []
    for row in std_rows:
        usage = row["usage"]
        credits = [{"name": c["name"], "amount": c["amount"]} for c in row["credits"]]
        adjustment = row["adjustment_info"]
        rows.append(
            {
                "billing_account_id": row["billing_account_id"],
                "service": row["service"],
                "sku": row["sku"],
                "id": _row_uuid(f"gcp/line/{row['billing_account_id']}/{row['invoice']['month']}/{row['usage_start_time']}/{row['sku']['id']}"),
                "invoice_id": _invoice_id(row),
                "invoice_month": row["invoice"]["month"],
                "cost_type": row["cost_type"],
                "usage_start_time": row["usage_start_time"],
                "usage_end_time": row["usage_end_time"],
                # A descrição do item vinha de sku.description, que agora fica ausente (a doc
                # pede a descrição do TIPO DE RECURSO e o estado não a modela). O nome do
                # serviço é um texto modelado e mantém o item legível; esta tabela não tem
                # spec, então não há contrato de coluna a violar.
                "description": row["sku"]["description"] or row["service"]["description"],
                "currency": row["currency"],
                "amount": row["cost"],
                "tax_amount": 0.0,
                "pricing_unit": usage["pricing_unit"],
                "pricing_amount": usage["amount_in_pricing_units"],
                "pricing_rate": _rate(
                    Decimal(str(row["cost"])), Decimal(str(usage["amount_in_pricing_units"] or 0))
                ),
                "credits": credits,
                "cost": row["cost"],
                "item_type": _item_type(row),
                "adjustment_id": adjustment["id"],
                "adjustment_type": adjustment["type"],
                "adjustment_description": adjustment["description"],
            }
        )
    return rows


def _invoice_rows(
    line_items: list[dict[str, Any]], billing_account_name: str
) -> list[dict[str, Any]]:
    """Roll the line items up into the official ``invoice`` table.

    One invoice per (billing account, invoice month). ``total_amount`` is the
    sum of the month's line items, which is the property a consumer checks
    when reconciling: ``invoice.total_amount == sum(invoice_line_item.cost)``
    for the same ``invoice_id``.
    """
    by_invoice: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for item in line_items:
        by_invoice.setdefault((item["billing_account_id"], item["invoice_month"]), []).append(item)

    rows: list[dict[str, Any]] = []
    for (billing_account_id, invoice_month), items in sorted(by_invoice.items()):
        total = sum(item["amount"] + item["tax_amount"] for item in items)
        currency = items[0]["currency"]
        invoice_date = min(item["usage_start_time"] for item in items)
        rows.append(
            {
                "billing_account_id": billing_account_id,
                "service": {"description": ""},
                "sku": {"description": ""},
                "invoice_id": items[0]["invoice_id"],
                "invoice_month": invoice_month,
                "invoice_date": invoice_date,
                # Google bills monthly in arrears: the invoice is stamped at
                # the period start and due one month later.
                "due_date": datetime.combine(
                    _next_month_first(invoice_date.date()), time(0, 0, 0), tzinfo=UTC
                ),
                "total_amount": total,
                "currency": currency,
                "cost": {"amount": total, "currency": currency},
                "status": "Posted",
                "name": f"GCP Billing Invoice {invoice_month}",
            }
        )
    return rows


def _cud_insert(fqtn: str, rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return []
    values = []
    for r in rows:
        values.append(
            "("
            f"{_sql_str(r['commitment_id'])}, "
            f"STRUCT({_sql_str(r['subscription_name'])} AS name, {_sql_str(r['plan'])} AS plan, "
            f"{_sql_str(r['status'])} AS status), "
            f"{_sql_str(r['scope_id'])}, {_sql_str(r['plan'])}, "
            f"{_sql_ts(r['start_time'])}, {_sql_ts(r['end_time'])}, {_sql_str(r['status'])})"
        )
    body = ",\n  ".join(values)
    cols = "commitment_id, subscription, scope_id, plan, start_time, end_time, status"
    return [f"INSERT INTO `{fqtn}` ({cols}) VALUES\n  {body};"]  # noqa: S608


class GcpBigQueryTopologyRenderer:
    """Renders the canonical estate to the official GCP billing-export topology."""

    name = "gcp_bigquery_topology"

    def __init__(
        self,
        *,
        project: str = "synthetic",
        user_dataset: str = "all_billing_data",
        location: str = _DEFAULT_LOCATION,
    ) -> None:
        self.project = project
        self.user_dataset = user_dataset
        self.location = location

    def build_scripts(self, estate: CanonicalEstate) -> tuple[_Names, dict[str, str], dict[str, int]]:
        """Return (names, {filename: sql}, {table: row_count}) -- the render payload.

        Pure; no filesystem. Used by both ``render`` and the unit tests.
        """
        names = _resolve_names(estate, self.project, self.user_dataset, self.location)
        # ONE spec-derived field tree per documented table; the row shape and the DDL
        # column block are both built from it, so they cannot disagree with each other.
        standard_fields = fields_for("standard")
        detailed_fields = fields_for("detailed")
        gcp_lines = _gcp_lines(estate)  # raises RenderError on illegal category (M1)
        credits_by_line = _allocate_credits(estate, gcp_lines, names)
        resource_names = _resource_name_by_uuid(estate)
        sources = _value_sources(estate)  # catálogos/perfis/hierarquia, indexados uma vez

        std_values = [
            _standard_values(line, estate, credits_by_line, resource_names, self.location, sources)
            for line in gcp_lines
        ]
        std_rows = [build_row(standard_fields, values) for values in std_values]
        tax_values = _tax_values(estate, gcp_lines, self.location, sources)
        tax_rows = _tax_rows_from(tax_values)
        all_std_rows = std_rows + tax_rows
        # Resource table: the DETAILED surface, built from the same values plus the
        # `resource` record resolved from the backing Resource (empty for the tax rows).
        res_rows: list[dict[str, Any]] = []
        for line, values in zip(gcp_lines, std_values, strict=True):
            rname = resource_names.get(line.resource_uuid or "", "")
            res_rows.append(
                build_row(detailed_fields, {**values, "resource.name": rname, "resource.global_name": rname})
            )
        res_rows.extend(build_row(detailed_fields, values) for values in tax_values)

        cud_rows = _cud_rows(estate, gcp_lines)
        # Pricing side: one row per GCP SKU of the catalogue, carrying the SAME sku.id
        # minted for the usage rows -- that is what closes the documented join.
        pricing_rows = _pricing_rows(estate, names, sources)
        # Invoice side of the export, derived from the same rows the usage
        # tables carry so the two can never disagree.
        line_item_rows = _invoice_line_item_rows(all_std_rows)
        gcp_ba_name = next(
            (b.name for b in estate.billing_accounts if b.provider == "gcp"), ""
        )
        invoice_rows = _invoice_rows(line_item_rows, gcp_ba_name)

        datasets_sql = "\n".join(
            [_create_schema(names.user_dataset, names.project), _create_schema(names.focus_dataset, names.project)]
        )
        tables_sql = "\n\n".join(
            [
                _create_standard_table(names.standard_table),
                _create_resource_table(names.resource_table),
                _create_pricing_table(names.pricing_table),
                _create_cud_table(names.cud_table),
                _create_focus_table(names.focus_table),
                _create_invoice_table(names.invoice_table),
                _create_invoice_line_item_table(names.invoice_line_item_table),
            ]
        )
        files: dict[str, str] = {
            "01_datasets.sql": datasets_sql + "\n",
            "02_tables.sql": tables_sql + "\n",
            "03_insert_standard.sql": self._join(
                _insert_statements(names.standard_table, standard_fields, all_std_rows)
            ),
            "04_insert_resource.sql": self._join(
                _insert_statements(names.resource_table, detailed_fields, res_rows)
            ),
            "05_insert_pricing.sql": (
                "-- cloud_pricing_export: schema in 02_tables.sql and ROWS here are derived from "
                "specs/gcp/billing-export-pricing.schema.json\n"
                "-- plus the estate's SKU catalogue (12_rows_pricing.json carries the same rows).\n"
                "-- sku.id is the SAME minted id the usage tables carry: the documented join "
                "(sku.id, tier_start_amount = start_usage_amount) closes.\n"
            )
            + self._join(_insert_statements(names.pricing_table, fields_for("pricing"), pricing_rows)),
            "06_insert_cud.sql": self._join(_cud_insert(names.cud_table, cud_rows)),
            "07_insert_focus.sql": (
                "-- gcp_billing_export_focus: FOCUS schema offline-unverifiable "
                "(TODO-verificar #4); no rows emitted\n"
            ),
            # Bulk-load payloads for the row tables. The SQL INSERTs above stay as the
            # human-readable record of the same rows, but the emulator cannot parse them at
            # this scale, so the provisioner streams these instead.
            "08_rows_standard.json": json_rows(all_std_rows),
            "09_rows_resource.json": json_rows(res_rows),
            "10_rows_invoice.json": json_rows(invoice_rows),
            "11_rows_invoice_line_item.json": json_rows(line_item_rows),
            "12_rows_pricing.json": json_rows(pricing_rows),
        }
        counts = {
            names.standard_table: len(all_std_rows),
            names.resource_table: len(res_rows),
            names.pricing_table: len(pricing_rows),
            names.cud_table: len(cud_rows),
            names.focus_table: 0,
            names.invoice_table: len(invoice_rows),
            names.invoice_line_item_table: len(line_item_rows),
        }
        return names, files, counts

    @staticmethod
    def _join(statements: list[str]) -> str:
        if not statements:
            return "-- (no rows)\n"
        return "\n\n".join(statements) + "\n"

    def _manifest(self, names: _Names, counts: dict[str, int]) -> dict[str, Any]:
        """Build the provisioner contract payload, written as ``PROVENANCE_FILENAME``.

        Ordered scripts + row counts + spec provenance + TODOs. These keys are ABOUT the
        export, not columns of it, which is why the file is ``_``-prefixed (sibling report)
        and must stay that way: inside the export tree the auditor would call them invented.
        """
        return {
            "project": names.project,
            "user_dataset": names.user_dataset,
            "focus_dataset": names.focus_dataset,
            "billing_account_id": names.billing_account_id,
            "scripts": [
                "01_datasets.sql",
                "02_tables.sql",
                "03_insert_standard.sql",
                "04_insert_resource.sql",
                "05_insert_pricing.sql",
                "06_insert_cud.sql",
                "07_insert_focus.sql",
            ],
            # The scripts the provisioner actually submits. 03/04/05 are excluded on
            # purpose: they are the same rows the three bulk payloads carry (the SQL path is
            # the human-readable record), and the emulator's parser cannot take the two big
            # ones at production scale (measured: it panics above ~166 KB per statement and
            # after ~54k rows in one table). Submitting them AND streaming would double the
            # rows and fail the manifest's own row-count assertion.
            "provision_scripts": [
                "01_datasets.sql",
                "02_tables.sql",
                "06_insert_cud.sql",
                "07_insert_focus.sql",
            ],
            "bulk_rows": {
                "standard": "08_rows_standard.json",
                "resource": "09_rows_resource.json",
                "pricing": "12_rows_pricing.json",
            },
            "tables": {
                "standard": {"table": names.standard_table, "expected_rows": counts[names.standard_table]},
                "resource": {"table": names.resource_table, "expected_rows": counts[names.resource_table]},
                "pricing": {"table": names.pricing_table, "expected_rows": counts[names.pricing_table]},
                "cud": {"table": names.cud_table, "expected_rows": counts[names.cud_table]},
                "focus": {"table": names.focus_table, "expected_rows": counts[names.focus_table]},
            },
            # Provenance of each documented table's column set: the spec file it was derived
            # from, the compared level and the column counts. ``columns`` counts DOTTED spec
            # paths (nested fields included), which is the level the fidelity test compares;
            # ``top_level`` counts top-level names only (they differ: 71 x 26 on the standard
            # table). A stale count here is a stale column block, visible in the manifest.
            "schema_specs": {
                "standard": schema_provenance("standard"),
                "detailed": schema_provenance("detailed"),
                "pricing": schema_provenance("pricing"),
            },
            # Colunas documentadas que o estado NÃO tem como preencher, com o motivo. É o
            # outro lado de "schema_specs": lá o conjunto de colunas, aqui quais delas têm
            # valor. O teste de fidelidade confronta esta lista com as linhas entregues nos
            # dois sentidos, então ela não envelhece em silêncio.
            "model_gaps": {
                "standard": model_gaps("standard"),
                "detailed": model_gaps("detailed"),
                "pricing": model_gaps("pricing"),
            },
            "model_gaps_note": (
                "Colunas sem fonte no modelo canônico. Coluna vazia apenas por falta de dado na "
                "execução (ex.: adjustment_info.* num estado sem linha de ajuste) não entra aqui: "
                "a fonte existe e a coluna é preenchida quando o dado existe."
            ),
            "todo_verificar": {
                "1": (
                    "standard/detailed export column SET is now derived from the spec "
                    "(resolved); remaining: which modelled value each optional field carries "
                    "(project.ancestors, system_labels, price.*, tags, consumption_model)"
                ),
                "2": "cost_type enum literals (regular|tax|adjustment|rounding_error)",
                "3": "credits[].type + full_name official literals",
                "4": "GCP FOCUS billing export column set + dataset/table naming",
                "5": (
                    "cloud_pricing_export SCHEMA and ROWS are now derived from the spec plus the "
                    "estate's SKU catalogue (resolved); remaining: cud_subscriptions_export schema"
                ),
                "6": "partitioning (_PARTITIONTIME); emulator partition support",
                "8": (
                    "location.location/zone are now sourced (zone from the instance profile when it "
                    "belongs to the line's region, else the region); remaining: the country mapping "
                    "table"
                ),
            },
        }

    def render(self, estate: CanonicalEstate, out_dir: Path) -> list[Path]:
        """Write the DDL/INSERT scripts + manifest under ``out_dir/gcp_bigquery_topology/``."""
        names, files, counts = self.build_scripts(estate)
        target = out_dir / "gcp_bigquery_topology"
        target.mkdir(parents=True, exist_ok=True)
        written: list[Path] = []
        for filename in (
            "01_datasets.sql",
            "02_tables.sql",
            "03_insert_standard.sql",
            "04_insert_resource.sql",
            "05_insert_pricing.sql",
            "06_insert_cud.sql",
            "07_insert_focus.sql",
            "08_rows_standard.json",
            "09_rows_resource.json",
            "12_rows_pricing.json",
        ):
            path = target / filename
            path.write_text(files[filename], encoding="utf-8")
            written.append(path)
        manifest_path = target / PROVENANCE_FILENAME
        manifest_path.write_text(
            json.dumps(self._manifest(names, counts), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        written.append(manifest_path)
        return written
