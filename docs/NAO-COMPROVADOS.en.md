# What this project has NOT proven yet

> Language: **English** | [Português](NAO-COMPROVADOS.md)

Registry **derived from the specifications** — the normative source of this repository — by `.artifacts/gerar-registro-nao-comprovados.py`. It exists because the gaps were declared inside each spec, field by field, and there was no single place answering *"what has not been proven yet?"*; several generator docstrings pointed to a `docs/synthetic-clouds/UNVERIFIED.md` that **only exists inside the FinOps repository**.

**Nothing here is new.** Every line is an `unverified` that was already written in the spec, with the reason the author recorded. What this document adds is the **consolidation** and the **count** — and that is why it is generated rather than hand-written: a second list would keep two truths about the same subject.

**A reading correction worth recording:** `spec.unverified` exposes only the **names**. The reasons live in `unverified_fields` (a name that does not belong to the contract) and `unverified_topics` (a topic that exists in the contract and whose proof is missing), and both have to be read: together they give 288 items in **49** surfaces. A registry that read only the list of names would give a third of the problem and no reason at all — which is half the value for whoever closes the gap. The numbers are computed, not written: a fixed total ages in silence as soon as a gap is closed by evidence.

## Numbers (at the revision in which it was generated)

* **288 unproven items** in **49 of 49 surfaces** (that is: **no** surface is without a declared gap).
* By provider: **aws** 88, **azure** 83, **gcp** 117.
* By type: **field** = the name does not belong to the contract; **topic** = the name exists and the proof that the value is canonical is missing.

**How to read each item.** A spec declares two kinds of unproven item, and the difference matters:

* **field** (`name`) — the name **does not belong** to that surface's contract. Emitting it is `invented`/`unverified_emitted`, and the auditor flags it. That is the case of the join key `resourceUuid`, which none of the official contracts declares.
* **topic** (`item`) — the name **does exist** in the contract (inside a map or an object), and what is missing is the **proof** that that value/key is canonical. Registering it as a field would be saying that it does not belong to the format — and it does belong.

The *kind* column below is that distinction, read from the spec JSON (`name` vs `item`).

## `aws/aws-config-snapshot-s3` — 18 item(ns)

Spec: [`specs/aws/aws-config-snapshot-s3.schema.json`](../specs/aws/aws-config-snapshot-s3.schema.json)

| kind | item | declared reason |
|---|---|---|
| field | `configurationItemDeliveryTime in S3 file` | documented as optional and not guaranteed; absent from the official file example |
| field | `recordingFrequency in S3 file` | documented as API-response-only when DAILY recording is enabled |
| field | `supplementaryConfiguration in S3 file` | documented in API schema only; absent from official file example |
| field | `resourceName in S3 file` | documented in API schema only; absent from official file example |
| field | `file character encoding` | not documented |
| field | `formal s3ObjectKey template` | AWS publishes literal examples only, not a placeholder template; templates here are marked derived |
| field | `manifest/index artifact` | no manifest is described in any consulted official page (negative evidence) |
| field | `SNS envelope schema` | standard SNS envelope appears in examples but is not defined by AWS Config documentation |
| field | `Configuration Snapshot Delivery Started notification` | example page could not be retrieved; referenced by navigation only |
| topic | `configurationItemDeliveryTime in S3 file` | documented as optional and not guaranteed; absent from the official file example |
| topic | `recordingFrequency in S3 file` | documented as API-response-only when DAILY recording is enabled |
| topic | `supplementaryConfiguration in S3 file` | documented in API schema only; absent from official file example |
| topic | `resourceName in S3 file` | documented in API schema only; absent from official file example |
| topic | `file character encoding` | not documented |
| topic | `formal s3ObjectKey template` | AWS publishes literal examples only, not a placeholder template; templates here are marked derived |
| topic | `manifest/index artifact` | no manifest is described in any consulted official page (negative evidence) |
| topic | `SNS envelope schema` | standard SNS envelope appears in examples but is not defined by AWS Config documentation |
| topic | `Configuration Snapshot Delivery Started notification` | example page could not be retrieved; referenced by navigation only |

## `aws/bcm-data-exports-cur2` — 22 item(ns)

Spec: [`specs/aws/bcm-data-exports-cur2.schema.json`](../specs/aws/bcm-data-exports-cur2.schema.json)

| kind | item | declared reason |
|---|---|---|
| field | `Manifest.json key names for columns, data files and covered period` | AWS documents the manifest contents in prose only; no JSON schema, key list or example is published. Only the literal key additionalOutputFiles is confirmed. |
| field | `Manifest.json key order, nesting and required/optional status` | Not documented. |
| field | `Structure of the additionalOutputFiles section` | Only the section name is documented; its internal structure is not. |
| field | `JSON type of the FocusVersion manifest value` | Name and values ('1.2' / '1.0') are documented; the JSON type is not explicitly stated. |
| field | `Manifest file name (<export-name>-Manifest.json vs Manifest.json)` | The Metadata section and the Summary section of the same page document different file names. |
| field | `Compression parameter value PARQUET equals Snappy` | PARQUET is a documented valid value of the Compression parameter, but the documentation never states it maps to Snappy. The only documented Parquet/Snappy link is the .snappy.parquet file extension. |
| field | `Currency/unit of monetary CUR 2.0 columns (line_item_*_cost, pricing_public_on_demand_cost, reservation_*, savings_plan_*, discount_*)` | Field documentation describes semantics but never declares the currency unit. The only currency statement in the table is 'All AWS customers are billed in US dollars by default' on line_item_currency_code; the actual export currency is runtime-determined by line_item_currency_code and pricing_currency. |
| field | `Unit of line_item_usage_amount, line_item_normalized_usage_amount and split_line_item_* usage columns` | Unit is service-dependent; the documentation refers to pricing_unit / lineItem/UsageType without a fixed value. |
| field | `CSV/gzip header, delimiter and encoding` | The delivery documentation defines only file names and the TEXT_OR_CSV format option; it makes no statement about header, delimiter or encoding. |
| field | `Whether the line_item_line_item_type value list is exhaustive` | 14 values are documented with descriptions, but the documentation does not state the list is closed. |
| field | `Second 'Capacity Reservation' column group` | The column-group list names both 'Capacity reservation' and 'Capacity Reservation'. No own page could be retrieved for the second (HTTP 404 on candidate URLs); it cannot be confirmed whether a separate set of columns exists. |
| topic | `Manifest.json key names for columns, data files and covered period` | AWS documents the manifest contents in prose only; no JSON schema, key list or example is published. Only the literal key additionalOutputFiles is confirmed. |
| topic | `Manifest.json key order, nesting and required/optional status` | Not documented. |
| topic | `Structure of the additionalOutputFiles section` | Only the section name is documented; its internal structure is not. |
| topic | `JSON type of the FocusVersion manifest value` | Name and values ('1.2' / '1.0') are documented; the JSON type is not explicitly stated. |
| topic | `Manifest file name (<export-name>-Manifest.json vs Manifest.json)` | The Metadata section and the Summary section of the same page document different file names. |
| topic | `Compression parameter value PARQUET equals Snappy` | PARQUET is a documented valid value of the Compression parameter, but the documentation never states it maps to Snappy. The only documented Parquet/Snappy link is the .snappy.parquet file extension. |
| topic | `Currency/unit of monetary CUR 2.0 columns (line_item_*_cost, pricing_public_on_demand_cost, reservation_*, savings_plan_*, discount_*)` | Field documentation describes semantics but never declares the currency unit. The only currency statement in the table is 'All AWS customers are billed in US dollars by default' on line_item_currency_code; the actual export currency is runtime-determined by line_item_currency_code and pricing_currency. |
| topic | `Unit of line_item_usage_amount, line_item_normalized_usage_amount and split_line_item_* usage columns` | Unit is service-dependent; the documentation refers to pricing_unit / lineItem/UsageType without a fixed value. |
| topic | `CSV/gzip header, delimiter and encoding` | The delivery documentation defines only file names and the TEXT_OR_CSV format option; it makes no statement about header, delimiter or encoding. |
| topic | `Whether the line_item_line_item_type value list is exhaustive` | 14 values are documented with descriptions, but the documentation does not state the list is closed. |
| topic | `Second 'Capacity Reservation' column group` | The column-group list names both 'Capacity reservation' and 'Capacity Reservation'. No own page could be retrieved for the second (HTTP 404 on candidate URLs); it cannot be confirmed whether a separate set of columns exists. |

## `aws/bcm-data-exports-focus12` — 20 item(ns)

Spec: [`specs/aws/bcm-data-exports-focus12.schema.json`](../specs/aws/bcm-data-exports-focus12.schema.json)

| kind | item | declared reason |
|---|---|---|
| field | `Currency/unit of all monetary columns (BilledCost, EffectiveCost, ListCost, ContractedCost, ContractedUnitPrice, ListUnitPrice, PricingCurrencyContractedUnitPrice, PricingCurrencyEffectiveCost, PricingCurrencyListUnitPrice, x_Discounts)` | The official column page documents type and nullability but never declares unit or currency. BillingCurrency exists as a column, but AWS does not state that BilledCost is denominated in it. The FinOps FOCUS 1.2 specification (focus.finops.org, incl. the official PDF) returned HTTP 403 on every attempt, so units could not be verified from an official source. |
| field | `Units of CommitmentDiscountQuantity, CommitmentDiscountUnit, ConsumedQuantity, ConsumedUnit, PricingQuantity, PricingUnit` | AWS documents these as provider-specified or 'denominated in Commitment Discount Units' and does not enumerate values. |
| field | `Literal timestamp format and timezone of BillingPeriodStart, BillingPeriodEnd, ChargePeriodStart, ChargePeriodEnd` | The type is documented as timestamp_milliseconds, but the page states neither the serialized format nor UTC for these columns (unlike CUR 2.0, which explicitly states UTC and YYYY-MM-DDTHH:mm:ssZ). |
| field | `Allowed values of ChargeCategory, ChargeClass, ChargeFrequency, CommitmentDiscountCategory, CommitmentDiscountStatus, CommitmentDiscountType, PricingCategory, ServiceCategory, ServiceSubcategory, BillingAccountType, SubAccountType, CapacityReservationStatus, ResourceType` | AWS documents the semantics but does not enumerate valid values on this page; the FOCUS 1.2 specification that enumerates them was unreachable (HTTP 403). |
| field | `Complete list of tag prefixes used in the Tags column` | The migration page mentions the aws:tags:CostCategory/ prefix, but no complete prefix list is published for this table. |
| field | `Literal value of the S3 partition for a FOCUS 1.2 export` | The delivery documentation describes data/<partition>/ generically and details the partition explicitly only for CUR 2.0 (BILLING_PERIOD=YYYY-MM). The FOCUS 1.2 partition is never stated. |
| field | `Manifest.json literal key names for columns, data files and covered period` | AWS documents the manifest contents in prose only; no JSON schema, key list or example is published. |
| field | `JSON type of the FocusVersion manifest value and internal structure of additionalOutputFiles` | Name and value ('1.2') are documented; the JSON type is not stated, and the internal structure of additionalOutputFiles is not published. |
| field | `InvoiceIssuerId` | Listed among the new FOCUS 1.2 columns on the migration page, but absent from the official column table of this surface. With no row documenting it, it is not generated. |
| field | `CSV/gzip header, delimiter and encoding` | The delivery documentation defines only file names and the format options; it makes no statement about header, delimiter or encoding. |
| topic | `Currency/unit of all monetary columns (BilledCost, EffectiveCost, ListCost, ContractedCost, ContractedUnitPrice, ListUnitPrice, PricingCurrencyContractedUnitPrice, PricingCurrencyEffectiveCost, PricingCurrencyListUnitPrice, x_Discounts)` | The official column page documents type and nullability but never declares unit or currency. BillingCurrency exists as a column, but AWS does not state that BilledCost is denominated in it. The FinOps FOCUS 1.2 specification (focus.finops.org, incl. the official PDF) returned HTTP 403 on every attempt, so units could not be verified from an official source. |
| topic | `Units of CommitmentDiscountQuantity, CommitmentDiscountUnit, ConsumedQuantity, ConsumedUnit, PricingQuantity, PricingUnit` | AWS documents these as provider-specified or 'denominated in Commitment Discount Units' and does not enumerate values. |
| topic | `Literal timestamp format and timezone of BillingPeriodStart, BillingPeriodEnd, ChargePeriodStart, ChargePeriodEnd` | The type is documented as timestamp_milliseconds, but the page states neither the serialized format nor UTC for these columns (unlike CUR 2.0, which explicitly states UTC and YYYY-MM-DDTHH:mm:ssZ). |
| topic | `Allowed values of ChargeCategory, ChargeClass, ChargeFrequency, CommitmentDiscountCategory, CommitmentDiscountStatus, CommitmentDiscountType, PricingCategory, ServiceCategory, ServiceSubcategory, BillingAccountType, SubAccountType, CapacityReservationStatus, ResourceType` | AWS documents the semantics but does not enumerate valid values on this page; the FOCUS 1.2 specification that enumerates them was unreachable (HTTP 403). |
| topic | `Complete list of tag prefixes used in the Tags column` | The migration page mentions the aws:tags:CostCategory/ prefix, but no complete prefix list is published for this table. |
| topic | `Literal value of the S3 partition for a FOCUS 1.2 export` | The delivery documentation describes data/<partition>/ generically and details the partition explicitly only for CUR 2.0 (BILLING_PERIOD=YYYY-MM). The FOCUS 1.2 partition is never stated. |
| topic | `Manifest.json literal key names for columns, data files and covered period` | AWS documents the manifest contents in prose only; no JSON schema, key list or example is published. |
| topic | `JSON type of the FocusVersion manifest value and internal structure of additionalOutputFiles` | Name and value ('1.2') are documented; the JSON type is not stated, and the internal structure of additionalOutputFiles is not published. |
| topic | `InvoiceIssuerId` | Listed among the new FOCUS 1.2 columns on the migration page, but absent from the official column table of this surface. With no row documenting it, it is not generated. |
| topic | `CSV/gzip header, delimiter and encoding` | The delivery documentation defines only file names and the format options; it makes no statement about header, delimiter or encoding. |

## `aws/ec2-describe-instances` — 16 item(ns)

Spec: [`specs/aws/ec2-describe-instances.schema.json`](../specs/aws/ec2-describe-instances.schema.json)

| kind | item | declared reason |
|---|---|---|
| field | `JSON property names/schema for DescribeInstances` | only XML is documented; no JSON example or JSON property list is published |
| field | `exact XML container element spelling rule` | API Reference member names (BlockDeviceMapping.N) differ from Sample Response elements (<blockDeviceMapping>) and from the AWS Config CI example (blockDeviceMappings); no conversion rule is published |
| field | `az-id pattern` | the availability-zone-id filter exists but the identifier pattern is not published. RECONFIRMED on 2026-10-15: the Placement object page (API_Placement.html) describes Placement.AvailabilityZone as only 'The Availability Zone of the instance', Type: String, Required: No -- with no pattern, no example and no format, while the SAME object publishes Valid Values for Tenancy (default | dedicated | host). The absence of the pattern and of the data type is a fact about the source, not about the reading: when AWS publishes a closed domain, it publishes. |
| field | `platformDetails valid values` | the Instance object page does not publish the list; the list on DescribeInstances belongs to a filter, not to a return value |
| field | `AWS::EC2::Instance configuration-object schema` | AWS Config does not publish per-resource-type property schemas; it redirects to CloudFormation |
| field | `field-by-field mapping between Instance and the AWS Config configuration object` | AWS Config only states the configuration is what the Describe or List API returns |
| field | `export mechanism to a durable artifact` | not documented (negative evidence); DescribeInstances is a read API |
| field | `publicDnsName / publicIpAddress as Instance return members` | the Instance page uses dnsName and ipAddress; the AWS Config CI example uses publicDnsName and publicIpAddress; neither document publishes the latter as Instance members |
| topic | `JSON property names/schema for DescribeInstances` | only XML is documented; no JSON example or JSON property list is published |
| topic | `exact XML container element spelling rule` | API Reference member names (BlockDeviceMapping.N) differ from Sample Response elements (<blockDeviceMapping>) and from the AWS Config CI example (blockDeviceMappings); no conversion rule is published |
| topic | `az-id pattern` | the availability-zone-id filter exists but the identifier pattern is not published. RECONFIRMED on 2026-10-15: the Placement object page (API_Placement.html) describes Placement.AvailabilityZone as only 'The Availability Zone of the instance', Type: String, Required: No -- with no pattern, no example and no format, while the SAME object publishes Valid Values for Tenancy (default | dedicated | host). The absence of the pattern and of the data type is a fact about the source, not about the reading: when AWS publishes a closed domain, it publishes. |
| topic | `platformDetails valid values` | the Instance object page does not publish the list; the list on DescribeInstances belongs to a filter, not to a return value |
| topic | `AWS::EC2::Instance configuration-object schema` | AWS Config does not publish per-resource-type property schemas; it redirects to CloudFormation |
| topic | `field-by-field mapping between Instance and the AWS Config configuration object` | AWS Config only states the configuration is what the Describe or List API returns |
| topic | `export mechanism to a durable artifact` | not documented (negative evidence); DescribeInstances is a read API |
| topic | `publicDnsName / publicIpAddress as Instance return members` | the Instance page uses dnsName and ipAddress; the AWS Config CI example uses publicDnsName and publicIpAddress; neither document publishes the latter as Instance members |

## `aws/config-describe-compliance-by-config-rule` — 4 item(ns)

Spec: [`specs/aws/config-describe-compliance-by-config-rule.schema.json`](../specs/aws/config-describe-compliance-by-config-rule.schema.json)

| kind | item | declared reason |
|---|---|---|
| topic | `o valor maximo que CappedCount trunca e que CapExceeded compara` | The ComplianceContributorCount page publishes 'up to a maximum number' and describes CapExceeded as 'Indicates whether the maximum count is reached', but does NOT publish the number. Without the ceiling, the comparison CapExceeded performs is not reproducible from the documentation, and the boolean stays null. Verified at https://docs.aws.amazon.com/config/latest/APIReference/API_ComplianceContributorCount.html |
| topic | `exemplo de resposta JSON de DescribeComplianceByConfigRule` | The action page publishes the Response Syntax section, but no filled-in payload example. The structure of this renderer's artifacts comes from the Response Syntax and the Request Parameters section, not from an official example. |
| topic | `regra gerenciada 'ConfigRuleName' x regra gerenciada avaliada` | ConfigRuleName is the NAME of an AWS Config managed rule. The official list (https://docs.aws.amazon.com/config/latest/developerguide/managed-rules-by-aws-config.html) was read on 2026-10-16 and contains 838 names; every name emitted by this renderer was checked against it before being written. The requiredKeyTags PARAMETER that many tagged rules accept is NOT published in the API Reference of this action, and therefore is not part of this surface: it belongs to the rule's parameter, not to the response. |
| topic | `o escopo (conta, regiao) de um item de ComplianceByConfigRules` | The API Reference describes the response as a list of rules, without declaring in the envelope which account and which region produced the item. The grouping by (account, region) that the renderer does is a projection of the estate's own scope -- AWS Config records per account AND per region -- and not a field that the documentation publishes. |

**Divergence recorded, not resolved on its own.** The Valid Values line of the field
`ComplianceType` lists `COMPLIANT | NON_COMPLIANT | NOT_APPLICABLE | INSUFFICIENT_DATA`, and the
**same page** for the `Compliance` shape states that *"AWS Config does not support the NOT_APPLICABLE
value for the Compliance data type"*. Both sides stay here; the renderer's choice is never to emit
`NOT_APPLICABLE`, and it is a constant in the code (`NOT_APPLICABLE_EMITTED = False`). The asymmetry that
makes the confusion easy: the `ComplianceTypes` request filter **accepts** `NOT_APPLICABLE`, only the
response does not.

## `aws/security-hub-asff` — 18 item(ns)

Spec: [`specs/aws/security-hub-asff.schema.json`](../specs/aws/security-hub-asff.schema.json)

| kind | item | declared reason |
|---|---|---|
| field | `S3 object key template for native export` | REWRITTEN on 2026-10-15 with the S3ExportDestination type page: the ObjectPrefix is 'an optional key prefix that Security Hub PREPENDS to the Amazon S3 object keys of the export output', with a maximum of 512 characters and not required. What AWS publishes is the PREFIX; the full key template stays out: none of the export pages (securityhub-v2-findings-export, StartExportJobV2, GetExportJobV2, S3ExportDestination) publishes a suffix, a per-account/region/date folder or a job name. |
| field | `export file name and structure` | not documented -- and now the evidence is structural, not a search that failed. GetExportJobV2 returns, in total, DataType, Destination, EndedAt, ExportJobId, FailureCode, FailureMessage, Name, OutputConfiguration, Scopes, StartedAt and Status: no member describes written files. The only structural detail is the use of multipart upload on large exports, stated in the example policies of StartExportJobV2 (s3:AbortMultipartUpload, UploadPart), which explains the parts but names no object. |
| field | `export compression and encoding` | not documented. SEPARATE from what AWS publishes: the CRYPTOGRAPHY is documented and is mandatory -- S3ExportDestination.KmsKeyArn requires a symmetric ENCRYPT_DECRYPT key, single-Region (mrk- rejected), full ARN and in the same account and Region as the job, for 'server-side encryption' of the objects. What the source does not publish is compression (gzip) and character encoding. |
| field | `CSV header line, quoting rules and line terminator` | RENAMED on 2026-10-15: what used to be 'CSV header and exact delimiter' already has half the answer. FindingsOutput publishes that CSV 'produces comma-separated rows' (the delimiter) and that, for CSV, SelectedFields is MANDATORY and 'the field paths that you specify become the columns of the output, IN THE ORDER that you provide them', from 1 to 50 fields. In other words: the set and the order of the columns are published. What still has no source is the HEADER LINE itself, the CSV quoting/escape rule and the line terminator. |
| field | `export manifest` | RECONFIRMED by structural evidence on 2026-10-15: GetExportJobV2 -- the operation that describes the job and what it wrote -- has no manifest member at all, and the console page does not mention one either. StartExportJobV2 returns only ExportJobId. It is not that the search failed: the page that would describe the manifest exists, was read, and it is not there. |
| field | `exhaustive bodies of the remaining ASFF subobjects` | CORRECTED on 2026-10-15: the limit was the READING, not the source. The JSON outline page is the COMPLETE outline (AWS itself writes 'This page provides a complete outline of the JSON for a finding in ASFF') and it has a .md version; what was truncating it was the .html in the reading tool. Each subobject also has its own page (asff-resourcedetails-<resource>.html, asff-recorddetails-*.html). Closing this item is enumeration work, not new evidence: the source already publishes everything. |
| field | `ASFF to CSV column mapping: the path behind each default column` | The mapping RULE is published and was what was missing: FindingsOutput says that, for CSV, SelectedFields is mandatory, that the columns ARE the OCSF field paths given and that they are applied IN THE ORDER in which they were provided (1 to 50 fields). The console page also publishes the NAMES of the nine default columns -- Finding title, Severity, Resource ID, Created at, Status, Finding account, Finding region, Product vendor name, Finding type -- and says that each option shows the source OCSF path, with one explicit example: 'Finding account' comes from cloud.account.uid. What AWS does not publish is the path of the OTHER eight: without the name->path pairs, an artifact would have to pick the path for 'Severity', 'Status' and 'Created at' by analogy -- and those are exactly the columns whose path the OCSF contract already determines (severity, status, finding_info.created_time_dt), which makes the temptation greater, not smaller. That is why the CSV column stays out of the artifact. |
| field | `OCSF JSON schema emitted by the export` | OCSF format referenced and field paths listed, but no full OCSF schema or version published |
| field | `EventBridge custom action S3 layout` | mechanism described without layout, file name, or output schema |
| topic | `S3 object key template for native export` | REWRITTEN on 2026-10-15 with the S3ExportDestination type page: the ObjectPrefix is 'an optional key prefix that Security Hub PREPENDS to the Amazon S3 object keys of the export output', with a maximum of 512 characters and not required. What AWS publishes is the PREFIX; the full key template stays out: none of the export pages (securityhub-v2-findings-export, StartExportJobV2, GetExportJobV2, S3ExportDestination) publishes a suffix, a per-account/region/date folder or a job name. |
| topic | `export file name and structure` | not documented -- and now the evidence is structural, not a search that failed. GetExportJobV2 returns, in total, DataType, Destination, EndedAt, ExportJobId, FailureCode, FailureMessage, Name, OutputConfiguration, Scopes, StartedAt and Status: no member describes written files. The only structural detail is the use of multipart upload on large exports, stated in the example policies of StartExportJobV2 (s3:AbortMultipartUpload, UploadPart), which explains the parts but names no object. |
| topic | `export compression and encoding` | not documented. SEPARATE from what AWS publishes: the CRYPTOGRAPHY is documented and is mandatory -- S3ExportDestination.KmsKeyArn requires a symmetric ENCRYPT_DECRYPT key, single-Region (mrk- rejected), full ARN and in the same account and Region as the job, for 'server-side encryption' of the objects. What the source does not publish is compression (gzip) and character encoding. |
| topic | `CSV header line, quoting rules and line terminator` | RENAMED on 2026-10-15: what used to be 'CSV header and exact delimiter' already has half the answer. FindingsOutput publishes that CSV 'produces comma-separated rows' (the delimiter) and that, for CSV, SelectedFields is MANDATORY and 'the field paths that you specify become the columns of the output, IN THE ORDER that you provide them', from 1 to 50 fields. In other words: the set and the order of the columns are published. What still has no source is the HEADER LINE itself, the CSV quoting/escape rule and the line terminator. |
| topic | `export manifest` | RECONFIRMED by structural evidence on 2026-10-15: GetExportJobV2 -- the operation that describes the job and what it wrote -- has no manifest member at all, and the console page does not mention one either. StartExportJobV2 returns only ExportJobId. It is not that the search failed: the page that would describe the manifest exists, was read, and it is not there. |
| topic | `exhaustive bodies of the remaining ASFF subobjects` | CORRECTED on 2026-10-15: the limit was the READING, not the source. The JSON outline page is the COMPLETE outline (AWS itself writes 'This page provides a complete outline of the JSON for a finding in ASFF') and it has a .md version; what was truncating it was the .html in the reading tool. Each subobject also has its own page (asff-resourcedetails-<resource>.html, asff-recorddetails-*.html). Closing this item is enumeration work, not new evidence: the source already publishes everything. |
| topic | `ASFF to CSV column mapping: the path behind each default column` | The mapping RULE is published and was what was missing: FindingsOutput says that, for CSV, SelectedFields is mandatory, that the columns ARE the OCSF field paths given and that they are applied IN THE ORDER in which they were provided (1 to 50 fields). The console page also publishes the NAMES of the nine default columns -- Finding title, Severity, Resource ID, Created at, Status, Finding account, Finding region, Product vendor name, Finding type -- and says that each option shows the source OCSF path, with one explicit example: 'Finding account' comes from cloud.account.uid. What AWS does not publish is the path of the OTHER eight: without the name->path pairs, an artifact would have to pick the path for 'Severity', 'Status' and 'Created at' by analogy -- and those are exactly the columns whose path the OCSF contract already determines (severity, status, finding_info.created_time_dt), which makes the temptation greater, not smaller. That is why the CSV column stays out of the artifact. |
| topic | `OCSF JSON schema emitted by the export` | OCSF format referenced and field paths listed, but no full OCSF schema or version published |
| topic | `EventBridge custom action S3 layout` | mechanism described without layout, file name, or output schema |

## `aws/security-hub-ocsf-export` — 4 item(ns)

Spec: [`specs/aws/security-hub-ocsf-export.schema.json`](../specs/aws/security-hub-ocsf-export.schema.json)

| kind | item | declared reason |
|---|---|---|
| field | `metadata.version` | OCSF declares 'version' as mandatory in the metadata object, and AWS does not state which revision of the schema the export uses. The last RELEASED OCSF revision was checked (1.9.0, via the repository's releases API, prerelease=false), but choosing a version for the artifact would be asserting a fact that the AWS source does not publish. The field stays out of the artifact until AWS (or a sample output) says which one it is. RECONSULTED on 2026-10-15: the export operation page (securityhub-v2-findings-export.html) says only that the OCSF_JSON format contains the whole finding, without a version; and the complete list of valid paths of FindingsOutput.SelectedFields (119 paths, checked in the .md) does NOT publish 'metadata.version' -- it publishes 'metadata.uid' and 'metadata.product.*', and not the revision. The only AWS sentence about a version ('Security Hub currently supports findings in OCSF schema version 1.6', securityhub-ocsf.html) declares the schema revision that Security Hub SUPPORTS for findings in general, and not the field value in the export; turning that sentence into the value would be inference, not reading. |
| field | `class_uid / category_uid / type_uid` | OCSF identifies the class and the category by numeric identifiers in the event envelope. The AWS field list does NOT publish any of them, and no consulted page states which class ('compliance_finding' would be the natural candidate) the export uses. Emitting them would be choosing a class by analogy -- exactly what this investigation refused to do. RECONSULTED on 2026-10-15, with evidence backing the refusal: AWS publishes 'class_name' as a valid path of the export itself (in the FindingsOutput.SelectedFields list and in the OCSF field table of the securityhub-v2-automation-rules page), but does not publish the corresponding 'class_uid', nor the category, nor the type, nor the list of values of 'class_name'. What the source asserts is the field NAME, never the value -- so the envelope stays declared as a gap. |
| field | `partition layout of the exported objects` | AWS publishes only ObjectPrefix (up to 512 characters) as the prefix prepended to the object keys; there is no partitioning template, no number of parts and no published file-name convention for the findings export. The path_template stays null instead of invented. |
| field | `compliance.assessments / compliance.control / compliance.standards` | The paths are published by AWS and the state does NOT carry framework, control nor assessment: the ASFF mapping of the same finding also emits 'Compliance: None', with the recorded justification that the model does not have that data. Omitting is the correct answer; emitting empty would assert that the finding was assessed without a framework. |

## `aws/vpc-flow-logs-s3` — 16 item(ns)

Spec: [`specs/aws/vpc-flow-logs-s3.schema.json`](../specs/aws/vpc-flow-logs-s3.schema.json)

| kind | item | declared reason |
|---|---|---|
| field | `header row in text format` | not documented in Flow log records / Flow log files |
| field | `file character encoding` | not documented |
| field | `Parquet/Arrow schema and column names` | only per-field Parquet data types are documented (see parquet_type on each column) |
| field | `hash suffix algorithm in file name` | file name format documented, hash origin not |
| field | `TagFieldSpecifications object schema` | referenced but not published in the consulted pages |
| field | `textual representation of start/end` | documented as Unix seconds; exact textual formatting in the file not published |
| field | `az-id identifier pattern` | meaning documented, pattern not published |
| field | `version 6 fields` | official table jumps from v5 to v7; no v6 exists in the table |
| topic | `header row in text format` | not documented in Flow log records / Flow log files |
| topic | `file character encoding` | not documented |
| topic | `Parquet/Arrow schema and column names` | only per-field Parquet data types are documented (see parquet_type on each column) |
| topic | `hash suffix algorithm in file name` | file name format documented, hash origin not |
| topic | `TagFieldSpecifications object schema` | referenced but not published in the consulted pages |
| topic | `textual representation of start/end` | documented as Unix seconds; exact textual formatting in the file not published |
| topic | `az-id identifier pattern` | meaning documented, pattern not published |
| topic | `version 6 fields` | official table jumps from v5 to v7; no v6 exists in the table |

## `azure/arm-network-security-group-rules` — 6 item(ns)

Spec: [`specs/azure/arm-network-security-group-rules.schema.json`](../specs/azure/arm-network-security-group-rules.schema.json)

| kind | item | declared reason |
|---|---|---|
| field | `properties.flushConnection` | The page publishes the type (bool) and the description of the effect, but does not exemplify the payload nor fix a value: the field enters the format and not the value contract. No rule in this state defines it, so it is not emitted. |
| field | `ApplicationSecurityGroup.properties` | The page publishes the ApplicationSecurityGroupPropertiesFormat table EMPTY -- the provider does not declare the content. It is the name-only case: the name enters the contract, the value comes out empty instead of invented. |
| field | `ApplicationSecurityGroup.tags` | The page references ResourceTags and publishes the table EMPTY (the type is 'Dictionary of tag names and values' in the parent's prose). With no published tag names, there is nothing to emit. |
| field | `apiVersion` | The page lists 60 versions in the navigation and the 'Resource format' section uses 2025-09-01 in the example, but no consulted page states which version is current for the payload. The version is not a field of the response BODY, so it is not emitted. |
| field | `properties.securityRules[].id` | The page publishes the TYPE ('id | Resource ID. | string') and does not state the SHAPE of a rule's id -- whether it is the nested path .../networkSecurityGroups/{nsg}/securityRules/{rule} or something else. With the type published and the shape not, the only faithful output is to NOT emit the field: composing the path would be inventing the shape. That is why the name is here and not in 'sets' (a column cannot belong to the format and be unproven at the same time). |
| field | `limite de regras por NSG / numero maximo de regras` | Not published in the consulted pages. This state emits two rules and the ceiling is not asserted. |

## `azure/arm-resource-representation` — 9 item(ns)

Spec: [`specs/azure/arm-resource-representation.schema.json`](../specs/azure/arm-resource-representation.schema.json)

| kind | item | declared reason |
|---|---|---|
| field | `GET response Definitions table (per-field type and required flags for nested types)` | The official Virtual Machines - Get page did not expose its type Definitions section in any retrieval attempt; the returned content stops at the Examples. The anchors #virtualmachine, #instanceviewtypes and #clouderror are referenced inside the page, so the definitions exist on the page but their content was never read. No field in this file is attributed to that section. |
| field | `sku (top-level)` | Does not appear in any official GET/List All example response for Microsoft.Compute/virtualMachines, nor in the ARM template top-level property list for this type. Not listed, to avoid inventing a property. |
| field | `properties.instanceView.*` | $expand=InstanceView is documented as a parameter, but no consulted official example returns the instanceView object, so none of its subfields (vmAgent, disks, extensions, statuses, computerName, osName, osVersion, ...) are listed. |
| field | `properties.storageProfile.osDisk.managedDisk.additionalDiskProperties.managedDiskProperties.*` | The template reference lists the equivalent structure for osDisk but the child properties were only transcribed in full for dataDisks; not duplicated by inference. |
| field | `required flag for every field other than properties.storageProfile.dataDisks[].createOption` | Only DataDisk.createOption is explicitly marked '(required)' in the consulted template reference: 'CreateOption' carries '(required)' in the Value column, and no other property does. Because the REST Definitions table could not be read, the remaining required flags are unknown rather than false. |
| field | `read-only (readOnly) status of most properties` | Only properties.vmId, properties.storageProfile.imageReference.exactVersion, properties.timeCreated and identity.principalId/identity.tenantId have documentary evidence of being read-only (present in responses but absent from the deployment property list, or described as platform-assigned). For the rest the REST reference was not readable. |
| field | `structure of resources[].properties.settings and .protectedSettings` | Examples show them as arbitrary objects; no schema is published. |
| field | `CloudError / ErrorResponse field list` | The error response type is referenced but no field table for it was read. |
| field | `delivery.path_template / delivery.compression` | Not applicable: this is an ARM REST JSON response, not a push export. No blob path or compression exists in the documentation. Empty by design. |

## `azure/azure-resource-graph-virtual-machines` — 9 item(ns)

Spec: [`specs/azure/azure-resource-graph-virtual-machines.schema.json`](../specs/azure/azure-resource-graph-virtual-machines.schema.json)

| kind | item | declared reason |
|---|---|---|
| field | `formal Resources table column schema (names + types)` | Microsoft publishes no page listing the resources table's columns with types (unlike Azure Monitor tables, which have explicit column tables). All names were read from official JSON response examples; the types are not asserted by any consulted page. |
| field | `Resources column data types (kind, managedBy, plan, sku, tags, tenantId, ...)` | They appear in examples as ""/{} which does not fix a type (string vs object vs nullability). |
| field | `required flags for any Resources column` | No consulted official page states that any resources column is always present. |
| field | `complete properties.* list for microsoft.compute/virtualmachines in the resources table` | Only the paths listed in the .md are proven (official example JSON plus the official REST query example). No complete list is published, and the documented PII scrub means the set may differ from ARM. |
| field | `properties.extended.* for VMs beyond instanceView.powerState.code` | Only that path is exemplified officially; extended properties are documented as a preview feature. |
| field | `official enumeration of SecurityResources resource types` | The supported-tables-resources document retrieved does not present a SecurityResources section with an enumerated type list. |
| field | `SecurityResources field data types` | No consulted official page publishes a type table; number/array/dynamic values in this file are the spec author's classification based on how the official queries use them (tolong, todouble, mv-expand, todynamic). |
| field | `delivery.path_template / delivery.format / delivery.compression` | Resource Graph is a query service, not a push export; no storage path, file format or compression is documented. The only documented file export is the manual Resource Graph Explorer CSV (55000 record cap) whose column header is not published. Empty by design. |
| field | `resourcechanges / ResourceChanges table schema` | The 'Get resource changes' page shows an example payload and defers to the REST reference /rest/api/resources/changes for the full field reference. That reference was not read in this investigation, so no field is asserted here. |

## `azure/cost-management-export-cost-details` — 7 item(ns)

Spec: [`specs/azure/cost-management-export-cost-details.schema.json`](../specs/azure/cost-management-export-cost-details.schema.json)

| kind | item | declared reason |
|---|---|---|
| field | `data types for all classic cost details columns` | No official Microsoft page publishes a DataType per classic cost details column. The FOCUS dataset documentation does publish types, but the classic dataset does not. Not generated. |
| field | `nullability / required flag for all classic cost details columns` | Not published by Microsoft for the classic dataset. |
| field | `units and currency semantics per column` | Prose descriptions indicate currency for some columns, but no per-column unit declaration exists. |
| field | `timestamp format for Date, UsageDateTime, billingPeriodStartDate, servicePeriodStartDate etc.` | The pages give semantic descriptions ("The usage or purchase date of the charge") and, for UsageDateTime only, the pattern yyyy-mm-dd. No authoritative ISO 8601/UTC declaration is published for the classic dataset. |
| field | `allowed values for ChargeType, Frequency, PricingModel, PublisherType, Term` | Only illustrative value examples appear in prose; no complete enumeration table is published. |
| field | `exact casing of benefitId / benefitName / PayGPrice / payGPrice / PricingModel / pricingModel` | Casing is inconsistent between the schema pages and, within a single page, between dataset versions. See the divergences section of the .md spec. |
| field | `whether actual and amortized differ in column set` | Microsoft documents actual and amortized as separate datasets but the schema index publishes ONE cost and usage details schema per agreement, not one per metric. No document states that actual and amortized share an identical column list. |

## `azure/cost-management-export-focus12` — 2 item(ns)

Spec: [`specs/azure/cost-management-export-focus12.schema.json`](../specs/azure/cost-management-export-focus12.schema.json)

| kind | item | declared reason |
|---|---|---|
| field | `x_PricingCurrency` | Listed as column 79 in the Cost Management FOCUS 1.2-preview schema page, but absent from the official FinOps toolkit FocusCost_1.2-preview metadata JSON (106 columns) that Microsoft links from the same documentation. Casing/type and presence are therefore contradictory between two official Microsoft sources. |
| field | `column order` | The schema page enumerates columns 1-105 while the official metadata JSON enumerates 106 columns; the two orders disagree from index 73 onward (x_InvoiceIssuerId, x_SkuTerm, x_SkuPlanName/x_SkuPartNumber). No single authoritative order can be cited. |

## `azure/cost-management-export-manifest` — 6 item(ns)

Spec: [`specs/azure/cost-management-export-manifest.schema.json`](../specs/azure/cost-management-export-manifest.schema.json)

| kind | item | declared reason |
|---|---|---|
| field | `exportConfig.beginDate` | Not present in the only official _manifest.json example. Microsoft publishes no manifest field table or JSON Schema, so its existence and format cannot be proven. Not generated. |
| field | `exportConfig.endDate` | Not present in the only official _manifest.json example. Same reasoning as exportConfig.beginDate. Not generated. |
| field | `aggregate semantics of top-level byteCount/dataRowCount when blobCount > 1` | The official example has blobCount=1 so top-level and partition values coincide. Documentation never states whether top-level values are sums over partitions. |
| field | `complete value sets for exportConfig.type / exportConfig.timeFrame / exportConfig.granularity` | No retrievable enumeration table was found on the consulted official pages; only values appearing in official examples are proven. |
| field | `manifest schema stability across manifestVersion values` | No published manifest schema version list or changelog, so future field sets cannot be proven. |
| field | `manifest for non-partitioned exports` | Documentation ties the manifest to partitioned data and states partitioning can no longer be disabled; no example or path is documented for a non-partitioned export. |

## `azure/defender-for-cloud-continuous-export` — 14 item(ns)

Spec: [`specs/azure/defender-for-cloud-continuous-export.schema.json`](../specs/azure/defender-for-cloud-continuous-export.schema.json)

| kind | item | declared reason |
|---|---|---|
| field | `Severity` | Present in the Defender for Cloud alert data model (alerts-schemas) but absent from the documented SecurityAlert table column list, which uses AlertSeverity. Conflicting official sources; type not asserted. |
| field | `SourceSystem` | Listed as 'unused' in the alert data model with no type; absent from the SecurityAlert table column list. |
| field | `TenantId` | Listed in the alert data model with no type; absent from the SecurityAlert table column list. |
| field | `DiscoveredTimeUTC (SecurityAlert)` | Referenced by the alert data model as identical to TimeGenerated but absent from the documented SecurityAlert column list. |
| field | `SecureScores / SecureScoresSnapshot record schema` | EventSource value is documented, but no official page consulted publishes the exported record schema for secure score. |
| field | `SecureScoreControls / SecureScoreControlsSnapshot record schema` | EventSource value is documented, but no official page consulted publishes the exported record schema for secure score controls. |
| field | `RegulatoryComplianceAssessment / RegulatoryComplianceAssessmentSnapshot record schema` | EventSource value is documented, but no official page consulted publishes the exported record schema. |
| field | `SubAssessments / SubAssessmentsSnapshot record schema and destination table` | EventSource value is documented, but no official page consulted publishes the record schema nor names a destination table for sub-assessments. |
| field | `AttackPaths continuous-export payload schema` | The published attack path schema belongs to the Azure Resource Graph API (securityresources), not to the continuous export event payload. No official page consulted documents the export payload. |
| field | `Event Hub message envelope / headers / partition key` | Official docs only state the format is JSON. No envelope, headers or partitioning scheme is published. |
| field | `aka.ms/ASCAutomationSchemas content` | Referenced by the official continuous export page as the schema reference, but the link redirects cross-origin to github.com and could not be retrieved; the corresponding GitHub folder returned HTTP 404. Not read, therefore not used as a source. |
| field | `CSV report column header (Download CSV report)` | The manual CSV export is documented as a feature, but no official page consulted publishes its column set. |
| field | `delivery.path_template` | Azure Storage is not a documented destination of continuous export, so no blob path template exists in the official documentation. Field left empty by design. |
| field | `delivery.compression` | No compression is documented for continuous export delivery. Field left empty by design. |

## `azure/nsg-flow-logs-v2` — 7 item(ns)

Spec: [`specs/azure/nsg-flow-logs-v2.schema.json`](../specs/azure/nsg-flow-logs-v2.schema.json)

| kind | item | declared reason |
|---|---|---|
| field | `delivery.compression` | No official page consulted states a compression algorithm (or its absence) for PT1H.json. Field intentionally left empty. |
| field | `delivery.encoding` | No official page consulted states the character encoding. |
| field | `flowTuples counter values for flow state B` | Docs state 'Statistics aren't provided' for B and the official examples show empty fields; no numeric value or literal placeholder is documented. |
| field | `records[].time fractional-second digit count` | All official examples show exactly 7 fractional digits, but the documentation does not assert that the count is fixed. |
| field | `manifest / metadata blob` | No manifest or metadata file is documented for NSG flow logs v2. |
| field | `records[].resourceid (all-lowercase spelling)` | Appears in the property list of the official page while every official JSON example uses 'resourceId'. Both spellings exist in the same official document; no inference taken about which is authoritative. |
| field | `maximum PT1H.json size / maximum record count` | Not documented. |

## `azure/vnet-flow-logs` — 10 item(ns)

Spec: [`specs/azure/vnet-flow-logs.schema.json`](../specs/azure/vnet-flow-logs.schema.json)

| kind | item | declared reason |
|---|---|---|
| field | `blob compression` | No official page consulted documents compression for PT1H.json. |
| field | `blob encoding` | No official page consulted documents the character encoding. |
| field | `NTANetAnalytics column data types` | The official schema table presents 'Format' as descriptive prose (e.g. 'Date and time in UTC', 'Subscription ID') and leaves it empty for the flow-count fields. The integer/datetime types used here are the spec author's classification, not official assertions. |
| field | `NTAIpDetails column data types` | Same as above: the official 'Format' cell is descriptive prose. |
| field | `literal value of a platform rule name in flowGroups[].rule` | The docs describe 'platform rules' conceptually but never publish the literal string emitted in that case. |
| field | `allowed values of records[].flowLogVersion` | The only value visible in the official documentation is 4 (sample record). No enumeration of valid values is published. |
| field | `manifest / metadata file` | No manifest or metadata artifact is documented for virtual network flow logs. |
| field | `blob_id field` | Referenced in the traffic analytics prose ('use the blob_id field, which can be referenced from storage') but absent from the published schema table, so no row/type/source could be established. |
| field | `exact derivation of the NETWORKWATCHER_{Region}_{ResourceName}-{ResourceGroupName}-FLOWLOGS partition segment` | The path template shows the segment but the documentation does not state how it is derived when the flow log name is customised. |
| field | `SrcIP_s / DestIP_s / VMIP_s / PublicIPs_s suffixed variants` | Mentioned in the Notes prose ('Some field names are appended with _s or _d') but not present as rows in the published schema table (which uses unsuffixed names). No schema row could be established. |

## `gcp/asset-search-all-iam-policies` — 2 item(ns)

Spec: [`specs/gcp/asset-search-all-iam-policies.schema.json`](../specs/gcp/asset-search-all-iam-policies.schema.json)

| kind | item | declared reason |
|---|---|---|
| field | `results[].resourceUuid` | The gcp_rest_fixtures artifact emits this cross-plane join key, and the official IamPolicySearchResult contract does NOT declare it (zero occurrences in the complete discovery document). The path enters here because the core compares the full path, and a name cannot belong to the format and be unproven at the same time. |
| field | `results[].resourceUuid` | Cross-plane join key that the old renderer emitted and that NONE of the six official contracts declares (zero occurrences in the complete documents). Recorded here because the claim also holds for this surface: the auditor has to flag the field if it shows up. See docs/CONTRATO-APIS-GCP.md for the risk per transport. |

## `gcp/asset-search-all-resources` — 3 item(ns)

Spec: [`specs/gcp/asset-search-all-resources.schema.json`](../specs/gcp/asset-search-all-resources.schema.json)

| kind | item | declared reason |
|---|---|---|
| field | `results[].resourceUuid` | The gcp_rest_fixtures artifact emits 'resourceUuid' (the cross-plane join key) inside each result, and the official ResourceSearchResult proto does NOT declare that field. In proto3 an unknown field is not part of the contract, and the code itself records, for the alertPolicies family, that an undeclared top-level field makes the client REJECT the whole response ('ParseDict fails with has no field named resourceUuid'). The PATH enters here, and not in 'sets', because a name cannot belong to the format and be unproven at the same time -- and the fidelity core compares the full path, not the short name. Where it LIVES when emitted: inside the item, so here; where it lives in the raw body: next to 'name'. As long as the renderer emits it, the auditor flags it [unverified_emitted] -- and that flagging is the pending decision of this item, not a noise to be silenced. |
| field | `results[].name value shape` | The TYPE and the SHAPE of the field are published, and the VALUE does not follow the format by type. The proto says that 'name' is the full resource name (example: //compute.googleapis.com/projects/my_project_123/zones/zone1/instances/instance1) and the official asset-names table (https://docs.cloud.google.com/asset-inventory/docs/asset-names) publishes the format PER TYPE: Instance -> //compute.googleapis.com/projects/PROJECT_ID/zones/ZONE/instances/INSTANCE; Instance (Cloud SQL) -> //cloudsql.googleapis.com/projects/PROJECT_ID/instances/INSTANCE; Cluster -> //container.googleapis.com/projects/PROJECT_ID/locations/LOCATION/clusters/CLUSTER; Bucket -> //storage.googleapis.com/BUCKET. The artifact composes '//<resource_type>.googleapis.com/projects/<project>/<resource_type>/<resource_name>', which carries no zones/locations and uses the type's internal name as a path segment. The field exists and is emitted; the value is under audit. |
| field | `results[].assetType value shape` | The TYPE of the field is published (string) and the proto exemplifies 'compute.googleapis.com/Disk'; the official asset-names table publishes 'compute.googleapis.com/Instance'. The artifact composes '<resource_type>.googleapis.com' (e.g. 'compute_instance.googleapis.com'), without an asset-type suffix -- the state's internal type name is not the asset type that CAI indexes. The complete official list is a page of its own (supported-asset-types) that was not consulted type by type for this state. |

## `gcp/billing-budgets` — 2 item(ns)

Spec: [`specs/gcp/billing-budgets.schema.json`](../specs/gcp/billing-budgets.schema.json)

| kind | item | declared reason |
|---|---|---|
| field | `budgets[].amount.specifiedAmount.units value shape` | The field and the type are published (int64 as a string); the VALUE is fixed ('1000') and comes from no budget of the state -- a declared sample value, not a measured one. |
| field | `budgets[].resourceUuid` | Cross-plane join key that the old renderer emitted and that NONE of the six official contracts declares (zero occurrences in the complete documents). Recorded here because the claim also holds for this surface: the auditor has to flag the field if it shows up. See docs/CONTRATO-APIS-GCP.md for the risk per transport. |

## `gcp/billing-export-detailed` — 18 item(ns)

Spec: [`specs/gcp/billing-export-detailed.schema.json`](../specs/gcp/billing-export-detailed.schema.json)

| kind | item | declared reason |
|---|---|---|
| field | `partitioning [gcp_billing_export_resource_v1_<BILLING_ACCOUNT_ID>]` | No official documentation page consulted states the partitioning column or granularity of the detailed usage cost table. The detailed schema page does not contain the word partition; only query examples use _PARTITIONTIME. |
| field | `clustering [gcp_billing_export_resource_v1_<BILLING_ACCOUNT_ID>]` | No official documentation page consulted states clustering columns for this table. |
| field | `file_format [gcp_billing_export_resource_v1_<BILLING_ACCOUNT_ID>]` | Delivery is a BigQuery table; no file format, compression, encoding, delimiter or header is documented for this surface. |
| field | `manifest_metadata_schema [gcp_billing_export_resource_v1_<BILLING_ACCOUNT_ID>]` | No manifest or metadata document is emitted to the customer in the documented mechanism. |
| field | `credits.amount sign convention [credits.amount]` | The field reference documents only the amount of the credit applied to the usage. The negative sign appears only in an example query result and is implied by the net-cost formula SUM(cost) + SUM(credits.amount). |
| field | `net cost column [table columns]` | No net-cost column exists in the documented schema; the docs compute it with a query expression. |
| field | `closed enumeration of usage.unit / usage.pricing_unit / price.unit values [usage.unit, usage.pricing_unit, price.unit]` | Docs give examples and refer to the Cloud Billing Catalog API; no closed value list is published. |
| field | `exact timestamp string format [usage_start_time, usage_end_time, export_time]` | Type is declared as Timestamp and the docs link to the BigQuery timestamp data types page; no exact literal pattern is asserted. Official query examples render values as 2025-09-16 00:00:00.000000 UTC. |
| field | `universal population of resource.name / resource.global_name [resource.name, resource.global_name]` | The docs list which services expose resource granularity and note exceptions (for example Snapshot_disk_time metrics do not provide resource.name, and StreamingInsertBytes has no resource identifier), but never assert universal population. |
| topic | `partitioning [gcp_billing_export_resource_v1_<BILLING_ACCOUNT_ID>]` | No official documentation page consulted states the partitioning column or granularity of the detailed usage cost table. The detailed schema page does not contain the word partition; only query examples use _PARTITIONTIME. |
| topic | `clustering [gcp_billing_export_resource_v1_<BILLING_ACCOUNT_ID>]` | No official documentation page consulted states clustering columns for this table. |
| topic | `file_format [gcp_billing_export_resource_v1_<BILLING_ACCOUNT_ID>]` | Delivery is a BigQuery table; no file format, compression, encoding, delimiter or header is documented for this surface. |
| topic | `manifest_metadata_schema [gcp_billing_export_resource_v1_<BILLING_ACCOUNT_ID>]` | No manifest or metadata document is emitted to the customer in the documented mechanism. |
| topic | `credits.amount sign convention [credits.amount]` | The field reference documents only the amount of the credit applied to the usage. The negative sign appears only in an example query result and is implied by the net-cost formula SUM(cost) + SUM(credits.amount). |
| topic | `net cost column [table columns]` | No net-cost column exists in the documented schema; the docs compute it with a query expression. |
| topic | `closed enumeration of usage.unit / usage.pricing_unit / price.unit values [usage.unit, usage.pricing_unit, price.unit]` | Docs give examples and refer to the Cloud Billing Catalog API; no closed value list is published. |
| topic | `exact timestamp string format [usage_start_time, usage_end_time, export_time]` | Type is declared as Timestamp and the docs link to the BigQuery timestamp data types page; no exact literal pattern is asserted. Official query examples render values as 2025-09-16 00:00:00.000000 UTC. |
| topic | `universal population of resource.name / resource.global_name [resource.name, resource.global_name]` | The docs list which services expose resource granularity and note exceptions (for example Snapshot_disk_time metrics do not provide resource.name, and StreamingInsertBytes has no resource identifier), but never assert universal population. |

## `gcp/billing-export-pricing` — 20 item(ns)

Spec: [`specs/gcp/billing-export-pricing.schema.json`](../specs/gcp/billing-export-pricing.schema.json)

| kind | item | declared reason |
|---|---|---|
| field | `clustering [cloud_pricing_export]` | No official page consulted declares clustering columns for this table. |
| field | `partition granularity as an explicit statement [cloud_pricing_export._PARTITIONTIME]` | The docs describe _PARTITIONTIME as the date the data belongs to and always filter with DATE(...), but never write an explicit 'partitioned by day' statement. |
| field | `file_format [cloud_pricing_export]` | Delivery is a BigQuery table; no file format, compression, encoding, delimiter or header is documented. |
| field | `manifest_metadata_schema [cloud_pricing_export]` | No manifest or metadata document is emitted to the customer in the documented mechanism. |
| field | `exhaustive subfields of list_price / billing_account_price [list_price, billing_account_price]` | The docs introduce these structs with 'including: aggregation_info, tiered_rates' (plus price_info for billing_account_price) without enumerating every subfield. |
| field | `subfields of consumption_model_prices.list_price and .billing_account_price [consumption_model_prices.list_price, consumption_model_prices.billing_account_price]` | The docs defer to the list_price and billing_account_price descriptions rather than enumerating subfields in this nested context. |
| field | `real type of tiered_rates [tiered_rates]` | Documentation declares 'Array of Strings' while its subfields are numeric and the official example UNNESTs it as a struct array. Internal contradiction; recorded as documented. |
| field | `temporal type of currency_conversion_rate [currency_conversion_rate]` | Documented as String here but as Float in the usage cost tables. Recorded as documented in each surface, not normalized. |
| field | `closed enumeration of pricing_unit / pricing_unit_description [pricing_unit, pricing_unit_description]` | Only examples are given (GiBy.mo / gibibyte month); no closed value list is published. |
| field | `exact timestamp string format [export_time, pricing_as_of_time]` | Type is declared as Timestamp and the docs link to the BigQuery timestamp data types page; no exact literal pattern is asserted for these columns. |
| topic | `clustering [cloud_pricing_export]` | No official page consulted declares clustering columns for this table. |
| topic | `partition granularity as an explicit statement [cloud_pricing_export._PARTITIONTIME]` | The docs describe _PARTITIONTIME as the date the data belongs to and always filter with DATE(...), but never write an explicit 'partitioned by day' statement. |
| topic | `file_format [cloud_pricing_export]` | Delivery is a BigQuery table; no file format, compression, encoding, delimiter or header is documented. |
| topic | `manifest_metadata_schema [cloud_pricing_export]` | No manifest or metadata document is emitted to the customer in the documented mechanism. |
| topic | `exhaustive subfields of list_price / billing_account_price [list_price, billing_account_price]` | The docs introduce these structs with 'including: aggregation_info, tiered_rates' (plus price_info for billing_account_price) without enumerating every subfield. |
| topic | `subfields of consumption_model_prices.list_price and .billing_account_price [consumption_model_prices.list_price, consumption_model_prices.billing_account_price]` | The docs defer to the list_price and billing_account_price descriptions rather than enumerating subfields in this nested context. |
| topic | `real type of tiered_rates [tiered_rates]` | Documentation declares 'Array of Strings' while its subfields are numeric and the official example UNNESTs it as a struct array. Internal contradiction; recorded as documented. |
| topic | `temporal type of currency_conversion_rate [currency_conversion_rate]` | Documented as String here but as Float in the usage cost tables. Recorded as documented in each surface, not normalized. |
| topic | `closed enumeration of pricing_unit / pricing_unit_description [pricing_unit, pricing_unit_description]` | Only examples are given (GiBy.mo / gibibyte month); no closed value list is published. |
| topic | `exact timestamp string format [export_time, pricing_as_of_time]` | Type is declared as Timestamp and the docs link to the BigQuery timestamp data types page; no exact literal pattern is asserted for these columns. |

## `gcp/billing-export-standard` — 16 item(ns)

Spec: [`specs/gcp/billing-export-standard.schema.json`](../specs/gcp/billing-export-standard.schema.json)

| kind | item | declared reason |
|---|---|---|
| field | `partitioning [gcp_billing_export_v1_<BILLING_ACCOUNT_ID>]` | No official documentation page consulted states the partitioning column or granularity of the standard usage cost table. Searched: standard-usage, export-data-bigquery-tables, export-data-bigquery-setup, export-data-bigquery, bq-examples (no mention of partitioning for the standard table). |
| field | `clustering [gcp_billing_export_v1_<BILLING_ACCOUNT_ID>]` | No official documentation page consulted states clustering columns for this table. |
| field | `file_format [gcp_billing_export_v1_<BILLING_ACCOUNT_ID>]` | Delivery is a BigQuery table; no file format, compression, encoding, delimiter or header is documented for this surface. |
| field | `manifest_metadata_schema [gcp_billing_export_v1_<BILLING_ACCOUNT_ID>]` | No manifest or metadata document is emitted to the customer in the documented mechanism. |
| field | `credits.amount sign convention [credits.amount]` | The field reference documents only 'The amount of the credit applied to the usage.' The sign is shown (negative) only in an example query result and implied by the net-cost formula SUM(cost) + SUM(credits.amount); no textual statement in the schema documents it as a contract. |
| field | `net cost column [table columns]` | No net-cost column exists in the documented schema; the docs compute it with a query expression. |
| field | `closed enumeration of usage.unit / usage.pricing_unit / price.unit values [usage.unit, usage.pricing_unit, price.unit]` | Docs give examples (byte-seconds) and refer to the Cloud Billing Catalog API; no closed value list is published. |
| field | `exact timestamp string format [usage_start_time, usage_end_time, export_time]` | Type is declared as Timestamp and the docs link to the BigQuery timestamp data types page; no exact literal pattern (e.g. YYYY-MM-DDTHH:MM:SSZ) is asserted for these columns. Official query examples render values as '2025-09-16 00:00:00.000000 UTC'. |
| topic | `partitioning [gcp_billing_export_v1_<BILLING_ACCOUNT_ID>]` | No official documentation page consulted states the partitioning column or granularity of the standard usage cost table. Searched: standard-usage, export-data-bigquery-tables, export-data-bigquery-setup, export-data-bigquery, bq-examples (no mention of partitioning for the standard table). |
| topic | `clustering [gcp_billing_export_v1_<BILLING_ACCOUNT_ID>]` | No official documentation page consulted states clustering columns for this table. |
| topic | `file_format [gcp_billing_export_v1_<BILLING_ACCOUNT_ID>]` | Delivery is a BigQuery table; no file format, compression, encoding, delimiter or header is documented for this surface. |
| topic | `manifest_metadata_schema [gcp_billing_export_v1_<BILLING_ACCOUNT_ID>]` | No manifest or metadata document is emitted to the customer in the documented mechanism. |
| topic | `credits.amount sign convention [credits.amount]` | The field reference documents only 'The amount of the credit applied to the usage.' The sign is shown (negative) only in an example query result and implied by the net-cost formula SUM(cost) + SUM(credits.amount); no textual statement in the schema documents it as a contract. |
| topic | `net cost column [table columns]` | No net-cost column exists in the documented schema; the docs compute it with a query expression. |
| topic | `closed enumeration of usage.unit / usage.pricing_unit / price.unit values [usage.unit, usage.pricing_unit, price.unit]` | Docs give examples (byte-seconds) and refer to the Cloud Billing Catalog API; no closed value list is published. |
| topic | `exact timestamp string format [usage_start_time, usage_end_time, export_time]` | Type is declared as Timestamp and the docs link to the BigQuery timestamp data types page; no exact literal pattern (e.g. YYYY-MM-DDTHH:MM:SSZ) is asserted for these columns. Official query examples render values as '2025-09-16 00:00:00.000000 UTC'. |

## `gcp/catalog-services` — 3 item(ns)

Spec: [`specs/gcp/catalog-services.schema.json`](../specs/gcp/catalog-services.schema.json)

| kind | item | declared reason |
|---|---|---|
| field | `services[].serviceId value shape` | The type and the shape of the field are published (the doc exemplifies '6F81-5844-456A'), and the value is derived from the state's service name. The field is correct; the content of the id does not follow the published example. |
| field | `services[].name value shape` | Same: 'services/{id}' is the published format, and the embedded id is derived from the state. |
| field | `services[].resourceUuid` | Cross-plane join key that the old renderer emitted and that NONE of the six official contracts declares (zero occurrences in the complete documents). Recorded here because the claim also holds for this surface: the auditor has to flag the field if it shows up. See docs/CONTRATO-APIS-GCP.md for the risk per transport. |

## `gcp/catalog-skus` — 2 item(ns)

Spec: [`specs/gcp/catalog-skus.schema.json`](../specs/gcp/catalog-skus.schema.json)

| kind | item | declared reason |
|---|---|---|
| field | `skus[].skuId value shape` | The field and the format are published (the example is 'D041-B8A1-6E0B'); the value is the state's sku_id, which the generator forges internally. |
| field | `skus[].resourceUuid` | Cross-plane join key that the old renderer emitted and that NONE of the six official contracts declares (zero occurrences in the complete documents). Recorded here because the claim also holds for this surface: the auditor has to flag the field if it shows up. See docs/CONTRATO-APIS-GCP.md for the risk per transport. |

## `gcp/cloud-asset-inventory-compute-instance` — 9 item(ns)

Spec: [`specs/gcp/cloud-asset-inventory-compute-instance.schema.json`](../specs/gcp/cloud-asset-inventory-compute-instance.schema.json)

| kind | item | declared reason |
|---|---|---|
| field | `concrete shape of resource.data for compute.googleapis.com/Instance` | No Cloud Asset Inventory page publishes the schema of resource.data for this or any asset type. The Resource.data field is documented only as 'object (Struct format)': 'The content of the resource, in which some sensitive fields are removed and may not be present.' The mapping to the Compute Engine Instances REST representation is NOT asserted anywhere in the CAI documentation. |
| field | `per-asset-type schema produced by separateTablesPerAssetType=true for compute.googleapis.com/Instance` | The page states the schema maps nested Resource.data fields to RECORD columns (up to 15 nested levels) but publishes no resulting schema; the referenced examples live in the Cloud console. |
| field | `field-name casing inside resource.data (camelCase vs snake_case)` | Not asserted in the Cloud Asset Inventory documentation. |
| field | `compression and encoding of Cloud Storage NDJSON objects` | Only 'newline-delimited JSON' is documented; compression/encoding are not stated. |
| field | `export manifest` | No manifest is documented. Only the long-running Operation object with path projects/PROJECT_NUMBER/operations/ExportAssets/CONTENT_TYPE/OPERATION_ID. |
| field | `ACCESS_POLICY (VPCSC) schema columns` | RECLASSIFIED on 2026-10-15: it was not a pending reading, it was SCOPE. The exporting-to-bigquery page publishes a 'VPCSC policy schema', but it describes the contentType ACCESS_POLICY (Virtual Private Cloud Security Command Center), and the scope of this surface is the compute.googleapis.com/Instance table. Transcribing its columns here would put columns of ANOTHER content type into the table of a compute instance. The gap is definitive on this surface; turning it into a column would require a new surface for the contentType ACCESS_POLICY. |
| field | `OS_INVENTORY schema columns` | RECLASSIFIED on 2026-10-15: it was not a pending reading, it was SCOPE. The 'OS inventory schema' published by the page belongs to the contentType OS_INVENTORY, and the scope of this surface is the compute.googleapis.com/Instance table. The operating system inventory is a different product from the cloud resource inventory: it carries the same data (the resource) through another door. Do not generate it here. |
| field | `RELATIONSHIP schema columns` | RECLASSIFIED on 2026-10-15: it was not a pending reading, it was SCOPE. The published 'Relationship schema' belongs to the contentType RELATIONSHIP (the links between resources, exposed by the Servicer Relationship API), and the scope of this surface is the compute.googleapis.com/Instance table. A relationship is an entity with its own lifecycle and its own column set; mixing it into the resource's table would put two entities in one. |
| field | `relatedAssets status nuance` | Documented as DEPRECATED: 'The server will never generate responses with this field.' Present in the Asset message but must not be generated. |

## `gcp/compute-instances-rest` — 3 item(ns)

Spec: [`specs/gcp/compute-instances-rest.schema.json`](../specs/gcp/compute-instances-rest.schema.json)

| kind | item | declared reason |
|---|---|---|
| field | `enum constants (all top-level enums except the ones listed in the .md)` | The instances.get page prints the type 'enum' but does not enumerate the constants in the field table. |
| field | `per-field Required. marking` | The page marks no field as Required.; only 'Output only.' / 'Input only.' annotations are documented. |
| field | `all nested fields not transcribed in the .md (disks[].initializeParams.*, networkInterfaces[].accessConfigs.*, scheduling.*, resourceStatus.upcomingMaintenance.*, resourceStatus.physicalHostTopology.*)` | RECLASSIFIED on 2026-10-15: it stops being 'missing transcription' and becomes MODEL WORK. The source publishes the children (disks[].initializeParams.*, networkInterfaces[].accessConfigs[], and the like) and they can be transcribed today. What prevents it is the STATE: the renderer emits 'disks[]' and 'guestAccelerators[]' as EMPTY lists ([]) -- without the initializeParams, without the accessConfigs -- because the model does not carry those values. As in the SCC case, declaring the columns without emitting them would make the golden test flag it, and emitting them requires modeling the disk and network parameters of each instance. It is a decision about what the simulator represents, not a missing reading. |

## `gcp/monitoring-alert-policies` — 3 item(ns)

Spec: [`specs/gcp/monitoring-alert-policies.schema.json`](../specs/gcp/monitoring-alert-policies.schema.json)

| kind | item | declared reason |
|---|---|---|
| field | `alertPolicies[].userLabels.resource_uuid` | Cross-plane join key that the old artifact put in the userLabels map (schema-valid, because the map accepts user keys, and not a canonical key). The new artifact emits no synthetic join at all. |
| field | `alertPolicies[].conditions[].conditionAbsent.duration value` | The field and the format are published; the value '600s' is the consumer's own lookback window, cited from its code and not from a Google page. Recorded as unproven. |
| field | `alertPolicies[].resourceUuid` | Cross-plane join key that the old renderer emitted and that NONE of the six official contracts declares (zero occurrences in the complete documents). Recorded here because the claim also holds for this surface: the auditor has to flag the field if it shows up. See docs/CONTRATO-APIS-GCP.md for the risk per transport. |

## `gcp/monitoring-metric-descriptors` — 1 item(ns)

Spec: [`specs/gcp/monitoring-metric-descriptors.schema.json`](../specs/gcp/monitoring-metric-descriptors.schema.json)

| kind | item | declared reason |
|---|---|---|
| field | `metricDescriptors[].resourceUuid` | Cross-plane join key that the old renderer emitted and that NONE of the six official contracts declares (zero occurrences in the complete documents). Recorded here because the claim also holds for this surface: the auditor has to flag the field if it shows up. See docs/CONTRATO-APIS-GCP.md for the risk per transport. |

## `gcp/monitoring-time-series` — 6 item(ns)

Spec: [`specs/gcp/monitoring-time-series.schema.json`](../specs/gcp/monitoring-time-series.schema.json)

| kind | item | declared reason |
|---|---|---|
| field | `timeSeries[].resource.labels.resourcePath` | Cross-plane join key emitted by the old artifact. The 'labels' map accepts the key, but the contract says the labels are the ones DECLARED in the descriptor of the monitored type, and 'resourcePath' is in neither gce_instance nor cloudsql_database. |
| field | `timeSeries[].resource.labels.resourceUuid` | Same: a join key, not declared among the type's labels. |
| field | `labels condicionais ao tipo monitorado (instance_id, zone, database_id, region)` | The catalog publishes the labels PER TYPE: gce_instance has project_id/instance_id/zone and cloudsql_database has project_id/database_id/region. They are emitted, and the CONDITIONALITY is expressed through named sets (gce_instance_labels, cloudsql_database_labels) instead of prose: no record carries all five, and a set per type is what lets each one be checked without requiring the union on a single line. |
| field | `timeSeries[].metric.type value shape` | The published namespace is used (compute.googleapis.com / cloudsql.googleapis.com) and the last segment is the state's metric name. The short name could not be verified in the consulted sources -- declared unproven instead of asserted non-existent. |
| field | `timeSeries[].resourceUuid` | Cross-plane join key that the old renderer emitted and that NONE of the six official contracts declares (zero occurrences in the complete documents). Recorded here because the claim also holds for this surface: the auditor has to flag the field if it shows up. See docs/CONTRATO-APIS-GCP.md for the risk per transport. |
| topic | `labels condicionais ao tipo monitorado (instance_id, zone, database_id, region)` | The catalog publishes the labels PER TYPE: gce_instance has project_id/instance_id/zone and cloudsql_database has project_id/database_id/region. They are emitted, and the CONDITIONALITY is expressed through named sets (gce_instance_labels, cloudsql_database_labels) instead of prose: no record carries all five, and a set per type is what lets each one be checked without requiring the union on a single line. |

## `gcp/recommender-insights` — 3 item(ns)

Spec: [`specs/gcp/recommender-insights.schema.json`](../specs/gcp/recommender-insights.schema.json)

| kind | item | declared reason |
|---|---|---|
| field | `insights[].resourceUuid` | Cross-plane join key emitted by the old artifact; the Insight contract does NOT declare it. |
| field | `insights[].name value shape` | Same as the recommendation's: the value uses the target project with 'locations/global', and the real location varies. |
| field | `insights[].resourceUuid` | Cross-plane join key that the old renderer emitted and that NONE of the six official contracts declares (zero occurrences in the complete documents). Recorded here because the claim also holds for this surface: the auditor has to flag the field if it shows up. See docs/CONTRATO-APIS-GCP.md for the risk per transport. |

## `gcp/recommender-recommendations` — 3 item(ns)

Spec: [`specs/gcp/recommender-recommendations.schema.json`](../specs/gcp/recommender-recommendations.schema.json)

| kind | item | declared reason |
|---|---|---|
| field | `recommendations[].resourceUuid` | Cross-plane join key emitted by the old artifact; the Recommendation contract does NOT declare it. |
| field | `recommendations[].name value shape` | The SHAPE is confirmed in the machine contract: the Recommender's discovery v1 describes the field as 'Recommendation resource name, e.g. projects/[PROJECT_NUMBER]/locations/[LOCATION]/recommenders/[RECOMMENDER_ID]/recommendations/[RECOMMENDATION_ID]' -- exactly what the artifact emits. What the reading of 2026-10-15 adds is a NEGATION: the `parent` parameter of the list method says that 'LOCATION here refers to GCP Locations' (https://cloud.google.com/about/locations/) and sends the reader to the catalog of recommenders, without asserting that a recommendation's location is always `global`. `global` IS a valid GCP location -- so the emitted value is not invalid -- but it is a choice within a published domain, not a value the source imposes. That is why the field stays under audit: closing it would require the list of recommenders per location, which is a second source. |
| field | `recommendations[].resourceUuid` | Cross-plane join key that the old renderer emitted and that NONE of the six official contracts declares (zero occurrences in the complete documents). Recorded here because the claim also holds for this surface: the auditor has to flag the field if it shows up. See docs/CONTRATO-APIS-GCP.md for the risk per transport. |

## `gcp/scc-findings` — 3 item(ns)

Spec: [`specs/gcp/scc-findings.schema.json`](../specs/gcp/scc-findings.schema.json)

| kind | item | declared reason |
|---|---|---|
| field | `chaves de 'sourceProperties' (Explanation, Recommendation)` | The contract states that the keys of that map are managed by the SOURCE, and does not publish the list of Security Health Analytics keys: the two emitted keys have no official enumeration found. That is why it is a TOPIC record and not a field name -- the keys ARE inside a field that the contract defines (the map), and what is missing is the proof that they are the canonical ones. Registering the path as a field name would be saying that it does not belong to the format, and it does belong: the map accepts it. |
| field | `listFindingsResults[].resourceUuid` | Cross-plane join key that the old renderer emitted and that NONE of the six official contracts declares (zero occurrences in the complete documents). Recorded here because the claim also holds for this surface: the auditor has to flag the field if it shows up. See docs/CONTRATO-APIS-GCP.md for the risk per transport. |
| topic | `chaves de 'sourceProperties' (Explanation, Recommendation)` | The contract states that the keys of that map are managed by the SOURCE, and does not publish the list of Security Health Analytics keys: the two emitted keys have no official enumeration found. That is why it is a TOPIC record and not a field name -- the keys ARE inside a field that the contract defines (the map), and what is missing is the proof that they are the canonical ones. Registering the path as a field name would be saying that it does not belong to the format, and it does belong: the map accepts it. |

## `gcp/scc-sources` — 1 item(ns)

Spec: [`specs/gcp/scc-sources.schema.json`](../specs/gcp/scc-sources.schema.json)

| kind | item | declared reason |
|---|---|---|
| field | `sources[].resourceUuid` | Cross-plane join key that the old renderer emitted and that NONE of the six official contracts declares (zero occurrences in the complete documents). Recorded here because the claim also holds for this surface: the auditor has to flag the field if it shows up. See docs/CONTRATO-APIS-GCP.md for the risk per transport. |

## `gcp/security-command-center-findings-bigquery` — 7 item(ns)

Spec: [`specs/gcp/security-command-center-findings-bigquery.schema.json`](../specs/gcp/security-command-center-findings-bigquery.schema.json)

| kind | item | declared reason |
|---|---|---|
| field | `BigQuery types of the 6 findings-table columns` | Neither the continuous nor the bulk export page declares column types (STRING/RECORD/TIMESTAMP/...). Only names and descriptions are published. |
| field | `structure of the findings table 'resource' column` | The export page says 'see the API reference for the Resource object', but no reachable SCC REST page for that object was found: reference/rest/v1/Resource, reference/rest/v1/Asset and reference/rest/v1/organizations.assets all returned HTTP 404 on 2026-10-14. |
| field | `relationship between the 'resource' column and finding.resourceName / SecurityCenterProperties` | No official page obtained asserts this relationship. |
| field | `inner fields of every Finding sub-object (indicator.*, vulnerability.*, access.*, compliance.*, mitreAttack.*, ...)` | RECLASSIFIED on 2026-10-15: it stops being 'missing transcription' and becomes MODEL WORK. The 67 inner fields exist and were read in the Security Center's discovery v1 (finding.vulnerability 35, finding.access 12, finding.indicator 7, finding.mitreAttack 5, finding.exfiltration 5, finding.securityMarks 3) -- the source publishes them, and the field can be transcribed today. What prevents it is the STATE: the renderer emits 'finding.indicator', 'finding.vulnerability' and 'finding.access' as EMPTY objects ({}), because the NativeFinding model does not carry any of those values. Declaring the 67 columns without emitting them would make the golden test flag it (it requires declared column == emitted column), and emitting them requires first modeling vulnerability, access, indicator and MITRE in the state -- which is a product decision about what the simulator represents, not an evidence task. |
| field | `file format, compression, encoding, delimiter, header, bucket path, partitioning, manifest` | Delivery is a BigQuery table; no intermediate file or manifest is documented. |
| field | `dataset name and location` | The dataset is created by the user; the documentation fixes neither name nor region. |
| field | `which API version (v1 or v2) feeds the BigQuery findings table` | The export documentation does not state the API version. v2 documents a reduced Finding object, and the export pages do not cite it. |

## `gcp/vpc-flow-logs-bigquery` — 6 item(ns)

Spec: [`specs/gcp/vpc-flow-logs-bigquery.schema.json`](../specs/gcp/vpc-flow-logs-bigquery.schema.json)

| kind | item | declared reason |
|---|---|---|
| field | `direct VPC Flow Logs -> BigQuery export mechanism` | No official page describes a VPC-Flow-Logs-specific sink or export to BigQuery. The official destination is Cloud Logging; the BigQuery path is a linked dataset that queries data 'without exporting that data to BigQuery'. |
| field | `BigQuery column names and types of the linked dataset virtual view (_AllLogs)` | https://cloud.google.com/logging/docs/analyze/query-linked-dataset documents the view->virtual-view mapping and the example name _AllLogs but publishes no column list or types. |
| field | `file format, compression, encoding, delimiter, header` | No intermediate file exists on this path; the linked dataset is a read-only pointer. Nothing documented. |
| field | `delivery path / partitioning / shards` | Not documented for this path. |
| field | `manifest` | Not documented for this path. |
| field | `name of the specific table/view holding VPC flow logs` | Documentation cites _AllLogs only as an example log view name of a bucket; it never states that flow logs land there. |

## `aws/s3-list-buckets` — 3 item(ns)


Spec: [`specs/aws/s3-list-buckets.schema.json`](../specs/aws/s3-list-buckets.schema.json)


| kind | item | declared reason |
|---|---|---|
| topic | `Order of the elements inside ListAllMyBucketsResult` | The Response Syntax shows <Buckets>, <Owner>, <ContinuationToken>, <Prefix> in that order, but the response is XML and the page does not promise an ordering. The artifact sorts the bucket list by name, which is generator determinism and not a statement about the order the service returns. |
| topic | `Ordering of Buckets within the array` | None of the five sample responses of the page is in alphabetical order and the page does not declare an ordering. The ordering by name here is a determinism choice, declared in the _provenance.json of each artifact. |
| topic | `timestamp representation of CreationDate` | The page publishes the type as 'Timestamp' without fixing the textual form. The example uses '2019-12-11T23:32:47+00:00'. The state emits ISO-8601 with a UTC offset, which is the form of the official example, but AWS does not promise that it is the only accepted representation. |

## `aws/s3-get-bucket-acl` — 3 item(ns)


Spec: [`specs/aws/s3-get-bucket-acl.schema.json`](../specs/aws/s3-get-bucket-acl.schema.json)


| kind | item | declared reason |
|---|---|---|
| topic | `Order of the elements inside AccessControlPolicy` | The Response Syntax shows <Owner> before <AccessControlList> and the response is XML, but the page does not promise an ordering. The artifact sorts the grants by (Type, URI, ID, Permission), which is generator determinism and not a statement about the service's order. |
| topic | `JSON property names/schema for GetBucketAcl` | It is XML that documents it. No official JSON mapping is published for this action, and therefore the artifact is JSON with the XML ELEMENT names -- a serialization divergence, not a contract one. |
| topic | `VersionId request parameter` | The page does not publish VersionId among this action's parameters, and the Request Syntax shows only Bucket and x-amz-expected-bucket-owner. The parameter exists in other bucket actions, but not in this one, so it does not enter the artifact. |

## `aws/s3-get-bucket-policy` — 4 item(ns)


Spec: [`specs/aws/s3-get-bucket-policy.schema.json`](../specs/aws/s3-get-bucket-policy.schema.json)


| kind | item | declared reason |
|---|---|---|
| topic | `Condition element of a policy statement` | The policy language accepts Condition, and the action's example response shows NONE. The state does not generate a condition, so the member does not enter the artifact: a name that this surface's evidence does not show would be an invented contract. It enters the state if the source starts publishing it. |
| topic | `NotPrincipal, NotAction and NotResource` | They are negated variants accepted by the policy language and do not appear in the example response. The state does not generate them and they do not enter the artifact. |
| topic | `Type qualifier inside Principal` | The example response shows 'Principal': {'AWS': [...]} -- an object with a principal TYPE key. The state flattens the content into a list of strings and does not model the key (AWS, Service, Federated). A consumer that needs the principal's type does not find it in the artifact, and the reason is in this column. |
| topic | `Return shape when the bucket has no policy` | The action signals a bucket without policy with the NoSuchBucketPolicy error (404), but the Response Elements list marks Policy as not required and the state does not model error codes. The artifact represents the absence as a null Policy, which is the reading of the published type, and not as an error envelope. |

## `aws/s3-get-public-access-block` — 4 item(ns)


Spec: [`specs/aws/s3-get-public-access-block.schema.json`](../specs/aws/s3-get-public-access-block.schema.json)


| kind | item | declared reason |
|---|---|---|
| topic | `Boolean representation of the four members` | The example response writes TRUE and FALSE, which is the boolean spelling of XML. The published type is 'Boolean' without fixing the textual representation. The artifact emits true/false, which is the corresponding boolean in JSON, and the conversion is declared in this spec. |
| topic | `Account-level PublicAccessBlock effect on these results` | The page states that in the evaluation S3 uses the MOST RESTRICTIVE combination between the bucket's block and the account's. The state does not model the account-level block, so the effective value of the combination is not in the artifact: what is there are the four facts of the bucket, and what the page says this operation returns. |
| topic | `JSON property names/schema for GetPublicAccessBlock` | It is XML that documents it. The artifact is JSON with the XML element names -- a serialization divergence, not a contract one. |
| topic | `RegionalAccessBlockConfiguration (Region, RegionPrefix, BlockPublicAcls, BlockPublicPolicy, IgnorePublicAcls, RestrictPublicBuckets)` | ZERO occurrences in API_GetPublicAccessBlock.html AND in API_PutPublicAccessBlock.html (measured on 2026-10-18). The names come from the shape the SDKs publish, and not from a page of the consulted reference. Declared as unproven instead of declared non-existent: the set is in the artifact, separated from the response, and with the reason for this entry in the _provenance of each response. |

## `aws/ec2-describe-security-groups` — 4 item(ns)


Spec: [`specs/aws/ec2-describe-security-groups.schema.json`](../specs/aws/ec2-describe-security-groups.schema.json)


| kind | item | declared reason |
|---|---|---|
| field | `securityGroupRuleId` | The official DescribeSecurityGroups Sample Response brings <securityGroupRuleId>sgr-abcdefghi01234560</securityGroupRuleId> inside <groups>, but the UserIdGroupPair page publishes seven members and this is NOT one of them. The example shows a member that the type page does not document, so it stays forbidden in the artifact: emitting a name the source does not document is inventing a contract. If AWS starts documenting it, it enters as its own column. |
| topic | `JSON property names/schema for DescribeSecurityGroups` | Only XML is documented; no JSON property list nor JSON example is published for this action. The same limit registered in aws/ec2-describe-instances, and for the same reason: the EC2 Reference publishes the member name in XML/Query form and the JSON artifact uses the mapping of the same contract. |
| topic | `enumeração fechada dos valores de ipProtocol` | The IpPermission page exemplifies the names 'tcp', 'udp', 'icmp' and 'icmpv6', says that a protocol NUMBER is also accepted and that '-1' means all protocols, but does not publish a closed list. The accepted value is name-or-number-or-'-1'; a closed set would be a claim the documentation does not make. |
| topic | `vínculo VPC <-> security group do estate` | The API publishes vpcId in SecurityGroup, but the canonical model does not carry the relationship: the estate's 'vpc' resources and 'security_group' resources live in different regions and no (account, region) pair has both. The vpcId written here comes from the network SEGMENT of the same (account, region), which is the model's VPC at that scope -- a declared derivation, not a fact read from AWS. The pending verification is the VPC<->SG relationship of a real account. |

## `aws/iam-get-account-password-policy` — 4 item(ns)


Spec: [`specs/aws/iam-get-account-password-policy.schema.json`](../specs/aws/iam-get-account-password-policy.schema.json)


| kind | item | declared reason |
|---|---|---|
| topic | `Boolean representation of the seven boolean members` | The Sample Response writes true and false, which is the boolean spelling of JSON, inside an XML envelope. The published type is 'Boolean' without fixing the textual representation. The artifact emits true/false, which is the corresponding boolean, and the conversion is declared in this spec. |
| topic | `Whether a member can be absent from the response` | The ten members are Required: No and the page does not declare a presence condition. The Sample Response brings all ten. The artifact does NOT emit an absent member: it emits the value, and for MaxPasswordAge -- the only one whose absence the page itself describes -- the state without expiration is published as a null MaxPasswordAge, with ExpirePasswords false derived from that null. |
| topic | `Which account each response belongs to` | Neither PasswordPolicy nor the Sample Response carries the account id, and the state does not model the request that triggered the read. The per-account labelling is the ARTIFACT's and is declared in the _provenance of each response. |
| topic | `JSON schema for the IAM JSON protocol` | The consulted documentation SHOWS the response in XML. IAM also accepts JSON, but no page here publishes the JSON schema, so the member-name conversion in the artifact is the XML->JSON conversion, not a verified JSON contract. |

## `gcp/observability-partial` — 3 item(ns)


Spec: [`specs/gcp/observability-partial.schema.json`](../specs/gcp/observability-partial.schema.json)


| kind | item | declared reason |
|---|---|---|
| topic | `request.name accepts '-' as a wildcard` | The use of the '-' wildcard for multi-project scope is documented in Googleapis practice, but the consulted method page describes the field as 'The project on which to execute the query, formatted as projects/{PROJECT_ID}' without declaring the wildcard. Declared here as unproven instead of asserted; the artifact does NOT emit '-', because '-' is a REQUEST and never enters the body of a response. |
| topic | `Whether a resposta parcial e indistinguivel de uma completa sem o inventario irmao` | ListTimeSeriesResponse declares no field stating how many items the scope had. An empty nextPageToken means 'last page', not 'all the data'. That is why missing.json exists: the artifact's honesty cannot depend on a field the contract does not publish. |
| topic | `timeSeries[].metric.type value shape` | Same declaration as the parent surface gcp/monitoring-time-series: the public namespace is used and the last segment is the state's metric name, which could not be verified in the consulted sources. |

## `aws/iam-get-credential-report` — 3 item(ns)


Spec: [`specs/aws/iam-get-credential-report.schema.json`](../specs/aws/iam-get-credential-report.schema.json)


| kind | item | declared reason |
|---|---|---|
| topic | `The LITERAL in the 'user' column of the root account row (a VALUE, not the column)` | Neither API_GetCredentialReport.html nor the IAM User Guide's column page (credential-reports.html), both read on 2026-10-18, declare the value of that column in the root account row. The report brings a row for the root, and without it the root-account-mfa-enabled rule would have no row at all to read the root's MFA from -- that is why the artifact emits the row. The LITERAL goes marked as unproven and the reason is in the _provenance: a consumer that compares the 'user' column against that string needs to know that it was not checked against an official page. |
| topic | `CSV quoting rules for a value containing the delimiter` | Neither of the two pages publishes the report's CSV escape rule (quotes, double escape, delimiter). The artifact emits a plain CSV with a comma delimiter and does NOT work around values: all the values here come from a vocabulary with no comma and no quotes, so no field needs escaping. A user with a comma in the name would change the discussion, and the state has none. |
| topic | `Whether the CSV declares a Content-Type line or a BOM` | The action page says ReportFormat = 'text/csv' and that Content is Base64; it does not declare a BOM nor line breaks. The artifact writes UTF-8 without BOM and with \n, and declares that in the _provenance. |

## `gcp/compute-firewalls` — 6 item(ns)


Spec: [`specs/gcp/compute-firewalls.schema.json`]](../specs/gcp/compute-firewalls.schema.json)


| kind | item | declared reason |
|---|---|---|
| topic | `allowed[].IPProtocol = "all"` | The Firewall page says that IPProtocol 'can either be one of the following well known protocol strings (tcp, udp, icmp, esp, ah, ipip, sctp) or the IP protocol number' -- and 'all' is NOT in that list. But 'all' is the value the API actually returns: the official output of 'gcloud compute firewall-rules list' from a freshly created project brings default-allow-internal with the ALLOW column equal to 'all', and the VPC firewall guide says that 'If you omit both protocols and ports, the firewall rule is applicable for all traffic on any protocol and any destination port' and offers 'Allow all' at creation. The value is real in the response and it is on this surface precisely because of that; the divergence is between the field's prose and the API, and it is recorded here so that nobody reads the prose as a closed list. |
| topic | `JSON property names da resposta de firewalls.list` | GCP publishes the JSON shape of this surface -- and the Compute v1 discovery document is, itself, the machine source that the Firewall page uses to render the properties table. There is no encoding divergence as in AWS (which publishes only XML): here the JSON names ARE the documented ones. |
| topic | `rede VPC global vs. uma rede por regiao no modelo` | On GCP a VPC network is GLOBAL and has subnets in several regions; the only regional member of the pair is subnetworks. The canonical model, on the contrary, gives this estate one network per (project, region) -- segment_id changes with the region, as if it were the AWS VPC. The Firewall.network value written here is the model's real segment_id, so it is a FACT of the model and not a derivation, but it is not the shape GCP produces. The pending verification is the network-VPC<->project relationship of a real project, which only resolves when the model starts carrying one network per project. |
| topic | `nomes de regra pre-populados da rede default como contrato` | The four names (default-allow-internal, default-allow-ssh, default-allow-rdp, default-allow-icmp), the priority 65534 and the protocol:port pairs come from the 'Pre-populated rules in the default network' table of the VPC firewall guide and from the output of 'gcloud compute firewall-rules list' that Google itself publishes in its training material. There is no type page that declares them: they are the state of a freshly created project, not a schema contract. They enter as a DECLARED posture, with the source cited, and not as a column. |
| topic | `as duas regras implicitas de toda rede VPC` | GCP documents that every network has an implicit ingress rule that denies everything and an egress one that allows everything, both at priority 65535. They are NOT resources and firewalls.list does not return them, so there is no column for them and the artifact does not carry them. Recorded here because it is the point at which a consumer scanning the list cannot see the rule that protects the network. |
| topic | `membros do objeto FirewallList.warning` | The discovery declares warning as 'Informational warning message' with type object and does NOT publish its members. It comes out {}: an object with no published fields does not become an invented structure. |

## `azure/security-assessments-list` — 10 item(ns)


Spec: [`specs/azure/security-assessments-list.schema.json`]](../specs/azure/security-assessments-list.schema.json)


| kind | item | declared reason |
|---|---|---|
| topic | `valor de 'properties.status.cause' (ex.: 'OffByPolicy')` | The page publishes the TYPE ('string') and the description ('Programmatic code for the cause of the assessment status'), but does not publish a closed domain. The only observable value is the one from the response example ('"cause": "OffByPolicy"', in the NotApplicable assessment). A payload example fixes the SHAPE of the field, not its vocabulary: the member is emitted EMPTY. |
| topic | `membros de 'properties.additionalData'` | The page publishes the type 'object' and the response example shows a 'linkedWorkspaceId'. It does not publish the member list, so there is nothing to enumerate: the member comes out as an EMPTY object, without the invented key. |
| topic | `template de 'properties.links.azurePortalUri'` | The type and the meaning are published ('Link to assessment in Azure Portal'), but no consulted page publishes the URI format nor gives an example. Building a portal URL by rule would be inventing the transport. |
| topic | `'properties.metadata.policyDefinitionId' na avaliacao embutida` | The page publishes the member and describes it as 'Azure resource ID of the policy definition that turns this assessment calculation on', but does not exemplify the value and the response example does not bring 'metadata'. An ARM policy definition id would be an id that no consulted page publishes, so the member comes out empty. |
| topic | `categorias, ameacas, esforco de implementacao e impacto por avaliacao` | The DOMAINS are published ('categories', 'threats', 'implementationEffort', 'userImpact' have the enumeration tables), but the page does not state which value EACH assessment belongs to, and the canonical state does not model the Defender's assessment catalog. Choosing a value would be inventing the association; the members come out as an empty collection/string. |
| topic | `'properties.partnersData.partnerName', 'properties.metadata.partnerData.partnerName' e '...productName'` | The three members have published type and description, but the state has no partner: no assessment of this state is a third party's. They come out empty instead of receiving an invented company name. |
| topic | `'properties.partnersData.secret' e 'properties.metadata.partnerData.secret'` | The page marks both as 'write only' ('Secret to authenticate the partner - write only'). A member explicitly of WRITE does not belong to a read response, so it does not enter 'sets': emitting it would be publishing a field that the documentation itself says does not come back. |
| topic | `variantes OnPremise de 'properties.resourceDetails'` | The page publishes three variants (AzureResourceDetails, OnPremiseResourceDetails, OnPremiseSqlResourceDetails) and the state produces only the Azure one: the two OnPremise ones describe machines under a Log Analytics agent, which this repository does not model. The choice of variant is a FACT of the assessed resource, and the assessed resource here is a VNet on Azure. |
| topic | `pagina de 'nextLink'` | The response is a page of a collection and the page does not publish the page size nor an example cursor. The envelope is delivered as a single page (all the assessments of the scope fit in it), with the member present and empty. |
| topic | `escopo por grupo de gerenciamento` | The page publishes that 'scope' can be a subscription OR a management group. The FinOps consumer queries the subscription, and the canonical state does not model an Azure management group; an envelope per group would be a cut the model does not have. |

## `azure/deployment-stacks-what-if` — 4 item(ns)


Spec: [`specs/azure/deployment-stacks-what-if.schema.json`]](../specs/azure/deployment-stacks-what-if.schema.json)


| kind | item | declared reason |
|---|---|---|
| topic | `properties.changes.deploymentScopeChange and denySettingsChange` | DeploymentStacksWhatIfChange publishes both members, but the simulator's estate models neither a stack scope change nor deny settings. They are not emitted rather than filled with a placeholder. |
| topic | `the full DeploymentStacksWhatIfResult property set (parameters, template, templateLink, validationLevel, diagnostics, retentionInterval, provisioningState, ...)` | The REST reference publishes them as part of the result, but the simulator only models the resource changes this phase needs. Omitting them is intentional; inventing their values would be worse than an honest subset. |
| topic | `resourceConfigurationChanges.delta element type` | The page publishes the delta member and describes DeploymentStacksWhatIfPropertyChange, but does not print an explicit type link for delta. The fields transcribed here are the ones the property-change definition publishes; the container type is not asserted. |
| topic | `the concrete spelling of delta[].path for a tag key` | The property-change definition publishes path as a string and the examples shown are for resource properties, not for a tag key. The simulator emits tags.<key> as a scenario path; the documentation consulted does not print an example for a tag map key, so tags.<key> is not asserted as the published spelling. |

## `gcp/infrastructure-manager-resource-drift` — 4 item(ns)


Spec: [`specs/gcp/infrastructure-manager-resource-drift.schema.json`]](../specs/gcp/infrastructure-manager-resource-drift.schema.json)


| kind | item | declared reason |
|---|---|---|
| field | `concrete shape of before/after for a given Terraform type` | The REST reference publishes before/after as a Value (arbitrary JSON). It does not publish a per-resource-type schema, so the simulator may emit only values derived from the estate's own model and must not infer a nested shape from a provider example. |
| field | `semantics of before/after relative to desired state` | The page describes the values as 'before/after the actions' without stating which side is the desired state for a drift preview. The direction must be measured on a real preview before a consumer maps it to expected/actual. |
| topic | `the resourceDrifts[]/nextPageToken/unreachable[] envelope` | The envelope belongs to the list method, not to the ResourceDrift item; it is documented at the list method page and is intentionally outside this item schema. |
| topic | `the grammar of propertyDrifts[].path for a map key` | The REST reference publishes `path` as the path of the property drift, but does not publish the path grammar for maps. The simulator emits `labels.<key>` as a scenario path derived from the estate; that spelling is not asserted by the GCP documentation and must not be read as a published contract. |

## `gcp/container-clusters` — 22 item(ns)


Spec: [`specs/gcp/container-clusters.schema.json`]](../specs/gcp/container-clusters.schema.json)


| kind | item | declared reason |
|---|---|---|
| field | `currentMasterVersion` | Output only. The current software version of the master endpoint. The estate does not model a Kubernetes version: the cluster's sku_id names the NODE SKU it bills, which is not the master's version. Publishing one would be a version the estate never asserted. |
| field | `currentNodeVersion` | Output only. The current software version of the node software. The estate bills the cluster under a node SKU and models no Kubernetes release for it. |
| field | `nodePools` | The node pools associated with this cluster. The estate models one row per cluster and no pool inside it; a pool would be a resource the estate does not carry. |
| field | `nodeConfig` | The node configuration for this cluster. The estate carries the cluster's billed SKU, not a node configuration, and the two are not the same shape. |
| field | `network` | The name of the Google Compute Engine network to which the cluster is connected. The estate models no VPC for a cluster, so there is no network name to publish. |
| field | `subnetwork` | The VPC-native network id the cluster uses. The estate models no subnetwork for a cluster. |
| field | `status` | Output only. The current status of this cluster. The estate is a billing baseline, not a control-plane state machine: it asserts that the cluster is billed for, not that it is RUNNING. |
| field | `createTime` | Output only. The time the cluster was created, in RFC3339 text format. The estate asserts no creation time for a resource, and the simulator's clock would be a fabricated one. |
| field | `selfLink` | Output only. Server-defined URL for the resource. The estate mints a uuid, not a GCP server-defined URL, so any path published here would be a path the provider never defined. |
| field | `id` | Output only. Unique id for the cluster. The estate's uuid is the estate's own identifier and is not the provider's numeric id. |
| field | `zone` | Output only, and deprecated in favour of 'location'. The estate records a region and nothing finer, so there is no zone to publish; 'location' carries the region. |
| field | `clusterIpv4Cidr` | The IPv4 range for the cluster's nodes. The estate models no address plan for a cluster. |
| field | `masterAuth.clientKey` | Output only. Base64-encoded private key used by clients to authenticate to the cluster endpoint. It is a PRIVATE key: the simulator derives one to sign the CA certificate and never publishes it. Publishing it here would publish a secret the contract does not carry. |
| field | `masterAuth.clientCertificate` | Output only. Base64-encoded public certificate used by clients to authenticate to the cluster endpoint, issued only if clientCertificateConfig is set. The estate models no client certificate configuration. |
| field | `masterAuth.username` | The username to use for HTTP basic authentication to the master endpoint. The estate models no basic-authentication account for a cluster, and the page itself marks basic authentication as deprecated. |
| field | `masterAuth.password` | Deprecated on the page. The estate models no password for a cluster, and a published password would be a credential nobody published. |
| field | `masterAuth.clientCertificateConfig` | Configuration for client certificate authentication on the cluster. The estate models no client certificate configuration. |
| topic | `the remaining published members of Cluster that the estate does not model (secretManagerConfig, alphaClusterFeatureGates, nodePoolAutoConfig, monitoringService, userManagedKeysConfig, description, nodeIpv4CidrSize, masterAuthorizedNetworksConfig, costManagementConfig, maintenancePolicy, networkPolicy, nodePoolDefaults, legacyAbac, secretSyncConfig, addonsConfig, podAutoscaling, locations, meshCertificates, servicesIpv4Cidr, etag, tpuIpv4CidrBlock, gkeAutoUpgradeConfig, satisfiesPzi, managedMachineLearningDiagnosticsConfig, rbacBindingConfig, compliancePostureConfig, workloadIdentityConfig, enterpriseConfig, scheduleUpgradeConfig, resourceUsageExportConfig, controlPlaneEgress, rollbackSafeUpgrade, releaseChannel, currentEmulatedVersion, controlPlaneEndpointsConfig, initialNodeCount, databaseEncryption, labelFingerprint, instanceGroupUrls, statusMessage, verticalPodAutoscaling, anonymousAuthenticationConfig, fleet, conditions, enableKubernetesAlpha, parentProductConfig, resourceLabels, monitoringConfig, networkConfig, privateClusterConfig, loggingConfig, shieldedNodes, securityPostureConfig, binaryAuthorization, expireTime, identityServiceConfig, enableK8sBetaApis, confidentialNodes, ipAllocationPolicy, notificationConfig, initialClusterVersion, enableTpu, managedOpentelemetryConfig, satisfiesPzs, defaultMaxPodsConstraint, loggingService, currentNodeCount, autopilot, autoscaling, authenticatorGroupsConfig, nodeCreationConfig)` | The API publishes these members and the estate models none of them: a cluster row carries a name, a region, a billed SKU and tags, and nothing else. They are listed by name so that no published member is silently omitted from the accounting, and they stay out of the artifact because publishing them would mean inventing the value the estate does not carry. |
| topic | `the endpoint as an IP address (the published wording of the member)` | The field table publishes the endpoint as 'Output only. The IP address of this cluster's master endpoint', and the estate carries no address for a cluster. The simulator publishes an HTTPS URL derived from the resource's uuid instead -- the form the same paragraph shows the endpoint being used at ('https://username:password@endpoint/'). The divergence is declared, not silent: a consumer that needs an IP must know the simulator does not publish one. |
| topic | `the zonal (projects.zones.clusters.list) and aggregated (projects.aggregated.clusters.list) variants of the same list` | Both exist in the same API version and return the same ListClustersResponse. Only the regional projects.locations.clusters.list is served by the emulator; the other two are a scope limit of this surface, not a claim that they do not exist. |
| topic | `the deprecated query parameters 'projectId' and 'zone'` | The list method publishes both as deprecated and replaced by the 'parent' path parameter. The route takes the parent form only, so a client sending the deprecated spelling is answered by the same parent path instead. |
| topic | `the reachability of the published endpoint` | The endpoint names the cluster's master endpoint and is derived from the resource's uuid; the emulator hosts no Kubernetes API server behind it. A client that dials it is not reaching a cluster control plane. |
