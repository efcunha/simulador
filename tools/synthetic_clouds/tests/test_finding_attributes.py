"""Titulo, descricao e ``Types`` do finding: campos OBRIGATORIOS que saiam vazios.

O ASFF marca os tres como obrigatorios. Antes de 2026-10-14 o modelo nao os
carregava, entao o artefato entregava as colunas e nenhum valor -- fiel ao formato
e vazio, outra vez. Estes testes protegem o dado e os limites que a documentacao
publica.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from tools.synthetic_clouds.generate.estate_builder import (
    FINDING_CLASSIFIER_BY_CATEGORY,
    FINDING_TEXT_BY_CATEGORY,
    FINDING_TYPE_NAMESPACES,
    build_estate,
)
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.scenarios.emit import apply_all
from tools.synthetic_clouds.validate.gate import run as run_gate
from tools.synthetic_clouds.validate.quality import (
    DESCRIPTION_MAX,
    GENERATOR_ID_MAX,
    PRODUCT_NAME_MAX,
    TITLE_MAX,
    QualityError,
)

CATEGORIAS = tuple(FINDING_TEXT_BY_CATEGORY)


@pytest.fixture(scope="module")
def estate() -> CanonicalEstate:
    return build_estate(seed=123, profile="small", currency="USD")


def test_todo_finding_tem_os_tres_campos_obrigatorios(estate: CanonicalEstate) -> None:
    assert estate.findings
    for finding in estate.findings:
        assert finding.title, finding.finding_id
        assert finding.description, finding.finding_id
        assert finding.types, finding.finding_id


def test_titulo_e_descricao_respeitam_os_limites_documentados(estate: CanonicalEstate) -> None:
    for finding in estate.findings:
        assert len(finding.title) <= TITLE_MAX
        assert len(finding.description) <= DESCRIPTION_MAX


def test_namespace_de_types_vem_da_lista_fechada_do_asff(estate: CanonicalEstate) -> None:
    for finding in estate.findings:
        for tipo in finding.types:
            namespace = tipo.split("/", 1)[0]
            assert namespace in FINDING_TYPE_NAMESPACES, tipo
            assert tipo.count("/") == 2, "a forma documentada e namespace/category/classifier"


def test_titulo_e_descricao_citam_o_recurso(estate: CanonicalEstate) -> None:
    """Um titulo generico serviria, mas o nome do recurso e o que torna o dado util."""
    por_uuid = {resource.identity.uuid: resource for resource in estate.resources}
    for finding in estate.findings:
        nome = por_uuid[finding.resource_uuid].resource_name
        assert nome in finding.title
        assert nome in finding.description


def test_cada_categoria_nativa_tem_texto_e_classificador_proprios() -> None:
    for categoria in CATEGORIAS:
        assert categoria in FINDING_CLASSIFIER_BY_CATEGORY, categoria


def test_os_findings_do_cenario_c09_tambem_carregam_os_campos(estate: CanonicalEstate) -> None:
    """O C09 acrescenta findings por outro caminho; sem os campos, o gate reprovaria."""
    com_cenario = apply_all(estate)
    assert len(com_cenario.findings) > len(estate.findings)
    for finding in com_cenario.findings:
        assert finding.title and finding.description and finding.types


def test_sao_deterministicos_e_sensiveis_a_semente() -> None:
    a = build_estate(seed=11, profile="small", currency="USD")
    b = build_estate(seed=11, profile="small", currency="USD")
    c = build_estate(seed=12, profile="small", currency="USD")

    assert [(f.title, f.types) for f in a.findings] == [(f.title, f.types) for f in b.findings]
    assert [(f.title, f.types) for f in a.findings] != [(f.title, f.types) for f in c.findings]


def test_o_gate_aceita_os_findings_gerados(estate: CanonicalEstate) -> None:
    run_gate(estate)


def test_o_gate_recusa_titulo_vazio(estate: CanonicalEstate) -> None:
    corrompido = replace(estate, findings=(replace(estate.findings[0], title=""),))

    with pytest.raises(QualityError, match="titulo fora de"):
        run_gate(corrompido)


def test_o_gate_recusa_descricao_longa_demais(estate: CanonicalEstate) -> None:
    longa = "x" * (DESCRIPTION_MAX + 1)
    corrompido = replace(estate, findings=(replace(estate.findings[0], description=longa),))

    with pytest.raises(QualityError, match="descricao fora de"):
        run_gate(corrompido)


def test_o_gate_recusa_namespace_fora_da_lista(estate: CanonicalEstate) -> None:
    inventado = replace(estate.findings[0], types=("Namespace Que Nao Existe/x/y",))
    corrompido = replace(estate, findings=(inventado,))

    with pytest.raises(QualityError, match="fora da lista"):
        run_gate(corrompido)


def test_o_gate_recusa_types_vazio(estate: CanonicalEstate) -> None:
    corrompido = replace(estate, findings=(replace(estate.findings[0], types=()),))

    with pytest.raises(QualityError, match="sem 'types'"):
        run_gate(corrompido)


# --- procedencia e escalas ---------------------------------------------------


def test_toda_finding_carrega_procedencia(estate: CanonicalEstate) -> None:
    """``GeneratorId`` e obrigatorio no ASFF; produto e empresa tem limites publicados."""
    for finding in estate.findings:
        assert finding.generator_id, finding.finding_id
        assert finding.product_name, finding.finding_id
        assert finding.company_name, finding.finding_id
        assert len(finding.generator_id) <= GENERATOR_ID_MAX
        assert len(finding.product_name) <= PRODUCT_NAME_MAX
        assert len(finding.company_name) <= PRODUCT_NAME_MAX


def test_escalas_ficam_em_zero_a_cem(estate: CanonicalEstate) -> None:
    for finding in estate.findings:
        assert finding.confidence is not None and 0 <= finding.confidence <= 100
        assert finding.criticality is not None and 0 <= finding.criticality <= 100


def test_primeira_observacao_cai_no_dia_do_alerta_e_com_fuso(estate: CanonicalEstate) -> None:
    for finding in estate.findings:
        assert finding.first_observed_at is not None
        assert finding.first_observed_at.tzinfo is not None, "a documentacao exige UTC"
        assert finding.first_observed_at.date() == finding.raised_on
        assert estate.sim_start <= finding.first_observed_at.date() <= estate.sim_now


def test_procedencia_e_deterministica() -> None:
    a = build_estate(seed=21, profile="small", currency="USD")
    b = build_estate(seed=21, profile="small", currency="USD")

    assert [(f.confidence, f.criticality, f.first_observed_at) for f in a.findings] == [
        (f.confidence, f.criticality, f.first_observed_at) for f in b.findings
    ]


def test_o_gate_recusa_escala_fora_da_faixa(estate: CanonicalEstate) -> None:
    corrompido = replace(estate, findings=(replace(estate.findings[0], criticality=101),))

    with pytest.raises(QualityError, match="fora da escala"):
        run_gate(corrompido)


def test_o_gate_recusa_generator_id_vazio(estate: CanonicalEstate) -> None:
    corrompido = replace(estate, findings=(replace(estate.findings[0], generator_id=""),))

    with pytest.raises(QualityError, match="generator_id"):
        run_gate(corrompido)


def test_o_gate_recusa_primeira_observacao_sem_fuso(estate: CanonicalEstate) -> None:
    sem_fuso = replace(estate.findings[0], first_observed_at=datetime(2026, 1, 1, 12, 0))
    corrompido = replace(estate, findings=(sem_fuso,))

    with pytest.raises(QualityError, match="fuso"):
        run_gate(corrompido)


def test_o_gate_recusa_primeira_observacao_fora_da_janela(estate: CanonicalEstate) -> None:
    fora = replace(
        estate.findings[0],
        first_observed_at=datetime(2020, 1, 1, tzinfo=UTC),
    )
    corrompido = replace(estate, findings=(fora,))

    with pytest.raises(QualityError, match="fora da janela"):
        run_gate(corrompido)
