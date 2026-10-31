# Simulador
# Synthetic cloud generator + API emulators

> Language: **English** | [Português](README.md)

Standalone multi-cloud simulator. It generates all the data that is needed —
FinOps, security, network, instances and **drift/what-if** — for **AWS, GCP and
Azure** and for a **synthetic Kubernetes cluster**, and delivers it following
the export mechanism and format that **each cloud really uses**. The very APIs
the consumer calls in the real cloud are served by the emulators.

![Synthetic multi-cloud data, real API contracts](docs/img/hero.svg)

The repository has three parts:

| Part | Where | What it is |
|---|---|---|
| **Generator** | `tools/synthetic_clouds/` | Derives the artifacts from the cited specs; it holds the fidelity gates. |
| **Emulators** | `emulators/` | Serve the same data through each cloud's APIs: `aws-sim`, `azure-sim`, `gcp-sim` and `k8s-sim` (OpenCost). |
| **Deployment** | `deploy/`, `scripts/` | Compose per plane, the TLS front with the real hostnames, and the CloudPilot integration automation. |

> The "Current state" numbers were measured on **2026-10-30**, at revision
> `9ccbc71c`. The "How to measure" column says exactly which command reproduces
> each one — if a number diverges from the code, the command wins over the
> number.

## Current state

| Metric | Value | How to measure |
|---|---|---|
| Specified surfaces | **49** — AWS 15 · GCP 23 · Azure 11 | `specs/**/*.schema.json` |
| **READY** surfaces | **47** | `fidelity --ready` → `PRONTO: 47`, exit 0 |
| Blocked by the documentation | **2** — `azure/cost-management-export-cost-details` and `gcp/container-clusters` | `fidelity --matrix` → `bloqueado=2` |
| Missing | **0** | `fidelity --matrix` → `falta=0` |
| Invented column (any provider) | **0** | `fidelity --audit aws` → `com coluna inventada=0` |
| Unproven items | **293** across 49 surfaces — AWS 88 · GCP 122 · Azure 83 | `specs\_tools\gerar-registro-nao-comprovados.py` |
| Tests | **1106 pass, 20 skip** (1126 collected; 12–14 min) | `pytest tools\synthetic_clouds\tests -q` |
| Specs in prose | **30** | `specs/<provider>/*.md` |
| Emulators | **4** — AWS · Azure · GCP · Kubernetes/OpenCost | `emulators/` |
| Versioned files | **492** | `git ls-files` |

Both blocked surfaces are **deliberate refusals**, not gaps:

* `azure/cost-management-export-cost-details` — Microsoft publishes the 132
  names **without types**, and none of them appears in the five contracts at the
  same time. Generating it would require inventing the type and choosing a
  contract — exactly what rule 3 below forbids.
* `gcp/container-clusters` — the documentation sustains the **shape** (the
  `ListClustersResponse` envelope and 4 of the 87 published members of
  `Cluster`), but the surface is an **API response** served live by `gcp-sim` on
  `container.googleapis.com`, not an export file. Without a renderer that
  produces an artifact checkable against the spec, calling the surface
  "implemented" would be a lie. The published shape and the official citation
  are in [`specs/gcp/container-clusters.md`](specs/gcp/container-clusters.md).

The reason for each one — and for each of the 293 declared gaps — is in
[`docs/NAO-COMPROVADOS.md`](docs/NAO-COMPROVADOS.md), which is derived from the
specs and never hand-edited.

![Coverage, measured](docs/img/cobertura.svg)

## Inviolable rules

1. **Nothing outside this tree.** The simulator is autonomous: it writes to no
   third party database, container or repository, and never talks to the real
   cloud.
2. **Measured fidelity, not presumed.** Every field name, type, unit, date
   format, path layout and file type comes from the provider's **official
   documentation**, cited with URL and consultation date.
3. **No invented field.** Whatever is not documented is marked as `UNVERIFIED`
   and stays out of the generation until it is proven. There is no "seems
   reasonable" in this project.
4. **No credential and no billable call.** The simulator never talks to the real
   cloud. `aws-sim` still refuses to start if it detects real credential
   material in the environment (`emulators/aws-sim/aws_sim/guard.py`).

## Layout

| Path | Role |
|---|---|
| `specs/` | Export specifications per cloud, citing the official docs. **The source of truth.** |
| `specs/<cloud>/*.schema.json` | Machine-readable field inventory, derived from the spec and used by the fidelity tests. |
| `specs/_tools/` | Versioned audit utilities (provenance, columns per spec, URLs, generator of the unproven-items registry). |
| `tools/synthetic_clouds/` | The generator, with the fidelity engine, the daily scheduler, the delivery to the emulators and the test suite. |
| `docs/` | Method notes, decisions, audits, emulated-API contracts and the impact maps in `docs/regression/`. |
| `emulators/aws-sim/` | AWS emulator (Query + S3 REST, STS, EC2, S3, Config, IAM, EKS, ECS, ELB, RDS, Lambda, DynamoDB, CloudWatch, CloudFormation, SSO) + `Containerfile`. |
| `emulators/azure-sim/` | Azure emulator (ARM, Resource Graph, network, Container Service, cost export, Defender, Monitor, deployment stacks, token) + `Containerfile`. |
| `emulators/gcp-sim/` | GCP emulator (REST: compute, container, Config/Infra Manager, recommender, monitoring, catalog, budgets, CRM, storage; gRPC: monitoring and SCC) + `Dockerfile`. |
| `emulators/k8s-sim/` | Kubernetes/OpenCost emulator (`/allocation/compute`, `/clusterInfo`, `/healthz`) + `Containerfile`. |
| `deploy/synthetic-clouds/` | One compose per plane (Azure, GCP, AWS, Kubernetes), the TLS front (`tls-front/`) and the integration automation (`integration/`). |
| `scripts/synthetic-clouds/` | Orchestration (`up`, `down`, `smoke` for AWS/GCP, `export_once`, `run_azure_sim`). |

The `tools/synthetic_clouds` path is deliberate: the code self-imports as
`tools.synthetic_clouds` in **871** places, and moving it would require a mass
rename with no gain. The package's `ruff`/`mypy`/`pytest` configuration is in
`tools/synthetic_clouds/pyproject.toml` — **do not** create a config at the root.

## Method

The work advances in this order, always:

1. **Specify** — capture the official format in `specs/`, with the citation.
2. **Generate** — implement the renderer from the spec, never from memory.
3. **Prove** — fidelity test that compares the generated artifact against
   `specs/<cloud>/*.schema.json`: exact column set, order, units and formats.

A surface is only considered ready when the three steps close.

## Architecture

![How the data flows](docs/img/pipeline.svg)

The path is always the same: the **spec** is the source of truth, the
**generator** is deterministic, the **emulators** serve the same data through
each cloud's APIs, and the **consumer** ingests through its own production path.
On the CloudPilot network, the emulators and a **TLS front** publish the real
hostnames (`management.azure.com` from `azure-sim`; `bigquery.googleapis.com`,
`container.googleapis.com`, `securitycenter.googleapis.com`, ... from the nginx
front) and forward them to the right emulator — the consumer code never knows it
is talking to a simulator. The simulator never talks to the real cloud at any
point.

## What is emulated

![What is emulated, by domain](docs/img/dominios.svg)

**Five data domains** — cost/FinOps, security, network, instances and
**drift/what-if** — in the three clouds. Each cell corresponds to surfaces with
their own spec, generator and fidelity test.

Beyond the specified surfaces, the emulators expose the **live routes** that
correspond to several of them — SCC findings (gRPC) and Compute firewalls (REST)
in `gcp-sim`, `container.googleapis.com` for the cluster list — and serve two
contracts that have **no export surface** (which is why they are not among the
49): **cluster discovery** for EKS/AKS, which is an API response, and the
`k8s-sim` **OpenCost** contract. For those two, what exists is the contract
measured in code and in the emulator tests, recorded in the impact maps
(`docs/regression/`) and in `docs/k8s-sim-opencost-contract.md`.

**How CloudPilot reaches the `k8s-sim`.** Since S4b2-C it is attached to the
`cloudpilot-deploy_cloudpilot_net` network with the `k8s-sim` alias; since **S4b2-E** the
consumer reaches it over **HTTPS**, at the front's own name,
`https://opencost.synthetic-clouds.test` — the `k8s-sim` alias stays as the front's
upstream, at `http://k8s-sim:8089`. The link is
re-applied idempotently by `deploy/synthetic-clouds/integration/ensure-cloudpilot.ps1`,
which also creates the container from `compose.k8s.yaml` when it is missing — without
a rebuild. Detail in
[regression/mapa-impacto-s4b2c.md](docs/regression/mapa-impacto-s4b2c.md) and
[regression/mapa-impacto-s4b2e.md](docs/regression/mapa-impacto-s4b2e.md).

**How CloudPilot reaches the `aws-sim`.** The AWS plane has its **own** variable
namespace: `compose.aws.yaml` reads `AWS_SIM_SEED`/`AWS_SIM_PROFILE`, not the generic
`SEED`/`PROFILE` names the Azure/GCP planes read. Without the `AWS_SIM_*` pair, the
`aws-sim` falls back to the `small` default and serves a **different** estate from the
rest of the stack. The emulator's `sts` is reached through the **per-account endpoint**
(`cur_config.endpoint_overrides.sts`), not through a `sts.amazonaws.com` hostname
hijack — a global hijack would break the real AWS accounts CloudPilot also consumes.
Detail in [regression/mapa-impacto-s4b2c.md](docs/regression/mapa-impacto-s4b2c.md) §7.

**How CloudPilot reaches the `aws-sim` CUR.** The CUR reader uses the **per-account**
`endpoint_url` (`cur_config.endpoint_url`): in this installation, `http://s3mock:9090` in
path style, on the `AWS_SIM_BUCKET` bucket (`synthetic-focus12-daily-full`), under the
prefix `focus12-full/<export_name>/`. The `export_name` has to be the name the **renderer
emits** (`synthetic-focus12-daily-full`); `cloudpilot-focus12-daily-full` belongs to the
renderer from **before** the standalone publish (the one that wrote a `Manifest.json` into
the export) and **does not find the published keys** — measured in S4b3-A. The `aws-sim`
exposes the **same tree** through its REST S3 surface (the `aws_sim_render` volume,
`AWS_SIM_S3_STORE_DIR=/render/aws_focus`); the `s3mock` store is **in memory**, so
recreating the container empties the bucket and `aws-up.ps1` has to run again. Measured in
S4b3-A: the FOCUS/S3 tree was re-rendered in the **`medium`** profile (130.236 rows, 966
resources with billing), published and **ingested** — 58.926 rows / US$ 166,204.47 in the
homologation account's `/costs/unified`. Detail in
[regression/mapa-impacto-s4b3a.md](docs/regression/mapa-impacto-s4b3a.md).

**And the daily delivery (FR-22).** The generated day goes up to S3 through the official
mechanism (`tools.synthetic_clouds.deliver`), and it publishes into the **same namespace** the
consumer reads: bucket and export segment `synthetic-focus12-daily-full`, prefix
`focus12-full`. Before S4b3-B the delivery published into `cloudpilot-focus12-daily-full` — the
name of the renderer from **before** the standalone publish — and the day was generated, went
up to S3, the ingestion reported `status: ok`, and `/costs/unified` stayed **without AWS**: a
silent delivery. Measured in S4b3-B: delivery of day `2026-10-26` → **exit 0**, 1 new object at
`focus12-full/synthetic-focus12-daily-full/data/billing_period=2026-10/...` and **no**
`cloudpilot-focus12-daily-full` bucket created; official ingestion → `rows_promoted=54096`;
`/costs/unified` → `HOMOLOGATION AWS [sim] · 54,143.54` with
`data_source: focus_cost_records` (before: `cost: null`, `data_state: "unavailable"`). Detail in
[regression/mapa-impacto-s4b3b.md](docs/regression/mapa-impacto-s4b3b.md).

**And the delivery now runs on its own (S4b3-C).** The Windows task `simulador-nuvem-daily` is
**registered** — daily at 12:00 and on logon, with `StartWhenAvailable` — and the wrapper it runs
points at the **current path** (`tools/synthetic_clouds/schedule/run-daily.cmd`). The ledger
backlog was recovered through the mechanism itself (`schedule tick --deliver`): it generated and
delivered `2026-10-27` .. `2026-10-31` (5 days, 5 objects in the `s3mock` S3, 2,260–2,282 rows
per day in BigQuery, 304 estate days in the `azure-sim`), exit 0. The `2026-10-27` day, which had
been left **partial** (render interrupted, no `aws_focus`, out of the ledger), was rewritten in
full (45 surfaces). Official ingestion on the homologation account → **29,946 rows / US$ 65,575.88**
in `focus_cost_records`; `/costs/unified` → `HOMOLOGATION AWS [sim] · 65,575.88` with
`data_source: focus_cost_records`, and the volume agrees in all three places (parquet
`EffectiveCost` 65,575.879831 = ledger = `/costs/unified`). Detail in
[regression/mapa-impacto-s4b3c.md](docs/regression/mapa-impacto-s4b3c.md).

**And the test suite can no longer switch the task off.** The generated `run-daily.cmd` now belongs
to the **owner of the configuration** (`config_path.parent`), not to the package: the path used to
come from the *package* location, and a scheduler test wrote to that production path and deleted
it in its `finally` — running the suite switched the scheduled task off (`Last Result: 1`, with
nothing in the `task.log`, because the wrapper was not there to run). The fix is in
`tools/synthetic_clouds/schedule/windows.py` and keeps the production path identical. Detail in
[regression/mapa-impacto-s4b3c.md](docs/regression/mapa-impacto-s4b3c.md) §3.3.

**Debts on this front.** The Kubernetes plane **has** TLS since S4b2-E (own name
`opencost.synthetic-clouds.test`, with the SAN on the front's leaf), but still has **no** real
cloud hostname to imitate; `scripts/synthetic-clouds/up.ps1` does **not**
bring that plane up (it comes up with the integration, which owns the link); and
`docs/DECISOES-PENDENTES.md` still says the `k8s-sim` "has no Containerfile and no
compose service" — a sentence that became false at S4b2-B, in a file outside this
phase's allowlist, so the text was not corrected here. S4b3-C leaves a debt of the same
kind: `docs/AGENDAMENTO.en.md` (the English twin of the scheduling document) still says the
task is not registered and that the ledger stops at `2026-10-26` — it is **not** in the
phase's allowlist, so the text was not corrected here.

## Environment

```powershell
# the project's own interpreter (CPython 3.12)
& "C:\Users\ECUNHA\AppData\Local\Programs\Python\Python312\python.exe" -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -U pip
& .\.venv\Scripts\python.exe -m pip install pandas pyarrow pydantic pytest ruff mypy
```

The emulators have their own dependencies — `fastapi`/`uvicorn` in all of them,
`boto3` and `botocore` in the `aws-sim` tests — and each one pins its own
environment in the `Containerfile`; they do **not** run in the generator's
`.venv`.

`python -m tools...` finds the package from its own CWD and **does not** need
`PYTHONPATH`; only the scripts run by path (`specs\_tools\*.py`) do — and those
already insert the root into `sys.path` themselves.

### Generator verification

```powershell
# the spec contract and the readiness state (exit != 0 while there is a problem)
& .\.venv\Scripts\python.exe -m tools.synthetic_clouds.fidelity --ready
& .\.venv\Scripts\python.exe -m tools.synthetic_clouds.fidelity --matrix   # generated / missing / blocked
& .\.venv\Scripts\python.exe -m tools.synthetic_clouds.fidelity --audit aws # invented columns

# lint and types use the package's registered configuration: ALWAYS with --config
& .\.venv\Scripts\ruff.exe check tools\synthetic_clouds --config tools\synthetic_clouds\pyproject.toml
& .\.venv\Scripts\mypy.exe -p tools.synthetic_clouds --config-file tools\synthetic_clouds\pyproject.toml
& .\.venv\Scripts\python.exe -m pytest tools\synthetic_clouds\tests -q
```

**The suite is `pytest tools\synthetic_clouds\tests`.** `mypy` takes `-p`, not a
path: `mypy tools\synthetic_clouds` fails with *"Source file found twice under
different module names"* and **checks nothing**.

### The 20 skips in the suite are decisions, not failures

The skips come from two deliberate guards: the `real_parser` fixture loads the
**consumer** platform's CUR/FOCUS parser to check the round-trip — that platform
is not part of this repository, so the fixture **skips** when it is absent (the
guard is `pytest.skip`, not an error); and the GCP fixture tests **skip** when
the declared surface has no conditional label. Neither hides a failure: a skip
is not a passing test.

## Emulators

The stack comes up with `podman compose`. Each plane has its own fragment, and
`up.ps1` sequences the three cloud planes:

| Compose | Services | Host ports |
|---|---|---|
| `compose.yaml` | `azurite` + `azure-sim` | 8080 (API) · 10000 (blob) — 443/TLS inside the network |
| `compose.gcp.yaml` | `bigquery-emulator` + `gcp-bq-provision` + `gcp-sim` | 9050 (BigQuery REST) · 9060 (BigQuery gRPC) · 8085 (REST) · 8087 (gRPC) — the SCC gRPC (8088) and Azure's 443 are internal to the network |
| `compose.aws.yaml` | `s3mock` + `aws-sim` | 9090 (S3) · 8086 (Query/JSON) |
| `compose.tls-front.yaml` | nginx front | 443 (real hostnames, CloudPilot network) |

```powershell
cd deploy\synthetic-clouds
Copy-Item .env.example .env      # adjust the ports if needed
..\..\scripts\synthetic-clouds\up.ps1
```

The fourth emulator, `k8s-sim`, serves the OpenCost contract
(`/allocation/compute`, `/clusterInfo`, `/healthz`) from the versioned fixture
`k8s_sim/fixtures/clusters.json`. Since **S4b2-B** it has a `Containerfile` and a
compose service (`deploy/synthetic-clouds/compose.k8s.yaml`); since **S4b2-C** it is
**attached to the CloudPilot network** with the `k8s-sim` alias; and since **S4b2-E** the
CloudPilot backend reaches it over **HTTPS**, at
`https://opencost.synthetic-clouds.test` (the TLS front's own name — the plane imitates no
cloud hostname). The contract and the run
command are in
[`docs/k8s-sim-opencost-contract.md`](docs/k8s-sim-opencost-contract.md).

`gcp-sim` needs the rendered *fixtures* to answer; the `gcp-smoke.ps1` does the
whole cycle (render → provision → read).

For CloudPilot to talk to the stack through the **real hostnames** (DNS + local
TLS), use the idempotent automation in `deploy/synthetic-clouds/integration/`
(`cold-start.ps1`, `ensure-cloudpilot.ps1`) and read
[`docs/INTEGRACAO-CLOUDPILOT-TLS.md`](docs/INTEGRACAO-CLOUDPILOT-TLS.md).

### How the images are built

The **build context** is the root of this repository, and each `Containerfile`
copies **only** what it needs:

```dockerfile
COPY tools/synthetic_clouds      /app/tools/synthetic_clouds
COPY emulators/aws-sim           /app/emulators/aws-sim
```

The generator enters the image as the `tools.synthetic_clouds.*` namespace,
resolved by `PYTHONPATH=/app` — never as an installed wheel. No other directory
takes part in the build, and `k8s-sim` uses the **package itself** as its build
context (it imports no generator).

## Where to read more

| Document | What it is for |
|---|---|
| [`AGENTS.md`](AGENTS.md) | Operational contract for agents: how to run, what never to hand-edit, what to do when the evidence does not exist. |
| [`specs/README.md`](specs/README.md) | The contract that each `.md` spec and each `*.schema.json` must meet. |
| [`docs/ESTADO.en.md`](docs/ESTADO.en.md) | State of the simulator: what is ready, what is blocked and why, and what changed in each wave. |
| [`docs/NAO-COMPROVADOS.en.md`](docs/NAO-COMPROVADOS.en.md) | The 293 declared gaps, with the reason the spec records; derived from the specs. |
| [`docs/POSTURA-SEGURANCA.en.md`](docs/POSTURA-SEGURANCA.en.md) | The security checks of the generator and of the emulators. |
| [`docs/INTEGRACAO-CLOUDPILOT-TLS.md`](docs/INTEGRACAO-CLOUDPILOT-TLS.md) | Real hostnames, TLS, STS and the automation that survives a restart. |
| [`docs/k8s-sim-opencost-contract.md`](docs/k8s-sim-opencost-contract.md) | The `k8s-sim` `/allocation/compute` contract, with the source of each field. |
| [`docs/AGENDAMENTO.en.md`](docs/AGENDAMENTO.en.md) | Daily generation: schedule, lag, retention and the delivery to the emulators. |
| [`tools/synthetic_clouds/README.md`](tools/synthetic_clouds/README.md) | The generator in detail: structure, method and known traps. |
