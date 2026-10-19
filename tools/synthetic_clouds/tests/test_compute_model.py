"""Perfil de instancia: o dado que faltava nas superficies de computo.

Os renderers de instancia estavam fieis ao formato e vazios -- a representacao
REST do Compute preenchia 3 dos 48 campos, o `DescribeInstances` 3 dos 61 membros
de `Instance`. Estes testes protegem o dado e, sobretudo, a COERENCIA com a rede:
uma instancia cujo IP privado difere do IP da sua propria NIC e estado impossivel.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import replace

import pytest

from tools.synthetic_clouds.generate.estate_builder import INSTANCE_TYPE_BY_SKU, build_estate
from tools.synthetic_clouds.model.compute import STATES
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.identity import AWS_ID_PREFIXES, aws_resource_id
from tools.synthetic_clouds.validate.gate import run as run_gate
from tools.synthetic_clouds.validate.integrity import IntegrityError


@pytest.fixture(scope="module")
def estate() -> CanonicalEstate:
    return build_estate(seed=123, profile="small", currency="USD")


def test_ha_perfil_por_interface_e_nos_tres_provedores(estate: CanonicalEstate) -> None:
    assert len(estate.instance_profiles) == len(estate.network_interfaces)
    assert set(Counter(perfil.provider for perfil in estate.instance_profiles)) == {"aws", "azure", "gcp"}


def test_ip_privado_da_instancia_e_o_da_sua_propria_interface(estate: CanonicalEstate) -> None:
    por_uuid = {interface.interface_uuid: interface for interface in estate.network_interfaces}
    for perfil in estate.instance_profiles:
        assert perfil.interface_uuid is not None
        interface = por_uuid[perfil.interface_uuid]
        assert perfil.private_ip == interface.private_ip
        assert perfil.resource_uuid == interface.resource_uuid
        assert perfil.segment_uuid == interface.segment_uuid


def test_tipo_de_instancia_vem_do_catalogo_e_nunca_e_adivinhado(estate: CanonicalEstate) -> None:
    """O tipo sai de uma tabela explicita; SKU fora dela produz None, nao palpite."""
    por_uuid = {resource.identity.uuid: resource for resource in estate.resources}
    for perfil in estate.instance_profiles:
        sku = por_uuid[perfil.resource_uuid].sku_id
        esperado = INSTANCE_TYPE_BY_SKU.get(sku)
        assert perfil.instance_type == esperado, f"{sku} -> {perfil.instance_type!r}"
        if perfil.instance_type is not None:
            assert sku in INSTANCE_TYPE_BY_SKU


def test_zona_segue_a_forma_de_cada_provedor(estate: CanonicalEstate) -> None:
    for perfil in estate.instance_profiles:
        assert perfil.zone, perfil.native_id
        if perfil.provider == "aws":
            assert perfil.zone[-1].isalpha()
        elif perfil.provider == "gcp":
            assert "-" in perfil.zone and perfil.zone[-1].isalpha()
        else:
            assert perfil.zone in {"1", "2", "3"}


def test_id_nativo_segue_a_forma_de_cada_provedor(estate: CanonicalEstate) -> None:
    """Na AWS o id sai de ``aws_resource_id`` -- a MESMA fonte que os renderers usam.

    Antes o perfil derivava ``i-`` + hex do uuid por conta propria enquanto as
    superficies AWS usavam ``aws_resource_id``: a mesma instancia tinha DOIS ids, e
    os renderers de ARM e GCP liam um enquanto a AWS lia o outro.
    """
    por_uuid = {resource.identity.uuid: resource for resource in estate.resources}
    for perfil in estate.instance_profiles:
        recurso = por_uuid[perfil.resource_uuid]
        if perfil.provider == "aws":
            assert perfil.native_id == aws_resource_id(recurso.resource_type, perfil.resource_uuid)
            assert perfil.native_id.startswith(AWS_ID_PREFIXES[recurso.resource_type])
            assert perfil.image_id is not None and perfil.image_id.startswith("ami-")
        elif perfil.provider == "azure":
            assert perfil.native_id.startswith("/subscriptions/")
            assert "Microsoft.Compute/virtualMachines" in perfil.native_id
        else:
            assert perfil.native_id.isdigit(), "o id do Compute e uint64"
            assert perfil.image_id is not None and perfil.image_id.startswith("projects/")


def test_ip_publico_usa_faixa_de_documentacao(estate: CanonicalEstate) -> None:
    publicos = [perfil.public_ip for perfil in estate.instance_profiles if perfil.public_ip]
    assert publicos, "nenhuma instancia com IP publico"
    for endereco in publicos:
        assert endereco.startswith(("198.51.100.", "203.0.113.")), "fora da faixa RFC 5737"


def test_estado_e_lancamento_ficam_no_dominio(estate: CanonicalEstate) -> None:
    for perfil in estate.instance_profiles:
        assert perfil.state in STATES
        assert estate.sim_start <= perfil.launch_time.date() <= estate.sim_now
        assert perfil.root_volume_size_gb > 0


def test_perfis_sao_deterministicos_e_sensíveis_a_semente() -> None:
    a = build_estate(seed=5, profile="small", currency="USD")
    b = build_estate(seed=5, profile="small", currency="USD")
    c = build_estate(seed=6, profile="small", currency="USD")

    assert a.instance_profiles == b.instance_profiles
    assert a.instance_profiles != c.instance_profiles


def test_o_gate_aceita_os_perfis(estate: CanonicalEstate) -> None:
    run_gate(estate)


def test_o_gate_recusa_ip_divergente_da_interface(estate: CanonicalEstate) -> None:
    """A coerencia de IP e o que impede um estado impossivel de existir calado."""
    perfil = estate.instance_profiles[0]
    divergente = replace(perfil, private_ip="10.255.255.255")
    corrompido = replace(estate, instance_profiles=(divergente,))

    with pytest.raises(IntegrityError, match="diferente do IP da sua propria interface"):
        run_gate(corrompido)


def test_o_gate_recusa_interface_de_outro_recurso(estate: CanonicalEstate) -> None:
    perfil = estate.instance_profiles[0]
    outra = estate.network_interfaces[-1]
    trocado = replace(perfil, interface_uuid=outra.interface_uuid, private_ip=outra.private_ip)
    corrompido = replace(estate, instance_profiles=(trocado,))

    with pytest.raises(IntegrityError, match="interface de outro recurso"):
        run_gate(corrompido)
