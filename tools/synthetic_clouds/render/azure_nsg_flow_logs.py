"""Azure NSG flow logs, schema Version 2 — the ``PT1H.json`` blob written to a storage account.

Surface: ``specs/azure/nsg-flow-logs-v2.schema.json`` — 39 columns in 2 named sets, 13
emittable/generatable (the 13 JSON members of ``records[]``); the 13 CSV positions of
``flowTuples`` are described but NOT generatable (the payload hands them over inside one
string, so no example fixes a JSON type for a position).

THE DELIVERY IS A REAL BLOB, WITH A DOCUMENTED CONTAINER AND PATH
-----------------------------------------------------------------
``delivery.kind`` is ``azure-blob-storage``, container
``insights-logs-networksecuritygroupflowevent``, and the spec transcribes the official
template literally::

    https://{storageAccountName}.blob.core.windows.net/insights-logs-networksecuritygroupflowevent/
      resourceId=/SUBSCRIPTIONS/{subscriptionID}/RESOURCEGROUPS/{resourceGroupName}/
      PROVIDERS/MICROSOFT.NETWORK/NETWORKSECURITYGROUPS/{nsgName}/
      y={year}/m={month}/d={day}/h={hour}/m=00/macAddress={macAddress}/PT1H.json

Every one of those segments now has a value: the network model carries the NSG's ARM id
(``NetworkSegment.network_security_group_id``), its resource group
(``NetworkSegment.resource_group``) and the NIC's MAC (``NetworkInterface.mac_address``). The
delivered tree therefore starts at the container (the ``{storageAccountName}`` host is the
blob ENDPOINT, not a path segment) and keeps the literal ``m=00`` minute component the
documentation fixes. The file is plain UTF-8 JSON with no compression: the spec records
compression and encoding as UNVERIFIED, and JSON is UTF-8 by default, so no gzip and no BOM is
assumed.

THE RECORD IS NOW FILLED FROM THE MODEL — AND WHAT STAYS EMPTY, AND WHY
----------------------------------------------------------------------
``model/network.py`` carries the segment, the interface and the flow, so the 13 members stop
being empty:

* ``records[].time`` — the flow window's start, in the 7-fractional-digit UTC shape the
  official sample shows (the digit count is a registered UNVERIFIED item);
* ``records[].systemId`` — the NSG **GUID** (``network_security_group_uuid``). It is NOT the
  subscription: the documented meaning is "System ID of the network security group", and
  projecting the scope there would put a subscription id in a resource's field;
* ``records[].resourceId`` — the NSG's ARM id, projected VERBATIM (never re-composed);
* ``category``/``operationName``/``properties.Version`` — the documented constants of a
  Version 2 record;
* ``records[].properties.flows[].flows[].mac`` — the MAC of the NIC that collected the flow,
  in the documented spelling (12 hex digits, no separators, as in ``000D3AF87856``);
* ``...flowTuples`` — the CSV string with the 13 positions in the order the spec fixes:
  ``timestamp,src_ip,dst_ip,src_port,dst_port,protocol,traffic_flow,traffic_decision,flow_state,packets_sent,bytes_sent,packets_received,bytes_received``,
  with the epoch in **seconds** (NSG granularity, unlike the VNet's milliseconds) and the
  protocol as ``T``/``U`` (unlike the VNet's IANA number).

Still EMPTY, deliberately: ``flows[].rule`` — ``model/network.py`` carries no rule identity
(no ``rule``/``acl_id``), and the literal of a platform rule is a registered UNVERIFIED item,
so deriving a rule name from the decision would be inventing vocabulary; the four counters of
a flow whose state is ``B`` — the documentation states "Statistics aren't provided" for
``Begin`` and the official sample shows the four trailing fields empty; and the protocol
position of an ICMP flow — the documented domain is ``T``/``U`` only, while the model keeps the
IANA number (``1`` for ICMP), for which Azure publishes no literal.

GRAIN AND ATTRIBUTION
---------------------
One blob per (NSG, collecting NIC, hour), one ``records[]`` entry per flow window, one
``flows[]`` entry per rule (empty, as above) and one ``flows[].flows[]`` entry per MAC,
holding the window's ``flowTuples``. The model states the direction relative to a local
endpoint without naming it, so the collecting NIC is the only attribution the documented grain
permits: the SOURCE interface on an egress flow, the DESTINATION on an ingress flow. A flow
whose local endpoint is unknown is counted in ``_provenance.json`` as a gap instead of
receiving an invented MAC.

The report is a SIBLING file: the artifact carries ONLY documented fields, and everything
about provenance (the spec, the mechanism, the counts, the gaps) lives in ``_provenance.json``.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from typing import Any

from tools.synthetic_clouds.fidelity.spec import (
    DEFAULT_SPECS_ROOT,
    SpecError,
    SurfaceSpec,
    load_spec,
)
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.network import (
    DECISION_ALLOWED,
    DECISION_DENIED,
    DIRECTION_EGRESS,
    DIRECTION_INGRESS,
    NetworkFlow,
    NetworkInterface,
    NetworkSegment,
)
from tools.synthetic_clouds.render.azure_arm_instances import (
    PROVENANCE_FILE,
    arm_id_token,
    arm_resource_name,
    documented_document,
    documented_projection,
    emittable_columns,
    mac_wire,
    not_generated,
    provenance,
    write_json,
)
from tools.synthetic_clouds.render.base import RenderError

#: O caminho da especificação normativa DENTRO de ``specs/`` (a proveniência cita este texto).
_SPEC_FILE = "azure/nsg-flow-logs-v2.schema.json"

#: A especificação normativa desta superfície (fonte da verdade; NUNCA editada aqui).
SPEC_PATH = DEFAULT_SPECS_ROOT / _SPEC_FILE

_AZURE = "azure"

#: O conjunto dos 13 membros JSON do registo -- o escopo obrigatório de ``check_artifact``.
RECORD_SCOPE = "record"

#: Contentor documentado (``delivery.container``) e nome do ficheiro (``delivery.file_name``).
CONTAINER = "insights-logs-networksecuritygroupflowevent"
FILE_NAME = "PT1H.json"

#: Constantes documentadas de um registo Version 2.
_CATEGORY = "NetworkSecurityGroupFlowEvent"
_OPERATION_NAME = "NetworkSecurityGroupFlowEvents"
_VERSION = 2

#: Número IANA -> literal documentado. O domínio publicado é ``T``/``U``; para qualquer outro
#: protocolo a posição sai VAZIA (a Azure não publica literal para ICMP).
_PROTOCOL_LITERALS: dict[int, str] = {6: "T", 17: "U"}

#: Direção e decisão canônicas -> literais documentados. O modelo garante o domínio (o gate o
#: valida), então um valor fora dele é erro de modelo e deve estourar, não virar vazio.
_TRAFFIC_FLOW: dict[str, str] = {DIRECTION_INGRESS: "I", DIRECTION_EGRESS: "O"}
_TRAFFIC_DECISION: dict[str, str] = {DECISION_ALLOWED: "A", DECISION_DENIED: "D"}

#: Estados de fluxo que o NSG documenta. O ``D`` é do VNet e não é publicado aqui.
_NSG_FLOW_STATES = frozenset({"B", "C", "E"})

#: Estado cujos contadores a documentação afirma NÃO serem fornecidos ("Statistics aren't
#: provided" para ``Begin``): as quatro posições saem vazias, como no exemplo oficial.
_STATISTICLESS_STATES = frozenset({"B"})


@cache
def _spec() -> SurfaceSpec:
    """A spec normativa desta superfície, carregada uma vez; falha FECHADO se não servir."""
    try:
        return load_spec(SPEC_PATH)
    except SpecError as exc:
        raise RenderError(f"{SPEC_PATH}: {exc}") from exc


def _seven_digit_utc(moment: datetime) -> str:
    """ISO 8601 UTC com 7 dígitos fracionários e sufixo ``Z`` (a forma da amostra oficial).

    A documentação exemplifica ``2018-11-13T12:00:35.3899262Z`` e registra como UNVERIFIED que
    a parte fracionária tenha sempre 7 dígitos; o sétimo dígito entregue é um zero, e não uma
    precisão que o estado carregue.
    """
    return f"{moment.astimezone(UTC).strftime('%Y-%m-%dT%H:%M:%S')}.{moment.microsecond:06d}0Z"


def _counter(value: int | None) -> str:
    """Uma posição de contador: vazia quando o modelo não a tem, nunca um zero inventado."""
    return "" if value is None else str(value)


def observing_interface_uuid(flow: NetworkFlow) -> str | None:
    """A interface que COLETOU o fluxo -- a dona do MAC no grupo ``flows[].mac``.

    O modelo descreve a direção em relação a uma ponta local sem nomeá-la, então a atribuição
    possível é a única compatível com a direção: a origem num fluxo de saída e o destino num
    fluxo de entrada. Sem essa ponta o fluxo não tem grupo e é CONTADO como lacuna.
    """
    return flow.src_interface_uuid if flow.direction == DIRECTION_EGRESS else flow.dst_interface_uuid


def flow_tuple(flow: NetworkFlow) -> str:
    """A string CSV de ``flowTuples``: as 13 posições, na ordem que a spec fixa.

    O que a documentação condiciona, o renderer respeita: o instante em SEGUNDOS epoch, o
    protocolo no literal ``T``/``U``, a direção em ``I``/``O``, a decisão em ``A``/``D`` e o
    estado em ``B``/``C``/``E`` (o ``D`` do VNet não é publicado aqui). Um estado fora do
    domínio do NSG e um protocolo sem literal documentado saem VAZIOS.
    """
    state = flow.flow_state or ""
    if state not in _NSG_FLOW_STATES:
        state = ""
    counters: tuple[str, str, str, str] = (
        ("", "", "", "")
        if state in _STATISTICLESS_STATES
        else (
            _counter(flow.packets),
            _counter(flow.bytes),
            _counter(flow.packets_reverse),
            _counter(flow.bytes_reverse),
        )
    )
    return ",".join(
        (
            str(int(flow.window_start.timestamp())),
            flow.src_ip,
            flow.dst_ip,
            str(flow.src_port),
            str(flow.dst_port),
            _PROTOCOL_LITERALS.get(flow.protocol_number, ""),
            _TRAFFIC_FLOW[flow.direction],
            _TRAFFIC_DECISION[flow.decision],
            state,
            *counters,
        )
    )


def blob_document(
    windows: Mapping[datetime, Sequence[NetworkFlow]], segment: NetworkSegment, interface: NetworkInterface
) -> dict[str, Any]:
    """O documento ``PT1H.json`` de uma hora: um registo por janela, com os ``flowTuples``.

    ``records[]`` é a raiz documentada; cada registo tem o seu instante e o grupo
    ``flows[].flows[]`` com o MAC da NIC que coletou o fluxo. O ``rule`` fica vazio porque o
    modelo não carrega identidade de regra.
    """
    columns = emittable_columns(_spec(), RECORD_SCOPE)
    mac = mac_wire(interface.mac_address)
    records: list[dict[str, Any]] = []
    for start in sorted(windows):
        flows = sorted(windows[start], key=lambda flow: flow.flow_id)
        values: dict[str, Any] = {
            "records[].time": _seven_digit_utc(start),
            "records[].systemId": segment.network_security_group_uuid,
            "records[].resourceId": segment.network_security_group_id,
            "records[].category": _CATEGORY,
            "records[].operationName": _OPERATION_NAME,
            "records[].properties.Version": _VERSION,
            "records[].properties.flows[].flows[].mac": mac,
            "records[].properties.flows[].flows[].flowTuples": [flow_tuple(flow) for flow in flows],
        }
        document = documented_document(columns, values)
        # O construtor monta o documento inteiro (a raiz ``records``); um blob é a soma dos
        # registos das suas janelas, então é o array da raiz que se acumula.
        records.extend(document["records"])
    return {"records": records}


def blob_path(target: Path, *, segment: NetworkSegment, interface: NetworkInterface, moment: datetime) -> Path:
    """O caminho do blob, segmento a segmento, segundo o template oficial transcrito.

    O token de assinatura é lido do PRÓPRIO ARM id da NSG (``subscriptions/<token>``): assim o
    caminho e o ``resourceId`` do registo não podem discordar, e nenhum id é reescrito aqui.
    """
    nsg_id = segment.network_security_group_id or segment.segment_id
    subscription = arm_id_token(nsg_id, "subscriptions") or segment.scope_id
    return (
        target
        / CONTAINER
        / "resourceId="
        / "SUBSCRIPTIONS"
        / subscription
        / "RESOURCEGROUPS"
        / (segment.resource_group or segment.scope_id)
        / "PROVIDERS"
        / "MICROSOFT.NETWORK"
        / "NETWORKSECURITYGROUPS"
        / arm_resource_name(nsg_id)
        / f"y={moment.year}"
        / f"m={moment.month:02d}"
        / f"d={moment.day:02d}"
        / f"h={moment.hour:02d}"
        / "m=00"
        / f"macAddress={mac_wire(interface.mac_address)}"
        / FILE_NAME
    )


def _hour_of(moment: datetime) -> datetime:
    """A hora cheia que contém ``moment`` -- a partição ``y=/m=/d=/h=`` do blob é horária."""
    return moment.astimezone(UTC).replace(minute=0, second=0, microsecond=0)


def _grouped_flows(
    estate: CanonicalEstate, segments: Mapping[str, NetworkSegment], interfaces: Mapping[str, NetworkInterface]
) -> tuple[dict[tuple[str, str], list[NetworkFlow]], Counter[str]]:
    """Os fluxos Azure agrupados por (segmento, interface que coletou) e as lacunas contadas."""
    groups: dict[tuple[str, str], list[NetworkFlow]] = {}
    gaps: Counter[str] = Counter()
    for flow in sorted(estate.network_flows, key=lambda item: item.flow_id):
        if flow.segment_uuid not in segments:
            continue
        uuid = observing_interface_uuid(flow)
        interface = interfaces.get(uuid) if uuid is not None else None
        if interface is None:
            gaps["flow_without_observing_interface"] += 1
            continue
        groups.setdefault((flow.segment_uuid, interface.interface_uuid), []).append(flow)
        if flow.flow_state not in _NSG_FLOW_STATES:
            gaps["flow_state_not_published_by_nsg"] += 1
        if flow.protocol_number not in _PROTOCOL_LITERALS:
            gaps["protocol_without_documented_literal"] += 1
    return groups, gaps


def _projection_name(segment: NetworkSegment, interface: NetworkInterface, hour: datetime) -> str:
    """O nome do arquivo de projeção: os quatro eixos do caminho do blob, sem barras."""
    nsg_id = segment.network_security_group_id or segment.segment_id
    return (
        f"{arm_id_token(nsg_id, 'subscriptions')}_{arm_resource_name(nsg_id)}"
        f"_{mac_wire(interface.mac_address)}_{hour.strftime('%Y%m%dT%H')}.json"
    )


class AzureNsgFlowLogsRenderer:
    """Entrega os blobs ``PT1H.json`` de NSG flow logs Version 2 no layout documentado."""

    name = "azure_nsg_flow_logs"

    def render(self, estate: CanonicalEstate, out_dir: Path) -> list[Path]:
        """Escreve um blob por (NSG, NIC coletora, hora) sob ``out_dir/azure_nsg_flow_logs``."""
        target = out_dir / self.name
        segments = {segment.segment_uuid: segment for segment in estate.network_segments if segment.provider == _AZURE}
        interfaces = {interface.interface_uuid: interface for interface in estate.network_interfaces}
        groups, gaps = _grouped_flows(estate, segments, interfaces)

        columns = emittable_columns(_spec(), RECORD_SCOPE)
        written: list[Path] = []
        records_total = 0
        tuples_total = 0
        for segment_uuid, interface_uuid in sorted(groups):
            segment = segments[segment_uuid]
            interface = interfaces[interface_uuid]
            by_hour: dict[datetime, dict[datetime, list[NetworkFlow]]] = {}
            for flow in groups[(segment_uuid, interface_uuid)]:
                by_hour.setdefault(_hour_of(flow.window_start), {}).setdefault(flow.window_start, []).append(flow)
            for hour in sorted(by_hour):
                windows = by_hour[hour]
                document = blob_document(windows, segment, interface)
                blob = blob_path(target, segment=segment, interface=interface, moment=hour)
                write_json(blob, document)
                # A projeção é derivada dos BYTES entregues (lidos de volta do disco) e carrega os
                # 13 membros JSON que a spec enumera -- as posições do CSV não são campos do ficheiro.
                projection = target / "field_projection" / _projection_name(segment, interface, hour)
                write_json(projection, documented_projection(json.loads(blob.read_text(encoding="utf-8")), columns))
                written.extend((blob, projection))
                records_total += len(document["records"])
                tuples_total += len(windows)

        write_json(
            target / PROVENANCE_FILE,
            provenance(
                _spec(),
                spec_file=_SPEC_FILE,
                artifacts=[f"{CONTAINER}/**/{FILE_NAME}", "field_projection/*.json", PROVENANCE_FILE],
                mechanism={
                    "kind": "azure-blob-storage",
                    "container": CONTAINER,
                    "file_name": FILE_NAME,
                    "path_template": (
                        f"https://{{storageAccountName}}.blob.core.windows.net/{CONTAINER}/"
                        "resourceId=/SUBSCRIPTIONS/{subscriptionID}/RESOURCEGROUPS/{resourceGroupName}/"
                        "PROVIDERS/MICROSOFT.NETWORK/NETWORKSECURITYGROUPS/{nsgName}/"
                        f"y={{year}}/m={{month}}/d={{day}}/h={{hour}}/m=00/macAddress={{macAddress}}/{FILE_NAME}"
                    ),
                    "format": "json",
                    "compression": None,
                    "compression_note": "a spec registra a compressao como UNVERIFIED: nao se assume gzip",
                    "encoding": "UTF-8 (o JSON e UTF-8 por definicao; o encoding do blob e UNVERIFIED)",
                    "partitioning": (
                        "resourceId=/SUBSCRIPTIONS/<assinatura>/RESOURCEGROUPS/<rg>/PROVIDERS/"
                        "MICROSOFT.NETWORK/NETWORKSECURITYGROUPS/<nsg>/y=/m=/d=/h=/m=00/macAddress="
                    ),
                    "manifest": None,
                    "manifest_note": "nenhum manifesto e documentado para NSG flow logs v2: nao se gera nenhum",
                    "cadence": "PT1H (um blob por hora por MAC); logs coletados a cada 1 minuto",
                    "root": "records[]",
                    "delivery_note": (
                        "a Azure escreve os NSG flow logs numa conta de armazenamento; o host "
                        "{storageAccountName}.blob.core.windows.net e o ENDPOINT do blob, nao um segmento do caminho"
                    ),
                    "mac_partition": "12 digitos hexadecimais em maiusculas, sem separadores (forma do exemplo oficial)",
                    "epoch_unit": "segundos (o VNet publica milissegundos: as duas unidades NAO se uniformizam)",
                },
                columns={
                    "documented": len(_spec().columns),
                    "emittable": len(columns),
                    "generated": len(columns),
                    "sets": list(_spec().set_names),
                },
                counts={
                    "segments": len(segments),
                    "interfaces": len(interfaces),
                    "blobs": len(written) // 2,
                    "records": records_total,
                    "flow_tuples": tuples_total,
                    "flow_windows": len(
                        {(flow.window_start, flow.window_end) for flow in estate.network_flows}
                    ),
                    **dict(gaps),
                },
                not_generated=not_generated(_spec(), RECORD_SCOPE) + not_generated(_spec(), "flowTuples-position"),
                model_gaps=[
                    {
                        "item": "identidade de regra (``flows[].rule``)",
                        "reason": (
                            "model/network.py nao carrega a regra que permitiu ou negou o fluxo (nem acl_id); o "
                            "literal de uma platform rule e UNVERIFIED na spec, entao derivar a regra da decisao "
                            "seria inventar vocabulario"
                        ),
                    },
                    {
                        "item": "protocolo ICMP na posicao 6 do ``flowTuples``",
                        "reason": (
                            "o modelo guarda o numero IANA (1 para ICMP) e o dominio documentado do NSG e apenas "
                            "T/U: sem literal publicado, a posicao sai VAZIA"
                        ),
                    },
                    {
                        "item": "contadores de um fluxo em estado Begin",
                        "reason": (
                            "a documentacao afirma que estatisticas NAO sao fornecidas para B e o exemplo oficial "
                            "mostra as quatro posicoes vazias; o modelo tem os contadores e o renderer os descarta"
                        ),
                    },
                    {
                        "item": "MAC/NIC que COLETOU o fluxo",
                        "reason": (
                            "o modelo nao nomeia a interface coletora; ela e derivada da direcao (origem em egress, "
                            "destino em ingress), que e a unica atribuicao compativel com o grao documentado"
                        ),
                    },
                    {
                        "item": "tamanho maximo do blob / numero maximo de registos",
                        "reason": "UNVERIFIED na spec: a fatia entregue e a hora das janelas de fluxo do estado",
                    },
                ],
            ),
        )
        written.append(target / PROVENANCE_FILE)
        return written
