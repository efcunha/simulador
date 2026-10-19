# Scheduling of the daily generation

> Language: **English** | [Português](AGENDAMENTO.md)

Operational document. It answers **how to configure the schedule**, **what happens when the
machine is turned off** and **what is still unresolved** — without repeating what is already in
[`ESTADO.md`](ESTADO.en.md).

## The problem this document solves

The simulator had the **capability** of generating day by day since FR-22: a *month-to-date*
window, deterministic by `(seed, profile, currency, dia)`, and a CLI
(`python -m tools.synthetic_clouds.daily --day YYYY-MM-DD`). What **did not exist** was anything
that would trigger it:

* no task in the Windows Task Scheduler (191 tasks in the system, none related);
* no scheduler in the code — neither cron nor APScheduler;
* and the proof that it never really ran: `out/daily/` did not exist. The only thing under
  `out/` was suite leftover (`out/pytest-daily/pid-*`).

The daily CLI requires an explicit date and refuses without one. In other words: the engine
existed, the ignition did not. This work is the ignition.

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
| `windows.py` | the registration in the Task Scheduler, so that the trigger comes from the operating system. |

`daily/` still reads no clock at all — that is what makes a day reproducible. Whoever asks "what
time is it" is the `runner`, and it converts the answer into an **explicit date** before handing
it to the generator.

### Why the target is yesterday, not today

`lag_days` (default **1**) is not slack: `clock.py` (FR-B2) documents that a charge for day `D`
is only exported on `D+1` at `00:00 UTC`. The most recent day whose export is complete at
today's date is therefore **yesterday**. Generating today would be asking for a day whose export
does not exist yet.

The parameter exists to be explicit, not to be adjusted without reason.

### Idempotence: why firing twice is harmless

The task has **two triggers** — the daily one at the configured time and one **on logon** — plus
`StartWhenAvailable`, which makes the Task Scheduler run the missed task as soon as the machine
comes back. Neither has to be exact, because the `tick` queries the ledger before generating:

| Situation | What happens |
|---|---|
| Fires again on the same day | `up-to-date`, nothing is generated |
| Machine off for N days | generates exactly the missing days, in order |
| Off for more than `backfill_max_days` (default 31) | generates the **N most recent** ones and **warns** how many were left out |
| Empty ledger (first run) | generates **one day** — the target. It does not dump a month of history |
| Clock went backwards (NTP, timezone change) | nothing is generated; `--force` is the only door |
| A day fails | the days already completed **stay recorded**; the error goes to the log and the exit code is 1 |

The first run generating a single day is deliberate: an empty ledger means "nothing was
generated", not "a month is missing". Generating history is an explicit act, and the daily CLI
already does that with `--from/--to`.

### Retention: why it exists and what it does not do

Measured: one day of the `small` profile with all the surfaces is **2,736 files / 61.3 MB**.
Without retention that is ~1.8 GB per month filling the disk silently — the classic failure mode
of an unattended job.

**This repository's installation has run on the `medium` profile since 2026-10-14** (decision in
[DECISOES-PENDENTES.md](DECISOES-PENDENTES.en.md#e3--volume-and-retention-with-the-new-schedule)).
Measured on the same day (`2026-10-13`, seed 123, USD, 19 surfaces): **12,006 files / 281.3 MB**,
3,330 resources, 49.4 s of build+render. The profile does not change the generated window (which
is *month-to-date*, derived from the day), and instead changes the **resource density**: 370 per
scope against 79. Practical consequence: the retention ceiling is ~4.6× that of the `small`
profile.

`retention_days = N` keeps the **N most recent days ending on the target day** and deletes the
older ones. The pruning runs on **every** tick, including the ones with nothing to generate: a
machine that is always up to date would never prune if pruning only happened along with a
generation.

The delicate point is the ledger. A deleted day is **removed from the ledger**, not kept as
"complete": `is_complete` cannot answer "yes" for a day whose artifact does not exist — that
would be the same lie in the opposite direction. And the day does not come back:

* the backfill only fills the hole **after** the most recent known day, so an old pruned day is
  never regenerated;
* if the pruning fails (file in use), the day **stays in the ledger** and the error is reported —
  the status of the run remains the one of the generation, because a cleanup failure is not a
  data failure.

```powershell
& $py -m tools.synthetic_clouds.schedule set --retention-days 30   # keep 30 days
& $py -m tools.synthetic_clouds.schedule set --retention-days none # go back to keeping everything
```

### Timezone: the configured one and the machine's

They are two different things, and confusing them is the classic mistake:

* `time_zone` decides **which day** a run belongs to (the day turns over in the configured
  timezone);
* the Windows Task Scheduler only understands **the machine's local time**, so the task is
  written at that time.

The `install` shows both readings and **warns** when the offsets diverge. If they diverge, what
guarantees the right day is the `tick`'s idempotence, not a coincidence of timezone.

If the machine is already in the configured timezone, the two readings coincide and there is
nothing to reconcile.

> On the first run of `init`, the default timezone is **UTC** with an explicit warning. The
> Python standard library does not convert the Windows identifier
> (*E. South America Standard Time*) into an IANA name, and the project **refuses to guess**:
> 06:30 UTC would be 03:30 in São Paulo, and a silent default would look like it had worked.

## Commands

```powershell
cd <repo-root>
$env:PYTHONPATH='<repo-root>'
$py = '.\.venv\Scripts\python.exe'

# 1. create the configuration and set the timezone and the time
& $py -m tools.synthetic_clouds.schedule init
& $py -m tools.synthetic_clouds.schedule set --time-zone America/Sao_Paulo --time 06:30
& $py -m tools.synthetic_clouds.schedule show

# 2. see what will be registered, without registering anything
& $py -m tools.synthetic_clouds.schedule install --dry-run

# 3. register the task  <-- this step requires PowerShell AS ADMINISTRATOR
& $py -m tools.synthetic_clouds.schedule install

# 4. check
& $py -m tools.synthetic_clouds.schedule status
```

> **Step 3 does NOT require administrator** — and the first version of this document said it
> did, which was wrong. Registration as a regular user works: it is how this project's task
> went live.
>
> The confusion came from a real defect in the XML. A `<LogonTrigger>` **without** `<UserId>`
> is an **all-encompassing** trigger — it would fire whenever *any* account logged on — and
> registering that is an administrative operation. `schtasks` answered "Access denied" and the
> symptom pointed at privilege, when the problem was the XML asking for too much. Limiting the
> trigger to the account (`<UserId>` in the `LogonTrigger` and in the `Principal`) makes the
> registration a regular user operation. Today `task_xml` **requires** the `user_id`: the
> whole-machine variant can no longer be built by omission.
>
> If a registration is denied, the message names that cause instead of sending you after a
> privilege that may not even be missing.

`tick` is what the task executes. Running it by hand is the way to test without waiting for the
scheduled time:

```powershell
# generates the day due now (yesterday, if lag_days=1)
& $py -m tools.synthetic_clouds.schedule tick

# generates a specific day, out of order
& $py -m tools.synthetic_clouds.schedule tick --date 2026-03-18

# redoes the target day even if it is already in the ledger
& $py -m tools.synthetic_clouds.schedule tick --force

# remove the task
& $py -m tools.synthetic_clouds.schedule uninstall
```

### Configuration fields

| Field | Default | What it does |
|---|---|---|
| `time` | `06:30` | time **in the `time_zone` timezone** |
| `time_zone` | `UTC` (with a warning) | IANA name, e.g.: `America/Sao_Paulo` |
| `seed` | `123` | generator seed |
| `profile` | `small` | `small` / `medium` / `large`. **`medium` is here** since 2026-10-14 — 281.3 MB/day against 61.3 MB of `small`. |
| `currency` | `USD` | `USD` / `BRL` |
| `lag_days` | `1` | export delay (FR-B2) |
| `backfill_max_days` | `31` | ceiling of days recovered in one run |
| `retention_days` | `null` (keeps everything) | how many days to keep; the oldest ones are deleted |
| `renderers` | `null` (all) | list of surfaces, or `null` for all |
| `enabled` | `true` | turns generation off without removing the task |

An unknown key is **refused**, not ignored: `"hour": "07:00"` next to `time` would make the job
run at the default time while the file states something else.

## Where the files live

Everything under `tools/synthetic_clouds/` — the project's write boundary (NFR-4). The CLI's
`tick` refuses a path outside it, and so does `save_config`.

| Path | What it is |
|---|---|
| `schedule/config.json` | the configuration (today: profile `medium`, 12:00 `America/Sao_Paulo`, retention 30) |
| `schedule/run-daily.cmd` | the wrapper the task executes (generated; do not edit by hand) |
| `schedule/<tarefa>.xml` | the task definition in XML (generated) |
| `out/daily/<YYYY-MM-DD>/<seed>-<profile>-<currency>/{canonical,render}/` | the day's artifacts |
| `out/daily/_state/state.json` | the ledger |
| `out/daily/_state/runs.log` | one JSON line per `tick` |
| `out/daily/_state/task.log` | stdout/stderr of the process triggered by Windows |

`state.json` and the logs carry clock instants, and that is deliberate: they are **operational**
records, not artifacts. Nothing written in them reaches a Parquet or an export JSON — the
artifacts remain byte-deterministic (there is a test that proves it: regenerating the same day
with `--force` reproduces the same hashes).

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

Verified in this project's real registration: `Hora da próxima execução: 15/10/2026 06:30:00`,
`Último resultado: 0`, and the daily trigger **fired on its own** in a test with an early time
(`runs.log` recorded the exact instant).

## Known limits — what this work does NOT solve

It is worth being explicit, so the document does not promise more than it delivers:

1. **Delivery to FinOps is still pending.** The artifacts are born inside
   `tools/synthetic_clouds/out/daily/`. Nothing is published to a bucket, MinIO or any place
   FinOps reads: there is no `boto3`, `minio` nor upload in the package, and the bridge that
   wrote to the product's database (`seed/`) was deliberately left out. Making the delivery
   happen is workstream **C** — and it depends on closing the ingestion points on the other
   side.
2. **10 of the 21 surfaces have no identified ingestion point** in `<ingestion-doc>.md`.
   Generating every day does not make those arrive anywhere until this is resolved on FinOps'
   side.
3. **Service coverage is workstream B.** The scheduler generates the 20 surfaces that exist; it
   does not create new surfaces. EKS/GKE/AKS and much of GCP's and Azure's services still have
   no artifact of their own — they show up only as a cost line.
4. **A scheduled task only runs with the user logged in** (or with the machine on, in the case
   of the logon trigger). A server that is off does not generate — and that is why the backfill
   exists.
5. **Retention is opt-in, and the default is to keep everything.** `retention_days` starts at
   `null`. Measured: one day of the `small` profile with all the surfaces is **2,736 files /
   61.3 MB** in **12.3 s**; one day of the `medium` profile is **12,006 files / 281.3 MB** in
   **49.4 s**. The installation done here was left with **30 days** — but that number was
   chosen when the profile was `small`, and **`medium` with 30 days asks for ~17 GB**
   (*month-to-date* windows of 13 to 31 days, average ~24–26). At the 2026-10-14T17:54
   reading, **`D:` has 26.67 GB free** — the ~17 GB ceiling fits (at the morning reading there
   were 12.10 GB, and it did not fit) —, and the decision of 2026-10-14 was to **keep the 30
   days for now, with a review marked** for when the accumulated usage approaches what is free:
   the risk is declared, not silent. `large` is out of the question on this disk (~4× the
   `medium`).

## Verification

```powershell
cd <repo-root>
$env:PYTHONPATH='<repo-root>'
& .\.venv\Scripts\python.exe -m pytest tools\synthetic_clouds\tests\test_schedule.py -q
```

The scheduler suite covers: invalid configuration (time, timezone, unknown key, boolean seed),
the write boundary, the ledger (version, corrupted JSON, key that is not a date), the backfill
plan (first run, on the day, hole, ceiling, clock backwards, explicit day), the `tick` with an
injected generator (idempotence, backfill, failure in the middle, disabled, log), the
registration on Windows (wrapper, XML, time conversion, rollover to the next day) and the
end-to-end CLI **with real rendering** — including the test that proves that a `--force`
reproduces the same bytes.
