"""Export the estate's Kubernetes clusters into the k8s-sim fixture.

**What this is.** A development tool. It reads the canonical ``resources.parquet``
of a generated estate and writes ``k8s_sim/fixtures/clusters.json`` -- the catalog of
the estate's Kubernetes clusters that the simulator serves.

**Why the fixture exists at all.** The ``k8s-sim`` service must not import the
generator at runtime: it is a standalone HTTP service, it has no estate to build,
and the whole point of its determinism is that the answer is a pure function of the
request. The cluster catalog is therefore a **versioned artifact**, derived from the
estate once, and read at runtime as data.

**What the fixture is derived from.** The canonical ``resources.parquet`` of the
``123-medium-USD`` profile (seed 123, profile ``medium``), filtered on the three
Kubernetes cluster resource types. Each record carries two identities:

- ``cluster_name`` -- the estate's ``resource_name``. This is the **contract's
  identity**: it is what the CloudPilot discovery returns and what the consumer
  sends back as ``filter=cluster:"<name>"``, and it is what the simulator
  publishes in ``properties.cluster`` and keys ``aggregate=cluster`` by. The
  generator writes noise into names (``TEMP-gke_cluster-0037``, ``gke_cluster-0357
  (do not delete)``), but that noise is part of the name the consumer really
  holds, so the simulator has to carry it verbatim.
- ``cluster_id`` -- the estate's canonical ``uuid``. It is the **auxiliary**
  identity: unique across the estate, and accepted as an *alias* of the name in
  the filter, never published as the identity.

A name is **not** unique across the estate: the 309 clusters carry 160 distinct
names, because the estate reuses a name across scopes (measured on the canonical
parquet of 2026-10-28). The catalog therefore keeps **every** cluster -- one
record per cluster of the estate -- and the name identifies the cluster within
its scope.

**When to regenerate.** Whenever the estate changes. The output is sorted by
``cluster_name`` (with ``cluster_id`` breaking ties) and carries no timestamp, so
regenerating it from an unchanged estate reproduces the file byte for byte -- a
diff in the fixture means the estate changed.

**Usage** (from the repository root)::

    .\\.venv\\Scripts\\python.exe emulators\\k8s-sim\\scripts\\export_clusters.py

Options: ``--parquet PATH`` to read a specific file, ``--out PATH`` to write
elsewhere. The default input is the most recent ``123-medium-USD`` canonical
``resources.parquet`` under ``tools/synthetic_clouds/out``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

#: The repository root, derived from this file's location:
#: ``<root>/emulators/k8s-sim/scripts/export_clusters.py``.
REPO_ROOT = Path(__file__).resolve().parents[3]

#: Where the generated estate keeps its canonical parquet files.
ESTATE_GLOB = "tools/synthetic_clouds/out/**/123-medium-USD/canonical/resources.parquet"

#: Where the fixture is written, relative to the repository root.
FIXTURE_PATH = "emulators/k8s-sim/k8s_sim/fixtures/clusters.json"

#: The resource types that are Kubernetes clusters, one per provider.
CLUSTER_RESOURCE_TYPES = ("eks_cluster", "gke_cluster", "aks_cluster")


def find_parquet(explicit: str | None) -> Path:
    """The canonical ``resources.parquet`` to read.

    An explicit path wins. Otherwise the most recently written ``123-medium-USD``
    canonical parquet under the estate output tree is taken.

    The choice of snapshot does not change the fixture: every ``123-medium-USD``
    snapshot of the estate carries the same 309 Kubernetes clusters with the same
    identities (measured over the snapshots of 2026-10-16..2026-10-27 and the
    ``gcp-plane`` snapshot).
    """
    if explicit:
        path = Path(explicit).resolve()
        if not path.is_file():
            raise SystemExit(f"export_clusters: no such parquet: {path}")
        return path

    matches = [path for path in REPO_ROOT.glob(ESTATE_GLOB) if path.is_file()]
    if not matches:
        raise SystemExit(
            "export_clusters: no estate parquet found. Generate the estate first "
            f"(looked for {ESTATE_GLOB} under {REPO_ROOT})."
        )
    return max(matches, key=lambda path: path.stat().st_mtime)


def read_clusters(parquet: Path) -> list[dict[str, str]]:
    """The estate's Kubernetes clusters, as the fixture's records.

    Each record carries exactly the four fields the fixture publishes: the
    ``cluster_name`` the consumer names the cluster by, the canonical
    ``cluster_id`` (the estate's ``uuid``), the ``provider`` that owns the cluster
    and the ``region_id`` it lives in. The records are sorted by name, with the
    id breaking ties, which makes the fixture reproducible from an unchanged
    estate.
    """
    import pyarrow.parquet as pq

    table = pq.read_table(parquet)
    columns = set(table.column_names)
    missing = {"uuid", "resource_name", "provider", "region_id", "resource_type"} - columns
    if missing:
        raise SystemExit(f"export_clusters: {parquet} has no column(s): {sorted(missing)}")

    records: list[dict[str, str]] = []
    for row in table.to_pylist():
        if row["resource_type"] not in CLUSTER_RESOURCE_TYPES:
            continue
        records.append(
            {
                "cluster_id": str(row["uuid"]),
                "cluster_name": str(row["resource_name"]),
                "provider": str(row["provider"]),
                "region_id": str(row["region_id"]),
            }
        )

    records.sort(key=lambda record: (record["cluster_name"], record["cluster_id"]))
    return records


def write_fixture(records: list[dict[str, str]], out: Path) -> None:
    """Write the fixture as a JSON array, sorted, with a trailing newline."""
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(records, indent=2, ensure_ascii=False) + "\n"
    out.write_text(payload, encoding="utf-8")


def summarize(records: list[dict[str, str]]) -> str:
    """A one-line-per-provider summary of what was written."""
    counts: dict[str, int] = {}
    for record in records:
        counts[record["provider"]] = counts.get(record["provider"], 0) + 1
    return "\n".join(f"  {provider}: {count}" for provider, count in sorted(counts.items()))


def main(argv: list[str] | None = None) -> int:
    """Read the estate, write the fixture, report what was written."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--parquet", default=None, help="the canonical resources.parquet to read")
    parser.add_argument("--out", default=None, help=f"where to write the fixture (default: {FIXTURE_PATH})")
    args = parser.parse_args(argv)

    parquet = find_parquet(args.parquet)
    records = read_clusters(parquet)
    if not records:
        raise SystemExit(f"export_clusters: {parquet} holds no Kubernetes cluster.")

    out = Path(args.out).resolve() if args.out else REPO_ROOT / FIXTURE_PATH
    write_fixture(records, out)

    print(f"export_clusters: read {parquet}")
    print(f"export_clusters: wrote {len(records)} clusters to {out}")
    print(summarize(records))
    return 0


if __name__ == "__main__":
    sys.exit(main())
