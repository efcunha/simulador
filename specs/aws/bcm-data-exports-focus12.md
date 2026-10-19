# AWS BCM Data Exports — FOCUS 1.2 with AWS columns

## 1. Identificação

| Item | Valor |
|---|---|
| Nome oficial da superfície | **FOCUS 1.2 with AWS columns** (AWS Data Exports, AWS Billing and Cost Management / BCM Data Exports) |
| Nome SQL da tabela | `FOCUS_1_2_AWS` |
| Documento oficial (página da tabela) | *FOCUS 1.2 with AWS columns* — https://docs.aws.amazon.com/cur/latest/userguide/table-dictionary-focus-1-2-aws.md |
| Documento oficial (colunas) | *FOCUS 1.2 with AWS columns* (tabela de colunas) — https://docs.aws.amazon.com/cur/latest/userguide/table-dictionary-focus-1-2-aws-columns.md |
| Documento oficial (migração/versão) | *Migrating from FOCUS 1.0 to FOCUS 1.2* — https://docs.aws.amazon.com/cur/latest/userguide/table-dictionary-focus-1-2-migrating.md |
| Documento oficial (lacunas de conformidade) | *FOCUS 1.2 with AWS columns conformance gaps* — https://docs.aws.amazon.com/cur/latest/userguide/table-dictionary-focus-1-2-aws-conformance.md |
| Documento oficial (entrega) | *Understanding export delivery* — https://docs.aws.amazon.com/cur/latest/userguide/dataexports-export-delivery.md |
| Versão/schema de referência | **FOCUS 1.2**: 57 colunas da especificação FOCUS + 3 colunas proprietárias AWS (`x_Discounts`, `x_Operation`, `x_ServiceCode`) = **60 colunas** |
| Data de consulta | 2026-10-14 |

A documentação da AWS afirma textualmente (tabela comparativa de migração): "FOCUS 1.2 specification with 57 FOCUS columns + 3 AWS columns (60 total)". A contagem de 60 nomes de coluna foi confirmada por extração da tabela HTML oficial.

Nota: as colunas proprietárias da AWS usam o prefixo `x_`, que a especificação FOCUS reserva para extensões de provedor. A documentação lista exatamente três: `x_Discounts`, `x_Operation` e `x_ServiceCode`. Os nomes de coluna da parte FOCUS usam **PascalCase**, diferentemente do snake_case da CUR 2.0.

## 2. Mecanismo e entrega

### 2.1 Destino e formato

| Aspecto | Valor documentado | Fonte |
|---|---|---|
| Destino de entrega | Bucket Amazon S3 | https://docs.aws.amazon.com/cur/latest/userguide/table-dictionary-focus-1-2-migrating.md |
| Formatos de saída | `GZIP`, `Parquet` | idem |
| Compressão/formato na API | `Compression`: `GZIP` \| `PARQUET` \| `ZIP`; `Format`: `TEXT_OR_CSV` \| `PARQUET` | https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/API_DataExports_S3OutputConfigurations.html |
| Nome de arquivo Parquet | `<export-name>-<chunk-number>.snappy.parquet` | https://docs.aws.amazon.com/cur/latest/userguide/dataexports-export-delivery.md#export-data-file-names |
| Nome de arquivo gzip/csv | `<export-name>-<chunk-number>.csv.gz` | idem |
| Numeração de chunk | Sempre cinco dígitos, a partir de `00001` | idem |
| Fuso horário | UTC (convenção de timestamp dos campos desta tabela; ver seção 3) | https://docs.aws.amazon.com/cur/latest/userguide/table-dictionary-focus-1-2-aws-columns.md |

### 2.2 Layout no S3

A página *Understanding export delivery* descreve o mecanismo de entrega dos Data Exports e é a fonte aplicável a esta tabela. Ela documenta o caminho genérico e detalha a partição **explicitamente para a CUR 2.0** ("For CUR 2.0, the partition corresponds to the 'billing period' in the format `BILLING_PERIOD=YYYY-MM`").

Layout genérico documentado (aplicável ao export FOCUS 1.2, que é um Data Export entregue em S3):

```
# dados
s3://<bucket-name>/<prefix>/<export-name>/data/<partition>/

# metadados
s3://<bucket-name>/<prefix>/<export-name>/metadata/<partition>/<export-name>-Manifest.json
```

Modos de versionamento:

```
# create new (CREATE_NEW_REPORT)
s3://<bucket-name>/<prefix>/<export-name>/data/<partition>/<timestamp>-<execution-id>/
s3://<bucket-name>/<prefix>/<export-name>/metadata/<partition>/<timestamp>-<execution-id>
s3://<bucket-name>/<prefix>/<export-name>/metadata/<partition>/Manifest.json          # sempre o refresh mais recente

# overwrite (OVERWRITE_REPORT)
s3://<bucket-name>/<prefix>/<export-name>/data/<partition>/
s3://<bucket-name>/<prefix>/<export-name>/metadata/<partition>/Manifest.json
```

**Restrição de comprovação:** a documentação oficial **não afirma** que o valor literal da partição de um export FOCUS 1.2 seja `BILLING_PERIOD=YYYY-MM`. A única partição documentada com valor literal é a da CUR 2.0. Por isso o `partition_format` desta superfície fica `UNVERIFIED` no `schema.json` (ver seção 4).

### 2.3 Manifesto

O export FOCUS 1.2 emite o mesmo `Manifest.json` dos Data Exports. A documentação de migração confirma um campo específico desta tabela:

| Item | Valor documentado | Fonte |
|---|---|---|
| Campo `FocusVersion` no manifesto | `"1.2"` para a tabela FOCUS 1.2 (e `"1.0"` para FOCUS 1.0) | https://docs.aws.amazon.com/cur/latest/userguide/table-dictionary-focus-1-2-migrating.md |
| Conteúdo geral do manifesto | Todas as colunas incluídas no export; lista dos arquivos do export e seus caminhos; período coberto; seção `additionalOutputFiles` | https://docs.aws.amazon.com/cur/latest/userguide/dataexports-export-delivery.md |
| Momento da entrega | Só é entregue depois que todos os arquivos de dados foram entregues ao S3 | idem |
| Frequência | Atualizado a cada refresh; novo manifesto por nova partição | idem |

O schema completo do `Manifest.json` (nomes literais das chaves, ordem, tipos, aninhamento) **não é publicado** pela AWS; ver seção 4.

### 2.4 Table configurations

Fonte: https://docs.aws.amazon.com/cur/latest/userguide/table-dictionary-focus-1-2-aws.md#focus-1-2-table-configurations (consultado em 2026-10-14).

| Configuração | Valores válidos | Efeito |
|---|---|---|
| `TIME_GRANULARITY` | `HOURLY`, `DAILY`, `MONTHLY` | Altera a granularidade temporal dos itens de linha |

A tabela FOCUS 1.2 tem **somente** essa configuração (ao contrário da CUR 2.0). A página de criação de export no console afirma "For **FOCUS with AWS columns**, there are no table configurations" (https://docs.aws.amazon.com/cur/latest/userguide/dataexports-create-standard.html), o que diverge da página da tabela — ver seção 5.

### 2.5 Frequência de atualização

Fonte: https://docs.aws.amazon.com/cur/latest/userguide/dataexports-export-delivery.md (consultado em 2026-10-14). Os Data Exports de billing/cost são atualizados **até uma vez por dia** ("Daily - export is refreshed up to one time per day", conforme a página de criação no console). A documentação não publica um SLA distinto por tabela.

## 3. Campos

**60 colunas.** Todas as linhas desta seção foram extraídas da tabela oficial de colunas (https://docs.aws.amazon.com/cur/latest/userguide/table-dictionary-focus-1-2-aws-columns.md) em **2026-10-14**.

Convenções:

- **Tipo** = exatamente como a AWS documenta a coluna "Data type", incluindo `timestamp_milliseconds` e `map <string, string>`.
- **Obrigatório** = `sim` quando a AWS documenta "Null value allowed" = `No`; `não` quando documenta `Yes`. A AWS documenta a permissão de nulo para **todas** as 60 colunas, o que é incomum e específico desta tabela.
- **Valores permitidos** = somente quando a AWS enumera valores documentados; caso contrário `—`.
- **Formato data/hora** = as colunas `timestamp_milliseconds` não são acompanhadas de formato literal na página da AWS; o fuso não é afirmado por campo nesta tabela (ver seção 4).
- **Unidade** = ver seção 4. A AWS **não declara** unidade para nenhuma das 60 colunas desta tabela.

### 3.1 Colunas

| Campo | Tipo | Obrigatório | Unidade | Formato data/hora | Valores permitidos | Descrição | Fonte |
|---|---|---|---|---|---|---|---|
| `AvailabilityZone` | string | não | — | — | — | Identificador atribuído pelo provedor para uma área física separada e isolada dentro de uma Região, que provê alta disponibilidade e tolerância a falhas. | https://docs.aws.amazon.com/cur/latest/userguide/table-dictionary-focus-1-2-aws-columns.md |
| `BilledCost` | double | sim | — | — | — | Encargo que serve de base para a fatura, incluindo todas as taxas reduzidas e descontos, excluindo a amortização de encargos antecipados (únicos ou recorrentes). | idem |
| `BillingAccountId` | string | sim | — | — | — | Identificador atribuído a uma conta de faturamento pelo provedor. | idem |
| `BillingAccountName` | string | não | — | — | — | Nome de exibição atribuído a uma conta de faturamento. | idem |
| `BillingAccountType` | string | sim | — | — | — | Nome atribuído pelo provedor para identificar o tipo de conta de faturamento. | idem |
| `BillingCurrency` | string | sim | — | — | — | Moeda na qual um encargo foi faturado. | idem |
| `BillingPeriodEnd` | timestamp_milliseconds | sim | — | — | — | Limite final exclusivo de um período de faturamento. | idem |
| `BillingPeriodStart` | timestamp_milliseconds | sim | — | — | — | Limite inicial inclusivo de um período de faturamento. | idem |
| `CapacityReservationId` | string | não | — | — | — | Identificador atribuído a uma capacity reservation pelo provedor. | idem |
| `CapacityReservationStatus` | string | não | — | — | — | Indica se o encargo representa o consumo de uma capacity reservation ou quando ela está não utilizada. | idem |
| `ChargeCategory` | string | sim | — | — | — | Classificação de mais alto nível de um encargo, com base na natureza de como é faturado. | idem |
| `ChargeClass` | string | não | — | — | — | Indica se a linha representa uma correção de um período de faturamento faturado anteriormente. | idem |
| `ChargeDescription` | string | não | — | — | — | Resumo autocontido do propósito e do preço do encargo. | idem |
| `ChargeFrequency` | string | sim | — | — | — | Indica com que frequência um encargo ocorrerá. | idem |
| `ChargePeriodEnd` | timestamp_milliseconds | sim | — | — | — | Limite final exclusivo de um período de encargo. | idem |
| `ChargePeriodStart` | timestamp_milliseconds | sim | — | — | — | Limite inicial inclusivo de um período de encargo. | idem |
| `CommitmentDiscountCategory` | string | não | — | — | — | Indica se o desconto de compromisso identificado em `CommitmentDiscountId` é baseado em quantidade de uso ou em custo (ou seja, "spend"). | idem |
| `CommitmentDiscountId` | string | não | — | — | — | Identificador atribuído a um desconto de compromisso pelo provedor. | idem |
| `CommitmentDiscountName` | string | não | — | — | — | Nome de exibição atribuído a um desconto de compromisso. | idem |
| `CommitmentDiscountQuantity` | double | não | — | — | — | Quantidade de um desconto de compromisso comprada ou contabilizada em linhas relacionadas a desconto de compromisso, denominada em Commitment Discount Units. | idem |
| `CommitmentDiscountStatus` | string | não | — | — | — | Indica se o encargo corresponde ao consumo de um desconto de compromisso ou à porção não utilizada do valor comprometido. | idem |
| `CommitmentDiscountType` | string | não | — | — | — | Identificador atribuído pelo provedor para o tipo de desconto de compromisso aplicado à linha. | idem |
| `CommitmentDiscountUnit` | string | não | — | — | — | Unidade de medida especificada pelo provedor que indica como ele mede a `CommitmentDiscountQuantity` de um desconto de compromisso. | idem |
| `ConsumedQuantity` | double | não | — | — | — | Volume de um SKU medido, associado a um recurso ou serviço utilizado, com base na `ConsumedUnit`. | idem |
| `ConsumedUnit` | string | não | — | — | — | Unidade de medida especificada pelo provedor que indica como ele mede o uso de um SKU medido associado a um recurso ou serviço. | idem |
| `ContractedCost` | double | sim | — | — | — | Custo calculado multiplicando o preço unitário contratado pela `PricingQuantity` correspondente. | idem |
| `ContractedUnitPrice` | double | não | — | — | — | Preço unitário acordado para uma unidade de preço do SKU associado, incluindo descontos negociados, se houver, excluindo descontos de compromisso negociados ou quaisquer outros descontos. | idem |
| `EffectiveCost` | double | sim | — | — | — | Custo amortizado do encargo após aplicar todas as taxas reduzidas, descontos e a porção aplicável de compras pré-pagas relevantes (únicas ou recorrentes) que cobriram este encargo. | idem |
| `InvoiceId` | string | não | — | — | — | Identificador atribuído pelo provedor para uma fatura que encapsula parte ou todos os encargos do período de faturamento correspondente de uma dada conta de faturamento. | idem |
| `InvoiceIssuerName` | string | sim | — | — | — | Nome da entidade responsável pela emissão da fatura dos recursos ou serviços consumidos. | idem |
| `ListCost` | double | sim | — | — | — | Custo calculado multiplicando o `ListUnitPrice` pela `PricingQuantity` correspondente. | idem |
| `ListUnitPrice` | double | não | — | — | — | Preço unitário sugerido, publicado pelo provedor, para uma unidade de preço do SKU associado, excluindo quaisquer descontos. | idem |
| `PricingCategory` | string | não | — | — | — | Descreve o modelo de precificação usado para um encargo no momento do uso ou da compra. | idem |
| `PricingCurrency` | string | não | — | — | — | Denominação de moeda nacional ou virtual na qual um recurso ou serviço foi precificado. | idem |
| `PricingCurrencyContractedUnitPrice` | double | não | — | — | — | Preço unitário acordado para uma unidade de preço do SKU associado, incluindo descontos negociados, se houver, excluindo descontos de compromisso negociados ou quaisquer outros descontos, **expresso em `PricingCurrency`**. | idem |
| `PricingCurrencyEffectiveCost` | double | não | — | — | — | Custo do encargo após aplicar todas as taxas reduzidas, descontos e a porção aplicável de compras pré-pagas relevantes que cobriram este encargo, **denominado em `PricingCurrency`**. | idem |
| `PricingCurrencyListUnitPrice` | double | não | — | — | — | Preço unitário sugerido, publicado pelo provedor, para uma unidade de preço do SKU associado, excluindo quaisquer descontos e **expresso em `PricingCurrency`**. | idem |
| `PricingQuantity` | double | não | — | — | — | Volume de um dado SKU associado a um recurso ou serviço usado ou comprado, com base na `PricingUnit`. | idem |
| `PricingUnit` | string | não | — | — | — | Unidade de medida especificada pelo provedor para determinar preços unitários, indicando como ele tarifa o uso medido e as quantidades compradas após aplicar regras de preço como block pricing. | idem |
| `ProviderName` | string | sim | — | — | — | Nome da entidade que disponibilizou os recursos ou serviços para compra. | idem |
| `PublisherName` | string | sim | — | — | — | Nome da entidade que produziu os recursos ou serviços que foram comprados. | idem |
| `RegionId` | string | não | — | — | — | Identificador atribuído pelo provedor para uma área geográfica isolada onde um recurso é provisionado ou um serviço é fornecido. | idem |
| `RegionName` | string | não | — | — | — | Nome de uma área geográfica isolada onde um recurso é provisionado ou um serviço é fornecido. | idem |
| `ResourceId` | string | não | — | — | — | Identificador atribuído a um recurso pelo provedor. | idem |
| `ResourceName` | string | não | — | — | — | Nome de exibição atribuído a um recurso. | idem |
| `ResourceType` | string | não | — | — | — | O tipo de recurso ao qual o encargo se aplica. | idem |
| `ServiceCategory` | string | sim | — | — | — | Classificação de mais alto nível de um serviço, com base na função central do serviço. | idem |
| `ServiceName` | string | sim | — | — | — | Uma oferta que pode ser comprada de um provedor (por exemplo, máquina virtual em nuvem, banco de dados SaaS, serviços profissionais de um integrador de sistemas). | idem |
| `ServiceSubcategory` | string | sim | — | — | — | Classificação secundária da `ServiceCategory` de um serviço, com base em sua função central. | idem |
| `SkuId` | string | não | — | — | — | Identificador único especificado pelo provedor que representa um SKU específico (por exemplo, uma oferta quantificável de bem ou serviço). | idem |
| `SkuMeter` | string | não | — | — | — | Descreve a funcionalidade que está sendo medida por um SKU específico em um encargo. | idem |
| `SkuPriceId` | string | não | — | — | — | Identificador único especificado pelo provedor que representa um preço de SKU específico associado a um recurso ou serviço usado ou comprado. | idem |
| `SkuPriceDetails` | map \<string, string\> | não | — | — | — | Conjunto de propriedades de um `SkuPriceId` que são significativas e comuns a todas as instâncias daquele `SkuPriceId`. | idem |
| `SubAccountId` | string | não | — | — | — | ID atribuído a um agrupamento de recursos ou serviços, frequentemente usado para gerenciar acesso e/ou custo. | idem |
| `SubAccountName` | string | não | — | — | — | Nome atribuído a um agrupamento de recursos ou serviços, frequentemente usado para gerenciar acesso e/ou custo. | idem |
| `SubAccountType` | string | não | — | — | — | Nome atribuído pelo provedor para identificar o tipo de subconta. | idem |
| `Tags` | map \<string, string\> | não | — | — | — | Conjunto de tags atribuídas a fontes de tag que respondem por potenciais avaliações de tags definidas pelo provedor ou pelo usuário. | idem |
| `x_Discounts` | map \<string, double\> | não | — | — | — | Coluna de mapa com pares chave-valor de quaisquer descontos específicos que se aplicam a este item de linha. | idem |
| `x_Operation` | string | não | — | — | — | A operação AWS específica coberta por este item de linha. Por exemplo, `RunInstances` indica a operação de uma instância Amazon EC2. | idem |
| `x_ServiceCode` | string | não | — | — | — | O código do produto medido. Por exemplo, Amazon EC2 é o código de produto do Amazon Elastic Compute Cloud. | idem |

### 3.2 Diferenças de schema em relação a FOCUS 1.0

Fonte: https://docs.aws.amazon.com/cur/latest/userguide/table-dictionary-focus-1-2-migrating.md (consultado em 2026-10-14).

| Aspecto | FOCUS 1.2 | FOCUS 1.0 |
|---|---|---|
| Schema | 57 colunas FOCUS + 3 colunas AWS (**60**) | 43 colunas FOCUS + 5 colunas AWS (48) |
| Nome SQL da tabela | `FOCUS_1_2_AWS` | `FOCUS_1_0_AWS` |
| `Manifest` `FocusVersion` | `"1.2"` | `"1.0"` |
| Formatos de saída | `GZIP`, `Parquet` | `GZIP`, `Parquet` |
| Table configurations | `TIME_GRANULARITY` = `HOURLY`, `DAILY`, `MONTHLY` | exporta apenas em `HOURLY` |

Colunas **novas** em 1.2 (trecho da coluna "New columns"): `InvoiceIssuerId`, `CapacityReservationId`, `CapacityReservationStatus`, `CommitmentDiscountQuantity`, `CommitmentDiscountUnit`, `ServiceSubcategory`, `SkuMeter`, `SkuPriceDetails`, `PricingCurrency`, `PricingCurrencyEffectiveCost`, `PricingCurrencyListUnitPrice`, `PricingCurrencyContractedUnitPrice`, `BillingAccountType`, `SubAccountType`.

Colunas **removidas** de 1.0 para 1.2: `x_UsageType` (passou a ser `SkuMeter`) e `x_CostCategories` (passou a ser incluído na coluna `Tags` com o prefixo `aws:tags:CostCategory/`).

Divergência interna registrada: a coluna `InvoiceIssuerId` é listada como **nova** em 1.2, mas **não aparece** na tabela de colunas da página oficial (que contém `InvoiceIssuerName`, e não `InvoiceIssuerId`). Ver seção 5.

Mudanças de comportamento (não de schema) relevantes:

| Item | FOCUS 1.2 | FOCUS 1.0 |
|---|---|---|
| Contagem de linhas | Itens de ODCR e EC2 Capacity Blocks for ML passam a ser divididos em status "Used" e "Unused", aumentando a contagem de linhas | Sem detalhamento de status de capacity reservation |
| `PricingCategory` | Compras de desconto de compromisso (taxas antecipadas de RI e Savings Plan) passam a ser categorizadas como `Standard` | Compras categorizadas como `Committed` |
| Nulabilidade de `ConsumedQuantity` | Nulo quando `CommitmentDiscountStatus` é `Unused` | Valor `0` quando `CommitmentDiscountStatus` é `Unused` |
| Nulabilidade de `ConsumedUnit` | Atrelada à de `ConsumedQuantity` (deve ser nulo quando `ConsumedQuantity` é nulo) | Regras de nulabilidade independentes |
| Requisito da coluna de tags | Inclui tags de recurso definidas pelo usuário e pelo provedor, e tags de categoria de custo definidas pelo usuário | Inclui apenas tags de recurso definidas pelo usuário e pelo provedor |

### 3.3 Lacunas de conformidade declaradas pela AWS

Fonte: https://docs.aws.amazon.com/cur/latest/userguide/table-dictionary-focus-1-2-aws-conformance.md (consultado em 2026-10-14). Estas lacunas são **afirmadas pela própria AWS** e devem ser reproduzidas, não corrigidas.

**Missing data:**

| Coluna afetada | Requisito FOCUS 1.2 | Lacuna declarada |
|---|---|---|
| `ContractedUnitPrice` | não deve ser nulo para itens `Usage` e `Purchase` que não sejam correções | pode ser nulo para certas ofertas de produto |
| `InvoiceIssuerName` | não deve ser nulo | pode ser nulo para certos encargos |
| `ListUnitPrice` | não deve ser nulo para itens `Usage` e `Purchase` que não sejam correções | pode ser nulo para certas ofertas de produto |
| `PricingUnit` | não deve ser nulo para itens `Usage` e `Purchase` que não sejam correções | pode ser nulo para certas ofertas de produto |
| `PublisherName` | não deve ser nulo | pode ser nulo para certos encargos |
| `SkuId` | não deve ser nulo para itens `Usage` e `Purchase` que não sejam correções | pode ser nulo para certas ofertas de produto |
| `SkuPriceId` | não deve ser nulo para itens `Usage` e `Purchase` que não sejam correções | pode ser nulo para certos itens quando não deveria |
| `CapacityReservationStatus` | não deve ser nulo quando `CapacityReservationId` não é nulo e `ChargeCategory` é `Usage` | pode ser nulo para uma capacity reservation em estado reserved, não sendo "used" nem "unused" |

**Incorrect data:**

| Coluna afetada | Requisito FOCUS 1.2 | Lacuna declarada |
|---|---|---|
| `ConsumedQuantity` | é coluna obrigatória para mostrar a quantidade de uso efetivamente usada | conterá a quantidade de uso **cobrada**; pode estar incorreta quando um mínimo cobrado se aplica (ex.: mínimo de 10 MB por consulta Athena, mínimo de 10 minutos por execução de Glue crawler) |
| `SkuMeter` | deve ser nulo quando `SkuId` é nulo | pode ser nulo para certas ofertas de produto |
| `ConsumedUnit` | nulabilidade deve corresponder à de `ConsumedQuantity` | pode ser nulo para certas ofertas de produto que têm `ConsumedQuantity` |

## 4. Campos não comprovados

Os itens abaixo **não são gerados** pelo simulador (ou são gerados sem afirmação de valor). Motivo declarado em cada linha.

### 4.1 Unidade de todas as 60 colunas (UNVERIFIED)

| Item | Status | Motivo |
|---|---|---|
| Unidade monetária de `BilledCost`, `EffectiveCost`, `ListCost`, `ContractedCost`, `ContractedUnitPrice`, `ListUnitPrice`, `PricingCurrencyContractedUnitPrice`, `PricingCurrencyEffectiveCost`, `PricingCurrencyListUnitPrice`, `x_Discounts` | `UNVERIFIED` | A página oficial de colunas documenta tipo e nulabilidade, mas **não declara unidade nem moeda** para nenhuma coluna. Existe a coluna `BillingCurrency` ("a moeda na qual um encargo foi faturado"), mas a AWS não afirma que `BilledCost` esteja denominada nela. Tentativas de consultar a especificação FOCUS 1.2 do FinOps (`https://focus.finops.org/focus-specification/v1-2/`, `https://focus.finops.org/docs/specification/v1-2/columns/`, PDF oficial em `focus.finops.org/wp-content/uploads/2025/05/FOCUS-spec-v1_2.pdf`) retornaram **HTTP 403**, portanto não foi possível comprovar por fonte oficial. |
| Unidades de `CommitmentDiscountQuantity`, `CommitmentDiscountUnit`, `ConsumedQuantity`, `ConsumedUnit`, `PricingQuantity`, `PricingUnit` | `UNVERIFIED` | A documentação afirma que as unidades são "provider-specified" / "denominadas em Commitment Discount Units" e **não enumera** valores. Sem enumeração oficial, não há valores a gerar. |

### 4.2 Formato e fuso dos timestamps (UNVERIFIED)

| Item | Status | Motivo |
|---|---|---|
| Formato literal e fuso de `BillingPeriodStart`, `BillingPeriodEnd`, `ChargePeriodStart`, `ChargePeriodEnd` | `UNVERIFIED` | O tipo é documentado como `timestamp_milliseconds`, mas a página oficial **não** informa o formato serializado nem afirma UTC para esses campos. Ao contrário da CUR 2.0 (que afirma explicitamente "in UTC. The format is `YYYY-MM-DDTHH:mm:ssZ`"), esta tabela não traz essa afirmação. |

### 4.3 Valores permitidos (UNVERIFIED)

| Item | Status | Motivo |
|---|---|---|
| Valores permitidos de `ChargeCategory`, `ChargeClass`, `ChargeFrequency`, `CommitmentDiscountCategory`, `CommitmentDiscountStatus`, `CommitmentDiscountType`, `PricingCategory`, `ServiceCategory`, `ServiceSubcategory`, `BillingAccountType`, `SubAccountType`, `CapacityReservationStatus`, `ResourceType` | `UNVERIFIED` | A AWS documenta a **semântica** dessas colunas, mas **não enumera os valores válidos** nesta página. A especificação FOCUS 1.2, que os enumeraria, está inacessível (HTTP 403). |
| Prefixos de tag usados na coluna `Tags` (ex.: `aws:tags:CostCategory/`) | `PARCIAL` | A página de migração cita o prefixo `aws:tags:CostCategory/` para tags de categoria de custo. A lista completa de prefixos **não** é publicada para esta tabela. |

### 4.4 Partição de entrega (UNVERIFIED)

| Item | Status | Motivo |
|---|---|---|
| Valor literal da partição `<partition>` de um export FOCUS 1.2 (se é `BILLING_PERIOD=YYYY-MM` ou outro) | `UNVERIFIED` | A documentação de entrega descreve o caminho genérico `data/<partition>/` e detalha a partição **explicitamente apenas para a CUR 2.0**. Não afirma qual é a partição da tabela FOCUS 1.2. |

### 4.5 Manifesto (UNVERIFIED)

| Item | Status | Motivo |
|---|---|---|
| Nomes literais das chaves do `Manifest.json` de um export FOCUS 1.2 (colunas, arquivos, período) | `UNVERIFIED` | A AWS descreve o conteúdo do manifesto em prosa e não publica schema, exemplo ou lista de chaves. Única chave literal confirmada: `additionalOutputFiles`; único campo confirmado para esta tabela: `FocusVersion` = `"1.2"`. |
| Tipo JSON do valor `FocusVersion` | `UNVERIFIED` | Nome e valores (`"1.2"`) são documentados; o tipo JSON não é afirmado explicitamente. |
| Estrutura interna da seção `additionalOutputFiles` | `UNVERIFIED` | Apenas a existência da seção é documentada. |

### 4.6 Coluna `InvoiceIssuerId` (UNVERIFIED)

| Item | Status | Motivo |
|---|---|---|
| `InvoiceIssuerId` | `UNVERIFIED` | A página de migração lista `InvoiceIssuerId` entre as colunas **novas** do FOCUS 1.2, mas a página oficial de colunas da tabela **não a contém** (contém `InvoiceIssuerName`). Como não há linha na tabela de colunas que a documente, ela não entra em `columns` e não é gerada. Ver seção 5. |

### 4.7 CSV/gzip (UNVERIFIED)

| Item | Status | Motivo |
|---|---|---|
| Presença de cabeçalho, delimitador e encoding do arquivo `text/csv` | `UNVERIFIED` | A documentação de entrega define apenas nomes de arquivo e as opções de formato; não afirma cabeçalho, delimitador nem encoding. |

## 5. Divergências conhecidas

Registradas sem escolha por parte desta spec.

1. **Descrição da especificação na página da tabela.** A página afirma que a tabela contém dados "formatted with FinOps Open Cost and Usage Specification (FOCUS) **1.0**", enquanto o título é "FOCUS **1.2** with AWS columns", o nome SQL é `FOCUS_1_2_AWS` e a página de migração trata a tabela como FOCUS 1.2. Fonte: https://docs.aws.amazon.com/cur/latest/userguide/table-dictionary-focus-1-2-aws.md. Trata-se de texto residual da versão 1.0 na documentação; registrado sem correção unilateral.

2. **`InvoiceIssuerId` vs. tabela de colunas.** A tabela de migração lista `InvoiceIssuerId` como coluna nova do 1.2, mas a tabela oficial de colunas não a inclui (apenas `InvoiceIssuerName`). Fontes: https://docs.aws.amazon.com/cur/latest/userguide/table-dictionary-focus-1-2-migrating.md vs. https://docs.aws.amazon.com/cur/latest/userguide/table-dictionary-focus-1-2-aws-columns.md.

3. **"FOCUS with AWS columns — there are no table configurations".** A página de criação de export no console afirma que FOCUS não tem table configurations; a página da tabela FOCUS 1.2 documenta `TIME_GRANULARITY`. Fontes: https://docs.aws.amazon.com/cur/latest/userguide/dataexports-create-standard.html vs. https://docs.aws.amazon.com/cur/latest/userguide/table-dictionary-focus-1-2-aws.md#focus-1-2-table-configurations.

4. **Contagem de colunas 57 + 3 = 60 vs. presença de `InvoiceIssuerId`.** A contagem oficial (60) confere exatamente com a tabela de colunas publicada, o que reforça que `InvoiceIssuerId` não existe no schema desta tabela apesar da menção na página de migração.

5. **Formato de timestamp.** As quatro colunas de período usam o tipo `timestamp_milliseconds`, enquanto a CUR 2.0 usa `timestamp` com formato `YYYY-MM-DDTHH:mm:ssZ` em UTC. A diferença de tipo entre as duas tabelas é documentada; a representação serializada do `timestamp_milliseconds` não é.

6. **Erro de redação na página de colunas da CUR 2.0.** A descrição de `product_to_region_code` na documentação da CUR 2.0 diz "Describes the source Region code for the AWS service", o mesmo texto de `product_from_region_code`, embora o nome indique destino. Fonte: https://docs.aws.amazon.com/cur/latest/userguide/table-dictionary-cur2-product.md. Registrado aqui por afetar o entendimento conjunto das superfícies AWS; a ocorrência está detalhada em `specs/aws/bcm-data-exports-cur2.md`.
