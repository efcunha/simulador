"""Ids cunhados pelo modelo: forma documentada, unicidade e determinismo.

Os ids de provedor que o estado precisa inventar (o ``InstanceId`` da AWS, o
GUID da assinatura Azure, o SKU do GCP) existem porque reusar o ``ResourceIdentity.uuid``
poria um UUIDv5 num campo cuja forma a documentacao publica -- e um consumidor que
valida a forma recusaria o dado. O que estes testes protegem: a forma, a unicidade
e o determinismo. A entropia real do provedor NAO e reproduzida, e isso esta dito
no docstring de cada canho.
"""

from __future__ import annotations

import re

import pytest

from tools.synthetic_clouds.generate import constants as const
from tools.synthetic_clouds.model.identity import gcp_sku_id

#: Forma do exemplo documentado: ``2E27-4F75-95CD``.
_FORMA_SKU = re.compile(r"^[0-9A-F]{4}(-[0-9A-F]{4}){3}$")


def _skus_do_catalogo() -> list[str]:
    return [linha[3] for linha in const.GCP_SERVICES]


def test_sku_do_gcp_segue_a_forma_do_exemplo_documentado() -> None:
    for sku in _skus_do_catalogo():
        assert _FORMA_SKU.match(gcp_sku_id(123, sku)), sku


def test_cada_sku_do_catalogo_tem_id_proprio() -> None:
    """Fundir SKUs distintos numa linha de preco e o defeito que isto evita."""
    ids = [gcp_sku_id(123, sku) for sku in _skus_do_catalogo()]

    assert len(set(ids)) == len(ids)


def test_sku_e_estavel_por_semente_e_muda_com_ela() -> None:
    assert gcp_sku_id(7, "gcp-pd-ssd") == gcp_sku_id(7, "gcp-pd-ssd")
    assert gcp_sku_id(7, "gcp-pd-ssd") != gcp_sku_id(8, "gcp-pd-ssd")


def test_o_id_nao_e_o_token_do_catalogo() -> None:
    """Escrever o token do simulador no campo do provedor seria o defeito simetrico."""
    for sku in _skus_do_catalogo():
        assert gcp_sku_id(123, sku) != sku


@pytest.mark.parametrize("seed", [0, 1, 123, 999_999])
def test_nunca_colide_entre_skus_em_sementes_diversas(seed: int) -> None:
    ids = [gcp_sku_id(seed, sku) for sku in _skus_do_catalogo()]

    assert len(set(ids)) == len(ids)
