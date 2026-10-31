# Scheduling of the daily generation

> Language: **English** | [Português](AGENDAMENTO.md)
>
> Last updated: **2026-10-31** (revision `adbede44`, branch
> `feat/p76-security-posture-gcp-azure`).

Operational document. It answers **how to configure the schedule**, **what happens when the
machine is turned off** and **what is still unresolved** — without repeating what is already
in [`ESTADO.md`](ESTADO.en.md).

In the command blocks below:

```powershell
cd <repo-root>
$py = '.\.venv\Scripts\python.exe'
```

`python -m tools.synthetic_clouds…` resolves the package from the working directory:
**`PYTHONPATH` is not needed** for anything in this document. (The task wrapper sets it
because the Task Scheduler may start the process in another directory — see
[What the Windows task does](#what-the-windows-task-does).)

## The problem this document solves

The simulator had the **capability** of generating day by day since FR-22: a *month-to-date*
window, deterministic by `(seed, profile, currency, dia)`, and a CLI
(`python -m tools.synthetic_clouds.daily --day YYYY-MM-DD`). What **did not exist** was
anything that would trigger it (a situation measured on 2026-10-14, when the scheduler was
written):

* no task in the Windows Task Scheduler (situation measured on 2026-10-14: no related task
  in the system);
* no scheduler in the code — neither cron nor APScheduler;
* and the proof that it never really ran: `out/daily/` did not exist. The only thing under
  `out/` was suite leftover (`out/pytest-daily/pid-*`).

The daily CLI requires an explicit date (`--day`, or `--from`/`--to`) and refuses without
one. In other words: the engine existed, the ignition did not. This work is the ignition.

## How it works

```
config.json  ──►  tick  ──►  run_days(dia)  ──►  out/daily/<dia>/...
   (time,          │                                  ▲
    zone, seed)     └──►  state.json  (ledger)  ───────┘
                        records the completed day
```

Four modules in `tools/synthetic_clouds/schedule/`:

| Module | Responsibility |
|---|---|
| `config.py` | **when** to run and **with what**. Fail closed: a configuration that is not understood is refused at read time. |
| `state.py` | the ledger of what has already been generated. It is what gives idempotence. |
| `runner.py` | the `tick`. **The only place in the project that reads the wall clock.** |
| `windows.py` | the registration in the Task Scheduler, so the trigger comes from the operating system. |

`daily/` still reads no clock at all — that is what makes a day reproducible. Whoever asks
"what time is it" is the `runner`, and it converts the answer into an **explicit date**
before handing it to the generator.

## Two configuration levels: the factory default and this installation

Confusing the two is the mistake that makes an operator "fix" the code when they meant to
change the installation — or accept a default believing it is this repository's choice.

* **Factory default** is what `config.py` uses when there is no configuration: what a
  `schedule init` on a clean checkout writes. It is the reference and the validation floor,
  not the state of this machine.
* **Configuration of this installation** is `tools/synthetic_clouds/schedule/config.json`,
  **versioned** in this repository. It is what the scheduled task reads.

Reading of 2026-10-31 (`schedule show`):

```text
enabled              True
time                 12:00
time_zone            America/Sao_Paulo
lag_days             0
backfill_max_days    31
retention_days       30
seed                 123
profile              medium
currency             USD
renderers            None
```

The fields table, with both columns, is in
[Configuration fields](#configuration-fields).

### The target: why the default is yesterday and why this installation generates today

`lag_days` **is not slack**. `clock.py` (FR-B2) documents that a charge for day `D` is only
exported on `D+1` at `00:00 UTC`; that is why the **factory default** in `config.py` is
`lag_days = 1` and a tick targets yesterday. Generating today, under the FR-B2 model, would
be asking for a day whose export does not exist yet.

**This installation has run with `lag_days = 0` since 2026-10-26** (commit `1f674563`). The
reason is in the commit message:

* the demo dashboard needs to close on **"today"** — with lag 1, on day 27 the target is 26
  and day 27 itself is only born on the 28th;
* the simulator generates **complete, deterministic days** and delivery to the emulators is
  immediate, so there is no partial export to wait for;
* the delay stopped being a hole anyway since the consumer-side watermark backfill
  (`AZURE_FOCUS_INGEST_MAX_BACKFILL_DAYS`): if the machine stays off for days, the reader
  goes back to the last stored day.

In other words: FR-B2 remains true as the **rule of the data being emulated**, but it does
not force the simulator to deliver yesterday. To go back to the FR-B2 behaviour:

```powershell
& $py -m tools.synthetic_clouds.schedule set --lag-days 1
```

The parameter exists to be explicit — the difference between the default and the
installation is a recorded decision, not a silent adjustment.

### Idempotence: why firing twice is harmless

The task has **two triggers** — the daily one at the configured time and one **on logon** —
plus `StartWhenAvailable`, which makes the Task Scheduler run the missed task as soon as the
machine comes back. Neither has to be exact, because the `tick` queries the ledger before
generating:

| Situation | What happens |
|---|---|
| Fires again on the same day | `up-to-date`, nothing is generated |
| Machine off for N days | generates exactly the missing days, in order |
| Off for more than `backfill_max_days` (default 31) | generates the **N most recent** ones and **warns** how many were left out |
| Empty ledger (first run) | generates **one day** — the target (today with `lag_days=0`; yesterday with the default) |
| Clock went backwards (NTP, timezone change) | nothing is generated; `--force` is the only door |
| A day fails | the days already completed **stay recorded**; the error goes to the log and the exit code is 1 |

The first run generating a single day is deliberate: an empty ledger means "nothing was
generated", not "a month is missing". Generating history is an explicit act, and the daily
CLI already does that with `--from/--to`.

### Retention: why it exists and what it does not do

**Historical measurement, not the current state** (2026-10-13/14, seed 123, USD, **19
surfaces** — before the expansion to the current 49 surfaces): one day of the `small` profile
with every surface that existed then was **2,736 files / 61.3 MB**, in 12.3 s. Without
retention that is ~1.8 GB per month filling the disk silently — the classic failure mode of
an unattended job. Today's number is larger (more surfaces); the retention decision did not
change because of that.

**This repository's installation has run on the `medium` profile since 2026-10-14**
(decision in
[DECISOES-PENDENTES.md](DECISOES-PENDENTES.en.md#e3--volume-and-retention-with-the-new-schedule))
and with `retention_days = 30`. Measured on the same day (2026-10-13, seed 123, USD, 19
surfaces): **12,006 files / 281.3 MB**, 3,330 resources, 49.4 s of build+render. The profile
does not change the generated window (which is *month-to-date*, derived from the day), and
instead changes the **resource density**: 370 per scope against 79. Practical consequence:
the retention ceiling is ~4.6× that of the `small` profile.

`retention_days = N` keeps the **N most recent days ending on the target day** and deletes
the older ones. The pruning runs on **every** tick, including the ones with nothing to
generate: a machine that is always up to date would never prune if pruning only happened
along with a generation.

The delicate point is the ledger. A deleted day is **removed from the ledger**, not kept as
"complete": `is_complete` cannot answer "yes" for a day whose artifact does not exist — that
would be the same lie in the opposite direction. And the day does not come back:

* the backfill only fills the hole **after** the most recent known day, so an old pruned day
  is never regenerated;
* if the pruning fails (file in use), the day **stays in the ledger** and the error is
  reported — the status of the run remains the one of the generation, because a cleanup
  failure is not a data failure.

```powershell
& $py -m tools.synthetic_clouds.schedule set --retention-days 30   # keep 30 days (current state)
& $py -m tools.synthetic_clouds.schedule set --retention-days none # go back to keeping everything
```

### Timezone: the configured one and the machine's

They are two different things, and confusing them is the classic mistake:

* `time_zone` decides **which day** a run belongs to (the day turns over in the configured
  timezone);
* the Windows Task Scheduler only understands **the machine's local time**, so the task is
  written at that time.

The `install` shows both readings and **warns** when the offsets diverge. If they diverge,
what guarantees the right day is the `tick`'s idempotence, not a coincidence of timezone.

In this installation the configured zone is `America/Sao_Paulo`, which coincides with the
machine's zone — in that case the two readings coincide and the divergent-offset warning
does not fire.

> On the first run of `init`, the zone written is the **machine's**; when the Windows
> identifier (*E. South America Standard Time*) does not convert into an IANA name, the
> project **refuses to guess** and falls back to **UTC with an explicit warning** — 06:30 UTC
> would be 03:30 in São Paulo, and a silent default would look like it had worked.

## Commands

```powershell
# 1. configuration. In this checkout config.json ALREADY EXISTS and is versioned, and
#    `init` refuses to overwrite ("already exists; use `set` ..."). Reproducing this
#    installation's current config is the `set` below. On a checkout without config.json,
#    run `init` first.
& $py -m tools.synthetic_clouds.schedule set `
    --profile medium --time-zone America/Sao_Paulo --time 12:00 `
    --lag-days 0 --retention-days 30
& $py -m tools.synthetic_clouds.schedule show

# 2. see what will be registered, without registering anything
& $py -m tools.synthetic_clouds.schedule install --dry-run

# 3. register the task (no administrator needed — see the note below)
& $py -m tools.synthetic_clouds.schedule install

# 4. check
& $py -m tools.synthetic_clouds.schedule status
```

> **Step 3 does NOT require administrator** — and the first version of this document said it
> did, which was wrong. Registration as a regular user works: it is how this project's task
> went live on 2026-10-15.
>
> The confusion came from a real defect in the XML. A `<LogonTrigger>` **without** `<UserId>`
> is an **all-encompassing** trigger — it would fire whenever *any* account logged on — and
> registering that is an administrative operation. `schtasks` answered "Access denied" and
> the symptom pointed at privilege, when the problem was the XML asking for too much.
> Limiting the trigger to the account (`<UserId>` in the `LogonTrigger` and in the
> `Principal`) makes the registration a regular user operation. Today `task_xml`
> **requires** the `user_id`: the whole-machine variant can no longer be built by omission.
>
> If a registration is denied, the message names that cause instead of sending you after a
> privilege that may not even be missing.

`tick` is what the task executes. Running it by hand is the way to test without waiting for
the scheduled time:

```powershell
# generates the day due now (today with lag_days=0 in this installation; yesterday with the factory default)
& $py -m tools.synthetic_clouds.schedule tick

# generates a specific day, out of order
& $py -m tools.synthetic_clouds.schedule tick --date 2026-03-18

# redoes the target day even if it is already in the ledger
& $py -m tools.synthetic_clouds.schedule tick --force

# remove the task
& $py -m tools.synthetic_clouds.schedule uninstall
```

### Configuration fields

`config.py` defines the factory default; `config.json` (versioned) carries this
installation's choice. Both columns are measured, not estimated.

| Field | Factory default (`config.py`) | In this installation (`config.json`) | What it does |
|---|---|---|---|
| `time` | `06:30` | `12:00` | time **in the `time_zone` timezone** |
| `time_zone` | the machine's zone; `UTC` **with a warning** when it does not resolve | `America/Sao_Paulo` | IANA name, e.g.: `America/Sao_Paulo` |
| `seed` | `123` | `123` | generator seed |
| `profile` | `small` | `medium` | `small` / `medium` / `large`. The `medium` density is ~4.6× the `small` in volume. |
| `currency` | `USD` | `USD` | `USD` / `BRL` |
| `lag_days` | `1` (FR-B2) | `0` (since 2026-10-26, `1f674563`) | export delay; see [The target](#the-target-why-the-default-is-yesterday-and-why-this-installation-generates-today) |
| `backfill_max_days` | `31` | `31` | ceiling of days recovered in one run |
| `retention_days` | `null` (keeps everything) | `30` | how many days to keep; the oldest ones are deleted |
| `renderers` | `null` (all) | `null` (all) | list of surfaces, or `null` for all |
| `enabled` | `true` | `true` | turns generation off without removing the task |

An unknown key is **refused**, not ignored: `"hour": "07:00"` next to `time` would make the
job run at the default time while the file states something else.

## Where the files live

Everything under `tools/synthetic_clouds/` — the project's write boundary (NFR-4). The CLI's
`tick` refuses a path outside it, and so does `save_config`.

| Path | What it is |
|---|---|
| `schedule/config.json` | the configuration — **versioned**; today: profile `medium`, 12:00 `America/Sao_Paulo`, lag 0, retention 30 |
| `schedule/run-daily.cmd` | the wrapper the task executes (generated by `install`; git-ignored; do not edit by hand). It is written **next to the configuration that owns it** — see [the wrapper belongs to its configuration](#state-of-this-installation-reading-of-2026-10-31) |
| `schedule/<tarefa>.xml` | the task definition in XML (generated; git-ignored) |
| `out/daily/<YYYY-MM-DD>/<seed>-<profile>-<currency>/{canonical,render}/` | the day's artifacts |
| `out/daily/_state/state.json` | the ledger |
| `out/daily/_state/runs.log` | one JSON line per `tick` |
| `out/daily/_state/task.log` | stdout/stderr of the process triggered by Windows |

`state.json` and the logs carry clock instants, and that is deliberate: they are
**operational** records, not artifacts. Nothing written in them reaches a Parquet or an
export JSON — the artifacts remain byte-deterministic (there is a test that proves it:
regenerating the same day with `--force` reproduces the same hashes).

## State of this installation (reading of 2026-10-31)

`schedule status` is the cheap way to answer "what is happening". In this reading:

| Item | Reading |
|---|---|
| configuration | `medium`, 12:00 `America/Sao_Paulo`, `lag_days=0`, retention 30 (see above) |
| ledger | **16 days** generated, from `2026-10-16` to `2026-10-31`; last record `2026-10-31T13:06:48.390274-03:00` (`up-to-date`) |
| target now | `2026-10-31` |
| Windows task | **registered** (`simulador-nuvem-daily`): daily at `2026-11-01T12:00:00`, plus the logon trigger of `DESKTOP-38HP3S9\ECUNHA`, `StartWhenAvailable=true` |

The ledger is **up to date**: the target and the last generated day are the same day
(`2026-10-31`), and the last run was `up-to-date` — nothing was pending. The five days
between the previous reading (2026-10-26) and this one were closed by the backfill of the
run recorded at `2026-10-31T12:37:15` (`runs.log`), which generated `2026-10-27` through
`2026-10-31` in one batch.

The task **fires on its own**. The Task Scheduler reading of 2026-10-31 shows
`Horário da última execução: 31/10/2026 13:06:47` with `Último resultado: 0`, and
`runs.log` recorded the same instant — the daily trigger ran with nobody touching the
machine. The action it ran is `cmd.exe /c "...\schedule\run-daily.cmd"`, and the XML in
`schedule/simulador-nuvem-daily.xml` carries the two triggers and the user's account
(`StartBoundary 2026-11-01T12:00:00`).

### The wrapper belongs to its configuration

`run-daily.cmd` is written **next to the configuration that owns it**: `install` derives the
path from the `--config` file, not from the package. For this installation both live in
`schedule/`, so the path is unchanged — `schedule/run-daily.cmd`.

That detail is not cosmetic. Deriving it from the package instead made the **package** the
owner of a production file: the scheduler test suite wrote the real `run-daily.cmd` and its
cleanup deleted it, so running the tests silently removed the daily job's wrapper and the
task went back to failing with no trace in `task.log`. A test must not be able to delete
what the production task runs. The regression test that protects this lives in
`tests/test_schedule.py` — `test_the_plan_writes_the_wrapper_next_to_its_own_configuration`
and `test_the_suite_does_not_touch_the_production_wrapper`.

## Delivery to the emulators (`--deliver`)

The task's `tick` runs with `--deliver` (that is what `render_wrapper` writes into
`run-daily.cmd`): after generating the day, it delivers the day to the emulators that
CloudPilot reads through its **production connectors** (S3/CUR, BigQuery billing export and
Cost Management). Without that step the day exists on disk only.

| Target | What it does | Default endpoint |
|---|---|---|
| `aws` | uploads the FOCUS 1.2 to S3 at `<prefix>/<export_name>/data/billing_period=YYYY-MM/<execution>/...` | `http://localhost:9090` |
| `gcp` | deletes the day's rows and inserts the render's (`insertAll`) into the billing tables | `http://localhost:9050` |
| `azure` | extends the `azure-sim` estate window through the day **or through the current UTC day, whichever is greater** (`POST /admin/estate/refresh`) | `http://localhost:8080` |

```powershell
# deliver an already generated day (without generating it again)
& $py -m tools.synthetic_clouds.deliver --day 2026-10-23

# one target only
& $py -m tools.synthetic_clouds.deliver --day 2026-10-23 --targets aws,gcp
```

Delivery is **idempotent per day**: GCP deletes the day before inserting (so a
`tick --force` does not duplicate rows), AWS overwrites the same keys and Azure recreates the
same deterministic window. Endpoints, bucket and export name can be changed with
`DELIVERY_TARGETS` (default targets), `DELIVERY_AWS_ENDPOINT`, `DELIVERY_AWS_BUCKET`,
`DELIVERY_AWS_PREFIX`, `DELIVERY_AWS_EXPORT_NAME`, `DELIVERY_GCP_ENDPOINT`,
`DELIVERY_GCP_PROJECT`, `DELIVERY_GCP_DATASET`, `DELIVERY_AZURE_ENDPOINT`.

A delivery failure **does not undo** the day in the ledger (the data was generated and
recorded), but the `tick` exits with code 1 and the error goes to `task.log` — the task shows
up as failed instead of silencing a delivery that did not happen.

## What the Windows task does

| Item | Value |
|---|---|
| name | `simulador-nuvem-daily` (`--task-name` swaps it) |
| account | the one that registered (`DOMAIN\user`), with `InteractiveToken` and minimum privilege |
| triggers | daily at the configured time **+** on logon **of that account** |
| missed delay | `StartWhenAvailable=true` |
| simultaneous instances | `IgnoreNew` (two concurrent `tick` do not step on each other) |
| execution limit | 4 h |
| power | runs on battery and does not stop when switching to battery |

In the real registration of 2026-10-15, with the task registered, the Task Scheduler reading
showed `Hora da próxima execução: 15/10/2026 06:30:00`, `Último resultado: 0`, and the daily
trigger **fired on its own** in a test with an early time (`runs.log` recorded the exact
instant). **That is history**: since then the time changed to 12:00 (to match the delivery
window). The task **is registered** in this tree, and it fired on its own again on
2026-10-31 at 13:06:47 with `Último resultado: 0` — see
[State of this installation](#state-of-this-installation-reading-of-2026-10-31).

## Known limits — what this work does NOT solve

It is worth being explicit, so the document does not promise more than it delivers:

1. **Delivery to the emulators exists; ingestion on the FinOps side is still pending.** The
   task runs with `--deliver` and publishes the day to S3 (endpoint `localhost:9090`, the
   `s3mock` of this stack), BigQuery and Cost Management (see
   [Delivery to the emulators](#delivery-to-the-emulators---deliver)).
   The emulators are the **tip of the simulator**, not the consumer: how FinOps ingests each
   domain is in [`INGESTAO-D3-SEGURANCA.en.md`](INGESTAO-D3-SEGURANCA.en.md) (domain D3) and
   the general state in [`ESTADO.en.md`](ESTADO.en.md); the bridge that wrote to the
   product's database (`seed/`) was deliberately left out. Making ingestion happen is
   workstream **C**.
2. **Coverage: 49 specified surfaces, 47 generated and 2 blocked by the documentation**
   (reading of 2026-10-29, `fidelity --matrix` →
   `gerado=47 falta=0 bloqueado=2 total=49`). The blocked ones are
   `azure/cost-management-export-cost-details` (Microsoft publishes names without types) and
   `gcp/container-clusters` (it is an **API response** served live by `gcp-sim`, not an
   export file — there is no renderer that produces an artifact checkable against the spec,
   and without a renderer saying "implemented" would be a lie). The scheduler generates what
   exists; it does **not** create new surfaces.
3. **Services without an artifact of their own: this is workstream B.** EKS and AKS have no
   export surface — they are **APIs served live** by the emulators (`aws-sim` for
   EKS/EC2/S3/…, `azure-sim` for ARM/ContainerService/…). GKE has the
   `gcp/container-clusters` surface, but it is **blocked** precisely because it is an API
   response (`container.googleapis.com`, served by `gcp-sim`), not an export. Much of the
   rest of GCP's and Azure's services are the same: they show up in discovery and in the cost
   line, not as an export file.
4. **A scheduled task only runs with the user logged in** (or with the machine on, in the
   case of the logon trigger). A server that is off does not generate — and that is why the
   backfill exists.
5. **Retention is opt-in in the code, and this installation chose 30 days.**
   `retention_days` starts at `null` (keeps everything). The volume measurements above are
   **historical** (2026-10-13/14, 19 surfaces): today there are more surfaces, so the number
   per day is larger. The ~17 GB figure for `medium` with 30 days was computed on that
   measurement and remains the reference for the decision. The decision of 2026-10-14 was to
   **keep the 30 days for now, with a review marked** for when the accumulated usage
   approaches what is free. Reading of 2026-10-29: **`D:` has ~30.0 GB free**
   (32,264,364,032 bytes) — the estimated ceiling fits. `large` is out of the question on
   this disk (~4× the `medium`). The risk is declared, not silent.

## Verification

```powershell
& .\.venv\Scripts\python.exe -m pytest tools\synthetic_clouds\tests\test_schedule.py -q
```

The scheduler suite covers: invalid configuration (time, timezone, unknown key, boolean
seed), the write boundary, the ledger (version, corrupted JSON, key that is not a date), the
backfill plan (first run, on the day, hole, ceiling, clock backwards, explicit day), the
`tick` with an injected generator (idempotence, backfill, failure in the middle, disabled,
log), the registration on Windows (wrapper, XML, time conversion, rollover to the next day)
and the end-to-end CLI **with real rendering** — including the test that proves that a
`--force` reproduces the same bytes.

Two of those tests protect the ownership of the generated files: the plan writes the wrapper
**next to the configuration that owns it**, and the suite leaves the production
`schedule/run-daily.cmd` byte-identical (same content, same timestamp) — including when the
fix is reverted, in which case the test restores it instead of leaving the daily job
without its wrapper.
