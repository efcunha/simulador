# synthetic-clouds — azure-sim compose stack

Podman compose fragment for the Phase 2 `azure-sim` simulator plus an Azurite
blob backend. See `../../docs/synthetic-clouds/AZURE_SIM.md` for the operator and
Phase-4 integration reference; this README is the quick-start.

> **Podman, not Docker.** The compose uses the compose-spec schema that
> `podman compose` accepts. Commands below assume `podman compose`; swap in
> `podman-compose` if that is what your machine has.

## Services

| Service | Image / build | Port (container) | Volume |
|---|---|---|---|
| `azurite` | `mcr.microsoft.com/azure-storage/azurite` | `10000` (blob) | named `azurite-data` -> `/data` |
| `azure-sim` | built from `emulators/azure-sim/Containerfile` | `8080` (API) | none |

Both run on the dedicated bridge network `synthetic-clouds-net` and have
healthchecks. `azure-sim` starts only after `azurite` is healthy.

## Prerequisites

- Podman with a running machine (`podman machine start`).
- `podman compose` (or `podman-compose`).

## Run / stop

```bash
cd deploy/synthetic-clouds
cp .env.example .env            # optional — defaults work as-is
podman compose -f compose.yaml up -d
```

- API:   http://localhost:${API_PORT:-8080}  (health: `/healthz`)
- Blob:  http://localhost:${AZURITE_BLOB_PORT:-10000}/devstoreaccount1

Validate the compose schema without starting anything:

```bash
podman compose -f compose.yaml config
```

Stop (keep the named volume):

```bash
podman compose -f compose.yaml down
```

Stop and discard the Azurite data volume:

```bash
podman compose -f compose.yaml down -v
```

## Ports

Host ports are configurable via `.env` (`API_PORT`, `AZURITE_BLOB_PORT`); the
container ports are fixed (`8080` for the API, `10000` for Azurite blob). Change
only the host side if those ports are taken.

## Podman bind-mount caveat (hard constraint — design §6.4)

On this project's Windows + hyperv Podman machine, `D:\...:...` bind mounts fail
with `statfs ... input/output error`. **This stack never uses a `D:\` bind
mount.** Azurite persistence is a **named volume** (`azurite-data`). To seed or
extract files, use `podman cp` (wrapped by the helper scripts in
`scripts/synthetic-clouds/`), never a host bind.

The `azure-sim` image bakes the canonical generator in at build time, so it
needs no host mount to produce estates or exports.

## Trigger an export

With the stack up, run one export into Azurite:

```bash
pwsh -NoProfile -File ../../scripts/synthetic-clouds/export_once.ps1
```

Or directly:

```bash
podman compose -f compose.yaml exec azure-sim python -m azure_sim export --schedule one-time
```

## Configuration

All variables live in `.env` (template: `.env.example`). The simulator settings
block feeds `azure_sim/config.py`; the host-port block feeds compose only. The
**Phase-4 override contract** (`AZURE_MANAGEMENT_ENDPOINT`,
`AZURE_AUTHORITY_HOST`, `AZURE_BLOB_ENDPOINT`) is documented in `.env.example`
and `AZURE_SIM.md` — those are consumed by Phase 4's production clients, not by
this stack.
