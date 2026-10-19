# `security-command-center-findings-bigquery` — Security Command Center findings → BigQuery

## 1. Identificação

- **Nome oficial da superfície:** Security Command Center (SCC) — export de
  findings para BigQuery, nas duas modalidades oficiais:
  1. **Continuous export** / "Stream findings to BigQuery for analysis"
     (recomendada pela Google);
  2. **Bulk export** / "Bulk export findings to BigQuery" (snapshot sob demanda).
- **Documentos oficiais e datas de consulta (2026-10-14):**

| Documento | URL | Consultado em |
|---|---|---|
| "Stream findings to BigQuery for analysis" (continuous export; **tabela `findings`**) | <https://cloud.google.com/security-command-center/docs/how-to-analyze-findings-in-big-query> | 2026-10-14 |
| "Bulk export findings to BigQuery" (**tabela `findings`**, mesma estrutura) | <https://cloud.google.com/security-command-center/docs/bulk-exports-to-big-query> | 2026-10-14 |
| REST Resource: `organizations.sources.findings` (**objeto `Finding`** — campos aninhados) | <https://cloud.google.com/security-command-center/docs/reference/rest/v1/organizations.sources.findings> | 2026-10-14 |
| REST Resource: `organizations.sources.findings` (v2, `Finding` reduzido) | <https://cloud.google.com/security-command-center/docs/reference/rest/v2/organizations.sources.findings> | 2026-10-14 |

- **Versão/schema de referência:** Security Command Center API **v1**
  (a página v1 documenta o objeto `Finding` completo, com 68 campos de topo).

### 1.1 O mecanismo de export existe — confirmado

| Afirmação | Fonte |
|---|---|
| "BigQuery is Google Cloud's fully managed, petabyte-scale [...] To learn more about BigQuery, see the BigQuery documentation." + "findings that are written to Security Command Center are exported to a BigQuery table in near real time" | <https://cloud.google.com/security-command-center/docs/how-to-analyze-findings-in-big-query> |
| "This feature is the recommended way to export Security Command Center findings to BigQuery, because it's fully managed and doesn't require performing manual operations or writing custom code." | <https://cloud.google.com/security-command-center/docs/how-to-analyze-findings-in-big-query> |
| Bulk: "This feature delivers a snapshot of findings up to a certain point in time. This feature complements the continuous BigQuery export" | <https://cloud.google.com/security-command-center/docs/bulk-exports-to-big-query> |
| Níveis de ativação | "You can enable this feature at the organization, folder, and project levels" (continuous) | <https://cloud.google.com/security-command-center/docs/how-to-analyze-findings-in-big-query> |

## 2. Mecanismo e entrega

| Item | Valor documentado | Fonte |
|---|---|---|
| Destino | Tabela BigQuery chamada **`findings`** ("Each dataset contains a `findings` table, which has the following fields") | <https://cloud.google.com/security-command-center/docs/how-to-analyze-findings-in-big-query> e <https://cloud.google.com/security-command-center/docs/bulk-exports-to-big-query> |
| Dataset | Criado pelo usuário: "Create a BigQuery dataset. For more information, see Creating datasets." | <https://cloud.google.com/security-command-center/docs/how-to-analyze-findings-in-big-query> |
| Clustering | "which is **clustered by** `source_id`, `finding_id`, and `event_time`" | <https://cloud.google.com/security-command-center/docs/how-to-analyze-findings-in-big-query> |
| Semântica das linhas | "This feature adds each new finding and its subsequent updates as **new rows** in the `findings` table [...] This creates multiple finding records with the same `source_id` and `finding_id` values, but with different `event_time` values." | <https://cloud.google.com/security-command-center/docs/how-to-analyze-findings-in-big-query> |
| Duplicados | "Note that duplicate entries might exist in your dataset. To parse them out, you can use the `DISTINCT` clause" | <https://cloud.google.com/security-command-center/docs/how-to-analyze-findings-in-big-query> |
| Bulk export — comando | `gcloud scc findings export-to-bigquery PARENT --dataset=DATASET_NAME [--location=LOCATION; default="global"]` | <https://cloud.google.com/security-command-center/docs/bulk-exports-to-big-query> |
| Bulk export — formato de `PARENT` | `organizations/ORGANIZATION_ID`, `projects/PROJECT_ID`, `folders/FOLDER_ID` | <https://cloud.google.com/security-command-center/docs/bulk-exports-to-big-query> |
| Bulk export — formato de `DATASET_NAME` | `projects/PROJECT_ID/datasets/DATASET_ID` | <https://cloud.google.com/security-command-center/docs/bulk-exports-to-big-query> |
| Bulk export — assíncrono | "This command returns a long-running operation object that contains a `name` string" ; status por `gcloud scc operations describe LONG_RUNNING_OPERATION_NAME --organization=ORGANIZATION_ID` | <https://cloud.google.com/security-command-center/docs/bulk-exports-to-big-query> |
| Bulk export — limite de concorrência | "Only three concurrent bulk exports are allowed at any given time for a single organization." | <https://cloud.google.com/security-command-center/docs/bulk-exports-to-big-query> |
| Bulk export — não sobrescreve | "newer findings within the export are **appended** to the BigQuery `findings` table. Findings are not overwritten." | <https://cloud.google.com/security-command-center/docs/bulk-exports-to-big-query> |
| Expiração da tabela | "You must enable billing [...] and set the BigQuery table to **never expire**. Otherwise, the default table expiration is set to 60 days" | <https://cloud.google.com/security-command-center/docs/bulk-exports-to-big-query> |
| Formato de arquivo (Parquet/CSV/NDJSON), compressão, delimitador, cabeçalho, caminho de bucket | **Não documentado** — a entrega é em tabela BigQuery, não em arquivo. Ver secção 5. | — |
| Manifesto | **Não documentado.** Existe o objeto de operação de longa duração (`done: true`, código de erro) | <https://cloud.google.com/security-command-center/docs/bulk-exports-to-big-query> |

## 3. Campos

### 3.1 Tabela `findings` — campos de topo (documentados na página de export)

Fonte base: `https://cloud.google.com/security-command-center/docs/how-to-analyze-findings-in-big-query#dataset_structure`
e `https://cloud.google.com/security-command-center/docs/bulk-exports-to-big-query#dataset_structure`
(consulta **2026-10-14**). As duas páginas listam exatamente os mesmos seis
campos.

| Campo | Tipo | Obrigatório | Unidade | Formato data/hora | Valores permitidos | Descrição | Fonte |
|---|---|---|---|---|---|---|---|
| `source_id` | não declarado | sim (coluna de clustering) | — | — | — | "A unique identifier that Security Command Center assigns to the source of a finding. For example, all findings from the Cloud Anomaly Detection source have the same `source_id` value. Example: `1234567890`" | `#dataset_structure` |
| `finding_id` | não declarado | sim (coluna de clustering) | — | — | alfanumérico, ≤ 32 caracteres | "Unique identifier that represents the finding. It is unique within a source for an organization." | `#dataset_structure` |
| `event_time` | não declarado | sim (coluna de clustering) | — | conforme exemplo oficial: `2019-09-26 12:48:00.985000 UTC` | — | "The time that the event took place or the time that an update to the finding occurred. [...]" | `#dataset_structure` |
| `bulk_export_id` | não declarado | não | — | — | UUID (bulk) / vazio (continuous) | "For bulk exports, this is a UUID. For continuous exports, this field is empty." | `#dataset_structure` |
| `finding` | não declarado (RECORD aninhado — ver 5) | sim | — | — | — | "A record of assessment data like security, risk, health, or privacy, that is ingested into Security Command Center [...] For more information about the nested fields, see the API reference for the **`Finding`** object." | `#dataset_structure` |
| `resource` | não declarado | não | — | — | — | "Information related to the Google Cloud resource that is associated with this finding. For more information about the nested fields, see the API reference for the **`Resource`** object." | `#dataset_structure` |

> **Nota de fidelidade:** a página de export **não declara os tipos BigQuery**
> destas colunas (STRING/RECORD/TIMESTAMP/etc.). A coluna "Tipo" fica
> `não declarado` de propósito. Ver secção 5.

### 3.2 Objeto `Finding` — 68 campos de topo

A página de export remete explicitamente para o objeto `Finding` da API. Os
nomes abaixo são transcritos **verbatim** da secção *Resource: Finding* de
<https://cloud.google.com/security-command-center/docs/reference/rest/v1/organizations.sources.findings#Finding>
(consulta **2026-10-14**); o fragmento de cada linha é o nome do campo.

No export, estes campos ficam **aninhados sob a coluna `finding`** (ex.:
`finding.name`, `finding.category`, ...). O aninhamento é afirmado pela própria
página de export ("For more information about the nested fields, see the API
reference for the Finding object").

| Campo | Tipo documentado | Obrigatório | Descrição (resumida) | Fonte |
|---|---|---|---|---|
| `name` | string | não | "The relative resource name of the finding. Example: `organizations/{organizationId}/sources/{sourceId}/findings/{findingId}`" | `#Finding` |
| `parent` | string | não | "The relative resource name of the source the finding belongs to." | `#Finding` |
| `resourceName` | string | não | "For findings on Google Cloud resources, the full resource name of the Google Cloud resource this finding is for." | `#Finding` |
| `state` | enum (State) | não | "The state of the finding." | `#Finding` |
| `category` | string | não | "The additional taxonomy group within findings from a given source. This field is immutable after creation time." | `#Finding` |
| `externalUri` | string | não | "The URI that, if available, points to a web page outside of Security Command Center where additional information about the finding can be found." | `#Finding` |
| `sourceProperties` | map (key: string, value: value (Value format)) | não | "Source specific properties. These properties are managed by the source that writes the finding." | `#Finding` |
| `securityMarks` | object (SecurityMarks) | não (Output only) | "User specified security marks. These marks are entirely managed by the user [...]" | `#Finding` |
| `eventTime` | string (Timestamp format) | não | "The time the finding was first detected. If an existing finding is updated, then this is the time the update occurred." | `#Finding` |
| `createTime` | string (Timestamp format) | não | "The time at which the finding was created in Security Command Center." | `#Finding` |
| `severity` | enum (Severity) | não | "The severity of the finding. This field is managed by the source that writes the finding." | `#Finding` |
| `canonicalName` | string | não | "The canonical name of the finding." | `#Finding` |
| `mute` | enum (Mute) | não | "Indicates the mute state of a finding (either muted, unmuted or undefined)." | `#Finding` |
| `findingClass` | enum (FindingClass) | não | "The class of the finding." | `#Finding` |
| `indicator` | object (Indicator) | não | "Represents what's commonly known as an indicator of compromise (IoC) in computer forensics." | `#Finding` |
| `vulnerability` | object (Vulnerability) | não | "Represents vulnerability-specific fields like CVE and CVSS scores." | `#Finding` |
| `muteUpdateTime` | string (Timestamp format) | não (Output only) | "The most recent time this finding was muted or unmuted." | `#Finding` |
| `externalSystems` | map (key: string, value: object (ExternalSystem)) | não (Output only) | "Third party SIEM/SOAR fields within SCC, contains external system information and external system finding fields." | `#Finding` |
| `mitreAttack` | object (MitreAttack) | não | "MITRE ATT&CK tactics and techniques related to this finding." | `#Finding` |
| `access` | object (Access) | não | "Access details associated with the finding, such as more information on the caller, which method was accessed, and from where." | `#Finding` |
| `connections[]` | object (Connection) | não | "Contains information about the IP connection associated with the finding." | `#Finding` |
| `muteInitiator` | string | não | "Records additional information about the mute operation, for example, the mute configuration that muted the finding [...]" | `#Finding` |
| `muteInfo` | object (MuteInfo) | não (Output only) | "The mute information regarding this finding." | `#Finding` |
| `processes[]` | object (Process) | não | "Represents operating system processes associated with the Finding." | `#Finding` |
| `contacts` | map (key: string, value: object (ContactDetails)) | não (Output only) | "Map containing the points of contact for the given finding. The key represents the type of contact [...]" | `#Finding` |
| `compliances[]` | object (Compliance) | não | "Contains compliance information for security standards associated to the finding." | `#Finding` |
| `parentDisplayName` | string | não (Output only) | "The human readable display name of the finding source such as "Event Threat Detection" or "Security Health Analytics"." | `#Finding` |
| `description` | string | não | "Contains more details about the finding." | `#Finding` |
| `exfiltration` | object (Exfiltration) | não | "Represents exfiltrations associated with the finding." | `#Finding` |
| `iamBindings[]` | object (IamBinding) | não | "Represents IAM bindings associated with the finding." | `#Finding` |
| `nextSteps` | string | não | "Steps to address the finding." | `#Finding` |
| `moduleName` | string | não | "Unique identifier of the module which generated the finding." | `#Finding` |
| `containers[]` | object (Container) | não | "Containers associated with the finding. This field provides information for both Kubernetes and non-Kubernetes containers." | `#Finding` |
| `kubernetes` | object (Kubernetes) | não | "Kubernetes resources associated with the finding." | `#Finding` |
| `database` | object (Database) | não | "Database associated with the finding." | `#Finding` |
| `attackExposure` | object (AttackExposure) | não | "The results of an attack path simulation relevant to this finding." | `#Finding` |
| `files[]` | object (File) | não | "File associated with the finding." | `#Finding` |
| `cloudDlpInspection` | object (CloudDlpInspection) | não | "Cloud Data Loss Prevention (Cloud DLP) inspection results that are associated with the finding." | `#Finding` |
| `cloudDlpDataProfile` | object (CloudDlpDataProfile) | não | "Cloud DLP data profile that is associated with the finding." | `#Finding` |
| `kernelRootkit` | object (KernelRootkit) | não | "Signature of the kernel rootkit." | `#Finding` |
| `orgPolicies[]` | object (OrgPolicy) | não | "Contains information about the org policies associated with the finding." | `#Finding` |
| `job` | object (Job) | não | "Job associated with the finding." | `#Finding` |
| `application` | object (Application) | não | "Represents an application associated with the finding." | `#Finding` |
| `ipRules` | object (IpRules) | não | "IP rules associated with the finding." | `#Finding` |
| `backupDisasterRecovery` | object (BackupDisasterRecovery) | não | "Fields related to Backup and DR findings." | `#Finding` |
| `securityPosture` | object (SecurityPosture) | não | "The security posture associated with the finding." | `#Finding` |
| `logEntries[]` | object (LogEntry) | não | "Log entries that are relevant to the finding." | `#Finding` |
| `loadBalancers[]` | object (LoadBalancer) | não | "The load balancers associated with the finding." | `#Finding` |
| `cloudArmor` | object (CloudArmor) | não | "Fields related to Cloud Armor findings." | `#Finding` |
| `notebook` | object (Notebook) | não | "Notebook associated with the finding." | `#Finding` |
| `toxicCombination` | object (ToxicCombination) | não | "Contains details about a group of security issues that, when the issues occur together, represent a greater risk [...]" | `#Finding` |
| `groupMemberships[]` | object (GroupMembership) | não | "Contains details about groups of which this finding is a member." | `#Finding` |
| `disk` | object (Disk) | não | "Disk associated with the finding." | `#Finding` |
| `dataAccessEvents[]` | object (DataAccessEvent) | não | "Data access events associated with the finding." | `#Finding` |
| `dataFlowEvents[]` | object (DataFlowEvent) | não | "Data flow events associated with the finding." | `#Finding` |
| `networks[]` | object (Network) | não | "Represents the VPC networks that the resource is attached to." | `#Finding` |
| `dataRetentionDeletionEvents[]` | object (DataRetentionDeletionEvent) | não | "Data retention deletion events associated with the finding." | `#Finding` |
| `affectedResources` | object (AffectedResources) | não | "AffectedResources associated with the finding." | `#Finding` |
| `aiModel` | object (AiModel) | não | "The AI model associated with the finding." | `#Finding` |
| `chokepoint` | object (Chokepoint) | não | "Contains details about a chokepoint, which is a resource or resource group where high-risk attack paths converge [...]" | `#Finding` |
| `complianceDetails` | object (ComplianceDetails) | não | "Details about the compliance implications of the finding." | `#Finding` |
| `vertexAi` | object (VertexAi) | não | "VertexAi associated with the finding." | `#Finding` |
| `artifactGuardPolicies` | object (ArtifactGuardPolicies) | não | "ArtifactGuardPolicies associated with the finding." | `#Finding` |
| `secret` | object (Secret) | não | "Secret associated with the finding." | `#Finding` |
| `externalExposure` | object (ExternalExposure) | não | "External exposure associated with the finding." | `#Finding` |
| `policyViolationSummary` | object (PolicyViolationSummary) | não | "PolicyViolationSummary associated with the finding." | `#Finding` |
| `agentDataAccessEvents[]` | object (AgentDataAccessEvent) | não | "Agent data access events associated with the finding." | `#Finding` |
| `discoveredWorkload` | object (DiscoveredWorkload) | não | "DiscoveredWorkload associated with the finding." | `#Finding` |

**Total: 68 campos de topo do objeto `Finding` + 6 colunas da tabela = 74
entradas de campo nesta superfície.**

## 4. Campos não comprovados

| Item | Estado | Motivo |
|---|---|---|
| Tipos BigQuery das 6 colunas da tabela `findings` | UNVERIFIED | Nem a página de continuous export nem a de bulk export declaram os tipos (`STRING`, `RECORD`, `TIMESTAMP`, ...). A documentação só dá nomes e descrições. |
| Estrutura do campo `resource` da tabela `findings` | UNVERIFIED | A página de export diz "see the API reference for the **Resource** object", mas as páginas de referência REST do SCC para esse objeto não existem nos caminhos testados: `.../rest/v1/Resource` → HTTP 404; `.../rest/v1/Asset` → HTTP 404; `.../rest/v1/organizations.assets` → HTTP 404. Sem página, nenhum campo é gerado. |
| Relação exata entre a coluna `resource` e os campos `finding.resourceName` / `SecurityCenterProperties` | UNVERIFIED | Nenhuma página oficial obtida afirma essa relação. |
| Campos aninhados de todos os 60+ sub-objetos de `Finding` (`indicator.*`, `vulnerability.*`, `access.*`, `compliance.*`, `mitreAttack.*`, ...) | UNVERIFIED | A página v1 documenta cada sub-objeto em secções próprias, mas esses não foram transcritos nesta passagem. Estão confirmados como **existentes** (o tipo aparece na tabela da secção 3.2), mas os seus campos internos não entram nesta spec. |
| Constantes das enumerações (`State`, `Severity`, `Mute`, `FindingClass`) | UNVERIFIED | A página v1 lista as enumerações em secções separadas (`#State`, `#Severity`, ...) que não foram transcritas nesta passagem. Não gerar valores sem leitura direta. |
| Formato de arquivo, compressão, encoding, delimitador, cabeçalho, caminho de bucket/partição, manifesto | UNVERIFIED | A entrega é em tabela BigQuery; a documentação não descreve nenhum arquivo intermediário nem manifesto. |
| Localização/nome do dataset | UNVERIFIED | O dataset é criado pelo usuário; a documentação não fixa nome nem região. |
| Diferenças entre a versão v1 e v2 do objeto `Finding` no que é exportado | UNVERIFIED | A documentação de export não indica qual versão de API alimenta a tabela BigQuery. A v2 obtida documenta um `Finding` reduzido (ex.: `resourceName` ainda presente), mas a página de export não a cita. Registrado, sem escolha unilateral. |

## 5. Divergências conhecidas

- **Uma tabela, dois mecanismos:** bulk e continuous escrevem na **mesma**
  tabela `findings` com clustering idêntico. A documentação de bulk alerta que
  usar ambos no mesmo dataset pode "result in duplicated or missing findings".
  O campo `bulk_export_id` é o único discriminador documentado (UUID no bulk;
  vazio no continuous).
- **`event_time` tem dois significados documentados:** "The time that the event
  took place **or** the time that an update to the finding occurred". Ambas as
  leituras são oficiais; não escolher uma.
- **Exemplo de formato de `event_time`:** a página mostra
  `2019-09-26 12:48:00.985000 UTC` — ou seja, o exemplo oficial **não** está em
  RFC 3339 com `T` e `Z`. Registrado literalmente; ver secção 4 quanto ao tipo.
