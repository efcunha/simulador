# `cloud-asset-inventory-compute-instance` — Cloud Asset Inventory `ExportAssets`

## 1. Identificação

- **Nome oficial da superfície:** Cloud Asset Inventory — `ExportAssets`
  (método `cloudasset.googleapis.com/v1/{parent=*/*}:exportAssets`); tabelas
  BigQuery de export; destinos alternativos Cloud Storage e BigQuery.
- **Documentos oficiais e datas de consulta (2026-10-14):**

| Documento | URL | Consultado em |
|---|---|---|
| "Method: exportAssets" (API, `OutputConfig`, `GcsDestination`, `BigQueryDestination`, `PartitionSpec`, `PartitionKey`) | <https://cloud.google.com/asset-inventory/docs/reference/rest/v1/TopLevel/exportAssets> | 2026-10-14 |
| "Export asset metadata to BigQuery" (**schemas BigQuery oficiais**) | <https://cloud.google.com/asset-inventory/docs/exporting-to-bigquery> | 2026-10-14 |
| "Export asset metadata to Cloud Storage" | <https://cloud.google.com/asset-inventory/docs/exporting-to-cloud-storage> | 2026-10-14 |
| "Asset" (mensagem `Asset`, `Resource` e `Policy`) | <https://cloud.google.com/asset-inventory/docs/reference/rest/v1/Asset> | 2026-10-14 |
| "Supported asset types" (confirmação de `compute.googleapis.com/Instance`) | <https://cloud.google.com/asset-inventory/docs/supported-asset-types> | 2026-10-14 |

- **Versão/schema de referência:** Cloud Asset Inventory API **v1**.
  `compute.googleapis.com/Instance` consta na lista oficial de asset types
  suportados (<https://cloud.google.com/asset-inventory/docs/supported-asset-types>).

### 1.1 O mecanismo de export existe — e é oficial

| Afirmação | Fonte |
|---|---|
| "Exports assets with time and resource types to a given Cloud Storage location/BigQuery table." | <https://cloud.google.com/asset-inventory/docs/reference/rest/v1/TopLevel/exportAssets> |
| "For Cloud Storage location destinations, the output format is **newline-delimited JSON**. Each line represents a `google.cloud.asset.v1.Asset` in the JSON format" | <https://cloud.google.com/asset-inventory/docs/reference/rest/v1/TopLevel/exportAssets> |
| "for BigQuery table destinations, the output table stores the fields in asset Protobuf as columns" | <https://cloud.google.com/asset-inventory/docs/reference/rest/v1/TopLevel/exportAssets> |
| "This API implements the `google.longrunning.Operation` API [...] We recommend intervals of at least 2 seconds with exponential retry to poll the export operation result." | <https://cloud.google.com/asset-inventory/docs/reference/rest/v1/TopLevel/exportAssets> |
| "The `resource.data` column is the resource metadata represented as a **JSON string**." | <https://cloud.google.com/asset-inventory/docs/exporting-to-bigquery> |

## 2. Mecanismo e entrega

### 2.1 Pedido

| Campo do pedido | Tipo | Obrigatório | Descrição | Fonte |
|---|---|---|---|---|
| `parent` | string | sim | "The relative name of the root asset. This can only be an organization number (such as "organizations/123"), a project ID [...] or a folder number". Permissões: `cloudasset.assets.exportResource`, `cloudasset.assets.exportIamPolicy` | <https://cloud.google.com/asset-inventory/docs/reference/rest/v1/TopLevel/exportAssets#body.PATH_PARAMETERS.parent> |
| `readTime` | string (Timestamp format) | não | "Timestamp to take an asset snapshot. This can only be set to a timestamp between the current time and the current time minus 35 days (inclusive)." RFC 3339, Z-normalized | <https://cloud.google.com/asset-inventory/docs/reference/rest/v1/TopLevel/exportAssets#body.request_body.FIELDS.read_time> |
| `assetTypes[]` | string | não | "A list of asset types to take a snapshot for. For example: "compute.googleapis.com/Disk". Regular expressions are also supported." | <https://cloud.google.com/asset-inventory/docs/reference/rest/v1/TopLevel/exportAssets#body.request_body.FIELDS.asset_types> |
| `contentType` | enum (ContentType) | não | "Asset content type. If not specified, no content but the asset name will be returned." | <https://cloud.google.com/asset-inventory/docs/reference/rest/v1/TopLevel/exportAssets#body.request_body.FIELDS.content_type> |
| `outputConfig` | object (OutputConfig) | sim | "Required. Output configuration indicating where the results will be output to." | <https://cloud.google.com/asset-inventory/docs/reference/rest/v1/TopLevel/exportAssets#body.request_body.FIELDS.output_config> |
| `relationshipTypes[]` | string | não | "A list of relationship types to export, for example: INSTANCE_TO_INSTANCEGROUP. This field should only be specified if `contentType=RELATIONSHIP`." | <https://cloud.google.com/asset-inventory/docs/reference/rest/v1/TopLevel/exportAssets#body.request_body.FIELDS.relationship_types> |

### 2.2 Destino Cloud Storage (`GcsDestination`)

| Campo | Tipo | Obrigatório | Descrição | Fonte |
|---|---|---|---|---|
| `uri` | string | um de `object_uri` | "The URI of the Cloud Storage object. [...] Example: "gs://bucket_name/object_name". If the specified Cloud Storage object already exists and there is no hold, it will be overwritten with the exported result." | <https://cloud.google.com/asset-inventory/docs/reference/rest/v1/TopLevel/exportAssets#GcsDestination> |
| `uriPrefix` | string | um de `object_uri` | "The URI prefix of all generated Cloud Storage objects. Example: "gs://bucket_name/object_name_prefix". Each object URI is in format: "gs://bucket_name/object_name_prefix/<asset type>/<shard number>" and only contains assets for that type." Exemplo oficial: `gs://bucket_name/object_name_prefix/compute.googleapis.com/Disk/0` é o primeiro shard. | <https://cloud.google.com/asset-inventory/docs/reference/rest/v1/TopLevel/exportAssets#GcsDestination> |

- **Formato do arquivo (Cloud Storage):** "the output format is
  **newline-delimited JSON**. Each line represents a `google.cloud.asset.v1.Asset`
  in the JSON format" —
  <https://cloud.google.com/asset-inventory/docs/reference/rest/v1/TopLevel/exportAssets>
- **Compressão / encoding / delimitador / cabeçalho:** não documentados. O
  formato é NDJSON, portanto não há delimitador nem cabeçalho; a compressão não
  é declarada. Ver secção 5.
- **Sharding:** `<prefix>/<asset type>/<shard number>` começando em 0
  (exemplo oficial acima). É o único particionamento documentado para GCS.

### 2.3 Destino BigQuery (`BigQueryDestination`)

| Campo | Tipo | Obrigatório | Descrição | Fonte |
|---|---|---|---|---|
| `dataset` | string | sim | "Required. The BigQuery dataset in format "projects/projectId/datasets/datasetId" [...] Setting the `contentType` for `exportAssets` determines the schema of the BigQuery table. Setting `separateTablesPerAssetType` to TRUE also influences the schema." | <https://cloud.google.com/asset-inventory/docs/reference/rest/v1/TopLevel/exportAssets#BigQueryDestination> |
| `table` | string | sim | "Required. The BigQuery table to which the snapshot result should be written. If this table does not exist, a new table with the given name will be created." | <https://cloud.google.com/asset-inventory/docs/reference/rest/v1/TopLevel/exportAssets#BigQueryDestination> |
| `force` | boolean | não | "If the destination table already exists and this flag is TRUE, the table will be overwritten [...] If the flag is FALSE or unset and the destination table already exists, the export call returns an INVALID_ARGUMENT error." | <https://cloud.google.com/asset-inventory/docs/reference/rest/v1/TopLevel/exportAssets#BigQueryDestination> |
| `partitionSpec` | object (PartitionSpec) | não | "determines whether to export to partitioned table(s) and how to partition the data. [...] the snapshot results will be written to partitioned table(s) with two additional timestamp columns, `readTime` and `requestTime`, one of which will be the partition key." | <https://cloud.google.com/asset-inventory/docs/reference/rest/v1/TopLevel/exportAssets#BigQueryDestination> |
| `separateTablesPerAssetType` | boolean | não | "If this flag is TRUE, the snapshot results will be written to one or multiple tables, each of which contains results of one asset type." | <https://cloud.google.com/asset-inventory/docs/reference/rest/v1/TopLevel/exportAssets#BigQueryDestination> |
| `partitionSpec.partitionKey` | enum (PartitionKey) | não | "The partition key for BigQuery partitioned table." Valores: `PARTITION_KEY_UNSPECIFIED`, `READ_TIME`, `REQUEST_TIME` | <https://cloud.google.com/asset-inventory/docs/reference/rest/v1/TopLevel/exportAssets#PartitionSpec> |

- **Nome da tabela por asset type:** "Field [`table`] will be concatenated with
  "_" and the asset type names [...] in which all non-alphanumeric characters
  like "." and "/" will be substituted by "_". Example: if field [`table`] is
  "mytable" and snapshot results contain "storage.googleapis.com/Bucket" assets,
  the corresponding table name will be "mytable_storage_googleapis_com_Bucket"."
  — <https://cloud.google.com/asset-inventory/docs/reference/rest/v1/TopLevel/exportAssets#BigQueryDestination>
- **Clustering:** "Exporting to BigQuery **clustered tables isn't supported**."
  — <https://cloud.google.com/asset-inventory/docs/exporting-to-bigquery#limitations>
- **Append:** "Appending the export output to an existing table isn't supported
  unless you export to a partitioned table. The destination table must be empty
  or you must overwrite it."
  — <https://cloud.google.com/asset-inventory/docs/exporting-to-bigquery#limitations>
- **Campos com valor possivelmente nulo:** "Frequently changing asset fields
  such as `numBytes`, `numLongTermBytes`, `numPhysicalBytes`, and `numRows` might
  be exported with a null value."
  — <https://cloud.google.com/asset-inventory/docs/exporting-to-bigquery#limitations>
- **Limite de aninhamento:** até **15 níveis** (limite do BigQuery); acima disso
  os campos são guardados como string JSON no RECORD pai
  — <https://cloud.google.com/asset-inventory/docs/reference/rest/v1/TopLevel/exportAssets#BigQueryDestination>
- **Convenção de nomes (casing):** "For the RESOURCE content type when you export
  assets to tables per asset type, there are no spaces between words, and the
  first letter of each new word after the first is capitalized. For example,
  `assetType`. For all other content types, the field name is lowercase, with
  spaces replaced by underscores. For example, `asset_type`."
  — <https://cloud.google.com/asset-inventory/docs/exporting-to-bigquery#casing>
- **Manifesto:** o documento não descreve nenhum manifesto. O que existe é o
  objeto `Operation` (`google.longrunning.Operation`) devolvido pelo pedido, e o
  caminho de operação
  `projects/PROJECT_NUMBER/operations/ExportAssets/CONTENT_TYPE/OPERATION_ID`
  — <https://cloud.google.com/asset-inventory/docs/exporting-to-cloud-storage#view_the_status_of_an_export>

## 3. Schemas BigQuery publicados pela Google

### 3.1 Resource schema (content type `RESOURCE` ou não especificado, `separateTablesPerAssetType=false`)

Transcrito literalmente de
<https://cloud.google.com/asset-inventory/docs/exporting-to-bigquery#resource_schema>
(consulta 2026-10-14).

| Campo (coluna BigQuery) | Tipo BigQuery | Mode | Obrigatório | Unidade | Formato data/hora | Descrição | Fonte |
|---|---|---|---|---|---|---|---|
| `name` | STRING | NULLABLE | não | — | — | Nome do asset (corresponde a `Asset.name`) | #resource_schema |
| `asset_type` | STRING | NULLABLE | não | — | — | Tipo do asset (corresponde a `Asset.assetType`) | #resource_schema |
| `resource` | RECORD | NULLABLE | não | — | — | Representação do recurso | #resource_schema |
| `resource.version` | STRING | NULLABLE | não | — | — | Versão da API | #resource_schema |
| `resource.discovery_document_uri` | STRING | NULLABLE | não | — | — | URL do discovery document | #resource_schema |
| `resource.discovery_name` | STRING | NULLABLE | não | — | — | Nome do schema no discovery document | #resource_schema |
| `resource.resource_url` | STRING | NULLABLE | não | — | — | URL REST do recurso | #resource_schema |
| `resource.parent` | STRING | NULLABLE | não | — | — | Nome completo do pai imediato | #resource_schema |
| `resource.data` | STRING | NULLABLE | não | — | — | "The resource.data column is the resource metadata represented as a JSON string." | #resource_schema |
| `resource.location` | STRING | NULLABLE | não | — | — | Localização do recurso (zona/região) | #resource_schema |
| `ancestors` | STRING | REPEATED | não | — | — | Caminho de ancestralidade | #resource_schema |
| `update_time` | TIMESTAMP | NULLABLE | não | — | TIMESTAMP BigQuery | Última atualização do asset | #resource_schema |

### 3.2 IAM policy schema (content type `IAM_POLICY` / `iam-policy`)

Transcrito de
<https://cloud.google.com/asset-inventory/docs/exporting-to-bigquery#iam_policy_schema>.

| Campo | Tipo BigQuery | Mode | Obrigatório | Descrição | Fonte |
|---|---|---|---|---|---|
| `name` | STRING | NULLABLE | não | Nome do asset | #iam_policy_schema |
| `asset_type` | STRING | NULLABLE | não | Tipo do asset | #iam_policy_schema |
| `iam_policy` | RECORD | NULLABLE | não | Política IAM | #iam_policy_schema |
| `iam_policy.version` | INTEGER | NULLABLE | não | Versão da política | #iam_policy_schema |
| `iam_policy.bindings` | RECORD | REPEATED | não | Ligações da política | #iam_policy_schema |
| `iam_policy.bindings.role` | STRING | NULLABLE | não | Papel concedido | #iam_policy_schema |
| `iam_policy.bindings.members` | STRING | REPEATED | não | Membros do papel | #iam_policy_schema |
| `iam_policy.bindings.condition` | RECORD | NULLABLE | não | Condição da ligação | #iam_policy_schema |
| `iam_policy.bindings.condition.expression` | STRING | NULLABLE | não | Expressão da condição | #iam_policy_schema |
| `iam_policy.bindings.condition.title` | STRING | NULLABLE | não | Título da condição | #iam_policy_schema |
| `iam_policy.bindings.condition.description` | STRING | NULLABLE | não | Descrição da condição | #iam_policy_schema |
| `iam_policy.bindings.condition.location` | STRING | NULLABLE | não | Localização da condição | #iam_policy_schema |
| `iam_policy.audit_configs` | RECORD | REPEATED | não | Configurações de auditoria | #iam_policy_schema |
| `iam_policy.audit_configs.service` | STRING | NULLABLE | não | Serviço auditado | #iam_policy_schema |
| `iam_policy.audit_configs.audit_log_configs` | RECORD | REPEATED | não | Configurações de log de auditoria | #iam_policy_schema |
| `iam_policy.audit_configs.audit_log_configs.log_type` | INTEGER | NULLABLE | não | Tipo de log | #iam_policy_schema |
| `iam_policy.audit_configs.audit_log_configs.exempted_members` | STRING | REPEATED | não | Membros isentos | #iam_policy_schema |
| `iam_policy.etag` | STRING | NULLABLE | não | ETag da política | #iam_policy_schema |
| `ancestors` | STRING | REPEATED | não | Caminho de ancestralidade | #iam_policy_schema |
| `update_time` | TIMESTAMP | NULLABLE | não | Última atualização | #iam_policy_schema |

### 3.3 Organization policy schema (content type `ORG_POLICY` / `org-policy`)

Transcrito de
<https://cloud.google.com/asset-inventory/docs/exporting-to-bigquery#organization_policy_schema>.

| Campo | Tipo BigQuery | Mode | Obrigatório | Descrição | Fonte |
|---|---|---|---|---|---|
| `name` | STRING | NULLABLE | não | Nome do asset | #organization_policy_schema |
| `asset_type` | STRING | NULLABLE | não | Tipo do asset | #organization_policy_schema |
| `org_policy` | RECORD | REPEATED | não | Políticas de organização | #organization_policy_schema |
| `org_policy.version` | INTEGER | NULLABLE | não | Versão da política | #organization_policy_schema |
| `org_policy.constraint` | STRING | NULLABLE | não | Nome do constraint | #organization_policy_schema |
| `org_policy.etag` | STRING | NULLABLE | não | ETag | #organization_policy_schema |
| `org_policy.update_time` | TIMESTAMP | NULLABLE | não | Última atualização | #organization_policy_schema |
| `org_policy.list_policy` | RECORD | NULLABLE | não | Política de lista | #organization_policy_schema |
| `org_policy.list_policy.allowed_values` | STRING | REPEATED | não | Valores permitidos | #organization_policy_schema |
| `org_policy.list_policy.denied_values` | STRING | REPEATED | não | Valores negados | #organization_policy_schema |
| `org_policy.list_policy.all_values` | INTEGER | NULLABLE | não | Todos os valores | #organization_policy_schema |
| `org_policy.list_policy.suggested_value` | STRING | NULLABLE | não | Valor sugerido | #organization_policy_schema |
| `org_policy.list_policy.inherit_from_parent` | BOOLEAN | NULLABLE | não | Herdar do pai | #organization_policy_schema |
| `org_policy.boolean_policy` | RECORD | NULLABLE | não | Política booleana | #organization_policy_schema |
| `org_policy.boolean_policy.enforced` | BOOLEAN | NULLABLE | não | Se está forçada | #organization_policy_schema |
| `org_policy.restore_default` | RECORD | NULLABLE | não | Restaurar padrão | #organization_policy_schema |
| `org_policy.restore_default._present` | BOOLEAN | NULLABLE | não | Presença do marcador | #organization_policy_schema |
| `ancestors` | STRING | REPEATED | não | Caminho de ancestralidade | #organization_policy_schema |
| `update_time` | TIMESTAMP | NULLABLE | não | Última atualização | #organization_policy_schema |

### 3.4 Envelope `Asset` (fonte autoritativa dos nomes/tipos lógicos)

Fonte: <https://cloud.google.com/asset-inventory/docs/reference/rest/v1/Asset>
(consulta 2026-10-14). Estes são os campos da mensagem `Asset`, tal como a
referência REST os publica.

| Campo | Tipo | Obrigatório | Descrição | Fonte |
|---|---|---|---|---|
| `updateTime` | string (Timestamp) | não | "The last update timestamp of an asset. updateTime is updated when create/update/delete operation is performed. Uses RFC 3339, where generated output will always be Z-normalized and use 0, 3, 6 or 9 fractional digits." Exemplo: `"2014-10-02T15:01:23Z"` | [#Asset](https://cloud.google.com/asset-inventory/docs/reference/rest/v1/Asset#Asset) |
| `name` | string | não | "The full name of the asset. Example: `//compute.googleapis.com/projects/my_project_123/zones/zone1/instances/instance1`" | #Asset |
| `assetType` | string | não | "The type of the asset. Example: `compute.googleapis.com/Disk`" | #Asset |
| `resource` | object (Resource) | não | "A representation of the resource." | #Asset |
| `iamPolicy` | object (Policy) | não | "A representation of the IAM policy set on a Google Cloud resource. There can be a maximum of one IAM policy set on any given resource." | #Asset |
| `orgPolicy[]` | object (Policy) | não | "A representation of an organization policy. There can be more than one organization policy with different constraints set on a given resource." | #Asset |
| `osInventory` | object (Inventory) | não | "A representation of runtime OS Inventory information." | #Asset |
| `relatedAssets` | object (RelatedAssets) | não | **DEPRECATED.** "This field only presents for the purpose of backward-compatibility. The server will never generate responses with this field." | #Asset |
| `relatedAsset` | object (RelatedAsset) | não | "One related asset of the current asset." | #Asset |
| `ancestors[]` | string | não | "The ancestry path of an asset in Google Cloud resource hierarchy, represented as a list of relative resource names. [...] Example: `["projects/123456789", "folders/5432", "organizations/1234"]`" | #Asset |
| `assetExceptions[]` | object (AssetException) | não | "The exceptions of a resource." | #Asset |
| `accessPolicy` | object (AccessPolicy) | um de `access_context_policy` | "Also refer to the access policy user guide." | #Asset |
| `accessLevel` | object (AccessLevel) | um de `access_context_policy` | "Also refer to the access level user guide." | #Asset |
| `servicePerimeter` | object (ServicePerimeter) | um de `access_context_policy` | "Also refer to the service perimeter user guide." | #Asset |

### 3.5 Mensagem `Resource` e o campo `resource.data`

Fonte: <https://cloud.google.com/asset-inventory/docs/reference/rest/v1/Asset#Resource>

| Campo | Tipo | Obrigatório | Descrição | Fonte |
|---|---|---|---|---|
| `version` | string | não | "The API version. Example: `v1`" | #Resource |
| `discoveryDocumentUri` | string | não | "The URL of the discovery document containing the resource's JSON schema. Example: `https://www.googleapis.com/discovery/v1/apis/compute/v1/rest`" | #Resource |
| `discoveryName` | string | não | "The JSON schema name listed in the discovery document. Example: `Project`" | #Resource |
| `resourceUrl` | string | não | "The REST URL for accessing the resource. An HTTP GET request using this URL returns the resource itself." | #Resource |
| `parent` | string | não | "The full name of the immediate parent of this resource. [...] Example: `//cloudresourcemanager.googleapis.com/projects/my_project_123`" | #Resource |
| `data` | object (**Struct format**) | não | "The content of the resource, in which some sensitive fields are removed and may not be present." | #Resource |
| `location` | string | não | "The location of the resource in Google Cloud, such as its zone and region." | #Resource |

### 3.6 O que é documentado e o que é schema por asset type — **distinção explícita**

Esta é a separação pedida no escopo, com base apenas no que as páginas oficiais
afirmam:

1. **Documentado e explícito (verificado):**
   - Os schemas BigQuery das secções **3.1 (RESOURCE)**, **3.2 (IAM_POLICY)** e
     **3.3 (ORG_POLICY)** são publicados literalmente pela Google na página
     "Export asset metadata to BigQuery".
   - No schema RESOURCE, `resource.data` é uma **coluna STRING** contendo o
     metadata do recurso como **string JSON**.
   - Os nomes das colunas seguem a regra de *casing* da secção 2.3
     (`asset_type` em snake_case; `assetType` em camelCase quando se exporta
     para tabelas por asset type com content type RESOURCE).
2. **Documentado mas definido por asset type (não publicado por tipo):**
   - Quando `separateTablesPerAssetType=true` (e content type RESOURCE), "The
     schema of each table includes RECORD-type columns mapped to the nested
     fields in the `Resource.data` field of that asset type (up to the 15 nested
     levels that BigQuery supports)."
     ([exporting-to-bigquery#bigquery_schemas_used_for_export](https://cloud.google.com/asset-inventory/docs/exporting-to-bigquery))
   - A Google **não publica** o schema resultante para nenhum asset type
     específico. Para `compute.googleapis.com/Instance`, **não existe** schema
     por asset type publicado. Este é o ponto onde a fronteira entre "documentado"
     e "derivado" está.
3. **NÃO documentado (UNVERIFIED — não gerar):**
   - A forma concreta de `resource.data` para `compute.googleapis.com/Instance`
     **não é documentada** pela Cloud Asset Inventory. A página só a descreve
     como "Struct format" / "The content of the resource".
   - A relação entre os campos de `resource.data` e os campos da representação
     `Instances` do Compute Engine REST
     ([`compute-instances-rest.md`](compute-instances-rest.md)) **não é
     afirmada** em nenhuma página do Cloud Asset Inventory. A analogia é
     plausível, mas plausibilidade não é documentação — fica em UNVERIFIED.
   - Único exemplo oficial com forma concreta (e ainda assim em query SQL, não
     como schema): as consultas de exemplo usam
     `JSON_EXTRACT(instance.resource.data, ...)` para assets
     `compute.googleapis.com/Instance`
     — <https://cloud.google.com/asset-inventory/docs/exporting-to-bigquery#query_available_columns>

## 4. Campos

Os campos, tipos, modos e URLs de origem estão nas tabelas das secções 2 e 3
acima (uma linha por campo, com o URL da secção que o documenta). O inventário
legível por máquina correspondente está em
[`cloud-asset-inventory-compute-instance.schema.json`](cloud-asset-inventory-compute-instance.schema.json).

**Contagem (verificada no `.schema.json`):** 12 colunas no schema RESOURCE +
20 no IAM policy + 19 no organization policy + 14 campos da mensagem `Asset`
(13 ativos + `relatedAssets` deprecated) + 7 campos da mensagem `Resource` +
5 campos do pedido + 2 do destino GCS + 6 do destino BigQuery + 3 valores de
`PartitionKey` + 2 colunas extra de tabela particionada (`readTime`,
`requestTime`) = **90 entradas de campo**.

## 5. Campos não comprovados

| Item | Estado | Motivo |
|---|---|---|
| Forma concreta de `resource.data` para `compute.googleapis.com/Instance` | UNVERIFIED | Nenhuma página oficial do Cloud Asset Inventory publica o schema de `resource.data` para este (ou qualquer) asset type. A mensagem `Resource.data` é documentada apenas como "object (Struct format)": "The content of the resource, in which some sensitive fields are removed and may not be present." |
| Schema por asset type resultante de `separateTablesPerAssetType=true` para `compute.googleapis.com/Instance` | UNVERIFIED | A página afirma que o schema mapeia os campos aninhados de `Resource.data` em colunas RECORD (até 15 níveis), mas não publica o schema resultante; os "examples" referidos ficam no console, não na documentação. |
| Formato dos nomes de campo dentro de `resource.data` (camelCase vs snake_case) | UNVERIFIED | Não afirmado na documentação do Cloud Asset Inventory. |
| Compressão, encoding e formato exato dos objetos NDJSON no Cloud Storage | UNVERIFIED | Só o formato "newline-delimited JSON" é afirmado; compressão/encoding não são declarados. |
| Manifesto do export | UNVERIFIED | Não documentado. Existe o objeto `Operation` com o caminho `projects/PROJECT_NUMBER/operations/ExportAssets/CONTENT_TYPE/OPERATION_ID`, que não é um manifesto de arquivos. |
| Schema do content type `ACCESS_POLICY` (VPCSC) | PARCIAL | A página publica o schema `VPCSC policy schema`, mas ele não foi transcrito nesta passagem (a superfície pedida é `compute.googleapis.com/Instance`). Não gerar sem transcrição. |
| Schema do content type `OS_INVENTORY` | PARCIAL | A página publica o schema `OS inventory schema`, mas ele não foi transcrito nesta passagem. Não gerar sem transcrição. |
| Schema do content type `RELATIONSHIP` | PARCIAL | A página publica o schema `Relationship schema`, mas ele não foi transcrito nesta passagem. Não gerar sem transcrição. |

## 6. Divergências conhecidas

- **`updateTime` (Asset) vs `update_time` (coluna BigQuery):** a mensagem REST
  usa camelCase `updateTime`; a coluna BigQuery é `update_time`, TIMESTAMP. A
  regra de casing documentada explica a diferença; registrada para evitar que um
  gerador emita o nome errado em cada contexto.
- **`resource.data` como STRING (tabela única) vs RECORD (tabela por asset
  type):** o mesmo dado lógico é entregue com tipos BigQuery diferentes conforme
  `separateTablesPerAssetType`. Documentado explicitamente
  ([exporting-to-bigquery](https://cloud.google.com/asset-inventory/docs/exporting-to-bigquery)).
- **`relatedAssets` está deprecated** e "The server will never generate responses
  with this field", embora ainda conste da mensagem `Asset`. Registrado; não
  gerar. No `.schema.json` isto é expresso como `"status": "unverified"` +
  `"evidence": "deprecated"`: `status` é estritamente binário (`verified` /
  `unverified`) e a nuance qualitativa vive em `evidence`. Como qualquer
  `evidence` diferente de `declared` (ou ausente) torna a coluna **não
  gerável**, `relatedAssets` fica registrado como obsoleto e não é emitido.
