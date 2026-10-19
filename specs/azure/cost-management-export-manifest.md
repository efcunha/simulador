# Azure — Cost Management export: entrega em Blob Storage e arquivo de manifesto

## 1. Identificação

| Item | Valor |
|---|---|
| Nome oficial da superfície | **Microsoft Cost Management export — delivery to Azure Blob Storage e `_manifest.json`** |
| Documento oficial (entrega + exemplo de manifesto) | "Tutorial: Create and manage Cost Management exports" — https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-improved-exports — consultado em **2026-10-14** |
| Documento oficial (propriedade que cria o manifesto) | "Exports - Create Or Update" (REST API, api-version 2025-03-01), propriedade `properties.partitionData` — https://learn.microsoft.com/en-us/rest/api/cost-management/exports/create-or-update?view=rest-cost-management-2025-03-01&tabs=HTTP — consultado em **2026-10-14** |
| Documento oficial (localização do manifesto na run history) | "Exports - Get Execution History" (REST API, api-version 2025-03-01), propriedade `manifestFile` — https://learn.microsoft.com/en-us/rest/api/cost-management/exports/get-execution-history?view=rest-cost-management-2025-03-01 — consultado em **2026-10-14** |
| Versão/schema de referência | O manifesto **não** tem versão de schema própria publicada; o exemplo oficial traz `"manifestVersion": "2024-04-01"` |

### 1.1 Resposta direta: a Microsoft publica um schema formal do manifesto?

**NÃO.** A Microsoft **não publica um schema formal (JSON Schema, OpenAPI model ou tabela de campos)
para o arquivo `_manifest.json`.** O que existe oficialmente, e tudo o que esta spec usa, é:

1. a **declaração** de que cada run de export produz um `manifest.json` junto das partições, com
   "a summary of the full dataset and information for each file partition in it";
2. **um exemplo completo de `_manifest.json`** no tutorial (reproduzido literalmente em §3.1);
3. a propriedade REST `partitionData`, documentada como: *"If set to true, exported data will be
   partitioned by size and placed in a blob directory together with a manifest file."*;
4. a propriedade REST `manifestFile` na run history, descrita como *"The manifest file
   location(URI location) for the exported files."*

Portanto: **os nomes de campo do manifesto listados em §4 estão documentados apenas por exemplo
oficial e por inferência da estrutura de configuração do export** — não por uma definição
normativa de schema. Cada linha está marcada com seu nível de comprovação e nenhum campo foi
inventado. Campos cuja existência só se sustenta no exemplo estão marcados
`UNVERIFIED` em §5 e **não devem ser gerados** cegamente.

## 2. Mecanismo e entrega

### 2.1 Layout de container/caminho

Citação literal da documentação:

> The exported files are organized in a structured hierarchy within the storage folders.
> `StorageContainer/StorageDirectory/ExportName/[YYYYMMDD-YYYYMMDD]/[RunID]/`
> This path contains the CSV files and a manifest file.

| Elemento | Definição documentada | Quem nomeia |
|---|---|---|
| `StorageContainer` | Container do Azure Storage account configurado como destino. | Usuário, na criação do export |
| `StorageDirectory` | Diretório raiz dentro do container (`rootFolderPath` na API). | Usuário, na criação do export |
| `ExportName` | Nome do export. | Usuário, na criação do export |
| `[YYYYMMDD-YYYYMMDD]` | Pasta do período, delimitada por início e fim. Exemplos oficiais: `[20240401-20240430]`, `[20241101-20241130]`. | Azure |
| `[RunID]` | Pasta da execução, identificada por um RunID. | Azure |

Comportamento documentado de `overwrite`:

- **Sem file overwrite:** "You see multiple *RunIDs* within the month folder, representing different
  export runs. For example, 30 different *RunIDs* for 30 days."
- **Com file overwrite:** "You see only one *RunID* within the month folder, representing the latest run."

> "Azure ensures that the cost file for a particular month is available within that month's folder."

Fonte: https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-improved-exports (seção "How are the exported files organized in the blob storage folders?") — consultado em 2026-10-14

### 2.2 Convenção de nomes de arquivo e particionamento

| Item | Valor documentado | Fonte (2026-10-14) |
|---|---|---|
| Manifesto | `_manifest.json`, na **mesma pasta** dos arquivos de dados da run. | tutorial-improved-exports §"Manifest file" — o texto diz "a manifest.json file"; o exemplo de conteúdo é rotulado "Here's a \_manifest.json example manifest file." |
| Partições | Nomes no padrão `part<N><ext>`; o exemplo oficial único é `part0.csv` (o exemplo mostra `blobCount: 1`). | tutorial-improved-exports, exemplo de `_manifest.json` |
| Extensão | `.csv` (formato CSV) — o formato Parquet é suportado para o dataset, mas **o exemplo oficial de nome de partição é apenas `.csv`**. | tutorial-improved-exports |
| Regra de nomes | **"Avoid hardcoding or guessing partition names, as file naming conventions may change."** A documentação instrui a **sempre** obter os nomes pelo manifesto. | tutorial-improved-exports §"Working with partitioned files" |
| Critério de particionamento | **Por tamanho, não por contagem de linhas.** Cada arquivo descomprimido fica **abaixo de 1 GB**. Para formatos comprimidos como Gzip, o tamanho real varia conforme a eficiência da compressão. | tutorial-improved-exports §"Why and when file partitioning is applied" |
| Obrigatoriedade | Particionamento **sempre habilitado**, não pode ser desabilitado ("Partitioning is a default behavior in exports experience and cannot be disabled.") | tutorial-improved-exports |
| Cabeçalho | "Each file partition has headers and contains only a subset of the full dataset." | tutorial-improved-exports §"Manifest file" |
| Conteúdo | Para processar o dataset completo, é obrigatório ingerir **cada** partição listada no manifesto. | tutorial-improved-exports §"Manifest file" |
| Fuso horário | UTC. "Exports are scheduled using Coordinated Universal Time (UTC). The Exports API always uses and displays UTC." | tutorial-improved-exports |

> **Aviso de não-determinismo:** a própria Microsoft alerta que a convenção de nomes de arquivo
> pode mudar e que o manifesto é a única fonte confiável. O simulador deve tratar
> `blobs[].blobName` do manifesto como autoritativo e nunca reconstruir o nome por conta própria.

### 2.3 Formatos e compressão por dataset (relevante para os arquivos que o manifesto lista)

| Dataset | Formatos suportados | Compressão suportada |
|---|---|---|
| Cost and usage details (Actual) | CSV / Parquet | None, Gzip / None, Snappy |
| Cost and usage details (Amortized) | CSV / Parquet | None, Gzip / None, Snappy |
| Cost and usage details (Usage only) | CSV / Parquet | None, Gzip / None, Snappy |
| Cost and usage details (FOCUS) | CSV / Parquet | None, Gzip / None, Snappy |
| Reservation details | CSV | None |
| Reservation recommendations | CSV | None |
| Reservation transactions | CSV | None |
| Price Sheet | CSV / Parquet | None, Gzip / None, Snappy |

Fonte: https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-improved-exports (tabela "Which datasets support Parquet format and compression?") — consultado em 2026-10-14

## 3. Campos

Como não há schema formal publicado, **o campo normativo desta superfície é o exemplo oficial**.
A tabela abaixo tem uma linha por campo observável, com o nível de comprovação explícito.

Legenda de comprovação. No `.schema.json`, a coluna `status` é **estritamente** `verified` ou
`unverified`; a nuance vai no campo separado **`evidence`**. A coluna **Tipo** das tabelas abaixo
exibe `evidence` exatamente com o mesmo valor gravado no JSON:

- **`example-only`** — o nome e o valor aparecem literalmente no exemplo oficial de `_manifest.json`
  do tutorial, mas **apenas** num exemplo: não é contrato publicado nem schema normativo.
- **sem `evidence`** (declarativa) — o campo não aparece no exemplo, mas corresponde a uma
  propriedade do modelo de export do REST API oficial (mesma semântica, mesmo nome de propriedade
  na API).

> Efeito no validador de fidelidade: **nenhum** dos 29 campos `example-only` é geraVEL, porque
> `evidence` diferente de `declared` bloqueia a geração. Só os 12 campos com `evidence` declarativa
> são geraVEIS nesta superfície. É a expressão executável de "o manifesto não é contrato publicado".

**Semântica de `Obrigatório` (campo `required` do `.schema.json`):** significa **"o provedor declara
o campo como sempre presente no artefato"** — não significa "o valor nunca é nulo". Como a Microsoft
**não publica schema formal do manifesto**, um campo visto **apenas num exemplo** não pode ser
declarado sempre presente: um exemplo não é contrato. Por isso **apenas 12 dos 41 campos são
`required: true`** — exatamente os 12 que a API REST oficial documenta como propriedades do modelo de
export (o contrato publicado). Os **29 campos `example-only` são `required: false`**: o simulador
pode descrevê-los, mas também não pode ser acusado de omitir um campo que nenhum contrato promete.
O validador usa `required` para acusar *coluna obrigatória ausente no artefato*; tratar
`example-only` como obrigatório produziria exatamente esse falso positivo.

### 3.1 Exemplo oficial de `_manifest.json` (reproduzido literalmente)

Fonte: https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-improved-exports (seção "Manifest file") — consultado em 2026-10-14

```json
{
  "manifestVersion": "2024-04-01",
  "byteCount": 8032,
  "blobCount": 1,
  "dataRowCount": 36,
  "exportConfig": {
    "exportName": "sample",
    "resourceId": "/providers/Microsoft.Billing/billingAccounts/1234567/providers/Microsoft.CostManagement/exports/sample",
    "dataVersion": "2023-05-01",
    "apiVersion": "2023-07-01-preview",
    "type": "ReservationRecommendations",
    "timeFrame": "MonthToDate",
    "granularity": null
  },
  "deliveryConfig": {
    "partitionData": true,
    "dataOverwriteBehavior": "OverwritePreviousReport",
    "fileFormat": "Csv",
    "compressionMode": "None",
    "containerUri": "/subscriptions/ 00000000-0000-0000-0000-000000000000/resourceGroups/samplerg/providers/Microsoft.Storage/storageAccounts/samplestorage",
    "rootFolderPath": "folder"
  },
  "runInfo": {
    "executionType": "OnDemand",
    "submittedTime": "2025-03-21T21:04:06.5234447Z",
    "runId": "bbac73f1-9a05-4de6-84ab-c72b568a03b4",
    "startDate": "2025-03-01T00:00:00",
    "endDate": "2025-03-21T00:00:00Z"
  },
  "blobs": [
    {
      "blobName": " folder/sample/ 00000000-0000-0000-0000-000000000000/part0.csv",
      "byteCount": 8032,
      "dataRowCount": 36
    }
  ]
}
```

> Nota: os espaços dentro de `containerUri` e `blobName` (`"/subscriptions/ 00000000-..."` e
> `" folder/sample/ ..."`) estão **exatamente como publicados** no exemplo oficial. Não foram
> normalizados aqui de propósito — ver §6, divergência 2.

### 3.2 Campos do manifesto

| Campo | Tipo | Obrigatório | Unidade | Formato data/hora | Valores permitidos | Descrição | Fonte |
|---|---|---|---|---|---|---|---|
| `manifestVersion` | String | não | — | — | — | Versão do formato do manifesto. Exemplo oficial: `"2024-04-01"`. Não há lista de versões publicada. | [tutorial](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-improved-exports) — 2026-10-14 |
| `byteCount` | Integer | não | bytes | — | — | Soma de bytes do dataset completo (topo) ou de uma partição (em `blobs[]`). | [tutorial](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-improved-exports) — 2026-10-14 |
| `blobCount` | Integer | não | contagem de blobs | — | — | Número de partições (blobs) do dataset. Exemplo oficial: `1`. | [tutorial](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-improved-exports) — 2026-10-14 |
| `dataRowCount` | Integer | não | linhas de dados | — | — | Número de linhas de dados do dataset completo (topo) ou de uma partição (em `blobs[]`). O exemplo, com `blobCount=1`, traz `36` em ambos os níveis. | [tutorial](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-improved-exports) — 2026-10-14 |
| `exportConfig` | Object | não | — | — | — | Objeto com a configuração do export em vigor na run. | [tutorial](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-improved-exports) — 2026-10-14 |
| `exportConfig.exportName` | String | não | — | — | — | Nome do export. Exemplo: `"sample"`. Corresponde a `ExportName` do caminho do blob. | [tutorial](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-improved-exports) — 2026-10-14 |
| `exportConfig.resourceId` | String | não | — | — | — | Resource ID ARM do objeto export. Exemplo: `/providers/Microsoft.Billing/billingAccounts/1234567/providers/Microsoft.CostManagement/exports/sample`. | [tutorial](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-improved-exports) — 2026-10-14 |
| `exportConfig.dataVersion` | String | não | — | — | — | Versão do schema do dataset exportado. Exemplo: `"2023-05-01"`. Corresponde a `dataSet.configuration.dataVersion` da API. | [tutorial](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-improved-exports) — 2026-10-14 |
| `exportConfig.apiVersion` | String | não | — | — | — | Versão da API de export usada. Exemplo: `"2023-07-01-preview"`. | [tutorial](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-improved-exports) — 2026-10-14 |
| `exportConfig.type` | String | não | — | — | — | `ExportType` do dataset. Exemplo oficial: `"ReservationRecommendations"`. Corresponde ao `definition.type` da API. | [tutorial](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-improved-exports) — 2026-10-14 |
| `exportConfig.timeFrame` | String | não | — | — | — | `TimeframeType` do export. Exemplo oficial: `"MonthToDate"`. Corresponde a `definition.timeframe` da API (grafado `timeframe` em minúsculas na API). | [tutorial](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-improved-exports) — 2026-10-14 |
| `exportConfig.granularity` | String ou null | não | — | — | — | `GranularityType` do dataset. O exemplo traz `null`. Corresponde a `dataSet.granularity` da API. | [tutorial](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-improved-exports) — 2026-10-14 |
| `deliveryConfig` | Object | não | — | — | — | Objeto com a configuração de entrega em vigor na run. | [tutorial](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-improved-exports) — 2026-10-14 |
| `deliveryConfig.partitionData` | Boolean | não | — | — | `true`, `false` | Igual à propriedade REST de mesmo nome: *"If set to true, exported data will be partitioned by size and placed in a blob directory together with a manifest file."* Exemplo: `true`. | [tutorial](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-improved-exports) + [REST](https://learn.microsoft.com/en-us/rest/api/cost-management/exports/create-or-update?view=rest-cost-management-2025-03-01&tabs=HTTP) — 2026-10-14 |
| `deliveryConfig.dataOverwriteBehavior` | String | não | — | — | Exemplo oficial: `"OverwritePreviousReport"`; a API define também `"CreateNewReport"` (padrão). | `DataOverwriteBehaviorType`: sobrescrita dos dados do mesmo mês no storage account. | [tutorial](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-improved-exports) + [REST](https://learn.microsoft.com/en-us/rest/api/cost-management/exports/create-or-update?view=rest-cost-management-2025-03-01&tabs=HTTP) — 2026-10-14 |
| `deliveryConfig.fileFormat` | String | não | — | — | Exemplo oficial: `"Csv"`. A API define `FormatType` com `"Csv"` e `"Parquet"`. | Formato do arquivo entregue. Exemplo: `"Csv"`. Note que **na API o nome é `format`**, não `fileFormat`. | [tutorial](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-improved-exports) + [REST](https://learn.microsoft.com/en-us/rest/api/cost-management/exports/create-or-update?view=rest-cost-management-2025-03-01&tabs=HTTP) — 2026-10-14 |
| `deliveryConfig.compressionMode` | String | não | — | — | Exemplo oficial: `"None"`. A documentação do portal lista `None`, `Gzip` (CSV) e `Snappy` (Parquet); o exemplo REST usa `"gzip"`. | Esquema de compressão. Exemplo: `"None"`. | [tutorial](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-improved-exports) + [REST](https://learn.microsoft.com/en-us/rest/api/cost-management/exports/create-or-update?view=rest-cost-management-2025-03-01&tabs=HTTP) — 2026-10-14 |
| `deliveryConfig.containerUri` | String | não | — | — | — | Resource ID do storage account de destino. O exemplo oficial contém um espaço após `/subscriptions/` (ver §6). A API usa o nome `resourceId` no destino. | [tutorial](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-improved-exports) — 2026-10-14 |
| `deliveryConfig.rootFolderPath` | String | não | — | — | — | `StorageDirectory` (diretório raiz) do export. Exemplo: `"folder"`. Corresponde a `deliveryInfo.destination.rootFolderPath`. | [tutorial](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-improved-exports) — 2026-10-14 |
| `runInfo` | Object | não | — | — | — | Objeto com informações da execução. | [tutorial](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-improved-exports) — 2026-10-14 |
| `runInfo.executionType` | String | não | — | — | Exemplo oficial: `"OnDemand"`. A run history REST usa também `"Scheduled"`. | Tipo da execução. Exemplo: `"OnDemand"`. | [tutorial](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-improved-exports) + [REST](https://learn.microsoft.com/en-us/rest/api/cost-management/exports/get-execution-history?view=rest-cost-management-2025-03-01) — 2026-10-14 |
| `runInfo.submittedTime` | String | não | — | ISO 8601 UTC com **7 casas de fração de segundo** no exemplo oficial: `2025-03-21T21:04:06.5234447Z` | — | Momento em que a run foi submetida. Corresponde a `submittedTime` da run history. | [tutorial](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-improved-exports) — 2026-10-14 |
| `runInfo.runId` | String (GUID) | não | — | — | — | Identificador da run; é o `[RunID]` do caminho do blob. Exemplo: `bbac73f1-9a05-4de6-84ab-c72b568a03b4`. | [tutorial](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-improved-exports) — 2026-10-14 |
| `runInfo.startDate` | String | não | — | **Sem designador de fuso no exemplo oficial:** `"2025-03-01T00:00:00"`. Compare com `endDate`, que traz `Z`. | — | Data inicial do período da run. | [tutorial](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-improved-exports) — 2026-10-14 |
| `runInfo.endDate` | String | não | — | ISO 8601 UTC com `Z`: `"2025-03-21T00:00:00Z"` | — | Data final do período da run. | [tutorial](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-improved-exports) — 2026-10-14 |
| `blobs` | Array de Object | não | — | — | — | Lista das partições. "Each file partition has headers and contains only a subset of the full dataset." | [tutorial](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-improved-exports) — 2026-10-14 |
| `blobs[].blobName` | String | não | — | — | — | **Nome/caminho autoritativo da partição.** Exemplo: `" folder/sample/ 00000000-0000-0000-0000-000000000000/part0.csv"`. A documentação instrui a usar sempre o manifesto e nunca inferir nomes. | [tutorial](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-improved-exports) — 2026-10-14 |
| `blobs[].byteCount` | Integer | não | bytes | — | — | Tamanho da partição em bytes. | [tutorial](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-improved-exports) — 2026-10-14 |
| `blobs[].dataRowCount` | Integer | não | linhas de dados | — | — | Número de linhas de dados da partição. | [tutorial](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-improved-exports) — 2026-10-14 |
| `exportConfig.beginDate` | String | **não** | — | — | — | Campo de data inicial do export. **Não aparece no exemplo oficial.** Se existir, seguiria o padrão `beginDate`/`endDate` do objeto `ExportExecution`/`ExportRecurrencePeriod` da API. Não gerar sem confirmação. | UNVERIFIED — ver §5 |
| `exportConfig.endDate` | String | **não** | — | — | — | Campo de data final do export. **Não aparece no exemplo oficial.** Mesma ressalva de `beginDate`. | UNVERIFIED — ver §5 |

### 3.3 Campos relacionados ao manifesto na API (não dentro do arquivo)

Estes campos **não** estão dentro do `_manifest.json`; documentam onde o manifesto fica, e são a
ligação oficial entre a run e o arquivo.

| Campo | Onde | Tipo | Descrição | Fonte |
|---|---|---|---|---|
| `manifestFile` | Resposta de `GET .../exports/{exportName}/runHistory` (`ExportRun`) | String | *"The manifest file location(URI location) for the exported files."* Exemplos oficiais: `"ScheduledTestsForJohnDoe/JohnDoeSchedule/20180729-20180804/manifestfile"`. | [Get Execution History](https://learn.microsoft.com/en-us/rest/api/cost-management/exports/get-execution-history?view=rest-cost-management-2025-03-01) — 2026-10-14 |
| `properties.partitionData` | Request/response de `PUT .../exports/{exportName}` | Boolean | *"If set to true, exported data will be partitioned by size and placed in a blob directory together with a manifest file."* | [Create Or Update](https://learn.microsoft.com/en-us/rest/api/cost-management/exports/create-or-update?view=rest-cost-management-2025-03-01&tabs=HTTP) — 2026-10-14 |
| `fileName` | Resposta de `runHistory` (`ExportRun`) | String | Nome do arquivo exportado. Exemplo: `".../20180729-20180804/JohnDoeSchedule_1e25d58a-....csv"`. Note o padrão `{ExportName}_{RunId}.csv` no exemplo da API, que **difere** do padrão `part<N>.csv` do exemplo do manifesto. | [Get Execution History](https://learn.microsoft.com/en-us/rest/api/cost-management/exports/get-execution-history?view=rest-cost-management-2025-03-01) — 2026-10-14 |
| `runSettings.partitionData` | Resposta de `runHistory` | Boolean | Configuração de particionamento em vigor na run. Exemplo: `true`. | [Get Execution History](https://learn.microsoft.com/en-us/rest/api/cost-management/exports/get-execution-history?view=rest-cost-management-2025-03-01) — 2026-10-14 |
| `runSettings.format` | Resposta de `runHistory` | String | Formato em vigor na run. Exemplo: `"Csv"`. | [Get Execution History](https://learn.microsoft.com/en-us/rest/api/cost-management/exports/get-execution-history?view=rest-cost-management-2025-03-01) — 2026-10-14 |
| `runSettings.compressionMode` | Resposta de `runHistory` | String | Compressão em vigor na run. Exemplo: `"gzip"`. | [Get Execution History](https://learn.microsoft.com/en-us/rest/api/cost-management/exports/get-execution-history?view=rest-cost-management-2025-03-01) — 2026-10-14 |
| `runSettings.dataOverwriteBehavior` | Resposta de `runHistory` | String | Comportamento de sobrescrita em vigor. Exemplo: `"OverwritePreviousReport"`. | [Get Execution History](https://learn.microsoft.com/en-us/rest/api/cost-management/exports/get-execution-history?view=rest-cost-management-2025-03-01) — 2026-10-14 |
| `executionType` | Resposta de `runHistory` | String | `"OnDemand"` ou `"Scheduled"`. | [Get Execution History](https://learn.microsoft.com/en-us/rest/api/cost-management/exports/get-execution-history?view=rest-cost-management-2025-03-01) — 2026-10-14 |
| `submittedBy` | Resposta de `runHistory` | String | *"The identifier for the entity that triggered the export. For on-demand runs it is the user email. For scheduled runs it is 'System'."* | [ExportRun class](https://learn.microsoft.com/en-us/dotnet/api/azure.resourcemanager.costmanagement.models.exportrun?view=azure-dotnet) — 2026-10-14 |
| `status` | Resposta de `runHistory` | String | Último status conhecido da run. Exemplo: `"Completed"`. | [Get Execution History](https://learn.microsoft.com/en-us/rest/api/cost-management/exports/get-execution-history?view=rest-cost-management-2025-03-01) — 2026-10-14 |
| `processingStartTime` / `processingEndTime` | Resposta de `runHistory` | String (DateTime) | Início e fim do processamento. Exemplos: `"2018-08-03T07:52:16.9123797Z"`, `"2018-08-03T07:52:28.0373318Z"`. | [Get Execution History](https://learn.microsoft.com/en-us/rest/api/cost-management/exports/get-execution-history?view=rest-cost-management-2025-03-01) — 2026-10-14 |

## 4. Resumo da comprovação

| Nível | Quantidade | Campos |
|---|---|---|
| **example-only** (literal no exemplo oficial, §3.2) | 29 | 4 escalares (`manifestVersion`, `byteCount`, `blobCount`, `dataRowCount`) + `exportConfig` (objeto) e 7 filhos + `deliveryConfig` (objeto) e 6 filhos + `runInfo` (objeto) e 5 filhos + `blobs` (array) e 3 filhos = 29 |
| **UNVERIFIED dentro do manifesto** (§3.2) | 2 | `exportConfig.beginDate`, `exportConfig.endDate` — **não gerados** |
| **declarativa / sem `evidence`** (nome/valores confirmados em página REST oficial, §3.3) | 12 | `manifestFile`, `properties.partitionData`, `fileName`, `runSettings.partitionData`, `runSettings.format`, `runSettings.compressionMode`, `runSettings.dataOverwriteBehavior`, `executionType`, `submittedBy`, `status`, `processingStartTime`, `processingEndTime` |

Notas de contagem:

- O `.schema.json` desta superfície tem **41 entradas**: 29 do manifesto (`example-only`) + 12 da API (declarativas) (API-CORROBORATED). Os 2 itens `UNVERIFIED` do manifesto **não** entram como colunas geradas.
- Na §3.3, `processingStartTime` e `processingEndTime` estão numa **única linha de tabela** por serem o mesmo par
  início/fim; são **2 campos distintos** no `.schema.json`.

## 5. Campos não comprovados

| Campo | Status | Motivo |
|---|---|---|
| `exportConfig.beginDate` | **UNVERIFIED** | Não aparece no único exemplo oficial de `_manifest.json`. Não há tabela de campos nem JSON Schema do manifesto publicados pela Microsoft. Não gerar. |
| `exportConfig.endDate` | **UNVERIFIED** | Idem. Não gerar. |
| Estrutura de `exportConfig` em versões futuras | **UNVERIFIED** | Sem schema formal publicado, não há como provar que `manifestVersion` novo mantenha os mesmos campos. O simulador deve fixar `manifestVersion` explicitamente e não inferir variação. |
| Valores permitidos não exemplificados | **UNVERIFIED** | Os conjuntos completos de `exportConfig.type` (`ExportType`), `exportConfig.timeFrame` (`TimeframeType`) e `exportConfig.granularity` (`GranularityType`) **não** têm enumeração publicada em tabela recuperável nas páginas consultadas. Só os valores que aparecem em exemplos oficiais (`ReservationRecommendations`, `MonthToDate`, `null`, `ActualCost`, `Daily`, `PriceSheet`, `TheCurrentMonth`, `TheLastMonth`, `Custom`) são comprovados. |
| Precisão/casing de `manifestVersion` | **UNVERIFIED** | Único valor comprovado: `"2024-04-01"`. Não há lista de versões de manifesto publicada. |
| Caminho do manifesto para exports **não particionados** | **UNVERIFIED** | A documentação diz que o manifesto acompanha dados particionados, mas o particionamento é sempre ativo na experiência atual; não há exemplo de export sem manifesto nem de caminho alternativo. |

## 6. Divergências conhecidas

| # | Divergência | Fonte A | Fonte B | Tratamento |
|---|---|---|---|---|
| 1 | **Nome do arquivo de manifesto.** O texto diz "manifest.json"; o rótulo do exemplo diz `_manifest.json`; a API devolve o caminho como `.../manifestfile`. | https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-improved-exports ("a manifest.json file" / "Here's a \_manifest.json example manifest file") | https://learn.microsoft.com/en-us/rest/api/cost-management/exports/get-execution-history?view=rest-cost-management-2025-03-01 (exemplos com `manifestFile: ".../manifestfile"`) | Registrado, sem escolha unilateral. Recomendação para o simulador: emitir `_manifest.json` e **sempre** anunciar o caminho via `manifestFile`/descoberta, nunca assumir o nome. |
| 2 | **Espaços dentro de valores no exemplo oficial.** `containerUri` e `blobName` contêm um espaço após `/subscriptions/` e no início do caminho. | https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-improved-exports | — | Registrado. Provável artefato de formatação da página, mas **não** normalizamos: é o texto oficial. Não replicar o espaço em dados gerados; a decisão fica registrada aqui. |
| 3 | **Nome do campo de formato.** No manifesto é `fileFormat`; na API de export é `format`; na run history é `runSettings.format`. | `_manifest.json` de https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-improved-exports | https://learn.microsoft.com/en-us/rest/api/cost-management/exports/create-or-update?view=rest-cost-management-2025-03-01&tabs=HTTP | Registrado. O simulador usa `fileFormat` **dentro** do manifesto e `format` na API. |
| 4 | **Casing de compressão.** Manifesto: `"None"`. Run history REST: `"gzip"` (minúsculas). | `_manifest.json` (tutorial) | runHistory (`"compressionMode": "gzip"`) | Registrado. Não uniformizar. |
| 5 | **Padrão de nome de partição.** Manifesto: `part0.csv`. Run history REST: `JohnDoeSchedule_<RunId>.csv`. | `_manifest.json` (tutorial) | runHistory (`fileName`) | Registrado. A própria documentação proíbe depender de convenção de nome: usar `blobs[].blobName`. |
| 6 | **`startDate` sem designador UTC** no exemplo (`"2025-03-01T00:00:00"`), enquanto `endDate` tem `Z`. | `_manifest.json` (tutorial) | — | Registrado. Provável omissão do exemplo; a documentação declara que o Exports API "always uses and displays UTC". Ver `UNVERIFIED` em §5 quanto a tornar a omissão normativa. |
| 7 | **`byteCount`/`dataRowCount` com o mesmo valor em dois níveis.** Com `blobCount: 1`, topo e `blobs[0]` trazem `8032`/`36`. Com múltiplas partições, a documentação **não** afirma se o topo é a soma. | `_manifest.json` (tutorial) | — | Registrado como `UNVERIFIED` (§5): a semântica agregada do topo não é comprovada para `blobCount > 1`. |

## 7. Regra de ouro aplicada

- **Nenhum campo do manifesto foi inventado.** Todos vêm do exemplo oficial reproduzido em §3.1 ou de página REST oficial (§3.3).
- O manifesto é o **único** caso deste escopo em que a Microsoft documenta por exemplo e não por schema; isso está declarado explicitamente em §1.1 e §4, e os dois campos não exemplificados foram para §5 como `UNVERIFIED`.
- Não há schema formal do manifesto, portanto a afirmação "o schema do manifesto foi confirmado a partir da documentação" só é válida no sentido de **conjunto de campos exibidos em exemplo oficial** — não de esquema normativo.



