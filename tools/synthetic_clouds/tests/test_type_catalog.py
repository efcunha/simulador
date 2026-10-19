"""O vocabulario de tipos so afirma o que a documentacao exemplifica.

O risco aqui nao e esquecer uma entrada: e preencher a lacuna deduzindo o padrao
do nome. ``AwsLambdaFunction`` parece certo e pode nao ser o valor publicado; por
isso a tabela so carrega os exemplos que a spec cita, e o resto cai no escape
documentado (``Other``) ou em ``None`` -- que vira coluna vazia.
"""

from __future__ import annotations

from tools.synthetic_clouds.generate import constants as const
from tools.synthetic_clouds.generate.type_catalog import (
    ARM_TYPE_BY_RESOURCE,
    ASFF_OTHER,
    ASFF_TYPE_BY_RESOURCE,
    CAI_ASSET_TYPE_BY_RESOURCE,
    CONFIG_TYPE_BY_RESOURCE,
    arm_type,
    asff_type,
    cai_asset_type,
    config_type,
)

TABELAS = (
    CONFIG_TYPE_BY_RESOURCE,
    ASFF_TYPE_BY_RESOURCE,
    CAI_ASSET_TYPE_BY_RESOURCE,
    ARM_TYPE_BY_RESOURCE,
)


def _tipos_do_catalogo() -> set[str]:
    return {
        linha[0]
        for nome in ("AWS_SERVICES", "AZURE_SERVICES", "GCP_SERVICES")
        for linha in getattr(const, nome)
    }


def test_toda_entrada_aponta_para_um_tipo_real_do_catalogo() -> None:
    """Uma tabela que cita token inexistente vira documentacao morta."""
    validos = _tipos_do_catalogo()
    for tabela in TABELAS:
        for token in tabela:
            assert token in validos, f"{token!r} nao e um tipo de recurso do catalogo"


def test_os_exemplos_documentados_estao_na_tabela() -> None:
    assert config_type("ec2_instance") == "AWS::EC2::Instance"
    assert config_type("ebs_volume") == "AWS::EC2::Volume"
    assert asff_type("ec2_instance") == "AwsEc2Instance"
    assert asff_type("s3_bucket") == "AwsS3Bucket"
    assert cai_asset_type("compute_instance") == "compute.googleapis.com/Instance"
    assert cai_asset_type("persistent_disk") == "compute.googleapis.com/Disk"
    assert arm_type("virtual_machine") == "microsoft.compute/virtualmachines"


def test_token_sem_exemplo_documentado_devolve_none() -> None:
    """``None`` e a resposta honesta: a coluna sai vazia em vez de adivinhada."""
    assert config_type("lambda_function") is None
    assert cai_asset_type("cloud_run_service") is None
    assert arm_type("openai") is None


def test_asff_usa_o_escape_documentado_em_vez_de_deduzir_o_nome() -> None:
    """``Other`` esta publicado; ``AwsLambdaFunction`` seria deducao nossa."""
    for token in ("lambda_function", "cloudwatch_logs", "dynamodb_table"):
        assert asff_type(token) == ASFF_OTHER


def test_asff_nunca_devolve_none() -> None:
    """O escape cobre todo o resto, entao a coluna nunca fica sem valor no ASFF."""
    validos = _tipos_do_catalogo()
    for token in validos:
        assert asff_type(token)
