# Azure Cost Management — o conceito de "dataset" no Exports e quais têm schema documentado

## 1. Identificação

| Item | Valor |
|---|---|
| Assunto | O conceito de **dataset** (tipo de dado) exposto pelo Microsoft Cost Management Exports |
| Documento oficial primário | "Tutorial: Create and manage Cost Management exports" — https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-improved-exports — consultado em **2026-10-14** |
| Documento oficial (índice de schemas) | "Cost Management dataset schema index" — https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/schema-index — consultado em **2026-10-14** |
| Documento oficial (metadados FOCUS) | "Details about the FOCUS dataset" — https://learn.microsoft.com/en-us/cloud-computing/finops/focus/metadata — consultado em **2026-10-14** |

Este documento é a referência cruzada do diretório. Ele **não** define colunas; aponta para a spec
de cada superfície e declara, para cada dataset, **se a Microsoft publica schema**.

## 2. Como a Microsoft define "dataset"

Na experiência de Exports, um **export** é a unidade de agendamento e entrega; cada export carrega
**um ou mais datasets**. A documentação chama cada um de "Type of data" e "dataset":

> "You can create multiple exports of various data types using the following steps."
> "The exports feature supports multiple datasets including price sheets, reservation
> recommendations, reservation details, and reservation transactions."
> "You can add another export by selecting **+ Add export**. Select the **Type of data**, the
> **Dataset version**, and enter an **Export name**."
> "Exports let you choose the latest or any of the earlier dataset schema versions when you create
> a new export."

Ou seja: **dataset = (Type of data, Dataset version)**. O **Dataset version** é o eixo de
versionamento de schema — ex.: o FOCUS tem `1.2-preview`, `1.0`, `1.0-preview(v1)`; o dataset
clássico tem `2024-08-01`, `2023-12-01-preview`, `2021-10-01`, `2021-01-01`, `2019-11-01` etc.

Na API REST, o dataset é expresso por `properties.definition.type` (`ExportType`), com a versão em
`dataSet.configuration.dataVersion` e a granularidade em `dataSet.granularity`:

```json
"definition": {
  "type": "ActualCost",
  "dataSet": { "configuration": { "dataVersion": "2023-05-01" }, "granularity": "Daily" },
  "timeframe": "MonthToDate"
}
```

Fonte: https://learn.microsoft.com/en-us/rest/api/cost-management/exports/create-or-update?view=rest-cost-management-2025-03-01&tabs=HTTP — consultado em 2026-10-14

> Nota de fidelidade: a documentação **não** publica uma tabela exaustiva ligando o rótulo de UI
> ("Type of data") ao valor de `ExportType` (`ActualCost`, `AmortizedCost`, `FocusCost`,
> `PriceSheet`, `ReservationDetails`, `ReservationTransactions`, `ReservationRecommendations`…).
> Apenas alguns valores aparecem em exemplos oficiais. Ver §5.

### 2.1 Limite de datasets por export

- "You can create up to 10 exports when you select **+ Add new exports**."
- Cada export pode ter seu próprio dataset e versão; o `Export prefix` é comum.

Fonte: https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-improved-exports — consultado em 2026-10-14

## 3. Datasets, schema documentado e spec correspondente

| Dataset (Type of data na UI) | `ExportType` em exemplos oficiais | Schema de colunas documentado pela Microsoft? | Onde | Spec neste diretório |
|---|---|---|---|---|
| **Cost and usage details (actual)** | `ActualCost` | **Parcial**: nomes e ordem das colunas por contrato/versão, **sem** tipos, unidades, formatos ou enums | https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-ea · `-mca` · `-mca-partner` · `-mca-partner-subscription` · `-pay-as-you-go` | [`cost-management-export-cost-details.md`](cost-management-export-cost-details.md) |
| **Cost and usage details (amortized)** | `AmortizedCost` (não localizado em exemplo oficial consultado) | **Parcial** — a Microsoft publica **um só** schema "Cost and usage details" por contrato; **não** há schema separado por métrica | idem acima | idem |
| **Cost and usage details (usage only)** | `Usage` | **Parcial** (mesma família) | idem acima | idem |
| **Cost and usage details (FOCUS)** | `FocusCost` (não localizado em exemplo oficial consultado) | **SIM — completo**: nome, `DataType` e descrição por coluna, mais `SchemaId`, `FocusVersion`, `CreationDate`, `StringEncoding` | https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus e https://learn.microsoft.com/en-us/cloud-computing/finops/focus/metadata | [`cost-management-export-focus12.md`](cost-management-export-focus12.md) |
| **Price sheet** ("All available prices") | `PriceSheet` | **SIM — nomes e ordem**, por contrato (EA `2023-05-01`, MCA `2024-08-01`); tipos/unidades **não** publicados | https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/price-sheet-ea · https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/price-sheet-mca | fora do escopo desta entrega |
| **Reservation details** | `ReservationDetails` (não localizado em exemplo oficial consultado) | **SIM — nomes e ordem**, por contrato (`2023-03-01`) | https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/reservation-details-ea · https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/reservation-details-mca | fora do escopo desta entrega |
| **Reservation recommendations** | `ReservationRecommendations` | **SIM — nomes e ordem**, por contrato (`2023-05-01`) | https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/reservation-recommendations-ea · https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/reservation-recommendations-mca | fora do escopo desta entrega |
| **Reservation transactions** | `ReservationTransactions` (não localizado em exemplo oficial consultado) | **SIM — nomes e ordem**, por contrato (`2023-05-01`) | https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/reservation-transactions-ea · https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/reservation-transactions-mca | fora do escopo desta entrega |
| **Manifesto de entrega** (não é um dataset; acompanha toda run) | — | **NÃO**: só exemplo oficial | https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-improved-exports | [`cost-management-export-manifest.md`](cost-management-export-manifest.md) |

A lista oficial de "Type of data" documentada no tutorial, literalmente:

- Cost and usage details (actual) — "standard usage and purchase charges".
- Cost and usage details (amortized) — "amortized costs for purchases like Azure reservations and Azure savings plan for compute".
- Cost and usage details (FOCUS) — "cost and usage details using the open-source FinOps Open Cost and Usage Specification (FOCUS) format. It combines actual and amortized costs."
- Cost and usage details (usage only) — "standard usage charges without purchase information. Although you can't use this option when creating new exports, existing exports using this option are still supported."
- Price sheet — "download your organization's Azure pricing".
- Reservation details — "the current list of all available reservations".
- Reservation recommendations — "the list of reservation recommendations, which help with rate optimization".
- Reservation transactions — "the list of all reservation purchases, exchanges, and refunds".

Fonte: https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-improved-exports (seção "Understand export data types") — consultado em 2026-10-14

## 4. Diferenças operacionais relevantes entre datasets

| Dataset | Formatos | Compressão | Frequências | Retenção (portal / REST) | Escopos especiais |
|---|---|---|---|---|---|
| Cost and usage (Actual, Amortized, FOCUS) | CSV, Parquet | None/Gzip (CSV), None/Snappy (Parquet) | one-time; daily MTD; monthly last month; monthly last billing month | 13 meses / 7 anos | FOCUS **não** suporta management group; MOSP não suporta FOCUS |
| Cost and usage (Usage only) | CSV, Parquet | idem | idem | 13 meses / 7 anos | management group suportado (CSV, sem compressão) |
| Price sheet | CSV, Parquet | idem | one-time; current month; daily current month | 13 meses / MCA-MPA 13 meses, **EA 25 meses** | EA: billing account. Demais: billing profile |
| Reservation details | CSV | **None apenas** | one-time; daily MTD; monthly last month | 13 meses / 13 meses | EA: billing account; demais: billing profile |
| Reservation recommendations | CSV | **None apenas** | one-time; daily | **snapshot atual apenas** | EA: billing account; demais: billing profile |
| Reservation transactions | CSV | **None apenas** | one-time; daily; monthly last month | 13 meses / 7 anos | EA: billing account; demais: billing profile |

Fontes: https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-improved-exports (tabelas de formatos e de retenção) — consultado em 2026-10-14

## 5. Campos não comprovados

| Item | Status | Motivo |
|---|---|---|
| Mapa completo "Type of data" (UI) → `ExportType` (API) | **UNVERIFIED** | Nenhuma página oficial consultada publica a tabela de correspondência. Só valores avulsos aparecem em exemplos: `ActualCost`, `PriceSheet`, `ReservationRecommendations`. |
| `ExportType` de *amortized*, *usage only*, *FOCUS*, *reservation details* e *reservation transactions* | **UNVERIFIED** | Os valores `AmortizedCost`, `Usage`, `FocusCost`, `ReservationDetails`, `ReservationTransactions` **não** foram localizados em exemplo ou enumeração oficial nas páginas consultadas. Não afirmar. |
| Enumeração completa de `TimeframeType`, `GranularityType`, `RecurrenceType` | **UNVERIFIED** | Sem tabela de enumeração recuperável; só valores vistos em exemplos (`MonthToDate`, `TheCurrentMonth`, `TheLastMonth`, `Custom`, `Daily`, `None`). |
| Schema de colunas para Price sheet, Reservation details, Reservation recommendations, Reservation transactions | **não coletado nesta entrega** | As páginas existem oficialmente, mas estão **fora do escopo** desta tarefa. Não foram transcritas e **não devem** ser consideradas especificadas. |
| Se *actual* e *amortized* compartilham exatamente o mesmo conjunto de colunas | **UNVERIFIED** | Ver §5 de [`cost-management-export-cost-details.md`](cost-management-export-cost-details.md). |

## 6. Divergências conhecidas

| # | Divergência | Fonte A | Fonte B | Tratamento |
|---|---|---|---|---|
| 1 | **O índice de schemas não cobre todos os datasets que o tutorial lista.** O tutorial lista 8 tipos de dado; o índice lista schemas para "Cost and usage details", "Cost and usage details (FOCUS)", "Price sheet", "Reservation details", "Reservation recommendations" e "Reservation transactions". | https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-improved-exports | https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/schema-index | Registrado. O índice **não** tem entrada separada por métrica (actual/amortized/usage only). |
| 2 | **Nome do campo de dataset na UI vs na API.** A UI usa "Type of data" e "Dataset version"; a API usa `definition.type` e `dataSet.configuration.dataVersion`. | tutorial-improved-exports | https://learn.microsoft.com/en-us/rest/api/cost-management/exports/create-or-update?view=rest-cost-management-2025-03-01&tabs=HTTP | Registrado. Sem escolha unilateral; ambos os vocabulários são oficiais em seus contextos. |
| 3 | **Retenção do price sheet difere entre portal e API para EA** (13 meses no portal, 25 meses via API). | tutorial-improved-exports (tabela "Data retention limits by dataset") | — | Registrado. |

## 7. Regra de ouro aplicada

- Este documento **não** define colunas: apenas mapeia datasets → existência de schema → spec.
- Os valores de `ExportType` que não foram vistos em fonte oficial estão em §5 como `UNVERIFIED`.
- Os datasets fora do escopo estão explicitamente marcados como **não especificados**, para que
  ninguém os trate como documentados por engano.
