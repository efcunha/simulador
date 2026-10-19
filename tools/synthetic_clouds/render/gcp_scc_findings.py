"""Security Command Center findings -> BigQuery: the columns the documentation fixes.

The documented mechanism
------------------------
``specs/gcp/security-command-center-findings-bigquery.md`` (consulted 2026-10-14) records a
real export: SCC writes findings to a BigQuery table called **``findings``**, in a
user-created dataset, "in near real time" (continuous) or as a snapshot (bulk). Both pages
list the SAME six top-level columns and the table "is clustered by ``source_id``,
``finding_id``, and ``event_time``"; every new finding and each of its updates becomes a
NEW row, so one (source_id, finding_id) pair legitimately has several event_time rows.

Why NO DDL is emitted
---------------------
Neither export page declares the BigQuery TYPE of those six columns: it publishes names
and descriptions only. The target of a DDL is a typed table and this project does not invent
a type, so **no ``CREATE TABLE`` statement is emitted**: there is no honest DDL for the
``findings`` table.

What IS emitted, and the one asymmetry
--------------------------------------
``findings_rows.json`` carries one object per GCP finding, with the 68 documented
``finding.*`` paths of the SCC v1 ``Finding`` object PLUS the five envelope columns that
have a source:

* ``source_id``, ``finding_id``, ``event_time`` and ``bulk_export_id`` carry values, each
  from the source ``value_domains`` names;
* ``resource`` is present and EMPTY: the export page points at "the API reference for the
  ``Resource`` object" and every SCC REST path tried for it returned 404, so no inner field
  name is published;
* the ``finding`` CONTAINER is not emitted as a key. It is represented by its 68 flattened
  children -- the fidelity core compares the row's TOP-LEVEL keys with the spec names, so the
  children have to sit at the top to match, and an empty ``finding`` key would assert an
  empty record while a nested one would hide the children from the comparison. That is a
  declared representation (``required_empty_declared`` + ``container_representation`` in the
  provenance), not an omission.

Emitting a column whose type the documentation does not publish is a deliberate exception to
the core rule "a column only enters if ``belongs_to_schema``": that rule protects a TYPED
target, and this artifact is a record. Omitting a column the export page marks ``required``
would be as unfaithful as inventing a type for it, so the five are emitted, each declared,
and the core reports them as ``unverified_emitted`` -- exactly the five, plus the one
``missing`` container, and this module's test pins that set to the spec.

A field the canonical estate does not model is present and EMPTY; a value whose documented
domain the spec marks unverified (the ``State``/``Severity``/``Mute``/``FindingClass`` enum
constants were not transcribed) is left EMPTY too. The three clustering columns are emitted
AND kept as row metadata in ``_provenance.json`` -> ``row_keys``, which additionally carries
the estate's ``resource_uuid`` for the P2 cross-plane join -- spec nenhuma desta superficie
tem coluna para ele.

Artifact and report are separate files, always: ``findings_rows.json`` carries only
documented fields, and everything about provenance (the spec, the mechanism, the per-column
disposition, the required-empty declarations, the model gaps, the provider's JSON spelling
of a repeated field) lives in the SIBLING ``_provenance.json``.

The SCC source name is imported from ``gcp_rest_fixtures`` on purpose: a finding published
by this BigQuery plane and the same finding served on the REST plane must name ONE source,
not two.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from typing import Any

from tools.synthetic_clouds.fidelity.artifacts import is_empty_value
from tools.synthetic_clouds.fidelity.spec import (
    DEFAULT_SPECS_ROOT,
    Column,
    SpecError,
    SurfaceSpec,
    load_spec,
)
from tools.synthetic_clouds.model.compute import InstanceProfile
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.native import NativeFinding
from tools.synthetic_clouds.model.resource import Resource
from tools.synthetic_clouds.render.base import RenderError
from tools.synthetic_clouds.render.gcp_rest_fixtures import _SCC_SOURCE_NAME

#: A spec de origem, sob ``specs/`` (nunca editada aqui).
_SPEC_FILE = "gcp/security-command-center-findings-bigquery.schema.json"

#: O tipo de recurso cuja forma de nome completo esta spec cita.
_INSTANCE_TYPE = "compute_instance"

#: O artefato (os registros) e o relatorio de proveniencia, que NUNCA se misturam.
_ROWS_FILE = "findings_rows.json"
_PROVENANCE_FILE = "_provenance.json"

#: Namespace fixo e sem semente do id de export (mesmo padrao de
#: ``gcp_bigquery_topology._NS``): a chave ja carrega a identidade do estado, entao o id
#: derivado continua deterministico. TODO-verificar: o id do job de bulk export e atribuido
#: pelo SERVICO; a forma (UUID) e a documentada, o valor e nosso.
_EXPORT_NS = uuid.UUID("7d3f1a26-5b4c-4e8d-9a10-2c6f8b7e5d41")

#: As tres colunas de clustering que a pagina de export afirma (nome exato).
_CLUSTERING_COLUMNS = ("source_id", "finding_id", "event_time")

#: Tipos cujo vazio e um objeto sem campos; todo tipo NAO escalar cai aqui.
_RECORD_TYPES = frozenset({"record", "struct", "map", "object", "message"})
_ARRAY_PREFIXES = ("array", "repeated", "list of")


@cache
def scc_findings_spec() -> SurfaceSpec:
    """Carrega a spec normativa da superficie; falha FECHADO se ela nao servir."""
    path = DEFAULT_SPECS_ROOT / _SPEC_FILE
    try:
        return load_spec(path)
    except SpecError as exc:  # pragma: no cover - a spec invalida e um erro de repositorio
        raise RenderError(f"{path}: {exc}") from exc


def _empty_value(column: Column) -> Any:
    """Valor de AUSENCIA para o tipo documentado da coluna -- nunca um palpite.

    Um campo que o modelo canonico nao projeta continua existindo no artefato (omitir a
    coluna seria infiel ao formato) e nao pode receber valor (preencher seria infiel ao
    contrato). O vazio e escolhido pelo TIPO: lista vazia para um campo repetido, objeto
    vazio para um record/map, nulo para booleano/numero, string vazia para
    string/enum/bytes/timestamp.
    """
    lowered = (column.type or "").strip().lower()
    if column.name.endswith("[]") or lowered.startswith(_ARRAY_PREFIXES):
        return []
    base = lowered.split(" (", 1)[0].strip()
    if base in _RECORD_TYPES:
        return {}
    if base.startswith(("bool", "int", "uint", "float", "double", "numeric", "decimal")):
        return None
    if base.startswith(("string", "enum", "timestamp", "date", "bytes")):
        return ""
    # Tipo nomeado (mensagem aninhada) que nao e escalar: o vazio e o objeto sem campos.
    return {}


#: Colunas de ENVELOPE que a pagina de export lista e cujo TIPO BigQuery ela NAO publica,
#: mas que este artefato EMITE mesmo assim.
#:
#: A regra do nucleo e "uma coluna so entra se ``belongs_to_schema``", e ela existe para o
#: alvo ser TIPADO (DDL, Parquet): escrever uma coluna sem tipo publicado obrigaria a
#: inventar o tipo. Este artefato e um REGISTRO (uma linha da tabela documentada, nao um
#: DDL), e a propria pagina de export diz que essas colunas sempre estao la -- quatro delas
#: sao ``required``. Omiti-las seria tao infiel quanto inventar um tipo; emiti-las sem valor
#: inventado e a resposta honesta, e cada uma esta declarada em ``table_columns``.
#:
#: O container ``finding`` fica FORA desta lista de proposito: ele e representado pelos seus
#: 68 filhos achatados (ver ``container_representation`` na proveniencia), nunca por uma
#: chave vazia nem por um objeto que esconderia os filhos da conferencia.
_EMITTED_WITHOUT_PUBLISHED_TYPE = ("source_id", "finding_id", "event_time", "bulk_export_id", "resource")


def row_for(
    spec: SurfaceSpec,
    values: Mapping[str, Any],
    *,
    declared_untyped: Sequence[str] = (),
) -> dict[str, Any]:
    """Linha com as colunas que PERTENCEM ao formato MAIS as de envelope declaradas.

    ``declared_untyped`` so aceita nomes que a spec publica (a consulta a ``by_name``
    levantaria em nome desconhecido): uma coluna que a documentacao nao lista nao entra por
    aqui, e o teste da superficie confere o conjunto exato.
    """
    by_name = {column.name: column for column in spec.columns}
    nomes = [*declared_untyped, *(column.name for column in spec.columns if column.belongs_to_schema)]
    return {name: values.get(name, _empty_value(by_name[name])) for name in nomes}


def wire_naming(spec: SurfaceSpec) -> dict[str, str]:
    """Mapa ``nome documentado -> nome JSON do provedor``, so para os campos repetidos.

    O artefato carrega o nome que a DOCUMENTACAO da ao campo (``finding.connections[]``);
    a serializacao JSON do provedor dispensa os colchetes. O mapa e publicado na
    proveniencia para que um cliente converta o registro sem adivinhar.
    """
    return {
        column.name: column.name[:-2]
        for column in spec.columns
        if column.belongs_to_schema and column.name.endswith("[]")
    }


def _instant(moment: datetime | None) -> str:
    """Instante em UTC no formato de data RFC 3339 que o campo de Timestamp declara.

    ``NativeFinding.first_observed_at`` e um ``datetime`` com fuso (o gate exige UTC e que o
    dia caia dentro da janela); sem fuso nao haveria instante a projetar, e o campo sairia
    vazio em vez de receber um palpite.
    """
    if moment is None:
        return ""
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _profiles(estate: CanonicalEstate) -> dict[str, InstanceProfile]:
    """Os perfis de instancia GCP, por ``resource_uuid`` (FK do modelo, sem orfaos)."""
    return {
        profile.resource_uuid: profile for profile in estate.instance_profiles if profile.provider == "gcp"
    }


def _resources(estate: CanonicalEstate) -> dict[str, Resource]:
    """Os recursos do estado, por ``ResourceIdentity.uuid``."""
    return {resource.identity.uuid: resource for resource in estate.resources}


def _resource_name(resource: Resource | None, profile: InstanceProfile | None) -> str:
    """O nome completo do recurso, na forma que a descricao do campo ``resourceName`` cita.

    O campo documenta "the full resource name of the Google Cloud resource this finding is
    for" e a forma publicada para uma instancia Compute e
    ``//compute.googleapis.com/projects/<p>/zones/<z>/instances/<n>`` (a mesma que a
    mensagem ``Asset`` do Cloud Asset Inventory publica). A ZONA vem do
    ``InstanceProfile``; sem perfil, ou para um tipo de recurso cuja forma esta spec nao
    cita, o campo fica VAZIO -- montar a forma de outro tipo seria inventar identidade.
    """
    if resource is None or profile is None or not profile.zone:
        return ""
    if resource.resource_type != _INSTANCE_TYPE:
        return ""
    return (
        f"//compute.googleapis.com/projects/{resource.parent_scope_id}"
        f"/zones/{profile.zone}/instances/{resource.resource_name}"
    )


def _finding_values(
    finding: NativeFinding,
    resource: Resource | None = None,
    profile: InstanceProfile | None = None,
    export_id: str = "",
) -> dict[str, Any]:
    """Projecao do achar nativo GCP nos caminhos documentados de ``finding.*`` E do envelope.

    As colunas de ENVELOPE que a pagina de export lista (``source_id``, ``finding_id``,
    ``event_time``, ``bulk_export_id``, ``resource``) sao emitidas ACHATADAS junto dos 68
    filhos de ``finding``: o verificador de fidelidade compara as chaves de TOPO da linha,
    entao os 68 caminhos precisam estar no topo para casar com a spec, e o envelope tem de
    estar no mesmo nivel que eles. O container ``finding`` fica representado pelos seus
    filhos -- a proveniencia declara isso em ``required_empty_declared`` e
    ``container_representation`` --, em vez de duplicar os 68 campos dentro de um objeto.

    So os campos que o modelo canonico realmente carrega aparecem aqui; o resto fica no
    vazio do seu tipo (ver :func:`_empty_value`). As ausencias deliberadas:

    * ``finding.state`` / ``finding.severity`` / ``finding.mute`` / ``finding.findingClass``
      -- sao enums cujas constantes a propria spec registra como nao transcritas; a
      severidade nativa (``CRITICAL|HIGH|MEDIUM|LOW``) e a convencao do estado, nao um
      literal SCC verificado.
    * ``finding.sourceProperties`` -- o unico saco de propriedades do estado e
      ``evidence_json`` (chaves ``synthetic``/``rule``), cujas chaves a forma SCC nao
      define; espalha-lo escreveria ``synthetic`` num campo real.
    * ``finding.moduleName`` -- ver ``open_questions``: o vocabulario do modelo ali e o do
      ASFF (limites 1-512 do generator id), nao um modulo do SCC.
    * ``finding.canonicalName`` -- a spec transcreve so "The canonical name of the finding",
      sem a forma do valor; ``finding.name`` ja carrega a forma que ela publica.

    Os campos que o modelo ganhou e esta spec documenta sao projetados: ``finding.name``,
    ``finding.parent``, ``finding.category``, ``finding.description``,
    ``finding.resourceName`` (a forma completa do recurso, com a zona do perfil) e
    ``finding.eventTime``/``finding.createTime``, ambos do UNICO instante do modelo
    (``first_observed_at``): o SCC publica dois instantes (deteccao e criacao do registro) e
    o modelo tem um; a coincidencia esta registrada em ``value_domains``.
    """
    return {
        # Envelope da LINHA (as colunas de topo da tabela `findings`).
        "source_id": _source_id(),
        "finding_id": finding_id(finding),
        "event_time": _event_time(finding.first_observed_at),
        "bulk_export_id": export_id,
        # O objeto SCC `Resource` desta coluna nao tem pagina alcancavel (404 na consulta da
        # spec) e nenhuma pagina publica a sua estrutura: presente e VAZIO, como o container
        # -- um objeto sem campos publicados nao vira estrutura inventada.
        "resource": {},
        # Os 68 caminhos documentados do objeto Finding, achatados.
        "finding.name": f"{_SCC_SOURCE_NAME}/findings/{finding_id(finding)}",
        "finding.parent": _SCC_SOURCE_NAME,
        "finding.resourceName": _resource_name(resource, profile),
        "finding.category": finding.category,
        "finding.description": finding.description,
        "finding.eventTime": _instant(finding.first_observed_at),
        "finding.createTime": _instant(finding.first_observed_at),
    }


def _gcp_findings(estate: CanonicalEstate) -> list[NativeFinding]:
    """Achados nativos GCP, em ordem estavel (``finding_id``)."""
    return sorted(
        (finding for finding in estate.findings if finding.provider == "gcp"),
        key=lambda finding: finding.finding_id,
    )


def _populated_names(rows: list[dict[str, Any]]) -> list[str]:
    """Caminhos que carregam valor em AO MENOS uma linha, na ordem da spec.

    Usa ``is_empty_value`` do proprio nucleo de fidelidade, para que o numero relatado aqui
    seja o mesmo que ``populated_of`` mede no arquivo entregue.
    """
    if not rows:
        return []
    return [name for name in rows[0] if any(not is_empty_value(row.get(name)) for row in rows)]


def _required_empty_declared(spec: SurfaceSpec, populated: list[str]) -> list[dict[str, str]]:
    """As colunas ``required`` da spec que NAO carregam valor, com o motivo declarado.

    Derivada da spec (nao de uma lista literal): se uma coluna obrigatoria passar a receber
    valor, ela sai daqui sozinha; se a spec ganhar uma obrigatoria nova que ninguem
    preenche, ela aparece AQUI sem motivo -- e o teste da superficie falha, que e o ponto.
    """
    razoes = {
        "finding": (
            "o container que a pagina de export exige; o artefato entrega os 68 filhos "
            "ACHATADOS e o container fica representado por eles (ver container_representation)"
        ),
    }
    return [
        {"column": name, "reason": razoes.get(name, "SEM MOTIVO DECLARADO: pendencia")}
        for name in spec.required_names
        if name not in set(populated)
    ]


def _source_id() -> str:
    """Id da fonte SCC: o ultimo segmento do nome de fonte que a documentacao exige."""
    return _SCC_SOURCE_NAME.rsplit("/", 1)[-1]


def finding_id(finding: NativeFinding) -> str:
    """O id do achado na forma que a spec documenta: alfanumerico, <= 32 caracteres.

    A pagina de export declara exatamente esse dominio para ``finding_id``. A identidade do
    estado e um UUIDv5 (36 caracteres, com hifen), entao o id e a MESMA identidade na forma
    hexadecimal sem hifen: 32 caracteres alfanumericos, estavel e 1:1 com o achado. O
    ``finding.name`` e ``row_keys`` usam este mesmo valor -- um achado, um id.
    """
    return finding.finding_id.replace("-", "")


def _bulk_export_id(estate: CanonicalEstate, findings: list[NativeFinding]) -> str:
    """Id do job de export, um UUID como a pagina documenta para o bulk export.

    A coluna e "a UUID" no bulk export e VAZIA no continuous. Este artefato e o snapshot que
    o comando de bulk export produz (``gcloud scc findings export-to-bigquery``), entao ele
    carrega o id do job: derivado de ``(seed, sim_now, numero de achados)``, o mesmo estado
    produz sempre o mesmo id.
    """
    chave = f"scc/bulk-export/{estate.seed}/{estate.sim_now.isoformat()}/{len(findings)}"
    return str(uuid.uuid5(_EXPORT_NS, chave))


def _event_time(moment: datetime | None) -> str:
    """O instante da coluna de LINHA ``event_time``, na forma do unico exemplo publicado.

    A spec registra (secao 5) que o exemplo oficial desta coluna e
    ``2019-09-26 12:48:00.985000 UTC`` -- ou seja, **nao** e RFC 3339 -- e nao publica o
    TIPO da coluna. Seguindo a unica evidencia que existe para ela, o valor sai nessa forma;
    o campo ``finding.eventTime`` do objeto Finding continua saindo em RFC 3339, porque a
    declaracao de tipo DELE e "string (Timestamp format)". Dois campos, duas evidencias.
    """
    if moment is None:
        return ""
    return f"{moment.astimezone(UTC).strftime('%Y-%m-%d %H:%M:%S.%f')} UTC"


def _table_columns(spec: SurfaceSpec) -> list[dict[str, str]]:
    """As colunas de TOPO da tabela ``findings`` e o que este artefato faz com cada uma.

    Derivada de ``non_emittable_names`` (nao de uma lista literal): sao exatamente as
    colunas cujo tipo BigQuery a pagina de export NAO publica. Se a spec ganhar o tipo de
    alguma, ela sai desta lista sozinha.
    """
    disposicao = {
        "source_id": "emitida com valor: o id da fonte (ultimo segmento do nome de fonte documentado)",
        "finding_id": "emitida com valor: o id do achado na forma documentada (alfanumerico, <= 32)",
        "event_time": "emitida com valor: first_observed_at, na forma do unico exemplo publicado",
        "bulk_export_id": "emitida com valor: o id do job de bulk export (UUID, forma documentada)",
        "resource": "emitida VAZIA: a pagina remete ao objeto Resource e nenhuma estrutura foi obtida (404)",
        "finding": (
            "NAO emitida como chave: o container exigido fica representado pelos 68 filhos "
            "achatados (ver container_representation)"
        ),
    }
    return [
        {
            "column": name,
            "published_type": "none",
            "disposition": disposicao.get(name, "sem tipo publicado na documentacao oficial"),
        }
        for name in sorted(spec.non_emittable_names)
    ]


class GcpSccFindingsRenderer:
    """Projeta o estado canonico nos caminhos documentados do export SCC -> BigQuery."""

    name = "gcp_scc_findings"

    def build_rows(self, estate: CanonicalEstate) -> list[dict[str, Any]]:
        """Linhas planas (uma por achado GCP), na ordem da spec; puro, sem filesystem."""
        spec = scc_findings_spec()
        resources = _resources(estate)
        profiles = _profiles(estate)
        findings = _gcp_findings(estate)
        export_id = _bulk_export_id(estate, findings)
        return [
            row_for(
                spec,
                _finding_values(
                    finding,
                    resources.get(finding.resource_uuid),
                    profiles.get(finding.resource_uuid),
                    export_id,
                ),
                declared_untyped=_EMITTED_WITHOUT_PUBLISHED_TYPE,
            )
            for finding in findings
        ]

    def _provenance(self, estate: CanonicalEstate, rows: list[dict[str, Any]]) -> dict[str, Any]:
        """Relatorio (arquivo IRMAO): mecanismo documentado, contagens, lacunas e grafia."""
        spec = scc_findings_spec()
        findings = _gcp_findings(estate)
        populated = _populated_names(rows)
        return {
            "surface": spec.surface,
            "spec": f"specs/{_SPEC_FILE}",
            "kind": "provenance",
            "artifacts": [_ROWS_FILE],
            "artifact_field_names": (
                "the name the specification gives each documented field; a repeated field is spelled "
                "`nome[]`, as the provider's field table spells it"
            ),
            "naming": {
                "wire_names": wire_naming(spec),
                "note": (
                    "the provider's JSON serialization drops the `[]` on a repeated field; use this map "
                    "to hand a finding to a client parser. The artifact keeps the documented spelling so "
                    "it stays comparable, field by field, with the specification."
                ),
            },
            "mechanism": {
                "destination": "BigQuery table `findings`",
                "dataset": "created by the user; the documentation fixes neither name nor location (UNVERIFIED)",
                "clustering": list(_CLUSTERING_COLUMNS),
                "row_semantics": (
                    "each new finding and its subsequent updates are added as new rows "
                    "(same source_id/finding_id, different event_time)"
                ),
                "bulk_export": "gcloud scc findings export-to-bigquery PARENT --dataset=DATASET_NAME; appends, never overwrites",
                "file_format": None,
                "manifest": None,
                "ddl_emitted": False,
                "ddl_reason": (
                    "the six top-level columns of the `findings` table have no published BigQuery "
                    "type; four of them are required and `finding` is the RECORD hosting the 68 "
                    "documented subfields, so no typed DDL can be written without inventing a type"
                ),
            },
            "columns": {
                "documented": len(spec.columns),
                "emitted": len(rows[0]) if rows else 0,
                "without_published_type": len(spec.non_emittable_names),
                "container_not_emitted": len(_required_empty_declared(spec, populated)),
            },
            "populated_paths": populated,
            "populated_count": len(populated),
            # O invariante que o auditor mede (``obrig.vazias``): toda coluna ``required`` da
            # spec ou carrega valor, ou esta DECLARADA aqui com o motivo. Uma obrigatoria
            # vazia e nao declarada e uma pendencia, e o teste falha.
            "required_empty_declared": _required_empty_declared(spec, populated),
            "container_representation": {
                "column": "finding",
                "represents": sorted(name for name in populated if name.startswith("finding.")),
                "note": (
                    "the export page requires the `finding` column and the 68 Finding subfields. This "
                    "artifact emits the subfields FLATTENED (finding.name, finding.description, ...) "
                    "because the fidelity core compares the row's TOP-LEVEL keys with the spec names, so "
                    "the subfields have to sit at the top to match; the `finding` container is therefore "
                    "represented by its children and is NOT emitted as a key (emitting it empty would "
                    "assert an empty record, and nesting it would hide the 68 children from the "
                    "comparison). Not an omission: the representation is declared here."
                ),
            },
            "value_domains": {
                "source_id": (
                    "the SCC source id: the last segment of the documented source name "
                    "organizations/{org}/sources/{source}"
                ),
                "finding_id": (
                    "the estate's finding identity in the documented domain (alphanumeric, at most 32 "
                    "characters): the UUIDv5 hex form without hyphens, stable and 1:1 with the finding. "
                    "finding.name and row_keys use the SAME id"
                ),
                "event_time": (
                    "InstanceProfile-independent: NativeFinding.first_observed_at. The column's only "
                    "published evidence of its value form is the export page's example "
                    "'2019-09-26 12:48:00.985000 UTC' (the spec registers that this example is NOT RFC "
                    "3339), so the row column follows that form while finding.eventTime keeps RFC 3339, "
                    "the form the Finding object's own type declaration states"
                ),
                "bulk_export_id": (
                    "the column is 'a UUID' for bulk exports and empty for continuous ones. This artifact "
                    "is the snapshot the bulk export command produces, so it carries the job id: a "
                    "deterministic UUIDv5 of (seed, sim_now, finding count). TODO-verificar: the service "
                    "assigns the real id; the SHAPE is documented, the value is ours"
                ),
                "resource": (
                    "present and EMPTY: the export page points at 'the API reference for the Resource "
                    "object' and every SCC REST path tried for it returned 404, so no inner field name is "
                    "published to put here"
                ),
                "finding.description": (
                    "NativeFinding.description is the neutral description the model carries (the model's own "
                    "docstring names the SCC `description` as its target); a finding without one emits the "
                    "empty value rather than assembled prose"
                ),
                "finding.eventTime": (
                    "NativeFinding.first_observed_at (a timezone-aware instant) -> the documented 'time the "
                    "finding was first detected', as an RFC 3339 date string"
                ),
                "finding.createTime": (
                    "the SAME modelled instant. SCC publishes two instants (detection and record creation) "
                    "and the model carries one (first_observed_at); the collapse is explicit here, and "
                    "splitting them is a model change, not a renderer decision"
                ),
                "finding.name/finding.parent": (
                    "the documented shapes organizations/{org}/sources/{src}/findings/{id} and "
                    "organizations/{org}/sources/{src} built from the estate's org number and the finding id"
                ),
                "finding.resourceName": (
                    "the documented full resource name "
                    "//compute.googleapis.com/projects/<p>/zones/<z>/instances/<n>, built from the "
                    "resource's project and name plus the ZONE of its InstanceProfile. A finding whose "
                    "resource has no profile, or is not a compute instance, leaves it empty: this spec "
                    "cites the shape of an instance only"
                ),
            },
            "table_columns": _table_columns(spec),
            # As tres colunas de clustering agora SAO emitidas, e a identidade de linha
            # documentada continua registrada aqui junto do uuid do recurso -- a juncao P2
            # entre os planos, que spec nenhuma desta superficie tem coluna para carregar.
            "row_keys": [
                {
                    "source_id": _source_id(),
                    "finding_id": finding_id(finding),
                    "event_time": _event_time(finding.first_observed_at),
                    "resource_uuid": finding.resource_uuid,
                }
                for finding in findings
            ],
            "rows": len(rows),
            "model_gaps": [
                {
                    "item": "forma de nome completo para tipos que nao sejam instancia",
                    "reason": (
                        "a spec cita a forma publicada de uma instancia Compute "
                        "(//compute.googleapis.com/projects/<p>/zones/<z>/instances/<n>); para um achado "
                        "cujo recurso e um cluster GKE ou um banco Cloud SQL nao ha forma citada, entao "
                        "finding.resourceName fica vazio em vez de montar uma por analogia"
                    ),
                },
                {
                    "item": "constantes das enumeracoes State/Severity/Mute/FindingClass",
                    "reason": (
                        "a spec registra as constantes como nao transcritas; os campos de enum saem "
                        "vazios em vez de afirmar um literal nao verificado"
                    ),
                },
                {
                    "item": "propriedades de origem do achado",
                    "reason": (
                        "o estado carrega evidence_json (chaves synthetic/rule), que a forma SCC nao "
                        "define; sourceProperties sai vazio em vez de espalhar o marcador"
                    ),
                },
                {
                    "item": "procedencia com vocabulario do ASFF",
                    "reason": (
                        "NativeFinding carrega title, types (namespace/category/classifier), generator_id, "
                        "product_name, company_name, confidence e criticality. O objeto Finding v1 nao tem "
                        "campo de title, confidence nem criticality; `types` e a forma do ASFF e product/"
                        "company sao ProductName/CompanyName do ASFF. Nenhum deles vai para o vocabulario do "
                        "SCC por analogia."
                    ),
                },
                {
                    "item": "estrutura do campo `resource` da tabela findings",
                    "reason": (
                        "a pagina de export remete ao objeto Resource da API SCC, cujas paginas REST "
                        "retornaram 404 na consulta; nenhum campo e gerado sem pagina"
                    ),
                },
            ],
            "open_questions": [
                {
                    "item": "finding.moduleName <- NativeFinding.generator_id",
                    "note": (
                        "moduleName e 'unique identifier of the module which generated the finding' e "
                        "generator_id e a procedencia do gerador. O modelo declara para esse campo os "
                        "limites que a documentacao do ASFF publica (generator 1-512), entao o vocabulario "
                        "nao e comprovadamente o do SCC: o campo fica VAZIO ate a decisao do mantenedor."
                    ),
                }
            ],
        }

    def render(self, estate: CanonicalEstate, out_dir: Path) -> list[Path]:
        """Escreve ``findings_rows.json`` (os registros) e ``_provenance.json`` (o relatorio)."""
        target = out_dir / "gcp_scc_findings"
        target.mkdir(parents=True, exist_ok=True)
        rows = self.build_rows(estate)
        rows_path = target / _ROWS_FILE
        rows_path.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        provenance_path = target / _PROVENANCE_FILE
        provenance_path.write_text(
            json.dumps(self._provenance(estate, rows), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return [rows_path, provenance_path]
