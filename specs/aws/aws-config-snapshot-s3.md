# aws-config-snapshot-s3

## 1. Identificação

| Item | Valor |
|---|---|
| Nome oficial da superfície | AWS Config — entrega do **configuration history** e do **configuration snapshot** para um bucket do Amazon S3 (o provedor chama os artefatos de *configuration history file* e *configuration snapshot file*) |
| Documento oficial (entrega de snapshots) | *Delivering Configuration Snapshots to an Amazon S3 Bucket* — https://docs.aws.amazon.com/config/latest/developerguide/deliver-snapshot-cli.html |
| Documento oficial (estrutura do arquivo de snapshot) | *Example Configuration Snapshot from AWS Config* — https://docs.aws.amazon.com/config/latest/developerguide/example-s3-snapshot.html |
| Documento oficial (componentes do CI) | *Components of a Configuration Item* — https://docs.aws.amazon.com/config/latest/developerguide/config-item-table.html |
| Documento oficial (schema do ConfigItem) | *ConfigurationItem* (AWS Config API Reference) — https://docs.aws.amazon.com/config/latest/APIReference/API_ConfigurationItem.html |
| Documento oficial (layout S3 e notificação) | *Example Configuration History Delivery Notification* — https://docs.aws.amazon.com/config/latest/developerguide/example-configuration-history-notification.html |
| Documento oficial (layout S3 e notificação de snapshot) | *Example Configuration Snapshot Delivery Notification* — https://docs.aws.amazon.com/config/latest/developerguide/example-configuration-snapshot-notification.html |
| Documento oficial (conceitos) | *AWS Config terminology and concepts* — https://docs.aws.amazon.com/config/latest/developerguide/config-concepts.html |
| Data de consulta | 2026-10-14 |
| Versão/schema de referência | `fileVersion` `"1.0"` (arquivo de snapshot) e `configurationItemVersion` `"1.0"` (item). O hash MD5 e `relatedEvents` estão obsoletos desde a versão 1.3 do CI |

**O mecanismo de export existe e é oficialmente documentado.** AWS Config entrega a um bucket S3 que o cliente configura no *delivery channel*:

- *"AWS Config automatically delivers a configuration history file for each resource type that is being recorded to an Amazon S3 bucket that you specify."* — https://docs.aws.amazon.com/config/latest/developerguide/config-concepts.html
- *"You can have the configuration snapshot delivered to an Amazon Simple Storage Service (Amazon S3) bucket that you specify."* — mesma fonte
- *"AWS Config stores configuration snapshots in the Amazon S3 bucket that you specified when you enabled AWS Config."* — https://docs.aws.amazon.com/config/latest/developerguide/deliver-snapshot-cli.html

## 2. Mecanismo e entrega

### Como o dado é entregue

| Propriedade | Valor documentado | Fonte |
|---|---|---|
| Destino | Bucket Amazon S3 especificado no *delivery channel* | https://docs.aws.amazon.com/config/latest/developerguide/config-concepts.html |
| Gatilho do snapshot | Ação `DeliverConfigSnapshot` ou comando `aws configservice deliver-config-snapshot --delivery-channel-name default` | https://docs.aws.amazon.com/config/latest/developerguide/deliver-snapshot-cli.html |
| Gatilho do history | Entrega automática, por tipo de recurso gravado | https://docs.aws.amazon.com/config/latest/developerguide/config-concepts.html |
| Formato do arquivo | JSON | https://docs.aws.amazon.com/config/latest/developerguide/example-s3-snapshot.html |
| Compressão | Gzip (extensão `.json.gz` no `s3ObjectKey` publicado) | https://docs.aws.amazon.com/config/latest/developerguide/example-configuration-snapshot-notification.html |
| Encoding | Não documentado | — (ver secção 4) |
| Fuso horário | *"AWS Config uses the UTC format (Coordinated Universal Time) to record the time."* | https://docs.aws.amazon.com/config/latest/developerguide/verify-delivery-status.html |
| Notificação de entrega | SNS, com `s3Bucket` + `s3ObjectKey` | https://docs.aws.amazon.com/config/latest/developerguide/example-configuration-snapshot-notification.html |

### Particionamento S3 (account / region / date)

O `s3ObjectKey` **é publicado literalmente** nos exemplos oficiais de notificação. Os templates abaixo são **derivados dos exemplos oficiais** — a AWS não publica um template formal com placeholders.

**Configuration snapshot:**
```
AWSLogs/123456789012/Config/us-east-2/2016/9/27/ConfigSnapshot/123456789012_Config_us-east-2_ConfigSnapshot_20160927T183939Z_16da64e4-cb65-4846-b061-e6c3ba43cb96.json.gz
```
→ `AWSLogs/{accountId}/Config/{region}/{year}/{month}/{day}/ConfigSnapshot/{accountId}_Config_{region}_ConfigSnapshot_{YYYYMMDDTHHmmssZ}_{configSnapshotId}.json.gz`

**Configuration history:**
```
AWSLogs/123456789012/Config/us-east-2/2016/9/27/ConfigHistory/123456789012_Config_us-east-2_ConfigHistory_AWS::CloudTrail::Trail_20160927T195818Z_20160927T195818Z_1.json.gz
```
→ `AWSLogs/{accountId}/Config/{region}/{year}/{month}/{day}/ConfigHistory/{accountId}_Config_{region}_ConfigHistory_{resourceType}_{YYYYMMDDTHHmmssZ}_{YYYYMMDDTHHmmssZ}_{n}.json.gz`

Fontes: https://docs.aws.amazon.com/config/latest/developerguide/example-configuration-snapshot-notification.html e https://docs.aws.amazon.com/config/latest/developerguide/example-configuration-history-notification.html

**Observações de fidelidade sobre o particionamento:**
- `month` e `day` **não têm zero à esquerda** no exemplo oficial (`/2016/9/27/`), ao contrário dos flow logs. Isto está literalmente publicado.
- O `resourceType` do history contém `::` e preserva-se no nome do objeto.
- O sufixo final do history é um contador (`_1`), não um UUID; o do snapshot é o `configSnapshotId` (UUID).

### Manifesto e metadados

**AWS Config não emite um arquivo de manifesto.** O que existe é uma **notificação SNS** de entrega, cujos campos são publicados nos exemplos oficiais. O envelope da notificação (campos `Type`, `MessageId`, `TopicArn`, `Subject`, `Timestamp`, `SignatureVersion`, `Signature`, `SigningCertURL`, `UnsubscribeURL`) é o envelope padrão de notificação SNS da AWS e é idêntico em ambas as páginas oficiais.

Campos de `Message` (o payload específico do AWS Config):

| Campo | Valor no exemplo (snapshot) | Fonte |
|---|---|---|
| `configSnapshotId` | `"16da64e4-cb65-4846-b061-e6c3ba43cb96"` — presente **apenas** na notificação de snapshot | https://docs.aws.amazon.com/config/latest/developerguide/example-configuration-snapshot-notification.html |
| `s3ObjectKey` | chave completa do objeto no bucket | ambas |
| `s3Bucket` | `"config-bucket-123456789012-ohio"` | ambas |
| `notificationCreationTime` | `"2016-09-27T18:39:39.853Z"` — ISO 8601 UTC com milissegundos | ambas |
| `messageType` | `"ConfigurationSnapshotDeliveryCompleted"` (snapshot) / `"ConfigurationHistoryDeliveryCompleted"` (history) | ambas |
| `recordVersion` | `"1.1"` | ambas |

Fontes: https://docs.aws.amazon.com/config/latest/developerguide/example-configuration-snapshot-notification.html e https://docs.aws.amazon.com/config/latest/developerguide/example-configuration-history-notification.html

## 3. Campos

### 3.1 Envelope do arquivo de snapshot

O arquivo de snapshot é o objeto JSON de topo. Campos publicados no exemplo oficial de *Example Configuration Snapshot from AWS Config*.

| Campo | Tipo | Obrigatório | Unidade | Formato data/hora | Valores permitidos | Descrição | Fonte |
|---|---|---|---|---|---|---|---|
| `fileVersion` | string | sim (no exemplo) | — | — | `"1.0"` no exemplo oficial | Versão do arquivo de snapshot | https://docs.aws.amazon.com/config/latest/developerguide/example-s3-snapshot.html |
| `requestId` | string | sim (no exemplo) | — | — | — | Identificador da requisição que gerou o snapshot | https://docs.aws.amazon.com/config/latest/developerguide/example-s3-snapshot.html |
| `configurationItems` | array de objetos | sim (no exemplo) | — | — | — | Lista dos configuration items dos recursos gravados na região/conta. *"The snapshot describes the configuration for the resources that AWS Config is recording in the current region for your AWS account, and it describes the relationships between these resources."* | https://docs.aws.amazon.com/config/latest/developerguide/example-s3-snapshot.html |

### 3.2 Objeto ConfigurationItem dentro de `configurationItems`

Os nomes abaixo são **os nomes que aparecem no exemplo oficial do arquivo entregue ao S3**, e não os nomes camelCase da API `ConfigurationItem`. Onde os dois divergem, está registado na secção 5.

| Campo | Tipo | Obrigatório | Unidade | Formato data/hora | Valores permitidos | Descrição | Fonte |
|---|---|---|---|---|---|---|---|
| `configurationItemVersion` | string | sim (no exemplo) | — | — | `"1.0"` no exemplo oficial | Versão do configuration item. Corresponde a `version` na API `ConfigurationItem` | https://docs.aws.amazon.com/config/latest/developerguide/example-s3-snapshot.html |
| `resourceId` | string | sim (no exemplo) | — | — | — | O ID do recurso (ex.: `vol-ce676ccc`, `i-344c463d`) | https://docs.aws.amazon.com/config/latest/APIReference/API_ConfigurationItem.html |
| `resourceName` | string | não | — | — | — | O nome customizado do recurso, se disponível | https://docs.aws.amazon.com/config/latest/APIReference/API_ConfigurationItem.html |
| `arn` | string | não | — | — | — | Amazon Resource Name associado ao recurso. *Exemplo do arquivo:* `arn:aws:us-west-2b:123456789012:volume/vol-ce676ccc` | https://docs.aws.amazon.com/config/latest/APIReference/API_ConfigurationItem.html |
| `accountId` | string | não | — | — | 12 dígitos, pattern `\d{12}` | O ID de conta AWS de 12 dígitos associado ao recurso | https://docs.aws.amazon.com/config/latest/APIReference/API_ConfigurationItem.html |
| `awsRegion` | string | não | — | — | comprimento 1–64 | A região onde o recurso reside | https://docs.aws.amazon.com/config/latest/APIReference/API_ConfigurationItem.html |
| `availibilityZone` | string | não | — | — | — | A Availability Zone associada ao recurso. **Atenção: este é o nome exato publicado no exemplo do arquivo, com o erro de grafia `availibility`** | https://docs.aws.amazon.com/config/latest/developerguide/example-s3-snapshot.html |
| `configurationItemCaptureTime` | string (Timestamp) | não | — | ISO 8601 UTC com milissegundos, ex.: `2014-03-07T23:47:08.918Z` | — | O horário em que a gravação de mudanças de configuração foi iniciada para o recurso | https://docs.aws.amazon.com/config/latest/APIReference/API_ConfigurationItem.html |
| `configurationItemDeliveryTime` | string (Timestamp) | não | — | ISO 8601 UTC | — | O horário em que as mudanças de configuração foram entregues. **Não garantido**: presente com gravação diária, omitido com gravação contínua | https://docs.aws.amazon.com/config/latest/APIReference/API_ConfigurationItem.html |
| `configurationStateID` | string | não | — | — | — | Identificador que indica a ordenação dos configuration items de um recurso. **Grafia no arquivo: `configurationStateID`** (API: `configurationStateId`) | https://docs.aws.amazon.com/config/latest/developerguide/example-s3-snapshot.html |
| `configurationStateId` | string | não | — | — | — | Grafia da API para o mesmo campo. Use `configurationStateId` para garantir que se tem o CI mais recente, já que `configurationItemMD5Hash` está vazio desde a versão 1.3 | https://docs.aws.amazon.com/config/latest/APIReference/API_ConfigurationItem.html |
| `configurationItemStatus` | string | não | — | — | `OK` \| `ResourceDiscovered` \| `ResourceNotRecorded` \| `ResourceDeleted` \| `ResourceDeletedNotRecorded` | O status do configuration item. No arquivo aparece como `"OK"` | https://docs.aws.amazon.com/config/latest/APIReference/API_ConfigurationItem.html |
| `configurationItemMD5Hash` | string | não | — | — | — | Hash MD5 único que representa o estado do CI. **Vazio desde a versão 1.3** | https://docs.aws.amazon.com/config/latest/APIReference/API_ConfigurationItem.html |
| `relatedEvents` | array de strings | não | — | — | — | Lista de IDs de eventos CloudTrail. **Vazio desde a versão 1.3**; usar a API `LookupEvents` do CloudTrail | https://docs.aws.amazon.com/config/latest/APIReference/API_ConfigurationItem.html |
| `recordingFrequency` | string | não | — | — | `CONTINUOUS` \| `DAILY` | Frequência de gravação. **Só aparece na resposta da API quando `DAILY` está habilitado**; ausente significa `CONTINUOUS`. **Não aparece no exemplo oficial do arquivo S3** | https://docs.aws.amazon.com/config/latest/APIReference/API_ConfigurationItem.html |
| `resourceCreationTime` | string (Timestamp) | não | — | ISO 8601, ex.: `2014-02-27T21:43:53.885Z` | — | O timestamp de criação do recurso | https://docs.aws.amazon.com/config/latest/APIReference/API_ConfigurationItem.html |
| `resourceType` | string | não | — | — | Lista de tipos suportados (ex.: `AWS::EC2::Instance`, `AWS::EC2::Volume`, `AWS::EC2::SUBNET`). Alterado dinamicamente; ver *Supported Resource Types for AWS Config* | O tipo do recurso AWS | https://docs.aws.amazon.com/config/latest/APIReference/API_ConfigurationItem.html |
| `tags` | mapa string→string | não | — | — | — | Mapeamento de tags chave-valor associadas ao recurso. No arquivo aparece como objeto (`{"Name": "integ-test-1"}`) | https://docs.aws.amazon.com/config/latest/APIReference/API_ConfigurationItem.html |
| `relationships` | array de objetos `Relationship` | não | — | — | — | Lista de recursos AWS relacionados | https://docs.aws.amazon.com/config/latest/APIReference/API_ConfigurationItem.html |
| `configuration` | string JSON-encoded (API) / objeto JSON (arquivo) | não | — | — | — | O conteúdo da configuração do recurso. *"A JSON-encoded string that contains the contents for the resource configuration. This string needs to be deserialized using `json.loads()`."* **No arquivo de snapshot entregue ao S3, o mesmo campo aparece como objeto JSON já desserializado** | https://docs.aws.amazon.com/config/latest/APIReference/API_ConfigurationItem.html |
| `supplementaryConfiguration` | mapa string→string JSON-encoded | não | — | — | — | Conteúdo adicional para a configuração do recurso, devolvido para certos tipos de recurso. Requer `json.loads()` | https://docs.aws.amazon.com/config/latest/APIReference/API_ConfigurationItem.html |

### 3.3 Objeto `Relationship` dentro de `relationships`

| Campo | Tipo | Obrigatório | Unidade | Formato data/hora | Valores permitidos | Descrição | Fonte |
|---|---|---|---|---|---|---|---|
| `resourceId` | string | não | — | — | comprimento 1–768 | O ID do recurso relacionado (ex.: `sg-xxxxxx`) | https://docs.aws.amazon.com/config/latest/APIReference/API_Relationship.html |
| `resourceName` | string | não | — | — | — | O nome customizado do recurso relacionado, se disponível | https://docs.aws.amazon.com/config/latest/APIReference/API_Relationship.html |
| `resourceType` | string | não | — | — | Lista de tipos suportados | O tipo do recurso relacionado | https://docs.aws.amazon.com/config/latest/APIReference/API_Relationship.html |
| `relationshipName` | string | não | — | — | — | O tipo de relacionamento com o recurso relacionado. **Grafia da API** | https://docs.aws.amazon.com/config/latest/APIReference/API_Relationship.html |
| `name` | string | não | — | — | — | **Grafia que aparece no exemplo oficial do arquivo S3**, ex.: `"Attached to Instance"`, `"Attached Volume"`, `"Is contained in Subnet"`. Semanticamente igual a `relationshipName` | https://docs.aws.amazon.com/config/latest/developerguide/example-s3-snapshot.html |
| `direction` | string | não | — | — | `IN` \| `OUT` (no exemplo oficial) | **Presente no exemplo do arquivo S3**, ex.: `"direction": "OUT"`, `"direction": "IN"`. **Não está documentado no schema `Relationship` da API** | https://docs.aws.amazon.com/config/latest/developerguide/example-s3-snapshot.html |

### 3.4 Notificação SNS de entrega (metadados)

| Campo | Tipo | Obrigatório | Unidade | Formato data/hora | Valores permitidos | Descrição | Fonte |
|---|---|---|---|---|---|---|---|
| `s3ObjectKey` | string | sim | — | — | — | A chave completa do objeto entregue no bucket | https://docs.aws.amazon.com/config/latest/developerguide/example-configuration-history-notification.html |
| `s3Bucket` | string | sim | — | — | — | O nome do bucket de destino | https://docs.aws.amazon.com/config/latest/developerguide/example-configuration-history-notification.html |
| `notificationCreationTime` | string | sim | — | ISO 8601 UTC com milissegundos, ex.: `2016-09-27T20:37:05.217Z` | — | O horário de criação da notificação | https://docs.aws.amazon.com/config/latest/developerguide/example-configuration-history-notification.html |
| `messageType` | string | sim | — | — | `ConfigurationHistoryDeliveryCompleted` \| `ConfigurationSnapshotDeliveryCompleted` | O tipo da mensagem de entrega | https://docs.aws.amazon.com/config/latest/developerguide/example-configuration-history-notification.html |
| `recordVersion` | string | sim | — | — | `"1.1"` | A versão do registo da notificação | https://docs.aws.amazon.com/config/latest/developerguide/example-configuration-history-notification.html |
| `configSnapshotId` | string | não (só snapshot) | — | — | UUID | O ID do snapshot, presente **apenas** na notificação de snapshot | https://docs.aws.amazon.com/config/latest/developerguide/example-configuration-snapshot-notification.html |

**Total de campos documentados: 3 (envelope) + 21 (ConfigurationItem) + 6 (Relationship) + 6 (notificação) = 36.**

## 4. Campos não comprovados

| Item | Status | Motivo |
|---|---|---|
| Presença de `configurationItemDeliveryTime` no arquivo S3 | **UNVERIFIED** | O campo é documentado na API com a ressalva explícita de que é opcional e não garantido. Não aparece no exemplo oficial do arquivo de snapshot. Não afirmamos que exista nem que não exista no arquivo |
| Presença de `recordingFrequency` no arquivo S3 | **UNVERIFIED** | A doc diz que *"This field only appears in the API response when `DAILY` recording is enabled"* — ou seja, é explicitamente um campo de resposta de API. Não aparece no exemplo do arquivo |
| Presença de `supplementaryConfiguration` no arquivo S3 | **UNVERIFIED** | Documentado no schema da API; não aparece no exemplo oficial do arquivo de snapshot |
| Presença de `resourceName` no arquivo S3 | **UNVERIFIED** | Documentado no schema da API; não aparece no exemplo oficial do arquivo |
| Encoding de caracteres do arquivo `.json.gz` | **UNVERIFIED** | Não documentado |
| Template formal com placeholders para o `s3ObjectKey` | **UNVERIFIED como afirmação da AWS** | A AWS publica **apenas exemplos literais**, não um template com placeholders. Os templates nesta spec estão marcados como derivados |
| Existência de manifesto/índice de arquivos | **UNVERIFIED (evidência negativa)** | Nenhuma das páginas oficiais consultadas descreve manifesto. A ausência é reportada como achado, não como afirmação de que não existe |
| Campos do envelope SNS (`Type`, `MessageId`, `TopicArn`, `Subject`, `Timestamp`, `SignatureVersion`, `Signature`, `SigningCertURL`, `UnsubscribeURL`) | **UNVERIFIED como schema do AWS Config** | São o envelope padrão de notificação SNS; embora apareçam nos exemplos oficiais, nenhuma página do AWS Config os define como schema. Devem ser tomados da documentação do Amazon SNS |
| Notificação de "snapshot delivery started" | **UNVERIFIED (não obtida)** | A página de exemplo correspondente não pôde ser recuperada (a URL tentada devolveu o índice da documentação). Existe uma referência de navegação *"Example Configuration Snapshot Delivery Started Notification"* |

## 5. Divergências conhecidas

1. **Nomes de campo no arquivo S3 vs. no schema da API `ConfigurationItem`.** Quatro campos têm grafias diferentes:

   | Arquivo S3 (exemplo oficial) | API `ConfigurationItem` |
   |---|---|
   | `configurationItemVersion` | `version` |
   | `configurationStateID` | `configurationStateId` |
   | `availibilityZone` (grafia com erro) | `availabilityZone` |
   | `relationships[].name` | `relationships[].relationshipName` |

   Registamos ambos. O simulador deve gerar a grafia do arquivo S3, porque é ela que está publicada no artefato entregue. Fontes: https://docs.aws.amazon.com/config/latest/developerguide/example-s3-snapshot.html e https://docs.aws.amazon.com/config/latest/APIReference/API_ConfigurationItem.html

2. **`configuration` é string na API e objeto no arquivo.** O schema da API afirma explicitamente que `configuration` é *"A JSON-encoded string"*, enquanto o exemplo do arquivo de snapshot entregue ao S3 mostra `"configuration": { "volumeId": ... }` como objeto. Ambas as fontes são oficiais. Fontes: https://docs.aws.amazon.com/config/latest/APIReference/API_ConfigurationItem.html e https://docs.aws.amazon.com/config/latest/developerguide/example-s3-snapshot.html

3. **`relationships[].direction` só existe no exemplo do arquivo.** O schema `Relationship` da API não documenta `direction`, mas o exemplo do arquivo o usa com valores `IN` e `OUT`. Fonte: https://docs.aws.amazon.com/config/latest/developerguide/example-s3-snapshot.html

4. **`tags` aparece em dois formatos no exemplo oficial do arquivo.** No CI do volume, `"tags": {}` (mapa vazio). No CI da instância, `"tags": {"Name": "integ-test-1", "examplename": "examplevalue"}` (mapa). Mas dentro de `configuration`, `tags` aparece como **array de objetos** `{"key": ..., "value": ...}` (na instância) e `{"tagName": ..., "tagValue": ...}` (no volume). São dois níveis diferentes com três formatos diferentes no mesmo documento oficial. Fonte: https://docs.aws.amazon.com/config/latest/developerguide/example-s3-snapshot.html

5. **`arn` do volume no exemplo oficial não é um ARN válido.** O exemplo publica `"arn": "arn:aws:us-west-2b:123456789012:volume/vol-ce676ccc"` — com a AZ no lugar da região e sem o segmento `ec2`. O ARN da instância no mesmo exemplo é `arn:aws:ec2:us-west-2b:123456789012:instance/i-344c463d`. Registamos a inconsistência do exemplo oficial sem corrigi-la. Fonte: https://docs.aws.amazon.com/config/latest/developerguide/example-s3-snapshot.html

6. **O snapshot pode conter tipos de recurso não suportados.** Nota oficial: *"The configuration snapshot can include references to resources types and resource IDs that are not supported."* Fonte: https://docs.aws.amazon.com/config/latest/developerguide/example-s3-snapshot.html

7. **`configurationItemRelationship` e MD5/`relatedEvents` obsoletos.** *"As of Version 1.3, the relatedEvents field is empty."* e *"As of Version 1.3, the configurationItemMD5Hash field is empty."* Ambos continuam no schema e nos exemplos, mas vazios. O simulador deve emitir as chaves presentes e vazias, não omiti-las. Fonte: https://docs.aws.amazon.com/config/latest/developerguide/config-item-table.html
