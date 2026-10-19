# `compute-instances-rest` — Compute Engine `instances.get` / `instances.list`

## 1. Identificação

- **Nome oficial da superfície:** Compute Engine API — recurso `Instances`
  (métodos `instances.get` e `instances.list`).
- **Documento oficial:** "Method: instances.get" — Compute Engine REST reference.
  - URL: <https://cloud.google.com/compute/docs/reference/rest/v1/instances/get>
    (redireciona para <https://docs.cloud.google.com/compute/docs/reference/rest/v1/instances/get>)
  - Documento complementar (mesmo recurso, resposta em lista):
    <https://cloud.google.com/compute/docs/reference/rest/v1/instances/list>
- **Data de consulta:** 2026-10-14.
- **Versão/schema de referência:** Compute Engine API `v1`; o documento declara
  `"kind"` sempre `compute#instance`.

### Não é um mecanismo de export

Esta superfície **não é um export oficial**. É a representação canônica do
recurso, obtida por chamada de API (`GET`). Foi incluída no escopo como
**conjunto canônico de campos de uma instância** — a referência usada para
modelar o objeto de instância no simulador. Qualquer "export" de instância
(por exemplo Cloud Asset Inventory) carrega este conteúdo dentro de
`resource.data`, conforme documentado em
[`cloud-asset-inventory-compute-instance.md`](cloud-asset-inventory-compute-instance.md).

## 2. Mecanismo e entrega

| Item | Valor documentado | Fonte |
|---|---|---|
| Método | `GET https://compute.googleapis.com/compute/v1/projects/{project}/zones/{zone}/instances/{instance}` | <https://cloud.google.com/compute/docs/reference/rest/v1/instances/get> |
| Método alternativo (lista) | `GET .../projects/{project}/zones/{zone}/instances` → devolve `InstanceList` | <https://cloud.google.com/compute/docs/reference/rest/v1/instances/list> |
| Corpo da resposta | "If successful, the response body contains data with the following structure" — o objeto `Instances` | <https://cloud.google.com/compute/docs/reference/rest/v1/instances/get> |
| Formato | JSON (`application/json`), conforme a JSON representation da página | <https://cloud.google.com/compute/docs/reference/rest/v1/instances/get> |
| Parâmetros de caminho | `project`, `zone`, `instance` | <https://cloud.google.com/compute/docs/reference/rest/v1/instances/get> |
| Compactação / delimitador / cabeçalho | **Não documentado** para este método (a resposta é JSON de recurso, não arquivo em lote). Ver secção 4. | — |

### `instances.list` vs `instances.get`

`instances.get` devolve **um** recurso `Instances`. `instances.list` devolve um
`InstanceList`, cuja estrutura é `{"kind": string, "id": string, "items":
[ Instances ], "nextPageToken": string, "selfLink": string, "warning":
{...}}`. O elemento `items[]` é exatamente o recurso `Instances` documentado em
`instances.get`; portanto o conjunto de campos abaixo aplica-se aos dois casos.

## 3. Campos do recurso `Instances` (topo)

Convenções da tabela:

- **Tipo** reproduz o tipo como o documento o escreve. `object` = mensagem
  aninhada; `enum` = enumeração (ver secção 3.1); quando o documento não nomeia
  a mensagem aninhada, o tipo fica `object`.
- **Obrigatório** segue o documento: em REST, campos `Output only.` são
  preenchidos pelo servidor; os restantes são de entrada. A página **não** marca
  nenhum campo como `Required.`; ver secção 4.
- O **cabeçalho é o mesmo** para todas as linhas e é mostrado uma única vez
  antes da tabela para não repetir 50 URLs idênticas.

**Fonte de todas as linhas da tabela (URL base):**

```
https://cloud.google.com/compute/docs/reference/rest/v1/instances/get#<campo>
```

(ou seja, cada campo é documentado na secção de mesmo nome dessa página; o
fragmento é o nome exato do campo). Data de consulta: **2026-10-14**.

| Campo | Tipo | Obrigatório | Unidade | Formato data/hora | Valores permitidos | Descrição | Fonte |
|---|---|---|---|---|---|---|---|
| `kind` | string | não (Output only) | — | — | `compute#instance` | "Output only. Type of the resource. Always compute#instance for instances." | URL base + `#kind` |
| `id` | string (uint64 format) | não (Output only) | — | — | — | "Output only. The unique identifier for the resource. This identifier is defined by the server." | URL base + `#id` |
| `creationTimestamp` | string | não (Output only) | — | RFC3339 | — | "Output only. Creation timestamp in RFC3339 text format." | URL base + `#creationTimestamp` |
| `name` | string | não | — | — | regex `[a-z]([-a-z0-9]*[a-z0-9])?`, 1–63 chars, RFC1035 | "The name of the resource, provided by the client when initially creating the resource." | URL base + `#name` |
| `description` | string | não | — | — | — | "An optional description of this resource. Provide this property when you create the resource." | URL base + `#description` |
| `tags` | object | não | — | — | — | "Tags to apply to this instance. [...] specified by the client during instance creation." | URL base + `#tags` |
| `machineType` | string | não | — | — | — | "Full or partial URL of the machine type resource to use for this instance, in the format: zones/zone/machineTypes/machine-type." | URL base + `#machineType` |
| `status` | enum | não (Output only) | — | — | `PROVISIONING`, `STAGING`, `RUNNING`, `STOPPING`, `SUSPENDING`, `SUSPENDED`, `REPAIRING`, `TERMINATED` | "Output only. The status of the instance." | URL base + `#status` |
| `statusMessage` | string | não (Output only) | — | — | — | "Output only. An optional, human-readable explanation of the status." | URL base + `#statusMessage` |
| `zone` | string | não (Output only) | — | — | — | "Output only. URL of the zone where the instance resides." | URL base + `#zone` |
| `canIpForward` | boolean | não | — | — | — | Permite que a instância envie/receba pacotes com origem ou destino diferente do IP da interface. | URL base + `#canIpForward` |
| `networkInterfaces[]` | object | não | — | — | — | Interfaces de rede da instância (ver 3.2). | URL base + `#networkInterfaces` |
| `disks[]` | object | não | — | — | — | Discos anexados (ver 3.3). | URL base + `#disks` |
| `metadata` | object | não | — | — | — | "The metadata key/value pairs assigned to this instance." | URL base + `#metadata` |
| `serviceAccounts[]` | object | não | — | — | — | "A list of service accounts, with their specified scopes, authorized for this instance. Only one service account per VM instance is supported." | URL base + `#serviceAccounts` |
| `selfLink` | string | não (Output only) | — | — | — | "Output only. Server-defined URL for this resource." | URL base + `#selfLink` |
| `scheduling` | object | não | — | — | — | "Sets the scheduling options for this instance." | URL base + `#scheduling` |
| `cpuPlatform` | string | não (Output only) | — | — | — | "Output only. The CPU platform used by this instance." | URL base + `#cpuPlatform` |
| `labels` | map (key: string, value: string) | não | — | — | — | "Labels to apply to this instance. These can be later modified by the setLabels method." | URL base + `#labels` |
| `params` | object | não (Input only) | — | — | — | "Input only. [Input Only] Additional params passed with the request, but not persisted as part of resource payload. Available from 2026-03-01." | URL base + `#params` |
| `labelFingerprint` | string (bytes format) | não | — | — | base64 | "A fingerprint for this request [...] used for optimistic locking." | URL base + `#labelFingerprint` |
| `instanceEncryptionKey` | object | não | — | — | — | "Encrypts suspended data for an instance with a customer-managed encryption key. [...] Available from 2026-03-01." | URL base + `#instanceEncryptionKey` |
| `minCpuPlatform` | string | não | — | — | ex.: `Intel Haswell`, `Intel Sandy Bridge` | "Specifies a minimum CPU platform for the VM instance." | URL base + `#minCpuPlatform` |
| `guestAccelerators[]` | object | não | — | — | — | "A list of the type and count of accelerator cards attached to the instance." | URL base + `#guestAccelerators` |
| `startRestricted` | boolean | não (Output only) | — | — | — | "Output only. Whether a VM has been restricted for start because Compute Engine has detected suspicious activity." | URL base + `#startRestricted` |
| `deletionProtection` | boolean | não | — | — | — | "Whether the resource should be protected against deletion." | URL base + `#deletionProtection` |
| `resourcePolicies[]` | string | não | — | — | — | "Resource policies applied to this instance." | URL base + `#resourcePolicies` |
| `sourceMachineImage` | string | não | — | — | — | "Source machine image" | URL base + `#sourceMachineImage` |
| `reservationAffinity` | object | não | — | — | ver 3.4 | "Specifies the reservations that this instance can consume from." | URL base + `#reservationAffinity` |
| `hostname` | string | não | — | — | RFC1035 | "Specifies the hostname of the instance." | URL base + `#hostname` |
| `displayDevice` | object | não | — | — | ver 3.4 | "Enables display device for the instance." | URL base + `#displayDevice` |
| `shieldedInstanceConfig` | object | não | — | — | ver 3.4 | Configuração de Shielded VM da instância. | URL base + `#shieldedInstanceConfig` |
| `shieldedInstanceIntegrityPolicy` | object | não | — | — | ver 3.4 | Política de integridade do Shielded VM. | URL base + `#shieldedInstanceIntegrityPolicy` |
| `sourceMachineImageEncryptionKey` | object | não | — | — | — | "Source machine image encryption key when creating an instance from a machine image." | URL base + `#sourceMachineImageEncryptionKey` |
| `confidentialInstanceConfig` | object | não | — | — | ver 3.4 | Configuração de Confidential VM. | URL base + `#confidentialInstanceConfig` |
| `fingerprint` | string (bytes format) | não (Output only) | — | — | base64 | "Output only. Specifies a fingerprint for this request, which is essentially a hash of the instance's contents [...]" | URL base + `#fingerprint` |
| `privateIpv6GoogleAccess` | enum | não | — | — | — | Acesso do Google privado via IPv6 para a instância. | URL base + `#privateIpv6GoogleAccess` |
| `advancedMachineFeatures` | object | não | — | — | ver 3.4 | Recursos avançados de máquina (ex.: virtualização aninhada, threads por núcleo). | URL base + `#advancedMachineFeatures` |
| `lastStartTimestamp` | string | não (Output only) | — | RFC3339 | — | "Output only. Last start timestamp in RFC3339 text format." | URL base + `#lastStartTimestamp` |
| `lastStopTimestamp` | string | não (Output only) | — | RFC3339 | — | "Output only. Last stop timestamp in RFC3339 text format." | URL base + `#lastStopTimestamp` |
| `lastSuspendedTimestamp` | string | não (Output only) | — | RFC3339 | — | "Output only. Last suspended timestamp in RFC3339 text format." | URL base + `#lastSuspendedTimestamp` |
| `satisfiesPzs` | boolean | não (Output only) | — | — | — | "Output only. Reserved for future use." | URL base + `#satisfiesPzs` |
| `satisfiesPzi` | boolean | não (Output only) | — | — | — | "Output only. Reserved for future use." | URL base + `#satisfiesPzi` |
| `resourceStatus` | object | não (Output only) | — | — | ver 3.4 | "Output only. Specifies values set for instance attributes as compared to the values requested by user in the corresponding input only field. Available from 2026-03-01." | URL base + `#resourceStatus` |
| `networkPerformanceConfig` | object | não | — | — | ver 3.4 | Configuração de desempenho de rede da instância. | URL base + `#networkPerformanceConfig` |
| `keyRevocationActionType` | enum | não | — | — | `STOP`, `NONE` (padrão `NONE`) | "KeyRevocationActionType of the instance. [...] Available from 2026-03-01." | URL base + `#keyRevocationActionType` |
| `localSsdEncryptionMode` | enum | não | — | — | — | "Specifies which method should be used for encrypting the Local SSDs attached to the VM." | URL base + `#localSsdEncryptionMode` |
| `workloadIdentityConfig` | object | não | — | — | ver 3.4 | Configuração de identidade de workload da instância. | URL base + `#workloadIdentityConfig` |

**Total: 48 campos de topo.** (Contagem verificada por extração da tabela
*Fields* da página, linha a linha.)

### 3.1 Valores dos campos `enum` de topo

O documento enumera literalmente os valores apenas para `status` (ver tabela) e
`keyRevocationActionType` (`STOP`, `NONE`). Para os restantes `enum` de topo, a
página `instances.get` **não** imprime a lista de constantes na tabela de
campos; ver secção 4.

### 3.2 Campos aninhados com fonte verificada

| Campo | Tipo | Obrigatório | Unidade | Formato data/hora | Valores permitidos | Descrição | Fonte |
|---|---|---|---|---|---|---|---|
| `tags.items[]` | string | não | — | — | 1–63 chars, RFC1035 | "An array of tags. Each tag must be 1-63 characters long, and comply with RFC1035." | <https://cloud.google.com/compute/docs/reference/rest/v1/instances/get#tags.items> |
| `tags.fingerprint` | string (bytes format) | não | — | — | base64 | "Specifies a fingerprint for this request [...] A base64-encoded string." | <https://cloud.google.com/compute/docs/reference/rest/v1/instances/get#tags.fingerprint> |
| `metadata.kind` | string | não (Output only) | — | — | `compute#metadata` | "Output only. Type of the resource. Always compute#metadata for metadata." | <https://cloud.google.com/compute/docs/reference/rest/v1/instances/get#metadata.kind> |
| `metadata.fingerprint` | string (bytes format) | não | — | — | base64 | "Specifies a fingerprint for this request [...] used for optimistic locking." | <https://cloud.google.com/compute/docs/reference/rest/v1/instances/get#metadata.fingerprint> |
| `metadata.items[]` | object | não | — | — | — | Pares chave/valor de metadados da instância. | <https://cloud.google.com/compute/docs/reference/rest/v1/instances/get#metadata.items> |
| `metadata.items[].key` | string | não | — | — | regex `[a-zA-Z0-9-_]+`, < 128 bytes | "Key for the metadata entry." | <https://cloud.google.com/compute/docs/reference/rest/v1/instances/get#metadata.items.key> |
| `metadata.items[].value` | string | não | — | — | ≤ 262144 bytes (256 KiB) | "Value for the metadata entry. These are free-form strings [...]" | <https://cloud.google.com/compute/docs/reference/rest/v1/instances/get#metadata.items.value> |
| `serviceAccounts[].email` | string | não | — | — | — | "Email address of the service account." | <https://cloud.google.com/compute/docs/reference/rest/v1/instances/get#serviceAccounts.email> |
| `serviceAccounts[].scopes[]` | string | não | — | — | — | "The list of scopes to be made available for this service account." | <https://cloud.google.com/compute/docs/reference/rest/v1/instances/get#serviceAccounts.scopes> |
| `labels` (chaves) | map (key: string, value: string) | não | — | — | — | Mapa de rótulos; chave e valor são strings. | <https://cloud.google.com/compute/docs/reference/rest/v1/instances/get#labels> |
| `guestAccelerators[].acceleratorType` | string | não | — | — | — | "Full or partial URL of the accelerator type resource to attach to this instance." | <https://cloud.google.com/compute/docs/reference/rest/v1/instances/get#guestAccelerators.acceleratorType> |
| `guestAccelerators[].acceleratorCount` | integer | não | — | — | — | "The number of the guest accelerator cards exposed to this instance." | <https://cloud.google.com/compute/docs/reference/rest/v1/instances/get#guestAccelerators.acceleratorCount> |
| `reservationAffinity.consumeReservationType` | enum | não | — | — | `ANY_RESERVATION` (padrão), `SPECIFIC_RESERVATION`, `NO_RESERVATION` | "Specifies the type of reservation from which this instance can consume resources." | <https://cloud.google.com/compute/docs/reference/rest/v1/instances/get#reservationAffinity.consumeReservationType> |
| `reservationAffinity.key` | string | não | — | — | ex.: `googleapis.com/reservation-name` | "Corresponds to the label key of a reservation resource." | <https://cloud.google.com/compute/docs/reference/rest/v1/instances/get#reservationAffinity.key> |
| `reservationAffinity.values[]` | string | não | — | — | — | "Corresponds to the label values of a reservation resource." | <https://cloud.google.com/compute/docs/reference/rest/v1/instances/get#reservationAffinity.values> |
| `displayDevice.enableDisplay` | boolean | não | — | — | — | "Defines whether the instance has Display enabled." | <https://cloud.google.com/compute/docs/reference/rest/v1/instances/get#displayDevice.enableDisplay> |
| `shieldedInstanceConfig.enableSecureBoot` | boolean | não | — | — | — | "Defines whether the instance has Secure Boot enabled. Disabled by default." | <https://cloud.google.com/compute/docs/reference/rest/v1/instances/get#shieldedInstanceConfig.enableSecureBoot> |
| `shieldedInstanceConfig.enableVtpm` | boolean | não | — | — | — | "Defines whether the instance has the vTPM enabled. Enabled by default." | <https://cloud.google.com/compute/docs/reference/rest/v1/instances/get#shieldedInstanceConfig.enableVtpm> |
| `shieldedInstanceConfig.enableIntegrityMonitoring` | boolean | não | — | — | — | "Defines whether the instance has integrity monitoring enabled. Enabled by default." | <https://cloud.google.com/compute/docs/reference/rest/v1/instances/get#shieldedInstanceConfig.enableIntegrityMonitoring> |
| `shieldedInstanceIntegrityPolicy.updateAutoLearnPolicy` | boolean | não | — | — | — | "Updates the integrity policy baseline using the measurements from the VM instance's most recent boot." | <https://cloud.google.com/compute/docs/reference/rest/v1/instances/get#shieldedInstanceIntegrityPolicy.updateAutoLearnPolicy> |
| `networkPerformanceConfig.totalEgressBandwidthTier` | enum | não | — | — | — | Sem descrição na página (célula de descrição vazia). | <https://cloud.google.com/compute/docs/reference/rest/v1/instances/get#networkPerformanceConfig.totalEgressBandwidthTier> |
| `workloadIdentityConfig.identity` | string | não | — | — | — | Sem descrição na página (célula de descrição vazia). | <https://cloud.google.com/compute/docs/reference/rest/v1/instances/get#workloadIdentityConfig.identity> |
| `workloadIdentityConfig.identityCertificateEnabled` | boolean | não | — | — | — | Sem descrição na página (célula de descrição vazia). | <https://cloud.google.com/compute/docs/reference/rest/v1/instances/get#workloadIdentityConfig.identityCertificateEnabled> |
| `params.resourceManagerTags` | map (key: string, value: string) | não (Input only) | — | — | formato numérico `tagKeys/{id}`/`tagValues/{id}` ou com namespace | "Input only. Resource manager tags to be bound to the instance." | <https://cloud.google.com/compute/docs/reference/rest/v1/instances/get#params.resourceManagerTags> |
| `params.requestValidForDuration` | object | não (Input only) | — | — | — | "Relative deadline for waiting for capacity. Relevant only for Instances.Insert API." | <https://cloud.google.com/compute/docs/reference/rest/v1/instances/get#params.requestValidForDuration> |
| `params.requestValidForDuration.seconds` | string (int64 format) | não | segundos | — | 0 a 315.576.000.000 | "Span of time at a resolution of a second." | <https://cloud.google.com/compute/docs/reference/rest/v1/instances/get#params.requestValidForDuration.seconds> |
| `params.requestValidForDuration.nanos` | integer | não | nanossegundos | — | 0 a 999.999.999 | "Span of time that's a fraction of a second at nanosecond resolution." | <https://cloud.google.com/compute/docs/reference/rest/v1/instances/get#params.requestValidForDuration.nanos> |
| `resourceStatus.effectiveInstanceMetadata.vmDnsSettingMetadataValue` | string | não (Output only) | — | — | — | "Effective VM DNS setting at Instance level." | <https://cloud.google.com/compute/docs/reference/rest/v1/instances/get#resourceStatus.effectiveInstanceMetadata.vmDnsSettingMetadataValue> |
| `resourceStatus.effectiveInstanceMetadata.enableOsloginMetadataValue` | boolean | não (Output only) | — | — | — | "Effective enable-oslogin value at Instance level." | <https://cloud.google.com/compute/docs/reference/rest/v1/instances/get#resourceStatus.effectiveInstanceMetadata.enableOsloginMetadataValue> |
| `resourceStatus.effectiveInstanceMetadata.enableOsconfigMetadataValue` | boolean | não (Output only) | — | — | — | "Effective enable-osconfig value at Instance level." | <https://cloud.google.com/compute/docs/reference/rest/v1/instances/get#resourceStatus.effectiveInstanceMetadata.enableOsconfigMetadataValue> |
| `resourceStatus.effectiveInstanceMetadata.enableOsInventoryMetadataValue` | boolean | não (Output only) | — | — | — | "Effective enable-os-inventory value at Instance level." | <https://cloud.google.com/compute/docs/reference/rest/v1/instances/get#resourceStatus.effectiveInstanceMetadata.enableOsInventoryMetadataValue> |

> Nota metodológica: as sub-secções 3.2 e 3.3 não são exaustivas. O documento
> `instances.get` descreve **dezenas** de campos aninhados adicionais
> (por exemplo `disks[].initializeParams.*`,
> `networkInterfaces[].accessConfigs.*`, `scheduling.*`,
> `resourceStatus.upcomingMaintenance.*`). Foram incluídos acima apenas os
> aninhados necessários para modelar segurança, rede e identidade de uma
> instância, todos com verificação direta na página. Qualquer campo aninhado
> **não** listado aqui deve ser tratado como `UNVERIFIED` até ser lido na
> página (ver secção 4).

### 3.3 Estrutura JSON dos grupos principais

Transcrito da *JSON representation* da própria página (mesma URL,
`#SCHEMA_REPRESENTATION`):

```text
"tags": { "items": [ string ], "fingerprint": string }
"metadata": { "kind": string, "fingerprint": string,
              "items": [ { "key": string, "value": string } ] }
"serviceAccounts": [ { "email": string, "scopes": [ string ] } ]
"guestAccelerators": [ { "acceleratorType": string, "acceleratorCount": integer } ]
"reservationAffinity": { "consumeReservationType": enum, "key": string, "values": [ string ] }
"displayDevice": { "enableDisplay": boolean }
"shieldedInstanceConfig": { "enableSecureBoot": boolean, "enableVtpm": boolean,
                            "enableIntegrityMonitoring": boolean }
"shieldedInstanceIntegrityPolicy": { "updateAutoLearnPolicy": boolean }
"networkPerformanceConfig": { "totalEgressBandwidthTier": enum }
"workloadIdentityConfig": { "identity": string, "identityCertificateEnabled": boolean }
"params": { "resourceManagerTags": { string: string, ... },
            "requestValidForDuration": { "seconds": string, "nanos": integer } }
```

## 4. Campos não comprovados

| Campo / item | Estado | Motivo |
|---|---|---|
| Lista de constantes dos `enum` de topo que não `status` nem `keyRevocationActionType` (`reservationAffinity.consumeReservationType` exceto os 3 valores citados; `privateIpv6GoogleAccess`; `localSsdEncryptionMode`; `networkPerformanceConfig.totalEgressBandwidthTier`; `keyRevocationActionType` fora de `STOP`/`NONE`) | UNVERIFIED | A página `instances.get` imprime o tipo `enum` mas não enumera as constantes na tabela de campos. Sem uma secção oficial que liste os valores, eles não são gerados. |
| Marcação de obrigatoriedade (`Required.`) por campo | UNVERIFIED | A página **não** marca nenhum campo como `Required.`; apenas distingue `Output only.` / `Input only.`. A coluna "Obrigatório" desta spec reflete somente essa distinção documentada. |
| Todos os campos aninhados não listados em 3.2/3.3 (ex.: `disks[].initializeParams.*`, `networkInterfaces[].accessConfigs.*`, `scheduling.*`, `resourceStatus.upcomingMaintenance.*`, `resourceStatus.physicalHostTopology.*`) | UNVERIFIED | Existem na página, mas não foram transcritos nesta passagem. Não devem ser gerados até serem lidos e citados individualmente. |
| Compactação, delimitador e cabeçalho | UNVERIFIED | Não aplicável: a superfície é resposta JSON de API, não arquivo em lote. A documentação não descreve nenhum desses atributos para `instances.get` / `instances.list`. |

## 5. Divergências conhecidas

Nenhuma observada. A documentação de `instances.get` e `instances.list` é
consistente quanto ao fato de `items[]` conter o recurso `Instances`.
