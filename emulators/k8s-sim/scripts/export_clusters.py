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
Kubernetes cluster resource types. Each record carries three identities:

- ``cluster_name`` -- the estate's ``resource_name``. This is the **published
  identity**: it is what the simulator publishes in ``properties.cluster`` and keys
  ``aggregate=cluster`` by. The generator writes noise into names
  (``TEMP-gke_cluster-0037``, ``gke_cluster-0357 (do not delete)``), but that noise
  is part of the name the consumer really holds, so the simulator has to carry it
  verbatim.
- ``cluster_id`` -- the estate's canonical ``uuid``. It is the **auxiliary**
  identity: unique across the estate, and accepted as an *alias* of the name in
  the filter, never published as the identity.
- ``native_id`` -- the id the provider's own discovery publishes: the EKS **ARN**
  (``arn:aws:eks:<region>:<account>:cluster/<name>``), the AKS **ARM resource id**
  (``/subscriptions/<guid>/resourceGroups/<rg>/providers/Microsoft.ContainerService/
  managedClusters/<name>``) and the GKE **selfLink**
  (``projects/<project>/locations/<region>/clusters/<name>``). It is the identity
  the CloudPilot consumer holds since the C-IDENT: the consumer keys its
  configuration by it and sends it back as ``filter=cluster:"<id>"``, so the
  simulator has to accept it. It is **unique across the estate** -- measured on the
  canonical parquet of 2026-10-27: 309 clusters, 309 distinct native ids -- so it is
  also what tells two homonyms in different scopes apart.

**The native id is computed by the discoveries' OWN projections, not reimplemented
here.** This script is a development tool, so it may import the emulator packages:
``aws_sim.projections.eks.cluster_arn``,
``gcp_sim.projections.container.cluster(...)["selfLink"]`` and
``azure_sim.projections.arm.resource_id_for``. That is what makes the value in the
fixture byte for byte the value the discovery publishes -- a reimplementation of the
three formats here could drift from them, and a drifted id is an id the consumer
does not hold. The rule the export follows is therefore: **ask the discovery**.

**A name is not unique across the estate**: the 309 clusters carry 160 distinct
names, because the estate reuses a name across scopes (measured on the canonical
parquet of 2026-10-28). The catalog therefore keeps **every** cluster -- one
record per cluster of the estate -- and the name identifies the cluster within
its scope, while the native id identifies it across the estate.

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
from typing import Any

#: The repository root, derived from this file's location:
#: ``<root>/emulators/k8s-sim/scripts/export_clusters.py``.
REPO_ROOT = Path(__file__).resolve().parents[3]

#: Where the generated estate keeps its canonical parquet files.
ESTATE_GLOB = "tools/synthetic_clouds/out/**/123-medium-USD/canonical/resources.parquet"

#: Where the fixture is written, relative to the repository root.
FIXTURE_PATH = "emulators/k8s-sim/k8s_sim/fixtures/clusters.json"

#: The resource types that are Kubernetes clusters, one per provider.
CLUSTER_RESOURCE_TYPES = ("eks_cluster", "gke_cluster", "aks_cluster")

#: The emulator packages whose projections compute the native cluster id. They are
#: siblings of this package, not dependencies of it: the ``k8s-sim`` service declares
#: only ``fastapi`` and ``uvicorn``, and this script is a development tool, so it
#: puts their roots on ``sys.path`` to reach the projections that own each format.
_EMULATOR_ROOTS = ("aws-sim", "gcp-sim", "azure-sim")

for _entry in (REPO_ROOT, *(REPO_ROOT / "emulators" / _name for _name in _EMULATOR_ROOTS)):
    if str(_entry) not in sys.path:
        sys.path.insert(0, str(_entry))

from aws_sim.projections import eks as eks_projection  # noqa: E402
from azure_sim.projections import arm as arm_projection  # noqa: E402
from gcp_sim.projections import container as container_projection  # noqa: E402


class _SeedOnly:
    """The one attribute the ARM projection reads off the estate.

    ``arm.resource_id_for`` reaches the estate for exactly one thing: the seed, which
    the Azure subscription GUID is minted from (``azure_subscription_guid``). Carrying
    only that attribute is enough to compute the ARM id, and it spares the export from
    rebuilding the whole estate (measured: ~36 s) to mint one GUID. The value is the
    snapshot's own seed, read from its ``meta.json`` -- never a guess.
    """

    def __init__(self, seed: int) -> None:
        self.seed = seed


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


def read_seed(parquet: Path) -> int:
    """The seed of the snapshot the parquet belongs to.

    The AKS native id carries the GUID of the Azure subscription, and that GUID is
    minted from the estate's seed (``azure_subscription_guid``). The seed is read from
    the snapshot's own ``meta.json`` sidecar -- the file the serializer wrote next to
    the parquet -- rather than assumed: a GUID minted from another seed would name a
    subscription that does not exist, and the id would be wrong in a way no reader
    could see.
    """
    meta_path = parquet.parent / "meta.json"
    if not meta_path.is_file():
        raise SystemExit(
            f"export_clusters: no meta.json beside {parquet} -- the snapshot's seed is "
            "unknown, and the AKS native id cannot be minted without it."
        )
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    seed = meta.get("seed")
    if not isinstance(seed, int):
        raise SystemExit(f"export_clusters: {meta_path} carries no integer seed.")
    return seed


def cluster_native_id(row: dict[str, Any], seed: int) -> str:
    """The id the provider's discovery publishes for the cluster this row describes.

    The estate's own ``Resource`` is rebuilt from the row -- the canonical parquet holds
    the estate's resources flattened into columns, and the projections that compute a
    native id all take a ``Resource`` -- and then the discovery's **own** projection is
    asked for the id. Nothing is reimplemented here: a reimplementation of the three
    formats could drift from the discoveries, and a drifted id is an id the consumer
    does not hold.

    One projection per provider:

    - EKS: the ARN ``DescribeCluster`` reports
      (``aws_sim.projections.eks.cluster_arn``).
    - GKE: the ``selfLink`` of the cluster row
      (``gcp_sim.projections.container.cluster``).
    - AKS: the ARM id of the ``managedClusters`` row
      (``azure_sim.projections.arm.resource_id_for``).

    The GKE ``selfLink`` is built from the project that owns the cluster, and the
    estate's ``parent_scope_id`` **is** that project (``gcp_sim.scope.resources_of_type``
    filters on it). The AKS ARM id carries the subscription GUID, which the seed mints.

    ``capacity_reservation`` is ``None`` for every cluster: the estate attaches one to
    a compute resource only (``ec2_instance``), and the parquet does not carry the
    column for the rest.

    The generator's model is imported **here**, inside the function, and not at module
    level: ruff classifies a module-level import differently depending on how the
    config was reached (``--config`` resolves the project root to the repository root,
    where ``tools`` is first-party; the hierarchical discovery resolves it to this
    package, where it is not). A local import is classified the same way either time
    -- the same solution ``emulators/gcp-sim/tests/test_provision.py`` uses.
    """
    from tools.synthetic_clouds.model.identity import ResourceIdentity
    from tools.synthetic_clouds.model.resource import Resource

    resource = Resource(
        identity=ResourceIdentity(
            uuid=str(row["uuid"]),
            logical_path=str(row["logical_path"]),
            provider=str(row["provider"]),
        ),
        parent_scope_id=str(row["parent_scope_id"]),
        service_name=str(row["service_name"]),
        service_category=str(row["service_category"]),
        resource_type=str(row["resource_type"]),
        resource_name=str(row["resource_name"]),
        region_id=str(row["region_id"]),
        region_name=str(row["region_name"]),
        tags=tuple(tuple(str(part) for part in pair) for pair in json.loads(str(row["tags"]))),
        sku_id=str(row["sku_id"]),
        capacity_reservation=None,
    )

    if resource.resource_type == "eks_cluster":
        return eks_projection.cluster_arn(resource)
    if resource.resource_type == "gke_cluster":
        return str(container_projection.cluster(resource, resource.parent_scope_id)["selfLink"])
    if resource.resource_type == "aks_cluster":
        arm_id = arm_projection.resource_id_for(_SeedOnly(seed), resource)  # type: ignore[arg-type]
        if arm_id is None:
            raise SystemExit(
                f"export_clusters: the ARM projection publishes no id for "
                f"{resource.resource_type!r}."
            )
        return arm_id
    raise SystemExit(f"export_clusters: no native id for {resource.resource_type!r}.")


def read_clusters(parquet: Path, seed: int) -> list[dict[str, str]]:
    """The estate's Kubernetes clusters, as the fixture's records.

    Each record carries the five fields the fixture publishes: the ``cluster_name``
    the consumer names the cluster by, the canonical ``cluster_id`` (the estate's
    ``uuid``), the ``native_id`` the discovery publishes, the ``provider`` that owns
    the cluster and the ``region_id`` it lives in. The records are sorted by name,
    with the id breaking ties, which makes the fixture reproducible from an unchanged
    estate.
    """
    import pyarrow.parquet as pq

    table = pq.read_table(parquet)
    columns = set(table.column_names)
    missing = {
        "uuid",
        "logical_path",
        "provider",
        "parent_scope_id",
        "service_name",
        "service_category",
        "resource_type",
        "resource_name",
        "region_id",
        "region_name",
        "tags",
        "sku_id",
    } - columns
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
                "native_id": cluster_native_id(row, seed),
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
    seed = read_seed(parquet)
    records = read_clusters(parquet, seed)
    if not records:
        raise SystemExit(f"export_clusters: {parquet} holds no Kubernetes cluster.")

    native_ids = [record["native_id"] for record in records]
    if len(set(native_ids)) != len(native_ids):
        raise SystemExit("export_clusters: two clusters share one native id -- the fixture would not be unique.")

    out = Path(args.out).resolve() if args.out else REPO_ROOT / FIXTURE_PATH
    write_fixture(records, out)

    print(f"export_clusters: read {parquet} (seed {seed})")
    print(f"export_clusters: wrote {len(records)} clusters to {out}")
    print(summarize(records))
    return 0


if __name__ == "__main__":
    sys.exit(main())
