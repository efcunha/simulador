"""Cloud Asset Inventory ``ExportAssets`` for ``compute.googleapis.com/Instance``.

The documented mechanism (``specs/gcp/cloud-asset-inventory-compute-instance.md``)
---------------------------------------------------------------------------------
``ExportAssets`` is real and officially documented, with two destinations:

  * **Cloud Storage** -- "the output format is newline-delimited JSON. Each line
    represents a ``google.cloud.asset.v1.Asset`` in the JSON format", sharded as
    ``<prefix>/<asset type>/<shard number>``;
  * **BigQuery** -- "for BigQuery table destinations, the output table stores the fields in
    asset Protobuf as columns", and the service itself CREATES the table ("If this table
    does not exist, a new table with the given name will be created"). No customer DDL is
    part of the documented mechanism, and with ``separateTablesPerAssetType`` the table
    name is ``<table>_<assetType with non-alphanumerics replaced by _>``.

So this renderer emits asset DATA and the export REQUEST, never a ``CREATE TABLE``: the
table is the service's, and the schemas Google publishes (RESOURCE / IAM_POLICY /
ORG_POLICY) are what the data lands in. ``assets.ndjson`` is the delivered Cloud Storage
file, one Asset record per line, and one artifact per documented set carries that set's
fields at the level the spec spells and the fidelity core compares.

Artifact and report are separate files, always: every artifact emitted here carries ONLY
documented fields, and everything about provenance -- the spec, the mechanism, the model
gaps, the counts, the provider's JSON spelling of a repeated field -- lives in the SIBLING
``_provenance.json``. An ingester of an artifact must never see a key no cloud documents.
The artifacts key each field by the name the DOCUMENTATION gives it (``ancestors[]``, as
the provider's field table and the spec spell a repeated field); ``naming.wire_names`` in
the provenance carries the bracket-free spelling the provider's JSON serialization uses.

What is projected, and what stays empty
---------------------------------------
Only ``compute.googleapis.com/Instance`` assets are emitted: that is the surface's asset
type (the spec is named for it, and ``supported-asset-types`` lists it), and the estate's
other GCP resource types have no documented asset-type mapping in this spec, so minting
one would be invention. Per instance the model really carries:

  * ``assetType`` -> ``compute.googleapis.com/Instance``;
  * ``ancestors`` -> ``["projects/<project>", "folders/<folder>", "organizations/<org>"]``,
    read from ``estate.gcp_orgs`` (the documented shape is exactly that example);
  * ``name`` -> the documented full name of the asset
    ``//compute.googleapis.com/projects/<p>/zones/<z>/instances/<n>``, whose ZONE comes from
    the resource's ``InstanceProfile`` (a resource without a profile keeps it empty: the
    zone is identity, and inventing one would be inventing identity);
  * ``resource.location`` -> the profile's ZONE ("the location of the resource ... such as
    its zone and region"), falling back to ``Resource.region_id``.

Everything else is present and EMPTY, and the reasons are in ``_provenance.json``:

  * ``resource.parent`` needs the resource's immediate parent, and no CAI page consulted
    states which level that is for an instance (the published example is a project, for a
    project-type asset), so it stays empty;
  * ``resource.data`` is documented only as "object (Struct format)"; the concrete shape
    for ``compute.googleapis.com/Instance`` is explicitly UNVERIFIED, and the mapping to
    the Compute Engine Instances REST representation "is NOT asserted anywhere in the CAI
    documentation". It stays empty rather than carrying data the docs do not map;
  * ``iamPolicy``/``orgPolicy``/``osInventory``/``accessPolicy``/``accessLevel``/
    ``servicePerimeter``/``assetExceptions``/``relatedAsset``: the estate models none of
    them (and the OS-inventory, VPCSC, relationship and DEPRECATED ``relatedAssets``
    schemas are registered as unverified in the spec -- ``relatedAssets`` is not emitted at
    all, because the server "will never generate responses with this field").
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from datetime import date
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
from tools.synthetic_clouds.model.resource import Resource
from tools.synthetic_clouds.render.base import RenderError

#: A spec de origem, sob ``specs/`` (nunca editada aqui).
_SPEC_FILE = "gcp/cloud-asset-inventory-compute-instance.schema.json"

#: O asset type desta superficie (a spec e nomeada por ele; supported-asset-types o lista).
_ASSET_TYPE = "compute.googleapis.com/Instance"
_GCP = "gcp"
_INSTANCE_TYPE = "compute_instance"

#: Nome de dataset/tabela escolhido pelo OPERADOR: a documentacao cria o dataset mas nao
#: fixa nome nem regiao (UNVERIFIED na spec), entao o renderer decide onde escrever -- o
#: mesmo padrao de ``GcpBigQueryTopologyRenderer(project=..., user_dataset=...)``.
_DEFAULT_DATASET = "cloud_asset_inventory"
_DEFAULT_TABLE = "assets"
_DEFAULT_PREFIX = "cloud-asset-inventory"

#: Tipo de conteudo documentado cuja tabela e o schema RESOURCE.
_CONTENT_TYPE_RESOURCE = "RESOURCE"

#: Classe de caracteres de um nome de bucket Cloud Storage (minusculas, digitos, hifen/ponto,
#: 3-63 caracteres). Nao e usada para CORRIGIR nome nenhum: um nome fora da classe e pulado
#: na escolha do destino, porque a URI entregue tem de ser uma URI valida.
_BUCKET_PATTERN = re.compile(r"[a-z0-9][a-z0-9._-]{1,61}[a-z0-9]")

#: Conjunto da spec -> arquivo que carrega aquele conjunto. A tabela cobre TODOS os
#: conjuntos nomeados da spec: um conjunto que a documentacao publica nao pode ficar sem
#: artefato em silencio (o teste confere as chaves contra ``spec.set_names``).
ARTIFACT_BY_SCOPE: dict[str, str] = {
    "resource_schema": "resource_schema_rows.json",
    "iam_policy_schema": "iam_policy_schema_rows.json",
    "org_policy_schema": "org_policy_schema_rows.json",
    "asset_message": "assets.ndjson",
    "resource_message": "resource_messages.json",
    "export_request": "export_request.json",
    "gcs_destination": "gcs_destination.json",
    "bigquery_destination": "bigquery_destination.json",
    "partition_key_enum": "partition_key_enum.json",
    "partition_extra_column": "partition_extra_columns.json",
}

#: O arquivo ENTREGUE ao Cloud Storage (o unico formato de arquivo que a spec documenta):
#: newline-delimited JSON, um Asset por linha. E o artefato do conjunto ``asset_message``.
_NDJSON_FILE = "assets.ndjson"

#: O relatorio de proveniencia: arquivo IRMAO, nunca misturado com o registro do export.
_PROVENANCE_FILE = "_provenance.json"

#: Tipos cujo vazio e um objeto sem campos; todo tipo NAO escalar cai aqui.
_RECORD_TYPES = frozenset({"record", "struct", "map", "object", "message"})
_ARRAY_PREFIXES = ("array", "repeated", "list of")


@cache
def asset_inventory_spec() -> SurfaceSpec:
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

    Limitacao registrada: a spec publica tambem um ``mode`` (NULLABLE/REPEATED) por coluna
    BigQuery, que o leitor normativo (``fidelity.spec.Column``) NAO expoe. Por isso um
    RECORD repetido sem o sufixo ``[]`` no nome sai como objeto vazio, nao como lista --
    continua sendo ausencia de valor, que e o que o contrato exige.
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


def row_for(columns: Sequence[Column], values: Mapping[str, Any]) -> dict[str, Any]:
    """Linha com EXATAMENTE as colunas do CONJUNTO que PERTENCEM ao formato.

    Uma coluna so entra se ``belongs_to_schema``: ``relatedAssets`` (deprecated, sem
    contrato) nunca entra, mesmo que ``values`` traga um valor para ela.
    """
    return {
        column.name: values.get(column.name, _empty_value(column))
        for column in columns
        if column.belongs_to_schema
    }


def wire_naming(spec: SurfaceSpec, scope: str) -> dict[str, str]:
    """Mapa ``nome documentado -> nome JSON do provedor``, so para os campos repetidos.

    O artefato carrega o nome que a DOCUMENTACAO da ao campo (``ancestors[]``); a
    serializacao JSON do provedor dispensa os colchetes. O mapa e publicado na proveniencia
    para que um cliente converta o registro sem adivinhar.
    """
    return {
        column.name: column.name[:-2]
        for column in spec.columns_for(scope)
        if column.belongs_to_schema and column.name.endswith("[]")
    }


def _required_empty_declared(spec: SurfaceSpec, populated: list[str]) -> list[dict[str, str]]:
    """As colunas `required` da spec que NAO carregam valor, com o motivo declarado.

    O invariante do auditor (`obrig.vazias`): uma obrigatoria vazia e uma pendencia ATE ser
    explicada. Aqui a lista e derivada da spec e hoje sai VAZIA -- `outputConfig`,
    `dataset` e `table` carregam valor nos artefatos do pedido e do destino BigQuery --,
    mas o campo existe para que uma obrigatoria nova apareca como pendencia em vez de passar.
    """
    return [
        {"column": name, "reason": "SEM MOTIVO DECLARADO: pendencia"}
        for name in spec.required_names
        if name not in set(populated)
    ]


def _ndjson_rows(text: str) -> list[dict[str, Any]]:
    """Linhas de um NDJSON como objetos (o formato que a spec documenta para o GCS)."""
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _populated_names(rows: list[dict[str, Any]]) -> list[str]:
    """Caminhos que carregam valor em AO MENOS uma linha, na ordem da spec.

    Usa ``is_empty_value`` do proprio nucleo de fidelidade, para que o numero relatado aqui
    seja o mesmo que ``populated_of`` mede no arquivo entregue.
    """
    if not rows:
        return []
    return [name for name in rows[0] if any(not is_empty_value(row.get(name)) for row in rows)]


def _gcp_instances(estate: CanonicalEstate) -> list[Resource]:
    """As instancias Compute GCP do estado, em ordem estavel (uuid)."""
    return sorted(
        (r for r in estate.resources if r.identity.provider == _GCP and r.resource_type == _INSTANCE_TYPE),
        key=lambda r: r.identity.uuid,
    )


def _hierarchy(estate: CanonicalEstate) -> tuple[dict[str, tuple[str, str]], str]:
    """Mapa ``project_id -> (folder_id, org_id)`` e o primeiro project id do estado.

    A hierarquia e do proprio modelo (``GcpOrg.folders[].projects[]``); nada e derivado de
    um literal fixo.
    """
    index: dict[str, tuple[str, str]] = {}
    first = ""
    for org in estate.gcp_orgs:
        for folder in org.folders:
            for project in folder.projects:
                index.setdefault(project.project_id, (folder.folder_id, org.org_id))
                first = first or project.project_id
    return index, first


def _ancestors(project_id: str, index: Mapping[str, tuple[str, str]]) -> list[str]:
    """Caminho de ancestralidade do asset (forma publicada: projetos, pastas, organizacoes)."""
    folder_id, org_id = index.get(project_id, ("", ""))
    return [name for name in (f"projects/{project_id}", folder_id, org_id) if name]


def _profiles(estate: CanonicalEstate) -> dict[str, InstanceProfile]:
    """Os perfis de instancia GCP, por ``resource_uuid`` (FK do modelo, sem orfaos)."""
    return {
        profile.resource_uuid: profile for profile in estate.instance_profiles if profile.provider == _GCP
    }


def _asset_name(instance: Resource, profile: InstanceProfile | None) -> str:
    """O nome completo do asset, na forma que a propria descricao do campo publica.

    ``Asset.name``: "The full name of the asset. Example:
    ``//compute.googleapis.com/projects/my_project_123/zones/zone1/instances/instance1``". A
    forma e derivada do projeto, da ZONA e do nome do recurso; sem zona (nenhum perfil) o
    nome NAO e montado -- inventar a zona seria inventar identidade.
    """
    zone = profile.zone if profile is not None else None
    if not zone:
        return ""
    return (
        f"//compute.googleapis.com/projects/{instance.parent_scope_id}"
        f"/zones/{zone}/instances/{instance.resource_name}"
    )


def _location(instance: Resource, profile: InstanceProfile | None) -> str:
    """Localizacao do recurso: "such as its zone and region" -- a zona quando ha perfil.

    A tabela publicada do schema RESOURCE diz "Localizacao do recurso (zona/regiao)"; o
    perfil de instancia carrega a zona, entao ela e a leitura mais precisa, e a regiao
    continua sendo o valor quando nao ha perfil.
    """
    if profile is not None and profile.zone:
        return profile.zone
    return instance.region_id


def _asset_values(
    instance: Resource,
    profile: InstanceProfile | None,
    index: Mapping[str, tuple[str, str]],
) -> dict[str, Any]:
    """Valores do envelope ``Asset`` para uma instancia (ver o modulo para as ausencias).

    O campo ``resource`` recebe a mensagem ``Asset.Resource`` COMPLETA (os 7 campos que a
    spec publica, vazios onde o modelo nao projeta): uma linha do export nao pode carregar
    um record truncado so porque so um subcampo tem valor.
    """
    spec = asset_inventory_spec()
    return {
        "name": _asset_name(instance, profile),
        "assetType": _ASSET_TYPE,
        "resource": row_for(
            spec.columns_for("resource_message"), _resource_message_values(instance, profile)
        ),
        "ancestors[]": _ancestors(instance.parent_scope_id, index),
    }


def _resource_message_values(instance: Resource, profile: InstanceProfile | None) -> dict[str, Any]:
    """Valores da mensagem ``Asset.Resource``.

    ``data`` fica vazio por lacuna da SPEC, nao do modelo: a forma concreta de
    ``resource.data`` para ``compute.googleapis.com/Instance`` e UNVERIFIED, e a propria spec
    registra que a correspondencia com a representacao REST de Instances "nao e afirmada em
    nenhuma pagina". O perfil de instancia agora carrega os campos de maquina, mas projetar
    a forma REST dentro de ``data`` afirmaria exatamente essa correspondencia.
    """
    return {
        "location": _location(instance, profile),
    }


def _resource_table_values(
    instance: Resource,
    profile: InstanceProfile | None,
    index: Mapping[str, tuple[str, str]],
) -> dict[str, Any]:
    """Valores do schema BigQuery RESOURCE (a tabela unica de ``contentType=RESOURCE``)."""
    return {
        "name": _asset_name(instance, profile),
        "asset_type": _ASSET_TYPE,
        "resource.location": _location(instance, profile),
        "ancestors": _ancestors(instance.parent_scope_id, index),
    }


def _policy_table_values(
    instance: Resource,
    profile: InstanceProfile | None,
    index: Mapping[str, tuple[str, str]],
) -> dict[str, Any]:
    """Valores dos schemas IAM_POLICY / ORG_POLICY: nada de politica e modelado.

    O que o estado carrega de uma instancia e a identidade do asset (``name``, ``asset_type``
    e a ancestralidade); a politica IAM e a politica de organizacao nao existem no modelo,
    entao todos os seus campos saem vazios em vez de plausiveis.
    """
    return {
        "name": _asset_name(instance, profile),
        "asset_type": _ASSET_TYPE,
        "ancestors": _ancestors(instance.parent_scope_id, index),
    }


def _timestamp(day: date) -> str:
    """RFC 3339 (Z-normalizado) do dia -- o unico instante que um dia comporta."""
    return f"{day.isoformat()}T00:00:00Z"


def _bucket_name(estate: CanonicalEstate) -> tuple[str, int]:
    """Bucket GCS do estado para o destino Cloud Storage, e quantos nomes foram pulados.

    O destino e escolha do operador; usar um bucket que existe no proprio estado evita
    inventar um nome de bucket, e o prefixo/shard e a forma publicada. O gerador produz
    nomes deliberadamente fora do padrao (FR-D3) e um nome com maiusculas/underscore nao e
    um nome de bucket GCS valido, entao os que nao satisfazem a classe de caracteres
    publicada sao PULADOS (e contados no manifesto, nunca corrigidos).
    """
    buckets = sorted(
        r.resource_name for r in estate.resources if r.identity.provider == _GCP and r.resource_type == "gcs_bucket"
    )
    valid = [name for name in buckets if _BUCKET_PATTERN.fullmatch(name) is not None]
    return (valid[0] if valid else "", len(buckets) - len(valid))


def _gcs_destination_values(uri_prefix: str) -> dict[str, Any]:
    """``GcsDestination``: um dos ``object_uri`` -- aqui, o prefixo (o formato e NDJSON)."""
    return {"uriPrefix": uri_prefix}


def _bigquery_table_for_asset_type(table: str) -> str:
    """Nome da tabela por asset type, pela REGRA publicada (nao alfanumerico vira ``_``)."""
    suffix = "".join(char if char.isalnum() else "_" for char in _ASSET_TYPE)
    return f"{table}_{suffix}"


class GcpAssetInventoryRenderer:
    """Projeta o estado canonico no export Cloud Asset Inventory de instancias Compute."""

    name = "gcp_asset_inventory"

    def __init__(
        self,
        *,
        dataset: str = _DEFAULT_DATASET,
        table: str = _DEFAULT_TABLE,
        prefix: str = _DEFAULT_PREFIX,
    ) -> None:
        self.dataset = dataset
        self.table = table
        self.prefix = prefix

    def build_artifacts(self, estate: CanonicalEstate) -> dict[str, Any]:
        """Mapa ``arquivo -> payload`` (puro, sem filesystem).

        Um artefato por conjunto nomeado da spec (``ARTIFACT_BY_SCOPE``): o conjunto
        ``asset_message`` e o proprio NDJSON entregue ao Cloud Storage, e os demais sao
        arquivos JSON. Nenhum deles carrega proveniencia.
        """
        spec = asset_inventory_spec()
        instances = _gcp_instances(estate)
        index, project = _hierarchy(estate)
        read_time = _timestamp(estate.sim_now)
        bucket, _skipped_buckets = _bucket_name(estate)
        uri_prefix = f"gs://{bucket}/{self.prefix}" if bucket else ""
        profiles = _profiles(estate)

        asset_rows = [
            row_for(spec.columns_for("asset_message"), _asset_values(r, profiles.get(r.identity.uuid), index))
            for r in instances
        ]
        resource_rows = [
            row_for(
                spec.columns_for("resource_message"),
                _resource_message_values(r, profiles.get(r.identity.uuid)),
            )
            for r in instances
        ]
        artifacts: dict[str, Any] = {
            "resource_schema_rows.json": [
                row_for(
                    spec.columns_for("resource_schema"),
                    _resource_table_values(r, profiles.get(r.identity.uuid), index),
                )
                for r in instances
            ],
            "iam_policy_schema_rows.json": [
                row_for(
                    spec.columns_for("iam_policy_schema"),
                    _policy_table_values(r, profiles.get(r.identity.uuid), index),
                )
                for r in instances
            ],
            "org_policy_schema_rows.json": [
                row_for(
                    spec.columns_for("org_policy_schema"),
                    _policy_table_values(r, profiles.get(r.identity.uuid), index),
                )
                for r in instances
            ],
            "resource_messages.json": resource_rows,
            "export_request.json": row_for(
                spec.columns_for("export_request"),
                {
                    "readTime": read_time,
                    "assetTypes[]": [_ASSET_TYPE],
                    "contentType": _CONTENT_TYPE_RESOURCE,
                    "outputConfig": {"gcsDestination": _gcs_destination_values(uri_prefix)},
                },
            ),
            "gcs_destination.json": row_for(
                spec.columns_for("gcs_destination"), _gcs_destination_values(uri_prefix)
            ),
            "bigquery_destination.json": row_for(
                spec.columns_for("bigquery_destination"),
                {
                    "dataset": f"projects/{project}/datasets/{self.dataset}",
                    "table": self.table,
                    "separateTablesPerAssetType": True,
                    # O valor mora no CAMINHO documentado: o container ``partitionSpec``
                    # fica no seu vazio e o subcampo e irmao plano, como em ``resource``.
                    "partitionSpec.partitionKey": "READ_TIME",
                },
            ),
            # O conjunto publica os MEMBROS da enumeracao, nao campos: o artefato os carrega
            # pelo nome documentado, sem valor -- a spec nao publica o numero de cada membro.
            "partition_key_enum.json": row_for(spec.columns_for("partition_key_enum"), {}),
            "partition_extra_columns.json": row_for(
                spec.columns_for("partition_extra_column"),
                {"readTime": read_time, "requestTime": read_time},
            ),
            _NDJSON_FILE: "".join(json.dumps(row, sort_keys=True) + "\n" for row in asset_rows),
        }
        return artifacts

    def _provenance(self, estate: CanonicalEstate, artifacts: Mapping[str, Any]) -> dict[str, Any]:
        """Relatorio (arquivo IRMAO): mecanismo publicado, artefato por conjunto e lacunas."""
        spec = asset_inventory_spec()
        instances = _gcp_instances(estate)
        index, project = _hierarchy(estate)
        bucket, skipped_buckets = _bucket_name(estate)
        rows = _ndjson_rows(str(artifacts[_NDJSON_FILE]))
        return {
            "surface": spec.surface,
            "spec": f"specs/{_SPEC_FILE}",
            "kind": "provenance",
            "asset_type": _ASSET_TYPE,
            "artifacts": [*sorted(name for name in artifacts if name != _NDJSON_FILE), _NDJSON_FILE],
            "artifacts_by_scope": dict(sorted(ARTIFACT_BY_SCOPE.items())),
            "artifact_field_names": (
                "the name the specification gives each documented field; a repeated field is spelled "
                "`nome[]`, as the provider's field table spells it"
            ),
            "naming": {
                "wire_names": wire_naming(spec, "asset_message"),
                "note": (
                    "the provider's JSON serialization drops the `[]` on a repeated field; use this map "
                    "to hand an Asset line to a client parser. The artifact keeps the documented spelling "
                    "so it stays comparable, field by field, with the specification."
                ),
            },
            "mechanism": {
                "method": "cloudasset.googleapis.com/v1/{parent=*/*}:exportAssets",
                "destinations": ["Cloud Storage (newline-delimited JSON)", "BigQuery (fields as columns)"],
                "cloud_storage_format": "newline-delimited JSON; each line is one google.cloud.asset.v1.Asset",
                "cloud_storage_sharding": f"<uriPrefix>/<asset type>/<shard number>, example {_ASSET_TYPE}/0",
                "cloud_storage_bucket": bucket,
                "cloud_storage_bucket_source": (
                    "an estate gcs_bucket whose name satisfies the Cloud Storage bucket-name character "
                    f"class; {skipped_buckets} off-standard name(s) skipped (FR-D3), never rewritten"
                ),
                "bigquery_table_created_by": "the ExportAssets service creates the table; no customer DDL",
                "bigquery_per_asset_type_table": _bigquery_table_for_asset_type(self.table),
                "bigquery_clustering": "not supported for exports ('Exporting to BigQuery clustered tables isn't supported')",
                "bigquery_nesting_limit": 15,
                "casing_rule": (
                    "RESOURCE content type with per-asset-type tables uses camelCase (assetType); "
                    "all other content types use snake_case (asset_type)"
                ),
                "read_time": _timestamp(estate.sim_now),
                "read_time_note": "the snapshot timestamp; the documented window is the current time minus at most 35 days",
                "dataset": f"projects/{project}/datasets/{self.dataset}",
                "dataset_note": "the dataset is created by the user; the documentation fixes neither name nor region",
                "manifest": None,
                "manifest_note": "no manifest is documented; the long-running Operation is the status object",
            },
            "columns": {
                "documented": len(spec.columns),
                "sets": len(spec.set_names),
                "emitted_per_asset": len(rows[0]) if rows else 0,
                "not_generated": sorted(spec.non_emittable_names),
            },
            "assets": len(instances),
            "populated_paths": _populated_names(rows),
            "populated_count": len(_populated_names(rows)),
            "required_empty_declared": _required_empty_declared(spec, _populated_names(rows)),
            "value_domains": {
                "name / resource_schema.name": (
                    "the documented full name of the asset, built from the resource's project, its "
                    "InstanceProfile ZONE and its name; a resource without a profile leaves it empty"
                ),
                "resource.location / resource.location (BigQuery)": (
                    "the profile ZONE, falling back to Resource.region_id: the published RESOURCE table "
                    "says 'Localizacao do recurso (zona/regiao)'"
                ),
                "ancestors": "the estate hierarchy: projects/<project>, folders/<folder>, organizations/<org>",
                "asset_type": "the documented surface type compute.googleapis.com/Instance",
            },
            "model_gaps": [
                {
                    "item": "forma concreta de resource.data para compute.googleapis.com/Instance",
                    "reason": (
                        "UNVERIFIED na spec: nenhuma pagina do CAI publica o schema de resource.data, e a "
                        "correspondencia com a representacao REST de Instances nao e afirmada. O perfil de "
                        "instancia AGORA carrega os campos de maquina, mas projeta-los dentro de data "
                        "afirmaria exatamente essa correspondencia nao publicada -- entao data fica vazio"
                    ),
                },
                {
                    "item": "Resource.parent de uma instancia",
                    "reason": (
                        "a spec publica como exemplo o pai de um recurso do tipo projeto "
                        "(//cloudresourcemanager.googleapis.com/projects/...); para uma instancia o pai "
                        "imediato seria a zona, e nenhuma pagina consultada afirma isso"
                    ),
                },
                {
                    "item": "mapping resource_type -> asset type",
                    "reason": (
                        "a spec so documenta compute.googleapis.com/Instance; os outros tipos GCP do estado "
                        "(cloud_sql, gcs_bucket, ...) nao viram asset -- o tipo seria inventado"
                    ),
                },
                {
                    "item": "politica IAM e politica de organizacao",
                    "reason": "o estado nao modela IAM nem org policy; as duas tabelas publicadas saem vazias",
                },
                {
                    "item": "updateTime do asset",
                    "reason": "o estado nao modela o instante da ultima atualizacao do recurso",
                },
                {
                    "item": "osInventory / accessPolicy / accessLevel / servicePerimeter / assetExceptions",
                    "reason": (
                        "o estado nao modela inventario de SO, VPCSC nem excecoes; na spec, OS_INVENTORY, "
                        "ACCESS_POLICY e RELATIONSHIP estao registrados como nao transcritos"
                    ),
                },
                {
                    "item": "relatedAssets",
                    "reason": "DEPRECATED na propria documentacao ('The server will never generate responses with this field'): nao e emitido",
                },
            ],
            "notes": [
                "assetType is emitted only for the documented surface type (compute.googleapis.com/Instance)",
                "every artifact keys each field by the name the spec gives it (a repeated field is spelled "
                "nome[]); naming.wire_names carries the provider's bracket-free JSON spelling",
                "the estate's off-standard resource names (FR-D3) are projected verbatim and may not satisfy "
                "the RFC1035 pattern the cloud documents for a resource name",
                f"ancestors derived from estate.gcp_orgs for {len(instances)} instances across "
                f"{len({r.parent_scope_id for r in instances})} projects; folder/org from the estate hierarchy",
                f"resource.data is empty on every asset: {len(rows)} rows checked by the fidelity test",
            ],
            "spec_set_sizes": {name: len(spec.columns_for(name)) for name in spec.set_names},
        }

    def render(self, estate: CanonicalEstate, out_dir: Path) -> list[Path]:
        """Escreve os artefatos do export sob ``out_dir/gcp_asset_inventory/``."""
        target = out_dir / "gcp_asset_inventory"
        target.mkdir(parents=True, exist_ok=True)
        artifacts = self.build_artifacts(estate)
        written: list[Path] = []
        for filename in sorted(artifacts):
            path = target / filename
            payload = artifacts[filename]
            if filename.endswith(".ndjson"):
                path.write_text(str(payload), encoding="utf-8")
            else:
                path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            written.append(path)
        provenance_path = target / _PROVENANCE_FILE
        provenance_path.write_text(
            json.dumps(self._provenance(estate, artifacts), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        written.append(provenance_path)
        return written
