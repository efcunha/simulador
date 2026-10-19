# vpc-flow-logs-s3

## 1. Identificação

| Item | Valor |
|---|---|
| Nome oficial da superfície | VPC Flow Logs — publicação para o Amazon S3 (Publish flow logs to Amazon S3) |
| Documento oficial (formato do registro) | *Flow log records* — https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html |
| Documento oficial (arquivos e particionamento) | *Flow log files* — https://docs.aws.amazon.com/vpc/latest/userguide/flow-logs-s3-path.html |
| Documento oficial (mecanismo de publicação) | *Publish flow logs to Amazon S3* — https://docs.aws.amazon.com/vpc/latest/userguide/flow-logs-s3.html |
| Documento oficial (exemplos de registros) | *Flow log record examples* — https://docs.aws.amazon.com/vpc/latest/userguide/flow-logs-records-examples.html |
| Data de consulta | 2026-10-14 |
| Versão/schema de referência | VPC Flow Logs **version 5** (campos de `pkt-src-aws-service`/`pkt-dst-aws-service`/`flow-direction`/`traffic-path`). A tabela abaixo documenta **todos os campos publicados**, das versões 2 a 11, exatamente como a documentação oficial os publica. |

> **Nota sobre "v5"**: a versão do registro **não é um campo do arquivo**, é o primeiro campo (`version`) e é derivada automaticamente: *"If you use the default format, the version is 2. If you use a custom format, the version is the highest version among the specified fields."* ([fonte](https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html)). Não existe um "schema v5" publicado; existe o valor `5` no campo `version` quando o formato customizado inclui campos introduzidos na versão 5.

## 2. Mecanismo e entrega

**O mecanismo de export existe e é oficialmente documentado.** VPC Flow Logs é um *vended log* que publica dados em um bucket S3 que o cliente especifica.

### Formato do arquivo

| Propriedade | Valor documentado | Fonte |
|---|---|---|
| Formatos | `Text` (texto simples, **padrão**) ou `Parquet` (colunar) | https://docs.aws.amazon.com/vpc/latest/userguide/flow-logs-s3-path.html |
| Compressão | *"Each file is compressed into a single Gzip file."* — **todo** arquivo é Gzip, em ambos os formatos | https://docs.aws.amazon.com/vpc/latest/userguide/flow-logs-s3-path.html |
| Extensão | `.log.gz` | https://docs.aws.amazon.com/vpc/latest/userguide/flow-logs-s3-path.html |
| Delimitador (texto) | Espaço. *"Each record is a string with fields separated by spaces."* | https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html |
| Cabeçalho | Não documentado. A documentação não menciona linha de cabeçalho em nenhum formato | — (ver secção 4) |
| Encoding | Não documentado explicitamente | — (ver secção 4) |
| Ordem dos campos | Definida pelo formato escolhido na criação. No formato padrão, os campos v2 **na ordem da tabela**. No formato customizado, a ordem escolhida pelo usuário | https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html |
| Tipo de dado (texto) | *"If the format is plain text, all fields are of type STRING."* | https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html |
| Tipo de dado (Parquet) | Por campo, na coluna `Parquet data type:` de cada linha da tabela | https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html |
| Ausência de valor | *"If a field is not applicable or could not be computed for a specific record, the record displays a `-` symbol for that entry."* | https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html |

### Intervalo de agregação e latência

- Intervalo máximo de agregação: **10 minutos** por padrão, ou **1 minuto** se especificado. Em interfaces de instâncias Nitro, *"the aggregation interval is always 1 minute or less"*.
- *"The flow log service typically delivers logs to CloudWatch Logs in about 5 minutes and to Amazon S3 in about 10 minutes. However, log delivery is on a best effort basis."*
- Os arquivos são publicados *"at 5-minute intervals"*, e *"Multiple files may be published and each log file may contain some or all of the flow log records for the IP traffic recorded in the previous 5 minutes."*
- Fonte: https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html e https://docs.aws.amazon.com/vpc/latest/userguide/flow-logs-s3-path.html

### Layout de objetos no S3

Estrutura *"based on the flow log's ID, Region, creation date, and destination options"*.

| Opção | Template de caminho |
|---|---|
| Padrão | `bucket-and-optional-prefix/AWSLogs/account_id/vpcflowlogs/region/year/month/day/` |
| Hive-compatible S3 prefixes | `bucket-and-optional-prefix/AWSLogs/aws-account-id=account_id/aws-service=vpcflowlogs/aws-region=region/year=year/month=month/day=day/` |
| Hourly partitions | `bucket-and-optional-prefix/AWSLogs/account_id/vpcflowlogs/region/year/month/day/hour/` |
| Hive + hourly | `bucket-and-optional-prefix/AWSLogs/aws-account-id=account_id/aws-service=vpcflowlogs/aws-region=region/year=year/month=month/day=day/hour=hour/` |

Fonte: https://docs.aws.amazon.com/vpc/latest/userguide/flow-logs-s3-path.html

### Nome do arquivo

```
aws_account_id_vpcflowlogs_region_flow_log_id_YYYYMMDDTHHmmZ_hash.log.gz
```

Exemplo oficial: `123456789012_vpcflowlogs_us-east-1_fl-1234abcd_20180620T1620Z_fe123456.log.gz`

Fonte: https://docs.aws.amazon.com/vpc/latest/userguide/flow-logs-s3-path.html

Notas de fidelidade sobre o nome:
- O timestamp do nome é a janela de agregação. No exemplo oficial: *"The file contains the flow log records with an end time between 16:20:00 and 16:24:59."*
- O campo `Last modified` do objeto no S3 é **posterior** ao timestamp do nome: *"This is later than the timestamp in the file name, and differs by the amount of time taken to upload the file."*
- O sufixo `hash` e sua função **não são documentados** (ver secção 4).

### Manifesto e metadados

A documentação oficial de VPC Flow Logs para S3 **não descreve nenhum manifesto, arquivo de índice ou metadados laterais**. Nenhum manifesto deve ser gerado.
Fonte: https://docs.aws.amazon.com/vpc/latest/userguide/flow-logs-s3.html (índice completo de tópicos: Flow log files, S3 bucket permissions, key policy SSE-KMS, log file permissions, create, view — nenhum descreve manifesto).

## 3. Campos

Coluna **Campo** = nome exato como aparece no registro (minúsculas, hífen). A URL em **Fonte** é a secção *Available fields* que documenta aquele campo. Data de consulta de todas as linhas: **2026-10-14**.

A coluna **Obrigatório** refere-se à presença no **formato**, não ao valor: `default (v2)` = presente no formato padrão; `opt-in` = só aparece se incluído no formato customizado.

| Campo | Tipo (Parquet) | Obrigatório | Unidade | Formato data/hora | Valores permitidos | Descrição | Fonte |
|---|---|---|---|---|---|---|---|
| `version` | INT_32 | default (v2) | — | — | — | A versão do VPC Flow Logs. No formato padrão é `2`; no formato customizado é a **maior** versão entre os campos especificados | https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html |
| `account-id` | STRING | default (v2) | — | — | — | O ID da conta AWS dona da interface de rede de origem cujo tráfego é registrado. Se a interface foi criada por um serviço AWS, pode exibir `unknown` | https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html |
| `interface-id` | STRING | default (v2) | — | — | — | O ID da interface de rede cujo tráfego é registrado. Retorna `-` para fluxos associados a um NAT gateway regional | https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html |
| `srcaddr` | STRING | default (v2) | — | — | — | Para tráfego de entrada, o IP de origem. Para tráfego de saída, o IPv4 privado ou IPv6 da interface que envia | https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html |
| `dstaddr` | STRING | default (v2) | — | — | — | O endereço de destino para tráfego de saída, ou o IPv4/IPv6 da interface para tráfego de entrada. O IPv4 é sempre o privado | https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html |
| `srcport` | INT_32 | default (v2) | porta | — | — | A porta de origem do tráfego | https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html |
| `dstport` | INT_32 | default (v2) | porta | — | — | A porta de destino do tráfego | https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html |
| `protocol` | INT_32 | default (v2) | número IANA | — | — | O número de protocolo IANA do tráfego | https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html |
| `packets` | INT_64 | default (v2) | pacotes | — | — | O número de pacotes transferidos durante o fluxo | https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html |
| `bytes` | INT_64 | default (v2) | bytes | — | — | O número de bytes transferidos durante o fluxo | https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html |
| `start` | INT_64 | default (v2) | segundos Unix | Unix seconds (inteiro). Formato texto: epoch em segundos, sem fuso textual | — | O horário, em segundos Unix, do primeiro pacote do fluxo recebido dentro do intervalo de agregação. Pode ser até 60 s antes do recebimento ou até 60 s depois da transmissão | https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html |
| `end` | INT_64 | default (v2) | segundos Unix | Unix seconds (inteiro) | — | O horário, em segundos Unix, do último pacote do fluxo dentro do intervalo de agregação | https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html |
| `action` | STRING | default (v2) | — | — | `ACCEPT` \| `REJECT` | A ação associada ao tráfego | https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html |
| `log-status` | STRING | default (v2) | — | — | `OK` \| `NODATA` \| `SKIPDATA` | O status de log do flow log | https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html |
| `vpc-id` | STRING | opt-in (v3) | — | — | — | O ID da VPC que contém a interface de rede | https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html |
| `subnet-id` | STRING | opt-in (v3) | — | — | — | O ID da subnet que contém a interface. Retorna `-` para NAT gateway regional | https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html |
| `instance-id` | STRING | opt-in (v3) | — | — | — | O ID da instância associada à interface, se a instância for sua. Retorna `-` para interface gerenciada pelo requester (ex.: NAT gateway) | https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html |
| `tcp-flags` | INT_32 | opt-in (v3) | bitmask | — | `0`,`1`,`2`,`3`,`4`,`18`,`19` (combinações OR); `-` se inválido | O valor de bitmask das flags TCP: FIN=1, SYN=2, RST=4, SYN-ACK=18. Se nenhuma flag suportada for registrada, o valor é `0`. Flags não suportadas (ACK, PSH) resultam em `0` se sozinhas | https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html |
| `type` | STRING | opt-in (v3) | — | — | `IPv4` \| `IPv6` \| `EFA` | O tipo de tráfego | https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html |
| `pkt-srcaddr` | STRING | opt-in (v3) | — | — | — | O endereço IP de origem *a nível de pacote* (original). Use com `srcaddr` para distinguir IP de camada intermediária do IP original | https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html |
| `pkt-dstaddr` | STRING | opt-in (v3) | — | — | — | O endereço IP de destino *a nível de pacote* (original) | https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html |
| `region` | STRING | opt-in (v4) | — | — | — | A Region que contém a interface de rede cujo tráfego é registrado | https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html |
| `az-id` | STRING | opt-in (v4) | — | — | — | O ID da Availability Zone que contém a interface. `-` se o tráfego for de um sublocation | https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html |
| `sublocation-type` | STRING | opt-in (v4) | — | — | `wavelength` \| `outpost` \| `localzone`; `-` se não aplicável | O tipo do sublocation retornado em `sublocation-id` | https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html |
| `sublocation-id` | STRING | opt-in (v4) | — | — | `-` se não aplicável | O ID do sublocation que contém a interface | https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html |
| `pkt-src-aws-service` | STRING | opt-in (v5) | — | — | `AMAZON`, `AMAZON_APPFLOW`, `AMAZON_CONNECT`, `API_GATEWAY`, `AURORA_DSQL`, `CHIME_MEETINGS`, `CHIME_VOICECONNECTOR`, `CLOUD9`, `CLOUDFRONT`, `CLOUDFRONT_ORIGIN_FACING`, `CODEBUILD`, `DYNAMODB`, `EBS`, `EC2`, `EC2_INSTANCE_CONNECT`, `GLOBALACCELERATOR`, `IVS_LOW_LATENCY`, `IVS_REALTIME`, `KINESIS_VIDEO_STREAMS`, `MEDIA_PACKAGE_V2`, `ROUTE53`, `ROUTE53_HEALTHCHECKS`, `ROUTE53_HEALTHCHECKS_PUBLISHING`, `ROUTE53_RESOLVER`, `S3`, `WORKSPACES_GATEWAYS` | O nome do subconjunto de faixas de IP para o campo `pkt-srcaddr`, se o IP de origem for de um serviço AWS | https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html |
| `pkt-dst-aws-service` | STRING | opt-in (v5) | — | — | Mesma lista de `pkt-src-aws-service` | O nome do subconjunto de faixas de IP para `pkt-dstaddr`, se o IP de destino for de um serviço AWS | https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html |
| `flow-direction` | STRING | opt-in (v5) | — | — | `ingress` \| `egress` | A direção do fluxo em relação à interface onde o tráfego é capturado | https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html |
| `traffic-path` | INT_32 | opt-in (v5) | — | — | `1`,`2`,`3`,`4`,`5`,`6`,`7`,`8`; `-` se nenhum se aplicar | O caminho que o tráfego **de saída** toma até o destino. 1=outro recurso na mesma VPC; 2=internet gateway ou gateway VPC endpoint; 3=virtual private gateway; 4=peering intra-region; 5=peering inter-region; 6=Local Zone ou Wavelength Zone; 7=gateway VPC endpoint; 8=internet gateway | https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html |
| `ecs-cluster-arn` | STRING | opt-in (v7) | — | — | — | ARN do cluster ECS se o tráfego vier de uma task ECS em execução. Requer permissão `ecs:ListClusters` | https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html |
| `ecs-cluster-name` | STRING | opt-in (v7) | — | — | — | Nome do cluster ECS se o tráfego vier de uma task ECS em execução. Requer `ecs:ListClusters` | https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html |
| `ecs-container-instance-arn` | STRING | opt-in (v7) | — | — | `-` se o capacity provider for AWS Fargate | ARN da instância de container ECS se o tráfego vier de uma task ECS em instância EC2. Requer `ecs:ListClusters` e `ecs:ListContainerInstances` | https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html |
| `ecs-container-instance-id` | STRING | opt-in (v7) | — | — | `-` se o capacity provider for AWS Fargate | ID da instância de container ECS se o tráfego vier de uma task ECS em instância EC2. Requer `ecs:ListClusters` e `ecs:ListContainerInstances` | https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html |
| `ecs-container-id` | STRING | opt-in (v7) | — | — | — | Docker runtime ID do container se o tráfego vier de uma task ECS. Se houver mais de um container, é o ID do primeiro. Requer `ecs:ListClusters` | https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html |
| `ecs-second-container-id` | STRING | opt-in (v7) | — | — | — | Docker runtime ID do **segundo** container da task ECS. Requer `ecs:ListClusters` | https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html |
| `ecs-service-name` | STRING | opt-in (v7) | — | — | `-` se a task não foi iniciada por um serviço ECS | Nome do serviço ECS se o tráfego vier de uma task ECS iniciada por um serviço. Requer `ecs:ListClusters` e `ecs:ListServices` | https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html |
| `ecs-task-definition-arn` | STRING | opt-in (v7) | — | — | — | ARN da task definition ECS se o tráfego vier de uma task ECS em execução. Requer `ecs:ListClusters` e `ecs:ListTaskDefinitions` | https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html |
| `ecs-task-arn` | STRING | opt-in (v7) | — | — | — | ARN da task ECS se o tráfego vier de uma task ECS em execução. Requer `ecs:ListClusters` e `ecs:ListTasks` | https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html |
| `ecs-task-id` | STRING | opt-in (v7) | — | — | — | ID da task ECS se o tráfego vier de uma task ECS em execução. Requer `ecs:ListClusters` e `ecs:ListTasks` | https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html |
| `reject-reason` | STRING | opt-in (v8) | — | — | `BPA` \| `EC`; `-` para qualquer outro motivo | Motivo pelo qual o tráfego foi rejeitado. BPA = VPC Block Public Access; EC = rejeitado por VPC Endpoint devido a controles de criptografia | https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html |
| `resource-id` | STRING | opt-in (v9) | — | — | `-` para fluxos não associados a NAT gateway regional | O ID do NAT gateway regional que contém a interface de rede | https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html |
| `encryption-status` | INT_32 | opt-in (v10) | — | — | `0` \| `1` \| `2` \| `3`; `-` se VPC Encryption Controls não estiver habilitado | Status de criptografia do fluxo. 0=não criptografado; 1=nitro-encrypted; 2=application-encrypted; 3=nitro e application | https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html |
| `instance-tag` | STRING | opt-in (v11) | — | — | — | Valor da tag da **primeira** tag de instância incluída em `TagFieldSpecifications`. Valores têm caracteres especiais traduzidos com percent-encoding UTF-8. Requer `ec2:DescribeTags` e `iam:CreateServiceLinkedRole` | https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html |
| `instance-tag-2` | STRING | opt-in (v11) | — | — | — | Valor da tag da **segunda** tag de instância em `TagFieldSpecifications`. Percent-encoding UTF-8. Requer `ec2:DescribeTags` e `iam:CreateServiceLinkedRole` | https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html |
| `interface-tag` | STRING | opt-in (v11) | — | — | — | Valor da tag da **primeira** tag de interface de rede em `TagFieldSpecifications`. Percent-encoding UTF-8. Requer `ec2:DescribeTags` e `iam:CreateServiceLinkedRole` | https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html |
| `interface-tag-2` | STRING | opt-in (v11) | — | — | — | Valor da tag da **segunda** tag de interface de rede. Percent-encoding UTF-8. Requer `ec2:DescribeTags` e `iam:CreateServiceLinkedRole` | https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html |
| `asg-tag` | STRING | opt-in (v11) | — | — | — | Valor da tag do **primeiro** auto scaling group em `TagFieldSpecifications`. Percent-encoding UTF-8. Requer `autoscaling:DescribeTags` e `iam:CreateServiceLinkedRole`, **e** pelo menos um CloudTrail trail habilitado na conta | https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html |
| `asg-tag-2` | STRING | opt-in (v11) | — | — | — | Valor da tag do **segundo** auto scaling group. Percent-encoding UTF-8. Requer `autoscaling:DescribeTags` e `iam:CreateServiceLinkedRole`, **e** pelo menos um CloudTrail trail habilitado | https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html |
| `interface-type` | STRING | opt-in (v11) | — | — | `nat_gateway` \| `network_load_balancer` \| `regional_nat_gateway` \| `transit_gateway` \| `vpc_endpoint`; `-` se sem serviço associado ou não suportado | O tipo da interface de rede local que captura o fluxo | https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html |
| `next-hop-interface-id` | STRING | opt-in (v11) | — | — | — | O ID da interface de rede do próximo hop. Para tráfego de saída, é a interface que recebe o tráfego; para entrada, a que envia | https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html |
| `next-hop-subnet-id` | STRING | opt-in (v11) | — | — | — | O ID da subnet que contém a interface do próximo hop | https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html |
| `next-hop-az-id` | STRING | opt-in (v11) | — | — | — | O ID da Availability Zone que contém a interface do próximo hop | https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html |
| `next-hop-vpc-id` | STRING | opt-in (v11) | — | — | — | O ID da VPC que contém a interface do próximo hop | https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html |
| `next-hop-interface-type` | STRING | opt-in (v11) | — | — | Mesma lista de `interface-type` | O tipo da interface de rede do próximo hop | https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html |

**Total de campos documentados: 54.**

Todos os 54 vêm da tabela *Available fields* da mesma página. Nenhum campo desta tabela foi inferido, deduzido ou completado por analogia.

### Ordem exata do formato padrão

O formato padrão inclui **todos os campos v2, na ordem da tabela**:
`version account-id interface-id srcaddr dstaddr srcport dstport protocol packets bytes start end action log-status`

Fonte: https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html

## 4. Campos não comprovados

| Item | Status | Motivo |
|---|---|---|
| Linha de cabeçalho em arquivos texto | **UNVERIFIED** | A documentação de *Flow log records* e *Flow log files* não menciona cabeçalho. Não afirmamos presença nem ausência |
| Encoding de caracteres do arquivo (UTF-8, ASCII) | **UNVERIFIED** | Não documentado nas páginas consultadas |
| Separador exato em arquivos Parquet / schema Arrow | **UNVERIFIED** | A documentação dá *Parquet data type* por campo (`INT_32`, `INT_64`, `STRING`) mas não publica schema Arrow nem nomes de colunas Parquet |
| Algoritmo/comprimento do sufixo `hash` do nome do arquivo | **UNVERIFIED** | O nome do arquivo é documentado, a origem do `hash` não |
| Nomes dos campos de tag (`TagFieldSpecifications`) | **UNVERIFIED** | A doc diz "first instance tag included in your TagFieldSpecifications" mas não publica o schema desse objeto nas páginas consultadas |
| Fuso horário do campo `start`/`end` no arquivo texto | **UNVERIFIED como representação textual** | A doc afirma "in Unix seconds" (portanto UTC por definição), mas não publica se há sufixo ou formatação adicional no arquivo texto. O valor é epoch inteiro |
| Formato do `az-id` (ex.: `use1-az1`) | **UNVERIFIED** | A doc descreve o significado mas não publica o padrão do identificador |
| Presença de novos campos v6 | **UNVERIFIED** | A tabela oficial salta de `traffic-path` (v5) para `ecs-*` (v7) e depois v8, v9, v10, v11. **Não existe versão 6 na tabela oficial** — o número 6 não aparece. Isto é uma lacuna da documentação, registrada aqui, não preenchida |

## 5. Divergências conhecidas

1. **Intervalo de publicação: 5 minutos vs. entrega em ~10 minutos.** *Flow log files* afirma que os arquivos são publicados *"at 5-minute intervals"*, enquanto *Flow log records* afirma que a entrega ao S3 leva *"about 10 minutes"* e que *"log delivery is on a best effort basis"*. Ambos são oficiais; não escolhemos. Um simulador deve modelar janela de agregação de 5 min **e** latência de entrega não garantida.
   Fontes: https://docs.aws.amazon.com/vpc/latest/userguide/flow-logs-s3-path.html e https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html

2. **`traffic-path` valor 2 vs. valor 7 e 8.** A lista oficial atribui `2 — Through an internet gateway or a gateway VPC endpoint` **e também** `7 — Through a gateway VPC endpoint` e `8 — Through an internet gateway`. As descrições de 2, 7 e 8 sobrepõem-se. O exemplo oficial de *Service name, traffic path, and flow direction* usa `traffic-path` = `8` para internet gateway. Registramos a sobreposição tal como publicada.
   Fonte: https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html

3. **`tcp-flags` na linha de exemplo de saída IPv6 do exemplo de TCP flags.** No exemplo de *TCP flag sequence*, uma das linhas de resposta tem dois espaços antes de `10.0.0.62` (`5001 43638  10.0.0.62`), indicando um campo vazio na amostra oficial. Trata-se de um defeito de formatação na própria página oficial, não de um campo vazio documentado.
   Fonte: https://docs.aws.amazon.com/vpc/latest/userguide/flow-logs-records-examples.html

4. **`type` = `EFA` está documentado nos valores permitidos, mas a versão associada na tabela é 3**, e o exemplo de EFA não é publicado na página consultada. Aceitamos `EFA` como valor documentado, sem exemplo.
   Fonte: https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html
