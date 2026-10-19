# Microsoft Defender for Cloud — exportação contínua (continuous export)

## 1. Identificação

- **Nome oficial da superfície de export**: *Microsoft Defender for Cloud continuous export* ("Export alerts and recommendations with continuous export").
- **Documento oficial principal**: "Export alerts and recommendations with continuous export" —
  <https://learn.microsoft.com/en-us/azure/defender-for-cloud/benefits-of-continuous-export> — consultado em **2026-10-14** (página atualizada em 2026-06-17).
- **Documentos de apoio consultados em 2026-10-14**:
  - "Set up continuous export in the Azure portal" — <https://learn.microsoft.com/en-us/azure/defender-for-cloud/continuous-export> (atualizada 2026-08-08)
  - "Set up continuous export with REST API" — <https://learn.microsoft.com/en-us/azure/defender-for-cloud/continuous-export-rest-api> (atualizada 2026-08-08)
  - "View exported data in Azure Monitor" — <https://learn.microsoft.com/en-us/azure/defender-for-cloud/continuous-export-view-data> (atualizada 2026-08-08)
  - "Alerts schemas" — <https://learn.microsoft.com/en-us/azure/defender-for-cloud/alerts-schemas> (atualizada 2026-06-17)
  - "Automations - Get" (REST, Defender for Cloud, api-version `2023-12-01-preview`) — <https://learn.microsoft.com/en-us/rest/api/defenderforcloud-composite/automations/get?view=rest-defenderforcloud-composite-latest&tabs=HTTP>
  - "Azure Monitor Logs reference — SecurityAlert" — <https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/securityalert> (atualizada 2026-07-28)
  - "Azure Monitor Logs reference — SecurityRecommendation" — <https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/securityrecommendation> (atualizada 2026-07-28)
- **Versão/schema de referência**: API de automações do Defender for Cloud **`2023-12-01-preview`** (enum `EventSource`); tabelas do Log Analytics **`SecurityAlert`** e **`SecurityRecommendation`**.

## 2. Mecanismo e entrega

### 2.1 O mecanismo existe e está documentado

Microsoft documenta explicitamente que o Defender for Cloud exporta dados de segurança continuamente para destinos específicos:

> "Microsoft Defender for Cloud provides continuous export of security data. This feature allows you to stream security data to Log Analytics in Azure Monitor, to Azure Event Hubs, or to another Security Information and Event Management (SIEM), Security Orchestration Automated Response (SOAR) …"
> — <https://learn.microsoft.com/en-us/azure/defender-for-cloud/benefits-of-continuous-export>

**Destinos documentados:**

| Destino | Comprovado em |
|---|---|
| Log Analytics workspace (Azure Monitor) | <https://learn.microsoft.com/en-us/azure/defender-for-cloud/continuous-export> |
| Azure Event Hubs | <https://learn.microsoft.com/en-us/azure/defender-for-cloud/continuous-export> |
| Azure Logic Apps | <https://learn.microsoft.com/en-us/azure/defender-for-cloud/continuous-export-rest-api> |

**NÃO é destino documentado:** Azure Storage (conta de armazenamento / blob / container). Nenhum dos documentos consultados afirma que a exportação contínua escreva em Storage. A única exportação para ficheiro documentada é a **manual, pontual, em CSV**, a partir do portal — ver §5.

### 2.2 Formato do ficheiro / mensagem

- A documentação de destino (Log Analytics / Event Hubs) afirma: *"Defender for Cloud sends data in JavaScript Object Notation (JSON) format. You can use Event Hubs Capture or consumer groups to store and analyze the exported events."* — <https://learn.microsoft.com/en-us/azure/defender-for-cloud/continuous-export-view-data>
- **Não existe**, em nenhuma das páginas consultadas, um *path template*, `format`, `compression` ou convenção de particionamento documentados para esta superfície. O que é documentado é a **tabela** de destino no Log Analytics, não o caminho do blob.

### 2.3 Frequência e filtros

- **Streaming**: "Assessments are sent when a resource's health state is updated (if no updates occur, no data is sent)." — <https://learn.microsoft.com/en-us/azure/defender-for-cloud/continuous-export>
- **Snapshots**: "A snapshot of the current state of the selected data types that are sent once a week per subscription. To identify snapshot data, look for the field **IsSnapshot**." — <https://learn.microsoft.com/en-us/azure/defender-for-cloud/continuous-export>
- **Limite**: "Log Analytics supports only records that are up to 32 KB in size." — <https://learn.microsoft.com/en-us/azure/defender-for-cloud/continuous-export>

### 2.4 Tipos de registo (record types) oficialmente exportáveis

Os tipos exportáveis são fixados pelo enum `EventSource` da API de automações. São **13 valores** documentados:

`Assessments`, `AssessmentsSnapshot`, `SubAssessments`, `SubAssessmentsSnapshot`, `Alerts`, `SecureScores`, `SecureScoresSnapshot`, `SecureScoreControls`, `SecureScoreControlsSnapshot`, `RegulatoryComplianceAssessment`, `RegulatoryComplianceAssessmentSnapshot`, `AttackPaths`, `AttackPathsSnapshot`
— <https://learn.microsoft.com/en-us/rest/api/defenderforcloud-composite/automations/get?view=rest-defenderforcloud-composite-latest&tabs=HTTP> (secção `EventSource`)

A página "benefits-of-continuous-export" enumera as categorias de negócio equivalentes: Security recommendations (com subcategorias *Recommendation severity* e *Security findings*), Secure score (com subcategoria *Controls*), Security alerts, Regulatory compliance, Attack paths — <https://learn.microsoft.com/en-us/azure/defender-for-cloud/benefits-of-continuous-export>

### 2.5 Mapeamento tipo → tabela de destino (Log Analytics)

Documentado explicitamente:

- `SecurityAlert` — alertas de segurança. <https://learn.microsoft.com/en-us/azure/defender-for-cloud/continuous-export-view-data>
- `SecurityRecommendation` — recomendações/avaliações. <https://learn.microsoft.com/en-us/azure/defender-for-cloud/continuous-export-view-data>
- O tipo `AutomationActionWorkspace` confirma: "Security alerts data will reside in the 'SecurityAlert' table and the assessments data will reside in the 'SecurityRecommendation' table (under the 'Security'/'SecurityCenterFree' solutions)." — <https://learn.microsoft.com/en-us/rest/api/defenderforcloud-composite/automations/get?view=rest-defenderforcloud-composite-latest&tabs=HTTP>

> **Nota de fidelidade:** a documentação oficial **não** nomeia tabelas de destino para secure score, regulatory compliance nem attack paths. Ver §4 e §5.

## 3. Campos

Os campos abaixo são os campos de **esquema documentado**. Cada linha cita a secção exata.

### 3.1 Tabela `SecurityAlert` — payload de alertas

Fonte da lista de colunas e tipos: <https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/securityalert>
Fonte dos nomes/descrições de negócio: <https://learn.microsoft.com/en-us/azure/defender-for-cloud/alerts-schemas> (aba *Continuous export*)

| Campo | Tipo | Obrigatório | Unidade | Formato data/hora | Valores permitidos | Descrição | Fonte |
|---|---|---|---|---|---|---|---|
| AlertLink | string | false | — | — | — | Ligação do alerta (coluna da tabela) | https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/securityalert |
| AlertName | string | false | — | — | — | Alert display name | https://learn.microsoft.com/en-us/azure/defender-for-cloud/alerts-schemas |
| AlertSeverity | string | false | — | — | High / Medium / Low / Informational (documentados como "Severity") | The alert severity | https://learn.microsoft.com/en-us/azure/defender-for-cloud/alerts-schemas |
| AlertType | string | false | — | — | — | unique alert identifier | https://learn.microsoft.com/en-us/azure/defender-for-cloud/alerts-schemas |
| _BilledSize | real | false | bytes | — | — | The record size in bytes | https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/securityalert |
| CompromisedEntity | string | false | — | — | — | Entidade comprometida (coluna da tabela) | https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/securityalert |
| ConfidenceLevel | string | false | — | — | High / Low ("(Optional) The confidence level of this alert (High/Low)") | The confidence level of this alert | https://learn.microsoft.com/en-us/azure/defender-for-cloud/alerts-schemas |
| ConfidenceScore | real | false | — | — | — | Numeric confidence indicator of the security alert | https://learn.microsoft.com/en-us/azure/defender-for-cloud/alerts-schemas |
| Description | string | false | — | — | — | Description text for the alert | https://learn.microsoft.com/en-us/azure/defender-for-cloud/alerts-schemas |
| DisplayName | string | false | — | — | — | The alert's display name | https://learn.microsoft.com/en-us/azure/defender-for-cloud/alerts-schemas |
| EndTime | datetime | false | — | ISO 8601 UTC (tipo `datetime` do Log Analytics) | — | The effect end time of the alert | https://learn.microsoft.com/en-us/azure/defender-for-cloud/alerts-schemas |
| Entities | string | false | — | — | — | A list of entities related to the alert | https://learn.microsoft.com/en-us/azure/defender-for-cloud/alerts-schemas |
| ExtendedLinks | string | false | — | — | — | (Optional) A bag for all links related to the alert | https://learn.microsoft.com/en-us/azure/defender-for-cloud/alerts-schemas |
| ExtendedProperties | string | false | — | — | — | A bag of extra fields, which are relevant to the alert | https://learn.microsoft.com/en-us/azure/defender-for-cloud/alerts-schemas |
| _IsBillable | string | false | — | — | `true` / `false` | Specifies whether ingesting the data is billable | https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/securityalert |
| IsIncident | bool | false | — | — | `true` / `false` | Determines if the alert is an incident or a regular alert | https://learn.microsoft.com/en-us/azure/defender-for-cloud/alerts-schemas |
| ProcessingEndTime | datetime | false | — | ISO 8601 UTC (tipo `datetime`) | — | UTC timestamp in which the alert was created | https://learn.microsoft.com/en-us/azure/defender-for-cloud/alerts-schemas |
| ProductComponentName | string | false | — | — | — | (Optional) The name of a component inside the product, which generated the alert | https://learn.microsoft.com/en-us/azure/defender-for-cloud/alerts-schemas |
| ProductName | string | false | — | — | constant `Azure Security Center` | constant ('Azure Security Center') | https://learn.microsoft.com/en-us/azure/defender-for-cloud/alerts-schemas |
| ProviderName | string | false | — | — | — | unused | https://learn.microsoft.com/en-us/azure/defender-for-cloud/alerts-schemas |
| RemediationSteps | string | false | — | — | — | Manual action items to take to remediate the security threat | https://learn.microsoft.com/en-us/azure/defender-for-cloud/alerts-schemas |
| ResourceId | string | false | — | — | — | Full identifier of the affected resource | https://learn.microsoft.com/en-us/azure/defender-for-cloud/alerts-schemas |
| SourceComputerId | string | false | — | — | GUID | a unique GUID for the affected server (if the alert is generated on the server) | https://learn.microsoft.com/en-us/azure/defender-for-cloud/alerts-schemas |
| StartTime | datetime | false | — | ISO 8601 UTC (tipo `datetime`) | — | The effect start time of the alert | https://learn.microsoft.com/en-us/azure/defender-for-cloud/alerts-schemas |
| Status | string | false | — | — | — | Estado do alerta (coluna da tabela) | https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/securityalert |
| SubTechniques | string | false | — | — | — | Sub-técnicas MITRE (coluna da tabela) | https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/securityalert |
| SystemAlertId | string | false | — | — | — | Unique identifier of this security alert instance | https://learn.microsoft.com/en-us/azure/defender-for-cloud/alerts-schemas |
| Tactics | string | false | — | — | — | Táticas MITRE (coluna da tabela) | https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/securityalert |
| Techniques | string | false | — | — | — | Técnicas MITRE (coluna da tabela) | https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/securityalert |
| TimeGenerated | datetime | false | — | ISO 8601 UTC (tipo `datetime`) | — | UTC timestamp on which the assessment took place (Security Center's scan time) (identical to DiscoveredTimeUTC) | https://learn.microsoft.com/en-us/azure/defender-for-cloud/alerts-schemas |
| Type | string | false | — | — | constant `SecurityAlert` | constant ('SecurityAlert') | https://learn.microsoft.com/en-us/azure/defender-for-cloud/alerts-schemas |
| VendorName | string | false | — | — | e.g. `Microsoft` | The name of the vendor that provided the alert | https://learn.microsoft.com/en-us/azure/defender-for-cloud/alerts-schemas |
| VendorOriginalId | string | false | — | — | — | unused | https://learn.microsoft.com/en-us/azure/defender-for-cloud/alerts-schemas |
| WorkspaceResourceGroup | string | false | — | — | — | in case the alert is generated on a VM/server/VMSS/App Service instance that reports to a workspace, contains that workspace resource group name | https://learn.microsoft.com/en-us/azure/defender-for-cloud/alerts-schemas |
| WorkspaceSubscriptionId | string | false | — | — | — | in case the alert is generated on a VM/server/VMSS/App Service instance that reports to a workspace, contains that workspace subscriptionId | https://learn.microsoft.com/en-us/azure/defender-for-cloud/alerts-schemas |

**Campos documentados na tabela de negócio mas cujo tipo não é afirmado por nenhuma página oficial**: `Severity`, `SourceSystem`, `TenantId`. Ver §4.

### 3.2 Tabela `SecurityRecommendation` — payload de avaliações/recomendações

Fonte da lista de colunas e tipos: <https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/securityrecommendation>

| Campo | Tipo | Obrigatório | Unidade | Formato data/hora | Valores permitidos | Descrição | Fonte |
|---|---|---|---|---|---|---|---|
| AssessedResourceId | string | false | — | — | — | Recurso avaliado (coluna da tabela) | https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/securityrecommendation |
| _BilledSize | real | false | bytes | — | — | The record size in bytes | https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/securityrecommendation |
| Description | string | false | — | — | — | Descrição (coluna da tabela) | https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/securityrecommendation |
| DeviceId | string | false | — | — | — | Identificador do dispositivo (coluna da tabela) | https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/securityrecommendation |
| DiscoveredTimeUTC | datetime | false | — | ISO 8601 UTC (tipo `datetime`) | — | Instante de descoberta (coluna da tabela) | https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/securityrecommendation |
| Environment | string | false | — | — | — | Ambiente (coluna da tabela) | https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/securityrecommendation |
| FirstEvaluationDate | datetime | false | — | ISO 8601 UTC (tipo `datetime`) | — | Data da primeira avaliação (coluna da tabela) | https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/securityrecommendation |
| _IsBillable | string | false | — | — | `true` / `false` | Specifies whether ingesting the data is billable | https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/securityrecommendation |
| IsSnapshot | bool | false | — | — | `true` / `false` | "To identify snapshot data, look for the field **IsSnapshot**." | https://learn.microsoft.com/en-us/azure/defender-for-cloud/continuous-export |
| PolicyDefinitionId | string | false | — | — | — | Id da definição de política (coluna da tabela) | https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/securityrecommendation |
| Properties | dynamic | false | — | — | — | Propriedades dinâmicas (coluna da tabela) | https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/securityrecommendation |
| ProviderName | string | false | — | — | — | Nome do fornecedor (coluna da tabela) | https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/securityrecommendation |
| RecommendationAdditionalData | dynamic | false | — | — | — | Dados adicionais da recomendação (coluna da tabela) | https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/securityrecommendation |
| RecommendationDisplayName | string | false | — | — | — | Nome de apresentação da recomendação (coluna da tabela) | https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/securityrecommendation |
| RecommendationId | string | false | — | — | — | Id da recomendação (coluna da tabela) | https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/securityrecommendation |
| RecommendationName | string | false | — | — | — | Nome da recomendação (coluna da tabela) | https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/securityrecommendation |
| RecommendationSeverity | string | false | — | — | — | Severidade da recomendação (coluna da tabela) | https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/securityrecommendation |
| RecommendationState | string | false | — | — | — | Estado da recomendação (coluna da tabela) | https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/securityrecommendation |
| ResolvedTimeUTC | datetime | false | — | ISO 8601 UTC (tipo `datetime`) | — | Instante de resolução (coluna da tabela) | https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/securityrecommendation |
| ResourceRegion | string | false | — | — | — | Região do recurso (coluna da tabela) | https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/securityrecommendation |
| StatusChangeDate | datetime | false | — | ISO 8601 UTC (tipo `datetime`) | — | Data de mudança de estado (coluna da tabela) | https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/securityrecommendation |
| TimeGenerated | datetime | false | — | ISO 8601 UTC (tipo `datetime`) | — | Instante de geração do registo (coluna da tabela) | https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/securityrecommendation |
| Type | string | false | — | — | — | The name of the table | https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/securityrecommendation |

### 3.3 Campos do **recurso de configuração** de exportação (não são registos exportados)

Estes campos descrevem o recurso `Microsoft.Security/automations` (a configuração), e são o que determina *o que* é exportado. Documentados em
<https://learn.microsoft.com/en-us/rest/api/defenderforcloud-composite/automations/get?view=rest-defenderforcloud-composite-latest&tabs=HTTP>:

| Campo | Tipo | Obrigatório | Unidade | Formato data/hora | Valores permitidos | Descrição | Fonte |
|---|---|---|---|---|---|---|---|
| etag | string | false | — | — | — | Entity tag is used for comparing two or more entities from the same requested resource | https://learn.microsoft.com/en-us/rest/api/defenderforcloud-composite/automations/get |
| id | string (arm-id) | false | — | — | — | Fully qualified resource ID for the resource | https://learn.microsoft.com/en-us/rest/api/defenderforcloud-composite/automations/get |
| kind | string | false | — | — | — | Kind of the resource | https://learn.microsoft.com/en-us/rest/api/defenderforcloud-composite/automations/get |
| location | string | false | — | — | — | The geo-location where the resource lives | https://learn.microsoft.com/en-us/rest/api/defenderforcloud-composite/automations/get |
| name | string | false | — | — | — | The name of the resource | https://learn.microsoft.com/en-us/rest/api/defenderforcloud-composite/automations/get |
| properties.actions | AutomationAction[] | false | — | — | AutomationActionEventHub / AutomationActionLogicApp / AutomationActionWorkspace | A collection of the actions which are triggered if all the configured rules evaluations, within at least one rule set, are true | https://learn.microsoft.com/en-us/rest/api/defenderforcloud-composite/automations/get |
| properties.actions[].actionType | string | false | — | — | `EventHub` / `LogicApp` / `Workspace` | The type of the action that will be triggered by the Automation | https://learn.microsoft.com/en-us/rest/api/defenderforcloud-composite/automations/get |
| properties.actions[].connectionString | string | false | — | — | — | The target Event Hub connection string (it will not be included in any response) | https://learn.microsoft.com/en-us/rest/api/defenderforcloud-composite/automations/get |
| properties.actions[].eventHubResourceId | string | false | — | — | — | The target Event Hub Azure Resource ID | https://learn.microsoft.com/en-us/rest/api/defenderforcloud-composite/automations/get |
| properties.actions[].isTrustedServiceEnabled | boolean | false | — | — | `true` / `false` | Indicates whether the trusted service is enabled or not | https://learn.microsoft.com/en-us/rest/api/defenderforcloud-composite/automations/get |
| properties.actions[].sasPolicyName | string | false | — | — | — | The target Event Hub SAS policy name | https://learn.microsoft.com/en-us/rest/api/defenderforcloud-composite/automations/get |
| properties.actions[].logicAppResourceId | string | false | — | — | — | The triggered Logic App Azure Resource ID | https://learn.microsoft.com/en-us/rest/api/defenderforcloud-composite/automations/get |
| properties.actions[].uri | string (uri) | false | — | — | — | The Logic App trigger URI endpoint (it will not be included in any response) | https://learn.microsoft.com/en-us/rest/api/defenderforcloud-composite/automations/get |
| properties.actions[].workspaceResourceId | string | false | — | — | — | The fully qualified Log Analytics Workspace Azure Resource ID | https://learn.microsoft.com/en-us/rest/api/defenderforcloud-composite/automations/get |
| properties.description | string | false | — | — | — | The security automation description | https://learn.microsoft.com/en-us/rest/api/defenderforcloud-composite/automations/get |
| properties.isEnabled | boolean | false | — | — | `true` / `false` | Indicates whether the security automation is enabled | https://learn.microsoft.com/en-us/rest/api/defenderforcloud-composite/automations/get |
| properties.scopes | AutomationScope[] | false | — | — | — | A collection of scopes on which the security automations logic is applied | https://learn.microsoft.com/en-us/rest/api/defenderforcloud-composite/automations/get |
| properties.scopes[].description | string | false | — | — | — | The resources scope description | https://learn.microsoft.com/en-us/rest/api/defenderforcloud-composite/automations/get |
| properties.scopes[].scopePath | string | false | — | — | — | The resources scope path. Can be the subscription or a resource group under that subscription (fully qualified Azure resource IDs) | https://learn.microsoft.com/en-us/rest/api/defenderforcloud-composite/automations/get |
| properties.sources | AutomationSource[] | false | — | — | — | A collection of the source event types which evaluate the security automation set of rules | https://learn.microsoft.com/en-us/rest/api/defenderforcloud-composite/automations/get |
| properties.sources[].eventSource | EventSource (enum) | false | — | — | `Assessments`, `AssessmentsSnapshot`, `SubAssessments`, `SubAssessmentsSnapshot`, `Alerts`, `SecureScores`, `SecureScoresSnapshot`, `SecureScoreControls`, `SecureScoreControlsSnapshot`, `RegulatoryComplianceAssessment`, `RegulatoryComplianceAssessmentSnapshot`, `AttackPaths`, `AttackPathsSnapshot` | A valid event source type | https://learn.microsoft.com/en-us/rest/api/defenderforcloud-composite/automations/get |
| properties.sources[].ruleSets | AutomationRuleSet[] | false | — | — | — | A set of rules which evaluate upon event interception. A logical disjunction is applied between defined rule sets (logical 'or') | https://learn.microsoft.com/en-us/rest/api/defenderforcloud-composite/automations/get |
| properties.sources[].ruleSets[].rules | AutomationTriggeringRule[] | false | — | — | — | A rule which is evaluated upon event interception | https://learn.microsoft.com/en-us/rest/api/defenderforcloud-composite/automations/get |
| properties.sources[].ruleSets[].rules[].expectedValue | string | false | — | — | — | The expected value | https://learn.microsoft.com/en-us/rest/api/defenderforcloud-composite/automations/get |
| properties.sources[].ruleSets[].rules[].operator | Operator (enum) | false | — | — | `Equals`, `GreaterThan`, `GreaterThanOrEqualTo`, `LesserThan`, `LesserThanOrEqualTo`, `NotEquals`, `Contains`, `StartsWith`, `EndsWith` | A valid comparer operator to use | https://learn.microsoft.com/en-us/rest/api/defenderforcloud-composite/automations/get |
| properties.sources[].ruleSets[].rules[].propertyJPath | string | false | — | — | — | The JPath of the entity model property that should be checked | https://learn.microsoft.com/en-us/rest/api/defenderforcloud-composite/automations/get |
| properties.sources[].ruleSets[].rules[].propertyType | PropertyType (enum) | false | — | — | `String`, `Integer`, `Number`, `Boolean` | The data type of the compared operands | https://learn.microsoft.com/en-us/rest/api/defenderforcloud-composite/automations/get |
| systemData.createdAt | string (date-time) | false | — | ISO 8601 date-time (UTC) | — | The timestamp of resource creation (UTC) | https://learn.microsoft.com/en-us/rest/api/defenderforcloud-composite/automations/get |
| systemData.createdBy | string | false | — | — | — | The identity that created the resource | https://learn.microsoft.com/en-us/rest/api/defenderforcloud-composite/automations/get |
| systemData.createdByType | createdByType (enum) | false | — | — | `User`, `Application`, `ManagedIdentity`, `Key` | The type of identity that created the resource | https://learn.microsoft.com/en-us/rest/api/defenderforcloud-composite/automations/get |
| systemData.lastModifiedAt | string (date-time) | false | — | ISO 8601 date-time (UTC) | — | The timestamp of resource last modification (UTC) | https://learn.microsoft.com/en-us/rest/api/defenderforcloud-composite/automations/get |
| systemData.lastModifiedBy | string | false | — | — | — | The identity that last modified the resource | https://learn.microsoft.com/en-us/rest/api/defenderforcloud-composite/automations/get |
| systemData.lastModifiedByType | createdByType (enum) | false | — | — | `User`, `Application`, `ManagedIdentity`, `Key` | The type of identity that last modified the resource | https://learn.microsoft.com/en-us/rest/api/defenderforcloud-composite/automations/get |
| tags | object | false | — | — | — | Resource tags | https://learn.microsoft.com/en-us/rest/api/defenderforcloud-composite/automations/get |
| type | string | false | — | — | — | The type of the resource | https://learn.microsoft.com/en-us/rest/api/defenderforcloud-composite/automations/get |

### 3.4 Campos do payload de *attack path* (consumido por API/Resource Graph)

O documento "Retrieve attack path data with API" descreve os campos do registo de attack path devolvido pela API do Azure Resource Graph (`securityresources`, tipo `microsoft.security/attackpaths`).
Fonte: <https://learn.microsoft.com/en-us/azure/defender-for-cloud/attack-path-api>

| Campo | Tipo | Obrigatório | Unidade | Formato data/hora | Valores permitidos | Descrição | Fonte |
|---|---|---|---|---|---|---|---|
| ID | string | false | — | — | — | The Azure resource ID of the attack path instance | https://learn.microsoft.com/en-us/azure/defender-for-cloud/attack-path-api |
| Name | string | false | — | — | — | The Unique identifier of the attack path instance | https://learn.microsoft.com/en-us/azure/defender-for-cloud/attack-path-api |
| Type | string | false | — | — | always equals `microsoft.security/attackpaths` | The Azure resource type | https://learn.microsoft.com/en-us/azure/defender-for-cloud/attack-path-api |
| Tenant ID | string | false | — | — | — | The tenant ID of the attack path instance | https://learn.microsoft.com/en-us/azure/defender-for-cloud/attack-path-api |
| Location | string | false | — | — | — | The location of the attack path | https://learn.microsoft.com/en-us/azure/defender-for-cloud/attack-path-api |
| Subscription ID | string | false | — | — | — | The subscription of the attack path | https://learn.microsoft.com/en-us/azure/defender-for-cloud/attack-path-api |
| Properties.description | string | false | — | — | — | The description of the attack path | https://learn.microsoft.com/en-us/azure/defender-for-cloud/attack-path-api |
| Properties.displayName | string | false | — | — | — | The display name of the attack path | https://learn.microsoft.com/en-us/azure/defender-for-cloud/attack-path-api |
| Properties.attackPathType | string | false | — | — | — | The type of the attack path | https://learn.microsoft.com/en-us/azure/defender-for-cloud/attack-path-api |
| Properties.manualRemediationSteps | string | false | — | — | — | Manual remediation steps of the attack path | https://learn.microsoft.com/en-us/azure/defender-for-cloud/attack-path-api |
| Properties.refreshInterval | string | false | — | — | — | The refresh interval of the attack path | https://learn.microsoft.com/en-us/azure/defender-for-cloud/attack-path-api |
| Properties.potentialImpact | string | false | — | — | — | The potential impact of the attack path being breached | https://learn.microsoft.com/en-us/azure/defender-for-cloud/attack-path-api |
| Properties.riskCategories | string | false | — | — | — | The categories of risk of the attack path | https://learn.microsoft.com/en-us/azure/defender-for-cloud/attack-path-api |
| Properties.entryPointEntityInternalID | string | false | — | — | — | The internal ID of the entry point entity of the attack path | https://learn.microsoft.com/en-us/azure/defender-for-cloud/attack-path-api |
| Properties.targetEntityInternalID | string | false | — | — | — | The internal ID of the target entity of the attack path | https://learn.microsoft.com/en-us/azure/defender-for-cloud/attack-path-api |
| Properties.assessments | object (mapping) | false | — | — | — | Mapping of entity internal ID to the security assessments on that entity | https://learn.microsoft.com/en-us/azure/defender-for-cloud/attack-path-api |
| Properties.graphComponent | array | false | — | — | — | List of graph components representing the attack path | https://learn.microsoft.com/en-us/azure/defender-for-cloud/attack-path-api |
| Properties.graphComponent.insights | array | false | — | — | — | List of insights graph components related to the attack path | https://learn.microsoft.com/en-us/azure/defender-for-cloud/attack-path-api |
| Properties.graphComponent.entities | array | false | — | — | — | List of entities graph components related to the attack path | https://learn.microsoft.com/en-us/azure/defender-for-cloud/attack-path-api |
| Properties.graphComponent.connections | array | false | — | — | — | List of connections graph components related to the attack path | https://learn.microsoft.com/en-us/azure/defender-for-cloud/attack-path-api |
| Properties.AttackPathID | string | false | — | — | — | The unique identifier of the attack path instance | https://learn.microsoft.com/en-us/azure/defender-for-cloud/attack-path-api |

## 4. Campos não comprovados

Marcados `UNVERIFIED`. **Não devem ser gerados.**

### 4.0 Nota sobre `sets` e `evidence` no `.schema.json` (contrato atualizado)

O `.schema.json` está organizado em `sets`, um por estrutura documentada, porque os **nomes de campo colidem entre elas**. O mesmo nome em sets diferentes é legítimo e é exatamente o que a documentação descreve.

**Veredito de gerabilidade: 93 de 114 colunas são geráveis.**

**Justificação (uma frase):** as 93 geráveis são as três estruturas cuja documentação oficial **anuncia explicitamente o tipo de cada campo** — as tabelas `SecurityAlert` e `SecurityRecommendation` da referência do Azure Monitor (tabela de colunas com coluna "Type") e o recurso `Microsoft.Security/automations` da referência REST (anotação de tipo por campo) — enquanto as 21 colunas de `securityresources/microsoft.security/attackpaths` descrevem o **significado** de cada campo sem publicar o tipo, ficando com `type: null` e **não geráveis**.

| set | estrutura | `evidence` | Gerável? |
|---|---|---|---|
| `SecurityAlert` (35) | tabela do Log Analytics | `declared` | **35 sim** — a referência do Azure Monitor publica a tabela de colunas **com tipos** |
| `SecurityRecommendation` (23) | tabela do Log Analytics | `declared` | **23 sim** — idem |
| `Microsoft.Security/automations` (35) | recurso de configuração de exportação | `declared` | **35 sim** — a referência REST anota o tipo de cada campo (`string`, `boolean`, enum `EventSource`, …) |
| `securityresources/microsoft.security/attackpaths` (21) | registos devolvidos pela API do Resource Graph | 21 `author-classification` | **0** — a página "Retrieve attack path data with API" dá o **significado** de cada campo mas **não afirma o tipo**; o tipo foi classificado por nós, logo `type: null` |


| Campo | Estado | Motivo |
|---|---|---|
| `Severity` | UNVERIFIED | Aparece na tabela de *data model* de <https://learn.microsoft.com/en-us/azure/defender-for-cloud/alerts-schemas> com a descrição "The alert severity (High/Medium/Low/Informational)", mas **não consta** da lista de colunas de `SecurityAlert` em <https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/securityalert> (que lista `AlertSeverity`). As duas fontes oficiais divergem quanto ao nome e o tipo não é afirmado. Não inventar correspondência. |
| `SourceSystem` | UNVERIFIED | Listado no *data model* de <https://learn.microsoft.com/en-us/azure/defender-for-cloud/alerts-schemas> como "unused", sem tipo. Ausente da lista de colunas de `SecurityAlert`. |
| `TenantId` | UNVERIFIED | Listado no *data model* de <https://learn.microsoft.com/en-us/azure/defender-for-cloud/alerts-schemas> ("the identifier of the parent Microsoft Entra ID tenant…"), sem tipo, e ausente da lista de colunas de `SecurityAlert`. |
| `DiscoveredTimeUTC` (tabela `SecurityAlert`) | UNVERIFIED | O documento de alertas afirma que `TimeGenerated` é "identical to DiscoveredTimeUTC", mas `DiscoveredTimeUTC` não consta da lista de colunas de `SecurityAlert` (consta de `SecurityRecommendation`). |
| Esquema de `SecureScores` / `SecureScoresSnapshot` | UNVERIFIED | O tipo existe no enum `EventSource` (<https://learn.microsoft.com/en-us/rest/api/defenderforcloud-composite/automations/get>) mas **nenhuma página oficial consultada publica o esquema de campo** dos registos de secure score exportados. |
| Esquema de `SecureScoreControls` / `SecureScoreControlsSnapshot` | UNVERIFIED | idem — tipo confirmado, esquema de campos não publicado nas páginas consultadas. |
| Esquema de `RegulatoryComplianceAssessment` / `…Snapshot` | UNVERIFIED | idem — tipo confirmado, esquema de campos não publicado nas páginas consultadas. |
| Esquema de `SubAssessments` / `SubAssessmentsSnapshot` | UNVERIFIED | idem — tipo confirmado, esquema de campos não publicado nas páginas consultadas. `SecurityRecommendation` **não** é documentada como tabela de destino de sub-assessments; não inferir. |
| Esquema de `AttackPaths` / `AttackPathsSnapshot` **no destino Log Analytics/Event Hub** | UNVERIFIED | O esquema publicado em <https://learn.microsoft.com/en-us/azure/defender-for-cloud/attack-path-api> é o da **API do Azure Resource Graph**, não o do evento de exportação contínua. Não há página oficial consultada que publique o payload de exportação de attack paths. |
| Payload/schema do Event Hub (envelope de mensagem, headers, `properties`, partição) | UNVERIFIED | Os documentos consultados afirmam apenas que o formato é JSON ("Defender for Cloud sends data in JavaScript Object Notation (JSON) format") — <https://learn.microsoft.com/en-us/azure/defender-for-cloud/continuous-export-view-data>. Nenhum envelope, header ou esquema de mensagem é publicado. |
| `aka.ms/ASCAutomationSchemas` | UNVERIFIED (não recuperável) | <https://learn.microsoft.com/en-us/azure/defender-for-cloud/benefits-of-continuous-export> aponta para <https://aka.ms/ASCAutomationSchemas> como "Log Analytics table schemas" / "the event schemas of the exported data types". O link resolve para um domínio **github.com**; a recuperação automática falhou ("cross-origin redirect to https://github.com is not followed automatically"). As tentativas de localizar a pasta correspondente no GitHub devolveram 404. **O conteúdo desse repositório não foi lido e por isso não é citado como fonte de nenhum campo.** |

## 5. Divergências conhecidas

1. **Storage não é destino.** A exportação contínua documentada entrega a **Log Analytics, Event Hubs ou Logic Apps**. Não existe caminho/particionamento de blob documentado para esta superfície. Qualquer simulador que escreva estes registos para um contentor de Storage está a inventar um mecanismo que a Microsoft não documenta como continuous export.
2. **Nome do campo de severidade do alerta.** O *data model* usa `Severity`; a referência da tabela do Log Analytics usa `AlertSeverity`. Registado como divergência — não escolher por conta própria (ver §4).
3. **`ProductName` constante.** O *data model* afirma o valor constante `'Azure Security Center'` (nome legado), embora o produto se chame Microsoft Defender for Cloud. Manter o valor documentado.
4. **`ProviderName`, `SourceSystem`, `VendorOriginalId` marcados "unused"** na própria documentação, mas presentes (ou referidos) no modelo. Não gerar como dados significativos.
5. **CSV pontual vs. exportação contínua.** Existe uma exportação **manual** para CSV ("Download CSV report", <https://learn.microsoft.com/en-us/azure/defender-for-cloud/export-alerts-to-csv>) limitada a 25 000 linhas (limite de tamanho de ficheiro) para alertas e recomendações. **O formato das colunas desse CSV não é publicado** por nenhuma página oficial consultada — não confundir com a exportação contínua e não inventar o cabeçalho.
