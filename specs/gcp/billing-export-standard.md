# GCP — Cloud Billing export to BigQuery — Standard usage cost data

## 1. Identificação

- **Nome oficial da superfície (EN):** "Structure of Standard data export" / *standard usage cost data*
  (Google também escreve "standard usage cost table").
- **Documento oficial (schema):**
  - Título: *Structure of Standard data export*
  - URL: https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage
  - Data de consulta: **2026-10-14**
- **Documento oficial (nome da tabela / frequência / disponibilidade):**
  - Título: *Understand the Cloud Billing data tables in BigQuery*
  - URL: https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables
  - Data de consulta: **2026-10-14**
- **Versão/schema de referência:** não versionado pelo provedor. A própria documentação
  declara que *"The table schema for the Cloud Billing data exports can change"*
  ([limitations](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables)).
  O identificador estável da superfície é o **nome da tabela BigQuery** (ver §2).
- **Escopo deste arquivo:** apenas a tabela de *standard usage cost data*.
  Os campos que existem **somente** no export detalhado estão em
  `billing-export-detailed.md`.

## 2. Mecanismo e entrega

| Item | Valor documentado | Fonte |
|---|---|---|
| Mecanismo | Export do Cloud Billing direto para uma **tabela do BigQuery** (não há bucket/arquivo intermediário para o cliente). | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables |
| Nome exato da tabela | `gcp_billing_export_v1_<BILLING_ACCOUNT_ID>` | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables |
| Nome canônico completo | `project.dataset.<BQ_table_name>`; a doc usa o exemplo `my-billing-project.my_billing_dataset.gcp_billing_export_resource_v1_010101-F0FFF0-10X10X` (detalhado) e `project-ID.dataset.gcp_billing_export_v1_XXXXXX-XXXXXX-XXXXXX` (standard) para o mesmo formato `project.dataset.BQ_table_name`. | https://docs.cloud.google.com/billing/docs/how-to/bq-examples |
| Dataset | Escolhido pelo usuário. Localizações suportadas: multi-região `US`/`EU` e um subconjunto de regiões (Americas, Asia Pacific, Europe, Middle East — lista fechada na doc). Localização é definida na criação e **não pode ser alterada**. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables |
| Formato físico do dado | **Não documentado.** A doc descreve a *tabela* BigQuery (colunas e tipos); não descreve arquivo, compressão, encoding, delimitador nem cabeçalho. Não afirmar nada além disso. | — (ver §4) |
| Particionamento | **Não documentado.** A página de schema do standard **não menciona** particionamento nem clustering. Ver §4 (UNVERIFIED) e §5 (divergência: os exemplos de query oficiais usam `_PARTITIONTIME`). | — |
| Clustering | **Não documentado** para o export standard. | — |
| Frequência de carga | "regular intervals (there are no delivery or latency guarantees)"; dados exportados em ordem cronológica; backfill retroativo de até ~5 dias quando o dataset é multi-região. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables |
| Disponibilidade retroativa | Dataset multi-região (`US`/`EU`): dados desde o início do mês anterior. Dataset de região suportada: somente a partir da data de habilitação do export. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables |
| ACID | "BigQuery loads are ACID compliant" — não há leitura parcial durante a carga. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables |
| Conteúdo de recursos | O standard **não** inclui dado de custo em nível de recurso (ex.: VM ou SSD). Para isso, habilite o export detalhado. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage |

**Restrição de escrita:** as tabelas não devem ser modificadas
("Don't modify these tables, such as by adding a column or manually re-creating the tables").
Fonte: https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables

## 3. Campos

Uma linha por campo documentado. `Fonte` = URL com o anchor exato da seção que documenta
o campo (quando a doc dá anchor próprio; caso contrário, o anchor/grupo que contém o campo).
Data de consulta dos 71 campos abaixo: **2026-10-14**.

| Campo | Tipo | Obrigatório | Unidade | Formato data/hora | Valores permitidos | Descrição | Fonte |
|---|---|---|---|---|---|---|---|
| `billing_account_id` | String | sim | — | — | — | ID da conta de faturamento Cloud Billing associada ao uso. Para revendedor: em subconta, é o ID da subconta, não o da conta pai. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#billing_account_id |
| `invoice.month` | String | sim | — | — | `YYYYMM` (ex.: `"201901"`) | Ano e mês da fatura que inclui os line items. Primeiro mês completo: junho/2018. O mês da fatura pode diferir do mês de uso. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#invoice-month |
| `invoice.publisher_type` | String | não | — | — | `GOOGLE`, `PARTNER` | Publisher da transação: primeira parte (Google) ou terceira parte (parceiro). | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#invoice-publisher_type |
| `cost_type` | String | sim | — | — | `regular`, `tax`, `adjustment`, `rounding error` (grafia do texto; os exemplos de query exibem `regular`, `rounding_error`, `tax`, `adjustment`) | Tipo de custo que o line item representa. Primeiro mês completo: janeiro/2019. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#cost_type |
| `service.id` | String | sim | — | — | — | ID do serviço associado ao uso. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#service-id |
| `service.description` | String | sim | — | — | — | Serviço Google Cloud que reportou o dado. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#service-description |
| `sku.id` | String | sim | — | — | — | ID do recurso usado pelo serviço; mapeia para preços de lista (pricing pages, Pricing Table report, Cloud Billing Catalog API). | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#sku-id |
| `sku.description` | String | sim | — | — | — | Descrição do tipo de recurso usado (ex.: `Standard Storage US`). | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#sku-description |
| `usage_start_time` | Timestamp | sim | — | Timestamp BigQuery (UTC); janela de uso **horária** | — | Início da janela horária de uso na qual o custo foi calculado. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#usage_start_time |
| `usage_end_time` | Timestamp | sim | — | Timestamp BigQuery (UTC); janela de uso **horária** | — | Fim da janela horária de uso na qual o custo foi calculado. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#usage_end_time |
| `project` | Struct | não | — | — | — | Struct com ID, number, name, ancestry_numbers e labels do projeto. Pode faltar para uso nas primeiras 24 h de um projeto novo. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#project |
| `project.id` | String | não | — | — | — | ID do projeto que gerou o dado. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#project-id |
| `project.number` | String | não | — | — | — | Identificador único, anonimizado e gerado internamente para o projeto. Primeiro dia completo: 2020-10-29. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#project-number |
| `project.name` | String | não | — | — | — | Nome do projeto que gerou o dado. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#project-name |
| `project.ancestry_numbers` | String | não | — | — | — | Ancestrais na hierarquia de recursos, ex.: `/ParentOrgNumber/ParentFolderNumber/`. Primeiro mês completo: janeiro/2019. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#project_ancestry |
| `project.ancestors` | Struct | não | — | — | — | Estrutura e valor da hierarquia de recursos do line item (projeto, pastas, organizações), ordenada de nó para raiz. Primeiro mês completo: abril/2022. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#project-ancestors |
| `project.ancestors.resource_name` | String | não | — | — | Formato `resourceType/resourceNumber` | Nome de recurso relativo de cada ancestral; visão mais completa que `project.ancestry_numbers`. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#project-ancestors-resource_name |
| `project.ancestors.display_name` | String | não | — | — | — | Nome criado pelo usuário para o recurso no console. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#project-ancestors-display_name |
| `project.labels` | Struct | não | — | — | — | Campos que descrevem o label do projeto (`key`, `value`). | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#project-labels |
| `project.labels.key` | String | não | — | — | — | Parte `key` do par chave-valor do label do projeto onde ocorreu o uso. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#project-labels-key |
| `project.labels.value` | String | não | — | — | — | Parte `value` do par chave-valor do label do projeto onde ocorreu o uso. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#project-labels-value |
| `labels` | Struct | não | — | — | — | Campos que descrevem o label do **recurso** (`key`, `value`). | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#labels |
| `labels.key` | String | não | — | — | — | Parte `key` do label do recurso onde ocorreu o uso. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#labels-key |
| `labels.value` | String | não | — | — | — | Parte `value` do label do recurso onde ocorreu o uso. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#labels-value |
| `system_labels` | Struct | não | — | — | — | Campos que descrevem o system label (`key`, `value`). | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#system-labels |
| `system_labels.key` | String | não | — | — | Valores documentados: `compute.googleapis.com/machine_spec`, `compute.googleapis.com/cores`, `compute.googleapis.com/memory`, `compute.googleapis.com/is_unused_reservation`, `compute.googleapis.com/reservation_name`, `compute.googleapis.com/reservation_project_id`, `storage.googleapis.com/object_state` | Parte `key` do system label gerado pelo sistema. Primeiro dia completo: 2018-09-18. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#system_labels-key |
| `system_labels.value` | String | não | — | — | — | Parte `value` do system label gerado pelo sistema. Primeiro dia completo: 2018-09-18. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#system_labels-value |
| `location.location` | String | não | — | — | `global` ou multi-região / país / região / zona | Localização do uso. Primeiro dia completo: 2018-09-18. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#location-location |
| `location.country` | String | não | — | — | Ex.: `US` | País do uso, quando `location.location` é país, região ou zona. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#location-country |
| `location.region` | String | não | — | — | Ex.: `us-central1` | Região do uso, quando `location.location` é região ou zona. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#location-region |
| `location.zone` | String | não | — | — | Ex.: `us-central1-a` | Zona do uso, quando `location.location` é zona. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#location-zone |
| `cost` | Float | sim | Moeda de `currency` (ver §3.1) | — | — | Custo conforme o modelo de consumo aplicável, incluindo descontos negociados refletidos no preço customizado do contrato vinculado à conta (se houver). **Não** é o líquido: ver §3.1. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#cost |
| `currency` | String | sim | — | — | Código de moeda (doc aponta para "Local Currency for Billing and Payments") | Moeda na qual o custo é faturado. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#currency |
| `currency_conversion_rate` | Float | sim | taxa USD → moeda local | — | — | Taxa de câmbio de USD para a moeda local. `cost ÷ currency_conversion_rate` = custo em USD. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#currency_conversion_rate |
| `usage.amount` | Float | não | unidade de `usage.unit` | — | — | Quantidade de `usage.unit` usada. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#usage-amount |
| `usage.unit` | String | não | — | — | Ex.: `byte-seconds` | Unidade base em que o uso do recurso é medido. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#usage-unit |
| `usage.amount_in_pricing_units` | Float | não | unidade de `usage.pricing_unit` | — | — | Quantidade de `usage.pricing_unit` usada. Primeiro dia completo: 2018-01-22. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#usage-amount_in_pricing_units |
| `usage.pricing_unit` | String | não | — | — | — | Unidade em que o uso é medido, conforme a Cloud Billing Catalog API. Primeiro dia completo: 2018-01-22. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#usage-pricing_unit |
| `credits` | Struct | não | — | — | — | Struct com estrutura e valor dos créditos associados a SKUs Google Cloud e Google Maps Platform. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#credits |
| `credits.id` | String | não | — | — | ID alfanumérico único (ex.: `12-b34-c56-d78`) **ou** descrição do tipo de crédito (ex.: `Committed Usage Discount: CPU`); vazio se o SKU não tem crédito | Se presente, indica que um crédito está associado ao SKU. Primeiro dia completo: 2020-09-10. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#credits-id |
| `credits.full_name` | String | não | — | — | Ex.: `Free trial credit`, `Spend-based committed use discount`; vazio quando `credits.id` é uma descrição de tipo | Nome do crédito associado ao SKU (descrição legível de um `credits.id` alfanumérico). Primeiro dia completo: 2020-09-10. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#credits-full_name |
| `credits.type` | String | não | — | — | `FEE_UTILIZATION_OFFSET`, `COMMITTED_USAGE_DISCOUNT_DOLLAR_BASE`, `COMMITTED_USAGE_DISCOUNT`, `DISCOUNT`, `FREE_TIER`, `PROMOTION`, `RESELLER_MARGIN`, `SUBSCRIPTION_BENEFIT`, `SUSTAINED_USAGE_DISCOUNT` | Propósito/origem do `credits.id`. Primeiro dia completo: 2020-09-10. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#credits-type |
| `credits.name` | String | não | — | — | — | Descrição do crédito aplicado à conta de faturamento. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#credits-name |
| `credits.amount` | Float | não | Moeda de `currency` | — | — | Valor do crédito aplicado ao uso. Ver §3.1 (sinal). | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#credits-amount |
| `adjustment_info` | Struct | não | — | — | — | Detalhes de um ajuste a line items de custo; presente apenas se o line item foi gerado por modificação de faturamento. Primeiro dia completo: 2020-10-29. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#adjustment_info |
| `adjustment_info.id` | String | não | — | — | — | ID único de todos os ajustes associados a uma emissão. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#adjustment_info-id |
| `adjustment_info.description` | String | não | — | — | — | Descrição do ajuste e de sua causa. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#adjustment_info-description |
| `adjustment_info.type` | String | não | — | — | `USAGE_CORRECTION`, `PRICE_CORRECTION`, `METADATA_CORRECTION`, `GOODWILL`, `SALES_BASED_GOODWILL`, `SLA_VIOLATION`, `BALANCE_TRANSFER`, `ACCOUNT_CLOSURE`, `GENERAL_ADJUSTMENT` | Tipo do ajuste. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#adjustment_info-type |
| `adjustment_info.mode` | String | não | — | — | `PARTIAL_CORRECTION`, `COMPLETE_NEGATION_WITH_REMONETIZATION`, `COMPLETE_NEGATION`, `MANUAL_ADJUSTMENT` | Como o ajuste foi emitido. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#adjustment_info-mode |
| `export_time` | Timestamp | sim | — | Timestamp BigQuery (UTC) | — | Tempo de processamento associado a um append do dado; sempre aumenta a cada novo export. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#export_time |
| `tags` | Struct | não | — | — | — | Campos que descrevem a tag (`key`, `value`, `inherited`, `namespace`). Primeiro mês completo: outubro/2022. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#tags-struct |
| `tags.key` | String | não | — | — | — | Nome curto (display name) da chave da tag. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#tags-key |
| `tags.value` | String | não | — | — | — | Recurso(s) anexado(s) a `tags.key`; no máximo um valor por chave por recurso em um dado momento. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#tags-value |
| `tags.inherited` | Boolean | não | — | — | `true` / `false` | Indica se o binding da tag é herdado (`true`) ou direto/não herdado (`false`). | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#tags-inherited |
| `tags.namespace` | String | não | — | — | — | Hierarquia de recursos que define chave e valores da tag; combinável com os nomes curtos para formar o nome globalmente único. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#tags-namespace |
| `cost_at_list` | Float | não | Moeda de `currency` | — | — | Custo a preço de lista conforme o modelo de consumo padrão. Primeiro dia completo: 2023-06-29. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#cost_at_list |
| `transaction_type` | String | não | — | — | `GOOGLE = 1`, `THIRD_PARTY_RESELLER = 2`, `THIRD_PARTY_AGENCY = 3` | Tipo de transação do vendedor. Preenchido para line items com `cost_type = regular`; pode faltar nos outros `cost_type`. Primeiro dia completo: 2023-08-22. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#transaction_type |
| `seller_name` | String | não | — | — | — | Nome legal do vendedor; preenchido em line items de Marketplace. Primeiro dia completo: 2023-08-22. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#seller_name |
| `price` | Struct | não | — | — | — | Campos de estrutura e valores dos preços cobrados pelo uso. Primeiro dia completo: **2025-07-15** no export standard (no detalhado, 2023-04-13). | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#price-struct |
| `price.list_price` | Numeric | não | Moeda por `price.unit` | — | — | Preço de lista do SKU conforme o modelo de consumo padrão. Primeiro dia completo: 2025-07-15. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#price-list_price |
| `price.effective_price_default` | Numeric | não | Moeda por `price.unit` | — | — | Preço do SKU no modelo de consumo padrão, incluindo descontos negociados do contrato (se houver). Primeiro dia completo: 2025-07-15. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#price-effective_price_default |
| `price.list_price_consumption_model` | Numeric | não | Moeda por `price.unit` | — | — | Preço de lista do SKU no modelo de consumo aplicável, antes de descontos negociados. Primeiro dia completo: 2025-07-15. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#price-list_price_consumption_model |
| `price.effective_price` | Numeric | não | Moeda por `price.unit` | — | — | Preço do SKU no modelo de consumo aplicável, incluindo descontos negociados. Standard: primeiro dia completo 2025-07-15; detalhado: 2023-04-13. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#price-effective_price |
| `price.tier_start_amount` | Numeric | não | unidades de pricing | — | — | Limite inferior de unidades da faixa de preço (pricing tier) do SKU. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#price-tier_start_amount |
| `price.unit` | String | não | — | — | — | Unidade de uso na qual o preço é especificado e o uso é medido. Standard: primeiro dia completo 2025-07-15; detalhado: 2023-04-13. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#price-unit |
| `price.pricing_unit_quantity` | Numeric | não | — | — | Ex.: `1000000` para "$1 per 1000000 Bytes" | Quantidade da unidade de precificação do SKU. Standard: 2025-07-15; detalhado: 2023-04-13. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#price-pricing_unit_quantity |
| `cost_at_effective_price_default` | Numeric | não | Moeda de `currency` | — | — | Custo no modelo de consumo padrão incluindo descontos negociados do contrato (se houver). Primeiro dia completo: 2025-07-15. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#cost_at_effective_price_default |
| `cost_at_list_consumption_model` | Numeric | não | Moeda de `currency` | — | — | Custo no modelo de consumo aplicável, antes de descontos negociados. Primeiro dia completo: 2025-07-15. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#cost_at_list_consumption_model |
| `consumption_model` | Struct | não | — | — | — | Campos que descrevem o modelo de consumo aplicável. Primeiro dia completo: 2025-07-15. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#consumption_model |
| `consumption_model.id` | String | não | — | — | — | ID do modelo de consumo. Primeiro dia completo: 2025-07-15. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#consumption_model-id |
| `consumption_model.description` | String | não | — | — | — | Descrição do modelo de consumo. Primeiro dia completo: 2025-07-15. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#consumption_model-description |

**Total: 71 campos** (contando as structs e seus subcampos como entradas próprias, que é como a
documentação os lista).

### 3.1 Semântica de moeda, unidade e sinal dos créditos

O que **está** documentado:

- `cost`: "Cost per the applicable consumption model inclusive of any negotiated discounts
  reflected in the custom pricing in the contract linked to your Cloud Billing account
  (if applicable)." — ou seja, `cost` é o valor **antes** da aplicação dos créditos.
  Fonte: https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#cost
- A moeda é dada por `currency` ("The currency that the cost is billed in"), e
  `currency_conversion_rate` converte: `cost ÷ currency_conversion_rate` = custo em USD.
  Fontes: [#currency](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#currency),
  [#currency_conversion_rate](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#currency_conversion_rate).
- O **líquido** é documentado apenas por **query de exemplo**, não como coluna:
  `SELECT invoice.month, SUM(cost) + SUM(IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c), 0)) AS total`
  (calculado como "regular costs, taxes, adjustments, and rounding errors").
  Fonte: https://docs.cloud.google.com/billing/docs/how-to/bq-examples
- O sinal de `credits.amount`: **a documentação do campo não afirma o sinal**. O que existe é
  (a) a fórmula oficial `SUM(cost) + SUM(credits.amount)` para obter o total da fatura, e
  (b) o exemplo oficial "Query costs and credits by project" cuja coluna `total_credits`
  exibe valores negativos (ex.: `-4.763796`). Ambos em
  https://docs.cloud.google.com/billing/docs/how-to/bq-examples
  → Tratado em §5 (divergência/ambiguidade), **não** afirmado como contrato de geração.
- Precisão: os exemplos oficiais mostram `cost` como Float sujeito a erro de ponto flutuante, e
  recomendam `CAST(cost AS NUMERIC)`/micros para exatidão.
  Fonte: https://docs.cloud.google.com/billing/docs/how-to/bq-examples

## 4. Campos não comprovados

| Item | Status | Motivo |
|---|---|---|
| Particionamento da tabela standard (coluna/expressão de partição, granularidade) | **UNVERIFIED** | A página *Structure of Standard data export* não menciona partição; a página *Understand the Cloud Billing data tables in BigQuery* também não. Nenhuma página oficial consultada declara a chave de particionamento do `gcp_billing_export_v1_*`. |
| Clustering da tabela standard (colunas, ordem) | **UNVERIFIED** | Mesma ausência de documentação. |
| Formato físico/arquivo (Parquet/CSV/etc.), compressão, encoding, delimitador, cabeçalho | **UNVERIFIED** | A entrega é uma tabela BigQuery; a documentação oficial não descreve formato de arquivo para esta superfície. |
| Schema de manifesto/metadados | **UNVERIFIED (inexistente)** | A superfície é uma tabela gerenciada do BigQuery; não há manifesto emitido ao cliente na documentação. |
| Sinal (positivo/negativo) de `credits.amount` como contrato documentado | **UNVERIFIED** | Só é inferível das queries de exemplo, não de afirmação textual no schema. Ver §5. |
| Campo dedicado de custo líquido (ex.: `net_cost`) na tabela | **UNVERIFIED** | Não consta da tabela de schema; a doc calcula o líquido por query. |
| Valores de `pricing_unit`/`usage.unit` como enumeração fechada | **UNVERIFIED** | A doc dá exemplos (`byte-seconds`) e remete à Cloud Billing Catalog API, sem lista fechada. |
| Formato textual exato de timestamps (ex.: `YYYY-MM-DDTHH:MM:SSZ` vs. microssegundos) | **UNVERIFIED** | O tipo é declarado como Timestamp e a doc remete ao "timestamp data types" do BigQuery; nenhum padrão de string exato é afirmado para a coluna. Os exemplos de query oficiais exibem `2025-09-16 00:00:00.000000 UTC`. |

## 5. Divergências conhecidas

1. **`_PARTITIONTIME` aparece só em exemplos.** Os exemplos de query oficiais para a tabela
   detalhada usam `DATE(TIMESTAMP_TRUNC(t._PARTITIONTIME, DAY))` e os do export de preços usam
   `WHERE DATE(_PARTITIONTIME) = "2020-07-20"`, com o texto explicando que
   "_PARTITIONTIME is a field auto-generated by BigQuery and represents the date that the data
   belongs to". Para a tabela **standard**, nenhuma página oficial consultada usa
   `_PARTITIONTIME` nem declara particionamento.
   Fontes: https://docs.cloud.google.com/billing/docs/how-to/bq-examples e
   https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/pricing-data.
   → Não promovemos isso a contrato do export standard. Ver §4.

2. **`cost_type`: grafia divergente entre texto e exemplos.** O schema descreve
   "regular, tax, adjustment, or rounding error" (com espaço);
   os resultados de exemplo mostram `regular`, `rounding_error`, `tax`, `adjustment`.
   Fontes: https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#cost_type
   e https://docs.cloud.google.com/billing/docs/how-to/bq-examples.
   → Registrado dos dois lados; não escolhemos.

3. **Documentação ambígua sobre datas.** A doc afirma que "*qualquer* dos exports Cloud Billing
   pode mudar de schema" e, ao mesmo tempo, exibe datas de "primeiro dia/mês completo" por campo.
   O simulador deve tratar a lista acima como a fotografia de 2026-10-14.

4. **`price.*` está no standard desde 2025-07-15.** Os subcampos de `price` são documentados na
   mesma tabela do standard, com nota explícita de que o export **standard** só os traz a partir
   de 2025-07-15, enquanto o detalhado os traz desde 2023-04-13. Não confundir
   "campo exclusivo do detalhado" com "campo com data de início diferente".
   Fonte: https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#price-struct

5. **Citações de "Available system labels" e "About labels"** estão na mesma página do schema,
   mas em seções próprias, sem anchor por campo. As URLs de `system_labels.*` acima apontam para
   os anchors dos campos; a lista de valores de `system_labels.key` vem de
   https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage#available_system_labels.
