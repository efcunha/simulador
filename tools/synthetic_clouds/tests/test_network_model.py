"""Modelo canonico de rede: segmento, interface e fluxo.

O que estes testes protegem: a rede deixou de ser um renderer fiel e vazio. Sem
eles, o caminho de volta e silencioso -- os quatro renderers de flow log voltariam
a emitir formato sem dado, e nada acusaria.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import replace
from datetime import timedelta

import pytest

from tools.synthetic_clouds.generate.estate_builder import (
    FLOW_WINDOWS,
    NETWORK_ATTACHABLE_TYPES,
    build_estate,
)
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.identity import azure_subscription_guid
from tools.synthetic_clouds.model.network import (
    DECISIONS,
    DIRECTIONS,
    FLOW_STATES,
    NetworkFlow,
    NetworkInterface,
)
from tools.synthetic_clouds.validate.gate import run as run_gate
from tools.synthetic_clouds.validate.integrity import IntegrityError

PROVIDERS = ("aws", "azure", "gcp")


@pytest.fixture(scope="module")
def estate() -> CanonicalEstate:
    return build_estate(seed=123, profile="small", currency="USD")


# --- o inventario existe, nos tres provedores --------------------------------


def test_todo_provedor_tem_segmento_interface_e_fluxo(estate: CanonicalEstate) -> None:
    por_provedor = Counter(segment.provider for segment in estate.network_segments)
    assert set(por_provedor) == set(PROVIDERS), f"faltou provedor: {por_provedor}"
    assert len(estate.network_interfaces) > 0
    assert len(estate.network_flows) > 0


def test_toda_interface_pertence_a_um_recurso_que_carrega_interface(estate: CanonicalEstate) -> None:
    por_uuid = {resource.identity.uuid: resource for resource in estate.resources}
    for interface in estate.network_interfaces:
        recurso = por_uuid[interface.resource_uuid]
        assert recurso.resource_type in NETWORK_ATTACHABLE_TYPES, recurso.resource_type


def test_ids_nativos_seguem_a_forma_de_cada_provedor(estate: CanonicalEstate) -> None:
    for segment in estate.network_segments:
        if segment.provider == "aws":
            assert segment.segment_id.startswith("vpc-")
            assert segment.subnet_id.startswith("subnet-")
            assert segment.resource_group is None
        elif segment.provider == "azure":
            assert segment.segment_id.startswith("/subscriptions/")
            assert segment.resource_group, "o caminho do blob da Azure exige o resource group"
            assert segment.network_security_group_id is not None
            assert segment.network_security_group_uuid is not None
        else:
            assert segment.segment_id.startswith("projects/")
            assert segment.network_security_group_id is None


def test_guid_da_nsg_nao_e_a_assinatura(estate: CanonicalEstate) -> None:
    """``systemId`` do NSG e o GUID da NSG; projetar o scope_id ali seria mentir."""
    for segment in estate.network_segments:
        if segment.provider != "azure":
            continue
        assert segment.network_security_group_uuid != segment.scope_id
        assert len(segment.network_security_group_uuid or "") == 36


def test_arm_id_leva_o_guid_da_assinatura_e_nao_o_rotulo(estate: CanonicalEstate) -> None:
    """Um id ARM e afirmacao sobre o provedor, nao apelido interno.

    O FOCUS ja estampava ``azure_subscription_guid`` no ``SubAccountId`` e o
    promotor da Azure valida a forma 8-4-4-4-12; o modelo de rede embutia o rotulo
    (``sub-01``). Eram duas grafias da MESMA assinatura no mesmo estado, e a NIC
    que o flow log nomeia nao casava com a representacao ARM da VM.
    """
    for segment in estate.network_segments:
        if segment.provider != "azure":
            continue
        guid = azure_subscription_guid(estate.seed, segment.scope_id)
        assert guid in segment.segment_id, segment.segment_id
        assert f"/subscriptions/{segment.scope_id}/" not in segment.segment_id, "rotulo num ARM id"
        assert guid in (segment.network_security_group_id or "")

    for interface in estate.network_interfaces:
        if interface.interface_id.startswith("/subscriptions/"):
            assert "sub-0" not in interface.interface_id.split("/")[2]

    for perfil in estate.instance_profiles:
        if perfil.native_id.startswith("/subscriptions/"):
            assert perfil.native_id.split("/")[2] == azure_subscription_guid(
                estate.seed, next(
                    segment.scope_id
                    for segment in estate.network_segments
                    if segment.segment_uuid == perfil.segment_uuid
                )
            )


def test_mac_e_ip_sao_bem_formados_e_unicos(estate: CanonicalEstate) -> None:
    macs = [interface.mac_address for interface in estate.network_interfaces]
    assert len(set(macs)) == len(macs), "MAC repetido entre interfaces"
    for interface in estate.network_interfaces:
        partes = interface.mac_address.split(":")
        assert len(partes) == 6
        assert all(len(parte) == 2 for parte in partes)
        assert interface.mac_address.startswith("02:00:"), "MAC fora do prefixo de administracao local"
        assert interface.private_ip.startswith("10.")


# --- o fluxo pendura no inventario -------------------------------------------


def test_volume_de_fluxo_e_interface_vezes_janelas(estate: CanonicalEstate) -> None:
    assert len(estate.network_flows) == len(estate.network_interfaces) * FLOW_WINDOWS


def test_fluxo_tem_janela_de_uma_hora_e_doze_janelas_distintas(estate: CanonicalEstate) -> None:
    janelas = {(flow.window_start, flow.window_end) for flow in estate.network_flows}
    assert len(janelas) == FLOW_WINDOWS
    for inicio, fim in janelas:
        assert fim - inicio == timedelta(minutes=5)


def test_pelo_menos_uma_ponta_do_fluxo_esta_no_estate(estate: CanonicalEstate) -> None:
    uuids = {interface.interface_uuid for interface in estate.network_interfaces}
    for flow in estate.network_flows:
        pontas = [flow.src_interface_uuid, flow.dst_interface_uuid]
        assert any(ponta in uuids for ponta in pontas), flow.flow_id
        assert flow.log_resource_id, flow.flow_id


def test_valores_ficam_no_dominio_documentado(estate: CanonicalEstate) -> None:
    for flow in estate.network_flows:
        assert flow.protocol_number in {1, 6, 17}, "fora dos numeros IANA que as nuvens publicam"
        assert 1 <= flow.src_port <= 65535
        assert 1 <= flow.dst_port <= 65535
        assert flow.packets >= 0 and flow.bytes >= 0
        assert flow.direction in DIRECTIONS
        assert flow.decision in DECISIONS


# --- marcas especificas de cada nuvem, sem uniformizar -----------------------


def test_marcas_por_nuvem_aparecem_so_onde_a_nuvem_as_publica(estate: CanonicalEstate) -> None:
    provedor_do_segmento = {segment.segment_uuid: segment.provider for segment in estate.network_segments}
    por_provedor: dict[str, list[NetworkFlow]] = defaultdict(list)
    for flow in estate.network_flows:
        por_provedor[provedor_do_segmento[flow.segment_uuid]].append(flow)

    for flow in por_provedor["aws"]:
        assert flow.flow_state is None, "estado do fluxo e da Azure"
        assert flow.reported_by is None, "reporter por ponta e do GCP"
        assert flow.packets_reverse is None, "contador reverso e da Azure"

    for flow in por_provedor["azure"]:
        assert flow.flow_state in FLOW_STATES
        assert flow.packets_reverse is not None
        assert flow.reported_by is None

    for flow in por_provedor["gcp"]:
        assert flow.reported_by in {"SRC", "DEST"}
        assert flow.flow_state is None


# --- determinismo e gate ------------------------------------------------------


def test_duas_construcoes_produzem_a_mesma_rede() -> None:
    primeira = build_estate(seed=7, profile="small", currency="USD")
    segunda = build_estate(seed=7, profile="small", currency="USD")

    assert primeira.network_segments == segunda.network_segments
    assert primeira.network_interfaces == segunda.network_interfaces
    assert primeira.network_flows == segunda.network_flows


def test_sementes_diferentes_produzem_redes_diferentes() -> None:
    a = build_estate(seed=1, profile="small", currency="USD")
    b = build_estate(seed=2, profile="small", currency="USD")

    assert a.network_flows != b.network_flows


def test_o_gate_aceita_a_rede_gerada(estate: CanonicalEstate) -> None:
    run_gate(estate)  # levanta se algo estiver orfao ou fora do vocabulario


def test_o_gate_recusa_interface_orfa(estate: CanonicalEstate) -> None:
    """Prova que a invariante sabe falhar, em vez de passar por vacuidade."""
    orfa = NetworkInterface(
        interface_uuid="interface-orfa",
        resource_uuid="recurso-que-nao-existe",
        segment_uuid=estate.network_segments[0].segment_uuid,
        interface_id="eni-orfa",
        mac_address="02:00:00:00:00:00",
        private_ip="10.0.0.1",
        region_id="r",
    )
    corrompido = replace(estate, network_interfaces=estate.network_interfaces + (orfa,))

    with pytest.raises(IntegrityError, match="orphan network interface"):
        run_gate(corrompido)


def test_o_gate_recusa_fluxo_sem_ponta_no_estate(estate: CanonicalEstate) -> None:
    fluxo = estate.network_flows[0]
    solto = replace(fluxo, src_interface_uuid=None, dst_interface_uuid=None)
    corrompido = replace(estate, network_flows=(solto,))

    with pytest.raises(IntegrityError, match="sem nenhuma ponta"):
        run_gate(corrompido)
