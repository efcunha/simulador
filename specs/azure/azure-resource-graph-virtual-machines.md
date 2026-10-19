# Azure Resource Graph — tabela `resources` (com `microsoft.compute/virtualmachines`) e tabela `securityresources`

## 1. Identificação

- **Nome oficial da superfície de export**: *Azure Resource Graph* — tabela `Resources` (nome oficial no documento: "Resources — The default table if a table isn't defined in the query. Most Resource Manager resource types and properties are here.") e tabela `SecurityResources`.
- **Documento oficial principal**: "Azure Resource Graph table and resource type reference" —
  <https://learn.microsoft.com/en-us/azure/governance/resource-graph/reference/supported-tables-resources> — consultado em **2026-10-14**.
- **Documentos de apoio consultados em 2026-10-14**:
  - "Explore your Azure resources with Resource Graph" — <https://learn.microsoft.com/en-us/azure/governance/resource-graph/concepts/explore-resources> (atualizada 2024-06-03)
  - "Understanding the Azure Resource Graph query language" — <https://learn.microsoft.com/en-us/azure/governance/resource-graph/concepts/query-language> (atualizada 2026-04-30)
  - "Working with large Azure resource data sets" — <https://learn.microsoft.com/en-us/azure/governance/resource-graph/concepts/work-with-data> (atualizada 2024-06-03)
  - "Resources - Resources" (REST, Azure Resource Graph, api-version `2024-04-01`) — <https://learn.microsoft.com/en-us/rest/api/azureresourcegraph/resourcegraph/resources/resources?view=rest-azureresourcegraph-resourcegraph-2024-04-01>
  - "Azure Resource Graph sample queries for Microsoft Defender for Cloud" — <https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples>
  - "Retrieve attack path data with API" — <https://learn.microsoft.com/en-us/azure/defender-for-cloud/attack-path-api>
  - "Get resource changes" — <https://learn.microsoft.com/en-us/azure/governance/resource-graph/changes/get-resource-changes> (atualizada 2026-04-03)
- **Versão/schema de referência**: API `2024-04-01` (REST); a tabela `Resources` não tem número de versão de schema — é indexada pelo **tipo de recurso** do ARM (ex.: `microsoft.compute/virtualmachines`) e pela **api-version do provedor** de cada recurso.

## 2. Mecanismo e entrega

### 2.1 O mecanismo existe — mas NÃO é um "export para Storage/Log Analytics/Event Hub"

O Azure Resource Graph é um **serviço de consulta** (KQL sobre um índice gerido pela Microsoft), consumido por:
- Azure portal (Resource Graph Explorer),
- Azure CLI (`az graph query`),
- Azure PowerShell (`Search-AzGraph`),
- REST API (`POST https://management.azure.com/providers/Microsoft.ResourceGraph/resources?api-version=2024-04-01`) — <https://learn.microsoft.com/en-us/rest/api/azureresourcegraph/resourcegraph/resources/resources?view=rest-azureresourcegraph-resourcegraph-2024-04-01>

O único "export" para ficheiro documentado é a **descarga manual em CSV a partir do Resource Graph Explorer**:

> "When using the comma-separated value (CSV) export functionality of Azure Resource Graph Explorer, the result set is limited to 55,000 records. This limitation is a platform limit that can't be overridden by filing an Azure support ticket. To download CSV results from the Azure portal, browse to the Azure Resource Graph Explorer and run a query. On the toolbar, select **Download as CSV**."
> — <https://learn.microsoft.com/en-us/azure/governance/resource-graph/concepts/work-with-data>

> **Nota de fidelidade:** o Resource Graph **não** é um mecanismo de exportação contínua para Storage/Log Analytics/Event Hub. Não existe *path template*, particionamento, compressão nem manifesto documentados. As colunas `delivery.*` do `.schema.json` são deixadas vazias por esse motivo, e não por omissão de pesquisa.

### 2.2 Formato do resultado

Duas formas de resultado, selecionadas por `resultFormat` nas opções do pedido:

- **`Table`** (predefinição): "returns results in a JSON format designed to highlight the column design and row values of the properties returned by the query." Envelope: `{ "totalRecords", "count", "data": { "columns": [{"name","type"}], "rows": [[...]] }, "facets", "resultTruncated" }`.
- **`ObjectArray`**: "aligns to the key/value pair relationship common in JSON where the column and the row data are matched in array groups." Envelope: `{ "totalRecords", "count", "data": [ {…} ], "facets", "resultTruncated" }`.

Fonte: <https://learn.microsoft.com/en-us/azure/governance/resource-graph/concepts/work-with-data>

**Limites e paginação documentados** (fonte: <https://learn.microsoft.com/en-us/azure/governance/resource-graph/concepts/work-with-data>):

| Item | Valor documentado |
|---|---|
| Limite predefinido de registos por consulta | 1 000 |
| Máximo do parâmetro `first` / `$top` | 1 000 |
| Limite de linhas do export CSV do Explorer | 55 000 |
| Timeout de consulta | 30 segundos |
| Campos de paginação na resposta | `resultTruncated`, `$skipToken`, `count`, `totalRecords` |
| Limite de operadores `join` por consulta | 3 |
| Limite de `mv-expand` por consulta | 3 |
| Limite de pernas `union` por consulta | 3 |
| `RowLimit` máximo de `mv-expand` / `mvexpand` | 2 000 (predefinição 128) |

### 2.3 Aviso de fidelidade importante: scrub de PII

> "Azure Resource Graph scrubs PII information from our tables so you may see not see the same result as if you made a GET request on your resource directly. The difference is due to security practices preventing the exposure of any identifiable information."
> — <https://learn.microsoft.com/en-us/azure/governance/resource-graph/reference/supported-tables-resources>

**Consequência para o simulador:** a representação de um VM na tabela `Resources` **não é idêntica** à representação ARM do `GET` (ver `arm-resource-representation`). O Resource Graph pode omitir/alterar campos identificáveis. As duas superfícies **não são intercambiáveis**.

### 2.4 Caixa dos nomes (documentado)

> "Depending on the Resource Graph table, properties will either match the casing as shown in the Azure portal or be lowercased. For example, the name of a resource group when querying the `resourceContainers` table will match the portal, but the `resourceGroup` property of resources from the `resources` table will be lowercase."
> — <https://learn.microsoft.com/en-us/azure/governance/resource-graph/concepts/explore-resources>

### 2.5 Tabela `securityresources`

> "SecurityResources — Includes resources _related_ to `Microsoft.Security`."
> — <https://learn.microsoft.com/en-us/azure/governance/resource-graph/concepts/query-language>

O tipo de recurso para attack paths é `microsoft.security/attackpaths` — <https://learn.microsoft.com/en-us/azure/defender-for-cloud/attack-path-api>

## 3. Campos

### 3.1 Tabela `Resources` — propriedades de nível de linha comprovadas

> **ADVERTÊNCIA DE MÉTODO (ler antes de usar esta secção).** A Microsoft **não publica** nenhuma página oficial, entre as consultadas, que apresente a **lista formal de colunas com tipos** da tabela `Resources` (ao contrário do que faz para tabelas do Azure Monitor, que têm tabelas de colunas explícitas). Os nomes abaixo são os que aparecem **em exemplos JSON oficiais de resposta do Azure Resource Graph**. Cada linha cita o exemplo concreto de onde o nome foi lido. **Nenhum tipo de dados é afirmado oficialmente** para estas colunas — ver §4.

| Campo | Tipo (não afirmado oficialmente — ver §4) | Obrigatório | Unidade | Formato data/hora | Valores permitidos | Descrição / origem documental | Fonte |
|---|---|---|---|---|---|---|---|
| id | string | false | — | — | — | Identificador ARM completo do recurso. Presente nos exemplos oficiais de resposta. | https://learn.microsoft.com/en-us/azure/governance/resource-graph/concepts/explore-resources |
| kind | string | false | — | — | — | Campo devolvido no exemplo oficial de VM (`"kind": ""`). | https://learn.microsoft.com/en-us/azure/governance/resource-graph/concepts/explore-resources |
| location | string | false | — | — | — | Região do recurso (`"location": "westus2"`). Usado em `summarize count() by location`. | https://learn.microsoft.com/en-us/azure/governance/resource-graph/concepts/explore-resources |
| managedBy | string | false | — | — | — | Campo devolvido no exemplo oficial (`"managedBy": ""`). | https://learn.microsoft.com/en-us/azure/governance/resource-graph/concepts/explore-resources |
| name | string | false | — | — | — | Nome do recurso (`"name": "ContosoVM1"`). | https://learn.microsoft.com/en-us/azure/governance/resource-graph/concepts/explore-resources |
| plan | object | false | — | — | — | Campo devolvido no exemplo oficial (`"plan": {}`). | https://learn.microsoft.com/en-us/azure/governance/resource-graph/concepts/explore-resources |
| properties | object (dynamic) | false | — | — | — | Saco de propriedades específicas do tipo de recurso. É o objeto onde vivem `hardwareProfile`, `networkProfile`, `osProfile`, `storageProfile`, etc. | https://learn.microsoft.com/en-us/azure/governance/resource-graph/concepts/explore-resources |
| resourceGroup | string | false | — | — | — | Nome do grupo de recursos. **Documentado como minúsculo** nesta tabela. | https://learn.microsoft.com/en-us/azure/governance/resource-graph/concepts/explore-resources |
| sku | object | false | — | — | — | Campo devolvido no exemplo oficial (`"sku": {}`). | https://learn.microsoft.com/en-us/azure/governance/resource-graph/concepts/explore-resources |
| subscriptionId | string | false | — | — | — | Id da subscrição. Usado em `join ResourceContainers on subscriptionId`. | https://learn.microsoft.com/en-us/azure/governance/resource-graph/concepts/query-language |
| tags | object | false | — | — | — | Etiquetas do recurso (`"tags": {}`). Exemplo de uso: `| where tags ['Environment'] =~ 'prod'`. | https://learn.microsoft.com/en-us/azure/governance/resource-graph/changes/get-resource-changes |
| tenantId | string | false | — | — | — | Presente na lista `project tenantId, subscriptionId, …` dos exemplos oficiais do Defender for Cloud sobre `securityresources`; também aparece na projeção de recursos em geral. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| type | string | false | — | — | ex.: `microsoft.compute/virtualmachines` | Tipo do recurso. Nos exemplos oficiais aparece **em minúsculas** (`"type": "microsoft.compute/virtualmachines"`), e as consultas oficiais comparam com `=~` (case-insensitive). | https://learn.microsoft.com/en-us/azure/governance/resource-graph/concepts/explore-resources |

**Colunas adicionais documentadas em texto normativo (não em exemplo JSON):**

| Campo | Tipo | Fonte | Nota |
|---|---|---|---|
| properties.extended | object (dynamic) | https://learn.microsoft.com/en-us/azure/governance/resource-graph/concepts/query-language | "As a _preview_ feature, some of the resource types in Resource Graph have more type-related properties available to query beyond the properties provided by Azure Resource Manager. This set of values, known as _extended properties_, exists on a supported resource type in `properties.extended`." Consulta documentada: `Resources \| where isnotnull(properties.extended) \| distinct type`. |

### 3.2 `properties.*` para `microsoft.compute/virtualmachines` — caminhos comprovados

Todos os caminhos abaixo foram lidos no exemplo JSON oficial de "Explore your Azure resources with Resource Graph", que devolve um recurso do tipo `microsoft.compute/virtualmachines`.
Fonte única desta subsecção: <https://learn.microsoft.com/en-us/azure/governance/resource-graph/concepts/explore-resources>

| Caminho | Tipo (segundo o exemplo) | Valor de exemplo | Fonte |
|---|---|---|---|
| properties.hardwareProfile | object | `{ "vmSize": "Standard_B2s" }` | https://learn.microsoft.com/en-us/azure/governance/resource-graph/concepts/explore-resources |
| properties.hardwareProfile.vmSize | string | `Standard_B2s` | https://learn.microsoft.com/en-us/azure/governance/resource-graph/concepts/explore-resources |
| properties.networkProfile | object | — | https://learn.microsoft.com/en-us/azure/governance/resource-graph/concepts/explore-resources |
| properties.networkProfile.networkInterfaces | array | — | https://learn.microsoft.com/en-us/azure/governance/resource-graph/concepts/explore-resources |
| properties.networkProfile.networkInterfaces[].id | string | `/subscriptions/<subscriptionId>/MyResourceGroup/providers/Microsoft.Network/networkInterfaces/contosovm2222` | https://learn.microsoft.com/en-us/azure/governance/resource-graph/concepts/explore-resources |
| properties.networkProfile.networkInterfaces[].resourceGroup | string | `MyResourceGroup` | https://learn.microsoft.com/en-us/azure/governance/resource-graph/concepts/explore-resources |
| properties.osProfile | object | — | https://learn.microsoft.com/en-us/azure/governance/resource-graph/concepts/explore-resources |
| properties.osProfile.adminUsername | string | `localAdmin` | https://learn.microsoft.com/en-us/azure/governance/resource-graph/concepts/explore-resources |
| properties.osProfile.computerName | string | `ContosoVM1` | https://learn.microsoft.com/en-us/azure/governance/resource-graph/concepts/explore-resources |
| properties.osProfile.secrets | array | `[]` | https://learn.microsoft.com/en-us/azure/governance/resource-graph/concepts/explore-resources |
| properties.osProfile.windowsConfiguration | object | — | https://learn.microsoft.com/en-us/azure/governance/resource-graph/concepts/explore-resources |
| properties.osProfile.windowsConfiguration.enableAutomaticUpdates | boolean | `true` | https://learn.microsoft.com/en-us/azure/governance/resource-graph/concepts/explore-resources |
| properties.osProfile.windowsConfiguration.provisionVMAgent | boolean | `true` | https://learn.microsoft.com/en-us/azure/governance/resource-graph/concepts/explore-resources |
| properties.provisioningState | string | `Succeeded` | https://learn.microsoft.com/en-us/azure/governance/resource-graph/concepts/explore-resources |
| properties.storageProfile | object | — | https://learn.microsoft.com/en-us/azure/governance/resource-graph/concepts/explore-resources |
| properties.storageProfile.dataDisks | array | `[]` | https://learn.microsoft.com/en-us/azure/governance/resource-graph/concepts/explore-resources |
| properties.storageProfile.imageReference | object | — | https://learn.microsoft.com/en-us/azure/governance/resource-graph/concepts/explore-resources |
| properties.storageProfile.imageReference.offer | string | `WindowsServer` | https://learn.microsoft.com/en-us/azure/governance/resource-graph/concepts/explore-resources |
| properties.storageProfile.imageReference.publisher | string | `MicrosoftWindowsServer` | https://learn.microsoft.com/en-us/azure/governance/resource-graph/concepts/explore-resources |
| properties.storageProfile.imageReference.sku | string | `2016-Datacenter` | https://learn.microsoft.com/en-us/azure/governance/resource-graph/concepts/explore-resources |
| properties.storageProfile.imageReference.version | string | `latest` | https://learn.microsoft.com/en-us/azure/governance/resource-graph/concepts/explore-resources |
| properties.storageProfile.osDisk | object | — | https://learn.microsoft.com/en-us/azure/governance/resource-graph/concepts/explore-resources |
| properties.storageProfile.osDisk.caching | string | `ReadWrite` | https://learn.microsoft.com/en-us/azure/governance/resource-graph/concepts/explore-resources |
| properties.storageProfile.osDisk.createOption | string | `FromImage` | https://learn.microsoft.com/en-us/azure/governance/resource-graph/concepts/explore-resources |
| properties.storageProfile.osDisk.diskSizeGB | integer | `127` | https://learn.microsoft.com/en-us/azure/governance/resource-graph/concepts/explore-resources |
| properties.storageProfile.osDisk.managedDisk | object | — | https://learn.microsoft.com/en-us/azure/governance/resource-graph/concepts/explore-resources |
| properties.storageProfile.osDisk.managedDisk.id | string | `/subscriptions/…/Microsoft.Compute/disks/ContosoVM1_OsDisk_1_1111…` | https://learn.microsoft.com/en-us/azure/governance/resource-graph/concepts/explore-resources |
| properties.storageProfile.osDisk.managedDisk.resourceGroup | string | `MyResourceGroup` | https://learn.microsoft.com/en-us/azure/governance/resource-graph/concepts/explore-resources |
| properties.storageProfile.osDisk.managedDisk.storageAccountType | string | `Premium_LRS` | https://learn.microsoft.com/en-us/azure/governance/resource-graph/concepts/explore-resources |
| properties.storageProfile.osDisk.name | string | `ContosoVM1_OsDisk_1_1111…` | https://learn.microsoft.com/en-us/azure/governance/resource-graph/concepts/explore-resources |
| properties.storageProfile.osDisk.osType | string | `Windows` | https://learn.microsoft.com/en-us/azure/governance/resource-graph/concepts/explore-resources |
| properties.vmId | string (GUID) | `11111111-1111-1111-1111-111111111111` | https://learn.microsoft.com/en-us/azure/governance/resource-graph/concepts/explore-resources |
| properties.extended.instanceView.powerState.code | string | — | https://learn.microsoft.com/en-us/azure/governance/resource-graph/concepts/query-language |

**Caminhos `properties.storageProfile.osDisk.osType` confirmados independentemente** na referência REST oficial do Resource Graph, que usa exatamente `properties.storageProfile.osDisk.osType` numa consulta e devolve a coluna achatada `properties_storageProfile_osDisk_osType` com valores `Linux` e `Windows`:
<https://learn.microsoft.com/en-us/rest/api/azureresourcegraph/resourcegraph/resources/resources?view=rest-azureresourcegraph-resourcegraph-2024-04-01> (exemplo "Access a properties field")

### 3.3 Tabela `securityresources` — campos por tipo de recurso

#### 3.3.1 `microsoft.security/locations/alerts`

Fonte: <https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples>

| Campo | Tipo | Obrigatório | Unidade | Formato data/hora | Valores permitidos | Descrição | Fonte |
|---|---|---|---|---|---|---|---|
| type | string | false | — | — | `microsoft.security/locations/alerts` | Tipo do recurso (comparado com `=~` no exemplo oficial). | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| properties.Status | string | false | — | — | exemplo oficial usa `Active` | Estado do alerta. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| properties.Severity | string | false | — | — | `Low`, `Medium`, `High` (no exemplo oficial) | Severidade do alerta. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| properties.AlertType | string | false | — | — | — | Tipo do alerta. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| properties.SystemAlertId | string | false | — | — | — | Identificador do alerta. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| properties.ResourceIdentifiers | dynamic | false | — | — | — | Identificadores dos recursos afectados (lido com `todynamic`). | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |

#### 3.3.2 `microsoft.security/iotalerts`

| Campo | Tipo | Obrigatório | Unidade | Formato data/hora | Valores permitidos | Descrição | Fonte |
|---|---|---|---|---|---|---|---|
| type | string | false | — | — | `microsoft.security/iotalerts` | Tipo do recurso. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| properties.alertType | string | false | — | — | — | Tipo do alerta IoT. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| properties.systemAlertId | string | false | — | — | — | Identificador do alerta IoT. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |

#### 3.3.3 `microsoft.security/insights/classification`

| Campo | Tipo | Obrigatório | Unidade | Formato data/hora | Valores permitidos | Descrição | Fonte |
|---|---|---|---|---|---|---|---|
| type | string | false | — | — | `microsoft.security/insights/classification` | Tipo do recurso. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| properties.associatedResource | string | false | — | — | — | Recurso associado à classificação. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| properties.insightProperties.purviewCatalogs[0].sensitivity | string | false | — | — | — | Sensibilidade da classificação (projetada como `SensitivityInsight`). | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |

#### 3.3.4 `microsoft.security/assessments`

Fonte: <https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples>

| Campo | Tipo | Obrigatório | Unidade | Formato data/hora | Valores permitidos | Descrição | Fonte |
|---|---|---|---|---|---|---|---|
| type | string | false | — | — | `microsoft.security/assessments` | Tipo do recurso. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| id | string | false | — | — | — | Id do recurso; projetado como `resourceId` no exemplo oficial. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| name | string | false | — | — | — | Id da avaliação; projetado como `recommendationId` / `assessmentKey`. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| properties.displayName | string | false | — | — | — | Nome de apresentação da recomendação. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| properties.resourceDetails.Source | string | false | — | — | — | Origem do recurso avaliado. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| properties.status.code | string | false | — | — | — | Estado da avaliação (`recommendationState`). | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| properties.metadata.description | string | false | — | — | — | Descrição da avaliação. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| properties.metadata.assessmentType | string | false | — | — | — | Tipo de avaliação. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| properties.metadata.remediationDescription | string | false | — | — | — | Descrição da remediação. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| properties.metadata.policyDefinitionId | string | false | — | — | — | Id da definição de política associada. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| properties.metadata.implementationEffort | string | false | — | — | — | Esforço de implementação. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| properties.metadata.severity | string | false | — | — | — | Severidade da recomendação. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| properties.metadata.categories | array | false | — | — | — | Categorias da recomendação. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| properties.metadata.userImpact | string | false | — | — | — | Impacto no utilizador. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| properties.metadata.threats | array | false | — | — | — | Ameaças associadas. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| properties.links.azurePortal | string | false | — | — | — | Ligação para o portal (`portalLink`). | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |

#### 3.3.5 `microsoft.security/assessments/subassessments`

Fonte: <https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples>

| Campo | Tipo | Obrigatório | Unidade | Formato data/hora | Valores permitidos | Descrição | Fonte |
|---|---|---|---|---|---|---|---|
| type | string | false | — | — | `microsoft.security/assessments/subassessments` | Tipo do recurso. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| id | string | false | — | — | — | Id do recurso; usado com `extract('.*assessments/(.+?)/.*',1, id)` para derivar `assessmentKey`. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| name | string | false | — | — | — | Id da sub-avaliação (`subassessmentKey`). | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| resourceGroup | string | false | — | — | — | Grupo de recursos. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| subscriptionId | string | false | — | — | — | Subscrição. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| tenantId | string | false | — | — | — | Tenant. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| properties.description | string | false | — | — | — | Descrição. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| properties.displayName | string | false | — | — | — | Nome de apresentação. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| properties.resourceDetails.id | string | false | — | — | — | Id do recurso avaliado. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| properties.resourceDetails.source | string | false | — | — | — | Origem do recurso avaliado. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| properties.category | string | false | — | — | — | Categoria. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| properties.status.severity | string | false | — | — | — | Severidade. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| properties.status.code | string | false | — | — | — | Código de estado. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| properties.timeGenerated | string | false | — | — | — | Instante de geração (lido com `properties.timeGenerated`). | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| properties.remediation | string | false | — | — | — | Remediação. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| properties.impact | string | false | — | — | — | Impacto. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| properties.id | string | false | — | — | — | Id da vulnerabilidade (`vulnId`). | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| properties.additionalData | dynamic | false | — | — | — | Dados adicionais. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |

#### 3.3.6 `microsoft.security/securescores`

Fonte: <https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples>

| Campo | Tipo | Obrigatório | Unidade | Formato data/hora | Valores permitidos | Descrição | Fonte |
|---|---|---|---|---|---|---|---|
| type | string | false | — | — | `microsoft.security/securescores` | Tipo do recurso. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| subscriptionId | string | false | — | — | — | Subscrição. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| tenantId | string | false | — | — | — | Tenant. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| properties.score.max | number | false | — | — | — | Pontuação máxima do secure score da subscrição. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| properties.score.current | number | false | — | — | — | Pontuação atual do secure score da subscrição. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| properties.weight | number | false | — | — | — | Peso da subscrição no cálculo agregado. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |

#### 3.3.7 `microsoft.security/securescores/securescorecontrols`

Fonte: <https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples>

| Campo | Tipo | Obrigatório | Unidade | Formato data/hora | Valores permitidos | Descrição | Fonte |
|---|---|---|---|---|---|---|---|
| type | string | false | — | — | `microsoft.security/securescores/securescorecontrols` | Tipo do recurso. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| tenantId | string | false | — | — | — | Tenant. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| subscriptionId | string | false | — | — | — | Subscrição. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| properties.displayName | string | false | — | — | — | Nome do controlo (`controlName`). | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| properties.definition.name | string | false | — | — | — | Nome/id do controlo na definição (`controlId`). | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| properties.notApplicableResourceCount | number | false | — | — | — | Recursos não aplicáveis. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| properties.unhealthyResourceCount | number | false | — | — | — | Recursos não saudáveis. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| properties.healthyResourceCount | number | false | — | — | — | Recursos saudáveis. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| properties.score.percentage | number | false | — | — | — | Pontuação percentual do controlo. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| properties.score.current | number | false | — | — | — | Pontuação atual do controlo. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| properties.weight | number | false | — | — | — | Peso do controlo. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| properties.definition.properties.maxScore | number | false | — | — | — | Pontuação máxima do controlo (`maxScore`). | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| properties.definition.properties.source.sourceType | string | false | — | — | — | Tipo de origem do controlo (`controlType`). | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| properties.definition.properties.assessmentDefinitions | array | false | — | — | — | Ids de avaliação recomendados do controlo. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |

#### 3.3.8 `microsoft.security/regulatorycompliancestandards`

Fonte: <https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples>

| Campo | Tipo | Obrigatório | Unidade | Formato data/hora | Valores permitidos | Descrição | Fonte |
|---|---|---|---|---|---|---|---|
| type | string | false | — | — | `microsoft.security/regulatorycompliancestandards` | Tipo do recurso. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| name | string | false | — | — | — | Nome do padrão de conformidade (`complianceStandard`). | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| tenantId | string | false | — | — | — | Tenant. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| subscriptionId | string | false | — | — | — | Subscrição. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| properties.state | string | false | — | — | — | Estado do padrão. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| properties.passedControls | number | false | — | — | — | Controlos aprovados. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| properties.failedControls | number | false | — | — | — | Controlos reprovados. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| properties.skippedControls | number | false | — | — | — | Controlos ignorados. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| properties.unsupportedControls | number | false | — | — | — | Controlos não suportados. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |

#### 3.3.9 `microsoft.security/regulatorycompliancestandards/regulatorycompliancecontrols/regulatorycomplianceassessments`

Fonte: <https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples>

| Campo | Tipo | Obrigatório | Unidade | Formato data/hora | Valores permitidos | Descrição | Fonte |
|---|---|---|---|---|---|---|---|
| type | string | false | — | — | `microsoft.security/regulatorycompliancestandards/regulatorycompliancecontrols/regulatorycomplianceassessments` | Tipo do recurso. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| id | string | false | — | — | — | Id; usado para extrair `complianceStandard` e `complianceControl` por expressão regular oficial. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| tenantId | string | false | — | — | — | Tenant. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| subscriptionId | string | false | — | — | — | Subscrição. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| properties.description | string | false | — | — | — | Descrição da avaliação (`assessmentName`). | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| properties.state | string | false | — | — | — | Estado da avaliação. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| properties.skippedResources | number | false | — | — | — | Recursos ignorados. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| properties.passedResources | number | false | — | — | — | Recursos aprovados. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |
| properties.failedResources | number | false | — | — | — | Recursos reprovados. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/resource-graph-samples |

#### 3.3.10 `microsoft.security/attackpaths`

Fonte: <https://learn.microsoft.com/en-us/azure/defender-for-cloud/attack-path-api> (ver também a spec `defender-for-cloud-continuous-export.md`, §3.4)

| Campo | Tipo | Obrigatório | Unidade | Formato data/hora | Valores permitidos | Descrição | Fonte |
|---|---|---|---|---|---|---|---|
| type | string | false | — | — | `microsoft.security/attackpaths` | Tipo do recurso. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/attack-path-api |
| subscriptionId | string | false | — | — | — | Subscrição do attack path. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/attack-path-api |
| properties.displayName | string | false | — | — | — | Nome de apresentação do attack path. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/attack-path-api |
| ID, Name, Type, Tenant ID, Location, Subscription ID, Properties.* | — | — | — | — | — | Lista completa (21 campos) transcrita em `defender-for-cloud-continuous-export.md` §3.4, com a mesma fonte. | https://learn.microsoft.com/en-us/azure/defender-for-cloud/attack-path-api |

### 3.4 `securityresources` — tipos de recurso listados oficialmente

A lista de tipos suportados por tabela está em <https://learn.microsoft.com/en-us/azure/governance/resource-graph/reference/supported-tables-resources>. Para a tabela `securityresources`, o documento de tipos suportados **não** apresenta uma secção `securityresources` com tipos enumerados na versão consultada; os tipos comprovados nesta spec são os que aparecem nos exemplos oficiais do Defender for Cloud (§3.3) mais `microsoft.security/attackpaths`. Ver §4.

## 4. Campos não comprovados

### 4.0 Nota sobre `sets`, `evidence` e gerabilidade (contrato atualizado)

O `.schema.json` está em `sets`, um por tabela/tipo de recurso, porque os mesmos nomes (`id`, `name`, `type`, `resourceGroup`, `subscriptionId`, `tenantId`, `properties.displayName`, `properties.state`, …) aparecem em **estruturas diferentes** com significados diferentes. Isto é o que a documentação descreve, não uma arrumação nossa.

**Veredito de gerabilidade: 32 das 148 colunas são geráveis** — as 32 do conjunto `Resources/microsoft.compute/virtualmachines` cuja forma é fixada pelo exemplo JSON oficial; as outras 116 continuam **não-geráveis**.

**Justificação (uma frase):** a tabela `resources` **não tem documentação normativa das suas colunas em nenhum sítio que tenhamos alcançado** — a Microsoft não publica uma página com a lista de colunas e tipos da `resources` (ao contrário das referências do Azure Monitor) — pelo que os nomes vêm exclusivamente de exemplos/consultas oficiais; onde o exemplo oficial fixa a representação (`"vmSize": "Standard_B2s"` ⇒ string, `"diskSizeGB": 127` ⇒ inteiro, `"enableAutomaticUpdates": true` ⇒ boolean, `"secrets": []` ⇒ array, `"osProfile": { … }` ⇒ objeto) e o campo é `declared`, o contrato atual autoriza `type_source: "format-observed"` com o trecho citado em `type_note`; nos restantes a forma não é fixada ou o campo só existe no exemplo (trava).

Distribuição do `evidence` e o que a sustenta:

| set | `evidence` | Gerável | Sustentação |
|---|---|---|---|
| `Resources` (14) | `example-only` | 0 — trava | nomes lidos da amostra JSON oficial de "Explore your Azure resources with Resource Graph"; sem descrição normativa de campo |
| `Resources/microsoft.compute/virtualmachines` (33) | `declared` | **32 de 33** | cada caminho `properties.*` tem descrição na referência de templates ARM consultada; o exemplo oficial fixa a forma de 32 deles. `properties.extended.instanceView.powerState.code` fica sem tipo: a única menção oficial é a consulta `summarize count() by tostring(properties.extended.instanceView.powerState.code)`, que não é um payload |
| `SecurityResources/…/attackpaths` (17) | `declared` (15) + `example-only` (2) | 0 | a página "Retrieve attack path data with API" é uma **tabela de campos com descrição por campo**, sem tipo e **sem exemplo de payload** (o que impede `format-observed`); `type` e `subscriptionId` vêm só da consulta de exemplo |
| restantes 9 conjuntos de `securityresources` (84) | `example-only` | 0 — trava | os nomes vêm de **consultas de exemplo** oficiais do Defender for Cloud; a página não descreve cada campo |

Nos conjuntos que permanecem não-geráveis, a Microsoft não publica o **tipo** na documentação do Resource Graph e nenhum exemplo oficial fixa a forma (ou o campo só existe no exemplo, quando `evidence: example-only`), pelo que `type_source: "format-observed"` não se aplica; essas colunas mantêm `type: null` + `type_note`. **Consequência aceite e explícita: o simulador gera apenas `properties.*` de `microsoft.compute/virtualmachines`, nunca a linha inteira da tabela `Resources` nem a `securityresources`.**

> **Substituição de vocabulário:** o campo antigo `"type_asserted_by_docs": false` (que existia nestas colunas) foi **removido** e uniformemente substituído por `evidence` + `type: null`: onde a Microsoft não afirma o tipo, a coluna fica `declared` (campo descrito normativamente) ou `example-only` (campo só ilustrado). Deixou de existir qualquer flag booleana ad-hoc; a nuance está toda em `evidence`. *(Nota histórica: desde a introdução de `type_source`, uma coluna `declared` cuja forma o exemplo oficial fixa volta a ser gerável — é o caso das 32 de `microsoft.compute/virtualmachines`.)*

| Item | Estado | Motivo |
|---|---|---|
| **Esquema formal de colunas da tabela `resources` (nomes + tipos)** | UNVERIFIED | A Microsoft **não publica** uma página oficial com a tabela de colunas da `resources` com tipos, ao contrário do que faz para tabelas do Azure Monitor. Todos os nomes em §3.1 foram lidos em **exemplos JSON oficiais**; os **tipos** não são afirmados por nenhuma página consultada. |
| Tipos de dados das colunas `resources` (`kind`, `managedBy`, `plan`, `sku`, `tags`, `tenantId`, …) | UNVERIFIED | Aparecem em exemplos com `""`/`{}`, o que não fixa o tipo (string vs object vs nullable). |
| Obrigatoriedade (required) de qualquer coluna de `resources` | UNVERIFIED | Nenhuma página oficial afirma que uma coluna da tabela seja sempre presente. |
| Lista completa de `properties.*` para `microsoft.compute/virtualmachines` na tabela `resources` | UNVERIFIED | Só os caminhos de §3.2 estão comprovados (exemplo oficial + consulta REST oficial). A documentação **não** apresenta a lista completa, e o aviso de scrub de PII indica que pode divergir do ARM. |
| `properties.extended.*` para VMs, além de `instanceView.powerState.code` | UNVERIFIED | Apenas esse caminho é exemplificado oficialmente. `properties.extended` é marcado como **preview**. |
| Enumeração oficial dos tipos de recurso da tabela `securityresources` | UNVERIFIED | O documento de tipos suportados consultado não apresenta a lista para `securityresources` na versão obtida. |
| Campos de `microsoft.security/assessments` além dos usados no exemplo | UNVERIFIED | Os nomes são os do exemplo oficial; não há schema formal publicado. |
| Tipos de dados dos campos de `securityresources` | UNVERIFIED | Nenhuma página oficial apresenta tabela de tipos; os valores `number`/`array` em §3.3 são classificação do autor a partir do uso nas consultas (`tolong`, `todouble`, `mv-expand`, `todynamic`). |
| `delivery.path_template`, `delivery.compression`, `delivery.format` do Resource Graph | UNVERIFIED | O Resource Graph **não** é um mecanismo de exportação para Storage/Log Analytics/Event Hub; não existe caminho nem compressão documentados. Campos deixados vazios por desenho. O único formato de ficheiro documentado é o CSV manual do Explorer (55 000 linhas) cujo cabeçalho de colunas **não** é publicado. |
| Schema da tabela `ResourceChanges` / `resourcechanges` | UNVERIFIED | A página "Get resource changes" apresenta um **exemplo** de payload e remete para a referência REST `/rest/api/resources/changes` para o "full reference guide for change resource properties". Essa referência REST não foi lida nesta investigação, pelo que nenhum campo é aqui afirmado como schema dessa tabela. |

## 5. Divergências conhecidas

1. **Resource Graph NÃO é export.** É um serviço de consulta. O único "export" documentado é o CSV manual (55 000 linhas) do Resource Graph Explorer. Não existe entrega contínua para Storage/Log Analytics/Event Hub por este mecanismo.
2. **Scrub de PII.** O próprio documento oficial afirma que os resultados do Resource Graph **podem diferir** de um `GET` direto ao recurso. Portanto, um simulador que emita a tabela `resources` a partir da representação ARM **não é fiel**: tem de registar explicitamente a possibilidade de divergência.
3. **Caixa dos nomes.** `resourceGroup` é minúsculo na tabela `resources`, mas preserva a caixa do portal em `resourceContainers`. E `type` aparece em minúsculas nos exemplos, sendo a comparação feita oficialmente com `=~`.
4. **Achatamento de propriedades em consultas de agregação.** Quando uma consulta agrega por uma propriedade, os resultados vêm achatados com `_` no lugar dos pontos (ex.: `properties_storageProfile_osDisk_osType`), e não com a estrutura aninhada. Isto é um artefacto da consulta, não um schema alternativo — ver <https://learn.microsoft.com/en-us/rest/api/azureresourcegraph/resourcegraph/resources/resources?view=rest-azureresourcegraph-resourcegraph-2024-04-01> (exemplo "Access a properties field").
5. **Limite de `first` vs `limit`/`take`.** "The control that's _most restrictive_ wins." E `skip` é ignorado quando `limit`/`take` estão presentes.
6. **Nomes de tabela sensíveis à caixa?** Os exemplos oficiais escrevem `Resources`, `resources`, `SecurityResources`, `securityresources` e `resourcechanges` indiferentemente. A documentação não afirma que os nomes de tabela sejam case-insensitive; registado como observação, sem inferência.
