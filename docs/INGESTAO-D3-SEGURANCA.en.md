# D3 — Security ingestion: from the simulator to the `findings` table

> Language: **English** | [Português](INGESTAO-D3-SEGURANCA.md)

**Status as of 2026-10-16: rewritten. The previous version started from a wrong premise.**

**Last updated: 2026-10-29, revision `9533b901` (branch `feat/p76-security-posture-gcp-azure`).**

---

## Findings for the consumer team

**Canonical section for the 3 product findings** that the measurement of the posture surfaces
exposed. The other documents of this repository **point** here; the detail of each finding stays
written where it originated and is **not duplicated** below.

The consumer's paths are relative to `<consumer-tree>`.

| # | Finding | Consumer (file:line) | Symptom | One-line fix | Where the detail is |
|---|---|---|---|---|---|
| 1 | Rule name with one extra hyphen | `aws/security.py:721` (fn `_config_rule_severity`, def at `:701`) | `high_patterns` carries `cloud-trail-enabled`; the real name is `cloudtrail-enabled`. The pattern matches **0 of the 838** managed names, so the real rule falls into `return "MEDIUM"` (`:746`) instead of the intended `HIGH`. | `cloud-trail-enabled` → `cloudtrail-enabled` | [§Increment 4.3, in this doc](#the-consumer-defect-that-the-measurement-made-visible) · <coverage-doc>.md §G2 |
| 2 | VPC implicit rules are not listable | `gcp/security.py:114` (fn `_list_open_firewalls`) | GCP documents that every VPC network has **two** implicit rules — `ingress-deny-all` and `egress-allow-all`, priority 65535. They **are not resources** and `firewalls.list` **does not return them**: the scanner walks the list and never sees the rule that protects the network. | — **structural finding of the API**, not a one-line defect: there is no one-line fix | <coverage-doc>.md §2 · [NAO-COMPROVADOS.md, `gcp/compute-firewalls`](NAO-COMPROVADOS.en.md#gcpcompute-firewalls--6-itemns) (topic `as duas regras implícitas de toda rede VPC`) |
| 3 | Defender severity read from a path that does not exist | `azure/security.py:153` (fn `_list_defender_findings`, def at `:142`) | `assessment.properties.severity` raises `AttributeError`: the `SecurityAssessmentResponse` model (api 2021-06-01) **flattens** `properties.*` into top-level attributes and **has no** `properties` attribute. The outer `except Exception` swallows it, `_list_defender_findings` returns `[]` and the check logs `azure_defender_scan_failed` (`:171`). The `"MEDIUM"` fallback is **dead code** — `assessment.properties` is evaluated *before* the `getattr`. | `assessment.properties.severity` → `assessment.metadata.severity` | [§Increment 8, in this doc](#increment-8--the-azure-assessments-check-gained-the-surface-it-was-reading-2026-10-18) · <coverage-doc>.md §Increment 8 |

**None of the three was fixed here.** FinOps is read-only in this task (inviolable rule #1
of [ESTADO.md](ESTADO.en.md)): all three are **for the team over there**, recorded, measured and
not fixed. Finding 2 is the only one that **does not** have a one-line fix — GCP does not expose
the implicit rules in `firewalls.list`, and no simulator would deliver them without inventing a
resource that the documentation does not publish.

---

## 1. The correction that rewrites this spec

The first draft of this document mapped the **ASFF** (`AwsSecurityFinding`) to the `findings`
table. That started from the assumption that FinOps **consumes the Security Hub export**. Reading
the code and navigating the application disprove that.

**FinOps scans the cloud with scanners of its own.** `scan_security.py (consumer-module)` calls
`AWSSecurityScanner(client).run_full_scan(...)` on its own, and the result becomes a row in
`findings`. There is no ASFF reader, no OCSF reader, no CSV reader and no Security Hub reader in
the product — the scan was confirmed by searching the code and by the Security screen, which
describes the checks one by one.

And there is a more serious consequence: **on 2026-10-16 the simulator did not produce any of the
four checks** — all four only became producible in Increments 1–4, detailed in §4. This spec
stopped being "a bridge" and became "modeling a new domain".

| | the previous version said | what is true |
|---|---|---|
| origin | Security Hub ASFF export | the product's own 4 checks |
| right about | "built from scratch" | it holds, but for another reason — and now with the cause named |
| strategy | mapping existing fields | modeling the primitives the checks read |

---

## 2. The 4 checks, and what each one reads from AWS

Source: `security.py (consumer-module)`, 746 lines.

| # | Check | AWS API | Fingerprint (`scan_security.py`) |
|---|---|---|---|
| 1 | **Public S3** | `s3.list_buckets`, `get_bucket_acl`, `get_bucket_policy`, `get_public_access_block`, `get_bucket_location` | `s3.anonymous_policy` |
| 2 | **Security Groups** | `ec2.describe_regions`, `ec2.describe_security_groups` (paginator per region) | `ec2.security_group.open_all` / `ec2.security_group.open_port.<N>` |
| 3 | **IAM without MFA** | `iam.get_credential_report` (with per-user fallback) | `iam.user.mfa_required` |
| 4 | **AWS Config** | `config.describe_compliance_by_config_rule(ComplianceTypes=["NON_COMPLIANT"])` | `config.<rule_name>` |

On GCP, the product has two checks of its own — **Security Command Center** and **Firewall
Rules** — which on the 2026-10-16 screen both appeared as `0 ✓ clean`. Since 2026-10-26 the two
surfaces are served live by the `gcp-sim` (SCC over gRPC on `:8088`, firewalls over REST on
`:8085` — see §4).

## 3. What the `findings` table requires

19 columns, `UNIQUE(workspace_id, fingerprint)`, nine `NOT NULL` without default.
`SecurityFindingAdapter.from_dict(row) → Finding(**row)` requires that **the dict keys be exactly
the ORM column names**.

What the screen shows per finding — and therefore what has to exist: **severity**, **CVSS**,
**age/SLA** ("2d 13h remaining"; Critical 24h · High 72h · Medium 7d · Low 30d), **origin**
(`CONFIG`), **region** (`us-east-1`), **resource** (`AIDA3M3X…`, `ALBAccessLogsMonitor`).

The vocabulary already matches, and this was measured: the adapter's `_SEVERITY_TO_RISK` uses
`CRITICAL | HIGH | MEDIUM | LOW | INFORMATIONAL`, **exactly** the `Valid Values` of the ASFF's
`Severity.Label`, and normalizes with `.upper()`; `_category_to_complexity` falls into `MODERATE`.
The contract was made to tolerate the input.

## 4. What the simulator has today — measured, not estimated

> **Updated on 2026-10-16 and again on 2026-10-29.** The text was already updated three times on
> 2026-10-16: by the delivery of `aws/config-describe-compliance-by-config-rule` (Increment 1), by
> that of `aws/ec2-describe-security-groups` (Increment 2) and by the four bucket ones of
> **Increment 3** (`s3-list-buckets`, `s3-get-bucket-acl`, `s3-get-bucket-policy`,
> `s3-get-public-access-block`). On 2026-10-18 Increment 4 closed the IAM check, and on 2026-10-26
> the `gcp-sim` started serving the two GCP posture surfaces live. The AWS verdict went from **0 of
> 4** to **4 of 4** producible checks; the state measured on this date is below.

| Check | Before (2026-10-16) | Now (2026-10-29) | Why |
|---|---|---|---|
| 1. Public S3 | **NO** | **YES** | Increment 3 delivered the four bucket surfaces: ACL (`GetBucketAcl`, with `Grant`/`Grantee` and `Permission`), bucket policy (`GetBucketPolicy`), Block Public Access (`GetPublicAccessBlock`, the four booleans) and the per-account listing (`ListBuckets`). What was missing — "who can read or write this bucket" — became a fact of the model |
| 2. Security Groups | **NO** | **YES** | Increment 2 delivered `aws/ec2-describe-security-groups`: `SecurityGroup` with `IpPermissions`/`IpPermissionsEgress`, each rule with `ipProtocol`, `fromPort`/`toPort` and the origin. It is the same shape the Azure check already read in `azure/arm-network-security-group-rules` |
| 3. IAM without MFA | **NO** | **YES** | Increment 4 (2026-10-18) delivered `aws/iam-get-credential-report` (the 23 CSV columns, with per-user MFA and the root account row) and `aws/iam-get-account-password-policy` (the 10 members of `PasswordPolicy`, with `ExpirePasswords` derived); the three Config rules (`root-account-mfa-enabled`, `iam-password-policy`, `access-keys-rotated`) left `INSUFFICIENT_DATA` |
| 4. AWS Config | **PARTIAL** | **YES** | it was only `aws/aws-config-snapshot-s3`, which is the *snapshot* API. `aws/config-describe-compliance-by-config-rule` now exists, which is the compliance response **per rule** |

And there is a structural fact that explains the rest, and it holds **on the AWS side**: the
simulator has findings in the model and, of its **15** AWS surfaces, none is the flow of security
findings with an evaluated resource that the product consumes. `NativeFinding` exists and is
consumed by the ASFF renderer, and the 15 surfaces are `aws-config-snapshot-s3`,
`config-describe-compliance-by-config-rule`, `bcm-data-exports-cur2`,
`bcm-data-exports-focus12`, `ec2-describe-instances`, `ec2-describe-security-groups`,
`s3-list-buckets`, `s3-get-bucket-acl`, `s3-get-bucket-policy`, `s3-get-public-access-block`,
`security-hub-asff`, `security-hub-ocsf-export`, `vpc-flow-logs-s3`,
`iam-get-account-password-policy` and `iam-get-credential-report`. The delivery of Increments 1–4
gave compliance state per rule, network posture, bucket posture and identity — but it is still
**not** a flow of security findings with an evaluated resource on the AWS side.

**Verdict on 2026-10-29: the 4 of 4 AWS checks are producible** (they were 0 on 2026-10-16). On
GCP, the 2 checks started being served **live** on 2026-10-26; on Azure, the measured posture is an
**artifact** (the live NSG API has accepted the SDK's call since 2026-10-26, but returns an empty
list by design). The wrong surface is still `aws/security-hub-asff`: it delivers findings in the
Security Hub format, and the product does not read Security Hub.

### What the 2026-10-26 wave changed — GCP live, Azure unblocked (measured on 2026-10-29)

**GCP.** On 2026-10-26 (`192f3171`) the `gcp-sim` started serving the two posture surfaces the
`GCPSecurityScanner` calls:

- **SCC findings over gRPC** — `google.cloud.securitycenter.v1.SecurityCenter/ListFindings` on port
  **8088** (`emulators/gcp-sim/gcp_sim/routers/scc.py`). The client speaks gRPC because
  `google-cloud-securitycenter` registers its transports as `("grpc", "grpc_asyncio", "rest")` and
  picks the first one; before that, the service only had REST at the organization level and the
  scan never reached it. The plane serves the **66 findings** of the same rendered fixture
  (`scc_findings.json`) that the artifact delivers;
- **Compute firewalls over REST** — `GET /compute/v1/projects/{project}/global/firewalls`
  (`routers/compute.py`), with the rules the estate already models (`default-allow-ssh` on
  `0.0.0.0/0`:22, `default-allow-rdp` on `:3389`), ordered by name.

The TLS front publishes both hostnames: `securitycenter.googleapis.com` (gRPC, `http2` +
`grpc_pass` to `gcp-sim:8088`) and `compute.googleapis.com` (REST to `gcp-sim:8085`) —
`deploy/synthetic-clouds/tls-front/nginx.conf` and the aliases in `compose.tls-front.yaml`. What is
a **declared stub**: `ListFindings` returns the whole response for any `parent`/`filter` (it does
not filter or paginate), and `firewalls.list` does not paginate. **Field** fidelity is the
artifact's; filtering and pagination are outside what the simulator reproduces.

**Azure.** Since 2026-10-26 (`211f21c2`) the `azure-sim` accepts `api-version=2026-03-01` on
`networkSecurityGroups.list_all` — the version the installed `azure-mgmt-network` 33.1.0 sends;
before that, **every** NSG read was rejected with `InvalidApiVersion` and the Azure posture never
reached the scanner. The live projection still returns an **empty list** by design
(`emulators/azure-sim/azure_sim/projections/network.py`): the estate models no NSG resource. What
changed is that the call succeeds; the posture measured in Increment 7 is the artifact
`azure/arm-network-security-group-rules`, not the emulator's response.

**What this does not change:** the **D3 bridge** remains what it was — contract on the simulator
side and writing on the FinOps side. No new findings surface for ingestion was created; what
changed is the **read path** of the product's scanner.

### What Increment 3 adds to the bridge, and what it does not resolve

The public S3 check reads today's AWS Config **compliance rules**, and that is why Increment 3
does not make it "partially good": with the ACL, the policy and the block modeled, the **three**
managed exposure rules (`s3-bucket-public-read-prohibited`,
`s3-bucket-public-write-prohibited`, `s3-bucket-level-public-access-prohibited`) leave
`INSUFFICIENT_DATA` and start answering `COMPLIANT` **and** `NON_COMPLIANT` in the same state.

What the surface delivers to a findings writer:

- **`resource_id` / `resource_type` / `region`** — through the positional join described in each
  artifact's `_provenance.json` (`response_order`, with the account/region/bucket triple);
- **`description` / `evidence`** — the `Grant`s with `Permission` and the group's `URI`, and the
  policy's `Statement`s with `Effect`, `Action` and `Principal`;
- **`exposure`** — the four booleans of `PublicAccessBlockConfiguration`, which are the bucket's
  effective posture and not a derived label.

Two limitations remain, and they belong to the **model**, not to the contract:

- **the bucket creation date is derived.** `s3_bucket` is not measured — there is no consumption
  row the date could come from — so the `CreationDate` comes out of a hash of the resource
  itself, within a fixed interval. It is in the provenance as a derivation;
- **the ACCOUNT-level public access block is not modeled.** The `GetPublicAccessBlock` page is
  explicit: the operation returns *"the bucket-level configuration only"*, and in the assessment
  S3 uses the most restrictive combination between the bucket block and the account one. The
  check that wants the account-level effect still has no source, and the limitation is declared
  in the artifact's provenance.

### What Increment 2 adds to the bridge, and what it does not resolve

The surface `aws/ec2-describe-security-groups` gives the Security Groups check exactly what it
filters: `direction` (the `IpPermissions` list **or** `IpPermissionsEgress`) and the origin of
the rule. Two limitations remain and they belong to the **model**, not to the contract:

- **the VPC of each group is a derivation.** The estate does not link a security group to a VPC —
  the `vpc` and `security_group` resources live in different regions — and the emitted `vpcId`
  comes from the network segment of the same (account, region). It is marked `TODO-verificar` in
  the provenance;
- **`securityGroupArn` goes `null`**, because the ARN needs the partition and the model does not
  carry it.

And there is a direct consequence on the AWS Config side: with the rules now modeled,
`restricted-ssh`, `restricted-common-ports` and `vpc-default-security-group-closed` left
`INSUFFICIENT_DATA` and started answering with the text of each rule's page. Measured on the
small estate (seed 123): each one gives **2 scopes `COMPLIANT` and 1 `NON_COMPLIANT`**, and 6
`INSUFFICIENT_DATA` — the scopes with no security group at all, which is the "nothing evaluated"
case.

**What the new surface already delivers that is useful**, and that answers the AWS Config check
directly: 14 **real** managed rules (checked against the official list), with a verdict per rule
and the number of culprit resources. In the `small` estate, seed 123, there are 126 items: 2
`COMPLIANT`, 4 `NON_COMPLIANT` and 120 `INSUFFICIENT_DATA` — the 120 are the rules whose fact the
model does not carry, each one with the reason recorded. The real verdicts come from
`s3-bucket-tagged` and `lambda-function-tagged`, whose rule pages state the condition without
parameterization.

**What is still missing, measured on 2026-10-29** (and separated from what has been delivered):

1. **`GetComplianceDetailsByConfigRule`** — the consumer calls this API after
   `DescribeComplianceByConfigRule` for the resources behind each rule; the simulator delivers only
   the **per-rule** response. It is the only AWS posture read of the consumer with no corresponding
   surface;
2. **`aws/security-hub-asff` remains the wrong surface for the bridge** — the product does not read
   Security Hub; it is useful as the mold for `UserDefinedFields` (see §5);
3. **account-level Block Public Access** — not modeled; only the bucket one is (see *What Increment
   3 adds to the bridge*, above);
4. **the two implicit rules of every VPC network** remain outside `firewalls.list` — finding #2,
   structural to the real API, not to the simulator;
5. **the live NSG projection in the `azure-sim`** remains `[]`; the Azure posture arrives through
   the artifact.

Each one follows the same discipline: the field name comes from the official documentation, the
value comes from the state, and what the source does not publish is declared. **None of this is
evidence reading — it is modeling, and it is a product decision**: the simulator came to represent
security posture, not only cost.

## 5. What is already delivered and where that counts

The `commit b3dd315` H-18 made the simulator carry `category`, `evidence`, `exposure`, `impact` and
`fingerprint` in the ASFF's `UserDefinedFields`, so that the consumer did not fabricate data that
the producer has. **This remains valid** if the bridge goes through the ASFF — and it becomes the
*mold* of what the new findings surface must carry: the same five keys, the same names, the print
still recomputable from the document.

The rest is unchanged: 13 direct · 1 cardinality derivation · 1 vocabulary · 2 foreign keys
(`workspace_id`, `cloud_account_id`) · **0 missing**.

## 6. Sequence

D3 **does not depend** on the `D6 → D2 → D5` trio and can run in parallel. But §4 is a prerequisite
for everything: without a check that produces a finding, there is nothing to ingest. The shortest
path is:

1. **Check 4 (AWS Config) first.** It is the one with the highest real volume (14,531 of 14,889
   findings in the production account) and the simplest to model: rule name, state, evaluated
   resource.
2. **Check 2 (Security Groups)** next — the second largest (191) and the one that feeds
   `ec2.security_group.open_port.*` the most.
3. **Checks 1 and 3** last: 165 and 2 findings, and the IAM one is the poorest in signal.

Nothing here touches rule #1: the writing is in FinOps, and the team over there is the one who
executes. What this side delivers is the contract and the evidence.

## Increment 4 — the IAM check gained the surface it was reading (2026-10-18)

This document describes the **contract side**, not the writing: the writing is in FinOps, and the
team over there is the one who executes. What changed here is that the IAM check stopped waiting
for a surface that did not exist.

### What it was

The IAM check was the poorest in signal — and the cause was not the check. It was that the
contract side offered the **account password policy** (which is a configuration requirement) and
no surface with **the identities**. The consumer does the per-user MFA cross-check; without the
credential report, it had nothing to cross.

### What came to exist

| Surface | What it delivers | Who reads it |
|---|---|---|
| `aws/iam-get-credential-report` | 23 CSV columns: identities, password, MFA, key age, and the root account row | the per-user MFA cross-check |
| `aws/iam-get-account-password-policy` | the 10 members of `PasswordPolicy`, with `ExpirePasswords` derived | `iam-password-policy` |
| `gcp/observability-partial` | the same read requested over an entire project scope, partially answered, with `missing.json` | "what if the read were only over a subset?" |

### Three contract decisions that matter for the check

1. **`ExpirePasswords` is derived, not independent.** The type's page defines the member through
   `MaxPasswordAge`. Translating the two as separate facts would admit `ExpirePasswords: true`
   alongside a missing `MaxPasswordAge` — a state AWS never returns;
2. **the literal `N/A` is a state.** In the credential report, `N/A` means the object **does not
   exist** (user without a password, non-existent key), `not_supported` appears **only** on the
   root row, and `no_information` is a third value ("the password never opened an AWS site"). If
   the check translates any of them to `null`, it loses the difference between "this user has no
   password" and "this column came empty";
3. **the CSV boolean is `TRUE`/`FALSE`, uppercase.** All the other artifacts of the repository are
   JSON and spell `true`/`false`. A check that compares with `true` reads the whole account as
   `false` — and inverts the finding silently, without any error.

### What this side does not do

Nothing here writes into FinOps, and nothing here decides when the check starts reading. The §4
ingestion policy remains the decision of the team over there; what this side delivers is the
faithful surface and the evidence of why it is faithful.

## Increment 4.3 — the Config residue closes, and no new surface (2026-10-18)

This increment closes the **three** last Config rules that answered `INSUFFICIENT_DATA` in every
scope. The headline for the contract side is negative, and that is the important result:
**no new surface was created**.

### Why no new surface

The question that §4 of this document answers first — "does the product's check read this through
a call → of its own?" — was verified in the consumer, by reading:
`security.py (consumer-module)`.

The file **does not** contain `DescribeTrails`, `GetEnabledStandards` nor `DescribeVpcFlowLogs`.
What it contains is `_config_rule_severity(rule_name)`, which classifies the severity by
**substring** of the `ConfigRuleName` that comes in the `DescribeComplianceByConfigRule` payload.

Conclusion: **the Config compliance payload is already the channel through which the product
reads the three rules.** Delivering `cloudtrail:DescribeTrails` or `securityhub:DescribeHub` here
would be a surface nobody consumes. `fidelity/matrix.py` did not gain a line, and `--matrix`
stood at `gerado=43 falta=0` in the measurement of 2026-10-18 — the same number as before.

### What the check gains, in contract terms

The three rules now bring a real verdict. What the check needs to know so as not to read it wrong:

| Rule | What the verdict means | What it **does not** mean |
|---|---|---|
| `cloudtrail-enabled` | the account has at least one trail | it is not the number of trails, nor the bucket, nor the log group — the renderer does not pass the three optional parameters |
| `securityhub-enabled` | Security Hub is enabled in the account | it says nothing about findings, standards or aggregators — they are not modeled |
| `vpc-flow-logs-enabled` | **per VPC**: some VPC in the scope has no flow log | `CappedCount` is the **count of VPCs without a log**, not of evaluated VPCs |

The third is the one that matters most to the consumer: it is the only rule in the catalog that is
`NON_COMPLIANT` because of **one** VPC among several. A check that treated the rule's
`ComplianceType` as "the entire scope is non-compliant" would lose the count, which is in
`CappedCount`.

### The three `INSUFFICIENT_DATA` that remain, and why they are not a bug

`vpc-flow-logs-enabled` still returns `INSUFFICIENT_DATA` in **6 of the 9 scopes**, and that is
not a model gap: the estate puts the 15 `vpc` resources in a single region per account, so 6
scopes have no VPC at all. The API reports the `NOT_APPLICABLE` collapse as `INSUFFICIENT_DATA`.

The check **must not** treat that value as "we don't know" when there is a VPC in the scope, nor
as "all good". In the scope that has a VPC, a VPC without a flow log is `NON_COMPLIANT` with
`CappedCount` ≥ 1 — and that is how the finding distinguishes itself from a scope that simply had
nothing to evaluate.

### The consumer defect that the measurement made visible

`_config_rule_severity` has `cloud-trail-enabled` (with a hyphen) in `high_patterns`. The real
name is `cloudtrail-enabled`, **without** a hyphen — the page warns that *"the rule identifier
(CLOUD_TRAIL_ENABLED) and rule name (cloudtrail-enabled) are different"*. The pattern matches
**zero** names of the catalog, so the real rule falls into the `return "MEDIUM"` at the end of the
function instead of the intended `HIGH`. Already documented in `<coverage-doc>.md` (G2) based on 838
names, when none of the three existed here; this increment gives the **first real occurrence**.

**Not fixed here** — FinOps is read-only in this task, and the fix is on that side.

→ This is **finding #1** of the [canonical findings section](#findings-for-the-consumer-team).

## Increment 7 — the Azure NSG check gained the field the remediation depends on (2026-10-18)

### What it was

The `_list_open_nsgs` check (`security.py (consumer-module):103`) already had a simulator surface
— `azure/arm-network-security-group-rules` — but the fidelity audit found that it **did not
deliver the `nsg.id`**, which is the field two lines of the finding depend on:

```python
resource_id=nsg.id or nsg.name,                                    # security.py:121
... f"--resource-group {nsg.id.split('/')[4] if nsg.id else ''}"   # security.py:125
```

Without the field: the `resource_id` fell back to the NSG's **name** (an id that is not clickable
anywhere), and the `remediation_command` — which is what the operator copies into the terminal —
came out with `--resource-group` **empty**. Measured: `nsg.id` absent in **6/6** delivered NSGs.

### What changed in the contract

The `id` column entered the `networkSecurityGroup` set of the spec, and the renderer started
emitting it from `NetworkSecurityGroup.arm_id()` — the **same** method that already composed the
file path, which makes a divergence between "resource id" and "blob path" structurally
impossible.

The `properties.securityRules[].id`, which was in `unverified`, left it: the REST page publishes
the `Security Rule` object with `id | string | Resource ID.` and the GET example fixes the shape
`<id-do-NSG>/securityRules/<nome>`. The previous reading was true for the *template* page and
false for the source the consumer actually calls.

### The finding that changes the bridge: the check never fired

Running the consumer's **real** logic (full filter + `_parse_ports` + `_CRITICAL_PORTS`) over the
artifacts, the previous posture produced **0 findings in 6/6 NSGs**. Port 443 is not in the
consumer's dictionary of critical ports, and 3389 — which is — was a `Deny`, discarded before the
port could be read. The state exposed a port from any origin and the signature came out clean.

`AllowInternetInboundSsh` (`Internet` → `22`) went in, and the measurement went to **6 findings**.
That matters for the bridge because it is the case in which an internally coherent state
**silently** produces the signature the scan wants to avoid: no test that checks only the
`direction`/`access` pair — which was the one that existed — would see the difference.

### What this side does not do

The projection in `azure-sim` (`projections/network.py`, which still returns `[]` by design) is
written by FinOps' team — inviolable rule #1. What changes is that it now has, on the state side,
a faithful artifact **and** one that produces a finding, with `resource_id` and
`remediation_command` correctly formed.

## Increment 8 — the Azure assessments check gained the surface it was reading (2026-10-18)

**Finding for FinOps' team, and it is one of severity, not of style:** the `AzureSecurityScanner`
**produces no finding at all** today, and not for lack of data in the simulator.

Reading `security.assessments.list(scope="/subscriptions/{id}")`, it discards what has
`properties.status.code == "Healthy"` and, for the rest, assembles the finding. The line that
reads the severity is
`getattr(assessment.properties, "severity", "MEDIUM") if assessment.properties else "MEDIUM"`.

Measured on 2026-10-18 against the SDK FinOps itself uses (`azure-mgmt-security` 7.0.0, pinned in
`consumer/requirements.lock`):

| Fact | Measured as |
|---|---|
| api-version resolved by `SecurityCenter(cred, sub).assessments` | **2021-06-01** — the multiapi client declares `DEFAULT_API_VERSION = 2024-04-01`, and `_get_api_version("assessments")` falls into the only compatible branch |
| returned model | `SecurityAssessmentResponse`, which **flattens** `properties.*` into top-level attributes |
| `assessment.properties` | **does not exist** → `AttributeError: 'SecurityAssessmentResponse' object has no attribute 'properties'` |
| effect | the outer `except Exception` swallows it, `_list_defender_findings` returns `[]` and the check logs `azure_defender_scan_failed` |
| the `"MEDIUM"` fallback | **dead code** — `assessment.properties` is evaluated *before* the `getattr` |

Fixes that fit on that side:

1. `assessment.metadata.severity` in place of `assessment.properties.severity` — that is where the
   SDK publishes, and it is also where the documentation publishes (the severity **is not**
   `properties.severity`: it is `properties.metadata.severity`, on the
   `SecurityAssessmentMetadataProperties` object).
2. Consider case: the literal is `High`/`Medium`/`Low` and the finding uses
   `severity = severity.upper()`, so without the `.upper()` the value arrives as `High` and leaves
   `HIGH` — which is what FinOps' schema expects. Check what is already done.
3. The silent `[]` is the most expensive point: the worker degrades honestly
   (`defender_assessments` enters `failed_checks` and the coverage does not stamp 100%), so the
   failure does not pass as "all clean" — but it also does not show up as a real error.

→ This is **finding #3** of the [canonical findings section](#findings-for-the-consumer-team).

**Second observation, also measured:** `NotApplicable` **is not** the discarded branch. The filter
is `if not status or status.code == "Healthy"`, and the page describes `NotApplicable` as
*"Assessment for this resource did not happen"* — a check that did not even run enters the
DEFENDER findings queue. If the intent was "only what has a problem becomes a finding", the
condition needs to treat `NotApplicable` as well.

## What this side came to deliver

New surface `azure/security-assessments-list` (**36 columns**, 2 sets, api 2021-06-01), the state
gains `AzureDefenderAssessment` (opt-in collection, empty by default) and the golden test checks,
over the **delivered bytes**, that the consumer produces a finding **and** discards — both sides,
because a check that never sees the branch it has to decide trains nothing.

What **does not** change: the projection in `azure-sim` is written by FinOps' team. What changes
is that it now has, on the state side, an artifact faithful to the contract — including the
`resourceDetails.id` and the assessment's `id` formed from a true ARM id.
