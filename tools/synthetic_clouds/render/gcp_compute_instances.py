"""Compute Engine `Instances`: the documented REST representation of the resource.

This surface is NOT an export
-----------------------------
``specs/gcp/compute-instances-rest.md`` says it in its own words: "Esta superficie **nao e
um export oficial**. E a representacao canonica do recurso, obtida por chamada de API
(GET)". The documented object is the response body of
``GET https://compute.googleapis.com/compute/v1/projects/{project}/zones/{zone}/instances/{instance}``
("If successful, the response body contains data with the following structure"), in
``application/json``, with 48 documented top-level fields. No file format, compression,
delimiter or header is documented for it, because it is not a file at all.

The artifact, and where each value comes from
---------------------------------------------
``instances.json`` -- one record per GCP ``compute_instance`` of the estate, carrying
EXACTLY the 48 documented fields and nothing else. The record's keys are the names the
DOCUMENTATION gives each field (``networkInterfaces[]``, as the provider's field table and
the spec spell a repeated field); the provider's JSON serialization drops the brackets, and
that one mapping is published in ``_provenance.json`` under ``naming.wire_names`` so a
client parser can be handed the documented shape.

==========================  ==================================================
documented field            canonical source
==========================  ==================================================
``kind``                    the documented constant ``compute#instance``
``name``                    ``Resource.resource_name`` (verbatim, FR-D3 included)
``labels``                  ``Resource.tags`` (the documented ``map<string,string>``)
``id``                      ``InstanceProfile.native_id`` (the uint64 the API assigns)
``zone``                    ``InstanceProfile.zone``, in the partial-URL form
``machineType``             ``zones/<zone>/machineTypes/<instance_type>``, the format
                            the field's own description publishes
``status``                  ``InstanceProfile.state`` -> ``RUNNING``/``TERMINATED``, the
                            vocabulary ``model/compute.py`` names for GCP
``creationTimestamp``       ``InstanceProfile.launch_time`` (RFC 3339)
==========================  ==================================================

The other 40 fields are present and EMPTY, with the reason recorded per field family in
``_provenance.json``. Two of those reasons are worth naming here, because they are gaps of
the SPEC and not of the model:

  * the instance profile carries ``private_ip``, ``public_ip``, ``root_volume_size_gb`` and
    ``root_volume_type``, but their only documented homes are
    ``networkInterfaces[].networkIP``/``accessConfigs[].natIP`` and
    ``disks[].initializeParams.*`` -- and this spec transcribes NEITHER: §3.2 lists only the
    nested fields it read, and §4 says the untranscribed ones "devem ser tratados como
    UNVERIFIED ate ser lido na pagina". Emitting ``networkInterfaces: [{"networkIP": ...}]``
    would put an uncited subfield name inside a documented column;
  * ``InstanceProfile.image_id`` is a DISK image (``projects/<p>/global/images/img-...``)
    while the documented ``sourceMachineImage`` is a MACHINE image: different resources, so
    the field stays empty instead of carrying the wrong one.

Provenance never rides inside the artifact: an ingester that reads ``instances.json`` must
see cloud fields only.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
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
from tools.synthetic_clouds.model.compute import STATE_RUNNING, STATE_STOPPED, InstanceProfile
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.resource import Resource
from tools.synthetic_clouds.render.base import RenderError

_SPEC_FILE = "gcp/compute-instances-rest.schema.json"
_GCP = "gcp"
_INSTANCE_TYPE = "compute_instance"

#: O artefato (os registros) e o relatorio de proveniencia, que NUNCA se misturam.
_RECORDS_FILE = "instances.json"
_PROVENANCE_FILE = "_provenance.json"

#: O unico valor constante que a propria documentacao publica para um campo desta superficie.
_KIND = "compute#instance"

#: Vocabulario de ``status``: a documentacao publica PROVISIONING/STAGING/RUNNING/STOPPING/
#: SUSPENDING/SUSPENDED/REPAIRING/TERMINATED e o estado canonico e running/stopped. O proprio
#: ``model/compute.py`` nomeia a traducao do GCP (``RUNNING``/``TERMINATED``). Um estado
#: canonico sem literal publicado sai VAZIO em vez de adivinhado.
_STATE_LITERALS: dict[str, str] = {STATE_RUNNING: "RUNNING", STATE_STOPPED: "TERMINATED"}

#: O padrao publicado para ``name`` ("regex [a-z]([-a-z0-9]*[a-z0-9])?, 1-63 chars, RFC1035").
#: Nao e usado para CORRIGIR nome nenhum -- so para contar, na proveniencia, quantos nomes
#: fora do padrao o gerador produz (FR-D3 e deliberado).
_NAME_PATTERN = re.compile(r"[a-z]([-a-z0-9]*[a-z0-9])?")

#: Tipos cujo vazio e um objeto sem campos; todo tipo NAO escalar cai aqui.
_RECORD_TYPES = frozenset({"record", "struct", "map", "object", "message"})
_ARRAY_PREFIXES = ("array", "repeated", "list of")


@cache
def compute_instances_spec() -> SurfaceSpec:
    """Carrega a spec normativa da superficie; falha FECHADO se ela nao servir."""
    path = DEFAULT_SPECS_ROOT / _SPEC_FILE
    try:
        return load_spec(path)
    except SpecError as exc:  # pragma: no cover - a spec invalida e um erro de repositorio
        raise RenderError(f"{path}: {exc}") from exc


def wire_name(name: str) -> str:
    """Nome JSON do campo REST: a spec escreve um campo repetido como ``nome[]``."""
    return name[:-2] if name.endswith("[]") else name


def wire_naming(spec: SurfaceSpec, scope: str | None = None) -> dict[str, str]:
    """Mapa ``nome documentado -> nome JSON do provedor``, so para os campos repetidos."""
    columns = spec.columns if scope is None else spec.columns_for(scope)
    return {
        column.name: wire_name(column.name)
        for column in columns
        if column.belongs_to_schema and column.name.endswith("[]")
    }


def _empty_value(column: Column) -> Any:
    """Valor de AUSENCIA para o tipo documentado da coluna -- nunca um palpite.

    Um campo que o modelo canonico nao projeta continua existindo no registro (omitir a
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
    return {}


def row_for(spec: SurfaceSpec, values: Mapping[str, Any]) -> dict[str, Any]:
    """Registro com EXATAMENTE as colunas que PERTENCEM ao formato, na ordem da spec."""
    return {
        column.name: values.get(column.name, _empty_value(column))
        for column in spec.columns
        if column.belongs_to_schema
    }


def _instant(moment: datetime | None) -> str:
    """Instante em UTC no formato de data RFC 3339 que os campos de timestamp declaram."""
    if moment is None:
        return ""
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _zone_path(zone: str | None) -> str:
    """O campo ``zone`` documenta a "URL of the zone": o caminho parcial ``zones/<z>``.

    E a unica forma de URL que ESTA spec escreve (a de ``machineType``: "Full or partial URL
    ... in the format: zones/zone/machineTypes/machine-type"); o prefixo de host que a API
    devolve nao esta publicado aqui, entao nao se inventa um.
    """
    return f"zones/{zone}" if zone else ""


def _machine_type(zone: str | None, instance_type: str | None) -> str:
    """``zones/<zone>/machineTypes/<tipo>`` -- a forma que a descricao do campo publica."""
    if not zone or not instance_type:
        return ""
    return f"zones/{zone}/machineTypes/{instance_type}"


def _gcp_instances(estate: CanonicalEstate) -> list[Resource]:
    """As instancias Compute GCP do estado, em ordem estavel (uuid)."""
    return sorted(
        (r for r in estate.resources if r.identity.provider == _GCP and r.resource_type == _INSTANCE_TYPE),
        key=lambda r: r.identity.uuid,
    )


def _profiles(estate: CanonicalEstate) -> dict[str, InstanceProfile]:
    """Os perfis de instancia GCP, por ``resource_uuid`` (FK do modelo, sem orfaos)."""
    return {
        profile.resource_uuid: profile for profile in estate.instance_profiles if profile.provider == _GCP
    }


def _instance_values(instance: Resource, profile: InstanceProfile | None) -> dict[str, Any]:
    """Os campos que o estado canonico carrega para uma instancia (ver o modulo)."""
    values: dict[str, Any] = {
        "kind": _KIND,
        "name": instance.resource_name,
        "labels": dict(instance.tags),
    }
    if profile is not None:
        values["id"] = profile.native_id
        values["zone"] = _zone_path(profile.zone)
        values["machineType"] = _machine_type(profile.zone, profile.instance_type)
        values["status"] = _STATE_LITERALS.get(profile.state, "")
        values["creationTimestamp"] = _instant(profile.launch_time)
    return values


def _name_violations(instances: list[Resource]) -> list[str]:
    """Nomes que nao satisfazem o padrao publicado para ``name`` (RFC1035, 1-63 chars)."""
    return [
        instance.resource_name
        for instance in instances
        if len(instance.resource_name) > 63 or _NAME_PATTERN.fullmatch(instance.resource_name) is None
    ]


def _required_empty_declared(spec: SurfaceSpec, populated: list[str]) -> list[dict[str, str]]:
    """As colunas `required` da spec que NAO carregam valor, com o motivo declarado.

    O invariante do auditor (`obrig.vazias`). Esta spec NAO marca campo nenhum como
    `Required.` (a secao 4 do .md registra isso), entao a lista sai vazia por construcao --
    e continua sendo conferida pelo teste da superficie contra a propria spec.
    """
    return [
        {"column": name, "reason": "SEM MOTIVO DECLARADO: pendencia"}
        for name in spec.required_names
        if name not in set(populated)
    ]


def _populated_names(records: list[dict[str, Any]]) -> list[str]:
    """Caminhos que carregam valor em AO MENOS um registro, na ordem da spec."""
    if not records:
        return []
    return [name for name in records[0] if any(not is_empty_value(row.get(name)) for row in records)]


class GcpComputeInstancesRenderer:
    """Projeta o estado canonico na representacao REST documentada de uma instancia."""

    name = "gcp_compute_instances"

    def build_records(self, estate: CanonicalEstate) -> list[dict[str, Any]]:
        """Um registro por instancia, com os 48 campos documentados."""
        spec = compute_instances_spec()
        profiles = _profiles(estate)
        return [
            row_for(spec, _instance_values(resource, profiles.get(resource.identity.uuid)))
            for resource in _gcp_instances(estate)
        ]

    def _provenance(self, estate: CanonicalEstate, records: list[dict[str, Any]]) -> dict[str, Any]:
        """Relatorio (arquivo IRMAO): mecanismo documentado, contagens, lacunas e grafia."""
        spec = compute_instances_spec()
        instances = _gcp_instances(estate)
        violations = _name_violations(instances)
        populated = _populated_names(records)
        return {
            "surface": spec.surface,
            "spec": f"specs/{_SPEC_FILE}",
            "kind": "provenance",
            "artifacts": [_RECORDS_FILE],
            "artifact_field_names": (
                "the name the specification gives each documented field; a repeated field is spelled "
                "`nome[]`, as the provider's field table spells it"
            ),
            "naming": {
                "wire_names": wire_naming(spec),
                "note": (
                    "the provider's JSON serialization drops the `[]`; use this map to hand the record "
                    "to a client parser. The artifact itself keeps the documented spelling so it stays "
                    "comparable, field by field, with the specification."
                ),
            },
            "mechanism": {
                "kind": "rest-api",
                "is_export": False,
                "is_export_note": (
                    "not an official export: this is the canonical representation of the resource, "
                    "returned by a GET call"
                ),
                "get": "https://compute.googleapis.com/compute/v1/projects/{project}/zones/{zone}/instances/{instance}",
                "list": "https://compute.googleapis.com/compute/v1/projects/{project}/zones/{zone}/instances",
                "response_body": "the instances.get response body carries the Instances object",
                "format": "application/json",
                "file_format": None,
                "file_format_note": (
                    "compression, delimiter and header are not documented: the surface is an API "
                    "response, not a batch file"
                ),
                "instance_list_envelope": (
                    "InstanceList (items/nextPageToken/warning) is not part of this spec; the documented "
                    "element is the Instances resource emitted here"
                ),
            },
            "columns": {
                "documented": len(spec.columns),
                "emitted_per_instance": len(records[0]) if records else 0,
                "required": list(spec.required_names),
                "not_generated": sorted(spec.non_emittable_names),
            },
            "populated_paths": populated,
            "populated_count": len(populated),
            "required_empty_declared": _required_empty_declared(spec, populated),
            "instances": len(instances),
            "value_domains": {
                "kind": "the documented constant compute#instance",
                "id": (
                    "InstanceProfile.native_id: the Compute id is a uint64 and the profile mints a stable "
                    "integer in that form (the estate's own identity is a UUIDv5 and is NOT written here)"
                ),
                "zone": (
                    "InstanceProfile.zone ('region + letter', the form each cloud publishes) written as the "
                    "partial URL zones/<zone>: the field documents 'URL of the zone', and the partial form is "
                    "the only URL shape this spec publishes"
                ),
                "machineType": (
                    "zones/<zone>/machineTypes/<instance_type>, the format the field's description "
                    "publishes; instance_type is DERIVED from the catalog SKU, so a SKU the catalog does not "
                    "decode leaves the field empty"
                ),
                "status": (
                    "InstanceProfile.state (canonical running/stopped) -> the literals model/compute.py "
                    "names for GCP: RUNNING and TERMINATED"
                ),
                "creationTimestamp": "InstanceProfile.launch_time as an RFC 3339 date string",
                "labels": "Resource.tags, the documented map (key: string, value: string)",
            },
            "name_pattern_violations": {
                "pattern": "[a-z]([-a-z0-9]*[a-z0-9])?, 1-63 chars (RFC1035)",
                "count": len(violations),
                "note": (
                    "the generator produces deliberately off-standard names (FR-D3); they are emitted "
                    "verbatim -- mangling them would be its own infidelity -- and counted here"
                ),
                "examples": violations[:5],
            },
            "model_gaps": [
                {
                    "item": "enderecos de rede da instancia",
                    "reason": (
                        "SPEC, nao modelo: o InstanceProfile carrega private_ip e public_ip, mas os unicos "
                        "destinos documentados sao networkInterfaces[].networkIP e accessConfigs[].natIP, e "
                        "a spec NAO transcreve esses subcampos (a §3.2 lista so os aninhados lidos e a §4 "
                        "manda trata-los como UNVERIFIED). Escrever um nome de subcampo nao citado seria "
                        "inventar estrutura"
                    ),
                },
                {
                    "item": "disco raiz",
                    "reason": (
                        "SPEC, nao modelo: root_volume_size_gb/root_volume_type existem no perfil, mas o "
                        "destino documentado seria disks[].initializeParams.diskSizeGb/diskType, tambem nao "
                        "transcrito; disks[] sai vazio"
                    ),
                },
                {
                    "item": "imagem",
                    "reason": (
                        "InstanceProfile.image_id e uma imagem de DISCO (projects/<p>/global/images/img-...), "
                        "enquanto sourceMachineImage e uma MACHINE image: sao recursos diferentes, entao o "
                        "campo fica vazio em vez de carregar o errado (disks[].initializeParams.sourceImage "
                        "seria o destino certo, e nao esta transcrito)"
                    ),
                },
                {
                    "item": "ultimo start/stop/suspend",
                    "reason": (
                        "o modelo carrega UM instante (launch_time) e ele alimenta creationTimestamp; "
                        "'last start' e um evento distinto da criacao e 'last stop/suspend' nao existe no "
                        "modelo, entao os tres campos ficam vazios (ver open_questions)"
                    ),
                },
                {
                    "item": "selfLink, hostname, description, tags de rede",
                    "reason": (
                        "o modelo nao carrega a URL do recurso (a spec nao publica a forma do host), o "
                        "hostname, uma descricao nem tags de rede (as tags do estado sao LABELS, que saem "
                        "em labels)"
                    ),
                },
                {
                    "item": "metadata, serviceAccounts, scheduling, encryption, shielded/confidential",
                    "reason": (
                        "o modelo nao tem metadados, contas de servico, agendamento nem configuracao de "
                        "criptografia/Shielded/Confidential; os campos correspondentes saem vazios"
                    ),
                },
                {
                    "item": "enums de topo sem constantes transcritas",
                    "reason": (
                        "a spec so enumera status e keyRevocationActionType; os demais enums tem o tipo "
                        "`enum` sem constantes publicadas e saem vazios"
                    ),
                },
                {
                    "item": "params (Input only)",
                    "reason": (
                        "campo Input only: faz parte da estrutura documentada do recurso mas nunca aparece "
                        "numa resposta; emitido vazio"
                    ),
                },
            ],
            "open_questions": [
                {
                    "item": "lastStartTimestamp <- InstanceProfile.launch_time",
                    "note": (
                        "para uma instancia que nao reiniciou, 'last start' e o proprio instante de criacao, "
                        "e o modelo nao expressa reinicio; a coincidencia NAO foi projetada porque 'last "
                        "start' e um evento distinto da criacao. Uma linha aqui se o mantenedor quiser a "
                        "coincidencia."
                    ),
                }
            ],
            "notes": [
                "the record keys are the DOCUMENTED field names; naming.wire_names has the provider spelling",
                "there is no InstanceList envelope: it is not part of this spec",
            ],
        }

    def render(self, estate: CanonicalEstate, out_dir: Path) -> list[Path]:
        """Escreve ``instances.json`` (o registro) e ``_provenance.json`` (o relatorio)."""
        target = out_dir / "gcp_compute_instances"
        target.mkdir(parents=True, exist_ok=True)
        records = self.build_records(estate)
        records_path = target / _RECORDS_FILE
        records_path.write_text(json.dumps(records, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        provenance_path = target / _PROVENANCE_FILE
        provenance_path.write_text(
            json.dumps(self._provenance(estate, records), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return [records_path, provenance_path]
