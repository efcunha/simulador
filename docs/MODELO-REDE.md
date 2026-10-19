# Modelo canônico de rede

> **Estado (2026-10-14): implementado no modelo.** `model/network.py` traz
> `NetworkSegment`, `NetworkInterface` e `NetworkFlow`; `estate_builder` gera os
> três com streams nomeados; o gate recusa interface órfã, fluxo sem ponta e
> vocabulário fora do canônico; e `tests/test_network_model.py` prova
> determinismo, forma dos ids e presença das marcas por nuvem.
>
> Ordem respeitada: **inventário primeiro, fluxo depois** — como este documento
> argumenta. O que **falta** é o outro lado: os quatro renderers de flow log ainda
> não projetam esses dados, então continuam fiéis ao formato e vazios. É a próxima
> onda, e é trabalho de renderer, não de modelo.

Especificação do que o modelo do simulador precisa carregar para que os quatro
renderers de flow log tenham **dado real** a projetar. Escrita em 2026-10-14,
derivada das especificações já levantadas em `specs/` — nenhum campo aqui foi
inventado; a coluna "fonte" diz de qual spec cada grupo vem.

Existe porque fidelidade de coluna **não** é o mesmo que dado presente: hoje os
renderers de fluxo podem sair fiéis ao formato e com as listas vazias, já que o
modelo canônico não tem tipo algum para registro de fluxo.

## As quatro superfícies, como cada nuvem realmente entrega

| Superfície | Entrega documentada | Forma do registro | Campos |
|---|---|---|---|
| `aws/vpc-flow-logs-s3` | S3, gzip, texto ou Parquet | **colunas nomeadas** | 54 |
| `azure/nsg-flow-logs-v2` | Blob, JSON, `PT1H.json` | envelope + **tupla posicional** de 13 posições | 26 + 13 |
| `azure/vnet-flow-logs` | Blob, JSON | envelope de 23 + tupla de 13 posições, **mais** duas tabelas de tráfego analisado (62 e 14) | 127 |
| `gcp/vpc-flow-logs-bigquery` | Logging; BigQuery só como **dataset vinculado** | colunas nomeadas, muitas aninhadas | 181 |

Três consequências que o modelo precisa respeitar:

1. **Azure entrega posicional, não nomeado.** `flowTuples` é uma string com campos
   separados por vírgula. O modelo tem de carregar os campos; o renderer é quem
   os achata na ordem documentada.
2. **As tabelas `NTANetAnalytics` e `NTAIpDetails` são agregações**, produzidas por
   traffic analytics — não são registros crus. O modelo não deve alimentá-las com
   o mesmo objeto: são outra coisa, e misturá-las seria inventar semântica.
3. **GCP não exporta para BigQuery.** O destino é o Cloud Logging; o BigQuery é
   dataset vinculado. Registrar isso não é detalhe: muda o que o renderer emite.

## O núcleo: o que as QUATRO nuvens carregam

Estes campos existem, com nome próprio, em todas as quatro superfícies. São o
mínimo que um registro canônico precisa ter para não sair vazio em nenhuma delas.

| Campo canônico | AWS | Azure NSG | Azure VNet | GCP |
|---|---|---|---|---|
| início da janela | `start` | posição 0 | posição 0 | `start_time` |
| fim da janela | `end` | posição 0 | posição 0 | `end_time` |
| IP de origem | `srcaddr` | posição 1 | posição 1 | `connection.src_ip` |
| IP de destino | `dstaddr` | posição 2 | posição 2 | `connection.dest_ip` |
| porta de origem | `srcport` | posição 3 | posição 3 | `connection.src_port` |
| porta de destino | `dstport` | posição 4 | posição 4 | `connection.dest_port` |
| protocolo | `protocol` | posição 5 | posição 5 | `connection.protocol` |
| direção | `flow-direction` | posição 6 | posição 6 | `connection_direction` |
| decisão | `action` | posição 7 | posição 7 | `disposition` |
| pacotes | `packets` | posição 9 | posição 9 | `packets_sent` |
| bytes | `bytes` | posição 10 | posição 10 | `bytes_sent` |
| conta / projeto | `account-id` | `systemId` | `flowLogResourceID` | `src_vpc.project_id` |
| recurso do log | `interface-id` | `resourceId` | `targetResourceID` | `src_vpc.vpc_name` |
| região | `region` | (no `resourceId`) | (no `targetResourceID`) | `src_location.region` |

## Grupos adicionais, por quantas nuvens os carregam

**Contadores reversos** (Azure NSG e VNet, posições 11–13: pacotes e bytes
recebidos): `packets_reverse`, `bytes_reverse`. A AWS expressa a via reversa como
uma linha própria, e o GCP usa o campo `reporter` (`SRC`/`DEST`) — o mesmo fluxo
pode ser reportado pelas duas pontas. São três modelagens do mesmo fato, e o
modelo precisa guardar o suficiente para qualquer uma delas: quem reportou, e os
contadores de cada sentido.

**Estado do fluxo** (NSG v2 posição 8 na leitura 0-based, e também no VNet): `B`
(begin), `C` (continued), `E` (end) — e o **VNet acrescenta `D`**. A spec numera
1..13, então cuidado com a contagem ao implementar.

**Criptografia**: existe, mas **não no NSG v2** — a tabela de suporte da própria
página diz "identification of virtual network encryption: Not supported" para o
NSG. É posição do **VNet** (9ª, 1-based) e coluna `FlowEncryption` no
`NTANetAnalytics`. O `encryption-status` da AWS é o mesmo fato em outra nuvem.

**Endereço traduzido** (só AWS: `pkt-srcaddr`, `pkt-dstaddr`): o endereço
pré-NAT. Sem ele, um fluxo atrás de NAT sai incompleto.

**MAC da interface** (Azure: `flows[].mac`): a Azure exige o MAC em cada grupo de
fluxo, e ele vira **partição** (`macAddress=`) no caminho do blob. É o único campo
que a Azure **obriga** e que a AWS não tem.

**Identidade de regra** (Azure: `aclID` e `rule` na VNet; `rule` no NSG):
qual regra permitiu ou negou. A AWS não carrega a regra — carrega
`reject-reason` quando nega.

**Identidade do recurso do log** — atenção à semântica, que eu havia atribuído
errado na primeira versão deste documento: o `systemId` do NSG é o **GUID do
network security group**, e o `flowLogResourceID` do VNet é o **id do recurso
FlowLog**. Nenhum dos dois é a conta/assinatura. Projetar o `scope_id` neles
colocaria um id de assinatura num campo documentado como GUID de recurso. O mesmo
vale para a região: o ARM resource id **não** carrega região; ela vem do
`location` do recurso — que o estate tem para os recursos que modela e **não tem**
para NSG e VNet, porque não os modela.

**TCP flags** (AWS `tcp-flags`), **tipo de endereço** (AWS `type`: IPv4/IPv6),
**sublinha de local** (AWS `sublocation-type`/`sublocation-id`).

## O que o modelo precisa ANTES do tipo de fluxo

Esta é a parte que a primeira versão deste documento não previu, e sem ela o
`NetworkFlow` produz dado órfão:

**Inventário de recurso de rede** — NSG, VNet, NIC e sub-rede, com ARM resource
id e resource group. Sem ele:

* o `flow_record.log_resource_id` não tem de onde sair, e o gate do projeto (P2,
  sem órfãos) recusa;
* os segmentos `RESOURCEGROUPS/{rg}` e `NETWORKSECURITYGROUPS/{nsg}` do caminho
  documentado do blob não têm valor — hoje carregam o token do próprio template;
* as chaves de junção que o ARM, o Resource Graph e o Defender usam
  (`properties.networkInterfaces[].id`, `ResourceId`, `AssessedResourceId`) saem
  vazias;
* não há MAC por interface, e sem `interface_mac` não existe a partição
  `macAddress=` que a Azure exige em cada grupo de fluxo.

Ou seja: **primeiro o inventário de rede, depois o fluxo**. O fluxo pendura no
inventário, como o finding já pendura no recurso.

## Onde está o bloqueio, por superfície

Correção importante em relação à primeira versão: o bloqueio **não é o mesmo** em
toda parte.

| Superfície | O que bloqueia |
|---|---|
| `aws/vpc-flow-logs-s3` | o modelo: sem telemetria de rede, 7 das 54 colunas têm valor |
| `azure/nsg-flow-logs-v2` | o modelo. O `record` desbloqueia com `NetworkFlow` **e** inventário de rede — inclusive o `flowTuples`, que é coluna gerável e o renderer achata na ordem documentada |
| `azure/vnet-flow-logs` | a **spec**, não o modelo. O teto são 7 colunas de data/hora; os 120 campos de blob estão classificados `example-only` e a trava recusa derivar tipo para campo não declarado. Acrescentar `NetworkFlow` **não** desbloqueia coluna nova aqui |
| `gcp/vpc-flow-logs-bigquery` | o modelo — e o destino é o Cloud Logging, não o BigQuery |

**Metadados de serviço** — o grupo mais desigual, e onde é mais fácil inventar:

| Nuvem | O que documenta |
|---|---|
| AWS | `traffic-path`, `pkt-src-aws-service`, `pkt-dst-aws-service`, `next-hop-*`, e um bloco ECS inteiro (`ecs-cluster-arn` … `ecs-task-id`) |
| GCP | `src_gke_details` (cluster, pod, workload), `src_serverless_details` (Cloud Run, App Engine), PSC, `load_balancing`, `internet_routing_details`, `src_google_service` |
| Azure | nada equivalente no registro cru |

Consequência prática: num registro gerado para a AWS, os campos de ECS ficam
vazios a menos que a carga seja um cluster ECS; num registro do GCP, os 40 campos
de PSC, GKE e serverless ficam vazios a menos que o cenário os produza. **Vazio é
a resposta correta** — o modelo não deve fabricar cluster GKE para preencher
coluna.

## Divergências entre nuvens que o renderer NÃO pode uniformizar

| Divergência | Detalhe | O que fazer |
|---|---|---|
| Protocolo | Azure NSG usa `T`/`U`; AWS, VNet e GCP usam número IANA | O modelo guarda o número; cada renderer converte para a forma da sua nuvem. Não converter seria infiel; uniformizar no artefato seria mais infiel ainda. |
| Granularidade do tempo | Azure VNet usa **milissegundos**; NSG usa **segundos**; AWS e GCP usam ISO 8601 | Preservar a unidade documentada por superfície, não normalizar |
| Sentido do fluxo | AWS `flow-direction` (ingress/egress), Azure `traffic flow` (I/O), GCP `connection_direction` | Mapear para um vocabulário canônico e converter na saída |
| Contagem dupla | GCP tem `reporter` por ponta; AWS emite uma linha por sentido | O modelo precisa saber quem reportou para não contar o mesmo fluxo duas vezes |
| Agregado vs cru | `NTANetAnalytics`/`NTAIpDetails` da Azure são agregados | Não alimentar com o mesmo objeto do fluxo cru |
| Local do log | AWS `log-status`, Azure `category`/`operationName`, GCP `reporter` | Não são o mesmo campo; cada um tem sua semântica |

## Proposta de tipo

```python
@dataclass(frozen=True, slots=True)
class NetworkFlow:
    """Um registro de fluxo, no nível de detalhe que as quatro nuvens documentam."""

    flow_id: str                  # identidade determinística (UUIDv5)
    scope_id: str                 # conta | assinatura | projeto
    region: str
    log_resource_id: str          # interface-id | resourceId | vpc/subnet
    interface_mac: str | None     # Azure exige; None onde a nuvem não pede
    reported_by: str | None       # GCP reporter (SRC/DEST); quem observou

    window_start: datetime        # UTC
    window_end: datetime          # UTC
    src_ip: str
    dst_ip: str
    src_port: int
    dst_port: int
    protocol_number: int          # IANA; o renderer converte para a forma da nuvem
    direction: str                # canônico: ingress | egress
    decision: str                 # canônico: allowed | denied
    reject_reason: str | None

    packets: int
    bytes: int
    packets_reverse: int | None
    bytes_reverse: int | None

    flow_state: str | None        # B | C | E — só NSG v2
    encryption: str | None
    tcp_flags: int | None
    address_family: str | None    # IPv4 | IPv6 (AWS `type`)
    translated_src_ip: str | None # AWS pkt-srcaddr
    translated_dst_ip: str | None
    acl_id: str | None            # Azure VNet
    rule: str | None              # Azure
    log_status: str | None        # AWS log-status
```

Regra de uso: **o renderer emite a coluna e deixa vazia quando o modelo não tem
o dado**. O que não pode acontecer é preencher com valor plausível — é exatamente
o que este projeto existe para impedir.

## O que falta decidir antes de implementar

1. **Volume.** Um registro por fluxo por janela de 5 minutos, para quantos
   recursos? A AWS publica a cada 5 minutos; a Azure agrega por hora no blob. O
   perfil `small` não pode virar milhões de linhas.
2. **Realismo dos endereços.** Os IPs precisam ser coerentes com as VPCs,
   sub-redes e interfaces do estate — um fluxo que sai de uma interface que não
   existe é dado órfão, e o gate do projeto (P2, sem órfãos) vai recusar.
3. **Relação com o gate.** `validate/gate.py` exige que findings e inventário se
   liguem a uma identidade de recurso existente. Fluxos devem seguir a mesma
   regra.
4. **Determinismo.** Os fluxos precisam de um fluxo de aleatoriedade próprio, para
   não deslocar os números já estáveis dos outros domínios (há teste de
   estabilidade byte a byte).
