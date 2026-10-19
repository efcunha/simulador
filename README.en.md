# simulador — synthetic cloud generator + API emulators

> Language: **English** | [Português](README.md)

Standalone multi-cloud simulator. It generates all the data that is needed —
FinOps, security, network and instances — for **AWS, GCP and Azure**, and delivers it
following the export mechanism and format that **each cloud really uses**.

![Synthetic multi-cloud data, real API contracts](docs/img/hero.svg)

The repository has two parts:

| Part | Where | What it is |
|---|---|---|
| **Generator** | `tools/synthetic_clouds/` | Derives the artifacts from the cited specs; it holds the fidelity gates. |
| **Emulators** | `emulators/`, `deploy/`, `scripts/` | Serve the same data through each cloud's APIs (Query/S3 REST, ARM, GCP REST/gRPC). |

> The "Current state" numbers were measured on **2026-10-19**. The "How to measure"
> column says exactly which command reproduces each one — if a number diverges from
> the code, the command wins over the number.

## Current state

| Metric | Value | How to measure |
|---|---|---|
| Specified export surfaces | **46** — AWS 15 · GCP 21 · Azure 10 | `specs/**/*.schema.json` |
| **READY** export surfaces | **45** | `fidelity --ready` → `PRONTO: 45`, exit 0 |
| Blocked by the documentation | **1** — `azure/cost-management-export-cost-details` | `fidelity --matrix` → `bloqueado=1` |
| Missing | **0** | `fidelity --matrix` → `falta=0` |
| Invented column (any provider) | **0** | `fidelity --audit aws` → `com coluna inventada=0` |
| Tests | **1095 pass, 20 skip** (1115 collected) | `pytest tools\synthetic_clouds\tests --collect-only -q` |
| Specs in prose | **28** | `specs/<provider>/*.md` |
| Emulators | **3** — AWS · Azure · GCP | `emulators/` |
| Versioned files | **445** | `git ls-files` |

> On disk there are **447** files: the **445** versioned ones + `.publish-manifest.json`
> (a build artifact, outside git) + `tools/synthetic_clouds/schedule/simulador-nuvem-daily.xml`
> (ignored by the `.gitignore`).

The only blocked surface is a **deliberate refusal**, not a gap: Microsoft publishes
the 132 names without types, and none of them appears in the five contracts at the
same time. Generating it would require inventing a type and choosing a contract —
exactly what rule 3 below forbids. The reason is recorded in
`docs/NAO-COMPROVADOS.md`.

![Coverage, measured](docs/img/cobertura.svg)

## Inviolable rules

1. **Nothing outside this tree.** The simulator is autonomous: it writes to no third
   party database, container or repository, and never talks to the real cloud.
2. **Measured fidelity, not presumed.** Every field name, type, unit, date format,
   path layout and file type comes from the provider's **official documentation**,
   cited with URL and consultation date.
3. **No invented field.** Whatever is not documented is marked as `UNVERIFIED` and
   stays out of the generation until it is proven. There is no "seems reasonable"
   in this project.
4. **No credential and no billable call.** The simulator never talks to the real
   cloud. `aws-sim` still refuses to start if it detects real credential material
   in the environment (`emulators/aws-sim/aws_sim/guard.py`).

## Layout

| Path | Role |
|---|---|
| `specs/` | Export specifications per cloud, citing the official docs. **The source of truth.** |
| `specs/<cloud>/*.schema.json` | Machine-readable field inventory, derived from the spec and used by the fidelity tests. |
| `specs/_tools/` | Versioned audit utilities (provenance, columns per spec, URLs, generator of the unproven-items registry). |
| `tools/synthetic_clouds/` | The generator, with the fidelity engine and the test suite. |
| `docs/` | Method notes, decisions and audits. |
| `emulators/aws-sim/` | AWS emulator (Query + S3 REST) + `Containerfile`. |
| `emulators/azure-sim/` | Azure emulator (ARM + cost exporter) + `Containerfile`. |
| `emulators/gcp-sim/` | GCP emulator (REST + gRPC monitoring) + `Dockerfile`. |
| `deploy/synthetic-clouds/` | Composes and the stack `.env.example`. |
| `scripts/synthetic-clouds/` | Orchestration (`up`, `down`, `smoke`, `seed`, `export_once`). |

The `tools/synthetic_clouds` path is deliberate: the code self-imports as
`tools.synthetic_clouds` in 281 places, and moving it would require a mass rename with
no gain. The package's `ruff`/`mypy`/`pytest` configuration is in
`tools/synthetic_clouds/pyproject.toml` — **do not** create a config at the root.

## Method

The work advances in this order, always:

1. **Specify** — capture the official format in `specs/`, with the citation.
2. **Generate** — implement the renderer from the spec, never from memory.
3. **Prove** — fidelity test that compares the generated artifact against
   `specs/<cloud>/*.schema.json`: exact column set, order, units and formats.

An export surface is only considered ready when the three steps close.

## Architecture

![How the data flows](docs/img/pipeline.svg)

The path is always the same: the **spec** is the source of truth, the **generator** is
deterministic, the **emulators** serve the same data through each cloud's APIs, and
the **consumer** ingests through its own production path. The simulator never talks
to the real cloud at any point.

## What is emulated

![What is emulated, by domain](docs/img/dominios.svg)

Four domains — cost/FinOps, security, network and instances — in the three clouds.
Each cell corresponds to export surfaces with their own spec, generator and fidelity
test.

## Environment

```powershell
# the project's own interpreter (CPython 3.12)
& "C:\Users\ECUNHA\AppData\Local\Programs\Python\Python312\python.exe" -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -U pip
& .\.venv\Scripts\python.exe -m pip install pandas pyarrow pydantic structlog pytest ruff mypy
```

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

Ten of them come from the `real_parser` fixture, which loads the FOCUS parser of the
**consumer** platform to check the round-trip. That platform is not part of this
repository, so the fixture **skips** when it is not present (the guard is
`pytest.skip`, not an error). The other ten are the `integration` suite, which
requires a database.

## Emulators

The stack comes up with `podman compose`, from `deploy/synthetic-clouds/`:

```powershell
cd deploy\synthetic-clouds
Copy-Item .env.example .env      # adjust the ports if needed
..\..\scripts\synthetic-clouds\up.ps1
```

The three emulators answer on `localhost`:

| Emulator | Port | Health |
|---|---|---|
| `aws-sim` | 8086 | `GET /healthz` |
| `azure-sim` | 8080 | `GET /healthz` |
| `gcp-sim` | 8085 (REST) · 8087 (gRPC) | `GET /healthz` |

`gcp-sim` needs the rendered *fixtures* to answer; the `gcp-smoke.ps1` does the
whole cycle (render → provision → read).

### How the images are built

The **build context** is the root of this repository, and each `Containerfile`
copies **only** what it needs:

```dockerfile
COPY tools/synthetic_clouds      /app/tools/synthetic_clouds
COPY emulators/aws-sim           /app/emulators/aws-sim
```

The generator enters the image as the `tools.synthetic_clouds.*` namespace, resolved
by `PYTHONPATH=/app` — never as an installed wheel. No other directory takes part in
the build.

## Where to read more

| Document | What it is for |
|---|---|
| [`AGENTS.md`](AGENTS.md) | Operational contract for agents: how to run, what never to hand-edit, what to do when the evidence does not exist. |
| [`specs/README.md`](specs/README.md) | The contract that each `.md` spec and each `*.schema.json` must meet. |
| [`docs/ESTADO.en.md`](docs/ESTADO.en.md) | State of the simulator: what is ready, what is blocked and why. |
| [`docs/POSTURA-SEGURANCA.en.md`](docs/POSTURA-SEGURANCA.en.md) | The security checks of the generator and of the emulators. |
| [`tools/synthetic_clouds/README.md`](tools/synthetic_clouds/README.md) | The generator in detail: structure, method and known traps. |
