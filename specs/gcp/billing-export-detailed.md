# GCP — Cloud Billing export to BigQuery — Detailed usage cost data

## 1. Identificação

- **Nome oficial da superfície (EN):** "Structure of Detailed data export" / *detailed usage cost data*
  (Google também escreve "detailed usage cost table").
- **Documento oficial (schema):**
  - Título: *Structure of Detailed data export*
  - URL: https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage
  - Data de consulta: **2026-10-14**
- **Documento oficial (nome da tabela / frequência / disponibilidade):**
  - Título: *Understand the Cloud Billing data tables in BigQuery*
  - URL: https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables
  - Data de consulta: **2026-10-14**
- **Versão/schema de referência:** não versionado pelo provedor; sujeito a mudança
  ("The table schema for the Cloud Billing data exports can change").
- **Relação com o export standard:** *"The exported detailed usage cost data includes all of the
  fields and information contained in the standard usage cost data."*
  Fonte: https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage
  → este arquivo **repete** os 71 campos comuns (mesmos tipos e anchors próprios) e marca
  explicitamente os **9 campos que só existem no detalhado** (§3.2).

## 2. Mecanismo e entrega

| Item | Valor documentado | Fonte |
|---|---|---|
| Mecanismo | Export do Cloud Billing direto para uma **tabela do BigQuery**. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables |
| Nome exato da tabela | `gcp_billing_export_resource_v1_<BILLING_ACCOUNT_ID>` | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables |
| Nome canônico completo | `project.dataset.BQ_table_name`; exemplo oficial `my-billing-project.my_billing_dataset.gcp_billing_export_resource_v1_010101-F0FFF0-10X10X` | https://docs.cloud.google.com/billing/docs/how-to/bq-examples |
| Dataset | Escolhido pelo usuário; mesmas regras de localização do standard (multi-região `US`/`EU` + subconjunto de regiões). | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables |
| Formato físico do dado | **Não documentado** (a superfície é a tabela BigQuery). Ver §4. | — |
| Particionamento | **Não declarado** na página de schema. Os exemplos oficiais de query desta mesma página usam `DATE(TIMESTAMP_TRUNC(t._PARTITIONTIME, DAY))`, e a doc de preços explica que `_PARTITIONTIME` é um campo auto-gerado pelo BigQuery com a data à qual o dado pertence. Ver §5. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage , https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/pricing-data |
| Clustering | **Não documentado.** | — |
| Frequência de carga | Igual ao standard: intervalos regulares, sem garantia de entrega/latência; ordem cronológica; backfill até ~5 dias em dataset multi-região. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables |
| Conteúdo exclusivo | Dados de custo em **nível de recurso** (ex.: VM, SSD) — campos `resource.*` — e metadados de compromisso (`subscription.*`). | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage |
| Serviços com granularidade de recurso | Lista fechada documentada: AlloyDB for PostgreSQL, App Engine, BigQuery, Bigtable, Cloud Data Fusion, Cloud Deploy, Cloud Run functions, Cloud Logging, Cloud Run, Cloud SQL, Cloud Storage, Compute Engine, Dataflow, Managed Service for Apache Spark Metastore, Firestore and Datastore, Google Kubernetes Engine (GKE), Managed Microsoft AD, Memorystore for Redis, Pub/Sub, Secret Manager, Spanner. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#identify_granular_cost_data_by_service |
| GKE | Para ver custos granulares de cluster GKE é necessário **habilitar GKE cost allocation**; os dados não são retroativos a partir da habilitação. Identificação por `labels.key` com chaves `goog-fleet-project`, `goog-k8s-cluster-location`, `goog-k8s-cluster-name`, `goog-k8s-node-pool-name`, `k8s-namespace`, `k8s-namespace-labels`, `k8s-workload-name`, `k8s-workload-type`, `k8s-label`. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#identify_granular_cost_data_by_service |
| Restrição de escrita | "Don't modify these tables, such as by adding a column or manually re-creating the tables." | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables |

## 3. Campos

### 3.1 Campos comuns ao standard (mesmos nomes, tipos e anchors)

| Campo | Tipo | Obrigatório | Unidade | Formato data/hora | Valores permitidos | Descrição | Fonte |
|---|---|---|---|---|---|---|---|
| `billing_account_id` | String | sim | — | — | — | ID da conta de faturamento associada ao uso. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#billing_account_id |
| `invoice.month` | String | sim | — | — | `YYYYMM` | Ano e mês da fatura. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#invoice-month |
| `invoice.publisher_type` | String | não | — | — | `GOOGLE`, `PARTNER` | Publisher da transação. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#invoice-publisher_type |
| `cost_type` | String | sim | — | — | `regular`, `tax`, `adjustment`, `rounding error` (texto do schema) | Tipo de custo do line item. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#cost_type |
| `service.id` | String | sim | — | — | — | ID do serviço. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#service-id |
| `service.description` | String | sim | — | — | — | Serviço que reportou o dado. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#service-description |
| `sku.id` | String | sim | — | — | — | ID do recurso/SKU usado pelo serviço. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#sku-id |
| `sku.description` | String | sim | — | — | — | Descrição do tipo de recurso usado. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#sku-description |
| `usage_start_time` | Timestamp | sim | — | Timestamp BigQuery (UTC), janela horária | — | Início da janela horária de uso. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#usage_start_time |
| `usage_end_time` | Timestamp | sim | — | Timestamp BigQuery (UTC), janela horária | — | Fim da janela horária de uso. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#usage_end_time |
| `project` | Struct | não | — | — | — | Struct do projeto. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#project |
| `project.id` | String | não | — | — | — | ID do projeto. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#project-id |
| `project.number` | String | não | — | — | — | Número anonimizado único do projeto. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#project-number |
| `project.name` | String | não | — | — | — | Nome do projeto. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#project-name |
| `project.ancestry_numbers` | String | não | — | — | — | Ancestrais na hierarquia de recursos. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#project_ancestry |
| `project.ancestors` | Struct | não | — | — | — | Hierarquia do line item (projeto, pastas, organização). | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#project-ancestors |
| `project.ancestors.resource_name` | String | não | — | — | `resourceType/resourceNumber` | Nome de recurso relativo do ancestral. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#project-ancestors-resource_name |
| `project.ancestors.display_name` | String | não | — | — | — | Nome de exibição do ancestral. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#project-ancestors-display_name |
| `project.labels` | Struct | não | — | — | — | Label do projeto. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#project-labels |
| `project.labels.key` | String | não | — | — | — | Chave do label do projeto. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#project-labels-key |
| `project.labels.value` | String | não | — | — | — | Valor do label do projeto. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#project-labels-value |
| `labels` | Struct | não | — | — | — | Label do recurso. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#labels |
| `labels.key` | String | não | — | — | — | Chave do label do recurso. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#labels-key |
| `labels.value` | String | não | — | — | — | Valor do label do recurso. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#labels-value |
| `system_labels` | Struct | não | — | — | — | System label (key, value). | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#system-labels |
| `system_labels.key` | String | não | — | — | Mesmos valores documentados no standard | Chave do system label. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#system_labels-key |
| `system_labels.value` | String | não | — | — | — | Valor do system label. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#system_labels-value |
| `location.location` | String | não | — | — | — | Localização do uso. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#location-location |
| `location.country` | String | não | — | — | Ex.: `US` | País do uso. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#location-country |
| `location.region` | String | não | — | — | Ex.: `us-central1` | Região do uso. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#location-region |
| `location.zone` | String | não | — | — | Ex.: `us-central1-a` | Zona do uso. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#location-zone |
| `cost` | Float | sim | Moeda de `currency` | — | — | Custo conforme o modelo de consumo aplicável, incluindo descontos negociados; antes dos créditos (§3.3). | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#cost |
| `currency` | String | sim | — | — | — | Moeda de faturamento. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#currency |
| `currency_conversion_rate` | Float | sim | taxa USD → moeda local | — | — | `cost ÷ currency_conversion_rate` = custo em USD. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#currency_conversion_rate |
| `usage.amount` | Float | não | `usage.unit` | — | — | Quantidade de `usage.unit` usada. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#usage-amount |
| `usage.unit` | String | não | — | — | Ex.: `byte-seconds` | Unidade base de medida do uso. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#usage-unit |
| `usage.amount_in_pricing_units` | Float | não | `usage.pricing_unit` | — | — | Quantidade de `usage.pricing_unit` usada. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#usage-amount_in_pricing_units |
| `usage.pricing_unit` | String | não | — | — | — | Unidade de medida segundo a Cloud Billing Catalog API. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#usage-pricing_unit |
| `credits` | Struct | não | — | — | — | Créditos associados a SKUs. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#credits |
| `credits.id` | String | não | — | — | ID alfanumérico **ou** descrição do tipo de crédito | Indica crédito associado ao SKU. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#credits-id |
| `credits.full_name` | String | não | — | — | Ex.: `Free trial credit` | Nome legível do crédito. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#credits-full_name |
| `credits.type` | String | não | — | — | `FEE_UTILIZATION_OFFSET`, `COMMITTED_USAGE_DISCOUNT_DOLLAR_BASE`, `COMMITTED_USAGE_DISCOUNT`, `DISCOUNT`, `FREE_TIER`, `PROMOTION`, `RESELLER_MARGIN`, `SUBSCRIPTION_BENEFIT`, `SUSTAINED_USAGE_DISCOUNT` | Propósito/origem do crédito. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#credits-type |
| `credits.name` | String | não | — | — | — | Descrição do crédito aplicado. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#credits-name |
| `credits.amount` | Float | não | Moeda de `currency` | — | — | Valor do crédito aplicado ao uso (sinal não afirmado pela doc; §3.3). | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#credits-amount |
| `adjustment_info` | Struct | não | — | — | — | Detalhes de ajuste de faturamento. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#adjustment_info |
| `adjustment_info.id` | String | não | — | — | — | ID único dos ajustes de uma emissão. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#adjustment_info-id |
| `adjustment_info.description` | String | não | — | — | — | Descrição do ajuste. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#adjustment_info-description |
| `adjustment_info.type` | String | não | — | — | `USAGE_CORRECTION`, `PRICE_CORRECTION`, `METADATA_CORRECTION`, `GOODWILL`, `SALES_BASED_GOODWILL`, `SLA_VIOLATION`, `BALANCE_TRANSFER`, `ACCOUNT_CLOSURE`, `GENERAL_ADJUSTMENT` | Tipo do ajuste. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#adjustment_info-type |
| `adjustment_info.mode` | String | não | — | — | `PARTIAL_CORRECTION`, `COMPLETE_NEGATION_WITH_REMONETIZATION`, `COMPLETE_NEGATION`, `MANUAL_ADJUSTMENT` | Modo do ajuste. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#adjustment_info-mode |
| `export_time` | Timestamp | sim | — | Timestamp BigQuery (UTC) | — | Tempo de processamento do append; sempre crescente. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#export_time |
| `tags` | Struct | não | — | — | — | Tag (key, value, inherited, namespace). | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#tags-struct |
| `tags.key` | String | não | — | — | — | Nome curto da chave da tag. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#tags-key |
| `tags.value` | String | não | — | — | — | Valor anexado a `tags.key`. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#tags-value |
| `tags.inherited` | Boolean | não | — | — | `true` / `false` | Se o binding é herdado. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#tags-inherited |
| `tags.namespace` | String | não | — | — | — | Hierarquia que define a tag. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#tags-namespace |
| `cost_at_list` | Float | não | Moeda de `currency` | — | — | Custo a preço de lista no modelo padrão. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#cost_at_list |
| `transaction_type` | String | não | — | — | `GOOGLE = 1`, `THIRD_PARTY_RESELLER = 2`, `THIRD_PARTY_AGENCY = 3` | Tipo de transação do vendedor. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#transaction_type |
| `seller_name` | String | não | — | — | — | Nome legal do vendedor. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#seller_name |
| `price` | Struct | não | — | — | — | Preços cobrados pelo uso. **No detalhado, primeiro dia completo: 2023-04-13.** | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#price-struct |
| `price.list_price` | Numeric | não | Moeda por `price.unit` | — | — | Preço de lista no modelo padrão. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#price-list_price |
| `price.effective_price_default` | Numeric | não | Moeda por `price.unit` | — | — | Preço no modelo padrão com descontos negociados. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#price-effective_price_default |
| `price.list_price_consumption_model` | Numeric | não | Moeda por `price.unit` | — | — | Preço de lista no modelo aplicável, antes de descontos. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#price-list_price_consumption_model |
| `price.effective_price` | Numeric | não | Moeda por `price.unit` | — | — | Preço no modelo aplicável com descontos negociados. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#price-effective_price |
| `price.tier_start_amount` | Numeric | não | unidades de pricing | — | — | Limite inferior da faixa de preço. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#price-tier_start_amount |
| `price.unit` | String | não | — | — | — | Unidade na qual o preço é especificado. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#price-unit |
| `price.pricing_unit_quantity` | Numeric | não | — | — | Ex.: `1000000` | Quantidade da unidade de precificação. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#price-pricing_unit_quantity |
| `cost_at_effective_price_default` | Numeric | não | Moeda de `currency` | — | — | Custo no modelo padrão com descontos negociados. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#cost_at_effective_price_default |
| `cost_at_list_consumption_model` | Numeric | não | Moeda de `currency` | — | — | Custo no modelo aplicável, antes de descontos. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#cost_at_list_consumption_model |
| `consumption_model` | Struct | não | — | — | — | Modelo de consumo aplicável. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#consumption_model |
| `consumption_model.id` | String | não | — | — | — | ID do modelo de consumo. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#consumption_model-id |
| `consumption_model.description` | String | não | — | — | — | Descrição do modelo de consumo. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#consumption_model-description |

**Subtotal §3.1: 71 campos.**

### 3.2 Campos exclusivos do export detalhado

Documentados sob o título *"Additional fields available to detailed usage cost data export"*
(anchor `#detailed-data`).
Data de consulta: **2026-10-14**.

| Campo | Tipo | Obrigatório | Unidade | Formato data/hora | Valores permitidos | Descrição | Fonte |
|---|---|---|---|---|---|---|---|
| `resource` | Struct | não | — | — | — | Campos que descrevem a estrutura e o valor de informação relevante aos recursos de serviço (ex.: VM, SSD) que geram uso. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#resource |
| `resource.global_name` | String | não | — | — | — | Identificador de serviço **globalmente único** do recurso que gerou o uso. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#resource-globalname |
| `resource.name` | String | não | — | — | — | Identificador do recurso **específico do serviço**; pode ser gerado pelo usuário. Primeiro dia completo: 2021-08-11. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#resource-name |
| `subscription` | Struct | não | — | — | — | Campos que descrevem seus compromissos spend-based ou resource-based; permite analisar taxas (fees) de compromissos específicos. Primeiro dia completo: 2024-01-25. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#subscription-struct |
| `subscription.instance_id` | String | não | — | — | — | ID da subscription vinculada a um compromisso. Primeiro dia completo: 2024-01-25. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#subscription-instance_id |
| `consumption_model.applied_subscription_instance_id` | String | não | — | — | — | ID único da instância de subscription que forneceu o benefício de desconto no line item. Para CUDs spend-based, é o mesmo valor de `subscription.instance_id` nos line items de fee. Não é nulo em linhas cobertas por CUD spend-based e é nulo em linhas sem desconto de modelo de consumo. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#consumption_model-applied_subscription_instance_id |
| *(nota de semântica — não é campo)* `resource.name` / `resource.global_name` por serviço | — | — | — | — | — | Ver a tabela "How to identify resources" por serviço: para a maioria dos serviços usa-se `service.description` + `resource.name` ou `resource.global_name`; para Cloud SQL, Cloud Storage, Bigtable, Memorystore for Redis, Spanner e Cloud Logging a doc cita `resource.global_name`; GKE é identificado por `labels.key`. | https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#identify_granular_cost_data_by_service |

**Subtotal §3.2: 6 campos exclusivos** (`resource`, `resource.global_name`, `resource.name`,
`subscription`, `subscription.instance_id`, `consumption_model.applied_subscription_instance_id`).
A sétima linha acima é uma nota de semântica, **não** um campo adicional — por isso não é
contada nem entra no `.schema.json`.

**Total: 71 + 6 = 77 campos.**

### 3.3 Semântica de moeda, unidade e sinal dos créditos

Idêntica à do export standard (mesmos nomes de campo, mesmas definições):

- `cost`: custo conforme o modelo de consumo aplicável, incluindo descontos negociados do
  contrato; é o valor **antes** dos créditos.
  Fonte: https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#cost
- `currency`: "The currency that the cost is billed in".
  Fonte: https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#currency
- `currency_conversion_rate`: "The exchange rate from US dollars to the local currency. That is,
  cost ÷ currency_conversion_rate is the cost in US dollars."
  Fonte: https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#currency_conversion_rate
- Líquido: só por query de exemplo —
  `SUM(cost) + SUM(IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c), 0))`,
  com o exemplo oficial `SUM(cost) + SUM(IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c), 0)) AS net_cost`
  para a tabela `gcp_billing_export_resource_v1_*` no exemplo com `tags`.
  Fontes: https://docs.cloud.google.com/billing/docs/how-to/bq-examples e
  https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#cost-type-resource-level-per-invoice
- Sinal de `credits.amount`: **não afirmado** na referência de campo. Ver §4 e §5.
- Unidades: `usage.unit` é a unidade base (ex.: `byte-seconds`); `usage.pricing_unit` e
  `price.unit` são unidades de precificação conforme a Cloud Billing Catalog API; não há
  enumeração fechada publicada.

## 4. Campos não comprovados

| Item | Status | Motivo |
|---|---|---|
| Particionamento declarado da tabela detalhada | **UNVERIFIED** | A página *Structure of Detailed data export* **não** contém a palavra "partition"; a página *Understand the Cloud Billing data tables in BigQuery* também não. O uso de `_PARTITIONTIME` aparece apenas dentro de exemplos de query (§5). |
| Clustering da tabela detalhada | **UNVERIFIED** | Nenhuma página oficial consultada declara colunas de clustering. |
| Formato físico/arquivo, compressão, encoding, delimitador, cabeçalho | **UNVERIFIED** | A entrega é uma tabela BigQuery; formato de arquivo não é documentado para esta superfície. |
| Schema de manifesto/metadados | **UNVERIFIED (inexistente)** | Não há manifesto emitido ao cliente na documentação. |
| Sinal (positivo/negativo) de `credits.amount` como contrato documentado | **UNVERIFIED** | Só inferível das queries de exemplo; a referência do campo não afirma o sinal. |
| Coluna dedicada de custo líquido | **UNVERIFIED** | Não existe no schema documentado. |
| Enumeração fechada de `usage.unit` / `usage.pricing_unit` / `price.unit` | **UNVERIFIED** | A doc dá exemplos e remete à Cloud Billing Catalog API. |
| Formato textual exato de timestamps | **UNVERIFIED** | Tipo declarado Timestamp (BigQuery); nenhum padrão de string é afirmado. Exemplos renderizam `2025-09-16 00:00:00.000000 UTC`. |
| Garantia de que `resource.*` está preenchido para todo serviço | **UNVERIFIED** | A doc lista os serviços com granularidade de recurso e notas de exceção (ex.: nem toda métrica tem `resource.name`), mas não afirma cobertura universal. |

## 5. Divergências conhecidas

1. **`_PARTITIONTIME` aparece exclusivamente em exemplos de query, inclusive nesta página.**
   A própria página do schema detalhado traz, em *"View consumption for a given instance"* e nas
   queries seguintes, `WHERE t.service.id = '...' AND DATE(TIMESTAMP_TRUNC(t._PARTITIONTIME, DAY)) = '2025-09-16'`.
   Não há frase declarativa de particionamento no corpo do schema.
   Fontes: https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#view_consumption_for_a_given_instance
   e https://docs.cloud.google.com/billing/docs/how-to/bq-examples.
   → Não promovemos o exemplo a contrato do export. Ver §4.

2. **"Additional fields" vs. datas de início por campo.** `price.*` **não** é exclusivo do
   detalhado (está também no standard, com início em 2025-07-15), enquanto `resource.*` e
   `subscription.*` são. A data de início de `price.*` difere entre os dois exports
   (2023-04-13 no detalhado; 2025-07-15 no standard).
   Fonte: https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#price-struct

3. **`resource.name` não é único nem sempre presente.** A doc diz que é
   "A service-specific identifier ... can be input generated by the user" e nota explicitamente
   que `resource.name` pode faltar (ex.: `Snapshot_disk_time` metrics won't provide resource.name;
   StreamingInsertBytes não tem identificador de recurso no export). Não usar `resource.name`
   como chave primária.
   Fontes: https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#resource-name
   e https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#identify_granular_cost_data_by_service

4. **`cost_type` com grafia divergente** entre o texto do schema ("rounding error") e os
   resultados de exemplo ("rounding_error"). Registrado dos dois lados.

5. **GKE exige configuração adicional.** Custos granulares de cluster GKE só aparecem se
   *GKE cost allocation* estiver habilitado, e "The billing export doesn't backfill GKE cost
   allocation data".
   Fonte: https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/detailed-usage#identify_granular_cost_data_by_service
