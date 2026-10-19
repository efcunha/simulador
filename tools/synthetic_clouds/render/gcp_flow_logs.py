"""VPC Flow Logs: the documented record format, projected from the canonical network model.

The mechanism the documentation actually states
-----------------------------------------------
``specs/gcp/vpc-flow-logs-bigquery.md`` (consulted 2026-10-14) opens with the finding this
module is built around: **Google does not document a direct delivery of VPC Flow Logs to
BigQuery**. The documented destination is Cloud Logging ("This data is then sent to
Logging in the Google Cloud project of the VPC network that reported the flow", 30-day
default retention). The documented BigQuery path is a **linked BigQuery dataset** on a log
bucket upgraded to Observability Analytics, which lets BigQuery *query* the logs "without
exporting that data to BigQuery": log views are mapped to read-only **virtual views**
(example name ``_AllLogs``), the link is "a read-only pointer to your log bucket".

Two consequences, and both are about NOT asserting something:
  * there is no export file: format, compression, encoding, delimiter, header, bucket
    path, partitioning, sharding and manifest are all "not documented" on this path;
  * the linked dataset's column list and BigQuery types are NOT published either, so this
    renderer never claims a BigQuery column name or type. Nothing here is named after,
    or shaped as, a BigQuery table.

The record, and where each value comes from
------------------------------------------
What IS documented, with types, is the VPC Flow Logs **record format**
(``about-flow-logs-records``): 13 base fields always present + 22 optional metadata fields
= 35 top-level entries, plus 146 nested subfields = **181 documented field paths**. Each
record of ``flow_log_records.json`` is one canonical ``NetworkFlow`` of a GCP segment
(``model/network.py``), projected onto those paths:

================================  ==========================================
documented path                   canonical source
================================  ==========================================
``connection.src_ip``             ``NetworkFlow.src_ip``
``connection.dest_ip``            ``NetworkFlow.dst_ip``
``connection.src_port``           ``NetworkFlow.src_port``
``connection.dest_port``          ``NetworkFlow.dst_port``
``connection.protocol``           ``NetworkFlow.protocol_number`` (IANA)
``reporter``                      ``NetworkFlow.reported_by`` (``SRC``/``DEST``)
``connection_direction``          ``NetworkFlow.direction`` -> ``INGRESS``/``EGRESS``
``start_time`` / ``end_time``     ``window_start`` / ``window_end`` (RFC 3339, UTC)
``bytes_sent`` / ``packets_sent`` ``NetworkFlow.bytes`` / ``.packets``
``disposition``                   ``decision == denied`` -> ``DROPPED``, else empty
``src_instance.*``                source ``NetworkInterface`` -> its ``Resource``
``src_vpc.*``                     source interface -> its ``NetworkSegment``
``dest_instance.*`` / ``dest_vpc.*``  idem, for the destination
================================  ==========================================

``disposition`` deserves the quote, because it is the one place where the canonical decision
does NOT map one-to-one: the field table declares the value ``DROPPED`` and says the field
is "Populated only for log records that capture packet drops. This field is set to
DROPPED." So a denied flow (the packet was dropped) carries ``DROPPED`` and an allowed flow
carries NOTHING -- ``ALLOWED``/``DENIED`` are not values this documentation publishes, and
the project does not invent a value the source of truth does not state.

``src_instance`` is populated only when the interface's resource really IS a Compute
instance (``compute_instance``): the field documents "the VM instance details", and the
estate attaches interfaces to GKE clusters and Cloud SQL databases too -- calling one of
those a VM would be a plausibility claim. ``src_vpc`` is populated for every modelled
endpoint, because the VPC a NIC lives in is a real fact of the model whatever the resource
is. When an endpoint lies outside the estate the model carries no interface for it (and
``0.0.0.0`` as the address, verbatim from ``FLOW_ABSENT_ADDRESS``), so its
``*_instance``/``*_vpc`` details stay empty -- the documented "if the source of the flow is
a VM located in a VPC network" does not hold for an internet peer.

Everything else stays EMPTY, and the reasons are listed in ``_provenance.json``: the model
carries no round-trip time (``rtt_msec``, ``round_trip_time``), no drop reason
(``drop_reason``), no split between sent and dropped counters (``bytes_dropped``/
``packets_dropped``), no ``throughput_inclusion``, no geographic/AS/GKE/serverless/PSC/load
balancing/internet routing details, no zone and no managed instance group.

Artifact and report are separate files, always: the record file carries ONLY documented
fields, and everything about provenance (the mechanism, why there is no BigQuery artifact,
the value domains, the model gaps, the counts) lives in the SIBLING ``_provenance.json``.
"""

from __future__ import annotations

import json
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
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.network import (
    DECISION_DENIED,
    DIRECTION_EGRESS,
    DIRECTION_INGRESS,
    NetworkFlow,
    NetworkInterface,
    NetworkSegment,
)
from tools.synthetic_clouds.model.resource import Resource
from tools.synthetic_clouds.render.base import RenderError

#: A spec de origem, sob ``specs/`` (nunca editada aqui).
_SPEC_FILE = "gcp/vpc-flow-logs-bigquery.schema.json"

#: O artefato (os registros) e o relatorio de proveniencia, que NUNCA se misturam.
_RECORDS_FILE = "flow_log_records.json"
_PROVENANCE_FILE = "_provenance.json"

_GCP = "gcp"
#: So um recurso deste tipo pode alimentar ``*_instance``: o campo documenta "the VM".
_VM_RESOURCE_TYPE = "compute_instance"

#: ``NetworkFlow.direction`` -> o literal que a tabela de formato publica.
_DIRECTIONS: dict[str, str] = {DIRECTION_INGRESS: "INGRESS", DIRECTION_EGRESS: "EGRESS"}

#: O unico valor de ``disposition`` que a documentacao publica, para o unico caso em que a
#: propria tabela diz que o campo e populado (um registro que captura pacote derrubado).
_DISPOSITION_DROPPED = "DROPPED"

#: Tipos cujo vazio e um objeto sem campos; todo tipo NAO escalar cai aqui.
_RECORD_TYPES = frozenset({"record", "struct", "map", "object", "message"})
_ARRAY_PREFIXES = ("array", "repeated", "list of")


@cache
def flow_logs_spec() -> SurfaceSpec:
    """Carrega a spec normativa da superficie; falha FECHADO se ela nao servir."""
    path = DEFAULT_SPECS_ROOT / _SPEC_FILE
    try:
        return load_spec(path)
    except SpecError as exc:  # pragma: no cover - a spec invalida e um erro de repositorio
        raise RenderError(f"{path}: {exc}") from exc


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
    # Tipo nomeado (mensagem aninhada, ex.: IpConnection) que nao e escalar: objeto vazio.
    return {}


def row_for(spec: SurfaceSpec, values: Mapping[str, Any]) -> dict[str, Any]:
    """Registro com EXATAMENTE as colunas que PERTENCEM ao formato, na ordem da spec."""
    row: dict[str, Any] = {}
    for column in spec.columns:
        if not column.belongs_to_schema:
            continue
        row[column.name] = values.get(column.name, _empty_value(column))
    return row


def _rfc3339(moment: datetime) -> str:
    """Instante em UTC no formato de data RFC 3339 que a tabela de formato publica."""
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _gcp_segments(estate: CanonicalEstate) -> dict[str, NetworkSegment]:
    """Segmentos de rede do provedor GCP, por ``segment_uuid``."""
    return {segment.segment_uuid: segment for segment in estate.network_segments if segment.provider == _GCP}


def _gcp_flows(estate: CanonicalEstate) -> list[NetworkFlow]:
    """Os fluxos cujo segmento e GCP, em ordem estavel (janela, depois ``flow_id``)."""
    gcp = _gcp_segments(estate)
    flows = [flow for flow in estate.network_flows if flow.segment_uuid in gcp]
    return sorted(flows, key=lambda flow: (flow.window_start, flow.flow_id))


def _endpoint_values(
    prefix: str,
    interface: NetworkInterface | None,
    segments: Mapping[str, NetworkSegment],
    resources: Mapping[str, Resource],
) -> dict[str, Any]:
    """Detalhes de VPC e de instancia de UMA ponta do fluxo (prefixo ``src``/``dest``).

    Uma ponta sem interface e uma ponta FORA do estado (internet): a documentacao so popula
    esses campos "if the source of the flow is a VM located in a VPC network", entao ela sai
    vazia. A VPC e projetada de qualquer interface modelada (e um fato do modelo, qualquer
    que seja o recurso); a instancia so quando o recurso E uma instancia Compute, porque o
    campo documenta "the VM instance details" -- um cluster GKE ou um banco Cloud SQL nao e
    uma VM, e chama-lo de VM seria plausibilidade, nao projecao.
    """
    if interface is None:
        return {}

    values: dict[str, Any] = {}
    segment = segments.get(interface.segment_uuid)
    if segment is not None:
        values[f"{prefix}_vpc.project_id"] = segment.scope_id
        values[f"{prefix}_vpc.vpc_name"] = segment.name
        values[f"{prefix}_vpc.subnetwork_name"] = segment.subnet_id.rpartition("/")[2]
        values[f"{prefix}_vpc.subnetwork_region"] = segment.region_id

    resource = resources.get(interface.resource_uuid)
    if resource is not None and resource.resource_type == _VM_RESOURCE_TYPE:
        values[f"{prefix}_instance.project_id"] = resource.parent_scope_id
        values[f"{prefix}_instance.region"] = interface.region_id
        values[f"{prefix}_instance.vm_name"] = resource.resource_name
    return values


def _record_values(
    flow: NetworkFlow,
    interfaces: Mapping[str, NetworkInterface],
    segments: Mapping[str, NetworkSegment],
    resources: Mapping[str, Resource],
) -> dict[str, Any]:
    """Projecao de UM ``NetworkFlow`` nos caminhos documentados (ver o modulo)."""
    src = interfaces.get(flow.src_interface_uuid or "")
    dst = interfaces.get(flow.dst_interface_uuid or "")
    values: dict[str, Any] = {
        "connection.src_ip": flow.src_ip,
        "connection.dest_ip": flow.dst_ip,
        "connection.src_port": flow.src_port,
        "connection.dest_port": flow.dst_port,
        # O documento declara "The IANA protocol number": o numero do modelo E o valor.
        "connection.protocol": flow.protocol_number,
        # ``reported_by`` e ``None`` fora do GCP; nos fluxos desta superficie ele vem
        # preenchido (SRC/DEST), que e o vocabulario publicado para ``reporter``.
        "reporter": flow.reported_by or "",
        "connection_direction": _DIRECTIONS.get(flow.direction, ""),
        "start_time": _rfc3339(flow.window_start),
        "end_time": _rfc3339(flow.window_end),
        "bytes_sent": flow.bytes,
        "packets_sent": flow.packets,
        # "Populated only for log records that capture packet drops. This field is set to
        # DROPPED." Um fluxo permitido nao carrega valor nenhum aqui.
        "disposition": _DISPOSITION_DROPPED if flow.decision == DECISION_DENIED else "",
    }
    values.update(_endpoint_values("src", src, segments, resources))
    values.update(_endpoint_values("dest", dst, segments, resources))
    return values


def _populated_names(records: list[dict[str, Any]]) -> list[str]:
    """Caminhos que carregam valor em AO MENOS UM registro, na ordem da spec.

    Usa ``is_empty_value`` do proprio nucleo de fidelidade, para que o numero relatado aqui
    seja o mesmo que ``populated_of`` mede no arquivo entregue.
    """
    if not records:
        return []
    return [name for name in records[0] if any(not is_empty_value(record.get(name)) for record in records)]


def _required_empty_declared(spec: SurfaceSpec, populated: list[str]) -> list[dict[str, str]]:
    """As colunas ``required`` da spec que NAO carregam valor, com o motivo declarado.

    O invariante do auditor (``obrig.vazias``): uma obrigatoria vazia e uma pendencia ATE
    ser explicada -- ou o dado tem fonte e falta, ou a ausencia tem motivo. Derivada da spec,
    nao de uma lista literal: uma obrigatoria nova que ninguem preenche cai aqui SEM motivo e
    o teste da superficie falha, que e o ponto.
    """
    razoes = {
        "connection": (
            "container (IpConnection): o artefato entrega os filhos ACHATADOS "
            "(connection.src_ip/dest_ip/src_port/dest_port/protocol) e o container fica "
            "representado por eles, nunca por uma chave vazia"
        ),
        "round_trip_time": (
            "container (Latencies) sem valor E sem o filho: o modelo de rede nao carrega RTT, "
            "entao nem o container nem round_trip_time.median_msec tem fonte"
        ),
        "rtt_msec": "o modelo de rede nao carrega round-trip time",
        "drop_reason": (
            "o modelo diz que o fluxo foi derrubado (decision=denied) mas nao diz POR QUE "
            "(firewall, rota, fila); a documentacao publica valores como FIREWALL_DENY, e "
            "escolher um seria palpite"
        ),
        "bytes_dropped": (
            "o modelo carrega UM contador por fluxo (bytes), sem separar enviado de derrubado"
        ),
        "packets_dropped": (
            "o modelo carrega UM contador por fluxo (packets), sem separar enviado de derrubado"
        ),
        "throughput_inclusion": (
            "o modelo nao diz se o trafego derrubado entra ou nao em bytes_sent/packets_sent; "
            "a documentacao so publica INCLUDED/EXCLUDED para registro com disposition=DROPPED"
        ),
    }
    return [
        {"column": name, "reason": razoes.get(name, "SEM MOTIVO DECLARADO: pendencia")}
        for name in spec.required_names
        if name not in set(populated)
    ]


def _region_divergences(
    flows: list[NetworkFlow],
    interfaces: Mapping[str, NetworkInterface],
    segments: Mapping[str, NetworkSegment],
) -> int:
    """Pontas cuja regiao difere da regiao do segmento (divergencia DO MODELO, nao do dado).

    O segmento nasce com a regiao do PRIMEIRO recurso do escopo e agrupa interfaces de todas
    as regioes do escopo. Quando as duas divergem, o registro projeta cada campo do seu dono
    -- ``*_vpc.subnetwork_region`` do segmento (a regiao esta dentro do proprio ``subnet_id``)
    e ``*_instance.region`` da interface -- e o PAR nao existiria numa nuvem real. Corrigir
    isso e mudar o modelo (uma sub-rede por regiao); aqui o numero e relatado, nao mascarado.
    """
    contagem = 0
    for flow in flows:
        for interface_uuid in (flow.src_interface_uuid, flow.dst_interface_uuid):
            interface = interfaces.get(interface_uuid or "")
            if interface is None:
                continue
            segment = segments.get(interface.segment_uuid)
            if segment is not None and interface.region_id != segment.region_id:
                contagem += 1
    return contagem


class GcpFlowLogsRenderer:
    """Projeta os fluxos GCP canonicos no FORMATO de registro que a documentacao publica."""

    name = "gcp_flow_logs"

    def build_records(self, estate: CanonicalEstate) -> list[dict[str, Any]]:
        """Um registro por ``NetworkFlow`` de segmento GCP, no formato documentado."""
        spec = flow_logs_spec()
        interfaces = {interface.interface_uuid: interface for interface in estate.network_interfaces}
        segments = _gcp_segments(estate)
        resources = {resource.identity.uuid: resource for resource in estate.resources}
        return [
            row_for(spec, _record_values(flow, interfaces, segments, resources)) for flow in _gcp_flows(estate)
        ]

    def _provenance(self, estate: CanonicalEstate, records: list[dict[str, Any]]) -> dict[str, Any]:
        """Relatorio (arquivo IRMAO): o mecanismo documentado, a projecao e as lacunas."""
        spec = flow_logs_spec()
        populated = _populated_names(records)
        interfaces = {interface.interface_uuid: interface for interface in estate.network_interfaces}
        segments = _gcp_segments(estate)
        flows = _gcp_flows(estate)
        return {
            "surface": spec.surface,
            "spec": f"specs/{_SPEC_FILE}",
            "kind": "provenance",
            "artifacts": [_RECORDS_FILE],
            "artifact_field_names": (
                "the name the specification gives each documented field; this surface spells no field "
                "with the `nome[]` repeated notation, so the wire spelling is the documented one"
            ),
            "naming": {
                "wire_names": {},
                "note": "no documented field of this surface is spelled with the `nome[]` notation",
            },
            "mechanism": {
                "destination": "Cloud Logging",
                "destination_statement": (
                    "This data is then sent to Logging in the Google Cloud project of the VPC "
                    "network that reported the flow"
                ),
                "retention": "30 days by default; longer retention requires an export to a supported destination",
                "direct_bigquery_export": False,
                "direct_bigquery_export_note": (
                    "no official page describes a VPC-Flow-Logs-specific sink or export to BigQuery; "
                    "the destination is Cloud Logging"
                ),
                "bigquery_path": "linked BigQuery dataset on a log bucket with Observability Analytics",
                "bigquery_path_note": (
                    "Cloud Logging lets you query log data from BigQuery 'without exporting that data to "
                    "BigQuery'; log views are mapped to read-only virtual views (example name `_AllLogs`)"
                ),
                "bigquery_virtual_view_columns": "not published by the documentation",
                "file_format": None,
                "compression": None,
                "partitioning": None,
                "manifest": None,
            },
            "record_format": {
                "documented_paths": len(spec.columns),
                "top_level_paths": len({name.split(".", 1)[0] for name in spec.names}),
                "base_fields": 13,
                "metadata_fields": 22,
                "emitted_paths": len(records[0]) if records else 0,
            },
            "records": len(records),
            "records_note": (
                "one record per canonical GCP NetworkFlow (estate.network_flows on a gcp NetworkSegment); "
                "every documented path is present and a path the model does not carry is empty"
            ),
            "populated_paths": populated,
            "populated_count": len(populated),
            "required_empty_declared": _required_empty_declared(spec, populated),
            "container_representation": {
                "column": "connection",
                "represents": sorted(name for name in populated if name.startswith("connection.")),
                "note": (
                    "the format table requires the `connection` record and lists its subfields "
                    "(src_ip, dest_ip, src_port, dest_port, protocol). This artifact emits the subfields "
                    "FLATTENED because the fidelity core compares the row's TOP-LEVEL keys with the spec "
                    "names; the `connection` container is therefore represented by its children and is not "
                    "emitted as a key. Not an omission: declared here."
                ),
            },
            "model_divergences": [
                {
                    "item": "regiao da sub-rede vs regiao da interface",
                    "count": _region_divergences(flows, interfaces, segments),
                    "note": (
                        "o segmento nasce com a regiao do PRIMEIRO recurso do escopo e agrupa as "
                        "interfaces de todas as regioes dele; quando as duas divergem, o registro projeta "
                        "cada campo do seu dono (subnetwork_region do segmento, que tambem esta dentro do "
                        "subnet_id, e *_instance.region da interface) e o par nao existiria numa nuvem "
                        "real. A correcao pertence ao modelo (um segmento/sub-rede por regiao)."
                    ),
                }
            ],
            "value_domains": {
                "connection.protocol": (
                    "the document declares 'The IANA protocol number'; NetworkFlow.protocol_number is that number"
                ),
                "connection_direction": (
                    "NetworkFlow.direction -> the published literals EGRESS/INGRESS (the model's own "
                    "docstring records GCP as ingress/egress)"
                ),
                "reporter": (
                    "NetworkFlow.reported_by carries the GCP reporter (SRC/DEST); the model fills it only "
                    "for GCP, and a flow without it emits the empty value"
                ),
                "disposition": (
                    "the field table declares the value DROPPED and says it is 'Populated only for log "
                    "records that capture packet drops. This field is set to DROPPED.' A denied flow "
                    "(decision=denied) is such a record; an allowed flow carries no value. "
                    "ALLOWED/DENIED are NOT values this documentation publishes."
                ),
                "start_time/end_time": (
                    "NetworkFlow.window_start/window_end (UTC) rendered as RFC 3339 date strings, the "
                    "format the field table declares"
                ),
                "src_instance/dest_instance": (
                    "populated only when the endpoint interface's resource is a compute_instance: the field "
                    "documents 'the VM instance details'. project_id/region/vm_name come from the resource "
                    "and its interface; zone and managed_instance_group are not modelled"
                ),
                "src_vpc/dest_vpc": (
                    "populated from the endpoint interface's NetworkSegment: project_id=scope_id, "
                    "vpc_name=name, subnetwork_name=last segment of subnet_id, "
                    "subnetwork_region=segment.region_id"
                ),
            },
            "model_gaps": [
                {
                    "item": "round-trip time",
                    "reason": "o modelo nao carrega RTT; rtt_msec e round_trip_time.median_msec saem vazios",
                },
                {
                    "item": "motivo do descarte",
                    "reason": (
                        "o modelo tem decision=denied mas nao diz POR QUE (firewall, rota, fila); a "
                        "documentacao publica valores como FIREWALL_DENY, e escolher um seria palpite"
                    ),
                },
                {
                    "item": "contadores separados de derrubados",
                    "reason": (
                        "o modelo carrega UM contador por fluxo (bytes/packets), sem separar enviado de "
                        "derrubado; bytes_dropped e packets_dropped saem vazios"
                    ),
                },
                {
                    "item": "throughput_inclusion",
                    "reason": "o modelo nao diz se o trafego derrubado entra ou nao em bytes_sent/packets_sent",
                },
                {
                    "item": "zona e managed instance group",
                    "reason": (
                        "a interface carrega regiao, nao zona; src_instance.zone e "
                        "src_instance.managed_instance_group (e os campos de InstanceGroupDetails) saem vazios"
                    ),
                },
                {
                    "item": "sub-rede por regiao",
                    "reason": (
                        "o modelo tem UMA sub-rede por segmento, com a regiao do primeiro recurso do escopo, "
                        "enquanto as interfaces do segmento vivem em regioes diferentes; ver "
                        "model_divergences para a contagem medida"
                    ),
                },
                {
                    "item": "geografia, roteamento e servicos de rede",
                    "reason": (
                        "src_location/dest_location (ASN, cidade, continente, pais), "
                        "internet_routing_details.egress_as_path, load_balancing, network_service, psc, "
                        "src_gke_details/dest_gke_details, src_serverless_details e src_gateway: o modelo de "
                        "rede nao os carrega"
                    ),
                },
                {
                    "item": "ponta fora do estado",
                    "reason": (
                        "quando uma ponta esta fora do estate nao ha interface para ela e o modelo grava "
                        "0.0.0.0 (FLOW_ABSENT_ADDRESS) no endereco; os detalhes *_instance/*_vpc daquela "
                        "ponta ficam vazios, como a documentacao exige"
                    ),
                },
                {
                    "item": "BigQuery column names/types of the linked dataset virtual view",
                    "reason": "a documentacao nao publica a lista de colunas nem os tipos; nenhum nome e afirmado",
                },
            ],
        }

    def render(self, estate: CanonicalEstate, out_dir: Path) -> list[Path]:
        """Escreve ``flow_log_records.json`` e ``_provenance.json`` (arquivos irmãos)."""
        target = out_dir / "gcp_flow_logs"
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
