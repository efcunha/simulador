# Official contract of the GCP APIs that `gcp_rest_fixtures` emulates (G11)

> Language: **English** | [Português](CONTRATO-APIS-GCP.md)

> **This document is called CONTRATO-APIS-GCP.md and covers the Google Cloud APIs.** The
> contract of the **AWS OCSF** (collected for item E5) is in a section of its own at the end of
> the file, with the indication that it belongs to another provider — the file name did not follow
> the second use.

Survey executed on **2026-10-14**, by read-only reading. It exists so that the audit of the
families does not have to be redone: each line brings the **source URL** and the **excerpt** that
supports it. The renderer in question (`render/gcp_rest_fixtures.py`, 590 lines, 13 fixtures)
states in a comment that the envelopes are *"best-effort official-shaped"* with `TODO-verificar #7`
in almost every field — this document replaces memory with the source.

## The six families, and the state of each one

| # | Family | Method | Fixtures | Spec written | Checks out? |
|---|---|---|---|---|---|
| 1 | Cloud Asset Inventory | `searchAllResources` | `cai_search_all_resources.json` | **yes** (`gcp/asset-search-all-resources`) | two-level audit; `resourceUuid` outside the new artifact |
| 1b | Cloud Asset Inventory | `searchAllIamPolicies` | `cai_search_all_iam_policies.json` | no | envelope and fields check out; `resourceUuid` one extra |
| 1c | Cloud Asset Inventory | `analyzeIamPolicy` | `cai_analyze_iam_policy.json` | no | minimal body, not audited |
| 2 | Security Command Center | `sources.list` | `scc_sources.json` | no | fields check out |
| 2b | Security Command Center | `findings.list` | `scc_findings.json` | no | envelope checks out; `resourceUuid` one extra, and a synthetic `resourceName` |
| 3 | Recommender | `recommendations.list` | `recommender_recommendations.json` | no | envelope checks out; `resourceUuid` one extra; `projects/-` in the body |
| 3b | Recommender | `insights.list` | `recommender_insights.json` | no | same |
| 4 | Cloud Billing Catalog | `services.list` | `catalog_services.json` | no | **no unknown field** |
| 4b | Cloud Billing Catalog | `services.skus.list` | `catalog_skus.json` | no | **no unknown field** |
| 5 | Cloud Monitoring | `timeSeries.list` | `monitoring_time_series.json` | no | fields check out; 2 unofficial labels |
| 5b | Cloud Monitoring | `metricDescriptors.list` | `monitoring_metric_descriptors.json` | no | fields check out |
| 5c | Cloud Monitoring | `alertPolicies.list` | `monitoring_alert_policies.json` | no | fields check out; join in `userLabels` |
| 6 | Cloud Billing Budgets | `budgets.list` | `budgets.json` | no | **no unknown field** |

**No envelope error was found:** all the ten list field names that the renderer uses
(`results`, `listFindingsResults`, `recommendations`, `insights`, `services`, `skus`, `timeSeries`,
`metricDescriptors`, `alertPolicies`, `budgets`, `sources`) are **correct** in the official
documents. The renderer's problem is not the shape of the envelope — it is the join field it
adds.

## Sources (URL + HTTP + revision)

| Key | URL | HTTP | Revision |
|---|---|---|---|
| CAI | `https://www.googleapis.com/discovery/v1/apis/cloudasset/v1/rest` | 200 | `20261010` |
| SCC | `https://www.googleapis.com/discovery/v1/apis/securitycenter/v1/rest` | 200 | `20261009` |
| REC | `https://www.googleapis.com/discovery/v1/apis/recommender/v1/rest` | 200 | `20261004` |
| CAT | `https://www.googleapis.com/discovery/v1/apis/cloudbilling/v1/rest` | 200 | `20261002` |
| MON | `https://www.googleapis.com/discovery/v1/apis/monitoring/v3/rest` | 200 | `20260924` |
| BUD | **`https://www.googleapis.com/discovery/v1/apis/billingbudgets/v1/rest`** | **404** | — |
| BUD-API | `https://billingbudgets.googleapis.com/$discovery/rest?version=v1` | 200 | `20261011` |
| CAI proto | `https://raw.githubusercontent.com/googleapis/googleapis/master/google/cloud/asset/v1/assets.proto` | 200 | — |
| SCC proto | `https://raw.githubusercontent.com/googleapis/googleapis/master/google/cloud/securitycenter/v1/finding.proto` | 200 | — |
| REC proto | `https://raw.githubusercontent.com/googleapis/googleapis/master/google/cloud/recommender/v1/recommendation.proto` | 200 | — |
| NAMES | `https://docs.cloud.google.com/asset-inventory/docs/asset-names` | 200 | — |
| MONRES | `https://cloud.google.com/monitoring/api/resources` | 200 | — |
| AIP159 | `https://google.aip.dev/159` | 200 | — |
| PROTOJSON | `https://protobuf.dev/programming-guides/json/` | 200 | — |
| PROTO3 | `https://protobuf.dev/programming-guides/proto3/` | 200 | — |
| PYJSON | `https://googleapis.dev/python/protobuf/latest/google/protobuf/json_format.html` | 200 | — |

**Citation notes that were expensive to find:**

* `https://www.googleapis.com/discovery/v1/apis/billingbudgets/v1/rest` **does not exist** (404);
  family 6 is citable only via `https://billingbudgets.googleapis.com/$discovery/rest?version=v1`.
* `https://cloud.google.com/asset-inventory/docs/resource-name-format` **redirects**
  (cross-origin) to `https://docs.cloud.google.com/asset-inventory/docs/asset-names`.
* The `docs.cloud.google.com` pages **do not work for the list methods**: the navigation
  consumes the fetch budget before the field tables. The path that works is the *discovery
  document* (111 KB to 478 KB) and the `.proto` — both machine-readable.

## The main finding: `resourceUuid`

**`resourceUuid` occurs ZERO times in the six complete official documents.** It is not a field of
`ResourceSearchResult`, `IamPolicySearchResult`, `Finding`, `Recommendation`, `Insight` nor
`AlertPolicy`. It is a cross-plane join key that the renderer **invented** — the code itself
calls it *"synthetic cross-plane join key (P2)"*.

| # | Endpoint | Where | Emitted in |
|---|---|---|---|
| 1 | CAI `searchAllResources` | top of the result | `gcp_rest_fixtures.py:119` |
| 2 | CAI `searchAllIamPolicies` | top of the result | `:140` |
| 3 | SCC `findings.list` | top of the finding | `:206` |
| 4 | Recommender `recommendations.list` | top | `:243` |
| 5 | Recommender `insights.list` | top | `:270` |
| 6 | Monitoring `alertPolicies.list` | **already migrated** to `userLabels.resource_uuid` | `:529` |

### The risk, measured against the official documentation

The renderer's own code records, for family 6, the effect that made it migrate the field:

> *"this body is parsed into the CLIENT's own AlertPolicy proto, which declares no top-level
> resourceUuid and rejects the whole response when one is present (measured: ParseDict fails with
> 'has no field named resourceUuid')"*

The official documentation confirms the rule and **delimits the risk**:

* **JSON → proto rejects by default.** `google.protobuf.json_format.ParseDict(js_dict, message,
  ignore_unknown_fields=False, …)` — *"ignore_unknown_fields – If True, do not raise errors for
  unknown fields"*; and the ProtoJSON guide: *"The Protobuf JSON parser should reject unknown fields by
  default but may provide an option to ignore unknown fields in parsing"* and *"Any key validity
  checking should still occur (disallowing unknown fields)"*.
* **Binary gRPC does NOT reject.** The gRPC payload is binary protobuf, and proto3 *"preserve[s]
  unknown fields and include[s] them during parsing and in the serialized output"*. In other words:
  the same body that breaks via `ParseDict` **passes silently** through the gRPC transport — and the
  unknown field is still lost if the client reserializes to JSON (*"Serialize a proto to JSON"* is on
  the list of what discards unknown fields).

**Practical consequence, and this is what changes the decision:** the field is always
**undocumented** (that alone is enough for fidelity), but the effect **depends on the transport**.
Since the consumer uses both paths (`client.py (consumer-module)` builds gRPC clients; the fixtures
are JSON), the removal is correct for fidelity and *potentially* necessary for function — it is not
a guaranteed failure in production. This is stated as such in
`specs/gcp/asset-search-all-resources.schema.json` and in the provenance report of the new
renderer, so as not to trade one imprecision for another.

## Fields with a synthetic value inside a real field (→ `unverified`, not removal)

| Family | Field | Problem | Evidence |
|---|---|---|---|
| CAI | `name` | service always `cloudresourcemanager.googleapis.com` and path `projects/<p>/<type>/<name>`, without `zones/{zone}`/`locations/{loc}` | NAMES publishes the format **per type**: `//compute.googleapis.com/projects/PROJECT_ID/zones/ZONE/instances/INSTANCE`, `//cloudsql.googleapis.com/projects/PROJECT_ID/instances/INSTANCE`, `//container.googleapis.com/projects/PROJECT_ID/locations/LOCATION/clusters/CLUSTER`, `//storage.googleapis.com/BUCKET` |
| CAI | `assetType` | `<tipo_interno>.googleapis.com/Resource` | the proto gives `compute.googleapis.com/Disk` as an example; NAMES publishes `compute.googleapis.com/Instance` |
| SCC | `resourceName` | `//cloudasset.googleapis.com/<uuid>` — pure UUID where a path is expected | the field accepts a client string, but [NAMES] requires `//<serviço>/<path>` |
| SCC | `sourceProperties.Explanation` / `.Recommendation` | free-form keys; **I did not find** an official enumeration | the contract only says the keys are managed by the source |
| SCC | `name`/`parent` source number | synthetic int64 in the **correct shape** | the code itself admits it |
| REC | `name` | `projects/-/…` in the **response body** | AIP-159: *"The resource name in the response must use the canonical name of the resource, with actual parent collection identifiers (instead of - )"* |
| MON | `resource.labels.resourcePath`, `resource.labels.resourceUuid` | they are not **declared** labels for `gce_instance` (project_id/instance_id/zone) nor for `cloudsql_database` (project_id/database_id/region) | MONRES publishes the closed set per type |
| MON | `userLabels.resource_uuid` | schema-valid key, **not canonical** | the contract declares the map and the key rules, not this key |
| MON | `metric.type` | value **not verifiable** in the sources consulted | `metrics_gcp` is rendered by JS (0 occurrences of the strings in the HTML); declare `unverified`, **not** nonexistent |
| CAT | `serviceId`/`skuId`/`name` | correct `services/{id}` format; id derived from the service name | the doc gives `6F81-5844-456A` / `D041-B8A1-6E0B` as an example |
| BUD | `name` | correct format; the contract **does not impose** a format on `budgetId`, so a UUID is acceptable | — |

## What was **not** verified (stated, not omitted)

1. No official enumeration of the `Explanation`/`Recommendation` keys of `sourceProperties`.
2. No official sentence saying literally that gRPC does not fail with an unknown field — the
   conclusion above is the **combination** of two official statements (binary payload +
   preservation of the unknown field), not a single sentence.
3. No official verification of the `metric.type` values.
4. No official verification of the ids `google.compute.instance.MachineTypeRecommender` and
   `...MachineTypeInsight` (the recommenders catalog was not consulted).

---

# OCSF contract of the Security Hub (AWS) — collected for item E5

**This block is from another provider.** It stays here because item E5 came out of the same
session, and the file name did not follow the second use — it is stated at the top so that nobody
looks for OCSF in a document called "APIS-GCP".

## The finding that reorients E5

E5 was written as *"re-specify `aws/security-hub-asff` for `CSV`/`OCSF_JSON`"*. Reading the
current spec, it **already documents** the finding:

> *"ASFF is NOT an available export format. SelectedFields accepts OCSF field paths only, so ASFF
> and the S3 export are two different formats of the same source."*

And the primary source confirms, on the export operation page itself:

> *"Specify the destination bucket and AWS KMS key in the `Destination` parameter, and the output
> format (`CSV` or `OCSF_JSON`)"* — [StartExportJobV2](https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_StartExportJobV2.html), HTTP 200 on 2026-10-14

**Consequence:** the `aws/security-hub-asff` surface **is not wrong** — it describes the findings
in the format that the Security Hub API returns (`AwsSecurityFinding`, 96 columns, 0 unproven).
What D3(c) asks for is not to rewrite it: it is to **add the surface of the format that AWS
exports**, which does not exist. They are two surfaces of the same data, and the current one is
the other half.

## The OCSF inheritance chain (for the export format)

Source: the normative OCSF repository, file by file, HTTP 200 on 2026-10-14.

| Piece | File | What it fixes |
|---|---|---|
| Class | [`events/findings/compliance_finding.json`](https://raw.githubusercontent.com/ocsf/ocsf-schema/main/events/findings/compliance_finding.json) | `uid: 3`, `name: compliance_finding`, `extends: finding`; makes `compliance` **required** and adds `evidences`, `remediation`, `resource`†, `resources` |
| Base | [`events/findings/finding.json`](https://raw.githubusercontent.com/ocsf/ocsf-schema/main/events/findings/finding.json) | `extends: base_event`; makes `finding_info` **required**; declares `activity_id` (1 Create, 2 Update, 3 Close), `status_id` (1 New … 6 Deleted), `confidence_id`, `resources`, `vendor_attributes`, `time`, `start_time`, `end_time`; applies the `incident` profile |
| Object | [`objects/finding_info.json`](https://raw.githubusercontent.com/ocsf/ocsf-schema/main/objects/finding_info.json) | `uid` **required**; `title` recommended; `desc`, `types`, `analytic`, `created_time`, `src_url`, `tags`, `attacks`, `product`… |
| Object | [`objects/compliance.json`](https://raw.githubusercontent.com/ocsf/ocsf-schema/main/objects/compliance.json) | `status_id`: **1 Pass, 2 Warning, 3 Fail**; `control`, `standards`, `requirements`, `checks`, `status`, `status_code`, `desc` |
| Object | [`objects/metadata.json`](https://raw.githubusercontent.com/ocsf/ocsf-schema/main/objects/metadata.json) | `product` **required**, `version` **required** ("the version of the OCSF schema"); `log_name`, `reporter`, `source`, `tenant_uid` recommended |

† `resource` has been `@deprecated` since 1.3.0 with `superseded_by: ["resources"]` — the renderer
must use `resources`, and the singular `resource` **must not** be emitted.

**`version` is mandatory and has to be a RELEASED version.** The `main` branch of the repository
carries `{"version": "1.10.0-dev"}` — a pre-release, which does not serve for a mandatory field of
an artifact. The last released one, verified in the repository's releases API, is **`1.9.0`**
(`tag_name: "1.9.0"`, `prerelease: false`, published on 2026-08-03). The same version check
applies to `metadata.product.version` — which is the version of the **producer**, not of the OCSF.

## What the simulator's state supports projecting

Read from `render/security_hub.py:552-621` (the ASFF mapping, which already projects the same
facts):

| OCSF | Origin in the state |
|---|---|
| `finding_info.uid` | `NativeFinding.finding_id` |
| `finding_info.title` / `.desc` | `title` / `description` |
| `finding_info.types` | `finding.types` |
| `finding_info.created_time` | `raised_on` (as ASFF uses it in `CreatedAt`) |
| `severity_id` | `severity` — **RESOLVED on 2026-10-15**: the OCSF enum was read in `dictionary.json` (tags 1.6.0 and 1.9.0, identical) and the native literal is normalized to the caption (`LOW` → `"Low"`, **2**) |
| `resources[].uid` / `.name` / `.region` | `Resource` of the finding: ARN/uuid, `resource_name`, `region_id` |
| `metadata.product.name` / `.vendor_name` | `finding.product_name` / `company_name` |
| `metadata.version` | **constant `1.9.0`**, and not a value from the state |
| `metadata.log_name` | the export file name, which the surface fixes |
| `status_id` | `finding.status` — ASFF already does the mapping (`_RECORD_STATE: open -> ACTIVE`) |
| `compliance.status_id` / `.control` / `.standards` | **NOT modeled** — the ASFF also emits `Compliance: None`, with the recorded justification that the model carries neither framework nor control |

## What was **not** collected (stated, not omitted)

1. **The complete list of `base_event` attributes** (where `metadata`, `severity_id`, `time`,
   `class_uid`, `category_uid`, `type_uid` live) — it was not read in this execution. *(It looked
   like that file, but `base_event.json` **does not exist** in any tag: the base attributes live in
   the root `dictionary.json`, 258 KB. That is where the `severity_id` enum was found.)*
2. **The class the Security Hub export actually emits.** The natural candidate is
   `compliance_finding` (uid 3), but **none of the pages consulted states which class AWS uses**.
   Writing the spec against `compliance_finding` without that confirmation is an **assumption**,
   and the spec would have to record it as unproven. *(Re-consulted on 2026-10-15 — see "The
   residual that was looked for again".) What showed up was `class_name` as the published path of
   the export, and no numeric identifier.*
3. **The exact shape of the export file**: whether it is JSON per line (`.jsonl`), an array, or a
   file per page, and what the `ObjectPrefix`/partitioning is. The current spec already records
   that the `path_template` **is not documented** (only the `ObjectPrefix`, up to 512 chars).
4. **The OCSF `severity` -> `severity_id` mapping**: the enum was not read. *(Fulfilled on
   2026-10-15 — see "The gap the search closed" below.)*

**Where this leaves E5:** **CLOSED on 2026-10-14** — the `aws/security-hub-ocsf-export` surface
was written, and the two missing pieces were **resolved or declared**, each one on its own side:

* **The shape of the file: RESOLVED.** The `FindingsOutput` page publishes that `OCSF_JSON`
  *"produces newline-delimited JSON records"* — JSON per line, not an array. That is the shape of
  the delivered artifact.
* **The OCSF class: DECLARED AS A GAP.** The field list that AWS publishes **refuses** the
  analogy with `compliance_finding`: it mixes fields from `vulnerabilities`, `malware`,
  `databucket` and `evidences`, which indicates that the export does not use a single class as an
  envelope. The `class_uid`/`category_uid`/`type_uid` identifiers stay **outside** the artifact and
  `unverified` in the spec — and the golden test requires that they not be emitted.
* **`metadata.version`: DECLARED AS A GAP**, for the same reason: the last RELEASED revision of the
  OCSF is `1.9.0`, and AWS does not state which revision its export uses. *(Re-consulted on
  2026-10-15: AWS came to have **one** sentence about version — *"Security Hub currently supports findings in
  OCSF schema version 1.6"* — and it **does not** resolve it. See below.)*
* **The partitioning: DECLARED AS A GAP** — AWS publishes only the `ObjectPrefix`.

## The source that closed the item: `FindingsOutput`

| URL | HTTP | What it fixes |
|---|---|---|
| [`API_FindingsOutput.html`](https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_FindingsOutput.html) | 200 | **`Format`: `CSV \| OCSF_JSON`**; *"`OCSF_JSON` produces newline-delimited JSON records in the Open Cybersecurity Schema Framework (OCSF) format"*; **`SelectedFields` is not supported in `OCSF_JSON`** (the format includes the whole finding, and sending it returns `ValidationException`); and the list of ~120 OCSF paths with the field names that AWS publishes |
| [`API_ExportOutput.md`](https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_ExportOutput.md) | 200 | The union has **one** member: `Findings`, of type `FindingsOutput` |
| [`API_StartExportJobV2.md`](https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_StartExportJobV2.md) | 200 | *"the output format (`CSV` or `OCSF_JSON`)"*; delivery to S3 (`exportv2.securityhub.amazonaws.com`); the example bucket policy confirms that AWS writes **objects**, with multipart upload support |

**The `SelectedFields` list was used as a FIELD CATALOG, not as a selection.** It is the only
AWS source that publishes the **path names** of the export's OCSF format (`metadata.uid`,
`cloud.account.uid`, `finding_info.title`, `compliance.status`, `resources.name`…), and that is
why the spec's columns are those paths — and **not** shapes derived from the normative OCSF
repository, which differ: the OCSF has `resource` **singular** (`@deprecated` since 1.3.0, with
`superseded_by: ["resources"]`), while AWS publishes `resources`.

**A notation difference that got recorded in the test:** AWS publishes `resources.name`, and the
flattening of an array item writes `resources[].name`. The test normalizes the `[]` and compares
the **set of fields**, keeping the spec with AWS's citable spelling instead of rewriting it to
accommodate the flattening.

## The residual that was looked for again (2026-10-15)

Scope of this round: `class_uid`/`category_uid`/`type_uid` and `metadata.version`. The residual
had already been declared since 2026-10-14; this round is the **search** that closes the
declaration, and not the first search. All pages were searched on 2026-10-15.

| URL | HTTP | What it returned about the two questions |
|---|---|---|
| [`securityhub-v2-findings-export.html`](https://docs.aws.amazon.com/securityhub/latest/userguide/securityhub-v2-findings-export.html) | 200 | The **real** page of the export operation. It says that *"JSON (OCSF) exports always contain the complete finding, so there is no column selection"*. It does not mention class or version. *The old slug `securityhub-findings-export.html` redirects to the index — that is why it looked absent in the first round.* |
| [`securityhub-ocsf.html`](https://docs.aws.amazon.com/securityhub/latest/userguide/securityhub-ocsf.html) | 200 | The **only** AWS sentence about version in all the documentation: *"Security Hub currently supports findings in OCSF schema version 1.6."* |
| [`securityhub-v2-automation-rules.md`](https://docs.aws.amazon.com/securityhub/latest/userguide/securityhub-v2-automation-rules.md) | 200 | Table of the OCSF fields accepted in rule criteria (the same ones that the `Filters` of `GetFindingsV2` accepts). It publishes `class_name`; it **does not** publish `class_uid`, `category_uid`, `type_uid` nor `metadata.version`. |
| [`API_FindingsOutput.md`](https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_FindingsOutput.md) | 200 | **Complete** list of the valid `SelectedFields` paths — **119** paths. The `.md` returns the whole list; the `.html` truncates in the middle. It includes `class_name`, `metadata.uid`, `metadata.product.*`, `severity_id`, `status_id`; it **does not** include any of the three identifiers nor `metadata.version`. |
| [`API_OcsfFindingFilters.md`](https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_OcsfFindingFilters.md) | 200 | It publishes only `CompositeFilters` and `CompositeOperator`; the fields enter through `FieldName` inside each filter, with no closed catalog. |
| [`API_GetFindingsV2.html`](https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_GetFindingsV2.html) | 200 | Same OCSF format in the response, with pagination by `NextToken`. No record example, no version. |
| [`ocsf-aws-extension.html`](https://docs.aws.amazon.com/securityhub/latest/userguide/ocsf-aws-extension.html) | 200 | AWS's OCSF extension page (the "next" of the OCSF page). It does not cover the Security Hub export and does not fix class or version. |

**What this decides.** Two leads showed up, and neither of them is a value:

* **`class_name`** is the only class path that AWS publishes — and it publishes the **field name**,
  without the numeric identifier that the OCSF defines next to it, and without the list of values
  that `class_name` can take. A column needs both halves: the name comes from AWS, the value comes
  from nowhere. Emitting it would require inventing an example value; choosing `compliance_finding`
  (uid 3) would be choosing the class by analogy — which is what the field list already refused
  when it showed `vulnerabilities.*`/`malware.*`/`databucket.*`/`evidences.*` in the same catalog.
* **The `1.6` sentence** is about the schema revision that the service **supports** for findings
  in general, not about the field value in the exported file — and the export's field list does not
  even publish `metadata.version`. Emitting `1.6` would be taking the field name from the
  normative repository and the value from a side sentence: two inferences about a field that AWS
  does not document for this surface. Choosing `1.9.0` by the same path would be identical in
  spirit, and wrong for the same reason. The field stays declared.

**A third-party signal — recorded, and explicitly non-normative.** An article by the Cyber
Security Cloud team, in Japanese, published on 2026-05-25 and updated on 2026-05-28
([`zenn.dev/cscloud_blog`](https://zenn.dev/cscloud_blog/articles/securityhub-v2-overview)),
reports that a real call to `GetFindingsV2` returned `metadata.version: "1.8.0"` while the
documentation announces 1.6, and lists **four** classes in use in the service (Compliance Finding 2003,
Detection Finding 2004, Vulnerability Finding 2002, Data Security Finding 2006). None of that goes
into the spec — the project rule is an official source from the provider, and a blog is not a
source. It is recorded because it settles the same point from the other side: a value that the
documentation itself publicly contradicts is not a safe value for an artifact, and the existence of
**four** classes (not one) confirms that the export's envelope is not a single class.

**Where this leaves E5:** the surface stays **closed**, with the residual **declared** — now with
a reason that is positive, and not only absence: AWS publishes the class field name and not the
identifier, and publishes a supported schema version that is not the revision of the file. Both
items remain `unverified` in the spec, the `model_gaps` of the provenance report repeats the same
reasons, and the golden test keeps requiring that none of this be emitted. The unproven record
stood at **299** on that date — no gap was closed by deduction.

## The gap the search closed: `severity_id` (2026-10-15)

`severity_id` was the fifth `unverified` entry of this surface, with an honest and incomplete
reason: *"the OCSF literal->integer table was not read in this execution"*. It is a gap that
expected **reading**, not a decision.

**Where the enum really is.** The `spec` was looking for `base_event.json` — and that file **does
not exist** in any tag of the repository. The base attributes live in the
[`dictionary.json`](https://github.com/ocsf/ocsf-schema/blob/1.6.0/dictionary.json), at the root,
with **258 KB** in 1.6.0. It is what returned the table:

| `severity_id` | caption | | `severity_id` | caption |
|---|---|---|---|---|
| 0 | Unknown | | 4 | **High** |
| 1 | Informational | | 5 | **Critical** |
| 2 | **Low** | | 6 | Fatal |
| 3 | **Medium** | | 99 | Other |

**Why the number is trustworthy even though the schema revision remains unknown.** The same enum
was read in tag `1.9.0` and is **identical** — same values, same captions, same descriptions. A
value that does not change between 1.6 and 1.9 does not depend on resolving the `metadata.version`
gap, which stays declared. Without this cross-check, emitting `severity_id` would be hanging an
artifact on top of another open gap.

**The search also corrected the `severity`.** The dictionary defines the text field as *"normalized to
the caption of the `severity_id` value"* — in other words, the **caption** (`"High"`), not the
literal. The artifact emitted the **native uppercase** literal (`"HIGH"`), which is the model's
input vocabulary (`model/native.py`), not the value that the OCSF defines. The pair came out
inconsistent with the source that justified it, and the renderer itself already did the right thing
in the neighboring case: `status` comes out as `"New"`, not as the native `"open"`. Now
`severity`/`severity_id` follow the same path, with a declared case normalization — the same
technique that `render/azure_defender.py` uses in `AlertSeverity`, and for the same reason.

Result: the surface goes to **27 columns**, and the unproven record drops from **299 to 296**
(AWS: 117 → **114**) — the first gaps closed by **evidence**, not by deduction.

## The next batch: the ASFF `Severity.Label`, and the table nobody had read (2026-10-15)

The unproven record was treated as a queue, and the triage showed that the AWS items are **not**
of the same kind as `severity_id`: almost all of them say *"the source does not publish"*. But two
of them were of a different kind — of reading: the reason recorded that the page **had not been
read**:

| Item | Old reason | What the reading delivered |
|---|---|---|
| `Severity.Label formal enum` | *"prose guidance only; the Severity API object page was not read in this iteration"* | `API_Severity.html` publishes **`Valid Values: INFORMATIONAL \| LOW \| MEDIUM \| HIGH \| CRITICAL`**, each with its own meaning |
| `exhaustive bodies of the remaining ASFF subobjects` | *"JSON outline page response truncated"* | The limit was the **reading tool**, not the source: the page is the **complete** outline (AWS itself writes *"complete outline"*) and has a `.md` version |

And the same reading resolved the item that was **declared impossible** in the model. The
`Severity.Normalized` came out `null` with the reason *"the 0-100 ranges are not in the consulted
documentation"*. The range was there; what was missing was the **table**, and it is in the same
page:

> *"If you provide `Label` and don't provide `Normalized`, then `Normalized` is set automatically as
> follows: `INFORMATIONAL`–0, `LOW`–1, `MEDIUM`–40, `HIGH`–70, `CRITICAL`–90"*

The field now comes out filled with **the number that AWS publishes**, not with an integer picked
inside the range. And it came out that way for a reason worth recording: `Normalized` is
**deprecated as an input** (*"instead of providing Normalized, provide Label"*), but it remains in
the schema and is filled in by the Security Hub — and this surface describes the API **response**,
not what the finding provider submits. Emitting `null` would be asserting that the service returns
the field empty, which is false.

One item did **not** close, and the attempt turned into evidence in favor of the refusal: the
pattern of the Availability Zone identifier still has no source. The `Placement` object page
describes `AvailabilityZone` as `Type: String`, with no pattern — while the **same** object
publishes `Valid Values` for `Tenancy` (`default | dedicated | host`). When AWS has a closed
domain, it publishes; here it does not have one, and the absence is of the data type, not of the
reading.

## The batch on the export mechanism (2026-10-15): six gaps, none closed — and all stronger

Item 5 of the queue was applied to the `aws/security-hub-asff` surface, whose residuals are about
the **export mechanics** (and not about the ASFF format). The right source was not the JSON
outline page, it was the export API. All read on 2026-10-15:

| URL | HTTP | What it fixes |
|---|---|---|
| [`API_Operations`](https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_Operations.html) | 200 | The inventory of actions: `StartExportJobV2`, `GetExportJobV2`, `CancelExportJobV2`, `ListExportJobsV2` — and the fact that `API_ExportJob` **does not exist** |
| [`API_StartExportJobV2`](https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_StartExportJobV2.md) | 200 | `Destination`, `OutputConfiguration`, `Scopes`, `ClientToken`; `ExportJobId` with pattern `^[a-z0-9]+$`; policy examples with multipart upload |
| [`API_GetExportJobV2`](https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_GetExportJobV2.md) | 200 | The job's **complete** response — and the complete list of its members |
| [`API_ExportOutput`](https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_ExportOutput.md) | 200 | Union: the only member is `Findings`, of type `FindingsOutput` |
| [`API_ExportDestination`](https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_ExportDestination.md) | 200 | Union: the only member is `S3` |
| [`API_FindingsOutput`](https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_FindingsOutput.md) | 200 | `Format` (`CSV | OCSF_JSON`), `Filters`, `SelectedFields` (1–50 OCSF paths) |
| [`API_S3ExportDestination`](https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_S3ExportDestination.md) | 200 | `BucketArn`, `KmsKeyArn` (symmetric, single-Region, full ARN), `ObjectPrefix` (≤512, *prepended*) |

**None of the six residuals closed.** What changed was the nature of the evidence: it stopped being
*"I did not find it"* and became *"the page that would describe this exists, was read, and the
member is not there"*.

- **`export manifest`** — `GetExportJobV2` returns, in total, eleven members (`DataType`,
  `Destination`, `EndedAt`, `ExportJobId`, `FailureCode`, `FailureMessage`, `Name`,
  `OutputConfiguration`, `Scopes`, `StartedAt`, `Status`) and **none of them is a manifest**. It is
  structural evidence, not absence of search.
- **`ASFF to CSV column mapping`** — here the source **changed its mind**: the rule was published
  and nobody had read it. For `CSV`, `SelectedFields` is **mandatory**, the columns **are** the
  field paths and they come out **in the order provided** (1 to 50). The console also publishes the
  **names of the nine standard columns** and an explicit example — `Finding account` comes from
  `cloud.account.uid`. The residual was **reduced** to what is still missing: the path of the other
  eight. And the temptation there is real, because `Severity`, `Status` and `Created at` have an
  obvious path in the OCSF contract — that is why they stay out.
- **`CSV header line, quoting rules and line terminator`** — renamed, because half of the original
  question has an answer: the delimiter is "comma-separated rows" and the set/order of the columns
  are published. What is missing is the header line itself, the quoting rules and the terminator.
- **`export compression and encoding`** — separated what is documented: **encryption** is mandatory
  and detailed (SSE-KMS, symmetric key `ENCRYPT_DECRYPT`, single-Region, full ARN, same account and
  Region). Compression and encoding still have no source.
- **`S3 object key template`** — the `ObjectPrefix` is *prepended to the object keys*, with at most
  512 characters and optional. The template of the rest of the key stays out.

A reading correction that this batch produced: the spec's `delivery.format` already was
`CSV|OCSF_JSON` and the renderer already stated *"ASFF is NOT an available export format"*. Reading
the API was enough to confirm that it was right — **nothing had to change there**, which is the
result one likes to see.
