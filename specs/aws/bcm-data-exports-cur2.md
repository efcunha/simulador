# AWS BCM Data Exports — Cost and Usage Report (CUR) 2.0

## 1. Identificação

| Item | Valor |
|---|---|
| Nome oficial da superfície | **Cost and Usage Report (CUR) 2.0** (AWS Data Exports, AWS Billing and Cost Management / BCM Data Exports) |
| Nome SQL da tabela | `COST_AND_USAGE_REPORT` |
| Documento oficial (raiz) | *Data Exports table dictionary* — https://docs.aws.amazon.com/cur/latest/userguide/dataexports-table-dictionary.md |
| Documento oficial (tabela) | *Cost and Usage Report (CUR) 2.0* — https://docs.aws.amazon.com/cur/latest/userguide/table-dictionary-cur2.md |
| Documento oficial (entrega) | *Understanding export delivery* — https://docs.aws.amazon.com/cur/latest/userguide/dataexports-export-delivery.md |
| Versão/schema de referência | CUR 2.0 (schema fixo, 125 colunas possíveis). Não há número de versão de schema publicado; a superfície é identificada pelo nome da tabela `COST_AND_USAGE_REPORT`. |
| Data de consulta | 2026-10-14 |

Nota de nomenclatura: a documentação de colunas da CUR 2.0 usa **snake_case** em todos os nomes de coluna.

## 2. Mecanismo e entrega

Fonte: https://docs.aws.amazon.com/cur/latest/userguide/dataexports-export-delivery.md (consultado em 2026-10-14).

### 2.1 Estrutura de diretórios no S3

Cada export entrega os dados da consulta ao S3 (como um ou mais arquivos gzip/csv ou Parquet) **e** um arquivo de metadados `Manifest.json`.

**Dados:**

```
s3://<bucket-name>/<prefix>/<export-name>/data/<partition>/
```

**Metadados:**

```
s3://<bucket-name>/<prefix>/<export-name>/metadata/<partition>/<export-name>-Manifest.json
```

- `prefix` — prefixo de S3 atribuído ao export.
- `export-name` — nome atribuído ao export.
- `partition` — para CUR 2.0 corresponde ao **billing period**, no formato `BILLING_PERIOD=YYYY-MM`. Exemplo: novembro de 2023 → `BILLING_PERIOD=2023-11`.

Exemplo de caminho de dados citado na documentação:

```
s3://my-data-export-s3-bucket/my-cur-files/business_group_a_cur/data/BILLING_PERIOD=2023-11
```

### 2.2 Modos de versionamento de arquivo

**Create new** (`CREATE_NEW_REPORT`) — dados:

```
s3://<bucket-name>/<prefix>/<export-name>/data/<partition>/<timestamp>-<execution-id>
```

Entregue dois `Manifest.json` por execução: um em `metadata/<partition>/<timestamp>-<execution-id>` (corresponde àquela execução específica) e outro sobrescrito em `metadata/<partition>` (sempre representa o refresh mais recente).

**Overwrite** (`OVERWRITE_REPORT`) — dados:

```
s3://<bucket-name>/<prefix>/<export-name>/data/<partition>/
```

Os arquivos são sobrescritos a cada entrega da mesma partição. Um único `Manifest.json` é entregue por execução, em `metadata/<partition>`, sobrescrito a cada refresh.

### 2.3 Nomes de arquivo, chunks e formato

Fonte: https://docs.aws.amazon.com/cur/latest/userguide/dataexports-export-delivery.md#export-data-file-names (consultado em 2026-10-14).

| Formato | Padrão de nome |
|---|---|
| gzip/csv | `<export-name>-<chunk-number>.csv.gz` |
| Parquet | `<export-name>-<chunk-number>.snappy.parquet` |

- Números de chunk têm **sempre cinco dígitos**, enumerados a partir de `00001`.
- Compressão do Parquet: **Snappy** (evidenciada pela extensão `.snappy.parquet`).
- Caminhos completos com diretório, por modo:

```
# create new
s3://<bucket-name>/<prefix>/<export-name>/data/<partition>/<timestamp>-<execution-id>/<export-name>-<chunk-number>.snappy.parquet
s3://<bucket-name>/<prefix>/<export-name>/data/<partition>/<timestamp>-<execution-id>/<export-name>-<chunk-number>.csv.gz

# overwrite
s3://<bucket-name>/<prefix>/<export-name>/data/<partition>/<export-name>-<chunk-number>.snappy.parquet
s3://<bucket-name>/<prefix>/<export-name>/data/<partition>/<export-name>-<chunk-number>.csv.gz
```

Opcões de compressão/formato segundo a API (fonte: https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/API_DataExports_S3OutputConfigurations.html, consultado em 2026-10-14):

| Parâmetro da API | Valores válidos |
|---|---|
| `Compression` | `GZIP`, `PARQUET`, `ZIP` |
| `Format` | `TEXT_OR_CSV`, `PARQUET` |
| `OutputType` | `CUSTOM`, `ATHENA`, `REDSHIFT` |
| `Overwrite` | `CREATE_NEW_REPORT`, `OVERWRITE_REPORT` |

### 2.4 Frequência de atualização

- CUR 2.0 é atualizada **pelo menos uma vez por dia**.
- A partição do período de faturamento corrente é atualizada até o período terminar; depois disso a AWS pode atualizar a entrega do período anterior **nas duas primeiras semanas** após o término.
- Se o export encolher (query alterada ou correção de dados), chunks excedentes do refresh anterior são sobrescritos com dados vazios.

### 2.5 Formato de data/hora e fuso

Convenção documentada por campo (ver coluna *Formato data/hora* na seção 3): timestamps de data de faturamento e de uso são **UTC**, no formato `YYYY-MM-DDTHH:mm:ssZ`. `identity_time_interval` usa dois timestamps UTC separados por `/`.

### 2.6 Manifesto — o que a documentação afirma

Fonte: https://docs.aws.amazon.com/cur/latest/userguide/dataexports-export-delivery.md#export-s3-parent-directory-structure (consultado em 2026-10-14) e https://docs.aws.amazon.com/cur/latest/userguide/table-dictionary-focus-1-2-migrating.md (consultado em 2026-10-14).

Afirmado pela AWS:

1. `Manifest.json` é um arquivo de metadados "containing information about the export definition at the time the export was executed".
2. É atualizado a cada refresh; um novo `Manifest.json` é criado a cada nova partição (novo período de faturamento).
3. Contém:
   - **todas as colunas** incluídas no export;
   - uma **lista dos arquivos do export e seus caminhos** ("We recommend identifying which files to ingest by programmatically reading this list");
   - o **período coberto** pelo export;
   - uma seção chamada **`additionalOutputFiles`** que lista os arquivos adicionais entregues quando há integração com Athena ou Amazon Redshift.
4. O `Manifest.json` só é entregue depois que todos os arquivos de dados foram entregues ao S3.
5. O campo **`FocusVersion`** do manifesto é `"1.2"` para a tabela FOCUS 1.2 e `"1.0"` para a tabela FOCUS 1.0 (tabela comparativa "Manifest FocusVersion").

Não confirmado em documentação oficial nesta consulta: os **nomes literais de chave** dos campos de colunas, arquivos e período (exceto `additionalOutputFiles` e `FocusVersion`), a ordem das chaves, obrigatoriedade e tipos JSON. Ver seção 4.

### 2.7 Integrações Athena / Redshift (entrega adicional)

Fonte: https://docs.aws.amazon.com/cur/latest/userguide/dataexports-export-delivery.md (consultado em 2026-10-14).

| Artefato | Caminho |
|---|---|
| SQL de carga no Redshift | `<bucket>/<prefix>/<export-name>/metadata/<partition>/<export-name>-RedshiftCommands.sql` |
| Template CloudFormation (Athena) | `<prefix>/<export-name>/crawler-cfn.yml` |
| SQL de criação de tabela Athena | `<prefix>/<export-name>/metadata/<partition>/<export-name>-create-table.sql` |
| Pasta de status de refresh | `<prefix>/<export-name>/execution_status/` |

## 3. Campos

A tabela CUR 2.0 tem **125 colunas possíveis**, agrupadas pela AWS em 14 grupos: Bill, Cost category, Capacity reservation, Discount, Identity, Line item, Pricing, Product, Reservation, Resource tags, Savings plan, Split line item, Capacity Reservation e Tags. Os grupos "Capacity reservation" e "Capacity Reservation" aparecem os dois na lista da documentação; não há segunda página de colunas para o segundo grupo, então ele é tratado nesta spec como o mesmo grupo.

Convenções desta seção:

- **Obrigatório** = `sim` apenas quando a documentação afirma que a coluna está sempre presente. Colunas adicionadas por *table configuration* são `condicional`. Colunas cuja inclusão a documentação condiciona a "your account has a discount in the applicable billing period" são `condicional`.
- **Unidade** = `USD` somente para as colunas em que a documentação da AWS afirma literalmente que o cliente é faturado em dólares (ver `line_item_currency_code`). Os demais valores monetários não têm unidade afirmada na página do campo e são listados na seção 4.
- **Formato data/hora** = `UTC, YYYY-MM-DDTHH:mm:ssZ` somente onde a documentação afirma. `—` = a documentação não define formato para o campo.
- Todas as URLs desta seção foram consultadas em **2026-10-14**.

### 3.1 Bill columns (8)

Fonte-base: https://docs.aws.amazon.com/cur/latest/userguide/table-dictionary-cur2-bill.md

| Campo | Tipo | Obrigatório | Unidade | Formato data/hora | Valores permitidos | Descrição | Fonte |
|---|---|---|---|---|---|---|---|
| `bill_bill_type` | string | — | — | — | Anniv… | O tipo de fatura coberto pelo relatório. Tipos citados: Anniversary (itens de serviços usados no mês), Purchase (itens de taxas antecipadas), Refund (itens de reembolso). | https://docs.aws.amazon.com/cur/latest/userguide/table-dictionary-cur2-bill.md#table-dictionary-cur2-bill |
| `bill_billing_entity` | string | — | — | — | — | Ajuda a identificar se faturas/transações são de AWS Marketplace ou de outros serviços AWS. | idem |
| `bill_billing_period_end_date` | timestamp | — | — | UTC, `YYYY-MM-DDTHH:mm:ssZ` | — | Data de término do período de faturamento coberto pelo relatório, em UTC. | idem |
| `bill_billing_period_start_date` | timestamp | — | — | UTC, `YYYY-MM-DDTHH:mm:ssZ` | — | Data de início do período de faturamento coberto pelo relatório, em UTC. | idem |
| `bill_invoice_id` | string | — | — | — | — | ID associado a um item de linha específico. Até o relatório ser finalizado, `InvoiceId` fica em branco. | idem |
| `bill_invoicing_entity` | string | — | — | — | — | A entidade AWS que emite a fatura. | idem |
| `bill_payer_account_id` | string | — | — | — | — | ID da conta pagadora. Em organização AWS Organizations, é o ID da conta de gerenciamento. | idem |
| `bill_payer_account_name` | string | — | — | — | — | Nome da conta pagadora. Em AWS Organizations, é o nome da conta de gerenciamento. | idem |

### 3.2 Cost category columns (1)

Fonte-base: https://docs.aws.amazon.com/cur/latest/userguide/table-dictionary-cur2-cost-category.md

| Campo | Tipo | Obrigatório | Unidade | Formato data/hora | Valores permitidos | Descrição | Fonte |
|---|---|---|---|---|---|---|---|
| `cost_category` | map \<string, string\> | — | — | — | — | Coluna de mapa com pares chave-valor das categorias de custo e seus valores para o item de linha. Uma chave só aparece se tiver valor aplicável ao item. As chaves podem ser consultadas como colunas individuais com o operador ponto. | https://docs.aws.amazon.com/cur/latest/userguide/table-dictionary-cur2-cost-category.md#table-dictionary-cur2-cost-category |

### 3.3 Capacity reservation columns (3)

Fonte-base: https://docs.aws.amazon.com/cur/latest/userguide/table-dictionary-cur2-capacity-reservation.md — a documentação declara **Nullability** explicitamente para os três campos.

| Campo | Tipo | Obrigatório | Unidade | Formato data/hora | Valores permitidos | Descrição | Fonte |
|---|---|---|---|---|---|---|---|
| `capacity_reservation_capacity_reservation_arn` | String | condicional (INCLUDE_CAPACITY_RESERVATION_DATA); Nullable | — | — | — | ARN que representa o identificador único da capacity reservation. Não nulo quando o encargo se relaciona a uma capacity reservation ou representa sua porção não usada; nulo quando não há relação. | https://docs.aws.amazon.com/cur/latest/userguide/table-dictionary-cur2-capacity-reservation.md#table-dictionary-cur2-capacity-reservation |
| `capacity_reservation_capacity_reservation_status` | String | condicional (INCLUDE_CAPACITY_RESERVATION_DATA); Nullable | — | — | Reserved, Cancelling, Used, Unused | Indica se o item representa consumo ou cancelamento (no caso de capacity reservation com data futura), ou quando a reserva está unused ou reserved. Nulo quando o ARN é nulo. | idem |
| `capacity_reservation_capacity_reservation_type` | String | condicional (INCLUDE_CAPACITY_RESERVATION_DATA); Nullable | — | — | ODCR, EC2 Capacity Blocks for ML | Tipo de capacity reservation comprada. Dois tipos citados: ODCR e EC2 Capacity Blocks for ML. Nulo quando o ARN é nulo. | idem |

### 3.4 Discount columns (3)

Fonte-base: https://docs.aws.amazon.com/cur/latest/userguide/table-dictionary-cur2-discount.md

| Campo | Tipo | Obrigatório | Unidade | Formato data/hora | Valores permitidos | Descrição | Fonte |
|---|---|---|---|---|---|---|---|
| `discount` | map \<string, double\> | condicional — removida por `INCLUDE_MANUAL_DISCOUNT_COMPATIBILITY` | — | — | — | Coluna "struct" com pares chave-valor de descontos específicos aplicáveis ao item. Chaves correspondem a um tipo de desconto; valores são numéricos ou string conforme a chave. Não disponível quando "Manual discount compatibility" está habilitado. | https://docs.aws.amazon.com/cur/latest/userguide/table-dictionary-cur2-discount.md#table-dictionary-cur2-discount |
| `discount_bundled_discount` | double | — | — | — | — | Desconto agrupado aplicado ao item. Desconto agrupado é um desconto baseado em uso que concede uso gratuito ou com desconto de um serviço com base no uso de outro. Desde agosto de 2025 aplicado por "Owner-first approach". | idem |
| `discount_total_discount` | double | condicional — removida por `INCLUDE_MANUAL_DISCOUNT_COMPATIBILITY` | — | — | — | Soma de todas as colunas de desconto do item de linha correspondente. Não disponível quando "Manual discount compatibility" está habilitado. | idem |

### 3.5 Identity columns (2)

Fonte-base: https://docs.aws.amazon.com/cur/latest/userguide/table-dictionary-cur2-identity.md

| Campo | Tipo | Obrigatório | Unidade | Formato data/hora | Valores permitidos | Descrição | Fonte |
|---|---|---|---|---|---|---|---|
| `identity_line_item_id` | string | — | — | — | — | Gerado para cada item de linha; único em uma dada partição. Não garante unicidade em toda a entrega e não é consistente entre relatórios diferentes. | https://docs.aws.amazon.com/cur/latest/userguide/table-dictionary-cur2-identity.md#table-dictionary-cur2-identity |
| `identity_time_interval` | string | — | — | UTC, `YYYY-MM-DDTHH:mm:ssZ/YYYY-MM-DDTHH:mm:ssZ` | — | Intervalo de tempo ao qual o item se aplica. Em UTC; pode ser diário ou horário conforme a granularidade do relatório. | idem |

### 3.6 Line item columns (25)

Fonte-base: https://docs.aws.amazon.com/cur/latest/userguide/table-dictionary-cur2-line-item.md

| Campo | Tipo | Obrigatório | Unidade | Formato data/hora | Valores permitidos | Descrição | Fonte |
|---|---|---|---|---|---|---|---|
| `line_item_usage_account_name` | string | — | — | — | — | Nome da conta que usou este item de linha. Em organizações pode ser a conta de gerenciamento ou uma conta membro. | https://docs.aws.amazon.com/cur/latest/userguide/table-dictionary-cur2-line-item.md#table-dictionary-cur2-line-item |
| `line_item_availability_zone` | string | — | — | — | — | Zona de Disponibilidade que hospeda o item, por exemplo `us-east-1a`. | idem |
| `line_item_blended_cost` | double | — | — | — | — | `BlendedRate` multiplicado por `UsageAmount`. Em branco para itens com `LineItemType` = **Discount**. | idem |
| `line_item_blended_rate` | string | — | — | — | — | Custo médio por SKU na organização. Calculado no nível da conta de gerenciamento. | idem |
| `line_item_currency_code` | string | — | — | — | — | Moeda em que o item é exibido. **Todos os clientes AWS são faturados em dólares dos EUA por padrão.** | idem |
| `line_item_iam_principal` | string | condicional (INCLUDE_IAM_PRINCIPAL_DATA) | — | — | — | ARN IAM do principal que fez a inferência de modelo Amazon Bedrock. Suportado atualmente apenas para Amazon Bedrock. | idem |
| `line_item_legal_entity` | string | — | — | — | Amazon Web Services, Inc.; Amazon Web Services India Private Limited | Seller of Record de um produto ou serviço. Valores possíveis incluem as duas entidades citadas. | idem |
| `line_item_line_item_description` | string | — | — | — | — | Descrição do tipo de item de linha. | idem |
| `line_item_line_item_type` | string | — | — | — | BundledDiscount, Credit, Discount, DiscountedUsage, Fee, Refund, RIFee, Tax, Usage, SavingsPlanUpfrontFee, SavingsPlanRecurringFee, SavingsPlanCoveredUsage, SavingsPlanNegation, FlateRateSubscription | Tipo de encargo coberto pelo item de linha. A documentação lista os valores da coluna Valores permitidos. | idem |
| `line_item_net_unblended_cost` | double | condicional — só incluída quando a conta tem desconto no período | — | — | — | Custo real pós-desconto pago pelo item. | idem |
| `line_item_net_unblended_rate` | string | condicional — só incluída quando a conta tem desconto no período | — | — | — | Taxa real pós-desconto paga pelo item. | idem |
| `line_item_normalization_factor` | double | — | — | — | — | Fator de normalização usado para dimensionar RIs flexíveis em tamanho (EC2/RDS). | idem |
| `line_item_normalized_usage_amount` | double | — | — | — | — | Quantidade de uso em unidades normalizadas para RIs flexíveis em tamanho. Igual a `UsageAmount` × `NormalizationFactor`. | idem |
| `line_item_operation` | string | — | — | — | — | Operação AWS específica coberta pelo item. Ex.: `RunInstances`. | idem |
| `line_item_product_code` | string | — | — | — | — | Código do produto medido. Ex.: `AmazonEC2`. | idem |
| `line_item_resource_id` | string | condicional (INCLUDE_RESOURCES) | — | — | — | ID do recurso provisionado, quando a opção de incluir IDs individuais é escolhida. Em branco para tipos de uso sem host instanciado e para descontos, créditos e impostos. | idem |
| `line_item_tax_type` | string | — | — | — | — | Tipo de imposto aplicado ao item de linha. | idem |
| `line_item_unblended_cost` | double | — | — | — | — | `UnblendedRate` × `UsageAmount`. | idem |
| `line_item_unblended_rate` | string | — | — | — | — | Em consolidated billing, a taxa associada ao uso do serviço da conta individual. Para itens EC2/RDS com desconto de RI, a taxa é `0`. | idem |
| `line_item_usage_account_id` | string | — | — | — | — | ID da conta que usou o item de linha. | idem |
| `line_item_usage_amount` | double | — | — | — | — | Quantidade de uso incorrida no período especificado. Alguns encargos de assinatura têm `UsageAmount` igual a `0`. | idem |
| `line_item_usage_end_date` | timestamp | — | — | UTC, `YYYY-MM-DDTHH:mm:ssZ` (exclusivo) | — | Data e hora de término do item, em UTC, exclusiva. | idem |
| `line_item_usage_start_date` | timestamp | — | — | UTC, `YYYY-MM-DDTHH:mm:ssZ` (inclusivo) | — | Data e hora de início do item, em UTC, inclusiva. | idem |
| `line_item_usage_type` | string | — | — | — | — | Detalhes de uso do item. Ex.: `USW2-BoxUsage:m2.2xlarge`. | idem |
| `line_item_user_identifier` | string | — | — | — | — | Identificador do usuário workforce no IAM Identity Center. | idem |

### 3.7 Pricing columns (10)

Fonte-base: https://docs.aws.amazon.com/cur/latest/userguide/table-dictionary-cur2-pricing.md

| Campo | Tipo | Obrigatório | Unidade | Formato data/hora | Valores permitidos | Descrição | Fonte |
|---|---|---|---|---|---|---|---|
| `pricing_currency` | string | — | — | — | — | Moeda em que os dados de preço são exibidos. | https://docs.aws.amazon.com/cur/latest/userguide/table-dictionary-cur2-pricing.md#table-dictionary-cur2-pricing |
| `pricing_lease_contract_length` | string | — | — | — | — | Duração pela qual a RI está reservada. | idem |
| `pricing_offering_class` | string | — | — | — | — | Classe de oferta da Reserved Instance. | idem |
| `pricing_public_on_demand_cost` | double | — | — | — | — | Custo total do item com base nas taxas públicas On-Demand. Com múltiplos custos públicos por SKU, exibe o equivalente ao tier mais alto. | idem |
| `pricing_public_on_demand_rate` | string | — | — | — | — | Taxa pública On-Demand no período para o item específico. | idem |
| `pricing_purchase_option` | string | — | — | All Upfront, Partial Upfront, No Upfront | Forma de pagamento escolhida para o item. | idem |
| `pricing_rate_code` | string | — | — | — | — | Código único para uma combinação produto/oferta/tier de preço. | idem |
| `pricing_rate_id` | string | — | — | — | — | ID da taxa do item de linha. | idem |
| `pricing_term` | string | — | — | — | — | Se o uso é Reserved ou On-Demand. | idem |
| `pricing_unit` | string | — | — | — | — | Unidade de preço usada pela AWS para calcular o custo. Ex.: horas para uso de instância EC2. | idem |

Nota: a página "Pricing columns" documenta exatamente os 10 campos acima (`pricing_currency`, `pricing_lease_contract_length`, `pricing_offering_class`, `pricing_public_on_demand_cost`, `pricing_public_on_demand_rate`, `pricing_purchase_option`, `pricing_rate_code`, `pricing_rate_id`, `pricing_term`, `pricing_unit`), e todos foram incluídos nesta spec.

### 3.8 Product columns (22 titulares + atributos de serviço em `product`)

Fonte-base: https://docs.aws.amazon.com/cur/latest/userguide/table-dictionary-cur2-product.md

| Campo | Tipo | Obrigatório | Unidade | Formato data/hora | Valores permitidos | Descrição | Fonte |
|---|---|---|---|---|---|---|---|
| `product` | map \<string, string\> | — | — | — | — | Mapa com pares chave-valor de múltiplos atributos de produto. Qualquer coluna de produto do CUR legado fora do schema estático da CUR 2.0 aparece neste mapa. Chaves consultáveis com o operador ponto. | https://docs.aws.amazon.com/cur/latest/userguide/table-dictionary-cur2-product.md#table-dictionary-cur2-product |
| `product_comment` | string | — | — | — | — | Comentário a respeito do produto. | idem |
| `product_fee_code` | string | — | — | — | — | Código que se refere à taxa. | idem |
| `product_fee_description` | string | — | — | — | — | Descrição da taxa do produto. | idem |
| `product_from_location` | string | — | — | — | — | Local de origem do uso. | idem |
| `product_from_location_type` | string | — | — | — | — | Tipo de local de origem do uso. | idem |
| `product_from_region_code` | string | — | — | — | — | Código da Região de origem do serviço AWS. | idem |
| `product_instanceSKU` | string | — | — | — | — | SKU da instância do produto. (Casing exato conforme documentado.) | idem |
| `product_instance_family` | string | — | — | — | — | Família de instâncias EC2. | idem |
| `product_instance_type` | string | — | — | — | — | Tipo, tamanho e família da instância. | idem |
| `product_location` | string | — | — | — | — | Região onde o bucket Amazon S3 reside. | idem |
| `product_location_type` | string | — | — | — | — | Descreve o endpoint da tarefa. | idem |
| `product_operation` | string | — | — | — | — | Operação AWS específica coberta pelo item. | idem |
| `product_pricing_unit` | string | — | — | — | — | Menor unidade de faturamento de um serviço AWS. | idem |
| `product_product_family` | string | — | — | — | — | Categoria do tipo de produto. Para Amazon Bedrock, preenchido com o valor unificado `Amazon Bedrock`. | idem |
| `product_region_code` | string | — | — | — | — | Código da Região onde o serviço AWS está disponível. | idem |
| `product_sku` | string | — | — | — | — | Código único de produto, criado combinando `ProductCode`, `UsageType` e `Operation`. | idem |
| `product_servicecode` | string | — | — | — | — | Identifica o serviço AWS específico como abreviação curta única. | idem |
| `product_to _location_type` | string | — | — | — | — | Local de destino do uso do serviço. (Casing e espaço exatos conforme documentado: `product_to _location_type`.) | idem |
| `product_to_location` | string | — | — | — | — | Destino do uso. | idem |
| `product_to_region_code` | string | — | — | — | — | Código da Região de origem do serviço AWS (texto da doc). | idem |
| `product_usagetype` | string | — | — | — | — | Detalhes de uso do item de linha. | idem |

**Service-specific product attributes** (chaves dentro do mapa `product`, não colunas estáticas) — fonte: https://docs.aws.amazon.com/cur/latest/userguide/table-dictionary-cur2-product.md#table-dictionary-cur2-product-service-attributes

| Chave de mapa | Tipo | Aplica-se a | Valores de exemplo | Descrição |
|---|---|---|---|---|
| `provider` | (chave de `map<string,string>`) | Amazon Bedrock | Amazon, Anthropic, Meta, Cohere | Provedor do modelo de fundação. |
| `model` | idem | Amazon Bedrock | Claude 3.5 Sonnet, Nova Pro, Llama 3 | Nome do modelo, correspondente ao catálogo de modelos do console Bedrock. |
| `inference_type` | idem | Amazon Bedrock | input tokens, output tokens, image generation | Tipo de uso medido (tipo de token). |
| `feature` | idem | Amazon Bedrock | On-Demand, Batch | Modo de serviço de inferência. |

### 3.9 Reservation columns (27)

Fonte-base: https://docs.aws.amazon.com/cur/latest/userguide/table-dictionary-cur2-reservation.md

| Campo | Tipo | Obrigatório | Unidade | Formato data/hora | Valores permitidos | Descrição | Fonte |
|---|---|---|---|---|---|---|---|
| `reservation_amortized_upfront_cost_for_usage` | double | — | — | — | — | Pagamento antecipado inicial de RIs all upfront e partial upfront amortizado pelo tempo de uso. `0` para no upfront. Não fornecido para Dedicated Host reservations. | https://docs.aws.amazon.com/cur/latest/userguide/table-dictionary-cur2-reservation.md#table-dictionary-cur2-reservation |
| `reservation_amortized_upfront_fee_for_billing_period` | double | — | — | — | — | Quanto da taxa antecipada da reserva custa no período de faturamento. `0` para no upfront. Não fornecido para Dedicated Host reservations. | idem |
| `reservation_availability_zone` | string | — | — | — | — | Zona de Disponibilidade do recurso associado ao item. | idem |
| `reservation_effective_cost` | double | — | — | — | — | Soma da taxa antecipada e da taxa horária da RI, em média, como taxa horária efetiva. | idem |
| `reservation_end_time` | string | — | — | — | — | Data de término do prazo de locação da RI associada. | idem |
| `reservation_modification_status` | string | — | — | — | Original, System, Manual, ManualWithData | Indica se a locação de RI foi modificada ou não. | idem |
| `reservation_net_amortized_upfront_cost_for_usage` | double | condicional (desconto no período) | — | — | — | Igual ao amortized upfront cost for usage, com desconto. | idem |
| `reservation_net_amortized_upfront_fee_for_billing_period` | double | condicional (desconto no período) | — | — | — | Custo da taxa antecipada da reserva no período, com desconto. | idem |
| `reservation_net_effective_cost` | double | condicional (desconto no período) | — | — | — | Soma da taxa antecipada e horária, com desconto. | idem |
| `reservation_net_recurring_fee_for_usage` | double | condicional (desconto no período) | — | — | — | Custo pós-desconto da taxa de uso recorrente. | idem |
| `reservation_net_unused_amortized_upfront_fee_for_billing_period` | double | condicional (desconto no período) | — | — | — | Taxa antecipada amortizada não utilizada, líquida, no período. | idem |
| `reservation_net_unused_recurring_fee` | double | condicional (desconto no período) | — | — | — | Taxas recorrentes de horas de reserva não usadas, pós-desconto. | idem |
| `reservation_net_upfront_value` | double | condicional (desconto no período) | — | — | — | Valor antecipado da RI com descontos aplicados. | idem |
| `reservation_normalized_units_per_reservation` | string | — | — | — | — | Número de unidades normalizadas por instância de uma assinatura de reserva. | idem |
| `reservation_number_of_reservations` | string | — | — | — | — | Número de reservas cobertas pela assinatura. | idem |
| `reservation_recurring_fee_for_usage` | double | — | — | — | — | Taxa recorrente amortizada pelo tempo de uso, para partial upfront e no upfront. `0` para all upfront. | idem |
| `reservation_reservation_a_r_n` | string | — | — | — | — | ARN da RI beneficiada pelo item ("RI Lease ID"). | idem |
| `reservation_start_time` | string | — | — | — | — | Data de início do prazo da Reserved Instance associada. | idem |
| `reservation_subscription_id` | string | — | — | — | — | Identificador único que mapeia o item à oferta associada. | idem |
| `reservation_total_reserved_normalized_units` | string | — | — | — | — | Total de unidades normalizadas reservadas para a assinatura. | idem |
| `reservation_total_reserved_units` | string | — | — | — | — | Populado tanto em itens Fee quanto RIFee, com valores distintos. | idem |
| `reservation_units_per_reservation` | string | — | — | — | — | Populado tanto em itens Fee quanto RIFee, com valores distintos. | idem |
| `reservation_unused_amortized_upfront_fee_for_billing_period` | double | — | — | — | — | Porção amortizada da taxa antecipada inicial não utilizada. `0` para no upfront. Não fornecido para Dedicated Host reservations. | idem |
| `reservation_unused_normalized_unit_quantity` | double | — | — | — | — | Número de unidades normalizadas não usadas de uma RI regional flexível em tamanho no período. | idem |
| `reservation_unused_quantity` | double | — | — | — | — | Número de horas de RI não usadas no período. | idem |
| `reservation_unused_recurring_fee` | double | — | — | — | — | Taxas recorrentes de horas de reserva não usadas. `0` para all upfront. | idem |
| `reservation_upfront_value` | double | — | — | — | — | Preço antecipado pago pela Reserved Instance. `0` para no upfront. | idem |

### 3.10 Resource tags columns (1)

Fonte-base: https://docs.aws.amazon.com/cur/latest/userguide/table-dictionary-cur2-resource-tags.md

| Campo | Tipo | Obrigatório | Unidade | Formato data/hora | Valores permitidos | Descrição | Fonte |
|---|---|---|---|---|---|---|---|
| `resource_tags` | map \<string, string\> | — | — | — | — | Mapa com pares chave-valor de tags de recurso. Todos os valores são do tipo "string". Chaves só aparecem se habilitadas como cost allocation tags no console de Billing. | https://docs.aws.amazon.com/cur/latest/userguide/table-dictionary-cur2-resource-tags.md#table-dictionary-cur2-resource-tags |

### 3.11 Savings plan columns (17)

Fonte-base: https://docs.aws.amazon.com/cur/latest/userguide/table-dictionary-cur2-savings-plan.md

| Campo | Tipo | Obrigatório | Unidade | Formato data/hora | Valores permitidos | Descrição | Fonte |
|---|---|---|---|---|---|---|---|
| `savings_plan_amortized_upfront_commitment_for_billing_period` | double | — | — | — | — | Valor da taxa antecipada que uma assinatura de Savings Plan custa no período. `0` para No Upfront. | https://docs.aws.amazon.com/cur/latest/userguide/table-dictionary-cur2-savings-plan.md#table-dictionary-cur2-savings-plan |
| `savings_plan_end_time` | string | — | — | — | — | Data de expiração do acordo de Savings Plan. | idem |
| `savings_plan_instance_type_family` | string | — | — | — | — | Família de instâncias associada ao uso especificado. | idem |
| `savings_plan_net_amortized_upfront_commitment_for_billing_period` | double | condicional (desconto no período) | — | — | — | Custo da taxa antecipada da assinatura no período, com desconto. | idem |
| `savings_plan_net_recurring_commitment_for_billing_period` | double | condicional (desconto no período) | — | — | — | Custo unblended líquido da taxa do Savings Plan. | idem |
| `savings_plan_net_savings_plan_effective_cost` | double | condicional (desconto no período) | — | — | — | Custo efetivo de Savings Plans (uso dividido pelas taxas), com desconto. | idem |
| `savings_plan_offering_type` | string | — | — | — | — | Tipo de Savings Plan comprado. | idem |
| `savings_plan_payment_option` | string | — | — | — | — | Opções de pagamento disponíveis para o Savings Plan. | idem |
| `savings_plan_purchase_term` | string | — | — | — | — | Duração (prazo) do Savings Plan. | idem |
| `savings_plan_recurring_commitment_for_billing_period` | double | — | — | — | — | Taxa recorrente mensal das assinaturas de Savings Plan. | idem |
| `savings_plan_region` | string | — | — | — | — | Região AWS que hospeda os serviços. | idem |
| `savings_plan_savings_plan_a_r_n` | string | — | — | — | — | Identificador único do Savings Plan. | idem |
| `savings_plan_savings_plan_effective_cost` | double | — | — | — | — | Proporção do compromisso mensal (antecipado e recorrente) alocada a cada linha de uso. | idem |
| `savings_plan_savings_plan_rate` | double | — | — | — | — | Taxa do Savings Plan para o uso. | idem |
| `savings_plan_start_time` | string | — | — | — | — | Data de início do acordo de Savings Plan. | idem |
| `savings_plan_total_commitment_to_date` | double | — | — | — | — | Total do compromisso antecipado amortizado e do compromisso recorrente até a data, para aquela hora. | idem |
| `savings_plan_used_commitment` | double | — | — | — | — | Valor total em dólares do compromisso de Savings Plan usado (SavingsPlanRate × uso). | idem |

### 3.12 Split line item columns (11)

Fonte-base: https://docs.aws.amazon.com/cur/latest/userguide/table-dictionary-cur2-split-line-item.md — todas as colunas abaixo são **Added by: INCLUDE_SPLIT_COST_ALLOCATION_DATA**. O recurso é limitado a Amazon ECS (incluindo Fargate), AWS Batch e Amazon EKS.

| Campo | Tipo | Obrigatório | Unidade | Formato data/hora | Valores permitidos | Descrição | Fonte |
|---|---|---|---|---|---|---|---|
| `split_line_item_actual_usage` | double | condicional (INCLUDE_SPLIT_COST_ALLOCATION_DATA) | — | — | — | Uso de vCPU, memória ou aceleradores (conforme `lineItem/UsageType`) incorrido no período para a tarefa ECS ou pod Kubernetes. | https://docs.aws.amazon.com/cur/latest/userguide/table-dictionary-cur2-split-line-item.md#table-dictionary-cur2-split-line-item |
| `split_line_item_net_split_cost` | double | condicional (config) — condicional (desconto no período) | — | — | — | Custo efetivo para tarefas ECS ou pods Kubernetes após todos os descontos. | idem |
| `split_line_item_net_unused_cost` | double | condicional (config) — condicional (desconto no período) | — | — | — | Custo efetivo não usado para tarefas ECS ou pods após todos os descontos. | idem |
| `split_line_item_parent_resource_id` | string | condicional (INCLUDE_SPLIT_COST_ALLOCATION_DATA) | — | — | — | ID do recurso da instância EC2 pai associada à tarefa ECS ou pod EKS. Aplica-se apenas a tarefas ECS ou pods com launch type EC2. | idem |
| `split_line_item_public_on_demand_split_cost` | double | condicional (INCLUDE_SPLIT_COST_ALLOCATION_DATA) | — | — | — | Custo de vCPU ou memória alocado à tarefa/pod com base em taxas públicas On-Demand. | idem |
| `split_line_item_public_on_demand_unused_cost` | double | condicional (INCLUDE_SPLIT_COST_ALLOCATION_DATA) | — | — | — | Custo não usado de vCPU ou memória com base em taxas públicas On-Demand. | idem |
| `split_line_item_reserved_usage` | double | condicional (INCLUDE_SPLIT_COST_ALLOCATION_DATA) | — | — | — | Uso de vCPU, memória ou aceleradores configurado no período para a tarefa/pod. | idem |
| `split_line_item_split_cost` | double | condicional (INCLUDE_SPLIT_COST_ALLOCATION_DATA) | — | — | — | Custo de vCPU ou memória alocado no período à tarefa/pod, incluindo custos amortizados de reservas ou Savings Plans. | idem |
| `split_line_item_split_usage` | double | condicional (INCLUDE_SPLIT_COST_ALLOCATION_DATA) | — | — | — | Uso de vCPU ou memória alocado no período à tarefa/pod: máximo entre ReservedUsage e ActualUsage. | idem |
| `split_line_item_split_usage_ratio` | double | condicional (INCLUDE_SPLIT_COST_ALLOCATION_DATA) | — | — | — | Razão de recursos alocados à tarefa/pod em relação ao total disponível na instância EC2. | idem |
| `split_line_item_unused_cost` | double | condicional (INCLUDE_SPLIT_COST_ALLOCATION_DATA) | — | — | — | Custo não usado de vCPU, memória ou aceleradores alocado no período à tarefa/pod, incluindo custos amortizados. | idem |

### 3.13 Tags column (1)

Fonte-base: https://docs.aws.amazon.com/cur/latest/userguide/table-dictionary-cur2-tag-columns.md

| Campo | Tipo | Obrigatório | Unidade | Formato data/hora | Valores permitidos | Descrição | Fonte |
|---|---|---|---|---|---|---|---|
| `tags` | map \<string, string\> | — | — | — | — | Mapa com pares chave-valor de **todas** as tags (usuário, conta, categoria de custo e recurso). Valores sempre "string". Selecionar esta coluna dispensa selecionar Resource tags e Cost category. | https://docs.aws.amazon.com/cur/latest/userguide/table-dictionary-cur2-tag-columns.md#table-dictionary-cur2-tag-columns |

**Prefixos de tag documentados** (fonte: https://docs.aws.amazon.com/cur/latest/userguide/table-dictionary-cur2-tag-columns.md#table-dictionary-cur2-tag-prefixes): `resourceTags/`, `userAttribute/`, `accountTag/`, `costCategory/`, `iamPrincipal/`.

### 3.14 Contagem

| Grupo | Colunas |
|---|---|
| Bill | 8 |
| Cost category | 1 |
| Capacity reservation | 3 |
| Discount | 3 |
| Identity | 2 |
| Line item | 25 |
| Pricing | 10 |
| Product | 22 |
| Reservation | 27 |
| Resource tags | 1 |
| Savings plan | 17 |
| Split line item | 11 |
| Tags | 1 |
| **Total** | **131 nomes documentados** |

Contagem verificada por extração das tabelas HTML oficiais de cada página de grupo (as páginas de produto têm uma segunda tabela, "Service-specific product attributes", cujas 4 chaves de mapa **não** são colunas e por isso não entram na contagem). Somente o grupo "Capacity Reservation" não tem página própria, e o grupo "Capacity reservation" já está contado.

Divergência registrada: a documentação afirma "There are **125 possible columns** in the CUR 2.0 table", porém as 13 páginas de grupo documentam **131 nomes de coluna distintos**. Não escolhemos por conta própria: ver seção 5.

### 3.15 Table configurations (afetam o schema)

Fonte: https://docs.aws.amazon.com/cur/latest/userguide/table-dictionary-cur2.md#cur2-table-configurations (consultado em 2026-10-14).

| Configuração | Valores válidos | Efeito no schema | Nota da documentação |
|---|---|---|---|
| `TIME_GRANULARITY` | HOURLY, DAILY, MONTHLY | Altera a granularidade dos itens de linha | — |
| `INCLUDE_RESOURCES` | TRUE, FALSE | Adiciona `line_item_resource_id` | — |
| `INCLUDE_SPLIT_COST_ALLOCATION_DATA` | TRUE, FALSE | Adiciona as colunas `split_line_item_*` | — |
| `INCLUDE_CAPACITY_RESERVATION_DATA` | TRUE, FALSE | Adiciona 3 colunas de capacity reservation | Só adiciona dados nas novas colunas a partir de **1º de novembro de 2025** |
| `INCLUDE_IAM_PRINCIPAL_DATA` | TRUE, FALSE | Adiciona `line_item_iam_principal` | Só adiciona dados nas novas colunas a partir de **8 de abril de 2026** |
| `INCLUDE_MANUAL_DISCOUNT_COMPATIBILITY` | TRUE, FALSE | **Remove** `discount` e `total_discount` | Aplica-se apenas a clientes no programa Discount Automation |

## 4. Campos não comprovados

Os itens abaixo **não são gerados** pelo simulador. Motivo declarado em cada linha.

### 4.1 Chaves do `Manifest.json` (UNVERIFIED)

| Item | Status | Motivo |
|---|---|---|
| Nomes literais das chaves do `Manifest.json` que identificam colunas, arquivos de dados e período coberto | `UNVERIFIED` | A documentação oficial descreve o **conteúdo** do manifesto em prosa ("All of the columns…", "A list of the export files and their file path", "The time period covered by the export") mas **não publica um schema JSON, exemplo de manifesto ou os nomes de chave**. Única chave literal confirmada: `additionalOutputFiles` (https://docs.aws.amazon.com/cur/latest/userguide/dataexports-export-delivery.md). |
| `FocusVersion` (chave literal) | `VERIFIED` (nome e valores) / `UNVERIFIED` (tipo JSON) | A tabela comparativa em https://docs.aws.amazon.com/cur/latest/userguide/table-dictionary-focus-1-2-migrating.md lista "Manifest FocusVersion" com valores `"1.2"` e `"1.0"`. O tipo JSON (string) não é afirmado explicitamente; o uso de aspas na doc sugere string. |
| Ordem, aninhamento e obrigatoriedade das chaves do manifesto | `UNVERIFIED` | Não documentado. |
| Estrutura de `additionalOutputFiles` (chaves internas) | `UNVERIFIED` | Apenas a existência da seção é documentada; a estrutura interna não. |
| Nome do arquivo de manifesto (`<export-name>-Manifest.json` vs `Manifest.json`) | `DIVERGENTE` | A seção "Metadata" documenta `metadata/<partition>/<export-name>-Manifest.json`; o "Summary" da mesma página e a seção "create new"/"overwrite" documentam `metadata/<partition>/Manifest.json`. Ver seção 5. |
| `Compression` = `PARQUET` como sinônimo de Snappy | `UNVERIFIED` | A API lista `PARQUET` entre os valores válidos de `Compression`, mas a documentação **não afirma** que esse valor corresponda a Snappy. O único vínculo documentado entre Parquet e Snappy é a extensão de arquivo `.snappy.parquet`. |

### 4.2 Unidades monetárias (UNVERIFIED)

| Item | Status | Motivo |
|---|---|---|
| Unidade das colunas monetárias da CUR 2.0 (`line_item_blended_cost`, `line_item_unblended_cost`, `line_item_net_unblended_cost`, `pricing_public_on_demand_cost`, `reservation_*`, `savings_plan_*`, `discount_*`) | `UNVERIFIED` | A documentação de cada campo descreve a semântica, mas **não declara a moeda/unidade** dessas colunas. A única afirmação de moeda na tabela é: "All AWS customers are billed in US dollars by default" no campo `line_item_currency_code` (https://docs.aws.amazon.com/cur/latest/userguide/table-dictionary-cur2-line-item.md). A moeda efetiva do export é determinada em runtime por `line_item_currency_code`/`pricing_currency`, portanto **não fixamos USD** para essas colunas no `schema.json`. |
| Unidade de `line_item_usage_amount`, `line_item_normalized_usage_amount`, `split_line_item_*` | `UNVERIFIED` | A unidade é dependente do serviço e a documentação remete a `pricing_unit` / `lineItem/UsageType`, sem valor fixo. |

### 4.3 Formato e encoding para CSV/gzip (UNVERIFIED)

| Item | Status | Motivo |
|---|---|---|
| Presença de cabeçalho, delimitador e encoding do arquivo `text/csv` | `UNVERIFIED` | As páginas oficiais de entrega descrevem apenas os **nomes de arquivo** (`<export-name>-<chunk-number>.csv.gz`) e a opção de formato `TEXT_OR_CSV`. Não há afirmação sobre cabeçalho, delimitador ou encoding nesta documentação. |
| Schema/enumeração de `line_item_line_item_type` como lista fechada | `UNVERIFIED` (fechamento) | A documentação lista 14 tipos com descrição, mas não afirma que a lista seja exaustiva ou fechada. |

### 4.4 Páginas não recuperadas

| Item | Status | Motivo |
|---|---|---|
| Página própria do grupo "Capacity Reservation" (segunda entrada na lista de grupos) | `UNVERIFIED` | A lista de grupos em `table-dictionary-cur2.md` cita "Capacity reservation" e "Capacity Reservation"; as tentativas de URL para o segundo grupo retornaram HTTP 404. Não é possível afirmar se existe um segundo conjunto de colunas. |

## 5. Divergências conhecidas

Registradas sem escolha por parte desta spec.

1. **Contagem de colunas.** A documentação afirma 125 colunas possíveis; as 13 páginas de grupo documentam 131 nomes de coluna distintos (seção 3.14). Fontes: https://docs.aws.amazon.com/cur/latest/userguide/table-dictionary-cur2.md#cur2-column-groups ("There are 125 possible columns") vs. as páginas `table-dictionary-cur2-*`.

2. **Nome do arquivo de manifesto.** `metadata/<partition>/<export-name>-Manifest.json` (seção "Metadata") vs. `metadata/<partition>/Manifest.json` (seções "create new", "overwrite" e "Summary"). Ambas na mesma página: https://docs.aws.amazon.com/cur/latest/userguide/dataexports-export-delivery.md

3. **`product_to _location_type`.** O nome documentado contém um espaço antes de `location_type` (`product_to _location_type`), o que é incompatível com um identificador SQL válido. Fonte: https://docs.aws.amazon.com/cur/latest/userguide/table-dictionary-cur2-product.md. Esta spec preserva o texto exato da documentação.

4. **`product_instanceSKU`.** Casing misto (camelCase parcial) divergindo do snake_case do restante da tabela. Fonte: idem.

5. **Tipo de `line_item_blended_rate`, `line_item_net_unblended_rate`, `line_item_unblended_rate`, `reservation_normalized_units_per_reservation`, `reservation_number_of_reservations`, `reservation_total_reserved_normalized_units`, `reservation_total_reserved_units`, `reservation_units_per_reservation`.** Documentadas como `string` embora representem valores numéricos. Esta spec preserva o tipo exatamente como documentado.

6. **FOCUS 1.2 — descrição da especificação.** A página da tabela FOCUS 1.2 diz "formatted with FinOps Open Cost and Usage Specification (FOCUS) 1.0", enquanto o título, o nome SQL (`FOCUS_1_2_AWS`) e a página de migração tratam a tabela como FOCUS 1.2 (57 colunas FOCUS + 3 AWS). Fonte: https://docs.aws.amazon.com/cur/latest/userguide/table-dictionary-focus-1-2-aws.md. Trata-se de erro de redação da documentação; registrado sem correção unilateral.

7. **"FOCUS with AWS columns — there are no table configurations".** A página de criação de export no console afirma que FOCUS não tem table configurations, mas a página da tabela FOCUS 1.2 documenta `TIME_GRANULARITY`. Fontes: https://docs.aws.amazon.com/cur/latest/userguide/dataexports-create-standard.html vs. https://docs.aws.amazon.com/cur/latest/userguide/table-dictionary-focus-1-2-aws.md#focus-1-2-table-configurations. Provável texto residual de FOCUS 1.0 (que só exporta em HOURLY).
