"""Perfil de instancia: o que cada nuvem documenta sobre uma instancia de computo.

Fecha a outra metade do mesmo problema que o modelo de rede fechou. Os renderers
de instancia estavam fieis ao FORMATO e vazios de DADO: a representacao REST do
Compute tem 48 campos e so 3 tinham valor, o `DescribeInstances` preenchia 3 dos
61 membros de `Instance`, e o ARM/Resource Graph saiam quase ocos.

Duas regras governam este modulo:

**Derivacao, nunca invencao.** O tipo de instancia sai do catalogo de SKU, que ja
codifica o tipo (`aws-ec2-m5-large` -> ``m5.large``, `azure-vm-d2s-v5` ->
``Standard_D2s_v5``, `gcp-ce-e2-standard-2` -> ``e2-standard-2``). Quando o
catalogo nao diz, o campo fica ``None`` -- e o renderer emite a coluna vazia.

**Coerencia com a rede.** ``private_ip``, ``segment_uuid`` e ``interface_uuid``
vem da MESMA interface que o modelo de rede criou para o recurso. Uma instancia
com IP diferente do IP da sua propria NIC seria um estado incoerente, e o gate
recusa.

Assim como no protocolo e na direcao, o estado da instancia e guardado no
vocabulario CANONICO (``running``/``stopped``); cada renderer traduz para a forma
documentada da sua nuvem (AWS ``running``/``stopped``, GCP ``RUNNING``/
``TERMINATED``, Azure ``PowerState/running``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

STATE_RUNNING = "running"
STATE_STOPPED = "stopped"
STATES = (STATE_RUNNING, STATE_STOPPED)


@dataclass(slots=True, frozen=True)
class InstanceProfile:
    """O que se sabe sobre uma instancia de computo, com lastro no estado."""

    resource_uuid: str  # FK -> ResourceIdentity.uuid
    provider: str  # aws | azure | gcp
    native_id: str  # i-... | ARM id da VM | id numerico do Compute
    instance_type: str | None  # derivado do SKU do catalogo; None se ele nao diz
    zone: str | None  # regiao + letra, na forma que as nuvens publicam
    state: str  # canonico: running | stopped
    private_ip: str  # IGUAL ao da interface do mesmo recurso
    public_ip: str | None
    image_id: str | None
    launch_time: datetime  # UTC
    root_volume_size_gb: int
    root_volume_type: str | None
    segment_uuid: str | None  # FK -> NetworkSegment do mesmo recurso
    interface_uuid: str | None  # FK -> NetworkInterface do mesmo recurso
