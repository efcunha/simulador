"""Vocabulario de tipos: o nome que cada nuvem usa para o mesmo recurso.

Existe porque os renderers de inventario, configuracao e seguranca precisam
escrever o tipo do recurso na forma da nuvem, e o token do simulador
(``ec2_instance``) nao e esse nome. Sem esta tabela, cada renderer inventaria o
seu -- ou pior, escreveria o token do simulador num campo que a nuvem define.

**So entra o que a documentacao exemplifica.** Onde ela nao da o nome, usamos o
valor que a propria documentacao define como escape, em vez de deduzir o padrao e
arriscar um nome plausivel e errado. Cada entrada cita a spec que a sustenta.

Fontes (consultadas em 2026-10-14), com a linha exata, para a afirmacao ser conferivel:

* AWS Config -- ``resourceType``, ``specs/aws/aws-config-snapshot-s3.md`` linha 113:
  "Lista de tipos suportados (ex.: ``AWS::EC2::Instance``, ``AWS::EC2::Volume``,
  ``AWS::EC2::SUBNET``). Alterado dinamicamente". Os EXEMPLOS estao documentados;
  a lista completa e declarada dinamica e NAO e enumeravel aqui.
* ASFF -- ``Resources[].Type``, ``specs/aws/security-hub-asff.md`` linha 166:
  "comprimento 1-256. ``AwsEc2Instance``, ``AwsS3Bucket``, ... ou ``Other``". Os
  dois exemplos e o escape ``Other`` estao documentados; o resto do dominio nao.
* CAI -- ``assetType``, ``specs/gcp/cloud-asset-inventory-compute-instance.md``
  linhas 40, 50 e 192: ``compute.googleapis.com/Instance`` e
  ``compute.googleapis.com/Disk``.
* ARM -- ``specs/azure/azure-resource-graph-virtual-machines.schema.json``: os
  nomes dos CONJUNTOS sao os tipos publicados (``Resources/microsoft.compute/
  virtualmachines``). O de disco vem do id de exemplo em
  ``azure-resource-graph-virtual-machines.md`` linha 138
  (``/subscriptions/.../Microsoft.Compute/disks/ContosoVM1_OsDisk``); a caixa
  baixa segue a convencao dos nomes de conjunto, e id ARM nao diferencia caixa.
"""

from __future__ import annotations

#: Escape documentado do ASFF para o recurso que nao tem tipo proprio enumerado.
#: Existe justamente para nao precisarmos adivinhar o nome.
ASFF_OTHER = "Other"

#: Tipo do AWS Config por token do catalogo. Somente os exemplos que a spec cita.
CONFIG_TYPE_BY_RESOURCE: dict[str, str] = {
    "ec2_instance": "AWS::EC2::Instance",
    "ebs_volume": "AWS::EC2::Volume",
}

#: Tipo ASFF por token do catalogo. Somente os exemplos que a spec cita; o resto
#: cai em ``OTHER``, que e valor documentado.
ASFF_TYPE_BY_RESOURCE: dict[str, str] = {
    "ec2_instance": "AwsEc2Instance",
    "s3_bucket": "AwsS3Bucket",
}

#: ``assetType`` do Cloud Asset Inventory por token do catalogo.
CAI_ASSET_TYPE_BY_RESOURCE: dict[str, str] = {
    "compute_instance": "compute.googleapis.com/Instance",
    "persistent_disk": "compute.googleapis.com/Disk",
}

#: Tipo ARM por token do catalogo, na forma que o Resource Graph publica.
ARM_TYPE_BY_RESOURCE: dict[str, str] = {
    "virtual_machine": "microsoft.compute/virtualmachines",
    "managed_disk": "microsoft.compute/disks",
}


def config_type(resource_type: str) -> str | None:
    """Tipo do AWS Config, ou ``None`` quando a documentacao nao o exemplifica.

    ``None`` e a resposta correta: a coluna sai vazia em vez de carregar um nome
    deduzido do padrao ``AWS::Servico::Recurso``.
    """
    return CONFIG_TYPE_BY_RESOURCE.get(resource_type)


def asff_type(resource_type: str) -> str:
    """Tipo ASFF do recurso, com o escape documentado ``Other`` como padrao."""
    return ASFF_TYPE_BY_RESOURCE.get(resource_type, ASFF_OTHER)


def cai_asset_type(resource_type: str) -> str | None:
    """``assetType`` do CAI, ou ``None`` quando a spec nao o exemplifica."""
    return CAI_ASSET_TYPE_BY_RESOURCE.get(resource_type)


def arm_type(resource_type: str) -> str | None:
    """Tipo ARM, ou ``None`` quando a spec nao o exemplifica."""
    return ARM_TYPE_BY_RESOURCE.get(resource_type)
