# Decisions — record of what was decided

> Language: **English** | [Português](DECISOES-PENDENTES.md)

Every item here **was blocking** verifiable work. This document went from "record for a
decision" to **decision record**: on **2026-10-14** the recommendations below were
approved by the product owner, and what remains in each block is **execution**, not
choice.

**Provenance.** The **D1–D8** items come from §7 of <ingestion-doc>.md,
identified by read-only inspection of the FinOps repository. The **E1–E3** items came from
this session's analysis (<coverage-doc>.md).

**How to read it.** Each block brings the question that was open, the **approved decision** and its
**status**. Where the status is *pending*, the reason is stated: in no case is it a lack of
decision — it is work that has not been done yet, or that belongs to the other repository.

---

## D1 — Which generator feeds each plan?

**The question.** The `simulador-nuvem` (here) becomes the source for which of the two plans?

**Why it was blocked.** There are two models that are not interchangeable
(`INGESTAO:184-218`): **file-based ingestion** (CUR/FOCUS/blob/BigQuery) and **API
emulation**. This repository covers the first one entirely and **also** emits the 13 GCP
fixtures with the same file names. What it **does not** have is the emulation **server**
(`app.py`, routers, `provision.py`) — that exists only in the FinOps repository. And there
is a local copy of the generator there (`tools/synthetic_clouds`, 5 renderers)
that the scripts invoke today.

| Option | What would happen | Cost |
|---|---|---|
| a) Adopt it here only for the file plan; keep the local copy for the API | half the gain; two live generators | low |
| **b) Adopt it here for the file plan _and_ for the GCP fixtures, fixing the manifest name (§6.1)** | a single generator for GCP; the local copy shrinks | **one word** (§6.1) + rework of the scripts |
| c) Keep the local copy and retire this repository | the fidelity audit is lost (2,204 columns with URL) | high, and it throws away the asset |

**DECISION: (b), per plan.** §6.1 shows that the `_provenance.json` payload already has
exactly the keys the provisioner consumes — it is a rename in 4 places, not a contract
change.

**Status: pending — to be executed on the other side.** The file plan is already served by this
repository (that is what it does). The missing part is FinOps **adopting these fixtures**:
switch `manifest.json` → `_provenance.json` in `deploy/synthetic-clouds/compose.gcp.yaml:54-55`,
`emulators/gcp-sim/gcp_sim/provision.py` (read at `:216`, keys at
`:164,170,222,231,247-248`, CLI `:256`), `emulators/gcp-sim/tests/test_provision.py:34`
and `scripts/synthetic-clouds/gcp-smoke.ps1:45-48`. The local copy
remains necessary **until** that switch, because its scripts are the ones that invoke it.

**Verified on 2026-10-14 at revision `0f5e6da5` H-36:** all four paths exist and **none of them
moved**; the switch is a string change in 4 files, with the contract intact — this repository writes
`_provenance.json` (`render/gcp_bigquery_topology.py:138`, written at `:1754`) and the payload
(`:1649-1686`) has exactly the keys the provisioner reads. The detail that keeps the
divergence alive: **the local copy of the generator inside FinOps still writes `manifest.json`**
(`tools/synthetic_clouds\render\gcp_bigquery_topology.py:1103`).

**Rule #1 of this repository still stands:** the switch is written inside FinOps, and
whoever executes it is that team (or the owner, directly).

---

## D2 — Azure: discover deliveries without `manifest.json`?

**The question.** Does FinOps move to discovering Azure deliveries **without** a manifest, or
does it ask the simulator for an artifact that it currently **refuses** to emit by contract?

**Why it was blocked.** It is the **most expensive** of the three divergences (`INGESTAO:630-668`). The reader
requires a blob ending in `manifest.json` with `exportType` and `blobs`
(`blob_reader.py (consumer-module):235-244,98-139`); the simulator delivers `export_run.json`
with the 12 fields of the `ExportRun` and **without** `exportType`/`blobs`. Measured result: `discover()`
returns an **empty list** and **FinOps discovers no Azure delivery** from this generator.

| Option | What would happen | Cost |
|---|---|---|
| **a) FinOps discovers without a manifest (`export_run.json` for the type + parts by suffix)** | preserves this repo's fidelity policy (not naming the 29 `example-only` fields) | medium, in the reader |
| b) The simulator starts emitting the manifest | breaks the rule "a name that is not cited is not emitted": 29 of the 41 names exist only in an example | medium, here, and **changes the policy** |
| c) Point Azure ingestion at `azure-sim/exporter/`, which **already writes** the manifest | does not touch this repo's policy; creates **two producers** of the same artifact | low, but requires deciding who is in charge |

**DECISION: (a).** The GCP `provision.py` already does something equivalent, so the pattern exists
in the product itself.

**Status: pending — to be executed on the other side.** The FinOps blob reader moves to
discovering via `export_run.json` + parts by suffix, **and the simulator changes nothing**: the
delivery remains `focus.csv`, `focus.parquet` and `export_run.json`, without `_manifest.json`
(there is a test that requires that: `tests/test_focus_azure_spec_fidelity.py:392-401`).

**Assumption re-verified on 2026-10-14** at the current revision of FinOps (`0f5e6da5` H-36,
`feat/synthetic-clouds-phase6-aws`): the `blob_reader.py` still requires `exportType`/`blobs`, and
the cited path is `<consumer-tree>` (the `INGESTAO` cites
`<consumer-ingestion-module>`, without the `<consumer-tree>` prefix). The divergence is still real.

---

## D3 — Network (4 surfaces) and security (3): build the ingestion path?

**The question.** Build ingestion for the 10 surfaces in `NÃO IDENTIFICADO` — and, for
`aws/security-hub-asff`, is the target **ASFF** or the real export format (`CSV`/`OCSF_JSON`)?

**Why it was blocked.** **No network surface has an ingestion endpoint**, and the reason is twofold and
independent (`INGESTAO:220-242`): none of the three API plans emits a flow log, and there is
no per-file reader. The data exists here — `vpc_flow_logs` delivers **2,376 files in a single
day**. And ASFF carries an embedded decision: AWS **does not** export ASFF (`FindingsOutput.Format`
accepts only `CSV`/`OCSF_JSON`), so the current target is a format that AWS itself does not produce.

| Option | What would happen | Cost |
|---|---|---|
| a) Build ingestion for the 4 network ones | unlocks the whole domain; today it is 100% unconsumable | high (reader + destination + model) |
| b) Build only the security ones, leave network out | half; network still has no destination | medium |
| **c) Switch the ASFF target to `CSV`/`OCSF_JSON` and map** | stops consuming a format that AWS does not export | medium, on both sides |

**DECISION: split into two.** For ASFF, **(c)** — today the surface is faithful to a format
that is not an export format. For network, **(a) only after D4**, because a flow log without a resource
dimension does not join with anything.

**Status: pending, and it is the highest-volume item of work.** Two fronts:

1. **ASFF (c):** FinOps moves to target `CSV`/`OCSF_JSON` and to map; **and this
   repository has a consequence to investigate** — the `aws/security-hub-asff` surface is
   generated today with the ASFF fields. If the consumption target changes, the surface needs to be
   re-specified (spec + renderer + golden test) for the format AWS really exports,
   with a citation per field. **This was not done**: re-specifying is spec work, with an
   evidence URL per field, and rule #2 of this repository forbids assuming the
   mapping.

   **The 2026-10-14 verification changed the nature of this item: it is construction from scratch, not
   adaptation.** Measured at revision `0f5e6da5` H-36: **nothing** in FinOps consumes ASFF (`ASFF`,
   `FindingsOutput`, `OCSF`, `security-hub` → **0 occurrences** in `<consumer-tree>`), and the only
   `service="security-hub"` in the backend is an **OTel span label**
   (`security.py (consumer-module):99`) inside a scan that actually runs S3/SG/IAM/Config checks — it does not call
   the Security Hub API. The other hits are regexes over the
   **AWS Config rule name** (`securityhub-<rule>-<8 hex>`). In other words: **today the
   ASFF surface has no destination at all in the product**, and decision (c) implies building
   reader **and** destination.
2. **Network (a):** it only makes sense after D4. They are 4 surfaces `aws/vpc-flow-logs-s3`,
   `gcp/vpc-flow-logs-bigquery`, `azure/nsg-flow-logs-v2` and `azure/vnet-flow-logs` — the
   ingestion destination belongs to FinOps; this repository already delivers the data. **Confirmed
   unconsumable on 2026-10-14:** there is no file reader for any flow log
   (`vpcflowlogs`, `flowTuples`, `network_flows`, `flow_log` → 0 readers; `network_flows` →
   0 occurrences in the whole backend). The only hits are a compliance control name and the
   agent's remediation action — none of them reads the data.

---

## D4 — Resource dimension: a dedicated table or normalize `resource_id`?

**The question.** Create a resource table/model (with this simulator's `resource_uuid` as the
canonical key and a native id column per cloud), or normalize `resource_id` at load time?

**Why it was blocked.** **Today no cost ↔ inventory ↔ finding join closes**
(`INGESTAO:335-360`). Without a common resource key, each surface is an island: cost
knows the `resource_uuid`, inventory knows the native id, the finding knows what the cloud published.
It is the broadest-reaching decision of the list — it conditions D3.

| Option | What would happen | Cost |
|---|---|---|
| **a) Resource table with canonical `resource_uuid` + native id per cloud** | joins start closing; it is the design the simulator already supports (`model/identity.py`) | high, but it is the foundation |
| b) Normalize `resource_id` at load time | cheaper; each reader normalizes its own way and the divergence comes back | medium and recurring |

**DECISION: (a).** This repository already produces a deterministic `resource_uuid` and the native id
**in the documented form** per cloud — the foundation exists and is tested.

**Status: pending — to be executed on the other side, and the 2026-10-14 verification made the item worse.**
On this side there is **nothing to do**: the deterministic `resource_uuid` is emitted today and is what the
decision adopts as canonical. On that side, **creating the table is not enough** — measured at revision
`0f5e6da5` H-36:

- `resource_uuid` has **0 occurrences** in `<consumer-tree>`: the simulator's canonical id **never
  reaches the database**. It lives in the generator and in the emulators (`model/identity.py`, `render/*`,
  `services/*-sim`), not in the product.
- **Cost does not carry resource identity.** The promoters write a **sentinel**:
  AWS CUR uses `__cur_no_resource__` (`promotion.py (consumer-module):16-18,220`) when there is no
  ARN, and **Azure and GCP always write a sentinel** (`promotion.py (consumer-module):173`,
  `promotion.py (consumer-module):128-136` — "has no resource_id field").
- There is no resource table (0 `create_table("resources")`; none of the 71 tables of
  `<consumer-resource-model>` is a resource). Inventory and finding use **different strings** for the
  same concept: `findings.resource_id String(2048)` — the finding table is `findings`, **not**
  `security_findings` —, `ica_observations.resource_identity String(2048)`,
  `ec2_resource_names.resource_id String(64)`, `focus_cost_records.resource_id String(512)`.
- **No JOIN** links cost to inventory or to a finding (`join findings|resources|ica_*` in
  `<consumer-tree>` → 0).

In other words: decision (a) is the right one, but the work is bigger than "create table + migration" —
it includes **stopping the Azure/GCP promoters from writing a sentinel** and making cost carry the
resource key. Until then, D3-network is stuck by decision, not by oversight.

---

## D5 — GCP/Azure ingestion services already written and **not wired up**

**The question.** Wire them up (`beat_schedule`/endpoint, like `cur-ingestion`) or remove them?

**Why it was blocked.** `GcpIngestionService` and `AzureIngestionService` exist, have tests and
are behind a flag (`config.py:684-687`) — but **they have neither task nor route**. It is finished,
unreachable code: the shortest path to GCP/Azure ingestion is one scheduling away.

**DECISION: wire them up.** It is the best cost-benefit of the whole list, and it depends on D2 for
Azure (without it, the Azure service turns on and discovers nothing).

**Status: pending — to be executed on the other side, in the order D6 → D2 → D5.** The migration (D6) comes
first because it is where the GCP/Azure cost source is registered. **Assumption re-verified on
2026-10-14** at the current revision: the two services still have no caller outside their own
package — the only cells citing them are `service.py (consumer-module)`,
`service.py (consumer-module)`, `parity.py (consumer-module)` and `promotion.py (consumer-module)`, and the
flags remain `OFF` by default in `config.py (consumer-module):684-685` (the `INGESTAO` cites
`config.py (consumer-module)`; the file is `config.py (consumer-module)`).

**The two models to copy already exist, with the exact line** (identified at `0f5e6da5` H-36): the
scheduling in `celery_app.py (consumer-module):61-80` (`"ingest-cur-periodic"` → task
`sync_all_cur_exports (consumer-module)`, interval by
`CUR_INGEST_INTERVAL_MINUTES`, queue `costs`, `time_limit` 3600; gate `:72`), the task module in
`cur_ingestion_sync.py (consumer-module)`, and the route in `cur_ingestion.py (consumer-module):198`,
mounted in `router.py (consumer-module):106` with `prefix="/cur-ingestion"`. Wiring GCP/Azure is
following that pair — there is no new design to invent.

---

## D6 — Migration `128_v128_multicloud_cost_sources.py`

**The question.** Apply it or not?

**Why it was blocked.** The migration is marked "**PROPOSED, NOT APPLIED**" in the file itself
(`:4-6`) and is a **prerequisite** to register a GCP/Azure cost source without loosening the
AWS path (`INGESTAO:789-791`).

**DECISION: apply it**, otherwise D5 starts with nowhere to register the source.

**Status: pending — to be executed on the other side.** Re-verified on 2026-10-14 at revision
`0f5e6da5` H-36: the file is at `consumidor/128_v128_multicloud_cost_sources.py`
(the `INGESTAO` cites `consumidor/...`, without `consumidor/`), and the "PROPOSED, NOT
APPLIED" mark is still in the header (`:3-7`).

**The caveat about the duplicated id 128 is gone — it is no longer work.** The `WORKSPACE.md` recorded two
`128` (the main line with `128_v128_opportunity_economic_score` and this migration) and said that
applying it would require re-linking the graph. At the current revision **that duplicate no longer exists**: there is only
`128_v128_multicloud_cost_sources.py` (neither file nor revision, in `git rev-list --all`),
the `down_revision` is `127_v127_add_requested_by_to_policy_remediation`, **nothing points to 128 as
`down_revision`** and the chain is linear up to here — the migration **is already the head** (the re-linking was
done in commits `72bb40f9` and `9857d77c`, both ancestors of HEAD). What remains is the decision to
apply it and remove the "never run" seal.

*Scope caveat:* this verification is of the head of **this branch**
(`feat/synthetic-clouds-phase6-aws`); this clone has no `main`/`master` to compare against.

---

## D7 — `source` in `focus_cost_records`: `'cur'` or `'synthetic'`?

**The question.** Keep `'cur'` (as the promoters write today) or switch to `'synthetic'`?

**Why it was blocked.** The column accepts `'synthetic'` (`consumidor/128:119-120`), but **all the
FOCUS readers pin `source = 'cur'`** — a row under any other value stays **invisible**
(OA-2, answered with evidence in `ESTADO.md:325`). Switching requires adjusting every reader.

**DECISION: keep `'cur'` and record the debt.** The gain from marking synthetic data is for
audit, and this repository **already marks** all generated data (`markers.py`) — the consumer
can tell synthetic from real without depending on this column.

**Status: decided and in force — nothing to execute.** Confirmed on this side: the promoters
write `SOURCE_CUR = "cur"` and their docstring says why (`promotion.py (consumer-module):10-12`,
`promotion.py (consumer-module)`). The debt is recorded here and **does not** become a change.

---

## D8 — Pin the revision of the simulator that feeds the environment

**The question.** Which revision is the source, and who re-runs the `--audit` when it changes?

**Why it was blocked.** This repository changes with every commit. Today's `--matrix` confirms
`gerado=20 falta=0 bloqueado=1`. **Without a pinned revision, "the simulator" is not a reproducible
artifact** — and two measurements at different revisions are not comparable.

**DECISION: record the revision (commit) together with the environment and re-run `--audit` on change.**

**Status: decided and implemented on this side — the environment side is missing.** Recording the
revision by hand in a document goes stale in the next commit, and a document that asserts the
wrong revision is worse than one that asserts none. So the revision became **printed
by the measurement itself** (`fidelity/revision.py`): `--audit`, `--matrix`, `--golden`,
`--ready` and the spec audit end with

```
revisao=d44624c  branch=master  arvore=com alteracoes nao commitadas
```

Three deliberate properties: outside a git repository the revision becomes `desconhecida` and the
measurement remains valid (the audit measures artifacts, not git); `arvore` distinguishes a
reproducible measurement (clean) from one that no commit contains; and the field never claims "clean"
without having looked. What is missing is on the environment side: **whoever operates the ingestion pins the
commit it adopts and re-runs `--audit` on change** — the output then carries the commit for verification.

---

## E1 — Who applies the specifications in the FinOps repository?

**The question.** The three confirmed gaps that live there — **NSG** projection (`azure-sim`),
**`sqladmin`** router (`gcp-sim`), **`container`** router + Kubernetes API (`gcp-sim`) — are they
applied by whom?

**Why it was blocked.** The inviolable rule #1 of this project forbids writing there, and you confirmed
keeping it. The specification is ready
(<gaps-doc>.md), with contract,
file and how to prove it. **It does not apply itself.**

| Option | What would happen |
|---|---|
| **a) The FinOps team applies it from the specification** | keeps the boundary; depends on someone picking it up |
| b) Authorize targeted writing in this repo for those 3 items | closes faster; **revokes rule #1** |
| c) It stays stuck | the 3 gaps remain open |

**DECISION: (a).** The specification was written so that it does not require re-investigation.

**Status: pending — to be executed on the other side.** The three gaps remain open until someone
applies the specification; nothing changes on this side, and rule #1 keeps holding.
**Verified on 2026-10-14 at revision `0f5e6da5` H-36**, with one path correction and one finding that
changes the order:

- **(a) NSG — open on the FinOps side, and this side's half is DONE (2026-10-14).** The route
  exists and the projection is empty-by-design
  (`emulators/azure-sim/azure_sim/projections/network.py:29-31` →
  `"""Always empty: the estate models no network security group"""`), with its own test of the emptiness
  (`tests/test_api_resource_plane.py:186`). The consumer is the same
  (`security.py (consumer-module):107,109`). **Swapping the `return []` alone
  did not close it**, because the state had no `NetworkSecurityGroup`/`SecurityRule` — that was
  G1 of this repository, and it was executed: the state now has one NSG per Azure segment with
  the two postures (`Inbound/Allow` and `Deny`), and there is a new surface
  (`azure/arm-network-security-group-rules`) with cited spec, renderer, golden test and matrix entry
  (`--matrix`: `gerado=21 falta=0 bloqueado=1`; `--audit`: 12 artifacts, 16 paths, 0 invented
  columns). What is missing is the swap of the `return []` in `azure-sim`, which continues to be written
  in the FinOps repository.
- **(b) `sqladmin` — open, and the cited path changed.** **`services/gcp-sim` does not exist**: the
  emulator is at `emulators/gcp-sim`, with 11 routers and no `sqladmin`
  (`sqladmin|sql/v1beta4` → 0). The consumer stays the same
  (`resources.py (consumer-module):118,134`).
- **(c) `container` + Kubernetes API — open.** No `container.py`, and `container.googleapis.com`/
  `kubernetes`/`/api/v1/namespaces` → 0 in the `gcp-sim` tree. The consumer stays the same
  (`gcp.py (consumer-module):407,409,415` and `:100,111`).

---

## E2 — G11 priority: audit of `gcp_rest_fixtures`

**The question.** Bring `gcp_rest_fixtures` and `gcp_bigquery` into the fidelity matrix now
or later?

**Why it was blocked.** They are the artifacts that **carry the GCP inventory** for the API plan — and
they are **outside the audit**: `--matrix` itself reports `renderer sem superficie
especificada`. In other words, the path through which the GCP data reaches FinOps is the only one without a spec
with an evidence URL nor a golden test.

**DECISION: after G1.** It is expensive (13 endpoint families) and blocks nothing today.

**Status: IN EXECUTION since 2026-10-14 (G1 closed). And the scope changed when the item was opened — for
less, on one side, and for clearer on the other.** The sentence "`gcp_bigquery` is also outside the
audit" was **imprecise**, and the imprecision mattered:

| Renderer | What it is, measured | Real gap |
|---|---|---|
| `gcp_bigquery` (189 lines) | Phase-1 probe that **derives the columns from the spec** `gcp/billing-export-standard` through the same functions as topology (`render/gcp_bigquery_topology.py:61-68`) | **no surface gap.** It emits the SAME surface as `gcp_bigquery_topology` (which already has spec, golden and a matrix entry). The `--matrix` flags it because the matrix credits the surface to **one** renderer — a second producer of the same contract shows up as "not mapped" without being a gap |
| `gcp_rest_fixtures` (590 lines) | 13 API response fixtures in **6 families** (Cloud Asset Inventory, SCC, Recommender, Billing Catalog, Cloud Monitoring 3×, Budgets); the docstring itself admits "best-effort official-shaped" with `TODO-verificar #7` on almost every field | **it is the gap.** These are the artifacts through which the GCP inventory reaches the API plan, without a spec with an evidence URL nor a golden test |

In other words: of the two, **one is not a surface gap and the other has 6 families, not one**. The
work here is (i) writing the official contract of the `gcp_rest_fixtures` families and
confronting the artifact with it — which will require **new evidence**, because the renderer was
written from memory —; and (ii) deciding what to do with `gcp_bigquery`, which today is a second
producer of the same surface: declaring it as such in the matrix, or retiring it. Decision (ii)
is not technical: it is choosing whether the repository keeps two renderers for the same contract.

**One concrete risk, now measured with the official protobuf documentation — and it is narrower
than what I wrote before, and more interesting because of that.** The `gcp_rest_fixtures` emits a synthetic
topology key — `resourceUuid` — in five families (CAI `searchAllResources` and
`searchAllIamPolicies`, SCC findings, Recommender recommendations and insights), as the join between
plans. Verified: **`resourceUuid` occurs ZERO times in the six complete official documents** —
it is not a field of `ResourceSearchResult`, `IamPolicySearchResult`, `Finding`, `Recommendation`,
`Insight` nor `AlertPolicy`. The renderer code already records, for `alertPolicies`, that the field
**broke the client's parse** (*"ParseDict fails with has no field named resourceUuid"*).

What the official documentation adds is the **delimitation**: the rejection of an unknown field comes from the
**JSON → proto** path (`ParseDict(..., ignore_unknown_fields=False)` is the default, and ProtoJSON
*"should reject unknown fields by default"*); the **binary gRPC transport preserves** the unknown
field instead of failing (*"Proto3 messages preserve unknown fields and include them during
parsing"*). Since the consumer uses **both** paths, the field is always **undocumented** — which is
enough for fidelity —, but the effect in production **depends on the transport**. The removal is correct
by contract and *potentially* necessary by function; it is not a guaranteed failure.

The complete survey of the 6 families, with URL and excerpt per field, is in
[CONTRATO-APIS-GCP.md](CONTRATO-APIS-GCP.en.md) — written so that the audit of the remaining families does not
have to be redone. Two results it fixes: **no envelope error exists** (the ten list field names
the renderer uses are all correct), and there are **synthetic values inside
real fields** in four families (the CAI `name`, the SCC `resourceName`, the Recommender `projects/-` and
two Monitoring labels) — those are not fields to remove, they are values to mark.

**First family CLOSED (2026-10-14): Cloud Asset Inventory `searchAllResources`.** Surface
`gcp/asset-search-all-resources`, with spec cited in the official proto (envelope level and item
level), new renderer, projection at both levels, golden test and matrix entry — without touching
`gcp_rest_fixtures`. **The other 10 fixtures are also CLOSED** (same date): each endpoint
became a surface with the contract checked at both levels, in a data driver
(`render/gcp_api_fixtures.py`) instead of ten copied renderers. They are: CAI
`searchAllIamPolicies`, SCC `sources` and `findings`, Recommender `recommendations` and `insights`,
Billing Catalog `services` and `skus`, Monitoring `timeSeries`, `metricDescriptors` and
`alertPolicies`, and Billing Budgets `budgets`.

`--matrix`: **`gerado=33 falta=0 bloqueado=1`**; `--ready`: **33 READY surfaces**; `--audit
gcp`: 19 surfaces, **0 invented columns**. The `gcp_rest_fixtures` and the `gcp_bigquery` remain
without a surface of their own — and that is the decision that stays open: the first is the old producer of the same
11 surfaces, and the second is a **second producer** of the billing surface that the
`gcp_bigquery_topology` already serves. Keeping two producers per contract, or retiring one, is a
product decision.

**Functional effects the audit revealed, which are not only about fidelity:** the compliant Monitoring
artifact delivers only the label `project_id` — the only one common to both monitored
types —, so a reader that resolves the series by the resource label (`instance_id`/
`database_id`) does not find the resource that way. Emitting the conditional keys would require a spec with
**two disjoint contracts** (the `sets` mechanism this repository already uses), and it is named
work, not a one-line adjustment.

---

## E3 — Volume and retention with the new schedule

**DECIDED on 2026-10-14: `medium` profile**, with the disk caveat measured below. The
configuration in `schedule/config.json` was changed (`profile: small → medium`) and validated by
`schedule show`; the rest (`12:00`, `America/Sao_Paulo`, retention **30**, seed 123) did not change.

**Second decision, same day: retention stays at 30 days for now, with a scheduled review.** The
option (i) below (15 days) was presented with the measured ceiling and was **not** adopted: the disk
fills before the first prune takes effect, and the risk is assumed explicitly, not
silently. The review is the trigger — when the accumulated usage of `out/daily/` approaches the
free space on `D:` at the time, or on the first tick that fails for lack of space —, and the choice goes
back to the table with the same number. In the reading of `2026-10-14T17:54` this stopped being urgent:
`D:` had **26.67 GB** free against a ceiling of ~17 GB.

**The question.** With the scheduler at **12:00** and retention of **30 days**, keep the `small` profile
(61.3 MB/day, ~1.8 GB/month without pruning) or move up to `medium`/`large`?

**Why it matters.** `medium` (120-day window) and `large` (400) **multiply the volume per
execution**, and the 30-day retention becomes the disk ceiling.

### The measurement that supports the decision (2026-10-14, day 2026-10-13)

Method: `build_day` + `emit_day` for the same day, with the 19 surfaces, in a scratch
directory outside `out/daily` (does not touch the ledger nor the published artifacts). Seed 123, USD.

| | `small` | `medium` | factor |
|---|---|---|---|
| resources per scope × 9 scopes | 79 × 9 = **711** | 370 × 9 = **3,330** | 4.7× |
| `billing_lines` | 9,031 | 42,247 | 4.7× |
| `findings` | 86 | 368 | 4.3× |
| `inventory_assets` | 711 | 3,330 | 4.7× |
| `network_flows` | 2,664 | 12,312 | 4.6× |
| artifacts written | 2,727 | **11,997** | 4.4× |
| files on disk | 2,736 | **12,006** | 4.4× |
| **bytes on disk** | **61.3 MB** | **281.3 MB** | **4.6×** |
| build + render | 9.7 s | 49.4 s | 5.1× |

Two reading corrections the measurement imposes:

1. **The `medium` window (120 days) is not the generated window.** The day is *month-to-date* by
   construction (`daily/window.py`); the profile enters through the **resource density**
   (`_resources_per_scope`, `PROFILE_WINDOW_DAYS` = 45/120/400 against `PROFILE_TARGET_ROWS`
   = 40 k/500 k/2 M). That is why `medium` multiplies the volume by ~4.6× **on the same day**, and the
   volume of a day grows along the month (the window of 2026-10-13 has 13 days; the one of
   2026-10-31 would have 31).
2. **49.4 s per day is irrelevant to the scheduler** — the task limit is 4 h, and the maximum
   backfill is 31 days.

### The disk ceiling — the caveat

30-day retention with `medium` is not 30 × 281 MB: each day carries a window of a different
size. In the steady state (windows of 13 to 31 days), the average settles at ~24–26 days of
window, that is, **~17 GB** for 30 retained days (30 × ~560 MB); the theoretical worst case (30
31-day windows) is **~20 GB**.

**Free space on `D:`: 26.67 GB** — reading of `2026-10-14T17:54`, already **after** the regeneration
in `medium`. It was 12.10 GB measured at `17:36` the same day; the difference of +14.57 GB **does not** come
from this session (the only removal done here was the `123-small-USD` directory, 61.3 MB, and the
workspace's top-level directories add up to ~1.25 GB), so I do not attribute a cause — I record the reading.

Consequence for the decision: the ~17 GB ceiling for 30 days **fits** in the 26.67 GB free, and
option (ii) no longer requires freeing space. The ceiling remains the ceiling — the scheduled review
below is what prevents the disk from filling silently when the accumulated volume approaches the
free space.

The two options, measured:

| Option | What it costs |
|---|---|
| **(i) 15-day retention** (`schedule set --retention-days 15`) | measured ceiling ~8–10 GB; half the retained history |
| **(ii) keep 30 days** | ceiling ~17 GB, which **fits** in the 26.67 GB free today — but not in the 12.10 GB measured in the morning |

**Chosen: keep 30 days for now and review later** — that is, (ii). With today's free space the
option stops being risky in the short term; the review stays scheduled because the 30-day
ceiling grows with the window and the free space may return to the morning value. `large` (2 M rows)
remains out of the question: it would be ~4× the `medium`.

### Side effect of the profile swap — resolved the same day

The ledger counts **days**, not profiles, so the day `2026-10-13` was already `complete` and would **not**
be regenerated under `medium`; and the prune deletes the **day** directory, not the density one — the
two would have coexisted. Resolved the same day: `tick --force` regenerated the day (**11,997 artifacts**) and
the old density directory was removed.

```
out/daily/2026-10-13/123-small-USD/     <- removido (2.736 arquivos / 61,3 MB)
out/daily/2026-10-13/123-medium-USD/    <- o dia publicado, em medium
```

The ledger ended with `artifacts: 11997` for `2026-10-13` and `last_run.status = ok`. Worth noting what
**was not** touched: retention stays at 30 days, and no day left the ledger.

---

## Consolidated state

Assumption verification done on **2026-10-14** by read-only inspection of FinOps at
revision `0f5e6da5` H-36 (`feat/synthetic-clouds-phase6-aws`), file:line. **Nothing was written there** —
what the verification changed is marked below. *Scope:* this clone only has refs
`feat/synthetic-clouds*`; there is no `main`/`master` to compare against, so the claims hold for the
head of this branch.

| Item | Decision | Status |
|---|---|---|
| D1 | (b) per plan: this repo for the file plan and the GCP fixtures | **pending** — rename the manifest in 4 files in FinOps (verified: nothing moved) |
| D2 | (a) FinOps discovers Azure without a manifest | **pending** — blob reader; the simulator changes nothing (verified) |
| D3 | (c) ASFF to `CSV`/`OCSF_JSON`; network (a) **after D4** | **SPECIFICATION READY on 2026-10-15** — [INGESTAO-D3-SEGURANCA.md](INGESTAO-D3-SEGURANCA.en.md). **The previous line in this record ("it is not adaptation, it is construction from scratch") was wrong, and the measurement disproves it.** What exists in FinOps: the `findings` table (19 columns), the `SecurityFindingAdapter`, the Celery lift `ingest_security_findings` with batching of 500, the `OPPORTUNITY_SECURITY_PRODUCER_ENABLED` flag (fail-closed) and the CIP scheduling with `allowlist`. What does not exist: the **writer** — today the canonical one is `scan_security.scan_workspace_security`, which calls the cloud API and has no credential in staging. Score of the ASFF → `findings` mapping, measured: **9 direct columns, 4 derivations, 5 absent from the format, 2 foreign keys**. And the finding that shrinks the work: the adapter's `_SEVERITY_TO_RISK` uses `CRITICAL/HIGH/MEDIUM/LOW/INFORMATIONAL`, **exactly** the `Valid Values` of the `Severity.Label` the simulator emits, and normalizes with `.upper()` — the contract was already made to tolerate what the simulator produces. **The decision that blocks the execution:** `evidence`, `exposure` and `impact` are `Text NOT NULL` and ASFF **has no equivalent at all**; `fingerprint` is unique per workspace and **cannot be the ASFF `Id`**. Three options in §5 of the document: synthesize in the writer, explicit sentinel, or make the columns `nullable` — all of them change the product, all of them are yours |
| D4 | (a) resource table with canonical `resource_uuid` | **pending** — and **bigger than it looked**: cost does not even carry resource identity (the promoters write a sentinel) |
| D5 | wire up the ingestion services | **pending** — order D6 → D2 → D5; the two models to copy exist (beat `celery_app.py:61-80`, route `router.py:106`) |
| D6 | apply migration 128 | **pending, and simpler than what was written** — the duplicated id 128 **does not exist** at this revision: the migration is already the head of the chain, so there is no re-linking to do |
| D7 | keep `'cur'` | **in force** — nothing to execute (verified) |
| D8 | pin the revision and re-run `--audit` on change | **implemented here** (the revision comes out of the measurement); the environment pins the commit |
| E1 | the FinOps team applies the specification | **pending on that side** — **(a) NSG**: this side's half is done (state with NSG + surface `azure/arm-network-security-group-rules`); the swap of the `return []` in `azure-sim` is missing. **(b)** and **(c)** remain open; the GCP path is `emulators/gcp-sim`, **not** `services/gcp-sim` |
| E2 | audit of the `gcp_rest_fixtures` after G1 | **DONE on 2026-10-14** — 11 new surfaces (the 11 fixtures), with spec, golden and matrix; `--matrix` `gerado=33`, `--ready` 33 READY. **One product choice remains:** what to do with the `gcp_rest_fixtures` (the old producer of the same 11) and with the `gcp_bigquery` (the second producer of the billing surface) |
| E3 | `medium` profile, retention 30 with scheduled review | **done** |
| E4 | **functional gap in Monitoring** — the type-conditional labels | **DONE on 2026-10-14** — the `gcp/monitoring-time-series` surface emits the labels of the **monitored type** again (`gce_instance`: `instance_id`/`zone`; `cloudsql_database`: `database_id`/`region`), without which the series **is not attributable to the resource**. The conditionality is expressed by the project's **named sets** mechanism (`gce_instance_labels`, `cloudsql_database_labels`), and not in prose: no record carries all five, and one set per type is what makes it possible to check each one. `--matrix` `gerado=34`; `--audit gcp`: the surface delivers 3 files, 50 records, 16 paths, **0 invented columns** |
| E5 | **ASFF/OCSF: the surface of the format that AWS exports** | **DONE on 2026-10-14** — new surface `aws/security-hub-ocsf-export` (27 columns, line-delimited JSON), with the file shape, the OCSF paths and the residual cited at the source: [CONTRATO-APIS-GCP.md](CONTRATO-APIS-GCP.en.md#ocsf-contract-of-the-security-hub-aws--collected-for-item-e5). The `aws/security-hub-asff` **was not rewritten** — the reading showed that it correctly describes the **API response**, and that D3(c) asked for a **new** surface for the export. `--matrix` `gerado=34`; `--audit aws`: 1 file, 59 records, 27 paths, **0 invented columns**. **Two gaps remain declared, not resolved by analogy:** the envelope's **OCSF class** (`class_uid`/`category_uid`/`type_uid`) and the `metadata.version`. **Residual re-searched on 2026-10-15 and declared closed without a value**: AWS publishes `class_name` as an export path and never the numeric identifier nor the values, and the only AWS version sentence ("supports findings in OCSF schema version 1.6") is about the revision supported by the service findings, not about the field in the file — recorded with URLs in [CONTRATO-APIS-GCP.md](CONTRATO-APIS-GCP.en.md#the-residual-that-was-looked-for-again-2026-10-15). **A third gap was CLOSED by evidence on the same day:** `severity_id`, whose enum was only "not read in this execution" — see [CONTRATO-APIS-GCP.md](CONTRATO-APIS-GCP.en.md#the-gap-the-search-closed-severity_id-2026-10-15) |

## What this repository keeps doing

**The execution queue — work that does not depend on anyone crossing rule #1:**

| Order | Work | Size | Why in this order |
|---|---|---|---|
| 1 | **The OCSF class of the export** (`class_uid`/`category_uid`/`type_uid`) and the `metadata.version` | evidence first, then small | **CLOSED on 2026-10-15 — with the residual DECLARED, not resolved.** Left out of the artifact on purpose in E5; this round searched for the page (or a sample output) that would state the class. What AWS publishes is the **name** of the discriminator (`class_name`, in the export catalog and in the automation rules table) without the numeric identifier and without the values; and the only AWS version sentence is about the revision **supported** by the findings, not about the field in the exported file, whose field list does not even publish `metadata.version`. Without a value, the contract stays faithful to a declared omission. If a sample output ever shows up, it is field evidence — and the item reopens as a new piece, not as a deduction |
| 2 | **The two producers** (`gcp_rest_fixtures`, `gcp_bigquery`) | product decision, **already reviewed** | **DECIDED on 2026-10-15: keep both, and no_write spec.** The original framing ("two producers of the same contract") was **wrong**, and it is worth recording why. (a) `gcp_api_projection.py` is not a producer at all: it is a **shared library**, imported by `gcp_api_fixtures.py` and by `gcp_cai_search_all_resources.py`, and disappears with any scenario. (b) The two renderers **do not compete for the same contract**: `gcp_rest_fixtures` is the REST plan (590 lines, feeds the emulator, has its own test, and the specs cite it as the origin of two join keys that the official contract rejects) and `gcp_bigquery` is the **Phase 1 probe**, which `gcp_bigquery_topology.py` itself declares it replaces. (c) What the auditor flags is not competition, it is **`[renderer sem superfície]`**: both are registered and **no spec claims them**. The answer that matches the project's discipline is **to write a spec**, not to retire: retiring the `gcp_rest_fixtures` would take down precisely the producer that exposes the conflict with the official contract. The `gcp_bigquery` is the only real candidate for retirement — and that breaks two test files, which is work, not a decision |
| 3 | **The `attic/` breaking `pytest` at the root** | one line, decision taken | **CLOSED on 2026-10-15 by your decision: `conftest.py` at the root with `collect_ignore_glob = ["attic/*"]`.** The original framing (mine) was that the test imported "a module that no longer exists" and that the folder should have been **quarantined**. Reading `attic/README.md`, both things were wrong: the entire `coverage/` package (~1,800 lines) is there, **archived together with its 17 proofs**, and the folder is a documented decision, with the rule written on the first line. Quarantining the file would have thrown away an artifact chosen to be kept. The correct fix was to **codify the rule**: measured before and after, `pytest` at the root and `pytest tools\synthetic_clouds\tests` collect the **same 880 tests**, same `rootdir`, same `configfile`. One detail that stays on record: if the ingestion phase reactivates the material, the import needs to point at `attic/product-coupled/coverage/`, which has a **hyphen** in the path and requires `importlib` |
| 4 | **Watch E3's disk ceiling** | cheap | 30-day retention with `medium` requires ~17 GB; `D:` had 12.10 GB in the morning and 26.67 GB at 17:54. Review when usage approaches the free space |
| 5 | **Keep the documentation alive** | continuous | `ESTADO.md`, `<coverage-doc>.md` and this record |
| 6 | **Attack the record of the 295 unproven items** | continuous queue, each item is small | [NAO-COMPROVADOS.md](NAO-COMPROVADOS.en.md) consolidates what the project **has not yet proven** (114 on AWS, 70 on Azure, 111 on GCP), with the reason each spec already recorded and the distinction **field** (a name that does not belong to the contract) × **theme** (a name that exists and whose proof is missing). It is the list the next evidence work comes from — and it is generated, not written by hand. *The total drops when a gap is closed by evidence: 299 → 296 → **295** on 2026-10-15 (`severity_id` from the OCSF export, `Severity.Label` and `Severity.Normalized` from the ASFF, and the four enums of `scc-findings`). Correction of a claim of mine that came out wrong: I had written that "the record counts each entry **twice**, so closing 1 item lowers the total by 2". That is not a rule — the measurement disproved it. One entry removed from `scc-findings` lowered the total by **1**, and GCP went from 112 to 111. The count is whatever the generator derives from the specs, and it varies with how the spec declares the entry. What counts is the count observed at generation time, never a rule about it.*

**Queue triage (2026-10-15) — the information that decides whether it is worth attacking:** not every item in the record is reading work. Two classifiers were written to separate *"the source does not publish it"* from *"the page exists and nobody read it"*: `.artifacts/inventario-nao-comprovados.py` (list) and `.artifacts/auditar-classificador.py` (audits the classifier). Corrected result:

| Provider | Items | Awaiting reading | Where they are |
|---|---|---|---|
| AWS | 114 | 0 | — |
| Azure | 70 | **1** | VM template: `osDisk` transcribed only for `dataDisks` |
| GCP | 111 | **0** | — (the 3 that were here were closed or reclassified in the same batch: see below) |
| **Total** | **295** | **1** | |

In other words: **294 of the 295 items only close if the provider changes the documentation.** Only **one** real
reading remains in the whole queue: the `osDisk.managedDiskProperties.*` of the Azure VM template. Everything
else is a structural gap of the provider or modeling work — and modeling **is not** reading.

**Third batch, 2026-10-15, and it changes the recommendation above.** The three entries that were still
in this table as "reading pending" in GCP were resolved, each in its own way:
1. **The four enums of `scc-findings` (`State`, `Severity`, `Mute`, `FindingClass`) were CLOSED**
   — read in the discovery v1 and transcribed as `allowed_values`. One of them was still written in the
   previous section as "transcribed"; now it truly left `unverified`.
2. **The inner fields of the `scc-findings` sub-objects (67) were RECLASSIFIED as model
   work**, not reading: the source publishes them, but the renderer emits `finding.indicator`,
   `finding.vulnerability` and `finding.access` as EMPTY objects.
3. **The nested fields of `compute-instances-rest` were RECLASSIFIED for the same reason**: the
   renderer emits `disks[]` and `guestAccelerators[]` as empty lists.

The original table said GCP **3** and total **4**. The measurement now, after those three actions, is
GCP **0** and total **1**. Recording the table without re-running the classifier is like leaving it
disproven — that is why the number here is what `inventario-nao-comprovados.py` prints, and not an
estimate.

**Second reclassification, in the same batch (2026-10-15):** three items that the triage marked as
"reading pending" (`ACCESS_POLICY`/VPCSC, `OS_INVENTORY` and `RELATIONSHIP` from
`cloud-asset-inventory-compute-instance`) **were not pending readings — they were scope divergence**.
The page publishes these three schemas, but they describe the contentTypes
`ACCESS_POLICY`, `OS_INVENTORY` and `RELATIONSHIP`, while the surface's scope is the
`compute.googleapis.com/Instance` table. Transcribing them would have put columns from another content type in the
table of a compute instance. That dropped the pending-reading count from 6 to 3
in GCP. An item that looks like pending work is sometimes, in truth, the wrong question — and the
classifier, being blind to scope, had no way to say that.

**Method lesson the triage produced, and it is worth more than the number:** the first classifier returned **1** item in GCP and **0** in Azure, and that conclusion was wrong. The reason for 6 of them is *"the page publishes this, but it was not transcribed in this pass"* — waiting for a reading written in a word the regex was not looking for. A regex classifier over free text inherits the vocabulary of whoever wrote the text, and errs silently. The fix was to widen the pattern and **audit the classifier against the real distribution of phrases**, not against the regex. That is why the same session produced two numbers: the first was what the tool said, the second is what the tool saw after being checked.

**What is done and does not go back to the queue:** G1 (Azure NSG), D7, D8, E2/G11 (the 11 GCP API
fixtures under contract), E4 (Monitoring's conditional labels), E5 (the Security Hub export's OCSF
surface), the batch that closed `severity_id` and `Severity.Normalized`, the batch of the ASFF
export mechanism, the triage of the unproven-items record, and now the `attic/` rule codified
in `conftest.py` — `--matrix` `gerado=34 falta=0 bloqueado=1`, `--ready` 34 READY, 860 tests.

What I **cannot** do alone: D1–D6 (writing in the FinOps repository, which rule
#1 forbids), E1 (same) and freeing space on `D:`.
