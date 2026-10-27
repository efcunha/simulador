# O que este projeto ainda NÃO provou

> Idioma: **Português** | [English](NAO-COMPROVADOS.en.md)

Registro **derivado das especificações** — a fonte normativa deste repositório — por `.artifacts/gerar-registro-nao-comprovados.py`. Ele existe porque as lacunas estavam declaradas dentro de cada spec, campo a campo, e não havia um lugar único que respondesse *"o que ainda não foi provado?"*; vários docstrings do gerador apontavam para um `docs/synthetic-clouds/UNVERIFIED.md` que **só existe dentro do repositório do FinOps**.

**Nada aqui é novo.** Cada linha é um `unverified` que já estava escrito na spec, com o motivo que o autor registrou. O que este documento acrescenta é a **consolidação** e a **contagem** — e é por isso que ele é gerado, e não escrito à mão: uma segunda lista manteria duas verdades sobre o mesmo assunto.

**Uma correção de leitura que vale registrar:** `spec.unverified` expõe apenas os **nomes**. Os motivos vivem em `unverified_fields` (nome que não pertence ao contrato) e `unverified_topics` (assunto que existe no contrato e cuja prova falta), e os dois precisam ser lidos: juntos dão 288 itens em **49** superfícies. Um registro que lesse só a lista de nomes daria um terço do problema e nenhum motivo — que é metade do valor para quem for fechar a lacuna. Os números são calculados, não escritos: um total fixo envelhecia em silêncio assim que uma lacuna fosse fechada por evidência.

## Números (na revisão em que foi gerado)

* **288 itens não comprovados** em **49 de 49 superfícies** (ou seja: **nenhuma** superfície está sem lacuna declarada).
* Por provedor: **aws** 88, **azure** 83, **gcp** 117.
* Por tipo: **campo** = o nome não pertence ao contrato; **tema** = o nome existe e a prova de que o valor é canônico falta.

**Como ler cada item.** Uma spec declara dois tipos de não comprovado, e a diferença importa:

* **campo** (`name`) — o nome **não pertence** ao contrato daquela superfície. Emiti-lo é `invented`/`unverified_emitted`, e o auditor acusa. É o caso da chave de junção `resourceUuid`, que nenhum dos contratos oficiais declara.
* **tema** (`item`) — o nome **existe** no contrato (dentro de um mapa ou de um objeto), e o que falta é a **prova** de que aquele valor/chave é canônico. Registrar como campo seria dizer que ele não pertence ao formato, e ele pertence.

A coluna *tipo* abaixo é essa distinção, lida do JSON da spec (`name` vs `item`).

## `aws/aws-config-snapshot-s3` — 18 item(ns)

Spec: [`specs/aws/aws-config-snapshot-s3.schema.json`](../specs/aws/aws-config-snapshot-s3.schema.json)

| tipo | item | motivo declarado |
|---|---|---|
| campo | `configurationItemDeliveryTime in S3 file` | documented as optional and not guaranteed; absent from the official file example |
| campo | `recordingFrequency in S3 file` | documented as API-response-only when DAILY recording is enabled |
| campo | `supplementaryConfiguration in S3 file` | documented in API schema only; absent from official file example |
| campo | `resourceName in S3 file` | documented in API schema only; absent from official file example |
| campo | `file character encoding` | not documented |
| campo | `formal s3ObjectKey template` | AWS publishes literal examples only, not a placeholder template; templates here are marked derived |
| campo | `manifest/index artifact` | no manifest is described in any consulted official page (negative evidence) |
| campo | `SNS envelope schema` | standard SNS envelope appears in examples but is not defined by AWS Config documentation |
| campo | `Configuration Snapshot Delivery Started notification` | example page could not be retrieved; referenced by navigation only |
| tema | `configurationItemDeliveryTime in S3 file` | documented as optional and not guaranteed; absent from the official file example |
| tema | `recordingFrequency in S3 file` | documented as API-response-only when DAILY recording is enabled |
| tema | `supplementaryConfiguration in S3 file` | documented in API schema only; absent from official file example |
| tema | `resourceName in S3 file` | documented in API schema only; absent from official file example |
| tema | `file character encoding` | not documented |
| tema | `formal s3ObjectKey template` | AWS publishes literal examples only, not a placeholder template; templates here are marked derived |
| tema | `manifest/index artifact` | no manifest is described in any consulted official page (negative evidence) |
| tema | `SNS envelope schema` | standard SNS envelope appears in examples but is not defined by AWS Config documentation |
| tema | `Configuration Snapshot Delivery Started notification` | example page could not be retrieved; referenced by navigation only |

## `aws/bcm-data-exports-cur2` — 22 item(ns)

Spec: [`specs/aws/bcm-data-exports-cur2.schema.json`](../specs/aws/bcm-data-exports-cur2.schema.json)

| tipo | item | motivo declarado |
|---|---|---|
| campo | `Manifest.json key names for columns, data files and covered period` | AWS documents the manifest contents in prose only; no JSON schema, key list or example is published. Only the literal key additionalOutputFiles is confirmed. |
| campo | `Manifest.json key order, nesting and required/optional status` | Not documented. |
| campo | `Structure of the additionalOutputFiles section` | Only the section name is documented; its internal structure is not. |
| campo | `JSON type of the FocusVersion manifest value` | Name and values ('1.2' / '1.0') are documented; the JSON type is not explicitly stated. |
| campo | `Manifest file name (<export-name>-Manifest.json vs Manifest.json)` | The Metadata section and the Summary section of the same page document different file names. |
| campo | `Compression parameter value PARQUET equals Snappy` | PARQUET is a documented valid value of the Compression parameter, but the documentation never states it maps to Snappy. The only documented Parquet/Snappy link is the .snappy.parquet file extension. |
| campo | `Currency/unit of monetary CUR 2.0 columns (line_item_*_cost, pricing_public_on_demand_cost, reservation_*, savings_plan_*, discount_*)` | Field documentation describes semantics but never declares the currency unit. The only currency statement in the table is 'All AWS customers are billed in US dollars by default' on line_item_currency_code; the actual export currency is runtime-determined by line_item_currency_code and pricing_currency. |
| campo | `Unit of line_item_usage_amount, line_item_normalized_usage_amount and split_line_item_* usage columns` | Unit is service-dependent; the documentation refers to pricing_unit / lineItem/UsageType without a fixed value. |
| campo | `CSV/gzip header, delimiter and encoding` | The delivery documentation defines only file names and the TEXT_OR_CSV format option; it makes no statement about header, delimiter or encoding. |
| campo | `Whether the line_item_line_item_type value list is exhaustive` | 14 values are documented with descriptions, but the documentation does not state the list is closed. |
| campo | `Second 'Capacity Reservation' column group` | The column-group list names both 'Capacity reservation' and 'Capacity Reservation'. No own page could be retrieved for the second (HTTP 404 on candidate URLs); it cannot be confirmed whether a separate set of columns exists. |
| tema | `Manifest.json key names for columns, data files and covered period` | AWS documents the manifest contents in prose only; no JSON schema, key list or example is published. Only the literal key additionalOutputFiles is confirmed. |
| tema | `Manifest.json key order, nesting and required/optional status` | Not documented. |
| tema | `Structure of the additionalOutputFiles section` | Only the section name is documented; its internal structure is not. |
| tema | `JSON type of the FocusVersion manifest value` | Name and values ('1.2' / '1.0') are documented; the JSON type is not explicitly stated. |
| tema | `Manifest file name (<export-name>-Manifest.json vs Manifest.json)` | The Metadata section and the Summary section of the same page document different file names. |
| tema | `Compression parameter value PARQUET equals Snappy` | PARQUET is a documented valid value of the Compression parameter, but the documentation never states it maps to Snappy. The only documented Parquet/Snappy link is the .snappy.parquet file extension. |
| tema | `Currency/unit of monetary CUR 2.0 columns (line_item_*_cost, pricing_public_on_demand_cost, reservation_*, savings_plan_*, discount_*)` | Field documentation describes semantics but never declares the currency unit. The only currency statement in the table is 'All AWS customers are billed in US dollars by default' on line_item_currency_code; the actual export currency is runtime-determined by line_item_currency_code and pricing_currency. |
| tema | `Unit of line_item_usage_amount, line_item_normalized_usage_amount and split_line_item_* usage columns` | Unit is service-dependent; the documentation refers to pricing_unit / lineItem/UsageType without a fixed value. |
| tema | `CSV/gzip header, delimiter and encoding` | The delivery documentation defines only file names and the TEXT_OR_CSV format option; it makes no statement about header, delimiter or encoding. |
| tema | `Whether the line_item_line_item_type value list is exhaustive` | 14 values are documented with descriptions, but the documentation does not state the list is closed. |
| tema | `Second 'Capacity Reservation' column group` | The column-group list names both 'Capacity reservation' and 'Capacity Reservation'. No own page could be retrieved for the second (HTTP 404 on candidate URLs); it cannot be confirmed whether a separate set of columns exists. |

## `aws/bcm-data-exports-focus12` — 20 item(ns)

Spec: [`specs/aws/bcm-data-exports-focus12.schema.json`](../specs/aws/bcm-data-exports-focus12.schema.json)

| tipo | item | motivo declarado |
|---|---|---|
| campo | `Currency/unit of all monetary columns (BilledCost, EffectiveCost, ListCost, ContractedCost, ContractedUnitPrice, ListUnitPrice, PricingCurrencyContractedUnitPrice, PricingCurrencyEffectiveCost, PricingCurrencyListUnitPrice, x_Discounts)` | The official column page documents type and nullability but never declares unit or currency. BillingCurrency exists as a column, but AWS does not state that BilledCost is denominated in it. The FinOps FOCUS 1.2 specification (focus.finops.org, incl. the official PDF) returned HTTP 403 on every attempt, so units could not be verified from an official source. |
| campo | `Units of CommitmentDiscountQuantity, CommitmentDiscountUnit, ConsumedQuantity, ConsumedUnit, PricingQuantity, PricingUnit` | AWS documents these as provider-specified or 'denominated in Commitment Discount Units' and does not enumerate values. |
| campo | `Literal timestamp format and timezone of BillingPeriodStart, BillingPeriodEnd, ChargePeriodStart, ChargePeriodEnd` | The type is documented as timestamp_milliseconds, but the page states neither the serialized format nor UTC for these columns (unlike CUR 2.0, which explicitly states UTC and YYYY-MM-DDTHH:mm:ssZ). |
| campo | `Allowed values of ChargeCategory, ChargeClass, ChargeFrequency, CommitmentDiscountCategory, CommitmentDiscountStatus, CommitmentDiscountType, PricingCategory, ServiceCategory, ServiceSubcategory, BillingAccountType, SubAccountType, CapacityReservationStatus, ResourceType` | AWS documents the semantics but does not enumerate valid values on this page; the FOCUS 1.2 specification that enumerates them was unreachable (HTTP 403). |
| campo | `Complete list of tag prefixes used in the Tags column` | The migration page mentions the aws:tags:CostCategory/ prefix, but no complete prefix list is published for this table. |
| campo | `Literal value of the S3 partition for a FOCUS 1.2 export` | The delivery documentation describes data/<partition>/ generically and details the partition explicitly only for CUR 2.0 (BILLING_PERIOD=YYYY-MM). The FOCUS 1.2 partition is never stated. |
| campo | `Manifest.json literal key names for columns, data files and covered period` | AWS documents the manifest contents in prose only; no JSON schema, key list or example is published. |
| campo | `JSON type of the FocusVersion manifest value and internal structure of additionalOutputFiles` | Name and value ('1.2') are documented; the JSON type is not stated, and the internal structure of additionalOutputFiles is not published. |
| campo | `InvoiceIssuerId` | Listed among the new FOCUS 1.2 columns on the migration page, but absent from the official column table of this surface. With no row documenting it, it is not generated. |
| campo | `CSV/gzip header, delimiter and encoding` | The delivery documentation defines only file names and the format options; it makes no statement about header, delimiter or encoding. |
| tema | `Currency/unit of all monetary columns (BilledCost, EffectiveCost, ListCost, ContractedCost, ContractedUnitPrice, ListUnitPrice, PricingCurrencyContractedUnitPrice, PricingCurrencyEffectiveCost, PricingCurrencyListUnitPrice, x_Discounts)` | The official column page documents type and nullability but never declares unit or currency. BillingCurrency exists as a column, but AWS does not state that BilledCost is denominated in it. The FinOps FOCUS 1.2 specification (focus.finops.org, incl. the official PDF) returned HTTP 403 on every attempt, so units could not be verified from an official source. |
| tema | `Units of CommitmentDiscountQuantity, CommitmentDiscountUnit, ConsumedQuantity, ConsumedUnit, PricingQuantity, PricingUnit` | AWS documents these as provider-specified or 'denominated in Commitment Discount Units' and does not enumerate values. |
| tema | `Literal timestamp format and timezone of BillingPeriodStart, BillingPeriodEnd, ChargePeriodStart, ChargePeriodEnd` | The type is documented as timestamp_milliseconds, but the page states neither the serialized format nor UTC for these columns (unlike CUR 2.0, which explicitly states UTC and YYYY-MM-DDTHH:mm:ssZ). |
| tema | `Allowed values of ChargeCategory, ChargeClass, ChargeFrequency, CommitmentDiscountCategory, CommitmentDiscountStatus, CommitmentDiscountType, PricingCategory, ServiceCategory, ServiceSubcategory, BillingAccountType, SubAccountType, CapacityReservationStatus, ResourceType` | AWS documents the semantics but does not enumerate valid values on this page; the FOCUS 1.2 specification that enumerates them was unreachable (HTTP 403). |
| tema | `Complete list of tag prefixes used in the Tags column` | The migration page mentions the aws:tags:CostCategory/ prefix, but no complete prefix list is published for this table. |
| tema | `Literal value of the S3 partition for a FOCUS 1.2 export` | The delivery documentation describes data/<partition>/ generically and details the partition explicitly only for CUR 2.0 (BILLING_PERIOD=YYYY-MM). The FOCUS 1.2 partition is never stated. |
| tema | `Manifest.json literal key names for columns, data files and covered period` | AWS documents the manifest contents in prose only; no JSON schema, key list or example is published. |
| tema | `JSON type of the FocusVersion manifest value and internal structure of additionalOutputFiles` | Name and value ('1.2') are documented; the JSON type is not stated, and the internal structure of additionalOutputFiles is not published. |
| tema | `InvoiceIssuerId` | Listed among the new FOCUS 1.2 columns on the migration page, but absent from the official column table of this surface. With no row documenting it, it is not generated. |
| tema | `CSV/gzip header, delimiter and encoding` | The delivery documentation defines only file names and the format options; it makes no statement about header, delimiter or encoding. |

## `aws/ec2-describe-instances` — 16 item(ns)

Spec: [`specs/aws/ec2-describe-instances.schema.json`](../specs/aws/ec2-describe-instances.schema.json)

| tipo | item | motivo declarado |
|---|---|---|
| campo | `JSON property names/schema for DescribeInstances` | only XML is documented; no JSON example or JSON property list is published |
| campo | `exact XML container element spelling rule` | API Reference member names (BlockDeviceMapping.N) differ from Sample Response elements (<blockDeviceMapping>) and from the AWS Config CI example (blockDeviceMappings); no conversion rule is published |
| campo | `az-id pattern` | the availability-zone-id filter exists but the identifier pattern is not published. RECONFIRMADO em 2026-10-15: a pagina do objeto Placement (API_Placement.html) descreve Placement.AvailabilityZone como apenas 'The Availability Zone of the instance', Type: String, Required: No -- sem pattern, sem exemplo e sem format, enquanto o MESMO objeto publica Valid Values para Tenancy (default \| dedicated \| host). A ausencia de pattern e do tipo de dado, e nao de leitura: quando a AWS publica um dominio fechado, publica. |
| campo | `platformDetails valid values` | the Instance object page does not publish the list; the list on DescribeInstances belongs to a filter, not to a return value |
| campo | `AWS::EC2::Instance configuration-object schema` | AWS Config does not publish per-resource-type property schemas; it redirects to CloudFormation |
| campo | `field-by-field mapping between Instance and the AWS Config configuration object` | AWS Config only states the configuration is what the Describe or List API returns |
| campo | `export mechanism to a durable artifact` | not documented (negative evidence); DescribeInstances is a read API |
| campo | `publicDnsName / publicIpAddress as Instance return members` | the Instance page uses dnsName and ipAddress; the AWS Config CI example uses publicDnsName and publicIpAddress; neither document publishes the latter as Instance members |
| tema | `JSON property names/schema for DescribeInstances` | only XML is documented; no JSON example or JSON property list is published |
| tema | `exact XML container element spelling rule` | API Reference member names (BlockDeviceMapping.N) differ from Sample Response elements (<blockDeviceMapping>) and from the AWS Config CI example (blockDeviceMappings); no conversion rule is published |
| tema | `az-id pattern` | the availability-zone-id filter exists but the identifier pattern is not published. RECONFIRMADO em 2026-10-15: a pagina do objeto Placement (API_Placement.html) descreve Placement.AvailabilityZone como apenas 'The Availability Zone of the instance', Type: String, Required: No -- sem pattern, sem exemplo e sem format, enquanto o MESMO objeto publica Valid Values para Tenancy (default \| dedicated \| host). A ausencia de pattern e do tipo de dado, e nao de leitura: quando a AWS publica um dominio fechado, publica. |
| tema | `platformDetails valid values` | the Instance object page does not publish the list; the list on DescribeInstances belongs to a filter, not to a return value |
| tema | `AWS::EC2::Instance configuration-object schema` | AWS Config does not publish per-resource-type property schemas; it redirects to CloudFormation |
| tema | `field-by-field mapping between Instance and the AWS Config configuration object` | AWS Config only states the configuration is what the Describe or List API returns |
| tema | `export mechanism to a durable artifact` | not documented (negative evidence); DescribeInstances is a read API |
| tema | `publicDnsName / publicIpAddress as Instance return members` | the Instance page uses dnsName and ipAddress; the AWS Config CI example uses publicDnsName and publicIpAddress; neither document publishes the latter as Instance members |

## `aws/config-describe-compliance-by-config-rule` — 4 item(ns)

Spec: [`specs/aws/config-describe-compliance-by-config-rule.schema.json`](../specs/aws/config-describe-compliance-by-config-rule.schema.json)

| tipo | item | motivo declarado |
|---|---|---|
| tema | `o valor maximo que CappedCount trunca e que CapExceeded compara` | A pagina ComplianceContributorCount publica 'up to a maximum number' e descreve CapExceeded como 'Indicates whether the maximum count is reached', mas NAO publica o numero. Sem o teto, a comparacao nao e reproduzivel a partir da documentacao, e o booleano fica null. Verificado em https://docs.aws.amazon.com/config/latest/APIReference/API_ComplianceContributorCount.html |
| tema | `exemplo de resposta JSON de DescribeComplianceByConfigRule` | A pagina da acao publica a secao Response Syntax, mas nenhum exemplo de payload preenchido. A estrutura dos artefatos deste renderer vem da Response Syntax e da secao Request Parameters, nao de um exemplo oficial. |
| tema | `regra gerenciada 'ConfigRuleName' x regra gerenciada avaliada` | ConfigRuleName e o NOME de uma regra gerenciada do AWS Config. A lista oficial (https://docs.aws.amazon.com/config/latest/developerguide/managed-rules-by-aws-config.html) foi lida em 2026-10-16 e contem 838 nomes; cada nome emitido por este renderer foi conferido nela antes de ser escrito. O PARAMETRO requiredKeyTags que varias regras etiquetadas aceitam NAO e publicado na API Reference desta acao, e portanto nao faz parte desta superficie: ele pertence ao parametro da regra, nao da resposta. |
| tema | `o escopo (conta, regiao) de um item de ComplianceByConfigRules` | A API Reference descreve a resposta como uma lista de regras, sem declarar no envelope qual conta e qual regiao produziram o item. O agrupamento por (conta, regiao) que o renderer faz e uma projecao do escopo do proprio estate -- o AWS Config grava por conta E por regiao -- e nao um campo que a documentacao publique. |

**Divergência registrada, não resolvida por conta própria.** A linha de Valid Values do campo
`ComplianceType` lista `COMPLIANT | NON_COMPLIANT | NOT_APPLICABLE | INSUFFICIENT_DATA`, e a
**mesma página** da forma `Compliance` afirma que *"AWS Config does not support the NOT_APPLICABLE
value for the Compliance data type"*. Os dois lados ficam aqui; a escolha do renderer é never emitir
`NOT_APPLICABLE`, e é uma constante no código (`NOT_APPLICABLE_EMITTED = False`). A assimetria que
torna a confusão fácil: o filtro de requisição `ComplianceTypes` **aceita** `NOT_APPLICABLE`, só a
resposta é que não.

## `aws/security-hub-asff` — 18 item(ns)

Spec: [`specs/aws/security-hub-asff.schema.json`](../specs/aws/security-hub-asff.schema.json)

| tipo | item | motivo declarado |
|---|---|---|
| campo | `S3 object key template for native export` | RESCRITO em 2026-10-15 com a pagina do tipo S3ExportDestination: o ObjectPrefix e 'an optional key prefix that Security Hub PREPENDS to the Amazon S3 object keys of the export output', com maximo de 512 caracteres e nao obrigatorio. O que a AWS publica e o PREFIXO; o template da chave completa continua fora: nenhuma das paginas do export (securityhub-v2-findings-export, StartExportJobV2, GetExportJobV2, S3ExportDestination) publica sufixo, pasta por conta/regiao/data ou nome de job. |
| campo | `export file name and structure` | not documented -- e agora a evidencia e estrutural, nao uma busca que falhou. GetExportJobV2 devolve, no total, DataType, Destination, EndedAt, ExportJobId, FailureCode, FailureMessage, Name, OutputConfiguration, Scopes, StartedAt e Status: nenhum membro descreve arquivos escritos. O unico detalhe de estrutura e o uso de multipart upload em exports grandes, dito nas politicas de exemplo do StartExportJobV2 (s3:AbortMultipartUpload, UploadPart), o que explica as partes mas nao nomeia objeto nenhum. |
| campo | `export compression and encoding` | not documented. SEPARADO do que a AWS publica: a CRIPTOGRAFIA esta documentada e e obrigatoria -- S3ExportDestination.KmsKeyArn exige chave simetrica ENCRYPT_DECRYPT, single-Region (mrk- rejeitado), ARN completo e na mesma conta e Regiao do job, para 'server-side encryption' dos objetos. O que a fonte nao publica e compressao (gzip) e encoding de caracteres. |
| campo | `CSV header line, quoting rules and line terminator` | RENOMEADO em 2026-10-15: o que era 'CSV header and exact delimiter' ja tem metade da resposta. FindingsOutput publica que CSV 'produces comma-separated rows' (o delimitador) e que, para CSV, SelectedFields e OBRIGATORIO e 'the field paths that you specify become the columns of the output, IN THE ORDER that you provide them', de 1 a 50 campos. Ou seja: o conjunto e a ordem das colunas estao publicados. O que continua sem fonte e a LINHA DE CABECALHO em si, a regra de aspas/escape do CSV e o terminador de linha. |
| campo | `export manifest` | RECONFIRMADO por evidencia estrutural em 2026-10-15: GetExportJobV2 -- a operacao que descreve o job e o que ele escreveu -- nao tem nenhum membro de manifest, e a pagina do console tambem nao menciona um. StartExportJobV2 devolve apenas ExportJobId. Nao e que a busca falhou: a pagina que descreveria o manifest existe, foi lida, e ele nao esta la. |
| campo | `exhaustive bodies of the remaining ASFF subobjects` | CORRIGIDO em 2026-10-15: o limite era a LEITURA, nao a fonte. A pagina do contorno do JSON e o outline COMPLETO (a propria AWS escreve 'This page provides a complete outline of the JSON for a finding in ASFF') e ela tem versao .md; o que truncava era o .html na ferramenta de leitura. Cada subobjeto tambem tem pagina propria (asff-resourcedetails-<recurso>.html, asff-recorddetails-*.html). Fechar este item e trabalho de enumeracao, nao evidencia nova: a fonte ja publica tudo. |
| campo | `ASFF to CSV column mapping: the path behind each default column` | A REGRA do mapeamento esta publicada e era o que faltava: FindingsOutput diz que, para CSV, SelectedFields e obrigatorio, que as colunas SAO os field paths OCSF informados e que sao aplicadas NA ORDEM em que foram fornecidas (1 a 50 campos). A pagina do console publica ainda os NOMES das nove colunas padrao -- Finding title, Severity, Resource ID, Created at, Status, Finding account, Finding region, Product vendor name, Finding type -- e diz que cada opcao mostra o path OCSF de origem, com um exemplo explicito: 'Finding account' vem de cloud.account.uid. O que a AWS nao publica e o path das OUTRAS oito: sem os pares nome->path, um artefato teria de escolher o path de 'Severity', 'Status' e 'Created at' por analogia -- e sao exatamente as colunas cujo path o contrato do OCSF já determina (severity, status, finding_info.created_time_dt), o que torna a tentacao maior, nao menor. Por isso a coluna do CSV continua fora do artefato. |
| campo | `OCSF JSON schema emitted by the export` | OCSF format referenced and field paths listed, but no full OCSF schema or version published |
| campo | `EventBridge custom action S3 layout` | mechanism described without layout, file name, or output schema |
| tema | `S3 object key template for native export` | RESCRITO em 2026-10-15 com a pagina do tipo S3ExportDestination: o ObjectPrefix e 'an optional key prefix that Security Hub PREPENDS to the Amazon S3 object keys of the export output', com maximo de 512 caracteres e nao obrigatorio. O que a AWS publica e o PREFIXO; o template da chave completa continua fora: nenhuma das paginas do export (securityhub-v2-findings-export, StartExportJobV2, GetExportJobV2, S3ExportDestination) publica sufixo, pasta por conta/regiao/data ou nome de job. |
| tema | `export file name and structure` | not documented -- e agora a evidencia e estrutural, nao uma busca que falhou. GetExportJobV2 devolve, no total, DataType, Destination, EndedAt, ExportJobId, FailureCode, FailureMessage, Name, OutputConfiguration, Scopes, StartedAt e Status: nenhum membro descreve arquivos escritos. O unico detalhe de estrutura e o uso de multipart upload em exports grandes, dito nas politicas de exemplo do StartExportJobV2 (s3:AbortMultipartUpload, UploadPart), o que explica as partes mas nao nomeia objeto nenhum. |
| tema | `export compression and encoding` | not documented. SEPARADO do que a AWS publica: a CRIPTOGRAFIA esta documentada e e obrigatoria -- S3ExportDestination.KmsKeyArn exige chave simetrica ENCRYPT_DECRYPT, single-Region (mrk- rejeitado), ARN completo e na mesma conta e Regiao do job, para 'server-side encryption' dos objetos. O que a fonte nao publica e compressao (gzip) e encoding de caracteres. |
| tema | `CSV header line, quoting rules and line terminator` | RENOMEADO em 2026-10-15: o que era 'CSV header and exact delimiter' ja tem metade da resposta. FindingsOutput publica que CSV 'produces comma-separated rows' (o delimitador) e que, para CSV, SelectedFields e OBRIGATORIO e 'the field paths that you specify become the columns of the output, IN THE ORDER that you provide them', de 1 a 50 campos. Ou seja: o conjunto e a ordem das colunas estao publicados. O que continua sem fonte e a LINHA DE CABECALHO em si, a regra de aspas/escape do CSV e o terminador de linha. |
| tema | `export manifest` | RECONFIRMADO por evidencia estrutural em 2026-10-15: GetExportJobV2 -- a operacao que descreve o job e o que ele escreveu -- nao tem nenhum membro de manifest, e a pagina do console tambem nao menciona um. StartExportJobV2 devolve apenas ExportJobId. Nao e que a busca falhou: a pagina que descreveria o manifest existe, foi lida, e ele nao esta la. |
| tema | `exhaustive bodies of the remaining ASFF subobjects` | CORRIGIDO em 2026-10-15: o limite era a LEITURA, nao a fonte. A pagina do contorno do JSON e o outline COMPLETO (a propria AWS escreve 'This page provides a complete outline of the JSON for a finding in ASFF') e ela tem versao .md; o que truncava era o .html na ferramenta de leitura. Cada subobjeto tambem tem pagina propria (asff-resourcedetails-<recurso>.html, asff-recorddetails-*.html). Fechar este item e trabalho de enumeracao, nao evidencia nova: a fonte ja publica tudo. |
| tema | `ASFF to CSV column mapping: the path behind each default column` | A REGRA do mapeamento esta publicada e era o que faltava: FindingsOutput diz que, para CSV, SelectedFields e obrigatorio, que as colunas SAO os field paths OCSF informados e que sao aplicadas NA ORDEM em que foram fornecidas (1 a 50 campos). A pagina do console publica ainda os NOMES das nove colunas padrao -- Finding title, Severity, Resource ID, Created at, Status, Finding account, Finding region, Product vendor name, Finding type -- e diz que cada opcao mostra o path OCSF de origem, com um exemplo explicito: 'Finding account' vem de cloud.account.uid. O que a AWS nao publica e o path das OUTRAS oito: sem os pares nome->path, um artefato teria de escolher o path de 'Severity', 'Status' e 'Created at' por analogia -- e sao exatamente as colunas cujo path o contrato do OCSF já determina (severity, status, finding_info.created_time_dt), o que torna a tentacao maior, nao menor. Por isso a coluna do CSV continua fora do artefato. |
| tema | `OCSF JSON schema emitted by the export` | OCSF format referenced and field paths listed, but no full OCSF schema or version published |
| tema | `EventBridge custom action S3 layout` | mechanism described without layout, file name, or output schema |

## `aws/security-hub-ocsf-export` — 4 item(ns)

Spec: [`specs/aws/security-hub-ocsf-export.schema.json`](../specs/aws/security-hub-ocsf-export.schema.json)

| tipo | item | motivo declarado |
|---|---|---|
| campo | `metadata.version` | O OCSF declara 'version' como obrigatorio no objeto metadata, e a AWS nao afirma qual revisao do schema o export usa. A ultima revisao LANCADA do OCSF foi verificada (1.9.0, via a API de releases do repositorio, prerelease=false), mas escolher uma versao para o artefato seria afirmar um fato que a fonte da AWS nao publica. O campo fica fora do artefato ate a AWS (ou um exemplo de saida) dizer qual e. RECONSULTADO em 2026-10-15: a pagina da operacao de export (securityhub-v2-findings-export.html) diz apenas que o formato OCSF_JSON contem o achado inteiro, sem versao; e a lista completa de caminhos validos de FindingsOutput.SelectedFields (119 caminhos, conferida no .md) NAO publica 'metadata.version' -- ela publica 'metadata.uid' e 'metadata.product.*', e nao a revisao. A unica frase da AWS sobre uma versao ('Security Hub currently supports findings in OCSF schema version 1.6', securityhub-ocsf.html) declara a revisao de schema que o Security Hub SUPORTA para os achados em geral, e nao o valor do campo no export; transformar essa frase no valor seria inferencia, nao leitura. |
| campo | `class_uid / category_uid / type_uid` | O OCSF identifica a classe e a categoria por identificadores numericos no envelope do evento. A lista de campos da AWS NAO publica nenhum deles, e nenhuma pagina consultada afirma qual classe ('compliance_finding' seria o candidato natural) o export usa. Emiti-los seria escolher uma classe por analogia -- exatamente o que esta investigacao recusou fazer. RECONSULTADO em 2026-10-15, com evidencia a favor da recusa: a AWS publica 'class_name' como caminho valido do proprio export (na lista de FindingsOutput.SelectedFields e na tabela de campos OCSF da pagina securityhub-v2-automation-rules), mas nao publica o 'class_uid' correspondente, nem a categoria, nem o tipo, nem a lista de valores de 'class_name'. O que a fonte afirma e o NOME do campo, nunca o valor -- entao o envelope continua declarado como lacuna. |
| campo | `partition layout of the exported objects` | A AWS publica apenas ObjectPrefix (ate 512 caracteres) como prefixo prepended as chaves dos objetos; nao ha template de particionamento, numero de partes nem convencao de nome de arquivo publicada para o export de findings. O path_template fica null em vez de inventado. |
| campo | `compliance.assessments / compliance.control / compliance.standards` | Os caminhos sao publicados pela AWS e o estado NAO carrega framework, controle nem avaliacao: o mapeamento ASFF do mesmo achado tambem emite 'Compliance: None', com a justificativa registrada de que o modelo nao tem esses dados. Omitir e a resposta correta; emitir vazio afirmaria que o achado foi avaliado sem framework. |

## `aws/vpc-flow-logs-s3` — 16 item(ns)

Spec: [`specs/aws/vpc-flow-logs-s3.schema.json`](../specs/aws/vpc-flow-logs-s3.schema.json)

| tipo | item | motivo declarado |
|---|---|---|
| campo | `header row in text format` | not documented in Flow log records / Flow log files |
| campo | `file character encoding` | not documented |
| campo | `Parquet/Arrow schema and column names` | only per-field Parquet data types are documented (see parquet_type on each column) |
| campo | `hash suffix algorithm in file name` | file name format documented, hash origin not |
| campo | `TagFieldSpecifications object schema` | referenced but not published in the consulted pages |
| campo | `textual representation of start/end` | documented as Unix seconds; exact textual formatting in the file not published |
| campo | `az-id identifier pattern` | meaning documented, pattern not published |
| campo | `version 6 fields` | official table jumps from v5 to v7; no v6 exists in the table |
| tema | `header row in text format` | not documented in Flow log records / Flow log files |
| tema | `file character encoding` | not documented |
| tema | `Parquet/Arrow schema and column names` | only per-field Parquet data types are documented (see parquet_type on each column) |
| tema | `hash suffix algorithm in file name` | file name format documented, hash origin not |
| tema | `TagFieldSpecifications object schema` | referenced but not published in the consulted pages |
| tema | `textual representation of start/end` | documented as Unix seconds; exact textual formatting in the file not published |
| tema | `az-id identifier pattern` | meaning documented, pattern not published |
| tema | `version 6 fields` | official table jumps from v5 to v7; no v6 exists in the table |

## `azure/arm-network-security-group-rules` — 6 item(ns)

Spec: [`specs/azure/arm-network-security-group-rules.schema.json`](../specs/azure/arm-network-security-group-rules.schema.json)

| tipo | item | motivo declarado |
|---|---|---|
| campo | `properties.flushConnection` | A pagina publica o tipo (bool) e a descricao do efeito, mas nao exemplifica o payload nem fixa valor: o campo entra no formato e nao no contrato de valor. Nenhuma regra deste estado o define, entao ele nao e emitido. |
| campo | `ApplicationSecurityGroup.properties` | A pagina publica a tabela ApplicationSecurityGroupPropertiesFormat VAZIA -- o provedor nao declara o conteudo. E o caso name-only: o nome entra no contrato, o valor sai vazio em vez de inventado. |
| campo | `ApplicationSecurityGroup.tags` | A pagina referencia ResourceTags e publica a tabela VAZIA (o tipo e 'Dictionary of tag names and values' na prosa do pai). Sem nomes de tag publicados, nao ha o que emitir. |
| campo | `apiVersion` | A pagina lista 60 versoes na navegacao e a secao 'Resource format' usa 2025-09-01 no exemplo, mas nenhuma pagina consultada afirma qual versao e a corrente para o payload. A versao nao e um campo do CORPO da resposta, entao ela nao e emitida. |
| campo | `properties.securityRules[].id` | A pagina publica o TIPO ('id \| Resource ID. \| string') e nao afirma a FORMA do id de uma regra -- se e o caminho aninhado .../networkSecurityGroups/{nsg}/securityRules/{rule} ou outra coisa. Com o tipo publicado e a forma nao, a unica saida fiel e NAO emitir o campo: compor o caminho seria inventar a forma. Por isso o nome esta aqui e nao em 'sets' (uma coluna nao pode pertencer ao formato e ser nao comprovada ao mesmo tempo). |
| campo | `limite de regras por NSG / numero maximo de regras` | Nao publicado nas paginas consultadas. Este estado emite duas regras e o teto nao e afirmado. |

## `azure/arm-resource-representation` — 9 item(ns)

Spec: [`specs/azure/arm-resource-representation.schema.json`](../specs/azure/arm-resource-representation.schema.json)

| tipo | item | motivo declarado |
|---|---|---|
| campo | `GET response Definitions table (per-field type and required flags for nested types)` | The official Virtual Machines - Get page did not expose its type Definitions section in any retrieval attempt; the returned content stops at the Examples. The anchors #virtualmachine, #instanceviewtypes and #clouderror are referenced inside the page, so the definitions exist on the page but their content was never read. No field in this file is attributed to that section. |
| campo | `sku (top-level)` | Does not appear in any official GET/List All example response for Microsoft.Compute/virtualMachines, nor in the ARM template top-level property list for this type. Not listed, to avoid inventing a property. |
| campo | `properties.instanceView.*` | $expand=InstanceView is documented as a parameter, but no consulted official example returns the instanceView object, so none of its subfields (vmAgent, disks, extensions, statuses, computerName, osName, osVersion, ...) are listed. |
| campo | `properties.storageProfile.osDisk.managedDisk.additionalDiskProperties.managedDiskProperties.*` | The template reference lists the equivalent structure for osDisk but the child properties were only transcribed in full for dataDisks; not duplicated by inference. |
| campo | `required flag for every field other than properties.storageProfile.dataDisks[].createOption` | Only DataDisk.createOption is explicitly marked '(required)' in the consulted template reference: 'CreateOption' carries '(required)' in the Value column, and no other property does. Because the REST Definitions table could not be read, the remaining required flags are unknown rather than false. |
| campo | `read-only (readOnly) status of most properties` | Only properties.vmId, properties.storageProfile.imageReference.exactVersion, properties.timeCreated and identity.principalId/identity.tenantId have documentary evidence of being read-only (present in responses but absent from the deployment property list, or described as platform-assigned). For the rest the REST reference was not readable. |
| campo | `structure of resources[].properties.settings and .protectedSettings` | Examples show them as arbitrary objects; no schema is published. |
| campo | `CloudError / ErrorResponse field list` | The error response type is referenced but no field table for it was read. |
| campo | `delivery.path_template / delivery.compression` | Not applicable: this is an ARM REST JSON response, not a push export. No blob path or compression exists in the documentation. Empty by design. |

## `azure/azure-resource-graph-virtual-machines` — 9 item(ns)

Spec: [`specs/azure/azure-resource-graph-virtual-machines.schema.json`](../specs/azure/azure-resource-graph-virtual-machines.schema.json)

| tipo | item | motivo declarado |
|---|---|---|
| campo | `formal Resources table column schema (names + types)` | Microsoft publishes no page listing the resources table's columns with types (unlike Azure Monitor tables, which have explicit column tables). All names were read from official JSON response examples; the types are not asserted by any consulted page. |
| campo | `Resources column data types (kind, managedBy, plan, sku, tags, tenantId, ...)` | They appear in examples as ""/{} which does not fix a type (string vs object vs nullability). |
| campo | `required flags for any Resources column` | No consulted official page states that any resources column is always present. |
| campo | `complete properties.* list for microsoft.compute/virtualmachines in the resources table` | Only the paths listed in the .md are proven (official example JSON plus the official REST query example). No complete list is published, and the documented PII scrub means the set may differ from ARM. |
| campo | `properties.extended.* for VMs beyond instanceView.powerState.code` | Only that path is exemplified officially; extended properties are documented as a preview feature. |
| campo | `official enumeration of SecurityResources resource types` | The supported-tables-resources document retrieved does not present a SecurityResources section with an enumerated type list. |
| campo | `SecurityResources field data types` | No consulted official page publishes a type table; number/array/dynamic values in this file are the spec author's classification based on how the official queries use them (tolong, todouble, mv-expand, todynamic). |
| campo | `delivery.path_template / delivery.format / delivery.compression` | Resource Graph is a query service, not a push export; no storage path, file format or compression is documented. The only documented file export is the manual Resource Graph Explorer CSV (55000 record cap) whose column header is not published. Empty by design. |
| campo | `resourcechanges / ResourceChanges table schema` | The 'Get resource changes' page shows an example payload and defers to the REST reference /rest/api/resources/changes for the full field reference. That reference was not read in this investigation, so no field is asserted here. |

## `azure/cost-management-export-cost-details` — 7 item(ns)

Spec: [`specs/azure/cost-management-export-cost-details.schema.json`](../specs/azure/cost-management-export-cost-details.schema.json)

| tipo | item | motivo declarado |
|---|---|---|
| campo | `data types for all classic cost details columns` | No official Microsoft page publishes a DataType per classic cost details column. The FOCUS dataset documentation does publish types, but the classic dataset does not. Not generated. |
| campo | `nullability / required flag for all classic cost details columns` | Not published by Microsoft for the classic dataset. |
| campo | `units and currency semantics per column` | Prose descriptions indicate currency for some columns, but no per-column unit declaration exists. |
| campo | `timestamp format for Date, UsageDateTime, billingPeriodStartDate, servicePeriodStartDate etc.` | The pages give semantic descriptions ("The usage or purchase date of the charge") and, for UsageDateTime only, the pattern yyyy-mm-dd. No authoritative ISO 8601/UTC declaration is published for the classic dataset. |
| campo | `allowed values for ChargeType, Frequency, PricingModel, PublisherType, Term` | Only illustrative value examples appear in prose; no complete enumeration table is published. |
| campo | `exact casing of benefitId / benefitName / PayGPrice / payGPrice / PricingModel / pricingModel` | Casing is inconsistent between the schema pages and, within a single page, between dataset versions. See the divergences section of the .md spec. |
| campo | `whether actual and amortized differ in column set` | Microsoft documents actual and amortized as separate datasets but the schema index publishes ONE cost and usage details schema per agreement, not one per metric. No document states that actual and amortized share an identical column list. |

## `azure/cost-management-export-focus12` — 2 item(ns)

Spec: [`specs/azure/cost-management-export-focus12.schema.json`](../specs/azure/cost-management-export-focus12.schema.json)

| tipo | item | motivo declarado |
|---|---|---|
| campo | `x_PricingCurrency` | Listed as column 79 in the Cost Management FOCUS 1.2-preview schema page, but absent from the official FinOps toolkit FocusCost_1.2-preview metadata JSON (106 columns) that Microsoft links from the same documentation. Casing/type and presence are therefore contradictory between two official Microsoft sources. |
| campo | `column order` | The schema page enumerates columns 1-105 while the official metadata JSON enumerates 106 columns; the two orders disagree from index 73 onward (x_InvoiceIssuerId, x_SkuTerm, x_SkuPlanName/x_SkuPartNumber). No single authoritative order can be cited. |

## `azure/cost-management-export-manifest` — 6 item(ns)

Spec: [`specs/azure/cost-management-export-manifest.schema.json`](../specs/azure/cost-management-export-manifest.schema.json)

| tipo | item | motivo declarado |
|---|---|---|
| campo | `exportConfig.beginDate` | Not present in the only official _manifest.json example. Microsoft publishes no manifest field table or JSON Schema, so its existence and format cannot be proven. Not generated. |
| campo | `exportConfig.endDate` | Not present in the only official _manifest.json example. Same reasoning as exportConfig.beginDate. Not generated. |
| campo | `aggregate semantics of top-level byteCount/dataRowCount when blobCount > 1` | The official example has blobCount=1 so top-level and partition values coincide. Documentation never states whether top-level values are sums over partitions. |
| campo | `complete value sets for exportConfig.type / exportConfig.timeFrame / exportConfig.granularity` | No retrievable enumeration table was found on the consulted official pages; only values appearing in official examples are proven. |
| campo | `manifest schema stability across manifestVersion values` | No published manifest schema version list or changelog, so future field sets cannot be proven. |
| campo | `manifest for non-partitioned exports` | Documentation ties the manifest to partitioned data and states partitioning can no longer be disabled; no example or path is documented for a non-partitioned export. |

## `azure/defender-for-cloud-continuous-export` — 14 item(ns)

Spec: [`specs/azure/defender-for-cloud-continuous-export.schema.json`](../specs/azure/defender-for-cloud-continuous-export.schema.json)

| tipo | item | motivo declarado |
|---|---|---|
| campo | `Severity` | Present in the Defender for Cloud alert data model (alerts-schemas) but absent from the documented SecurityAlert table column list, which uses AlertSeverity. Conflicting official sources; type not asserted. |
| campo | `SourceSystem` | Listed as 'unused' in the alert data model with no type; absent from the SecurityAlert table column list. |
| campo | `TenantId` | Listed in the alert data model with no type; absent from the SecurityAlert table column list. |
| campo | `DiscoveredTimeUTC (SecurityAlert)` | Referenced by the alert data model as identical to TimeGenerated but absent from the documented SecurityAlert column list. |
| campo | `SecureScores / SecureScoresSnapshot record schema` | EventSource value is documented, but no official page consulted publishes the exported record schema for secure score. |
| campo | `SecureScoreControls / SecureScoreControlsSnapshot record schema` | EventSource value is documented, but no official page consulted publishes the exported record schema for secure score controls. |
| campo | `RegulatoryComplianceAssessment / RegulatoryComplianceAssessmentSnapshot record schema` | EventSource value is documented, but no official page consulted publishes the exported record schema. |
| campo | `SubAssessments / SubAssessmentsSnapshot record schema and destination table` | EventSource value is documented, but no official page consulted publishes the record schema nor names a destination table for sub-assessments. |
| campo | `AttackPaths continuous-export payload schema` | The published attack path schema belongs to the Azure Resource Graph API (securityresources), not to the continuous export event payload. No official page consulted documents the export payload. |
| campo | `Event Hub message envelope / headers / partition key` | Official docs only state the format is JSON. No envelope, headers or partitioning scheme is published. |
| campo | `aka.ms/ASCAutomationSchemas content` | Referenced by the official continuous export page as the schema reference, but the link redirects cross-origin to github.com and could not be retrieved; the corresponding GitHub folder returned HTTP 404. Not read, therefore not used as a source. |
| campo | `CSV report column header (Download CSV report)` | The manual CSV export is documented as a feature, but no official page consulted publishes its column set. |
| campo | `delivery.path_template` | Azure Storage is not a documented destination of continuous export, so no blob path template exists in the official documentation. Field left empty by design. |
| campo | `delivery.compression` | No compression is documented for continuous export delivery. Field left empty by design. |

## `azure/nsg-flow-logs-v2` — 7 item(ns)

Spec: [`specs/azure/nsg-flow-logs-v2.schema.json`](../specs/azure/nsg-flow-logs-v2.schema.json)

| tipo | item | motivo declarado |
|---|---|---|
| campo | `delivery.compression` | No official page consulted states a compression algorithm (or its absence) for PT1H.json. Field intentionally left empty. |
| campo | `delivery.encoding` | No official page consulted states the character encoding. |
| campo | `flowTuples counter values for flow state B` | Docs state 'Statistics aren't provided' for B and the official examples show empty fields; no numeric value or literal placeholder is documented. |
| campo | `records[].time fractional-second digit count` | All official examples show exactly 7 fractional digits, but the documentation does not assert that the count is fixed. |
| campo | `manifest / metadata blob` | No manifest or metadata file is documented for NSG flow logs v2. |
| campo | `records[].resourceid (all-lowercase spelling)` | Appears in the property list of the official page while every official JSON example uses 'resourceId'. Both spellings exist in the same official document; no inference taken about which is authoritative. |
| campo | `maximum PT1H.json size / maximum record count` | Not documented. |

## `azure/vnet-flow-logs` — 10 item(ns)

Spec: [`specs/azure/vnet-flow-logs.schema.json`](../specs/azure/vnet-flow-logs.schema.json)

| tipo | item | motivo declarado |
|---|---|---|
| campo | `blob compression` | No official page consulted documents compression for PT1H.json. |
| campo | `blob encoding` | No official page consulted documents the character encoding. |
| campo | `NTANetAnalytics column data types` | The official schema table presents 'Format' as descriptive prose (e.g. 'Date and time in UTC', 'Subscription ID') and leaves it empty for the flow-count fields. The integer/datetime types used here are the spec author's classification, not official assertions. |
| campo | `NTAIpDetails column data types` | Same as above: the official 'Format' cell is descriptive prose. |
| campo | `literal value of a platform rule name in flowGroups[].rule` | The docs describe 'platform rules' conceptually but never publish the literal string emitted in that case. |
| campo | `allowed values of records[].flowLogVersion` | The only value visible in the official documentation is 4 (sample record). No enumeration of valid values is published. |
| campo | `manifest / metadata file` | No manifest or metadata artifact is documented for virtual network flow logs. |
| campo | `blob_id field` | Referenced in the traffic analytics prose ('use the blob_id field, which can be referenced from storage') but absent from the published schema table, so no row/type/source could be established. |
| campo | `exact derivation of the NETWORKWATCHER_{Region}_{ResourceName}-{ResourceGroupName}-FLOWLOGS partition segment` | The path template shows the segment but the documentation does not state how it is derived when the flow log name is customised. |
| campo | `SrcIP_s / DestIP_s / VMIP_s / PublicIPs_s suffixed variants` | Mentioned in the Notes prose ('Some field names are appended with _s or _d') but not present as rows in the published schema table (which uses unsuffixed names). No schema row could be established. |

## `gcp/asset-search-all-iam-policies` — 2 item(ns)

Spec: [`specs/gcp/asset-search-all-iam-policies.schema.json`](../specs/gcp/asset-search-all-iam-policies.schema.json)

| tipo | item | motivo declarado |
|---|---|---|
| campo | `results[].resourceUuid` | O artefato do gcp_rest_fixtures emite esta chave de juncao entre planos, e o contrato oficial de IamPolicySearchResult NAO a declara (zero ocorrencias no documento de descoberta completo). O caminho entra aqui porque o nucleo compara o caminho completo, e um nome nao pode pertencer ao formato e ser nao comprovado ao mesmo tempo. |
| campo | `results[].resourceUuid` | Chave de juncao entre planos que o renderer antigo emitia e que NENHUM dos seis contratos oficiais declara (zero ocorrencias nos documentos completos). Registrada aqui porque a afirmacao vale para esta superficie tambem: o auditor tem de acusar o campo se ele aparecer. Ver docs/CONTRATO-APIS-GCP.md para o risco por transporte. |

## `gcp/asset-search-all-resources` — 3 item(ns)

Spec: [`specs/gcp/asset-search-all-resources.schema.json`](../specs/gcp/asset-search-all-resources.schema.json)

| tipo | item | motivo declarado |
|---|---|---|
| campo | `results[].resourceUuid` | O artefato do gcp_rest_fixtures emite 'resourceUuid' (chave de juncao entre planos sinteticos) dentro de cada resultado, e o proto oficial de ResourceSearchResult NAO declara esse campo. Em proto3 campo desconhecido nao esta no contrato, e o proprio codigo registra, para a familia alertPolicies, que um campo de topo nao declarado faz o cliente RECUSAR a resposta inteira ('ParseDict fails with has no field named resourceUuid'). O CAMINHO entra aqui, e nao em 'sets', porque um nome nao pode pertencer ao formato e ser nao comprovado ao mesmo tempo -- e o nucleo de fidelidade compara o caminho completo, nao o nome curto. Onde ele MORA quando e emitido: dentro do item, entao aqui; onde ele mora no corpo bruto: ao lado de 'name'. Enquanto o renderer o emitir, o auditor acusa [unverified_emitted] -- e essa acusacao e a decisao pendente deste item, nao um ruido a silenciar. |
| campo | `results[].name value shape` | O TIPO e a FORMA do campo sao publicados, e o VALOR nao segue o formato por tipo. O proto diz que 'name' e o full resource name (exemplo: //compute.googleapis.com/projects/my_project_123/zones/zone1/instances/instance1) e a tabela oficial de nomes de asset (https://docs.cloud.google.com/asset-inventory/docs/asset-names) publica o formato POR TIPO: Instance -> //compute.googleapis.com/projects/PROJECT_ID/zones/ZONE/instances/INSTANCE; Instance (Cloud SQL) -> //cloudsql.googleapis.com/projects/PROJECT_ID/instances/INSTANCE; Cluster -> //container.googleapis.com/projects/PROJECT_ID/locations/LOCATION/clusters/CLUSTER; Bucket -> //storage.googleapis.com/BUCKET. O artefato compoe '//<resource_type>.googleapis.com/projects/<project>/<resource_type>/<resource_name>', que nao traz zonas/locations e usa o nome interno do tipo como segmento de caminho. O campo existe e e emitido; o valor esta sob auditoria. |
| campo | `results[].assetType value shape` | O TIPO do campo e publicado (string) e o proto exemplifica 'compute.googleapis.com/Disk'; a tabela oficial de nomes publica 'compute.googleapis.com/Instance'. O artefato compoe '<resource_type>.googleapis.com' (ex.: 'compute_instance.googleapis.com'), sem sufixo de tipo de asset -- o nome interno do tipo do estado nao e o tipo de asset que a CAI indexa. A lista oficial completa e uma pagina propria (supported-asset-types) que nao foi consultada tipo a tipo deste estado. |

## `gcp/billing-budgets` — 2 item(ns)

Spec: [`specs/gcp/billing-budgets.schema.json`](../specs/gcp/billing-budgets.schema.json)

| tipo | item | motivo declarado |
|---|---|---|
| campo | `budgets[].amount.specifiedAmount.units value shape` | O campo e o tipo sao publicados (int64 como string); o VALOR e fixo ('1000') e nao vem de nenhum orcamento do estado -- um valor de exemplo declarado, nao medido. |
| campo | `budgets[].resourceUuid` | Chave de juncao entre planos que o renderer antigo emitia e que NENHUM dos seis contratos oficiais declara (zero ocorrencias nos documentos completos). Registrada aqui porque a afirmacao vale para esta superficie tambem: o auditor tem de acusar o campo se ele aparecer. Ver docs/CONTRATO-APIS-GCP.md para o risco por transporte. |

## `gcp/billing-export-detailed` — 18 item(ns)

Spec: [`specs/gcp/billing-export-detailed.schema.json`](../specs/gcp/billing-export-detailed.schema.json)

| tipo | item | motivo declarado |
|---|---|---|
| campo | `partitioning [gcp_billing_export_resource_v1_<BILLING_ACCOUNT_ID>]` | No official documentation page consulted states the partitioning column or granularity of the detailed usage cost table. The detailed schema page does not contain the word partition; only query examples use _PARTITIONTIME. |
| campo | `clustering [gcp_billing_export_resource_v1_<BILLING_ACCOUNT_ID>]` | No official documentation page consulted states clustering columns for this table. |
| campo | `file_format [gcp_billing_export_resource_v1_<BILLING_ACCOUNT_ID>]` | Delivery is a BigQuery table; no file format, compression, encoding, delimiter or header is documented for this surface. |
| campo | `manifest_metadata_schema [gcp_billing_export_resource_v1_<BILLING_ACCOUNT_ID>]` | No manifest or metadata document is emitted to the customer in the documented mechanism. |
| campo | `credits.amount sign convention [credits.amount]` | The field reference documents only the amount of the credit applied to the usage. The negative sign appears only in an example query result and is implied by the net-cost formula SUM(cost) + SUM(credits.amount). |
| campo | `net cost column [table columns]` | No net-cost column exists in the documented schema; the docs compute it with a query expression. |
| campo | `closed enumeration of usage.unit / usage.pricing_unit / price.unit values [usage.unit, usage.pricing_unit, price.unit]` | Docs give examples and refer to the Cloud Billing Catalog API; no closed value list is published. |
| campo | `exact timestamp string format [usage_start_time, usage_end_time, export_time]` | Type is declared as Timestamp and the docs link to the BigQuery timestamp data types page; no exact literal pattern is asserted. Official query examples render values as 2025-09-16 00:00:00.000000 UTC. |
| campo | `universal population of resource.name / resource.global_name [resource.name, resource.global_name]` | The docs list which services expose resource granularity and note exceptions (for example Snapshot_disk_time metrics do not provide resource.name, and StreamingInsertBytes has no resource identifier), but never assert universal population. |
| tema | `partitioning [gcp_billing_export_resource_v1_<BILLING_ACCOUNT_ID>]` | No official documentation page consulted states the partitioning column or granularity of the detailed usage cost table. The detailed schema page does not contain the word partition; only query examples use _PARTITIONTIME. |
| tema | `clustering [gcp_billing_export_resource_v1_<BILLING_ACCOUNT_ID>]` | No official documentation page consulted states clustering columns for this table. |
| tema | `file_format [gcp_billing_export_resource_v1_<BILLING_ACCOUNT_ID>]` | Delivery is a BigQuery table; no file format, compression, encoding, delimiter or header is documented for this surface. |
| tema | `manifest_metadata_schema [gcp_billing_export_resource_v1_<BILLING_ACCOUNT_ID>]` | No manifest or metadata document is emitted to the customer in the documented mechanism. |
| tema | `credits.amount sign convention [credits.amount]` | The field reference documents only the amount of the credit applied to the usage. The negative sign appears only in an example query result and is implied by the net-cost formula SUM(cost) + SUM(credits.amount). |
| tema | `net cost column [table columns]` | No net-cost column exists in the documented schema; the docs compute it with a query expression. |
| tema | `closed enumeration of usage.unit / usage.pricing_unit / price.unit values [usage.unit, usage.pricing_unit, price.unit]` | Docs give examples and refer to the Cloud Billing Catalog API; no closed value list is published. |
| tema | `exact timestamp string format [usage_start_time, usage_end_time, export_time]` | Type is declared as Timestamp and the docs link to the BigQuery timestamp data types page; no exact literal pattern is asserted. Official query examples render values as 2025-09-16 00:00:00.000000 UTC. |
| tema | `universal population of resource.name / resource.global_name [resource.name, resource.global_name]` | The docs list which services expose resource granularity and note exceptions (for example Snapshot_disk_time metrics do not provide resource.name, and StreamingInsertBytes has no resource identifier), but never assert universal population. |

## `gcp/billing-export-pricing` — 20 item(ns)

Spec: [`specs/gcp/billing-export-pricing.schema.json`](../specs/gcp/billing-export-pricing.schema.json)

| tipo | item | motivo declarado |
|---|---|---|
| campo | `clustering [cloud_pricing_export]` | No official page consulted declares clustering columns for this table. |
| campo | `partition granularity as an explicit statement [cloud_pricing_export._PARTITIONTIME]` | The docs describe _PARTITIONTIME as the date the data belongs to and always filter with DATE(...), but never write an explicit 'partitioned by day' statement. |
| campo | `file_format [cloud_pricing_export]` | Delivery is a BigQuery table; no file format, compression, encoding, delimiter or header is documented. |
| campo | `manifest_metadata_schema [cloud_pricing_export]` | No manifest or metadata document is emitted to the customer in the documented mechanism. |
| campo | `exhaustive subfields of list_price / billing_account_price [list_price, billing_account_price]` | The docs introduce these structs with 'including: aggregation_info, tiered_rates' (plus price_info for billing_account_price) without enumerating every subfield. |
| campo | `subfields of consumption_model_prices.list_price and .billing_account_price [consumption_model_prices.list_price, consumption_model_prices.billing_account_price]` | The docs defer to the list_price and billing_account_price descriptions rather than enumerating subfields in this nested context. |
| campo | `real type of tiered_rates [tiered_rates]` | Documentation declares 'Array of Strings' while its subfields are numeric and the official example UNNESTs it as a struct array. Internal contradiction; recorded as documented. |
| campo | `temporal type of currency_conversion_rate [currency_conversion_rate]` | Documented as String here but as Float in the usage cost tables. Recorded as documented in each surface, not normalized. |
| campo | `closed enumeration of pricing_unit / pricing_unit_description [pricing_unit, pricing_unit_description]` | Only examples are given (GiBy.mo / gibibyte month); no closed value list is published. |
| campo | `exact timestamp string format [export_time, pricing_as_of_time]` | Type is declared as Timestamp and the docs link to the BigQuery timestamp data types page; no exact literal pattern is asserted for these columns. |
| tema | `clustering [cloud_pricing_export]` | No official page consulted declares clustering columns for this table. |
| tema | `partition granularity as an explicit statement [cloud_pricing_export._PARTITIONTIME]` | The docs describe _PARTITIONTIME as the date the data belongs to and always filter with DATE(...), but never write an explicit 'partitioned by day' statement. |
| tema | `file_format [cloud_pricing_export]` | Delivery is a BigQuery table; no file format, compression, encoding, delimiter or header is documented. |
| tema | `manifest_metadata_schema [cloud_pricing_export]` | No manifest or metadata document is emitted to the customer in the documented mechanism. |
| tema | `exhaustive subfields of list_price / billing_account_price [list_price, billing_account_price]` | The docs introduce these structs with 'including: aggregation_info, tiered_rates' (plus price_info for billing_account_price) without enumerating every subfield. |
| tema | `subfields of consumption_model_prices.list_price and .billing_account_price [consumption_model_prices.list_price, consumption_model_prices.billing_account_price]` | The docs defer to the list_price and billing_account_price descriptions rather than enumerating subfields in this nested context. |
| tema | `real type of tiered_rates [tiered_rates]` | Documentation declares 'Array of Strings' while its subfields are numeric and the official example UNNESTs it as a struct array. Internal contradiction; recorded as documented. |
| tema | `temporal type of currency_conversion_rate [currency_conversion_rate]` | Documented as String here but as Float in the usage cost tables. Recorded as documented in each surface, not normalized. |
| tema | `closed enumeration of pricing_unit / pricing_unit_description [pricing_unit, pricing_unit_description]` | Only examples are given (GiBy.mo / gibibyte month); no closed value list is published. |
| tema | `exact timestamp string format [export_time, pricing_as_of_time]` | Type is declared as Timestamp and the docs link to the BigQuery timestamp data types page; no exact literal pattern is asserted for these columns. |

## `gcp/billing-export-standard` — 16 item(ns)

Spec: [`specs/gcp/billing-export-standard.schema.json`](../specs/gcp/billing-export-standard.schema.json)

| tipo | item | motivo declarado |
|---|---|---|
| campo | `partitioning [gcp_billing_export_v1_<BILLING_ACCOUNT_ID>]` | No official documentation page consulted states the partitioning column or granularity of the standard usage cost table. Searched: standard-usage, export-data-bigquery-tables, export-data-bigquery-setup, export-data-bigquery, bq-examples (no mention of partitioning for the standard table). |
| campo | `clustering [gcp_billing_export_v1_<BILLING_ACCOUNT_ID>]` | No official documentation page consulted states clustering columns for this table. |
| campo | `file_format [gcp_billing_export_v1_<BILLING_ACCOUNT_ID>]` | Delivery is a BigQuery table; no file format, compression, encoding, delimiter or header is documented for this surface. |
| campo | `manifest_metadata_schema [gcp_billing_export_v1_<BILLING_ACCOUNT_ID>]` | No manifest or metadata document is emitted to the customer in the documented mechanism. |
| campo | `credits.amount sign convention [credits.amount]` | The field reference documents only 'The amount of the credit applied to the usage.' The sign is shown (negative) only in an example query result and implied by the net-cost formula SUM(cost) + SUM(credits.amount); no textual statement in the schema documents it as a contract. |
| campo | `net cost column [table columns]` | No net-cost column exists in the documented schema; the docs compute it with a query expression. |
| campo | `closed enumeration of usage.unit / usage.pricing_unit / price.unit values [usage.unit, usage.pricing_unit, price.unit]` | Docs give examples (byte-seconds) and refer to the Cloud Billing Catalog API; no closed value list is published. |
| campo | `exact timestamp string format [usage_start_time, usage_end_time, export_time]` | Type is declared as Timestamp and the docs link to the BigQuery timestamp data types page; no exact literal pattern (e.g. YYYY-MM-DDTHH:MM:SSZ) is asserted for these columns. Official query examples render values as '2025-09-16 00:00:00.000000 UTC'. |
| tema | `partitioning [gcp_billing_export_v1_<BILLING_ACCOUNT_ID>]` | No official documentation page consulted states the partitioning column or granularity of the standard usage cost table. Searched: standard-usage, export-data-bigquery-tables, export-data-bigquery-setup, export-data-bigquery, bq-examples (no mention of partitioning for the standard table). |
| tema | `clustering [gcp_billing_export_v1_<BILLING_ACCOUNT_ID>]` | No official documentation page consulted states clustering columns for this table. |
| tema | `file_format [gcp_billing_export_v1_<BILLING_ACCOUNT_ID>]` | Delivery is a BigQuery table; no file format, compression, encoding, delimiter or header is documented for this surface. |
| tema | `manifest_metadata_schema [gcp_billing_export_v1_<BILLING_ACCOUNT_ID>]` | No manifest or metadata document is emitted to the customer in the documented mechanism. |
| tema | `credits.amount sign convention [credits.amount]` | The field reference documents only 'The amount of the credit applied to the usage.' The sign is shown (negative) only in an example query result and implied by the net-cost formula SUM(cost) + SUM(credits.amount); no textual statement in the schema documents it as a contract. |
| tema | `net cost column [table columns]` | No net-cost column exists in the documented schema; the docs compute it with a query expression. |
| tema | `closed enumeration of usage.unit / usage.pricing_unit / price.unit values [usage.unit, usage.pricing_unit, price.unit]` | Docs give examples (byte-seconds) and refer to the Cloud Billing Catalog API; no closed value list is published. |
| tema | `exact timestamp string format [usage_start_time, usage_end_time, export_time]` | Type is declared as Timestamp and the docs link to the BigQuery timestamp data types page; no exact literal pattern (e.g. YYYY-MM-DDTHH:MM:SSZ) is asserted for these columns. Official query examples render values as '2025-09-16 00:00:00.000000 UTC'. |

## `gcp/catalog-services` — 3 item(ns)

Spec: [`specs/gcp/catalog-services.schema.json`](../specs/gcp/catalog-services.schema.json)

| tipo | item | motivo declarado |
|---|---|---|
| campo | `services[].serviceId value shape` | O tipo e o formato do campo sao publicados (a doc exemplifica '6F81-5844-456A'), e o valor e derivado do nome do servico do estado. O campo esta correto; o conteudo do id nao segue o exemplo publicado. |
| campo | `services[].name value shape` | Idem: 'services/{id}' e o formato publicado, e o id embutido e derivado do estado. |
| campo | `services[].resourceUuid` | Chave de juncao entre planos que o renderer antigo emitia e que NENHUM dos seis contratos oficiais declara (zero ocorrencias nos documentos completos). Registrada aqui porque a afirmacao vale para esta superficie tambem: o auditor tem de acusar o campo se ele aparecer. Ver docs/CONTRATO-APIS-GCP.md para o risco por transporte. |

## `gcp/catalog-skus` — 2 item(ns)

Spec: [`specs/gcp/catalog-skus.schema.json`](../specs/gcp/catalog-skus.schema.json)

| tipo | item | motivo declarado |
|---|---|---|
| campo | `skus[].skuId value shape` | O campo e o formato sao publicados (o exemplo e 'D041-B8A1-6E0B'); o valor e o sku_id do estado, que o gerador cunha internamente. |
| campo | `skus[].resourceUuid` | Chave de juncao entre planos que o renderer antigo emitia e que NENHUM dos seis contratos oficiais declara (zero ocorrencias nos documentos completos). Registrada aqui porque a afirmacao vale para esta superficie tambem: o auditor tem de acusar o campo se ele aparecer. Ver docs/CONTRATO-APIS-GCP.md para o risco por transporte. |

## `gcp/cloud-asset-inventory-compute-instance` — 9 item(ns)

Spec: [`specs/gcp/cloud-asset-inventory-compute-instance.schema.json`](../specs/gcp/cloud-asset-inventory-compute-instance.schema.json)

| tipo | item | motivo declarado |
|---|---|---|
| campo | `concrete shape of resource.data for compute.googleapis.com/Instance` | No Cloud Asset Inventory page publishes the schema of resource.data for this or any asset type. The Resource.data field is documented only as 'object (Struct format)': 'The content of the resource, in which some sensitive fields are removed and may not be present.' The mapping to the Compute Engine Instances REST representation is NOT asserted anywhere in the CAI documentation. |
| campo | `per-asset-type schema produced by separateTablesPerAssetType=true for compute.googleapis.com/Instance` | The page states the schema maps nested Resource.data fields to RECORD columns (up to 15 nested levels) but publishes no resulting schema; the referenced examples live in the Cloud console. |
| campo | `field-name casing inside resource.data (camelCase vs snake_case)` | Not asserted in the Cloud Asset Inventory documentation. |
| campo | `compression and encoding of Cloud Storage NDJSON objects` | Only 'newline-delimited JSON' is documented; compression/encoding are not stated. |
| campo | `export manifest` | No manifest is documented. Only the long-running Operation object with path projects/PROJECT_NUMBER/operations/ExportAssets/CONTENT_TYPE/OPERATION_ID. |
| campo | `ACCESS_POLICY (VPCSC) schema columns` | RECLASSIFICADO em 2026-10-15: nao era leitura pendente, era ESCOPO. A pagina de exporting-to-bigquery publica mesmo um 'VPCSC policy schema', mas ele descreve o contentType ACCESS_POLICY (Virtual Private Cloud Security Command Center), e o escopo desta superficie e a tabela de compute.googleapis.com/Instance. Transcrever as colunas dele aqui colocaria colunas de OUTRO content type na tabela de uma instancia de computacao. A lacuna e definitiva nesta superficie; virar coluna exigiria uma superficie nova para o contentType ACCESS_POLICY. |
| campo | `OS_INVENTORY schema columns` | RECLASSIFICADO em 2026-10-15: nao era leitura pendente, era ESCOPO. O 'OS inventory schema' publicado pela pagina pertence ao contentType OS_INVENTORY, e o escopo desta superficie e a tabela de compute.googleapis.com/Instance. O inventario de sistema operacional e um produto diferente do inventario de recursos de nuvem: traze o mesmo dado (o recurso) por outra porta. Nao gerar aqui. |
| campo | `RELATIONSHIP schema columns` | RECLASSIFICADO em 2026-10-15: nao era leitura pendente, era ESCOPO. O 'Relationship schema' publicado pertence ao contentType RELATIONSHIP (os vinculos entre recursos, expostos pelo Servicer Relationship API), e o escopo desta superficie e a tabela de compute.googleapis.com/Instance. Um relacionamento e uma entidade com o proprio ciclo de vida e o proprio conjunto de colunas; mistura-lo na tabela do recurso colocaria duas entidades numa so. |
| campo | `relatedAssets status nuance` | Documented as DEPRECATED: 'The server will never generate responses with this field.' Present in the Asset message but must not be generated. |

## `gcp/compute-instances-rest` — 3 item(ns)

Spec: [`specs/gcp/compute-instances-rest.schema.json`](../specs/gcp/compute-instances-rest.schema.json)

| tipo | item | motivo declarado |
|---|---|---|
| campo | `enum constants (all top-level enums except the ones listed in the .md)` | The instances.get page prints the type 'enum' but does not enumerate the constants in the field table. |
| campo | `per-field Required. marking` | The page marks no field as Required.; only 'Output only.' / 'Input only.' annotations are documented. |
| campo | `all nested fields not transcribed in the .md (disks[].initializeParams.*, networkInterfaces[].accessConfigs.*, scheduling.*, resourceStatus.upcomingMaintenance.*, resourceStatus.physicalHostTopology.*)` | RECLASSIFICADO em 2026-10-15: deixa de ser 'falta transcrever' e passa a ser TRABALHO DE MODELO. A fonte publica os filhos (disks[].initializeParams.*, networkInterfaces[].accessConfigs[], e afins) e eles podem ser transcritos hoje. O que impede e o ESTADO: o renderer emite 'disks[]' e 'guestAccelerators[]' como listas VAZIAS ([]) -- sem o initializeParams, sem o accessConfigs -- porque o modelo nao carrega esses valores. Como no caso do SCC, declarar as colunas sem emiti-las faria o teste golden acusar, e emiti-las exige modelar os parametros de disco e de rede de cada instancia. E uma decisao sobre o que o simulador representa, nao uma leitura faltando. |

## `gcp/monitoring-alert-policies` — 3 item(ns)

Spec: [`specs/gcp/monitoring-alert-policies.schema.json`](../specs/gcp/monitoring-alert-policies.schema.json)

| tipo | item | motivo declarado |
|---|---|---|
| campo | `alertPolicies[].userLabels.resource_uuid` | Chave de juncao entre planos que o artefato antigo punha no mapa userLabels (schema-valida, porque o mapa aceita chaves de usuario, e nao uma chave canonica). O artefato novo nao emite juncao sintetica nenhuma. |
| campo | `alertPolicies[].conditions[].conditionAbsent.duration value` | O campo e o formato sao publicados; o valor '600s' e a janela de lookback do proprio consumidor, citada do codigo dele e nao de uma pagina da Google. Registrado como nao comprovado. |
| campo | `alertPolicies[].resourceUuid` | Chave de juncao entre planos que o renderer antigo emitia e que NENHUM dos seis contratos oficiais declara (zero ocorrencias nos documentos completos). Registrada aqui porque a afirmacao vale para esta superficie tambem: o auditor tem de acusar o campo se ele aparecer. Ver docs/CONTRATO-APIS-GCP.md para o risco por transporte. |

## `gcp/monitoring-metric-descriptors` — 1 item(ns)

Spec: [`specs/gcp/monitoring-metric-descriptors.schema.json`](../specs/gcp/monitoring-metric-descriptors.schema.json)

| tipo | item | motivo declarado |
|---|---|---|
| campo | `metricDescriptors[].resourceUuid` | Chave de juncao entre planos que o renderer antigo emitia e que NENHUM dos seis contratos oficiais declara (zero ocorrencias nos documentos completos). Registrada aqui porque a afirmacao vale para esta superficie tambem: o auditor tem de acusar o campo se ele aparecer. Ver docs/CONTRATO-APIS-GCP.md para o risco por transporte. |

## `gcp/monitoring-time-series` — 6 item(ns)

Spec: [`specs/gcp/monitoring-time-series.schema.json`](../specs/gcp/monitoring-time-series.schema.json)

| tipo | item | motivo declarado |
|---|---|---|
| campo | `timeSeries[].resource.labels.resourcePath` | Chave de juncao emitida pelo artefato antigo. O mapa 'labels' aceita a chave, mas o contrato diz que os labels sao os DECLARADOS no descritor do tipo monitorado, e 'resourcePath' nao consta de gce_instance nem de cloudsql_database. |
| campo | `timeSeries[].resource.labels.resourceUuid` | Idem: chave de juncao, nao declarada entre os labels do tipo. |
| campo | `labels condicionais ao tipo monitorado (instance_id, zone, database_id, region)` | O catalogo publica os labels POR TIPO: gce_instance tem project_id/instance_id/zone e cloudsql_database tem project_id/database_id/region. Eles sao emitidos, e a CONDICIONALIDADE e expressa por conjuntos nomeados (gce_instance_labels, cloudsql_database_labels) em vez de prosa: nenhum registro carrega os cinco, e um conjunto por tipo e o que permite conferir cada um sem exigir a uniao numa linha so. |
| campo | `timeSeries[].metric.type value shape` | O namespace publicado e usado (compute.googleapis.com / cloudsql.googleapis.com) e o ultimo segmento e o nome da metrica do estado. O nome curto nao foi verificavel nas fontes consultadas -- declarado nao comprovado em vez de afirmado inexistente. |
| campo | `timeSeries[].resourceUuid` | Chave de juncao entre planos que o renderer antigo emitia e que NENHUM dos seis contratos oficiais declara (zero ocorrencias nos documentos completos). Registrada aqui porque a afirmacao vale para esta superficie tambem: o auditor tem de acusar o campo se ele aparecer. Ver docs/CONTRATO-APIS-GCP.md para o risco por transporte. |
| tema | `labels condicionais ao tipo monitorado (instance_id, zone, database_id, region)` | O catalogo publica os labels POR TIPO: gce_instance tem project_id/instance_id/zone e cloudsql_database tem project_id/database_id/region. Eles sao emitidos, e a CONDICIONALIDADE e expressa por conjuntos nomeados (gce_instance_labels, cloudsql_database_labels) em vez de prosa: nenhum registro carrega os cinco, e um conjunto por tipo e o que permite conferir cada um sem exigir a uniao numa linha so. |

## `gcp/recommender-insights` — 3 item(ns)

Spec: [`specs/gcp/recommender-insights.schema.json`](../specs/gcp/recommender-insights.schema.json)

| tipo | item | motivo declarado |
|---|---|---|
| campo | `insights[].resourceUuid` | Chave de juncao entre planos emitida pelo artefato antigo; o contrato de Insight NAO a declara. |
| campo | `insights[].name value shape` | Idem ao da recomendacao: o valor usa o projeto alvo com 'locations/global', e a localizacao real varia. |
| campo | `insights[].resourceUuid` | Chave de juncao entre planos que o renderer antigo emitia e que NENHUM dos seis contratos oficiais declara (zero ocorrencias nos documentos completos). Registrada aqui porque a afirmacao vale para esta superficie tambem: o auditor tem de acusar o campo se ele aparecer. Ver docs/CONTRATO-APIS-GCP.md para o risco por transporte. |

## `gcp/recommender-recommendations` — 3 item(ns)

Spec: [`specs/gcp/recommender-recommendations.schema.json`](../specs/gcp/recommender-recommendations.schema.json)

| tipo | item | motivo declarado |
|---|---|---|
| campo | `recommendations[].resourceUuid` | Chave de juncao entre planos emitida pelo artefato antigo; o contrato de Recommendation NAO a declara. |
| campo | `recommendations[].name value shape` | A FORMA esta confirmada no contrato de maquina: o discovery v1 do Recommender descreve o campo como 'Recommendation resource name, e.g. projects/[PROJECT_NUMBER]/locations/[LOCATION]/recommenders/[RECOMMENDER_ID]/recommendations/[RECOMMENDATION_ID]' -- exatamente o que o artefato emite. O que a leitura de 2026-10-15 acrescenta e NEGA: o parametro `parent` do metodo list diz que 'LOCATION here refers to GCP Locations' (https://cloud.google.com/about/locations/) e remete o leitor ao catalogo de recommenders, sem afirmar que a localizacao de uma recomendacao seja sempre `global`. `global` E uma localizacao GCP valida -- entao o valor emitido nao e invalido -- mas e uma escolha dentro de um dominio publicado, nao um valor que a fonte imponha. Por isso o campo continua sob auditoria: fechar exigiria a lista de recommenders por localizacao, que e uma segunda fonte. |
| campo | `recommendations[].resourceUuid` | Chave de juncao entre planos que o renderer antigo emitia e que NENHUM dos seis contratos oficiais declara (zero ocorrencias nos documentos completos). Registrada aqui porque a afirmacao vale para esta superficie tambem: o auditor tem de acusar o campo se ele aparecer. Ver docs/CONTRATO-APIS-GCP.md para o risco por transporte. |

## `gcp/scc-findings` — 3 item(ns)

Spec: [`specs/gcp/scc-findings.schema.json`](../specs/gcp/scc-findings.schema.json)

| tipo | item | motivo declarado |
|---|---|---|
| campo | `chaves de 'sourceProperties' (Explanation, Recommendation)` | O contrato afirma que as chaves desse mapa sao geridas pela FONTE, e nao publica a lista das chaves do Security Health Analytics: as duas chaves emitidas nao tem enumeracao oficial encontrada. E por isso um registro de TEMA, e nao de nome de campo -- as chaves ESTAO dentro de um campo que o contrato define (o mapa), e o que falta e a prova de que sejam as canonicas. Registrar o caminho como nome de campo seria dizer que ele nao pertence ao formato, e ele pertence: o mapa o aceita. |
| campo | `listFindingsResults[].resourceUuid` | Chave de juncao entre planos que o renderer antigo emitia e que NENHUM dos seis contratos oficiais declara (zero ocorrencias nos documentos completos). Registrada aqui porque a afirmacao vale para esta superficie tambem: o auditor tem de acusar o campo se ele aparecer. Ver docs/CONTRATO-APIS-GCP.md para o risco por transporte. |
| tema | `chaves de 'sourceProperties' (Explanation, Recommendation)` | O contrato afirma que as chaves desse mapa sao geridas pela FONTE, e nao publica a lista das chaves do Security Health Analytics: as duas chaves emitidas nao tem enumeracao oficial encontrada. E por isso um registro de TEMA, e nao de nome de campo -- as chaves ESTAO dentro de um campo que o contrato define (o mapa), e o que falta e a prova de que sejam as canonicas. Registrar o caminho como nome de campo seria dizer que ele nao pertence ao formato, e ele pertence: o mapa o aceita. |

## `gcp/scc-sources` — 1 item(ns)

Spec: [`specs/gcp/scc-sources.schema.json`](../specs/gcp/scc-sources.schema.json)

| tipo | item | motivo declarado |
|---|---|---|
| campo | `sources[].resourceUuid` | Chave de juncao entre planos que o renderer antigo emitia e que NENHUM dos seis contratos oficiais declara (zero ocorrencias nos documentos completos). Registrada aqui porque a afirmacao vale para esta superficie tambem: o auditor tem de acusar o campo se ele aparecer. Ver docs/CONTRATO-APIS-GCP.md para o risco por transporte. |

## `gcp/security-command-center-findings-bigquery` — 7 item(ns)

Spec: [`specs/gcp/security-command-center-findings-bigquery.schema.json`](../specs/gcp/security-command-center-findings-bigquery.schema.json)

| tipo | item | motivo declarado |
|---|---|---|
| campo | `BigQuery types of the 6 findings-table columns` | Neither the continuous nor the bulk export page declares column types (STRING/RECORD/TIMESTAMP/...). Only names and descriptions are published. |
| campo | `structure of the findings table 'resource' column` | The export page says 'see the API reference for the Resource object', but no reachable SCC REST page for that object was found: reference/rest/v1/Resource, reference/rest/v1/Asset and reference/rest/v1/organizations.assets all returned HTTP 404 on 2026-10-14. |
| campo | `relationship between the 'resource' column and finding.resourceName / SecurityCenterProperties` | No official page obtained asserts this relationship. |
| campo | `inner fields of every Finding sub-object (indicator.*, vulnerability.*, access.*, compliance.*, mitreAttack.*, ...)` | RECLASSIFICADO em 2026-10-15: deixa de ser 'falta transcrever' e passa a ser TRABALHO DE MODELO. Os 67 campos internos existem e foram lidos no discovery v1 do Security Center (finding.vulnerability 35, finding.access 12, finding.indicator 7, finding.mitreAttack 5, finding.exfiltration 5, finding.securityMarks 3) -- a fonte publica, e o campo pode ser transcrito hoje. O que impede e o ESTADO: o renderer emite 'finding.indicator', 'finding.vulnerability' e 'finding.access' como objetos VAZIOS ({}), porque o modelo NativeFinding nao carrega nenhum desses valores. Declarar as 67 colunas sem emiti-las faria o teste golden acusar (ele exige coluna declarada == coluna emitida), e emiti-las exige antes modelar vulnerabilidade, acesso, indicador e MITRE no estado -- que e uma decisao de produto sobre o que o simulador representa, nao uma tarefa de evidencia. |
| campo | `file format, compression, encoding, delimiter, header, bucket path, partitioning, manifest` | Delivery is a BigQuery table; no intermediate file or manifest is documented. |
| campo | `dataset name and location` | The dataset is created by the user; the documentation fixes neither name nor region. |
| campo | `which API version (v1 or v2) feeds the BigQuery findings table` | The export documentation does not state the API version. v2 documents a reduced Finding object, and the export pages do not cite it. |

## `gcp/vpc-flow-logs-bigquery` — 6 item(ns)

Spec: [`specs/gcp/vpc-flow-logs-bigquery.schema.json`](../specs/gcp/vpc-flow-logs-bigquery.schema.json)

| tipo | item | motivo declarado |
|---|---|---|
| campo | `direct VPC Flow Logs -> BigQuery export mechanism` | No official page describes a VPC-Flow-Logs-specific sink or export to BigQuery. The official destination is Cloud Logging; the BigQuery path is a linked dataset that queries data 'without exporting that data to BigQuery'. |
| campo | `BigQuery column names and types of the linked dataset virtual view (_AllLogs)` | https://cloud.google.com/logging/docs/analyze/query-linked-dataset documents the view->virtual-view mapping and the example name _AllLogs but publishes no column list or types. |
| campo | `file format, compression, encoding, delimiter, header` | No intermediate file exists on this path; the linked dataset is a read-only pointer. Nothing documented. |
| campo | `delivery path / partitioning / shards` | Not documented for this path. |
| campo | `manifest` | Not documented for this path. |
| campo | `name of the specific table/view holding VPC flow logs` | Documentation cites _AllLogs only as an example log view name of a bucket; it never states that flow logs land there. |

## `aws/s3-list-buckets` — 3 item(ns)


Spec: [`specs/aws/s3-list-buckets.schema.json`](../specs/aws/s3-list-buckets.schema.json)


| tipo | item | motivo declarado |
|---|---|---|
| tema | `Order of the elements inside ListAllMyBucketsResult` | O Response Syntax mostra <Buckets>, <Owner>, <ContinuationToken>, <Prefix> nesta ordem, mas a resposta e XML e a pagina nao promete ordenacao. O artefacto ordena a lista de buckets por nome, que e determinismo do gerador e nao uma afirmacao sobre a ordem que o servico devolve. |
| tema | `Ordering of Buckets within the array` | Nenhuma das cinco respostas de exemplo da pagina esta em ordem alfabetica e a pagina nao declara ordenacao. A ordenacao por nome aqui e uma escolha de determinismo, declarada no _provenance.json de cada artefacto. |
| tema | `timestamp representation of CreationDate` | A pagina publica o tipo como 'Timestamp' sem fixar a forma textual. O exemplo usa '2019-12-11T23:32:47+00:00'. O estado emite ISO-8601 com offset UTC, que e a forma do exemplo oficial, mas a AWS nao promete que e a unica representacao aceita. |

## `aws/s3-get-bucket-acl` — 3 item(ns)


Spec: [`specs/aws/s3-get-bucket-acl.schema.json`](../specs/aws/s3-get-bucket-acl.schema.json)


| tipo | item | motivo declarado |
|---|---|---|
| tema | `Order of the elements inside AccessControlPolicy` | O Response Syntax mostra <Owner> antes de <AccessControlList> e a resposta e XML, mas a pagina nao promete ordenacao. O artefacto ordena os grants por (Type, URI, ID, Permission), que e determinismo do gerador e nao uma afirmacao sobre a ordem do servico. |
| tema | `JSON property names/schema for GetBucketAcl` | E o XML que a documenta. Nenhum mapeamento JSON oficial e publicado para esta acao, e por isso o artefacto e JSON com os nomes de ELEMENTO do XML -- divergencia de serializacao, nao de contrato. |
| tema | `VersionId request parameter` | A pagina nao publica VersionId entre os parametros desta acao, e o Request Syntax mostra apenas Bucket e x-amz-expected-bucket-owner. O parametro existe em outras acoes de bucket, mas nao nesta, entao nao entra no artefacto. |

## `aws/s3-get-bucket-policy` — 4 item(ns)


Spec: [`specs/aws/s3-get-bucket-policy.schema.json`](../specs/aws/s3-get-bucket-policy.schema.json)


| tipo | item | motivo declarado |
|---|---|---|
| tema | `Condition element of a policy statement` | A linguagem de policy aceita Condition, e a resposta de exemplo da acao NAO mostra nenhum. O estado nao gera condition, entao o membro nao entra no artefacto: um nome que a evidencia desta superficie nao mostra seria contrato inventado. Ele entra no estado se a fonte passar a publicalo. |
| tema | `NotPrincipal, NotAction and NotResource` | Sao variantes negadas aceitas pela linguagem de policy e nao aparecem na resposta de exemplo. O estado nao os gera e eles nao entram no artefacto. |
| tema | `Type qualifier inside Principal` | A resposta de exemplo mostra 'Principal': {'AWS': [...]} -- um objeto com chave de TIPO de principal. O estado achata o conteudo em lista de strings e nao modela a chave (AWS, Service, Federated). Um consumidor que precise do tipo do principal nao o encontra no artefacto, e o motivo esta na coluna. |
| tema | `Return shape when the bucket has no policy` | A acao sinaliza bucket sem policy com o erro NoSuchBucketPolicy (404), mas a lista de Response Elements marca Policy como sem obrigatoriedade e o estado nao modela codigos de erro. O artefacto representa a ausencia como Policy nulo, que e a leitura do tipo publicado, e nao como um envelope de erro. |

## `aws/s3-get-public-access-block` — 4 item(ns)


Spec: [`specs/aws/s3-get-public-access-block.schema.json`](../specs/aws/s3-get-public-access-block.schema.json)


| tipo | item | motivo declarado |
|---|---|---|
| tema | `Boolean representation of the four members` | A resposta de exemplo escreve TRUE e FALSE, que e a grafia booleana de XML. O tipo publicado e 'Boolean' sem fixar representacao textual. O artefacto emite true/false, que e o booleano correspondente em JSON, e a conversao esta declarada nesta spec. |
| tema | `Account-level PublicAccessBlock effect on these results` | A pagina afirma que na avaliacao o S3 usa a combinacao MAIS RESTRITIVA entre o block do bucket e o da conta. O estado nao modela o block de nivel de conta, entao o valor efetivo da combinacao nao esta no artefacto: o que esta sao os quatro fatos do bucket, e o que a pagina diz que esta operacao devolve. |
| tema | `JSON property names/schema for GetPublicAccessBlock` | E o XML que a documenta. O artefacto e JSON com os nomes de elemento do XML -- divergencia de serializacao, nao de contrato. |
| tema | `RegionalAccessBlockConfiguration (Region, RegionPrefix, BlockPublicAcls, BlockPublicPolicy, IgnorePublicAcls, RestrictPublicBuckets)` | ZERO ocorrencias em API_GetPublicAccessBlock.html E em API_PutPublicAccessBlock.html (medido em 2026-10-18). Os nomes vem da forma que os SDKs publicam, e nao de uma pagina da referencia consultada. Declarado como nao comprovado em vez de declarado inexistente: o conjunto esta no artefato, separado da resposta, e com o motivo desta entrada no _provenance de cada resposta. |

## `aws/ec2-describe-security-groups` — 4 item(ns)


Spec: [`specs/aws/ec2-describe-security-groups.schema.json`](../specs/aws/ec2-describe-security-groups.schema.json)


| tipo | item | motivo declarado |
|---|---|---|
| campo | `securityGroupRuleId` | A Sample Response oficial de DescribeSecurityGroups traz <securityGroupRuleId>sgr-abcdefghi01234560</securityGroupRuleId> dentro de <groups>, mas a página de UserIdGroupPair publica sete membros e esse NÃO é um deles. O exemplo mostra um membro que a página de tipo não documenta, então ele fica proibido no artefato: emitir nome que a fonte não documenta é inventar contrato. Se a AWS passar a documentá-lo, ele entra como coluna própria. |
| tema | `JSON property names/schema for DescribeSecurityGroups` | só o XML é documentado; nenhuma lista de propriedades JSON nem exemplo JSON é publicado para esta ação. O mesmo limite registrado em aws/ec2-describe-instances, e pelo mesmo motivo: o Reference do EC2 publica o nome do membro na forma XML/Query e o artefato JSON usa o mapeamento do mesmo contrato. |
| tema | `enumeração fechada dos valores de ipProtocol` | A página de IpPermission exemplifica os nomes 'tcp', 'udp', 'icmp' e 'icmpv6', diz que um NÚMERO de protocolo também é aceito e que '-1' significa todos os protocolos, mas não publica lista fechada. O valor aceito é nome-ou-número-ou-'-1'; um conjunto fechado seria uma afirmação que a documentação não faz. |
| tema | `vínculo VPC <-> security group do estate` | A API publica vpcId em SecurityGroup, mas o modelo canônico não carrega a relação: os recursos 'vpc' e os recursos 'security_group' do estate vivem em regiões diferentes e nenhum par (conta, região) tem os dois. O vpcId escrito aqui vem do SEGMENTO de rede do mesmo (conta, região), que é a VPC do modelo naquele escopo — uma derivação declarada, não um fato lido da AWS. A verificação pendente é a relação VPC<->SG de uma conta real. |

## `aws/iam-get-account-password-policy` — 4 item(ns)


Spec: [`specs/aws/iam-get-account-password-policy.schema.json`](../specs/aws/iam-get-account-password-policy.schema.json)


| tipo | item | motivo declarado |
|---|---|---|
| tema | `Boolean representation of the seven boolean members` | A Sample Response escreve true e false, que e a grafia booleana de JSON, dentro de um envelope XML. O tipo publicado e 'Boolean' sem fixar representacao textual. O artefacto emite true/false, que e o booleano correspondente, e a conversao esta declarada nesta spec. |
| tema | `Whether a member can be absent from the response` | Os dez membros sao Required: No e a pagina nao declara condicao de presenca. A Sample Response traz os dez. O artefacto NAO emite membro ausente: emite o valor, e para MaxPasswordAge -- o unico cuja ausencia a propria pagina descreve -- o estado sem expiracao e publicado como MaxPasswordAge nulo, com ExpirePasswords falso derivado desse nulo. |
| tema | `Which account each response belongs to` | Nem PasswordPolicy nem a Sample Response carregam o id da conta, e o estado nao modela a requisicao que disparou a leitura. A rotulagem por conta e do ARTEFATO e esta declarada no _provenance de cada resposta. |
| tema | `JSON schema for the IAM JSON protocol` | A documentacao consultada EXIBE a resposta em XML. O IAM tambem aceita JSON, mas nenhuma pagina aqui publica o schema JSON, entao a conversao de nome de membro e o que esta no artefacto e a conversao XML->JSON, nao um contrato JSON verificado. |

## `gcp/observability-partial` — 3 item(ns)


Spec: [`specs/gcp/observability-partial.schema.json`](../specs/gcp/observability-partial.schema.json)


| tipo | item | motivo declarado |
|---|---|---|
| tema | `request.name accepts '-' as a wildcard` | O uso do curinga '-' para alcance multi-projeto e documentado na pratica do Googleapis, mas a pagina do metodo consultada descreve o campo como 'The project on which to execute the query, formatted as projects/{PROJECT_ID}' sem declarar o curinga. Declarado aqui como nao comprovado em vez de afirmado; o artefato NAO emite '-', porque '-' e de REQUISICAO e nunca entra no corpo de uma resposta. |
| tema | `Whether a resposta parcial e indistinguivel de uma completa sem o inventario irmao` | ListTimeSeriesResponse nao declara um campo que diga quantos itens o escopo tinha. Um nextPageToken vazio significa 'ultima pagina', nao 'todos os dados'. Por isso missing.json existe: a honestidade do artefato nao pode depender de um campo que o contrato nao publica. |
| tema | `timeSeries[].metric.type value shape` | Mesma declaracao da superficie mae gcp/monitoring-time-series: o namespace publico e usado e o ultimo segmento e o nome da metrica do estado, que nao foi verificavel nas fontes consultadas. |

## `aws/iam-get-credential-report` — 3 item(ns)


Spec: [`specs/aws/iam-get-credential-report.schema.json`](../specs/aws/iam-get-credential-report.schema.json)


| tipo | item | motivo declarado |
|---|---|---|
| tema | `The LITERAL in the 'user' column of the root account row (a VALUE, not the column)` | Nem API_GetCredentialReport.html nem a pagina de colunas do IAM User Guide (credential-reports.html), ambas lidas em 2026-10-18, declaram o valor dessa coluna na linha da conta root. O report traz uma linha para a raiz, e sem ela a regra root-account-mfa-enabled nao teria linha alguma onde ler o MFA da raiz -- por isso o artefacto emite a linha. O LITERAL vai marcado como nao comprovado e o motivo esta no _provenance: um consumidor que compare a coluna 'user' contra essa string precisa saber que ela nao foi conferida contra uma pagina oficial. |
| tema | `CSV quoting rules for a value containing the delimiter` | Nenhuma das duas paginas publica a regra de escape do CSV do report (aspas, escape duplo, delimitador). O artefacto emite um CSV simples com delimitador virgula e NAO contorna valores: todos os valores aqui vem de um vocabulario sem virgula e sem aspas, entao nenhum campo precisa de escape. Um usuario com virgula no nome mudaria a discussao, e o estado nao tem um. |
| tema | `Whether the CSV declares a Content-Type line or a BOM` | A pagina da acao diz ReportFormat = 'text/csv' e que Content e Base64; nao declara BOM nem quebras de linha. O artefacto escreve UTF-8 sem BOM e com \n, e declara isso no _provenance. |

## `gcp/compute-firewalls` — 6 item(ns)


Spec: [`specs/gcp/compute-firewalls.schema.json`]](../specs/gcp/compute-firewalls.schema.json)


| tipo | item | motivo declarado |
|---|---|---|
| tema | `allowed[].IPProtocol = "all"` | A pagina de Firewall diz que IPProtocol 'can either be one of the following well known protocol strings (tcp, udp, icmp, esp, ah, ipip, sctp) or the IP protocol number' -- e 'all' NAO esta nessa lista. Mas 'all' e o valor que a API de fato devolve: a saida oficial de 'gcloud compute firewall-rules list' de um projeto recem-criado traz default-allow-internal com a coluna ALLOW igual a 'all', e o guia de VPC firewall diz que 'If you omit both protocols and ports, the firewall rule is applicable for all traffic on any protocol and any destination port' e oferece 'Allow all' na criacao. O valor e real na resposta e esta nesta superficie justamente por causa disso; a divergencia e entre a prosa do campo e a API, e ela esta registrada aqui para que ninguem leia a prosa como lista fechada. |
| tema | `JSON property names da resposta de firewalls.list` | A GCP publica a forma JSON desta superficie -- e e o que o documento de discovery da Compute v1 e, ele proprio, a fonte de maquina que a pagina de Firewall usa para renderizar a tabela de propriedades. Nao ha divergencia de encoding como na AWS (que publica so XML): aqui os nomes JSON E os de tipo sao os documentados. |
| tema | `rede VPC global vs. uma rede por regiao no modelo` | Na GCP uma rede VPC e GLOBAL e tem sub-redes em varias regioes; o unico membro regional do par e subnetworks. O modelo canonico, ao contrario, da a este estate uma rede por (projeto, regiao) -- segment_id muda com a regiao, como se fosse a VPC da AWS. O valor de Firewall.network escrito aqui e o segment_id real do modelo, entao ele e um FATO do modelo e nao uma derivacao, mas nao e a forma que a GCP produz. A verificacao pendente e a relacao rede-VPC<->projeto de um projeto real, que so se resolve quando o modelo passar a carregar uma rede por projeto. |
| tema | `nomes de regra pre-populados da rede default como contrato` | Os quatro nomes (default-allow-internal, default-allow-ssh, default-allow-rdp, default-allow-icmp), a prioridade 65534 e os pares protocolo:porta vem da tabela de 'Pre-populated rules in the default network' do guia de VPC firewall e da saida de 'gcloud compute firewall-rules list' que a propria Google publica no material de treinamento. Nao ha pagina de tipo que os declare: sao o estado de um projeto recem-criado, nao um contrato de schema. Eles entram como postura DECLARADA, com a fonte citada, e nao como coluna. |
| tema | `as duas regras implicitas de toda rede VPC` | A GCP documenta que toda rede tem uma regra implicita de ingress que nega tudo e uma de egress que libera tudo, ambas em prioridade 65535. Elas NAO sao recursos e firewalls.list nao as devolve, entao nao ha coluna para elas e o artefato nao as carrega. Registrado aqui porque e o ponto em que um consumidor que varre a lista nao consegue ver a regra que protege a rede. |
| tema | `membros do objeto FirewallList.warning` | O discovery declara warning como 'Informational warning message' com tipo object e NAO publica os membros dele. Sai {}: um objeto sem campos publicados nao vira estrutura inventada. |

## `azure/security-assessments-list` — 10 item(ns)


Spec: [`specs/azure/security-assessments-list.schema.json`]](../specs/azure/security-assessments-list.schema.json)


| tipo | item | motivo declarado |
|---|---|---|
| tema | `valor de 'properties.status.cause' (ex.: 'OffByPolicy')` | A pagina publica o TIPO ('string') e a descricao ('Programmatic code for the cause of the assessment status'), mas nao publica dominio fechado. O unico valor observavel e o do exemplo de resposta ('"cause": "OffByPolicy"', no assessment NotApplicable). Um exemplo de payload fixa a FORMA do campo, nao o seu vocabulario: o membro e emitido VAZIO. |
| tema | `membros de 'properties.additionalData'` | A pagina publica o tipo 'object' e o exemplo de resposta mostra um 'linkedWorkspaceId'. Ela nao publica a lista de membros, entao nao ha o que enumerar: o membro sai como objeto VAZIO, sem a chave inventada. |
| tema | `template de 'properties.links.azurePortalUri'` | O tipo e o significado estao publicados ('Link to assessment in Azure Portal'), mas nenhuma pagina consultada publica o formato da URI nem da um exemplo. Montar uma URL de portal por regra seria inventar o transporte. |
| tema | `'properties.metadata.policyDefinitionId' na avaliacao embutida` | A pagina publica o membro e o descreve como 'Azure resource ID of the policy definition that turns this assessment calculation on', mas nao exemplifica o valor e o exemplo de resposta nao traz 'metadata'. Um id de definicao de politica ARM seria um id que nenhuma pagina consultada publica, entao o membro sai vazio. |
| tema | `categorias, ameacas, esforco de implementacao e impacto por avaliacao` | Os DOMINIOS estao publicados ('categories', 'threats', 'implementationEffort', 'userImpact' tem as tabelas de enumeracao), mas a pagina nao afirma a qual valor CADA avaliacao pertence, e o estado canonico nao modela o catalogo de avaliacoes do Defender. Escolher um valor seria inventar a associacao; os membros saem como colecao/string vazia. |
| tema | `'properties.partnersData.partnerName', 'properties.metadata.partnerData.partnerName' e '...productName'` | Os tres membros tem tipo e descricao publicados, mas o estado nao tem parceiro: nenhuma verificacao deste estado e de terceiro. Saem vazios em vez de receberem um nome de empresa inventado. |
| tema | `'properties.partnersData.secret' e 'properties.metadata.partnerData.secret'` | A pagina marca os dois como 'write only' ('Secret to authenticate the partner - write only'). Um membro explicitamente de ESCRITA nao pertence a uma resposta de leitura, entao ele nao entra em 'sets': emiti-lo seria publicar um campo que a propria documentacao diz que nao volta. |
| tema | `variantes OnPremise de 'properties.resourceDetails'` | A pagina publica tres variantes (AzureResourceDetails, OnPremiseResourceDetails, OnPremiseSqlResourceDetails) e o estado so produz a Azure: as duas OnPremise descrevem maquinas sob um agente de Log Analytics, que este repositorio nao modela. A escolha da variante e um FATO do recurso avaliado, e o recurso avaliado aqui e uma VNet na Azure. |
| tema | `pagina de 'nextLink'` | A resposta e uma pagina de uma colecao e a pagina nao publica o tamanho de pagina nem um cursor de exemplo. O envelope e entregue como pagina unica (todos os assessments do escopo cabem nela), com o membro presente e vazio. |
| tema | `escopo por grupo de gerenciamento` | A pagina publica que 'scope' pode ser uma assinatura OU um grupo de gerenciamento. O consumidor do FinOps consulta a assinatura, e o estado canonico nao modela grupo de gerenciamento da Azure; um envelope por grupo seria um recorte que o modelo nao tem. |

## `azure/deployment-stacks-what-if` — 4 item(ns)


Spec: [`specs/azure/deployment-stacks-what-if.schema.json`]](../specs/azure/deployment-stacks-what-if.schema.json)


| tipo | item | motivo declarado |
|---|---|---|
| tema | `properties.changes.deploymentScopeChange and denySettingsChange` | DeploymentStacksWhatIfChange publishes both members, but the simulator's estate models neither a stack scope change nor deny settings. They are not emitted rather than filled with a placeholder. |
| tema | `the full DeploymentStacksWhatIfResult property set (parameters, template, templateLink, validationLevel, diagnostics, retentionInterval, provisioningState, ...)` | The REST reference publishes them as part of the result, but the simulator only models the resource changes this phase needs. Omitting them is intentional; inventing their values would be worse than an honest subset. |
| tema | `resourceConfigurationChanges.delta element type` | The page publishes the delta member and describes DeploymentStacksWhatIfPropertyChange, but does not print an explicit type link for delta. The fields transcribed here are the ones the property-change definition publishes; the container type is not asserted. |
| tema | `the concrete spelling of delta[].path for a tag key` | The property-change definition publishes path as a string and the examples shown are for resource properties, not for a tag key. The simulator emits tags.<key> as a scenario path; the documentation consulted does not print an example for a tag map key, so tags.<key> is not asserted as the published spelling. |

## `gcp/infrastructure-manager-resource-drift` — 4 item(ns)


Spec: [`specs/gcp/infrastructure-manager-resource-drift.schema.json`]](../specs/gcp/infrastructure-manager-resource-drift.schema.json)


| tipo | item | motivo declarado |
|---|---|---|
| campo | `concrete shape of before/after for a given Terraform type` | The REST reference publishes before/after as a Value (arbitrary JSON). It does not publish a per-resource-type schema, so the simulator may emit only values derived from the estate's own model and must not infer a nested shape from a provider example. |
| campo | `semantics of before/after relative to desired state` | The page describes the values as 'before/after the actions' without stating which side is the desired state for a drift preview. The direction must be measured on a real preview before a consumer maps it to expected/actual. |
| tema | `the resourceDrifts[]/nextPageToken/unreachable[] envelope` | The envelope belongs to the list method, not to the ResourceDrift item; it is documented at the list method page and is intentionally outside this item schema. |
| tema | `the grammar of propertyDrifts[].path for a map key` | The REST reference publishes `path` as the path of the property drift, but does not publish the path grammar for maps. The simulator emits `labels.<key>` as a scenario path derived from the estate; that spelling is not asserted by the GCP documentation and must not be read as a published contract. |

## `gcp/container-clusters` — 22 item(ns)


Spec: [`specs/gcp/container-clusters.schema.json`]](../specs/gcp/container-clusters.schema.json)


| tipo | item | motivo declarado |
|---|---|---|
| campo | `currentMasterVersion` | Output only. The current software version of the master endpoint. The estate does not model a Kubernetes version: the cluster's sku_id names the NODE SKU it bills, which is not the master's version. Publishing one would be a version the estate never asserted. |
| campo | `currentNodeVersion` | Output only. The current software version of the node software. The estate bills the cluster under a node SKU and models no Kubernetes release for it. |
| campo | `nodePools` | The node pools associated with this cluster. The estate models one row per cluster and no pool inside it; a pool would be a resource the estate does not carry. |
| campo | `nodeConfig` | The node configuration for this cluster. The estate carries the cluster's billed SKU, not a node configuration, and the two are not the same shape. |
| campo | `network` | The name of the Google Compute Engine network to which the cluster is connected. The estate models no VPC for a cluster, so there is no network name to publish. |
| campo | `subnetwork` | The VPC-native network id the cluster uses. The estate models no subnetwork for a cluster. |
| campo | `status` | Output only. The current status of this cluster. The estate is a billing baseline, not a control-plane state machine: it asserts that the cluster is billed for, not that it is RUNNING. |
| campo | `createTime` | Output only. The time the cluster was created, in RFC3339 text format. The estate asserts no creation time for a resource, and the simulator's clock would be a fabricated one. |
| campo | `selfLink` | Output only. Server-defined URL for the resource. The estate mints a uuid, not a GCP server-defined URL, so any path published here would be a path the provider never defined. |
| campo | `id` | Output only. Unique id for the cluster. The estate's uuid is the estate's own identifier and is not the provider's numeric id. |
| campo | `zone` | Output only, and deprecated in favour of 'location'. The estate records a region and nothing finer, so there is no zone to publish; 'location' carries the region. |
| campo | `clusterIpv4Cidr` | The IPv4 range for the cluster's nodes. The estate models no address plan for a cluster. |
| campo | `masterAuth.clientKey` | Output only. Base64-encoded private key used by clients to authenticate to the cluster endpoint. It is a PRIVATE key: the simulator derives one to sign the CA certificate and never publishes it. Publishing it here would publish a secret the contract does not carry. |
| campo | `masterAuth.clientCertificate` | Output only. Base64-encoded public certificate used by clients to authenticate to the cluster endpoint, issued only if clientCertificateConfig is set. The estate models no client certificate configuration. |
| campo | `masterAuth.username` | The username to use for HTTP basic authentication to the master endpoint. The estate models no basic-authentication account for a cluster, and the page itself marks basic authentication as deprecated. |
| campo | `masterAuth.password` | Deprecated on the page. The estate models no password for a cluster, and a published password would be a credential nobody published. |
| campo | `masterAuth.clientCertificateConfig` | Configuration for client certificate authentication on the cluster. The estate models no client certificate configuration. |
| tema | `the remaining published members of Cluster that the estate does not model (secretManagerConfig, alphaClusterFeatureGates, nodePoolAutoConfig, monitoringService, userManagedKeysConfig, description, nodeIpv4CidrSize, masterAuthorizedNetworksConfig, costManagementConfig, maintenancePolicy, networkPolicy, nodePoolDefaults, legacyAbac, secretSyncConfig, addonsConfig, podAutoscaling, locations, meshCertificates, servicesIpv4Cidr, etag, tpuIpv4CidrBlock, gkeAutoUpgradeConfig, satisfiesPzi, managedMachineLearningDiagnosticsConfig, rbacBindingConfig, compliancePostureConfig, workloadIdentityConfig, enterpriseConfig, scheduleUpgradeConfig, resourceUsageExportConfig, controlPlaneEgress, rollbackSafeUpgrade, releaseChannel, currentEmulatedVersion, controlPlaneEndpointsConfig, initialNodeCount, databaseEncryption, labelFingerprint, instanceGroupUrls, statusMessage, verticalPodAutoscaling, anonymousAuthenticationConfig, fleet, conditions, enableKubernetesAlpha, parentProductConfig, resourceLabels, monitoringConfig, networkConfig, privateClusterConfig, loggingConfig, shieldedNodes, securityPostureConfig, binaryAuthorization, expireTime, identityServiceConfig, enableK8sBetaApis, confidentialNodes, ipAllocationPolicy, notificationConfig, initialClusterVersion, enableTpu, managedOpentelemetryConfig, satisfiesPzs, defaultMaxPodsConstraint, loggingService, currentNodeCount, autopilot, autoscaling, authenticatorGroupsConfig, nodeCreationConfig)` | The API publishes these members and the estate models none of them: a cluster row carries a name, a region, a billed SKU and tags, and nothing else. They are listed by name so that no published member is silently omitted from the accounting, and they stay out of the artifact because publishing them would mean inventing the value the estate does not carry. |
| tema | `the endpoint as an IP address (the published wording of the member)` | The field table publishes the endpoint as 'Output only. The IP address of this cluster's master endpoint', and the estate carries no address for a cluster. The simulator publishes an HTTPS URL derived from the resource's uuid instead -- the form the same paragraph shows the endpoint being used at ('https://username:password@endpoint/'). The divergence is declared, not silent: a consumer that needs an IP must know the simulator does not publish one. |
| tema | `the zonal (projects.zones.clusters.list) and aggregated (projects.aggregated.clusters.list) variants of the same list` | Both exist in the same API version and return the same ListClustersResponse. Only the regional projects.locations.clusters.list is served by the emulator; the other two are a scope limit of this surface, not a claim that they do not exist. |
| tema | `the deprecated query parameters 'projectId' and 'zone'` | The list method publishes both as deprecated and replaced by the 'parent' path parameter. The route takes the parent form only, so a client sending the deprecated spelling is answered by the same parent path instead. |
| tema | `the reachability of the published endpoint` | The endpoint names the cluster's master endpoint and is derived from the resource's uuid; the emulator hosts no Kubernetes API server behind it. A client that dials it is not reaching a cluster control plane. |
