# Azure — Cost Management export: FOCUS 1.2 dataset

## 1. Identificação

| Item | Valor |
|---|---|
| Nome oficial da superfície | **FOCUS cost and usage details file** (no portal: *Cost and usage details (FOCUS)*; schema ID `1.2-preview`, FOCUS version `1.2`) |
| Documento oficial (schema) | "FOCUS cost and usage details file schema" — https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus — consultado em **2026-10-14** |
| Documento oficial (metadados/tipos) | "Details about the FOCUS dataset" — https://learn.microsoft.com/en-us/cloud-computing/finops/focus/metadata — consultado em **2026-10-14** |
| Metadados oficiais legíveis por máquina | `dataset-metadata.zip` → `FocusCost_1.2-preview.json` — https://github.com/microsoft/finops-toolkit/releases/latest/download/dataset-metadata.zip (linkado a partir da página de metadados acima) — consultado em **2026-10-14** |
| Especificação padrão | FinOps Open Cost and Usage Specification (FOCUS) **1.2** — https://focus.finops.org (o site retornou HTTP 403 para o agente; as definições de atributos foram lidas do repositório normativo `FinOps-Open-Cost-and-Usage-Spec/FOCUS_Spec`, tag `v1.2`) |
| Versão/schema de referência | `1.2-preview` (Schema ID), FOCUS `1.2`, `CreationDate` 2025-06-13, `StringEncoding` **UTF-8** |
| Conformidade declarada pela Microsoft | 94% em relação à especificação FOCUS 1.2 — https://learn.microsoft.com/en-us/cloud-computing/finops/focus/conformance-summary — consultado em **2026-10-14** |

> A Microsoft declara explicitamente que o arquivo FOCUS "uses columns, values, and semantics
> as they're defined in the FinOps Open Cost and Usage Specification (FOCUS) project" e contém
> os mesmos dados de custo e uso que os arquivos *actual* e *amortized*.
> Fonte: https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus — 2026-10-14

## 2. Mecanismo e entrega

| Item | Valor documentado |
|---|---|
| Como é entregue | Export agendado do Microsoft Cost Management para **Azure Blob Storage** (o destino padrão no portal). |
| Caminho exato | `StorageContainer/StorageDirectory/ExportName/[YYYYMMDD-YYYYMMDD]/[RunID]/` |
| Arquivos no diretório | Os arquivos de dados particionados **e** um `_manifest.json`. |
| Formato do arquivo | **CSV** ou **Parquet** (escolhido na criação do export). |
| Compressão | CSV: `None` ou `Gzip`. Parquet: `None` ou `Snappy`. |
| Encoding | `StringEncoding` = **UTF-8** (nos metadados oficiais). O guia de export manda usar *File origin* `65001: Unicode (UTF-8)` ao abrir o CSV no Excel. |
| Cabeçalho | Cada partição "has headers and contains only a subset of the full dataset". |
| Particionamento | **Sempre habilitado**, não pode ser desabilitado. Divisão **por tamanho, não por contagem de linhas**; cada arquivo descomprimido fica **abaixo de 1 GB**. |
| Fuso horário | UTC. "Exports are scheduled using Coordinated Universal Time (UTC). The Exports API always uses and displays UTC." |
| Substituição de dados | `OverwritePreviousReport` por padrão em exports diários (um único `RunID` na pasta do mês). |
| Frequências suportadas | One-time; daily export of month-to-date costs; monthly export of last month's costs; monthly export of last billing month's costs. |
| Escopos suportados | EA: enrollment, department, account, subscription, resource group. MCA: billing account, billing profile, invoice section, subscription, resource group. MPA: customer, subscription, resource group. **Management group NÃO é suportado para FOCUS.** |
| Retenção | Portal: até 13 meses. REST API: até 7 anos. |
| Fuso/formato de data nos arquivos | ISO 8601 em UTC, formato estendido `YYYY-MM-DDTHH:mm:ssZ` (ver §3). |

Fontes (todas consultadas em 2026-10-14):
- Layout de pastas, particionamento, formatos e compressão: https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-improved-exports
- Codificação UTF-8: https://learn.microsoft.com/en-us/cloud-computing/finops/focus/metadata

### 2.1 Formato de data/hora — exigência FOCUS 1.2

O atributo **DateTimeFormat** da especificação FOCUS 1.2 exige, para colunas que representam um
instante específico:

- valores em **UTC**;
- conformidade com **ISO 8601**;
- formato estendido com offset UTC: `YYYY-MM-DDTHH:mm:ssZ`;
- componentes de data e hora separados pela letra `T`;
- horas (`HH`), minutos (`mm`) e segundos (`ss`) com **dois dígitos**;
- terminação com o designador UTC `Z`.

Fonte: https://github.com/FinOps-Open-Cost-and-Usage-Spec/FOCUS_Spec/blob/v1.2/specification/attributes/datetime_format.md — consultado em 2026-10-14

A Microsoft documenta uma mudança relacionada (versão **1.0r2**), que serve de referência para a
convenção de segundos obrigatórios: um export 1.0 podia produzir `2024-01-01T00:00Z` e um export
1.0r2 produz `2024-01-01T00:00:00Z`. Fonte: https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus (nota "Version 1.0r2") — consultado em 2026-10-14

### 2.2 Formato numérico — exigência FOCUS 1.2

O atributo **NumericFormat** exige valor numérico único, sem símbolos de moeda, sem unidades de
medida, sem vírgulas nem separadores de milhar, com ponto decimal, e sinal negativo `-` para
valores negativos (nunca `+` para positivos). Tipos permitidos: **Integer** e **Decimal**. A
especificação **não fixa precisão**: "The level of precision required for a given column is
determined by the provider". A Microsoft não publica a precisão/scale por coluna.

Fonte: https://github.com/FinOps-Open-Cost-and-Usage-Spec/FOCUS_Spec/blob/v1.2/specification/attributes/numeric_format.md — consultado em 2026-10-14

## 3. Campos

**Contagem: 106 colunas**, conforme o metadata JSON oficial `FocusCost_1.2-preview.json`.
A coluna **Tipo** usa o `DataType` oficial do metadata JSON (equivalente ao tipo declarado pela
Microsoft). Todas as linhas foram consultadas em **2026-10-14**.

Fonte canônica de nome/tipo/descrição de cada linha:
- https://learn.microsoft.com/en-us/cloud-computing/finops/focus/metadata (tabela "FocusCost 1.2-preview", com `DataType`)
- https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview (numeração e descrições)
- https://github.com/microsoft/finops-toolkit/releases/latest/download/dataset-metadata.zip (`FocusCost_1.2-preview.json`)

**Semântica de `Obrigatório` (campo `required` do `.schema.json`):** significa **"a coluna está
sempre presente no export"**, isto é, o provedor a lista como posição fixa do schema — **não**
significa "o valor nunca é nulo". As duas coisas são independentes e nesta superfície divergem: a
Microsoft publica uma lista posicional fechada, numerada de 1 a 105, portanto **todas as 106
colunas estão sempre presentes no arquivo**, inclusive as seis marcadas como "Currently
null/empty", que aparecem **presentes e com valor nulo**. É por isso que **106 de 106** colunas são
`required: true`, enquanto a nulidade é registrada separadamente em `evidence` (ver §3.1).

A Microsoft **não publica indicador de obrigatoriedade por coluna** para este dataset: os rótulos
`Allows nulls`, `Feature level`, `Mandatory`, `Optional`, `Conditional` e `Null value allowed`
**não ocorrem nenhuma vez** na página de schema do FOCUS. O único sinal de nulidade publicado é a
anotação textual "Currently null/empty" das seis colunas de §3.1. Isso difere da AWS, cuja
documentação de FOCUS 1.2 publica `Null value allowed: No` por coluna.

| Campo | Tipo | Obrigatório | Unidade | Formato data/hora | Valores permitidos | Descrição | Fonte |
|---|---|---|---|---|---|---|---|
| `BilledCost` | Decimal | sim | — | — | — | A charge serving as the basis for invoicing, inclusive of all reduced rates and discounts while excluding the amortization of upfront charges (one-time or recurring). | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `BillingAccountId` | String | sim | — | — | — | Unique identifier assigned to a billing account by the provider. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `BillingAccountName` | String | sim | — | — | — | Display name assigned to a billing account. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `BillingAccountType` | String | sim | — | — | — | Provider label for the kind of entity the BillingAccountId represents. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `BillingCurrency` | String | sim | currency code | — | — | Currency that a charge was billed in. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `BillingPeriodEnd` | DateTime | sim | — | ISO 8601 UTC `YYYY-MM-DDTHH:mm:ssZ` | — | Exclusive end date and time of the billing period. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `BillingPeriodStart` | DateTime | sim | — | ISO 8601 UTC `YYYY-MM-DDTHH:mm:ssZ` | — | Inclusive start date and time of the billing period. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `CapacityReservationId` | String | sim | — | — | — | Unique identifier assigned to a capacity reservation by the provider. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `CapacityReservationStatus` | String | sim | — | — | — | Indicates whether the charge represents either the consumption of a capacity reservation or when a capacity reservation is unused. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `ChargeCategory` | String | sim | — | — | `Usage`, `Purchase`, `Tax`, `Credit`, `Adjustment` | Highest-level classification of a charge based on the nature of how it is billed. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `ChargeClass` | String | sim | — | — | `Correction` | Indicates whether the row represents a correction to one or more charges invoiced in a previous billing period. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `ChargeDescription` | String | sim | — | — | — | Self-contained summary of the charge's purpose and price. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `ChargeFrequency` | String | sim | — | — | `One-Time`, `Recurring`, `Usage-Based` | Indicates how often a charge will occur. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `ChargePeriodEnd` | DateTime | sim | — | ISO 8601 UTC `YYYY-MM-DDTHH:mm:ssZ` | — | Exclusive end date and time of a charge period. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `ChargePeriodStart` | DateTime | sim | — | ISO 8601 UTC `YYYY-MM-DDTHH:mm:ssZ` | — | Inclusive start date and time of a charge period. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `CommitmentDiscountCategory` | String | sim | — | — | `Spend`, `Usage` | Indicates whether the commitment-based discount identified in the CommitmentDiscountId column is based on usage quantity or cost (aka spend). | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `CommitmentDiscountId` | String | sim | — | — | — | Unique identifier assigned to a commitment-based discount by the provider. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `CommitmentDiscountName` | String | sim | — | — | — | Display name assigned to a commitment-based discount. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `CommitmentDiscountQuantity` | Decimal | sim | — | — | — | Amount of a commitment discount purchased or accounted for in commitment discount related rows that is denominated in Commitment Discount Units. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `CommitmentDiscountStatus` | String | sim | — | — | `Used`, `Unused` | Indicates whether the charge corresponds with the consumption of a commitment-based discount or the unused portion of the committed amount. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `CommitmentDiscountType` | String | sim | — | — | — | Label assigned by the provider to describe the type of commitment-based discount applied to the row. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `CommitmentDiscountUnit` | String | sim | — | — | — | Provider-specified measurement unit indicating how a provider measures the CommitmentDiscountQuantity of a commitment discount. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `ConsumedQuantity` | Decimal | sim | — | — | — | Volume of a given SKU associated with a resource or service used, based on the Consumed Unit. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `ConsumedUnit` | Decimal | sim | — | — | — | Provider-specified measurement unit indicating how a provider measures usage of a given SKU associated with a resource or service. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `ContractedCost` | Decimal | sim | — | — | — | Cost calculated by multiplying contracted unit price and the corresponding Pricing Quantity. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `ContractedUnitPrice` | Decimal | sim | — | — | — | The agreed-upon unit price for a single Pricing Unit of the associated SKU, inclusive of negotiated discounts, if present, while excluding negotiated commitment-based discounts or any other discounts. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `EffectiveCost` | Decimal | sim | — | — | — | The amortized cost of the charge after applying all reduced rates, discounts, and the applicable portion of relevant, prepaid purchases (one-time or recurring) that covered this charge. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `InvoiceId` | String | sim | — | — | — | Unique identifier for the invoice this charge was billed on. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `InvoiceIssuerName` | String | sim | — | — | — | The name of the entity responsible for invoicing for the resources or services consumed. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `ListCost` | Decimal | sim | — | — | — | Cost calculated by multiplying List Unit Price and the corresponding Pricing Quantity. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `ListUnitPrice` | Decimal | sim | — | — | — | Suggested provider-published unit price for a single Pricing Unit of the associated SKU, exclusive of any discounts. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `PricingCategory` | String | sim | — | — | `Standard`, `Dynamic`, `Committed`, `Other` | Describes the pricing model used for a charge at the time of use or purchase. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `PricingCurrency` | String | sim | currency code | — | — | Currency that the charge was priced in by the provider. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `PricingQuantity` | Decimal | sim | — | — | — | Volume of a given SKU associated with a resource or service used or purchased, based on the Pricing Unit. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `PricingUnit` | String | sim | — | — | — | Provider-specified measurement unit for determining unit prices, indicating how the provider rates measured usage and purchase quantities after applying pricing rules like block pricing. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `ProviderName` | String | sim | — | — | `Microsoft` | Name of the entity that made the resources and/or services available for purchase. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `PublisherName` | String | sim | — | — | — | Name of the entity that produced the resources and/or services that were purchased. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `RegionId` | String | sim | — | — | — | Provider-assigned identifier for an isolated geographic area where a resource is provisioned or a service is provided. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `RegionName` | String | sim | — | — | — | Name of an isolated geographic area where a resource is provisioned or a service is provided. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `ResourceId` | String | sim | — | — | — | Unique identifier assigned to a resource by the provider. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `ResourceName` | String | sim | — | — | — | Display name assigned to a resource. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `ResourceType` | String | sim | — | — | — | The kind of resource for which you are being charged. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `ServiceCategory` | String | sim | — | — | — | Highest-level classification of a service based on the core function of the service. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `ServiceName` | String | sim | — | — | — | An offering that can be purchased from a provider (for example, cloud virtual machine, SaaS database, professional services from a systems integrator). | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `ServiceSubcategory` | String | sim | — | — | — | Secondary classification of the ServiceCategory for a service based on its core function. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `SkuId` | String | sim | — | — | — | Unique identifier that defines a provider-supported construct for organizing properties that are common across one or more SKU Prices. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `SkuMeter` | String | sim | — | — | — | Describes the functionality being metered or measured by a particular SKU in a charge. This usually maps to a specific SKU or range of SKUs that have a specific price. Same as MeterName. Not available for some purchases. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `SkuPriceDetails` | String | sim | — | — | — | A set of properties of a SkuPriceId which are meaningful and common to all instances of that SkuPriceId. This column is formatted as a JSON object. Same as AdditionalInfo. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `SkuPriceId` | String | sim | — | — | — | Unique identifier that defines the unit price used to calculate the charge. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `SubAccountId` | String | sim | — | — | — | Unique identifier assigned to a grouping of resources and/or services, often used to manage access and/or cost. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `SubAccountName` | String | sim | — | — | — | Name assigned to a grouping of resources and/or services, often used to manage access and/or cost. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `SubAccountType` | String | sim | — | — | — | Provider label for the kind of entity the SubAccountId represents. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `Tags` | JSON | sim | — | — | — | List of custom key-value pairs applied to a charge defined as a JSON object. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `x_AccountId` | String | sim | — | — | — | Unique identifier for the identity responsible for billing for this subscription. This is your EA enrollment account owner or MOSA account admin. Not applicable to MCA. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `x_AccountName` | String | sim | — | — | — | Name of the identity responsible for billing for this subscription. This is your EA enrollment account owner or MOSA account admin. Not applicable to MCA. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `x_AccountOwnerId` | String | sim | — | — | — | Email address of the identity responsible for billing for this subscription. This is your EA enrollment account owner or MOSA account admin. Not applicable to MCA. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `x_AmortizationClass` | String | sim | — | — | `Principal`, `Amortized Charge` | Indicates how a row relates to amortization to identify and distinguish between the charges before and after amortization is applied. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `x_BilledCostInUsd` | Decimal | sim | USD | — | — | BilledCost in USD. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `x_BilledUnitPrice` | Decimal | sim | — | — | — | Unit price for a single Pricing Unit of the associated SKU that was charged per unit. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `x_BillingAccountId` | String | sim | — | — | — | Unique identifier for the Microsoft billing account. Same as BillingAccountId for EA. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `x_BillingAccountName` | String | sim | — | — | — | Name of the Microsoft billing account. Same as BillingAccountName for EA. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `x_BillingExchangeRate` | Decimal | sim | ratio | — | — | Exchange rate to multiply by when converting from the pricing currency to the billing currency. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `x_BillingExchangeRateDate` | DateTime | sim | — | ISO 8601 UTC `YYYY-MM-DDTHH:mm:ssZ` | — | Date the exchange rate was determined. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `x_BillingProfileId` | String | sim | — | — | — | Unique identifier for the Microsoft billing profile. Same as BillingAccountId for MCA. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `x_BillingProfileName` | String | sim | — | — | — | Name of the Microsoft billing profile. Same as BillingAccountName for MCA. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `x_ContractedCostInUsd` | Decimal | sim | USD | — | — | ContractedCost in USD. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `x_CostAllocationRuleName` | String | sim | — | — | — | Name of the Microsoft Cost Management cost allocation rule that generated this charge. Cost allocation is used to move or split shared charges. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `x_CostCenter` | String | sim | — | — | — | Custom value defined by a billing admin for internal chargeback. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `x_CustomerId` | String | sim | — | — | — | Unique identifier for the Cloud Solution Provider (CSP) customer tenant. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `x_CustomerName` | String | sim | — | — | — | Display name for the Cloud Solution Provider (CSP) customer tenant. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `x_EffectiveCostInUsd` | Decimal | sim | USD | — | — | EffectiveCost in USD. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `x_EffectiveUnitPrice` | Decimal | sim | — | — | — | Unit price for a single Pricing Unit of the associated SKU after applying all reduced rates, discounts, and the applicable portion of relevant, prepaid purchases (one-time or recurring) that covered this charge. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `x_InvoiceIssuerId` | String | sim | — | — | — | Unique identifier for the Cloud Solution Provider (CSP) partner. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `x_InvoiceSectionId` | String | sim | — | — | — | Unique identifier for the MCA invoice section or EA department. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `x_InvoiceSectionName` | String | sim | — | — | — | Display name for the MCA invoice section or EA department. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `x_ListCostInUsd` | Decimal | sim | USD | — | — | ListCost in USD. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `x_PartnerCreditApplied` | String | sim | — | — | — | Indicates when the Cloud Solution Provider (CSP) Partner Earned Credit (PEC) was applied for a charge. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `x_PartnerCreditRate` | String | sim | — | — | — | Rate earned based on the Cloud Solution Provider (CSP) Partner Earned Credit (PEC) applied. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `x_PricingBlockSize` | Decimal | sim | — | — | — | Indicates the number of usage units grouped together for block pricing. This number is usually a part of the PricingUnit. Divide UsageQuantity by PricingBlockSize to get the PricingQuantity. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `x_PricingSubcategory` | String | sim | — | — | — | Describes the kind of pricing model used for a charge within a specific Pricing Category. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `x_PricingUnitDescription` | String | sim | — | — | — | Indicates what measurement type is used by the PricingQuantity, including pricing block size. This is what is used in the price list and/or on the invoice. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `x_PublisherCategory` | String | sim | — | — | — | Indicates whether a charge is from a cloud provider or third-party Marketplace vendor. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `x_PublisherId` | String | sim | — | — | — | Unique identifier of the entity that produced the resources and/or services that were purchased. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `x_ResellerId` | String | sim | — | — | — | Unique identifier for the Cloud Solution Provider (CSP) reseller. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `x_ResellerName` | String | sim | — | — | — | Name of the Cloud Solution Provider (CSP) reseller. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `x_ResourceGroupName` | String | sim | — | — | — | Grouping of resources that make up an application or set of resources that share the same lifecycle (for example, created and deleted together). | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `x_ResourceType` | String | sim | — | — | — | Azure Resource Manager resource type. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `x_ServiceModel` | String | sim | — | — | `IaaS`, `PaaS`, `SaaS` | Indicates what aspects of the service are managed by the provider – infrastructure only, the platform custom code runs on, or the entire service. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `x_ServicePeriodEnd` | DateTime | sim | — | ISO 8601 UTC `YYYY-MM-DDTHH:mm:ssZ` | — | Exclusive end date of the service period applicable for the charge. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `x_ServicePeriodStart` | DateTime | sim | — | ISO 8601 UTC `YYYY-MM-DDTHH:mm:ssZ` | — | Start date of the service period applicable for the charge. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `x_SkuDescription` | String | sim | — | — | — | Description of the SKU that was used or purchased. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `x_SkuDetails` | JSON | sim | — | — | — | Additional information about the SKU. This column is formatted as a JSON object. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `x_SkuIsCreditEligible` | Boolean | sim | — | — | — | Indicates if the charge is eligible for Azure credits | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `x_SkuMeterCategory` | String | sim | — | — | — | Name of the service the SKU falls within. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `x_SkuMeterId` | String | sim | — | — | — | Unique identifier (sometimes a GUID, but not always) for the usage meter. This usually maps to a specific SKU or range of SKUs that have a specific price. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `x_SkuMeterName` | String | sim | — | — | — | Name of the usage meter. This usually maps to a specific SKU or range of SKUs that have a specific price. Not applicable for purchases. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `x_SkuMeterSubcategory` | String | sim | — | — | — | Group of SKU Classes that address the same core need within the SKU Group. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `x_SkuOfferId` | String | sim | — | — | — | Microsoft Cloud subscription type. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `x_SkuOrderId` | String | sim | — | — | — | Unique identifier of the entitlement product for this charge. Same as MCA ProductOrderId. Not applicable for EA. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `x_SkuOrderName` | String | sim | — | — | — | Display name of the entitlement product for this charge. Same as MCA ProductOrderId. Not applicable for EA. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `x_SkuPartNumber` | String | sim | — | — | — | Identifier to help break down specific usage meters. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `x_SkuPlanName` | String | sim | — | — | — | Name of the Marketplace service plan. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `x_SkuRegion` | String | sim | — | — | — | Region that the SKU operated in. This may be different from the resource region. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `x_SkuServiceFamily` | String | sim | — | — | — | Highest-level classification of a SKU based on the core function of the SKU. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `x_SkuTerm` | Number | sim | — | — | — | Number of months a purchase covers. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |
| `x_SkuTier` | String | sim | — | — | — | Pricing tier for the SKU when that SKU supports tiered or graduated pricing. | [schema 1.2-preview](https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview) — 2026-10-14 |

### 3.1 Colunas documentadas como "Currently null/empty"

A página de schema marca explicitamente seis colunas como **"Currently null/empty"** (presentes no
arquivo, mas sem valor na versão 1.2-preview). **A coluna é obrigatória (`required: true`, "sim") e o
valor é que sai vazio** — as duas coisas não se confundem. O simulador **deve emitir a coluna, com
valor nulo**, e não omiti-la. No `.schema.json` essa nulidade é registrada em
`evidence: "null-empty"`. O resumo de conformidade confirma que algumas delas "are not specified in
the Cost Management FOCUS 1.2-preview dataset".

Fontes: https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview e https://learn.microsoft.com/en-us/cloud-computing/finops/focus/conformance-summary — consultadas em 2026-10-14

| Coluna | Situação documentada |
|---|---|
| `CapacityReservationId` | "Currently null/empty." Conformance summary: "not specified in the Cost Management FOCUS 1.2-preview dataset". |
| `CapacityReservationStatus` | "Currently null/empty." Conformance summary: "not specified". |
| `CommitmentDiscountQuantity` | "Currently null/empty." Conformance summary: "not specified". |
| `CommitmentDiscountStatus` | "Currently null/empty." |
| `CommitmentDiscountUnit` | "(Future) Unit for commitment discount. Currently null/empty." |
| `SkuPriceDetails` | "Currently null/empty." Conformance summary: usar `x_SkuDetails` e prefixar as propriedades com `x_`. |

### 3.2 Lacunas e valores divergentes declarados pela Microsoft (conformance summary)

Não são colunas inventadas: são desvios **documentados oficialmente** entre o dataset 1.2-preview e
a especificação FOCUS 1.2. O simulador deve reproduzi-los, não "corrigi-los".

Fonte: https://learn.microsoft.com/en-us/cloud-computing/finops/focus/conformance-summary — consultado em 2026-10-14

| Coluna(s) | Comportamento documentado |
|---|---|
| `ContractedUnitPrice`, `ContractedCost` | São `0` para EA Marketplace, EA reservation usage com cost allocation habilitado, e toda MCA reservation usage. |
| `ListCost`, `ListUnitPrice` | `ListCost` não é suportado e é `0` para EA/MCA Marketplace e para EA/MCA reservation usage. |
| `SkuId`, `SkuPriceId` | Null quando não há preço correspondente no price sheet (ex.: savings plan unused, Marketplace). |
| `PublisherName` | Null para reservation usage, reservation purchases e savings plan unused. |
| `InvoiceId` | Não suportado para contas EA. |
| `ChargeDescription` | Null para savings plan unused e cargas sem SKU de produto direto. |
| `ServiceName` | Vazio para EA Marketplace purchases; vazio para MCA reservation e savings plan purchases, rounding adjustment, MACC shortfall e Azure credit records. |
| `AvailabilityZone` | Não existe no dataset de custos e **a coluna não está incluída** — não deve ser gerada. |
| `CommitmentDiscountId` vs `ResourceId` | `ResourceId` é convertido para minúsculas; `CommitmentDiscountId` não casa exatamente. |
| `ResourceName` | Pode não estar no casing original. |
| `SkuPriceId` | Não identifica um preço único e não tem equivalente no price sheet. |
| `SkuMeter` | Pode diferir para um mesmo `SkuId`. |
| `x_SkuMeterCategory`, `x_SkuMeterSubcategory` | Não normalizados; comprimento máximo avaliado de 355 caracteres (out/2024). |
| `ChargeDescription` | Comprimento máximo não documentado; avaliado em 355 caracteres (out/2024). |
| `Tags` | Tags do provedor não são prefixadas. |

## 4. Campos não comprovados

Nenhuma linha do §3 foi inferida. As entradas abaixo estão marcadas `UNVERIFIED` porque **fontes
oficiais da Microsoft divergem entre si** e nenhuma escolha pode ser feita por conta própria.
Esses itens **não são gerados** pelo simulador até que a divergência seja resolvida.

| Item | Status | Motivo |
|---|---|---|
| `x_PricingCurrency` | **UNVERIFIED** | Aparece como **coluna 79** da página de schema ("Currency used for all price columns."), mas está **ausente** do metadata JSON oficial `FocusCost_1.2-preview.json` (106 colunas), linkado pela própria página de metadados. Não há fonte única autoritativa para presença, tipo e ordem. |
| Ordem das colunas | **UNVERIFIED** | A página de schema enumera 105 colunas (1–105); o metadata JSON oficial enumera 106. As ordens divergem a partir do índice 73: `x_InvoiceIssuerId` e `x_SkuTerm` existem no JSON e não na página; `x_PricingCurrency` existe na página e não no JSON; e `x_SkuPlanName`/`x_SkuPartNumber` aparecem trocados (101/102). Nenhuma ordem única é citável. |
| `x_InvoiceIssuerId` | **UNVERIFIED (tipo)** | Presente no metadata JSON oficial como `String`, mas **não listado** na página de schema da versão 1.2-preview. O tipo consta apenas do metadata JSON. |
| `x_SkuTerm` | **UNVERIFIED (presença na 1.2-preview)** | Presente no metadata JSON oficial (`Number`) e na tabela "FocusCost 1.2-preview" da página de metadados, mas **ausente** da página de schema 1.2-preview. Divergência entre fontes oficiais quanto à presença. |
| Precisão/scale numérica | **UNVERIFIED** | A especificação FOCUS 1.2 delega a precisão ao provedor ("should be part of a data definition published by the provider") e a Microsoft **não publica** precisão ou scale por coluna em nenhuma página consultada. O tipo `Decimal` é o único nível comprovado. |

## 5. Divergências conhecidas

| # | Divergência | Fonte A | Fonte B | Tratamento |
|---|---|---|---|---|
| 1 | **105 vs 106 colunas.** A página de schema numera 1–105; o metadata JSON oficial tem 106. | https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus#version-12-preview (105) | `FocusCost_1.2-preview.json` de https://github.com/microsoft/finops-toolkit/releases/latest/download/dataset-metadata.zip (106) | Registrado, sem escolha unilateral. O `.schema.json` acompanha o metadata JSON (106) por ser o artefato gerado pela Microsoft; os três itens divergentes ficam em §4. |
| 2 | **`ConsumedUnit` tipada como `Decimal`.** | Página de metadados e metadata JSON: `ConsumedUnit` → `Decimal` | Especificação FOCUS 1.2: "ConsumedUnit MUST be of type String" — https://github.com/FinOps-Open-Cost-and-Usage-Spec/FOCUS_Spec/blob/v1.2/specification/columns/consumedunit.md | Registrado. O `.schema.json` segue o tipo declarado pela Microsoft e anota a não conformidade. |
| 3 | **`SkuPriceDetails` como `String` vs "JSON object".** | Metadata JSON: `SkuPriceDetails` → `String` | Página de schema: "This column is formatted as a JSON object." | Registrado. Tipo oficial `String`, com o conteúdo JSON descrito. |
| 4 | **`x_SkuDetails` a ser removida.** | Página de schema: "(To be removed when SkuPriceDetails is ready)" | — | Registrado; segue presente e obrigatória na 1.2-preview. |
| 5 | **Índice de schema desatualizado.** O índice lista EA `2023-12-01-preview` como mais recente, mas a página EA documenta também a versão **2024-08-01**. | https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/schema-index | https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-ea | Registrado; afeta o dataset clássico (ver `cost-management-export-cost-details.md`), não o FOCUS. |

## 6. Regra de ouro aplicada

- Toda linha do §3 tem nome, tipo e descrição vindos do **metadata JSON oficial da Microsoft** e URL da seção que a documenta, com data de consulta 2026-10-14.
- Nada foi preenchido por memória ou inferência.
- Onde fontes oficiais divergem, o item foi para §4 como `UNVERIFIED` e **não é gerado**.
