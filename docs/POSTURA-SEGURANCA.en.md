# Security posture in the simulator — the domain, the contract, and the order

> Language: **English** | [Português](POSTURA-SEGURANCA.md)

**Decision of 2026-10-16: the simulator now represents security posture, across the three clouds.**

Why, with evidence: FinOps scans the cloud with 4 AWS-native checks — **public S3**,
**Security Groups**, **IAM without MFA** and **AWS Config** — plus 2 GCP (SCC and firewall) and 2 Azure
(NSG and Defender). Measured in the real environment on 2026-10-16 (30 AWS accounts):

| Check | Open findings | % of the backlog |
|---|---|---|
| AWS Config | 14,531 | **97.6%** |
| Network / Security Groups | 191 | 1.3% |
| S3 Storage | 165 | 1.1% |
| IAM / Identity | 2 | 0.01% |
| SCC and Firewall (GCP) | 0 | 0% |

And measured in the **simulator**: **none** of the four is producible today. There is no bucket
surface with posture, nor of AWS Security Group, nor of IAM; and `aws-config-snapshot-s3` is the
*snapshot* API, not the compliance one.

## Milestone — the posture domain **closed** (2026-10-19)

**The 8 checks that the three FinOps `SecurityScanner`s run each have the simulator surface
that produces them** — measured against the real consumer, not inferred. The series that closed the
domain runs from `9848e1e` H-01 to `0f7e174` H-09: **15 commits** — **9 of delivery** (feat),
**5 of cleanup** (docs) and **1 of correction** (fix). The count was made back then with
`git rev-list --count 9848e1e^..0f7e174`; today the command no longer runs, because the commits
were lost in the flattening of the history. The complete list, with what each one
delivered, is in PROVENANCIA-HISTORICO.md §3.1.

| Provider | Consumer check | Simulator surface | Commit |
|---|---|---|---|
| AWS | Config by-rule | `aws/config-describe-compliance-by-config-rule` | `9848e1e` H-01 |
| AWS | Security Groups | `aws/ec2-describe-security-groups` | `5169404` H-02 |
| AWS | Public S3 | `aws/s3-list-buckets`, `aws/s3-get-bucket-acl`, `aws/s3-get-bucket-policy`, `aws/s3-get-public-access-block` | `c65faeb` H-03 |
| AWS | IAM without MFA | `aws/iam-get-credential-report` | `d38b325` H-04 |
| AWS | Config residue (3 audit rules) | *(no new surface — the same one as Config by-rule)* | `a80bc1f` H-05 |
| GCP | SCC findings | `gcp/scc-findings`, `gcp/scc-sources` | `69b721d` H-06 |
| GCP | Firewall | `gcp/compute-firewalls` | `dead1b0` H-07 |
| Azure | NSG rules | `azure/arm-network-security-group-rules` | `85951d9` H-08 |
| Azure | Defender/Assessments | `azure/security-assessments-list` | `0f7e174` H-09 |

The six cleanups in the series, which built no surface and therefore do not enter the table:
`df272f4` H-10, `186237f` H-11, `c091409` H-12, `ed1f1d5` H-13, `927eb93` H-14 (docs) and `7974f46` H-15 (fix).

**Config compliance measured** — running the renderer (`config_compliance_by_rule`, seed 123,
profile `small`), 14 rules × 9 scopes = **126** items:

```
COMPLIANT 45   NON_COMPLIANT 27   INSUFFICIENT_DATA 54   NOT_APPLICABLE 0
```

The 54 `INSUFFICIENT_DATA` have **one** cause only — the absence of a resource of the type in the
scope (the `NOT_APPLICABLE` collapse that the API reports as `INSUFFICIENT_DATA`) — and **zero** rules
without source. The decomposition is in *Named residue*, below.

**Repository state at the milestone:** `--matrix` → `gerado=45 falta=0 bloqueado=1 total=46`
(the blocked one is `azure/cost-management-export-cost-details`, a **cost** surface — it does not
enter the posture domain); `--ready` → `PRONTO: 45 superficies`, **0 invented columns** in
any provider; suite → **1095 passed / 20 skipped**.

The 3 product findings that this series of measurements exposed are gathered in a single place in
[INGESTAO-D3-SEGURANCA.en.md](INGESTAO-D3-SEGURANCA.en.md#findings-for-the-consumer-team) — the
canonical section, which the other documents point to.

The history of the increments, one by one, is below and **does not change** with this milestone.

## The rule that governs all surfaces from here on

The simulator emits **what the provider publishes**, in the provider's format. What maps into the
FinOps `findings` table is the writer, on that side. This keeps the project rule intact — the field
name comes from the official documentation, the value comes from the state, and what the source does
not publish is declared.

And there is a good consequence, measured in AWS Config's own API: **`describe_compliance_by_config_rule`
aggregates by RULE, not by resource.** The response brings one line per rule, with the number of
resources that do not comply in `Compliance.ComplianceContributorCount.CappedCount`. In other words, the
natural surface has ~150 lines (the number of AWS managed rules), and the expansion to the thousands of
per-resource findings is **the consumer's**. That removes the volume question without having to decide
anything: the simulator produces the aggregate that AWS publishes, and the backlog of 14,531 is the
product counting the resources.

## Increment 1 — AWS Config, `describe_compliance_by_config_rule` — **DELIVERED on 2026-10-16**

Surface `aws/config-describe-compliance-by-config-rule`, renderer
`config_compliance_by_rule`, spec `specs/aws/config-describe-compliance-by-config-rule.schema.json`.
Contract read on 2026-10-16 in the four pages of the API Reference (the action and the three shapes it
returns), plus the official list of managed rules.

### Request

| Parameter | Type | Published restriction |
|---|---|---|
| `ComplianceTypes` | array of strings | 0 to 3 items. **Valid Values: `COMPLIANT \| NON_COMPLIANT \| NOT_APPLICABLE \| INSUFFICIENT_DATA`** |
| `ConfigRuleNames` | array of strings | 0 to 25 items; length 1 to 128; **Pattern `[A-Za-z0-9_-]+`** |
| `NextToken` | string | pagination |

### Response

`ComplianceByConfigRules`: array of `ComplianceByConfigRule`

| Member | Type | Published restriction |
|---|---|---|
| `Compliance.ComplianceType` | string | `COMPLIANT \| NON_COMPLIANT \| NOT_APPLICABLE \| INSUFFICIENT_DATA` |
| `Compliance.ComplianceContributorCount.CapExceeded` | boolean | "whether the maximum was reached" — **the maximum is not published** |
| `Compliance.ComplianceContributorCount.CappedCount` | **Integer** | number of resources that **cause** `NON_COMPLIANT` |
| `ConfigRuleName` | string | length 1 to 64 |

The semantics are written in the source itself: *"A rule is compliant if all of the resources that the
rule evaluated comply with it. A rule is noncompliant if any of these resources do not comply."*

`INSUFFICIENT_DATA` has its own meaning, and AWS explains the three cases — a rule never
evaluated, a Lambda without `config:PutEvaluations`, or all resources `NOT_APPLICABLE`. **This value is
not a synonym of "not evaluated"**, and the simulator has to reproduce the distinction or the consumer
will read a state that does not exist.

### Two contract traps that a hasty reading gets wrong

**1. `NOT_APPLICABLE` appears in the enum and is not supported.** The Valid Values line above lists the
four values, but the **same page** for the `Compliance` shape says, in the type's description paragraph:
*"For the `Compliance` data type, AWS Config supports only `COMPLIANT`, `NON_COMPLIANT`, and
`INSUFFICIENT_DATA` values. AWS Config does not support the `NOT_APPLICABLE` value for the
`Compliance` data type."* And `DescribeComplianceByConfigRule` closes the loop: a rule whose Lambda
returned `NOT_APPLICABLE` in all evaluations is reported as `INSUFFICIENT_DATA`. Note the
real asymmetry: the **request filter** `ComplianceTypes` accepts `NOT_APPLICABLE`, the
**response** does not. The renderer never emits the value, and that is a constant in the code
(`NOT_APPLICABLE_EMITTED = False`), not just prose.

**2. `CappedCount` counts the culprits, not the evaluated ones.** The `ComplianceContributorCount`
page describes the object as *"The number of AWS resources or AWS Config rules that cause a result of
`NON_COMPLIANT`"*. So a `COMPLIANT` rule carries `CappedCount = 0` — not the total of resources
it evaluated. Counting the evaluated ones would be a different number, and one the documentation
does not publish.

**3. `CapExceeded` is not reproducible.** The boolean is documented as *"Indicates whether the
maximum count is reached"*, but the same page **never publishes that maximum** — it only says *"up to a
maximum number"*. Without the ceiling, the comparison does not come out of the documentation, so the
field goes `null` with the reason recorded in the provenance. `CappedCount` remains real, because it
is a count of the model.

### The rules are REAL, and that is what differentiates the surface

Every emitted `ConfigRuleName` is a **real AWS Config managed rule**, checked one by one against the
official list (`managed-rules-by-aws-config.html`, 838 names, read on 2026-10-16). Nothing here is
invented. That matters because the product side uses synthetic `synth-*` names
(`emulators/aws-sim`), which serves as a stub and **would not** serve to check a real posture screen.

The catalog covers the four domains — public S3, network, identity, audit — with 14 rules.

**Zero rules without source, and that is a result, not a failure.** The rules answered
`INSUFFICIENT_DATA` not because the verdict was uncertain, but because the estate did not carry the
**fact** that each one reads. And there are four subtler gaps that are worth recording here because
**they changed in the last four increments**:

- **Increment 2** — the estate did not carry the RULES of the AWS security group: `model/network.py`
  populated `NetworkSegment.network_security_group` only for Azure and left it `None` on AWS. There
  were 15 `security_group` resources, but none had an ingress rule to read.
- **Increment 3** — the estate did not carry ACL, bucket policy, nor public access block: there were 15
  `s3_bucket` resources inventoried and billed, but nothing in them stated who may read them or
  write to them. Today the posture lives in `model/storage.py`, in the `aws_bucket_postures` collection.
- **Increment 4** — the estate had **no IAM entity at all**: no root MFA, no password
  policy, no access keys. Today it lives in `model/iam.py`, in the `aws_identity_postures` collection.
- **Increment 4.3** — the estate had no CloudTrail trail, nor Security Hub enrollment, nor
  flow log configuration per VPC. Today they live in `model/audit.py`, in the
  `aws_audit_postures` (per account) and `aws_vpc_flow_logs` (per VPC) collections.

They were twelve; they were nine; they were six; they were three; **they are zero**.

**At Increment 1, only two were evaluated from the real state**: `s3-bucket-tagged` and
`lambda-function-tagged`. (Today they are fourteen — the paragraph below describes the starting point,
not the current state.) The
pages for the two rules say, in the same sentence, *"The rule is NON_COMPLIANT if there are no tags or
if the specified tag keys are not present. The rule does not check for tags starting with 'aws:'"* —
and `requiredKeyTags` is an **optional** parameter of the rule, which this renderer does not pass. The
condition reduces, then, to what the page states unconditionally: `NON_COMPLIANT` if the resource has
no tag. `Resource.tags` is exactly that fact. Measured **at Increment 1**, small estate, profile `small`,
canonical seed 123:
126 items (14 rules × 9 account/region scopes), being 2 `COMPLIANT`, 4 `NON_COMPLIANT` and 120
`INSUFFICIENT_DATA`. The split between `COMPLIANT` and `NON_COMPLIANT` varies with the seed — it is the
estate's tag distributor changing — but the **120** `INSUFFICIENT_DATA` were stable: 12
rules without source × 9 scopes, plus the 6 scopes without bucket and the 6 without Lambda.

A detail the estate produced and that justified the surface: each AWS resource type exists in
**one single region** per account (buckets in `us-west-2`, Lambda in `sa-east-1`, security groups in
`us-east-1`). So most scopes have no bucket at all, and the correct answer is not
`COMPLIANT` — a rule with no resource did not evaluate everything — nor `NOT_APPLICABLE`, which the type
does not support. It is `INSUFFICIENT_DATA`, which is the third documented case.

## Increment 2 — AWS Security Groups, `ec2.describe_security_groups` — **DELIVERED on 2026-10-16**

Surface `aws/ec2-describe-security-groups`, renderer `ec2_security_groups`, spec
`specs/aws/ec2-describe-security-groups.schema.json`. Contract read on 2026-10-16 in the eight pages
of the API Reference (the action and the seven shapes it returns), plus the *Security group rules*
page, which is where the semantics live. Measured audit: **9 artifacts, 112 records, 18 paths with
value, 0 invented columns**.

### Response

`securityGroupInfo`: array of `SecurityGroup` — **9 sets, 40 fields**.

| Set | Fields | What it is |
|---|---|---|
| `describe-security-groups-response` | 3 | `nextToken`, `requestId`, `securityGroupInfo` |
| `security-group` | 9 | identity, owning VPC, description, tags and the **two** rule lists |
| `ip-permission` | 7 | protocol, port range and the four source lists |
| `ip-range` / `ipv6-range` / `prefix-list-id` | 2 each | one source of each type |
| `user-id-group-pair` | 7 | reference to another group as a source |
| `tag` | 2 | `key`, `value` |
| `request-parameters` | 6 | `DryRun`, `Filter.N`, `GroupId.N`, `GroupName.N`, `MaxResults`, `NextToken` |

### Five contract traps that a hasty reading gets wrong

**1. The rule is allow-only, and "deny" does not exist.** The VPC guide is literal: *"You can specify
allow rules, but not deny rules"*. Blocking is the **absence** of a rule. That is why the model grew
its own types (`AwsSecurityGroup`, `AwsIpPermission`) instead of reusing Azure's `SecurityRule` —
the latter has `access` (`allowed`/`denied`), and AWS has no decision member to point to. There is
also no **priority**: Azure's NSG publishes `priority` 100..4096 with the lowest number winning;
`IpPermission` publishes nothing that orders rules.

**2. `ipProtocol` is name-or-number-or-`-1`.** It is a `String`, and the documentation accepts a name
(`tcp`/`udp`/`icmp`/`icmpv6`), a protocol number, or `-1`. It is not Azure's closed list of six
literals.

**3. `fromPort`/`toPort` are conditional.** They are `Required: No`. For `-1` the ports do not apply
— and the official sample carries the default egress rule *with neither of them*: absence, not zero. For
`icmp`/`icmpv6` the same fields are **ICMP type and code**, not ports.

**4. The source is a list, not a pair.** `IpPermission` has a set of sources — `IpRanges`
**or** `Ipv6Ranges` **or** `Groups` **or** `PrefixListIds` — and the `IpRange` page closes the
exclusivity: *"You can either specify a CIDR block or a source security group, not both."* Azure's
NSG has prefix **and** port, source **and** destination: four fields. And the **direction is the
list's name** (`IpPermissions` / `IpPermissionsEgress`), not a member of the rule.

**5. The official sample has a member that the type page does not document.** `Example 4` brings
`<securityGroupRuleId>` inside `<groups>`, but `UserIdGroupPair` publishes seven members and that is
not one of them. It stays in `unverified` and therefore **prohibited** in the artifact: a sample is not
a type contract.

That same `Example 4` is what identifies the VPC's **default group**: `<groupName>default</groupName>`
with `<groupDescription>default VPC security group</groupDescription>`. It is the group that
`vpc-default-security-group-closed` evaluates.

### The feedback: three network rules leave `INSUFFICIENT_DATA`

The three managed network rules all have *Resource Types:* `AWS::EC2::SecurityGroup`, and all
three read ingress rules — the first two — or their absence in the default group — the third.
With the rules now modeled, each one applies the text of **its own page**:

| Rule | Published condition | Verdict |
|---|---|---|
| `restricted-ssh` | *"COMPLIANT if the IP addresses of the incoming SSH traffic … are restricted (CIDR other than 0.0.0.0/0 or ::/0)"* | `NON_COMPLIANT` if some SG opens 22 to `0.0.0.0/0` |
| `restricted-common-ports` | COMPLIANT if the port is blocked, or opened only by Inbound rules whose source does not cover `0.0.0.0/0` / `::/0` | `NON_COMPLIANT` if some SG opens a blocked port to the whole internet |
| `vpc-default-security-group-closed` | *"NON_COMPLIANT if the default security group has one or more inbound or outbound traffic rules"* | `NON_COMPLIANT` if the **default** group has at least one rule |

Two reductions worth recording, because without them the verdict would be a local choice:

- `restricted-common-ports` has **optional** parameters (`blockedPort1..5`). The renderer passes
  none, so the rule reduces to the **defaults of the page itself**: 20, 21, 3389, 3306 and 4333. It is
  the same reduction that Increment 1 already made with `requiredKeyTags`.
- An ingress rule with `ipProtocol` `-1` counts as the one that opens the port. The `IpPermission`
  page says that `-1` *"allows traffic on all ports, regardless of any port range you specify"*;
  reading `-1` as "it is not TCP" would let through a rule that exposes SSH.

**Measured on the small estate, seed 123:** 126 items, being **8 `COMPLIANT`, 7 `NON_COMPLIANT` and 111
`INSUFFICIENT_DATA`** (they were 2 / 4 / 120). Each network rule yields **2 `COMPLIANT` scopes and 1
`NON_COMPLIANT`** — and the 6 `INSUFFICIENT_DATA` of each one are the scopes without any security
group, which is the "nothing evaluated" case and not the "everything compliant" case.

That two-sidedness is not decoration. **It was a real failure in this increment**, measured by the
golden test: with five groups per account and a single rotation of four profiles, *every* account
received an exposed group, and `restricted-ssh` — which is only `COMPLIANT` when *no* group in the
scope exposes the port — stayed `NON_COMPLIANT` in every scope. That would teach nothing: a consumer
with the port inverted, or a check that ignored the source CIDR, would receive exactly the same
response. The posture became **even account hardened, odd account exposed**.

### What was declared, and is not an assertion

`vpcId` is the real pending item of this surface, and it is a `TODO-verificar`. The estate does
**not** link a security group to a VPC: the `vpc` resources all live in `sa-east-1` and the
`security_group` all in `us-east-1`, and no (account, region) pair has both. The value comes from the
network **segment** of the same (account, region), whose `segment_id` is already the native `vpc-…` id —
in other words, it is the grouping function of the model itself, not a choice about the provider's
semantics. The construction **fails** if a group has no segment: a group without a VPC would make
`vpc-default-security-group-closed` answer about a VPC that does not exist.

`securityGroupArn` goes `null`: the ARN is `arn:<partition>:ec2:…` and the model does not carry the
**partition**. Writing `arn:aws:` would assert a fact the estate does not have — and the partition is
exactly what differs between commercial, GovCloud and China.

## Increment 3 — S3 Bucket: `list_buckets`, `get_bucket_acl`, `get_bucket_policy`, `get_public_access_block` — **DELIVERED on 2026-10-16**

Four surfaces, four renderers, four specs — the same design as Increment 2, applied to the
bucket family. Contract read on 2026-10-16 in the S3 API Reference pages (`API_ListBuckets`,
`API_Bucket`, `API_Owner`, `API_GetBucketAcl`, `API_Grant`, `API_Grantee`, `API_GetBucketPolicy`,
`API_GetPublicAccessBlock`, `API_PublicAccessBlockConfiguration`), plus three from the **User Guide**
that are where the semantics live: `acl-overview.md` (canned ACLs and predefined groups),
`access-control-block-public-access.md` (what AWS calls "public") and the three AWS Config managed
rule pages. Measured audit (`fidelity --audit`, revision 5169404): **40 surfaces,
0 with error, 0 without record, 0 with invented column** — the four S3 ones enter that total with
19 artifacts and 0 column outside the contract.

The posture lives in `model/storage.py`, in a collection **`CanonicalEstate.aws_bucket_postures`** — and
**not** as a column in `Resource`. `Resource` is the identity carrier that FOCUS 1.2 consumes
column by column; no S3 element belongs to that set, and putting an ACL there would place a field
that no FOCUS column defines inside the record that defines all of them.

### The four responses, and what each one publishes

| Surface | Sets | Fields | Response format |
|---|---|---|---|
| `aws/s3-list-buckets` | 4 | **14** | XML |
| `aws/s3-get-bucket-acl` | 5 | **13** | XML |
| `aws/s3-get-bucket-policy` | 4 | **11** | **JSON** |
| `aws/s3-get-public-access-block` | 2 | **6** | XML |

The scope is **not** the same across the four, and that is the first thing to get right: `ListBuckets`
lists *"all buckets owned by the authenticated sender"*, and each bucket's region travels **inside**
the `Bucket` object (`BucketRegion`). Hence it is **per account** — one artifact per (account, region)
would count the same set of buckets once per region. The other three are called **per bucket**,
by construction.

### Five contract traps that a hasty reading gets wrong

**1. The published ACL is the EFFECTIVE one, not the stored one.** The Block Public Access page is
literal: *"Calls to GetBucketAcl and GetObjectAcl always return the effective permissions in place for
the specified bucket or object… suppose that a bucket has an ACL that grants public access, but the
bucket also has the IgnorePublicAcls setting enabled. In this case, GetBucketAcl returns an ACL that
reflects the access permissions that Amazon S3 is enforcing, rather than the actual ACL that is
associated with the bucket."* The estate stores **both** ACLs and the renderer publishes the effective
one. Measured: **25 stored grants, 23 published, 2 suppressed** in 2 buckets.

**2. "Public" is a property of the RECIPIENT, not of the permission name.** The AWS definition is:
*"Amazon S3 considers a bucket or object ACL public if it grants any permissions to members of the
predefined AllUsers or AuthenticatedUsers groups."* Those two groups, and only them. The
`LogDelivery` group — which the `log-delivery-write` canned ACL uses — is **not** in the sentence, so
a bucket that receives it does not become public. And `FULL_CONTROL` for `AllUsers` counts as read
**and** as write, because it grants both.

**3. Block Public Access is a SHORT-CIRCUIT, not a fourth opinion.** The rule is a conjunction of
two disjunctions whose first term is the block. With `BlockPublicPolicy` on, that half passes
**without the policy being consulted** — even if it is public. A renderer that only asked "is the
policy public?" would fail where AWS approves. It is the most likely mistake when implementing this
rule, and that is why there is a profile dedicated to exercising it.

**4. Only `GetBucketPolicy` is JSON.** The other three carry "The following data is returned in
**XML** format by the service". Treating the fourth as XML for being in the same chapter would be
wrong. And the `Type` member of `Grantee` appears in the XML as `<xsi:type>`, which is the same thing
with the schema instance namespace — the member name is `Type`.

**5. `Policy` is the only Response Element on the policy page — and it is not where the members
are.** The list has a single item. `Version`, `Id`, `Statement` and, inside the statement, `Sid`,
`Effect`, `Principal`, `Action` and `Resource` come from the **Sample Response on the same page**.
`Condition` exists in the policy language and **does not** appear in that example, so it does not enter
the artifact; the reason is in `unverified` so that nobody extends the list thinking the page publishes
it.

### The feedback: three S3 rules leave `INSUFFICIENT_DATA`

All three publish *Resource Types:* `AWS::S3::Bucket`, and the first two read **the same three
things**: *"The rule checks the Block Public Access settings, the bucket policy, and the bucket
access control list (ACL)."*

| Rule | Published condition | Verdict |
|---|---|---|
| `s3-bucket-public-read-prohibited` | *"compliant when **both**: the Block Public Access setting restricts public policies **OR** the bucket policy does not allow public read access; **and** … restricts public ACLs **OR** the bucket ACL does not allow public read access"* | `NON_COMPLIANT` if some bucket escapes the block by policy **or** by ACL |
| `s3-bucket-public-write-prohibited` | the same structure, with write | same, in the write direction |
| `s3-bucket-level-public-access-prohibited` | *"NON_COMPLIANT if an S3 bucket is not listed in the `excludedPublicBuckets` parameter and bucket level settings are public"* | `NON_COMPLIANT` if some bucket has a public ACL or policy |

Two declared reductions, because without them the verdict would be a local choice:

- `excludedPublicBuckets` is **optional** and the renderer passes no parameter, so the exclusion is
  empty and the condition reduces to "the bucket-level settings are public".
- The text of the level rule is **a single sentence** and does not detail the evaluation. Here
  "public" is read as the presence of a public ACL or of a policy with a wildcard principal — the same
  definition that the Block Public Access page publishes. Limitation recorded in `unverified` in the
  spec.

**Measured on the small estate, seed 123:** the three rules give **2 `COMPLIANT` scopes and 1
`NON_COMPLIANT`** each, and 6 `INSUFFICIENT_DATA` — which are the scopes without any bucket, the
"nothing evaluated" case and not "everything compliant". The total of the 126 items of the compliance
renderer was **14 `COMPLIANT`, 10 `NON_COMPLIANT`, 102 `INSUFFICIENT_DATA`** (they were 8 / 7 / 111 —
the same 8 and 7 that Increment 2 measured). The accounting closes: each of the three rules swapped
**3 of its 9 scopes** from `INSUFFICIENT_DATA` to a verdict — 2 to `COMPLIANT` and 1 to
`NON_COMPLIANT` — which is 9 items in total, and `111 − 9 = 102`. The other 6 scopes of each rule
never changed state: they are the ones with no bucket at all.

### The two-sidedness again, and the way it failed here

The profiles are **declared**, never drawn, and the grants come from the table of **AWS canned ACLs**
— which is where AWS itself says who receives what in each predefined ACL. The even account receives
the restricted rotation, the odd one the exposed one.

The golden test caught a real distribution failure: with five buckets per account, the profile that
exercises the block short-circuit was in the **sixth** slot of the restricted rotation, and the
`small` profile only produces five. In other words, the rule's most important discrimination **did
not exist in any state that the suite builds** — it would have gone unnoticed. The correction was one
of ordering, not of code, and the lesson is the same as Increment 2's: the rotation is a proof
mechanism, and a proof mechanism only proves what it reaches.

A second consequence of the same mechanism is worth recording: the verdict of a rule is **per scope**,
and a single violating bucket is enough for the entire scope to become `NON_COMPLIANT`. That is why
the restricted rotation cannot contain any profile that fails the level rule — if it did, no compliant
scope would exist, and the good side of the rule would cease to exist in the state.

### What was declared, and is not an assertion

`BucketArn` goes `null`, and it is **by contract**: the `Bucket` type page says *"This parameter is
only supported for S3 directory buckets"*, and every bucket in the state is general-purpose. Emitting
an ARN would be asserting a fact the documentation withholds.

`CreationDate` is **derived**: a bucket is not measured — `s3_bucket` is among the types the estate
does not bill —, so there is no consumption line from which the date could come.

The join between response and bucket is **by position**, and that is declared, not accidental: the
responses of `GetBucketAcl`, `GetPublicAccessBlock` and `GetBucketPolicy` describe **one** bucket and
none of them has a member that names it. Instead of inventing a `bucketName`, the three surfaces
share a documented order — (account, region, bucket) — and each artifact records the `response_order`
map in the provenance. The triple is necessary, and the name is not: `estate_builder` restarts the
counter per scope, so `s3_bucket-0004` exists in more than one account.

## Following increments, in order

| # | Family | Check | Where the contract is |
|---|---|---|---|
| ~~2~~ | **AWS Security Group** | `ec2.describe_security_groups` + ingress | **delivered** |
| ~~3~~ | **S3 Bucket** | `list_buckets`, `get_bucket_acl`, `get_bucket_policy`, `get_public_access_block` | **delivered** |
| ~~4~~ | **IAM without MFA** | `iam.get_credential_report` | **delivered** |
| ~~5~~ | **GCP — SCC** | Security Command Center findings | **delivered on 2026-10-18 (fidelity)** |
| 6 | **GCP — firewall** | `0.0.0.0/0` rules on critical ports | Network Security / VPC firewall |
| ~~7~~ | **Azure — NSG** | NSG rules | **delivered on 2026-10-18 (fidelity)** |
| 8 | **Azure — Defender** | Defender for Cloud posture | Defender for Cloud |

Item 7 was the cheapest to **measure** (the surface already existed), not to **close**: the audit
found `nsg.id` missing — which the consumer's remediation command depends on — and a state that the
check never flagged. "The surface is already ready" is a starting hypothesis, not a verdict.

## What changes in the bridge (D3)

The FinOps writer starts reading these surfaces instead of the Security Hub export. The fields it
needs and that the simulator now brings:

| Consumer column | Where it comes from |
|---|---|
| `category` | `config` for Config, `network` for SG, `s3` for bucket, `iam` for MFA |
| `severity` | derived from the `ComplianceType` + rule — **rule to define**, see below |
| `resource_id` / `resource_type` | from the resource evaluated by the rule |
| `region` | from the resource |
| `description` / `evidence` / `exposure` / `impact` | from the `b3dd315` H-18 template (the five keys in `UserDefinedFields`) |
| `fingerprint` | same rule as `b3dd315` H-18, recomputable from the document |

**One decision that is yours:** the `severity` column is `NOT NULL` in the consumer's table, and the
AWS Config `ComplianceType` is a compliance state, **not** a severity. Mapping
`NON_COMPLIANT → HIGH` is a product judgment, not a documentation reading. The options are:
(a) the simulator carries the severity per rule, coming from the documentation of the managed rule
itself;
(b) the consumer derives it from `ComplianceType` with a fixed table, which is its own; or
(c) `severity` ceases to be `NOT NULL`. **None of them is obvious, and the choice changes what the
simulator needs to model.**

### The decision above is already answered on the product side — and in a way that changes the question

Checked on 2026-10-16 in `security.py (consumer-module):700-748`: the
product **already has** a severity table per rule, `_config_rule_severity`. In other words, option
(b) is already implemented — with a difference that matters: the table is indexed by the **rule
name**, not by `ComplianceType`. `ComplianceType` says the rule failed; the name says *which* rule
and *how severe* it is. That is better information than what the API delivers on its own, and that is
why option (a) — carrying severity in the simulator — is discarded at no cost: the API **does not
publish** severity per rule, and a simulator that invented it would violate the golden rule of this
phase.

And the consumption is literally what this surface delivers. The check `_scan_config_failures` calls
`DescribeComplianceByConfigRule` filtered by `ComplianceTypes=["NON_COMPLIANT"]` and then
`GetComplianceDetailsByConfigRule` for the resources behind each rule. **The first call is
this surface**; the second is a different surface, which stores the per-resource detail and which
remains out of scope.

### Rule name mismatch between the product and AWS — measured, not suspected

`security.py:721-722` lists two AWS Config rule names. Checked one by one against the official
list (838 names, read on 2026-10-16):

| Pattern in the product | Does it exist as a real name? | Effect |
|---|---|---|
| `cloud-trail-enabled` | **NO** — the real name is `cloudtrail-enabled`, without the hyphen | the pattern matches **0 of the 838** names, so the real rule falls into the final `return "MEDIUM"` instead of the intended `HIGH` |
| `cloudtrail-s3-dataevents` | the real name is `cloudtrail-s3-dataevents-enabled` | **benign**: the pattern matches the real name by prefix |

In other words: a real, small and dated defect. The official name exists with a different spelling
and the substring comparison never reaches it. It is a one-line fix on the product side and **was not
made here** — this task is read-only with respect to FinOps. Recorded for the writer.

→ This is **finding #1** of the [canonical findings section](INGESTAO-D3-SEGURANCA.en.md#findings-for-the-consumer-team).

## The golden rule of this phase

No invented value to close a security gap. If AWS publishes the field, it enters with
URL and date; if it does not publish it, it stays in `unverified` and the renderer emits empty —
exactly as `class_uid` and `metadata.version` ended up in OCSF. The gain here is **domain coverage**,
which is scope; value fidelity remains evidence.

## Increment 4 — IAM: three Config rules that stopped answering `INSUFFICIENT_DATA` (2026-10-18)

### The problem, in one sentence

`--matrix` was at **40 generated out of 41 declared** and `--ready` green, and even so the Config
posture panel showed `INSUFFICIENT_DATA` in **102 of the 126** responses. Neither of the two
measurements sees the problem: one counts the number of artifacts that exist, and the other the
number of faithful artifacts. **Column fidelity is not present data.**

### The golden rule, actually applied

This increment is the first in which the golden rule of this phase **changes length**: it is no
longer "no invented value to close a gap". It is **"no invented value to stop reporting a
gap"** — and the difference shows in `gcp/observability-partial` and in
`iam-get-credential-report`, where two gaps of shape (the `missing.json` set, the column
envelope) were **not** filled with an invented field, but with a sibling artifact or an
`unverified` mark.

The test of a gap is: *if I were not on this side, would the consumer know the same thing?*
For the credential report envelope, yes — it reads the decoded CSV; for the `missing`, yes — it
reads `missing.json`. Neither of the two required us to invent a field inside a body that the
documentation closes.

### The three rules, and the gap the three had

| Rule | Verdict | Reads |
|---|---|---|
| `root-account-mfa-enabled` | 6 C / 3 NC | the **root** account's MFA |
| `iam-password-policy` | 6 C / 3 NC | the account's **password policy** |
| `access-keys-rotated` | 6 C / 3 NC | age of the **users'** access keys |

All three answered `INSUFFICIENT_DATA` for the **same** named gap: the estate had
**no IAM entity at all**. Not "we do not know whether the password is strong" — we had no password
to look at. It is the gap that increments 2 and 3 closed for security groups and bucket posture,
and that this one closes for identity.

### The axis is the ACCOUNT, and that changes the shape of the rule

IAM is global. The password, the root MFA and the keys have no region. Therefore:

- the posture key is `AwsAccount.account_id`, **not** `Resource.identity.uuid`;
- the rule answers **per account** and **repeats** in the account's three regions;
- `resource_type` stays `None` for the three — and `None` has stopped meaning "not evaluated".

A different verdict per region would be a fact AWS does not have.

### Why each rule fails in a different account

```
conta 0  ->  só a SENHA reprova          (política de 8 caracteres, sem requisito)
conta 1  ->  só as CHAVES reprovam       (uma chave ATIVA de 410 dias)
conta 2  ->  só o ROOT reprova           (conta root sem MFA)
```

It is not aesthetics. If two rules failed in the same account, a renderer that swapped them
would receive the same response and **would pass**. With one violation per account, swapping two
rules changes the count — and that is what
`test_o_veredito_e_confirmado_pelas_tags_do_modelo` measures.

### One evaluator, and that is why

`render/_config_evaluators.py` is the **only** implementation of the verdict semantics. The Config
renderer calls it to write the artifact; `fidelity/review.py --state IAM` calls it to describe what
the screen would show. Divergence is **impossible by construction**.

`RuleVerdict` returns the verdict **and the `contributors`**, and that is not decoration:
`ComplianceContributorCount` requires `CappedCount == 0` in a `COMPLIANT` and `> 0` in a
`NON_COMPLIANT`. An evaluator that cannot say **what** failed satisfies the contract on paper and
gives the consumer nothing actionable.

### The retrospective diagnosis

An `INSUFFICIENT_DATA` on the screen has **three** causes that call for opposite actions:

1. **evaluable with the current state** → it is fixed in the **renderer**;
2. **loadable but the data is missing** → it is fixed in the **model**;
3. **configuration failure** → it is fixed in the **account**; no code solves it.

`--state IAM` measures the current `ComplianceType` in the **written bytes** — it is the measurement
that prevents the diagnosis from saying "it did not change" about a screen that did change.

### The 4 AWS posture checks are closed

The four checks that FinOps runs on AWS each have the surface that produces them:

| Check | Surface | Increment |
|---|---|---|
| AWS Config by-rule | `aws/config-describe-compliance-by-config-rule` | 1 |
| Security Groups | `aws/ec2-describe-security-groups` | 2 |
| Public S3 | `aws/s3-list-buckets`, `s3-get-bucket-acl`, `s3-get-bucket-policy`, `s3-get-public-access-block` | 3 |
| IAM without MFA | `aws/iam-get-credential-report` | 4 |

Measured compliance (seed 123, profile `small`, **126** records in **9** scopes):

```
COMPLIANT 45   NON_COMPLIANT 27   INSUFFICIENT_DATA 54   NOT_APPLICABLE 0
```

It was `32 / 19 / 75` before Increment 4.3 — the three last rules named in *Named
residue*, below, left `INSUFFICIENT_DATA` in all scopes.

### Named residue: three audit rules — **CLOSED at Increment 4.3 (2026-10-18)**

Of the catalog's **14** rules, **14** are evaluated from the state. No rule remains that does not
answer, and the remaining `INSUFFICIENT_DATA` has **one** cause only: the absence of a resource of
the type in the scope (the `NOT_APPLICABLE` collapse that the API reports as `INSUFFICIENT_DATA`). The
named model gap **no longer exists** on this surface.

What was modeled, and why in two formats:

| Rule | Granularity | New fact | Source of the format |
|---|---|---|---|
| `cloudtrail-enabled` | **per account** | the account's CloudTrail trails | page publishes trigger `Periodic` and **no** *Resource Types* |
| `securityhub-enabled` | **per account** | Security Hub enrollment | same — "Parameters: None" |
| `vpc-flow-logs-enabled` | **per VPC** | the VPC's flow log configuration | page publishes *Resource Types:* `AWS::EC2::VPC` |

The **54** `INSUFFICIENT_DATA` now decompose as follows, and the decomposition matters because it
separates two things that should no longer be conflated:

- **48** come from 8 **evaluated** rules that have no resource of the type in 6 of the 9 scopes;
- **6** come from the 9th per-resource rule, `vpc-flow-logs-enabled`, in the 6 scopes without a VPC.

In other words: **27 → 0**. The total drop was 21 (75 → 54) and not 27, because the VPC rule
behaves like any other per-resource rule — it answers in the 3 scopes that have a VPC and
collapses in the other 6. That is the "nothing evaluated" case, not a gap.

The three states that could previously be conflated and are now explicitly distinct:

- scope **with no VPC at all** → `INSUFFICIENT_DATA` (nothing was evaluated);
- VPC with an **empty** flow log list → `NON_COMPLIANT` (the estate asserts that it has no log);
- account **with no trail at all** → `NON_COMPLIANT`, naming the account as *contributor*.

Reading the empty list as an absence of knowledge would hide a real violation behind an "I don't
know" — which is exactly the defect this increment eliminates.

`lambda-function-tagged` follows the same pattern as before: it answers `NON_COMPLIANT` in the 3
scopes where there is a Lambda function and `INSUFFICIENT_DATA` in the other 6, because the estate
puts functions in one region per account. It is not a model gap — it is the absence of a resource in
the scope.

### What remains for the next one

- ~~`cloudtrail-enabled`, `securityhub-enabled`, `vpc-flow-logs-enabled`~~: **closed at
  Increment 4.3**. The `--state` diagnosis still covers them only by identity; the audit
  and flow log evaluation still has no retrospective of its own;
- `lambda-function-tagged`: it is **not** residue — it is evaluated where a resource exists, and the
  cause of the rest is the absence of a resource in the scope, not a model gap;
- the **account-level** Block Public Access — which the `GetPublicAccessBlock` page itself
  describes ("the most restrictive combination") — is not modeled; only the bucket one is.

## Increment 5 — GCP SCC: fidelity of the findings surface (2026-10-18)

### This increment builds nothing; it measures

The four previous increments built from scratch a surface that was missing. The SCC is the
opposite: `gcp/scc-findings` and `gcp/scc-sources` **already existed** and were
`STATUS_IMPLEMENTED`. The work was to audit those fields, one by one, against what FinOps actually
reads. And the golden rule applies in both directions: if I had invented a divergence to
"deliver something", I would have committed the same failure the rule forbids.

Two divergences were raised as hypotheses. **One was confirmed, the other was not.**

### The consumer contract, measured

Read in `<source-tree>` (read-only, `security.py (consumer-module)`),
`GCPSecurityScanner._list_scc_findings` calls `securitycenter_client().list_findings(...)` —
the gRPC API `securitycenter_v1`, **not** BigQuery — and projects five fields of the `finding`:

| Field read | Line | Simulator spec | Matches? |
|---|---|---|---|
| `f.severity.name` | `security.py:86` | `finding.severity` | yes |
| `f.resource_name` | `security.py:91` | `finding.resourceName` | yes |
| `f.category` | `security.py:92`, `:94` | `finding.category` | yes |
| `f.description` | `security.py:94` | **absent** | **NO — closed here** |
| `f.name` | `security.py:98` | `finding.name` | yes |

Correction to the request's premise: `f.state` is **not** read from the object. It appears only
inside the filter string (`security.py:80`), never as a projected field. The spec declares
`finding.state` because the filter names it and the renderer emits `ACTIVE` — and `ACTIVE` is the
value the official enum publishes. It was correct as it was.

### Divergence 1 — `description`: CONFIRMED and closed

The consumer builds the finding description with `f.description or f.resource_name`. The column
did not exist in the spec and the renderer did not emit the key: in proto3 the missing field
arrives as an empty string, so **every** finding on the surface would fall into the fallback and the
artifact would never exercise the field the consumer projects. Faithful to the format, unfaithful to
the contract.

Provable by two official machine sources:

- `finding.proto`: `string description = 37;` — *"Contains more details about the finding."*
- discovery v1 (`securitycenter.googleapis.com/$discovery/rest?version=v1`):
  `Finding.properties.description` = `{"type": "string"}`

Closed in two lines: the column `listFindingsResults[].finding.description` in the spec
(`status: verified`, with the docs page in `source_url` and the machine sources in
`reference_urls`), and the projection in the renderer. The value is `NativeFinding.description` — the
same fact the **sibling** renderer of the BigQuery table already projected in
`finding.description`. No value had to be invented: the `estate_builder` already populates that
field in every finding (`estate_builder.py:1817`), and the measurement on the artifact confirms
**64 out of 64** findings with non-empty text. The same `NativeFinding` that feeds both surfaces is
what prevents the divergence between them.

### Divergence 2 — `parent` project × organization: NOT a divergence

The consumer requests `projects/{project_id}/sources/-`; the simulator emits
`organizations/{org}/sources/{n}`. It was the most serious suspicion in the request, and it **did
not hold up**: both levels are published.

- `securitycenter_service.proto`, rpc `ListFindings`: three bindings — `organizations/*/sources/*`,
  `folders/*/sources/*` and `projects/*/sources/*`;
- discovery v1: `v1/projects/{projectsId}/sources/{sourcesId}/findings`, alongside the other two;
- `Finding.name` publishes the three patterns, and `Finding`'s `resource_reference` declares
  `organizations`, `folders` **and** `projects`.

Emitting at the organization level is a valid instance of the contract, not a missing case, and the
column's shape does not change with the level. I recorded the measurement in the spec (`notes`) so
that the question is not re-litigated at every increment. **No modeling was changed** — changing the
emitted level would swap one valid choice for another with no fidelity gain.

### Residue

- `sourceProperties.{Explanation,Recommendation}`: **remains `unverified`**, and the reason stays
  the same — the proto says the map's keys are managed by the source and publishes only the name's
  grammar (1–255 characters, starting with a letter). There is no official enumeration of the
  Security Health Analytics keys.
- `listFindingsResults[].resourceUuid`: **remains `unverified`** (legacy best-effort plan).

Neither of the two changed, so `NAO-COMPROVADOS.md` was not regenerated.

### State on the map

`gcp/scc-findings` closed at **13 columns in the spec, 13 populated, 0 absent, 0 invented**
(they were 12). The GCP SCC check in `<coverage-doc>.md` goes from *inferred* to *measured*: the
surface is faithful to the consumer contract in every field the consumer projects.

## Increment 7 — Azure NSG: fidelity of the rules surface (2026-10-18)

### This increment also does not build a surface; it measures it

`azure/arm-network-security-group-rules` already existed and was ready: 23 columns in two sets
(`rule`, `networkSecurityGroup`), renderer, model, golden test. The request listed four candidate
divergences. **Two were confirmed, one was refuted for being transport, one for already being
covered** — and the measurement revealed a problem **bigger than the four**, which none of them
anticipated.

### The consumer contract, measured

Read in `<source-tree>` (read-only, `security.py (consumer-module)`),
`AzureSecurityScanner._list_open_nsgs` (line 103) calls
`network.network_security_groups.list_all()`, iterates `nsg.security_rules or []` and filters by
direction, access, open source and **critical port**:

| Field read | Line | Simulator spec | Matches? |
|---|---|---|---|
| `rule.direction` (filters `Inbound`) | `security.py:109` | `...properties.direction` | yes |
| `rule.access` (filters `Allow`) | `security.py:109` | `...properties.access` | yes |
| `rule.source_address_prefix` (filters `*` / `0.0.0.0/0` / `Internet`) | `security.py:111` | `...properties.sourceAddressPrefix` | yes |
| `rule.destination_port_range` | `security.py:114` | `...properties.destinationPortRange` | yes |
| `rule.destination_port_ranges` (**plural**, list) | `security.py:114` | `...properties.destinationPortRanges` | in the spec, empty in the state |
| `rule.name` | `security.py:124` | `...name` | yes |
| `nsg.name` | `security.py:124` | `name` | yes |
| `nsg.location` | `security.py:123` | `location` | yes |
| `nsg.security_rules` | `security.py:108` | `properties.securityRules` | yes |
| **`nsg.id`** | **`security.py:121`, `:125`** | **absent** | **NO — closed here** |

### Divergence 1 — `list_all` envelope × per-NSG body: NOT a divergence

The consumer calls `list_all()`, whose REST envelope is `{"value": [...], "nextLink": ...}`
(`NetworkSecurityGroupListResult`). The surface emits **one body per NSG**, not the list envelope.

That is the **correct delivery shape**, and the source confirms it:
`NetworkSecurityGroupListResult` publishes exactly `nextLink | string (uri)` and
`value | Network Security Group []` — the collection's pagination, not a field of the resource. The
SDK unwraps `value` before handing each NSG to the consumer, and that is why it can read
`name`/`id`/`location`/`security_rules` from each iterated object. Emitting a `value` **inside**
each NSG would be inventing a member the resource does not have — the same trap as Increment 5. I
recorded the analysis in the spec (`notes`) so it is not re-litigated.

### Divergence 2 — `destinationPortRanges` (plural): already covered by the spec

The consumer reads `rule.destination_port_ranges` **in addition to** the singular, and `_parse_ports`
processes both. The spec **has** the column (`string[]`, `status: verified`) and the official doc
confirms the member. Therefore **there is no spec divergence to close**. What exists is a gap in
*state coverage*: the model stores the singular shape, so the plural comes out empty and the
`if ranges:` branch of `_parse_ports` never runs against the artifact. Closing it would require
modeling the plural shape in `SecurityRule` — which is a change in `model/network.py`, shared with
the NSG flow log renderers. **It was not done**: it is coverage gain, not fidelity, and the request
instructs building only what the proven divergence requires.

### Divergence 3 — `Internet` source: CONFIRMED as a dead branch

The consumer treats `Internet` as an open source (`security.py:111`), and the doc publishes
`"Default tags such as 'VirtualNetwork', 'AzureLoadBalancer' and 'Internet' can also be used"` —
therefore the spec, which declares `sourceAddressPrefix` as `string`, already covers the value.

The problem was not the spec: it was that **no rule in the state used `Internet`**. The two rules
used `*`, so the third branch of the filter never ran against the artifact. Closed together with
divergence 4 (below): the new critical rule uses `Internet` as its source.

### Divergence 4 — `nsg.id`: CONFIRMED, and with an observable effect

The template page does not publish `id`. But the **REST page** does: the `Network Security Group`
object carries the line `id | string | Resource ID.`, and the `list_all` response example shows the
full id of each NSG.

The impact is not cosmetic. The consumer does:

```python
resource_id=nsg.id or nsg.name,                                    # security.py:121
... f"--resource-group {nsg.id.split('/')[4] if nsg.id else ''}"   # security.py:125
```

Without the field, `resource_id` fell back to the NSG's **name** (an id that is not clickable
anywhere) and the remediation command came out with an **empty** `--resource-group` — in other
words, the command the operator copies into the terminal did not work. Measured before the change:
**`nsg.id` absent in 6/6 NSGs**.

Closed with two columns and one composition: `id` in the `networkSecurityGroup` set, and
`properties.securityRules[].id` — which was in `unverified` **for a reason the REST doc refutes**,
because it publishes the `Security Rule` object with the same line `id | string | Resource ID.` and
the GET example fixes the shape as `<id-do-NSG>/securityRules/<nome>`. Both come out of
`NetworkSecurityGroup.arm_id()`, the same method that already composed the file path: **no
spelling of the same id can diverge**.

### The finding the four divergences did not anticipate: the check never fired

Running the **real** logic of `_list_open_nsgs` (full filter + `_parse_ports` + the
`_CRITICAL_PORTS` dictionary) over the delivered artifacts, the result of the previous posture was:

```
NSGs entregues: 6
regra Inbound/Allow+source aberto por NSG: 6
ACHADOS CRITICAL que o consumidor real produziria: 0
```

**Zero.** The posture was coherent — `AllowVnetInboundTls` on 443 and `DenyInternetInboundRdp` on
3389, both inside the same NSG, the real exposure of the `Allow` evaluated before the `Deny`. But
443 **is not** in the consumer's `_CRITICAL_PORTS` (22, 3389, 5432, 3306, 1433, 27017, 6379), and
the only rule with a critical port was a `Deny`, discarded by the access filter **before** the port
was read.

In other words: the state exposed a port from any origin and the posture check reported
**nothing**. A check that never fires on the artifact does not train the check, and the old golden
test did not catch this because it checked only the `direction`/`access` pair — which the old
posture satisfied.

Closed with the `AllowInternetInboundSsh` rule (`Internet` → `22`, priority 100). Measured after:

```
ACHADOS CRITICAL do consumidor real: 6          (era 0)
split('/')[4] (resource-group) = 'synthetic-rg-sub-03'
id da regra coerente com nsg.id + /securityRules/ + nome: True
```

### Residue

- **Plural** forms of prefixes and ports: they stay empty by the model's choice (see Divergence 2).
  Closing them requires `model/network.py`, beyond what the proven divergence required.
- `defaultSecurityRules`: Azure creates three ingress and three egress rules by default, and the
  REST example **publishes** the six names and priorities (`AllowVnetInBound` 65000,
  `AllowAzureLoadBalancerInBound` 65001, `DenyAllInBound` 65500, and the three egress ones). They
  **do not** enter the state: the three ingress ones are `Allow` with source
  `VirtualNetwork`/`AzureLoadBalancer` (not open), and `DenyAllInBound` is `Deny` — therefore
  **none of them would produce a finding** and including them would be noise with no fidelity
  gain. It is recorded here as an observation, not as `unverified`.
- `NAO-COMPROVADOS.md` **was** regenerated: one `unverified` came out
  (`properties.securityRules[].id`).

### State on the map

`azure/arm-network-security-group-rules` closed at **27 columns in the spec, 16 documented, 16
emittable** (they were 25 columns in the spec; `topo` 16). The Azure NSG check in
`<coverage-doc>.md` goes from *inferred* to *measured*: the surface delivers, field by field,
everything `AzureSecurityScanner` projects — including the `nsg.id` that the remediation command
depends on — and the state now actually produces findings.
## Increment 8 — Azure assessments: the Defender check gained the surface it was reading (2026-10-18)

FinOps' `AzureSecurityScanner` reads `security.assessments.list(scope="/subscriptions/{id}")` and
filters by `properties.status.code`. **There was no surface** with that shape: the `azure-sim`
returned an empty list and the continuous export renderer delivers
`SecurityAlert`/`SecurityRecommendation`, which are a different object. Entered
`azure/security-assessments-list` — **36 columns** in 2 sets (`assessment` 34, `assessmentList` 2),
`SecurityAssessmentList` envelope per subscription, in api `2021-06-01`.

Source: [Assessments - List](https://learn.microsoft.com/en-us/rest/api/defenderforcloud-composite/assessments/list?view=rest-defenderforcloud-composite-stable).

### The state needs a new fact, and it is opt-in

`NativeFinding` **does not cope**: by definition it is a problem, and the consumer's filter
discards precisely the branch that is not a problem. A `Healthy` assessment has no finding, and a
`NotApplicable` one has no finding **for being** the assessment that does not apply to the resource
type.

That is why `AzureDefenderAssessment` (`model/native.py`) was introduced, keyed by `segment_uuid`
and not by resource: the segment is the only Azure object in the state with a true ARM id, and it
is what `properties.resourceDetails.id` and the assessment's `id` publish. The collection enters
**with an empty default** in `CanonicalEstate` — `Resource` and `NetworkSegment` did not change,
nothing was migrated, and therefore no approval checkpoint was needed.

### Two versions that were **measured and discarded**, not presumed

| Version | Result measured on profile `small`/seed 123 | Why it fell |
|---|---|---|
| Derive the state from the findings (`NativeFinding` of category `NETWORK` in the same scope → `Unhealthy`) | `Counter({'Unhealthy': 6, 'NotApplicable': 6})` — **no `Healthy`** | the consumer discards **only** `Healthy`; the artifact never exercised the discard |
| Alternate by the **scope** index | the consumer discarded `[0, 0, 2]` — two envelopes out of three with no discard | the segments group into **subscriptions**, not into scope indices |
| **Alternate by the segment index INSIDE THE SUBSCRIPTION** | each envelope carries both sides | it is the unit the response delivers |

The rule that matters: **a check that never sees the branch it has to decide trains nothing.** It
is the same one that forced Increment 7 to posture 443/3389 instead of leaving the NSG without an
opening.

### `NotApplicable` **is not** the discarded branch

The request that originated this increment assumed that `Healthy` **and/or** `NotApplicable` would
be the branch that does not become a finding. **That is not the case**, and it is measured in the
filter text (`if not status or status.code == "Healthy": continue`): only `Healthy` is discarded.
`NotApplicable` becomes a DEFENDER finding just like `Unhealthy` — and the page describes it as
*"Assessment for this resource did not happen"*, that is, a check that **did not even run** enters
the findings queue. The state delivers the three literals precisely to show this.

### The severity lives in `properties.metadata.severity`

`properties.severity` **does not exist** in this response. Measured against the SDK the consumer
uses (`azure-mgmt-security` 7.0.0, pinned in `requirements.lock`):

- `SecurityCenter(cred, sub).assessments` resolves to the **api 2021-06-01** — the multiapi client
  declares `DEFAULT_API_VERSION = 2024-04-01`, but `_get_api_version("assessments")` falls into the
  only compatible branch;
- the returned model is `SecurityAssessmentResponse`, which **flattens** `properties.*` into
  top-level attributes (`display_name`, `status`, `metadata`);
- that model **has no `properties` attribute**: `assessment.properties.severity` raises
  `AttributeError`, the outer `except Exception` swallows it, and the whole check returns `[]`
  logging `azure_defender_scan_failed`.

The `"MEDIUM"` fallback is **dead code**: `assessment.properties` is evaluated *before* the
`getattr`. Even with the path corrected, `"High"` would need upper-casing like the finding
(`severity = severity.upper()`). The correct path per the SDK is `assessment.metadata.severity`.

**Not fixed here** — FinOps is read-only in this task (inviolable rule #1).

→ This is **finding #3** of the [canonical findings section](INGESTAO-D3-SEGURANCA.en.md#findings-for-the-consumer-team).

### What stays empty, and why

The Defender's **assessment catalog** is not modeled by the state: `displayName`, `description` (at
both levels), `categories`, `threats`, `implementationEffort`, `userImpact`, `policyDefinitionId` and
`preview` come out empty. The domains are published, but the page **does not state which value each
assessment belongs to**.

`status.cause` also comes out empty, and this is the edge case: the response example carries
`"cause": "OffByPolicy"`, but **a payload example fixes the field's shape, not the vocabulary**.

And the effect is visible and named: the consumer uses `display_name` as the finding's **title**, so
the title comes out empty. It is a real gap, not a cosmetic detail.

### State on the map

`--matrix`: **gerado=45 falta=0 bloqueado=1 total=46** (the generated ones were 44; the total was
45). `--audit azure`: the surface delivers 4 files, 4 records, **17 documented paths with value**,
**0 invented columns**, **0 required empty**. `--ready azure`: `PRONTO: 9 superficies`. Golden test:
**34 tests**.
