"""Regras de NSG da Azure — a resposta ARM ``GET .../networkSecurityGroups/{nsg}``.

Superfície: ``specs/azure/arm-network-security-group-rules.schema.json`` — 27 colunas em 2
conjuntos nomeados (``rule``, ``networkSecurityGroup``), todas emitíveis e geráveis.

POR QUE ESTA SUPERFÍCIE EXISTE
------------------------------
O consumidor do lado do FinOps percorre as REGRAS de cada NSG e filtra por
``direction``/``access`` (``security.py (modulo do consumidor):107,109``). O estado canônico não
tinha nenhuma regra: o emulador ``azure-sim`` respondia lista vazia **por desenho** para
``networkSecurityGroups``, com a justificativa registrada de que "the estate models no
network security group". A consequência era medida: a subscription era reportada como limpa
porque **não havia o que varrer**. ``NetworkSecurityGroup``/``SecurityRule`` em
``model/network.py`` fecham a metade que cabia a este repositório, e esta superfície é a
metade visível dela: um artefato que carrega as regras, com os dois casos (``Allow`` e
``Deny``) no MESMO NSG, para que um filtro invertido não passe.

O QUE É EMITIDO, E POR QUE O ENVELOPE É O DO RECURSO PAI
--------------------------------------------------------
A página do recurso filho (``networkSecurityGroups/securityRules``) e a do pai
(``networkSecurityGroups``) publicam o **mesmo** ``SecurityRulePropertiesFormat``. O envelope
entregue é o do **pai**, por duas razões que vêm do consumidor: é o ``list`` de
``networkSecurityGroups`` que um scanner de postura chama, e é a coleção
``properties.securityRules[]`` que ele itera. Então o corpo é o do NSG, e cada regra ocupa
uma posição da coleção.

O que sai **vazio**, e por quê:

* ``sourceAddressPrefixes``/``destinationAddressPrefixes``/``sourcePortRanges``/
  ``destinationPortRanges`` — a spec publica os pares singulares E os plurais; uma regra usa
  uma das duas formas, e o modelo guarda a singular, então o plural fica vazio. Emiti-lo vazio
  é pertencer ao formato; preenchê-lo duplicaria o valor singular;
* ``sourceApplicationSecurityGroups``/``destinationApplicationSecurityGroups`` — as listas
  existem no formato e **nenhuma regra deste estado aponta para uma ASG**. Os membros
  publicados (``id``/``location``) saem vazios dentro de uma lista vazia, como o exemplo ARM
  oficial desenha.

O envelope de LISTA (``{"value": [...], "nextLink": ...}``, o ``NetworkSecurityGroupListResult``
que a API REST publica) **não** é emitido aqui: ele é a forma de paginação da coleção, não um
campo do recurso, e o SDK desembrulha ``value`` antes de entregar cada NSG ao consumidor. Emitir
um ``value`` dentro de cada NSG seria inventar um membro que o recurso não tem.

OS DOIS ``id`` (incremento 7)
---------------------------
A página REST publica ``id | string | Resource ID.`` tanto no objeto ``Network Security Group``
quanto no objeto ``Security Rule``, e o consumidor do FinOps lê o do NSG (``nsg.id`` →
``resource_id`` do achado e ``nsg.id.split('/')[4]`` → ``--resource-group`` do comando de
remediação). Os dois saem da **mesma** composição — :meth:`NetworkSecurityGroup.arm_id` — de modo
que o id do envelope, o caminho do arquivo e o caminho aninhado da regra não podem divergir. É
por isso que a regra recebe o ``nsg_arm_id`` em :func:`rule_values`.

A ASSINATURA NO CAMINHO É O GUID
--------------------------------
O caminho de saída é derivado do **próprio ARM id** do NSG (``subscriptions/<token>``), que o
modelo compõe a partir do GUID da assinatura — nunca do rótulo de escopo. Assim o caminho e o
``resourceId`` que o modelo também publica no flow log não podem discordar, e nenhum id é
reescrito aqui.

O relatório é um arquivo IRMÃO (``_provenance.json``): o artefato carrega apenas campo
documentado, e tudo sobre proveniência (spec, mecanismo, contagens, lacunas) vive nele.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Sequence
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
    NetworkSecurityGroup,
    NetworkSegment,
    SecurityRule,
)
from tools.synthetic_clouds.render.azure_arm_instances import (
    PROVENANCE_FILE,
    arm_id_token,
    documented_document,
    documented_projection,
    emittable_columns,
    not_generated,
    provenance,
    write_json,
)
from tools.synthetic_clouds.render.base import RenderError

#: O caminho da especificação normativa DENTRO de ``specs/`` (a proveniência cita este texto).
_SPEC_FILE = "azure/arm-network-security-group-rules.schema.json"

#: A especificação normativa desta superfície (fonte da verdade; NUNCA editada aqui).
SPEC_PATH = DEFAULT_SPECS_ROOT / _SPEC_FILE

_AZURE = "azure"

#: O conjunto das regras e o do envelope: os dois escopos obrigatórios de ``check_artifact``.
RULE_SCOPE = "rule"
NSG_SCOPE = "networkSecurityGroup"

#: Direção e acesso canônicos -> literais que a página de template publica. O modelo garante
#: o domínio (o gate o valida), então um valor fora dele é erro de modelo e deve estourar --
#: por isso são indexações diretas, e não ``.get`` com vazio.
_DIRECTION_LITERALS: dict[str, str] = {DIRECTION_INGRESS: "Inbound", DIRECTION_EGRESS: "Outbound"}
_ACCESS_LITERALS: dict[str, str] = {DECISION_ALLOWED: "Allow", DECISION_DENIED: "Deny"}


def _spec() -> SurfaceSpec:
    """A spec normativa desta superfície, carregada a cada chamada; falha FECHADO se não servir."""
    try:
        return load_spec(SPEC_PATH)
    except SpecError as exc:
        raise RenderError(f"{SPEC_PATH}: {exc}") from exc


def rule_values(rule: SecurityRule, nsg_arm_id: str) -> dict[str, Any]:
    """Os valores que o modelo sustenta para UMA regra, já nos literais publicados.

    Só os caminhos que o modelo carrega aparecem aqui: o resto do documento sai vazio por
    :func:`documented_document`, o que é a resposta correta para um campo do formato que
    nenhuma regra deste estado preenche.

    ``nsg_arm_id`` é o id ARM do NSG dono, porque o id da REGRA é o caminho aninhado que a
    documentação publica (``<id-do-NSG>/securityRules/<nome>``) — passá-lo mantém o id da
    regra e o id do NSG derivados da MESMA composição, sem duas grafias do mesmo caminho.
    """
    return {
        "properties.securityRules[].name": rule.name,
        "properties.securityRules[].id": f"{nsg_arm_id}/securityRules/{rule.name}",
        "properties.securityRules[].properties.access": _ACCESS_LITERALS[rule.access],
        "properties.securityRules[].properties.direction": _DIRECTION_LITERALS[rule.direction],
        "properties.securityRules[].properties.priority": rule.priority,
        "properties.securityRules[].properties.protocol": rule.protocol,
        "properties.securityRules[].properties.sourceAddressPrefix": rule.source_address_prefix,
        "properties.securityRules[].properties.destinationAddressPrefix": rule.destination_address_prefix,
        "properties.securityRules[].properties.sourcePortRange": rule.source_port_range,
        "properties.securityRules[].properties.destinationPortRange": rule.destination_port_range,
    }


def nsg_document(
    nsg: NetworkSecurityGroup, columns: Sequence[Any] | None = None, *, location: str | None = None
) -> dict[str, Any]:
    """O corpo da resposta para ``nsg``: o envelope do NSG com a coleção de regras.

    ``columns`` existe para o chamador passar as colunas já filtradas pelo contrato; sem ela,
    a superfície inteira é montada. A ordem das regras é a do modelo (por prioridade), que é a
    ordem em que a Azure avalia -- o artefato não tem direito de reordenar uma política.

    Cada regra é montada pelo construtor documentado a partir das colunas do conjunto
    ``rule``, e a coleção é montada AQUI, com uma posição por regra: o construtor semeia uma
    posição por caminho documentado, o que entregaria uma regra para cada caminho em vez de
    uma por regra da política.

    O envelope carrega ``id`` — o mesmo que :meth:`NetworkSecurityGroup.arm_id` devolve, e que
    também compõe o caminho do arquivo. Cada regra recebe esse id para compor o dela, o que
    impede que as duas grafias do mesmo caminho divergam.
    """
    columns = emittable_columns(_spec()) if columns is None else columns
    arm_id = nsg.arm_id()
    regras: list[dict[str, Any]] = []
    for rule in nsg.rules:
        documento = documented_document(columns, rule_values(rule, arm_id))
        regras.extend(documento["properties"]["securityRules"])

    return {
        "id": arm_id,
        "name": nsg.name,
        "properties": {"securityRules": regras},
    } | ({"location": location} if location is not None else {})


def _azure_segments(estate: CanonicalEstate) -> list[NetworkSegment]:
    """Os segmentos Azure que têm NSG com regras, em ordem determinística."""
    return sorted(
        (
            segment
            for segment in estate.network_segments
            if segment.provider == _AZURE and segment.network_security_group is not None
        ),
        key=lambda segment: (segment.scope_id, segment.region_id, segment.segment_uuid),
    )


def _nsg_path(target: Path, segment: NetworkSegment, nsg: NetworkSecurityGroup) -> Path:
    """O caminho do arquivo, derivado do ARM id que o próprio modelo compõe.

    O token de assinatura é lido do ARM id da NSG (``subscriptions/<token>``), e não do
    ``scope_id``: assim o caminho e o id que o flow log publica não podem discordar.
    """
    arm_id = nsg.arm_id()
    subscription = arm_id_token(arm_id, "subscriptions") or nsg.subscription_id
    resource_group = arm_id_token(arm_id, "resourcegroups") or nsg.resource_group
    return (
        target
        / "subscriptions"
        / subscription
        / "resourceGroups"
        / resource_group
        / "providers"
        / "Microsoft.Network"
        / "networkSecurityGroups"
        / nsg.name
        / f"{nsg.name}.json"
    )


def _model_gaps() -> list[dict[str, Any]]:
    """As lacunas que mantêm campos vazios nesta resposta -- o entregável do relatório."""
    return [
        {
            "item": "``sourceApplicationSecurityGroups``/``destinationApplicationSecurityGroups``",
            "reason": (
                "o campo pertence ao formato e nenhuma regra deste estado aponta para uma Application "
                "Security Group; os membros publicados (id/location) saem vazios dentro da lista, em vez "
                "de receberem um id inventado"
            ),
        },
        {
            "item": "formas PLURAIS dos prefixos e das portas",
            "reason": (
                "a Azure publica o par singular e o plural; o modelo guarda a forma singular (uma regra "
                "usa uma das duas), entao os plurais saem vazios -- preenche-los duplicaria o valor singular"
            ),
        },
        {
            "item": "``location`` do NSG",
            "reason": (
                "o resource group e o nome vem do modelo; a regiao do NSG e a do SEGMENTO, e o envio passa "
                "a regiao do segmento como location em vez de deixar o campo vazio"
            ),
        },
        {
            "item": "regras de plataforma (Default/AllowVnetInBound...)",
            "reason": (
                "a Azure cria tres regras de entrada e tres de saida por padrao; a pagina de template nao "
                "publica os seus nomes nem as suas prioridades, entao elas nao sao geradas -- gerar os "
                "literais seria inventar vocabulario"
            ),
        },
        {
            "item": "``apiVersion`` do envelope",
            "reason": (
                "nao e um campo do CORPO da resposta e nenhuma pagina consultada afirma qual versao e a "
                "corrente para o payload; a spec a registra como nao comprovada"
            ),
        },
    ]


class AzureNetworkSecurityGroupRenderer:
    """Entrega uma resposta ARM por NSG Azure do estado, com as regras em ``securityRules[]``."""

    name = "azure_nsg_rules"

    def render(self, estate: CanonicalEstate, out_dir: Path) -> list[Path]:
        """Escreve um JSON por NSG sob ``out_dir/azure_nsg_rules/subscriptions/...``."""
        target = out_dir / self.name
        columns = emittable_columns(_spec())
        written: list[Path] = []
        regras_por_acesso: Counter[str] = Counter()
        regras_por_direcao: Counter[str] = Counter()
        lacunas: Counter[str] = Counter()
        regras_total = 0

        for segment in _azure_segments(estate):
            nsg = segment.network_security_group
            if nsg is None:  # pragma: no cover - o filtro acima já garante
                continue
            document = nsg_document(nsg, columns, location=segment.region_id)
            caminho = _nsg_path(target, segment, nsg)
            write_json(caminho, document)
            # A projeção é derivada dos BYTES entregues (lidos de volta do disco), nunca de uma
            # segunda cópia em memória: é o que permite o núcleo de fidelidade conferir o arquivo.
            projecao = target / "field_projection" / f"{nsg.name}.json"
            write_json(
                projecao,
                documented_projection(json.loads(caminho.read_text(encoding="utf-8")), columns),
            )
            written.extend((caminho, projecao))
            regras_total += len(nsg.rules)
            for rule in nsg.rules:
                regras_por_acesso[rule.access] += 1
                regras_por_direcao[rule.direction] += 1
            if not any(
                rule.direction == DIRECTION_INGRESS and rule.access == DECISION_ALLOWED for rule in nsg.rules
            ):
                lacunas["nsg_sem_regra_inbound_allow"] += 1
            if not any(rule.access == DECISION_DENIED for rule in nsg.rules):
                lacunas["nsg_sem_regra_deny"] += 1

        write_json(
            target / PROVENANCE_FILE,
            provenance(
                _spec(),
                spec_file=_SPEC_FILE,
                artifacts=[
                    "subscriptions/**/networkSecurityGroups/*/*.json",
                    "field_projection/*.json",
                    PROVENANCE_FILE,
                ],
                mechanism={
                    "kind": "azure-arm-resource",
                    "file_name": "<nsgName>.json",
                    "path_template": (
                        "subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/"
                        "Microsoft.Network/networkSecurityGroups/{nsgName}/{nsgName}.json"
                    ),
                    "format": "json",
                    "compression": None,
                    "compression_note": "nenhuma compressao e documentada para uma resposta de API",
                    "encoding": "UTF-8 (o JSON e UTF-8 por definicao)",
                    "partitioning": (
                        "subscriptions/<guid>/resourceGroups/<rg>/providers/Microsoft.Network/"
                        "networkSecurityGroups/<nsg>/"
                    ),
                    "manifest": None,
                    "manifest_note": "resposta de API: nao ha manifesto de export para esta superficie",
                    "cadence": None,
                    "root": "properties.securityRules[]",
                    "delivery_note": (
                        "e a resposta do GET/list de networkSecurityGroups, como a superficie "
                        "arm-resource-representation: um corpo por NSG, nao um lote de export"
                    ),
                    "subscription_token": (
                        "lido do ARM id que o modelo compoe (GUID da assinatura), nunca do rotulo de escopo"
                    ),
                },
                columns={
                    "documented": len(_spec().columns),
                    "emittable": len(columns),
                    "generated": len(columns),
                    "sets": list(_spec().set_names),
                },
                counts={
                    "segments_azure_com_nsg": len(_azure_segments(estate)),
                    "rules": regras_total,
                    "by_access": dict(sorted(regras_por_acesso.items())),
                    "by_direction": dict(sorted(regras_por_direcao.items())),
                    **dict(lacunas),
                },
                not_generated=not_generated(_spec(), RULE_SCOPE) + not_generated(_spec(), NSG_SCOPE),
                model_gaps=_model_gaps(),
            ),
        )
        written.append(target / PROVENANCE_FILE)
        return written
