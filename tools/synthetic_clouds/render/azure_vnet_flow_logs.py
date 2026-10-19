"""Azure virtual network flow logs — the storage blob AND the two Log Analytics tables it feeds.

Surface: ``specs/azure/vnet-flow-logs.schema.json`` — 127 columns in 5 named sets, and only
7 of them are generatable, ALL of them in the two traffic-analytics tables:
``NTANetAnalytics`` (5: the processing-interval timestamps) and ``NTAIpDetails`` (2: the same
two interval bounds). The three blob sets (``blob``, ``blob-envelope``,
``flowTuples-position``) are ``example-only`` in every column: the official "Log format" table
names every field and gives it a Source, but publishes no TYPE for any of them, and the
contract refuses ``format-observed`` for a field that is not ``declared``.

THE CAP IS THE SPECIFICATION'S, NOT THE MODEL'S
-----------------------------------------------
This is the point the network model does NOT change, and it is worth stating plainly now that
``estate.network_flows`` exists and carries the 5-tuple, the counters, the state, the MAC and
the windows: **no column of the vnet blob sets may be emitted, whatever the model has**,
because not one of them belongs to the format under the contract. Emitting ``SrcIp`` or
``PacketsSrcToDest`` in ``NTANetAnalytics`` is not a data gap either -- those 57 (and
``NTAIpDetails``' 12) flow columns are equally ``example-only``, so a filled value is a
finding, not a projection (the golden test proves it by mutating one and getting
``unverified_emitted``). What the model DOES unlock is real and is what this renderer now
does: the aggregation exists, so ``FlowStartTime``/``FlowEndTime`` -- which are emittable and
mean "first/last occurrence of the flow in the processing interval" -- carry the model's
window bounds instead of staying empty, and the blob's PARTITION (subscription, resource
group, MAC) is filled from the model even though the document itself asserts no field.

TWO DOCUMENTED DELIVERY PATHS, AND WHICH ONE IS AUDITABLE
--------------------------------------------------------
(a) Storage — the mechanism itself. ``delivery.container`` is
    ``insights-logs-flowlogflowevent`` with the official template::

        .../insights-logs-flowlogflowevent/flowLogResourceID=/{subscriptionID}_NETWORKWATCHERRG/
          NETWORKWATCHER_{Region}_{ResourceName}-{ResourceGroupName}-FLOWLOGS/
          y={year}/m={month}/d={day}/h={hour}/m=00/macAddress={macAddress}/PT1H.json

    The delivered tree reproduces that layout segment by segment, one blob per
    (VNet, collecting NIC, hour). Its CONTENT is the empty document: with zero emittable
    columns, the only document the contract allows is the object with no member at all, so the
    file states the layout and asserts no field. The third partition segment keeps the
    documentation's OWN token: it is the ``FlowLog`` resource's name, which no entity of the
    state models (the spec itself registers that derivation as UNVERIFIED).

(b) Log Analytics through traffic analytics, which reads the storage blobs, aggregates and
    decorates the flows and ingests the result into ``NTANetAnalytics``/``NTAIpDetails``.
    That is a DISTINCT, aggregated schema, and it is the only part of this surface with a
    published type. One row per (VNet, processing interval): the interval bounds, the
    processing instant and the first/last flow occurrence come from the model's flows of that
    segment; every other column is refused by the spec and stays empty -- the aggregation KEY
    columns (``SrcIp``, ``DestIp``, ``DestPort``, ``FlowDirection``, ``FlowStatus``,
    ``L4Protocol``, the counters) are not emittable, so the rows cannot be told apart beyond
    their interval, which is a property of the SPEC and is recorded in ``_provenance.json``.

The report is a SIBLING file: the artifacts carry ONLY documented fields and the two schemas
are never mixed.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
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
from tools.synthetic_clouds.model.network import NetworkFlow, NetworkInterface, NetworkSegment
from tools.synthetic_clouds.render.azure_arm_instances import (
    PROVENANCE_FILE,
    arm_id_token,
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
_SPEC_FILE = "azure/vnet-flow-logs.schema.json"

#: A especificação normativa desta superfície (fonte da verdade; NUNCA editada aqui).
SPEC_PATH = DEFAULT_SPECS_ROOT / _SPEC_FILE

_AZURE = "azure"

#: Escopos (nomes de conjunto) desta superfície, tal como o ``.schema.json`` os nomeia.
BLOB_SCOPE = "blob"
BLOB_ENVELOPE_SCOPE = "blob-envelope"
FLOW_TUPLES_SCOPE = "flowTuples-position"
ANALYTICS_SCOPE = "NTANetAnalytics"
IP_DETAILS_SCOPE = "NTAIpDetails"

#: Contentor e ficheiro documentados para o blob.
CONTAINER = "insights-logs-flowlogflowevent"
FILE_NAME = "PT1H.json"

#: O segmento do nome do recurso ``FlowLog`` no template oficial, literal: a documentação não
#: afirma como ele é derivado (a spec o registra como UNVERIFIED) e nenhuma entidade do estado
#: modela o recurso ``FlowLog``, então ele NÃO é preenchido pela metade.
_FLOW_LOG_NAME = "NETWORKWATCHER_{Region}_{ResourceName}-{ResourceGroupName}-FLOWLOGS"


@cache
def _spec() -> SurfaceSpec:
    """A spec normativa desta superfície, carregada uma vez; falha FECHADO se não servir."""
    try:
        return load_spec(SPEC_PATH)
    except SpecError as exc:
        raise RenderError(f"{SPEC_PATH}: {exc}") from exc


def _iso_utc(moment: datetime) -> str:
    """ISO 8601 UTC com sufixo ``Z`` (a forma que as colunas ``datetime`` do Log Analytics usam)."""
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def azure_segments(estate: CanonicalEstate) -> list[NetworkSegment]:
    """As VNets Azure do estado, em ordem determinística."""
    return sorted(
        (segment for segment in estate.network_segments if segment.provider == _AZURE),
        key=lambda segment: segment.segment_uuid,
    )


def flows_by_segment(estate: CanonicalEstate) -> dict[str, list[NetworkFlow]]:
    """Os fluxos de cada segmento Azure, em ordem determinística."""
    segments = {segment.segment_uuid for segment in azure_segments(estate)}
    grouped: dict[str, list[NetworkFlow]] = {}
    for flow in sorted(estate.network_flows, key=lambda item: item.flow_id):
        if flow.segment_uuid in segments:
            grouped.setdefault(flow.segment_uuid, []).append(flow)
    return grouped


def blob_document() -> dict[str, Any]:
    """O documento do blob ``PT1H.json``: a forma que a spec autoriza, que aqui é vazia.

    Os conjuntos do blob têm ZERO colunas que pertençam ao formato (as três são
    ``example-only``). Uma coluna que não pertence ao formato não entra no artefato -- nem
    vazia --, então o documento entregue é o objeto sem membro nenhum, e o arquivo existe
    porque o LAYOUT é documentado.
    """
    return documented_document(emittable_columns(_spec(), BLOB_ENVELOPE_SCOPE), {})


def analytics_row(segment: NetworkSegment, flows: Sequence[NetworkFlow]) -> dict[str, Any]:
    """Uma linha de ``NTANetAnalytics`` para uma VNet e o seu intervalo de processamento.

    As cinco colunas geráveis são as do intervalo: ``FlowInterval*`` são os limites do
    intervalo que agregou, ``TimeProcessed`` é o instante em que o traffic analytics processou
    os blobs (o fim do intervalo, que é o que o processamento horário significa) e
    ``FlowStartTime``/``FlowEndTime`` são a PRIMEIRA e a ÚLTIMA ocorrência dos fluxos do
    segmento -- que agora existem no modelo. Qualquer coluna de FLUXO fica vazia: o contrato a
    recusa, não o modelo (ver o docstring do módulo).

    ``segment`` nomeia a VNet que a linha agrega. Nenhuma coluna gerável desta tabela carrega
    essa identidade -- as que a carregariam (``SrcSubscription``, ``FlowLogResourceId``) são
    ``example-only`` --, então o argumento não pode aparecer no registro; ele mantém o sítio da
    chamada honesto quanto à cardinalidade (uma linha por VNet).
    """
    start = min(flow.window_start for flow in flows)
    end = max(flow.window_end for flow in flows)
    row = dict.fromkeys((column.name for column in emittable_columns(_spec(), ANALYTICS_SCOPE)), None)
    row["TimeProcessed"] = _iso_utc(end)
    row["FlowIntervalStartTime"] = _iso_utc(start)
    row["FlowIntervalEndTime"] = _iso_utc(end)
    row["FlowStartTime"] = _iso_utc(min(flow.window_start for flow in flows))
    row["FlowEndTime"] = _iso_utc(max(flow.window_end for flow in flows))
    return row


def ip_details_row(flows: Sequence[NetworkFlow]) -> dict[str, Any]:
    """Uma linha de ``NTAIpDetails`` para o intervalo agregado de uma VNet.

    Só os dois limites do intervalo são geráveis; o enriquecimento de IP público (``IP``,
    ``PublicIPDetails``, ``Location``, ameaças) é ``example-only`` e o modelo não tem IP
    público nenhum, então nada mais pode ser preenchido.
    """
    row = dict.fromkeys((column.name for column in emittable_columns(_spec(), IP_DETAILS_SCOPE)), None)
    row["FlowIntervalStartTime"] = _iso_utc(min(flow.window_start for flow in flows))
    row["FlowIntervalEndTime"] = _iso_utc(max(flow.window_end for flow in flows))
    return row


def blob_path(target: Path, *, segment: NetworkSegment, interface: NetworkInterface, moment: datetime) -> Path:
    """O caminho do blob, segmento a segmento, segundo o template oficial transcrito.

    O token de assinatura é lido do PRÓPRIO ARM id da VNet, então o caminho não reescreve id
    nenhum e o MAC sai do modelo na forma documentada. O segmento do nome do ``FlowLog``
    mantém o token do template: nenhuma entidade do estado modela esse recurso.
    """
    subscription = arm_id_token(segment.segment_id, "subscriptions") or segment.scope_id
    return (
        target
        / CONTAINER
        / "flowLogResourceID="
        / f"{subscription}_NETWORKWATCHERRG"
        / _FLOW_LOG_NAME
        / f"y={moment.year}"
        / f"m={moment.month:02d}"
        / f"d={moment.day:02d}"
        / f"h={moment.hour:02d}"
        / "m=00"
        / f"macAddress={mac_wire(interface.mac_address)}"
        / FILE_NAME
    )


def _interfaces_per_segment(estate: CanonicalEstate) -> dict[str, list[NetworkInterface]]:
    """As interfaces de cada segmento Azure, em ordem determinística."""
    segments = {segment.segment_uuid for segment in azure_segments(estate)}
    grouped: dict[str, list[NetworkInterface]] = {}
    for interface in sorted(estate.network_interfaces, key=lambda item: item.interface_uuid):
        if interface.segment_uuid in segments:
            grouped.setdefault(interface.segment_uuid, []).append(interface)
    return grouped


def _delivered_hour(flows: Sequence[NetworkFlow]) -> datetime:
    """A hora cheia que os fluxos do segmento cobrem -- a partição ``h=`` do blob."""
    return min(flow.window_start for flow in flows).astimezone(UTC).replace(minute=0, second=0, microsecond=0)


class AzureVnetFlowLogsRenderer:
    """Entrega o blob ``PT1H.json`` no layout documentado e as duas tabelas do traffic analytics."""

    name = "azure_vnet_flow_logs"

    def render(self, estate: CanonicalEstate, out_dir: Path) -> list[Path]:
        """Escreve o blob por (VNet, NIC) e as tabelas ``NTANetAnalytics``/``NTAIpDetails``."""
        target = out_dir / self.name
        segments = azure_segments(estate)
        flows = flows_by_segment(estate)
        per_segment = _interfaces_per_segment(estate)

        columns = emittable_columns(_spec(), BLOB_ENVELOPE_SCOPE)
        written: list[Path] = []
        blobs = 0
        for segment in segments:
            interfaces = per_segment.get(segment.segment_uuid, [])
            if not interfaces or segment.segment_uuid not in flows:
                continue
            moment = _delivered_hour(flows[segment.segment_uuid])
            for interface in interfaces:
                blob = blob_path(target, segment=segment, interface=interface, moment=moment)
                write_json(blob, blob_document())
                # A projeção é derivada dos BYTES entregues (lidos de volta do disco). Nenhuma
                # coluna dos conjuntos do blob pertence ao formato, então ela é vazia.
                projection = (
                    target
                    / "field_projection"
                    / f"blob_{arm_id_token(segment.segment_id, 'subscriptions')}_{mac_wire(interface.mac_address)}.json"
                )
                write_json(projection, documented_projection(json.loads(blob.read_text(encoding="utf-8")), columns))
                written.extend((blob, projection))
                blobs += 1

        aggregated = [(segment, flows[segment.segment_uuid]) for segment in segments if flows.get(segment.segment_uuid)]
        analytics = target / f"{ANALYTICS_SCOPE}.json"
        ip_details = target / f"{IP_DETAILS_SCOPE}.json"
        write_json(analytics, [analytics_row(segment, segment_flows) for segment, segment_flows in aggregated])
        write_json(ip_details, [ip_details_row(segment_flows) for _segment, segment_flows in aggregated])
        # As tabelas do Log Analytics JÁ são planas (os nomes documentados não têm pontos),
        # então o próprio ficheiro entregue é o artefato que o núcleo de fidelidade lê.
        written.extend((analytics, ip_details))

        write_json(
            target / PROVENANCE_FILE,
            provenance(
                _spec(),
                spec_file=_SPEC_FILE,
                artifacts=[
                    f"{CONTAINER}/**/{FILE_NAME}",
                    "field_projection/*.json",
                    f"{ANALYTICS_SCOPE}.json",
                    f"{IP_DETAILS_SCOPE}.json",
                    PROVENANCE_FILE,
                ],
                mechanism={
                    "kind": "azure-blob-storage + log-analytics",
                    "container": CONTAINER,
                    "file_name": FILE_NAME,
                    "path_template": (
                        f"https://{{storageAccountName}}.blob.core.windows.net/{CONTAINER}/"
                        "flowLogResourceID=/{subscriptionID}_NETWORKWATCHERRG/"
                        f"{_FLOW_LOG_NAME}/y={{year}}/m={{month}}/d={{day}}/h={{hour}}/m=00/"
                        f"macAddress={{macAddress}}/{FILE_NAME}"
                    ),
                    "format": "json",
                    "compression": None,
                    "compression_note": "a spec registra a compressao do blob como UNVERIFIED",
                    "manifest": None,
                    "manifest_note": "nenhum manifesto e documentado: nao se gera nenhum",
                    "cadence": "PT1H (um blob por hora por MAC), ingerido em blocos a cada minuto",
                    "root": "records[]",
                    "second_delivery": {
                        "kind": "log-analytics",
                        "tables": [ANALYTICS_SCOPE, IP_DETAILS_SCOPE],
                        "reach": "somente pelo traffic analytics, que LE os blobs, agrega e decora os fluxos",
                        "schema": (
                            "esquema AGREGADO distinto (FASchemaVersion 3) -- nao e o registo cru do blob, "
                            "e o renderer nao alimenta as duas com o mesmo objeto"
                        ),
                    },
                    "epoch_unit": "milissegundos no VNet (o NSG publica segundos: as duas unidades NAO se uniformizam)",
                    "protocol": "numero IANA (o NSG publica T/U: os dois vocabularios NAO se convertem aqui)",
                },
                columns={
                    "documented": len(_spec().columns),
                    "per_set": {
                        scope: {
                            "documented": len(_spec().columns_for(scope)),
                            "emittable": len(emittable_columns(_spec(), scope)),
                        }
                        for scope in (BLOB_SCOPE, BLOB_ENVELOPE_SCOPE, FLOW_TUPLES_SCOPE, ANALYTICS_SCOPE, IP_DETAILS_SCOPE)
                    },
                    "emittable_total": len(_spec().emittable_names),
                    "generated": len(emittable_columns(_spec(), ANALYTICS_SCOPE))
                    + len(emittable_columns(_spec(), IP_DETAILS_SCOPE)),
                    "cap_note": (
                        "o teto e da SPEC, nao do modelo: os 23 campos do blob, as 13 posicoes do CSV e as 57+12 "
                        "colunas de fluxo das tabelas sao example-only (sem tipo publicado), e uma coluna assim nao "
                        "entra no artefato nem preenchida nem vazia"
                    ),
                },
                counts={
                    "segments": len(segments),
                    "interfaces": sum(len(per_segment.get(segment.segment_uuid, [])) for segment in segments),
                    "blobs": blobs,
                    "flow_records_in_blobs": 0,
                    "flow_records_in_blobs_note": "o blob nao carrega campo nenhum: nenhum fluxo e afirmado nele",
                    "analytics_rows": len(aggregated),
                    "ip_details_rows": len(aggregated),
                    "aggregated_flows": sum(len(segment_flows) for _segment, segment_flows in aggregated),
                    "aggregation_key_columns_not_emittable": len(
                        [column for column in _spec().columns_for(ANALYTICS_SCOPE) if not column.is_generatable]
                    ),
                },
                not_generated=not_generated(_spec(), BLOB_SCOPE)
                + not_generated(_spec(), BLOB_ENVELOPE_SCOPE)
                + not_generated(_spec(), FLOW_TUPLES_SCOPE)
                + not_generated(_spec(), ANALYTICS_SCOPE)
                + not_generated(_spec(), IP_DETAILS_SCOPE),
                model_gaps=[
                    {
                        "item": "tipo publicado para os campos do blob do VNet",
                        "reason": (
                            "os 23 campos do registo cru (e o envelope com ``records``) sao example-only na spec: "
                            "nao ha tipo, e sem tipo a coluna nao pertence ao formato. E uma lacuna da SPEC -- o "
                            "modelo de rede tem os valores (5-tupla, MAC, contadores, estado) e mesmo assim nenhum "
                            "campo do blob pode ser emitido"
                        ),
                    },
                    {
                        "item": "tipo publicado para as colunas de FLUXO de NTANetAnalytics/NTAIpDetails",
                        "reason": (
                            "as 57+12 colunas de fluxo do traffic analytics tambem sao example-only (a propria spec "
                            "registra 'colum data types' como UNVERIFIED): so os 5+2 timestamps de intervalo podem "
                            "receber valor, por mais fluxo que o modelo carregue"
                        ),
                    },
                    {
                        "item": "recurso FlowLog / Network Watcher",
                        "reason": (
                            "nenhuma entidade do estado modela o FlowLog nem o Network Watcher, entao o segmento "
                            "``NETWORKWATCHER_{Region}_{ResourceName}-{ResourceGroupName}-FLOWLOGS`` mantem o token do "
                            "template: a propria spec registra a derivacao dele como UNVERIFIED"
                        ),
                    },
                    {
                        "item": "enriquecimento de IP publico",
                        "reason": "o modelo so tem IP privado: IP/PublicIPDetails/Location/ThreatType ficam vazios em NTAIpDetails",
                    },
                    {
                        "item": "chaves de agregacao do traffic analytics",
                        "reason": (
                            "as colunas que distinguiriam uma linha da outra (SrcIp, DestIp, DestPort, L4Protocol, "
                            "FlowDirection, FlowStatus, AclGroup, AclRule) nao sao geraveis, entao as linhas so se "
                            "distinguem pelo intervalo"
                        ),
                    },
                ],
            ),
        )
        written.append(target / PROVENANCE_FILE)
        return written
