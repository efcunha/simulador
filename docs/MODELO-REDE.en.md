# Canonical network model

> Language: **English** | [Português](MODELO-REDE.md)

> **Status (2026-10-14): implemented in the model.** `model/network.py` brings
> `NetworkSegment`, `NetworkInterface` and `NetworkFlow`; `estate_builder` generates the
> three with named streams; the gate rejects an orphan interface, a flow without an endpoint and
> vocabulary outside the canonical one; and `tests/test_network_model.py` proves
> determinism, id shape and the presence of the cloud marks.
>
> Order respected: **inventory first, flow after** — as this document
> argues. What is **missing** is the other side: the four flow log renderers still
> do not project this data, so they remain faithful to the format and empty. It is the next
> wave, and it is renderer work, not model work.

Specification of what the simulator's model needs to carry so that the four flow log renderers
have **real data** to project. Written on 2026-10-14, derived from the specifications already
collected in `specs/` — no field here was invented; the "source" column says which spec each
group comes from.

It exists because column fidelity **is not** the same as data present: today the flow renderers
can come out faithful to the format with empty lists, since the canonical model has no type at
all for flow records.

## The four surfaces, as each cloud actually delivers

| Surface | Documented delivery | Record shape | Fields |
|---|---|---|---|
| `aws/vpc-flow-logs-s3` | S3, gzip, text or Parquet | **named columns** | 54 |
| `azure/nsg-flow-logs-v2` | Blob, JSON, `PT1H.json` | envelope + **positional tuple** of 13 positions | 26 + 13 |
| `azure/vnet-flow-logs` | Blob, JSON | 23-field envelope + 13-position tuple, **plus** two analyzed-traffic tables (62 and 14) | 127 |
| `gcp/vpc-flow-logs-bigquery` | Logging; BigQuery only as a **linked dataset** | named columns, many nested | 181 |

Three consequences the model must respect:

1. **Azure delivers positionally, not by name.** `flowTuples` is a string with fields separated
   by commas. The model has to carry the fields; the renderer is who flattens them in the
   documented order.
2. **The `NTANetAnalytics` and `NTAIpDetails` tables are aggregations**, produced by
   traffic analytics — they are not raw records. The model must not feed them the same object:
   they are something else, and mixing them would be inventing semantics.
3. **GCP does not export to BigQuery.** The destination is Cloud Logging; BigQuery is a
   linked dataset. Recording this is not a detail: it changes what the renderer emits.

## The core: what the FOUR clouds carry

These fields exist, under their own name, in all four surfaces. They are the minimum a canonical
record needs to have in order not to come out empty in any of them.

| Canonical field | AWS | Azure NSG | Azure VNet | GCP |
|---|---|---|---|---|
| window start | `start` | position 0 | position 0 | `start_time` |
| window end | `end` | position 0 | position 0 | `end_time` |
| source IP | `srcaddr` | position 1 | position 1 | `connection.src_ip` |
| destination IP | `dstaddr` | position 2 | position 2 | `connection.dest_ip` |
| source port | `srcport` | position 3 | position 3 | `connection.src_port` |
| destination port | `dstport` | position 4 | position 4 | `connection.dest_port` |
| protocol | `protocol` | position 5 | position 5 | `connection.protocol` |
| direction | `flow-direction` | position 6 | position 6 | `connection_direction` |
| decision | `action` | position 7 | position 7 | `disposition` |
| packets | `packets` | position 9 | position 9 | `packets_sent` |
| bytes | `bytes` | position 10 | position 10 | `bytes_sent` |
| account / project | `account-id` | `systemId` | `flowLogResourceID` | `src_vpc.project_id` |
| log resource | `interface-id` | `resourceId` | `targetResourceID` | `src_vpc.vpc_name` |
| region | `region` | (in the `resourceId`) | (in the `targetResourceID`) | `src_location.region` |

## Additional groups, by how many clouds carry them

**Reverse counters** (Azure NSG and VNet, positions 11–13: packets and bytes
received): `packets_reverse`, `bytes_reverse`. AWS expresses the reverse direction as
its own row, and GCP uses the `reporter` field (`SRC`/`DEST`) — the same flow can be reported by
both ends. They are three modelings of the same fact, and the model needs to keep enough for any
of them: who reported, and the counters of each direction.

**Flow state** (NSG v2 position 8 on 0-based reading, and also in VNet): `B`
(begin), `C` (continued), `E` (end) — and **VNet adds `D`**. The spec numbers
1..13, so be careful with the counting when implementing.

**Encryption**: it exists, but **not in NSG v2** — the support table on the page itself
says "identification of virtual network encryption: Not supported" for the NSG. It is a **VNet**
position (9th, 1-based) and the `FlowEncryption` column in `NTANetAnalytics`. The AWS
`encryption-status` is the same fact in another cloud.

**Translated address** (AWS only: `pkt-srcaddr`, `pkt-dstaddr`): the pre-NAT address.
Without it, a flow behind NAT comes out incomplete.

**Interface MAC** (Azure: `flows[].mac`): Azure requires the MAC in each flow group,
and it becomes the **partition** (`macAddress=`) in the blob path. It is the only field that
Azure **mandates** and that AWS does not have.

**Rule identity** (Azure: `aclID` and `rule` in VNet; `rule` in NSG):
which rule allowed or denied. AWS does not carry the rule — it carries
`reject-reason` when it denies.

**Identity of the log resource** — watch the semantics, which I had assigned
wrongly in the first version of this document: the NSG `systemId` is the **network security group
GUID**, and the VNet `flowLogResourceID` is the **FlowLog resource id**. Neither of them is the
account/subscription. Projecting the `scope_id` into them would put a subscription id into a field
documented as a resource GUID. The same goes for the region: the ARM resource id **does not**
carry the region; it comes from the resource's `location` — which the estate has for the
resources it models and **does not** have for NSG and VNet, because it does not model them.

**TCP flags** (AWS `tcp-flags`), **address type** (AWS `type`: IPv4/IPv6),
**sub-location** (AWS `sublocation-type`/`sublocation-id`).

## What the model needs BEFORE the flow type

This is the part the first version of this document did not anticipate, and without it
`NetworkFlow` produces orphan data:

**Network resource inventory** — NSG, VNet, NIC and subnet, with ARM resource
id and resource group. Without it:

* `flow_record.log_resource_id` has nowhere to come from, and the project gate (P2,
  no orphans) rejects;
* the `RESOURCEGROUPS/{rg}` and `NETWORKSECURITYGROUPS/{nsg}` segments of the documented blob
  path have no value — today they carry the template's own token;
* the join keys that the ARM, the Resource Graph and the Defender use
  (`properties.networkInterfaces[].id`, `ResourceId`, `AssessedResourceId`) come out
  empty;
* there is no per-interface MAC, and without `interface_mac` there is no
  `macAddress=` partition that Azure requires in each flow group.

In other words: **first the network inventory, then the flow**. The flow hangs on the
inventory, just as the finding already hangs on the resource.

## Where the blockage is, per surface

Important correction relative to the first version: the blockage is **not the same** everywhere.

| Surface | What blocks it |
|---|---|
| `aws/vpc-flow-logs-s3` | the model: without network telemetry, 7 of the 54 columns have a value |
| `azure/nsg-flow-logs-v2` | the model. The `record` unblocks with `NetworkFlow` **and** network inventory — including the `flowTuples`, which is a generatable column and the renderer flattens in the documented order |
| `azure/vnet-flow-logs` | the **spec**, not the model. The ceiling is 7 date/time columns; the 120 blob fields are classified `example-only` and the lock refuses to derive a type for an undeclared field. Adding `NetworkFlow` does **not** unblock any new column here |
| `gcp/vpc-flow-logs-bigquery` | the model — and the destination is Cloud Logging, not BigQuery |

**Service metadata** — the most uneven group, and where it is easiest to invent:

| Cloud | What it documents |
|---|---|
| AWS | `traffic-path`, `pkt-src-aws-service`, `pkt-dst-aws-service`, `next-hop-*`, and a whole ECS block (`ecs-cluster-arn` … `ecs-task-id`) |
| GCP | `src_gke_details` (cluster, pod, workload), `src_serverless_details` (Cloud Run, App Engine), PSC, `load_balancing`, `internet_routing_details`, `src_google_service` |
| Azure | nothing equivalent in the raw record |

Practical consequence: in a record generated for AWS, the ECS fields stay
empty unless the workload is an ECS cluster; in a GCP record, the 40 PSC, GKE and serverless
fields stay empty unless the scenario produces them. **Empty is the correct answer** — the model
must not fabricate a GKE cluster to fill a column.

## Divergences between clouds that the renderer CANNOT uniformize

| Divergence | Detail | What to do |
|---|---|---|
| Protocol | Azure NSG uses `T`/`U`; AWS, VNet and GCP use the IANA number | The model keeps the number; each renderer converts to the shape of its own cloud. Not converting would be unfaithful; uniformizing in the artifact would be even more unfaithful. |
| Time granularity | Azure VNet uses **milliseconds**; NSG uses **seconds**; AWS and GCP use ISO 8601 | Preserve the unit documented per surface, do not normalize |
| Flow direction | AWS `flow-direction` (ingress/egress), Azure `traffic flow` (I/O), GCP `connection_direction` | Map to a canonical vocabulary and convert on output |
| Double counting | GCP has `reporter` per end; AWS emits one row per direction | The model needs to know who reported so as not to count the same flow twice |
| Aggregate vs raw | Azure's `NTANetAnalytics`/`NTAIpDetails` are aggregates | Do not feed them the same object as the raw flow |
| Log location | AWS `log-status`, Azure `category`/`operationName`, GCP `reporter` | They are not the same field; each has its own semantics |

## Type proposal

```python
@dataclass(frozen=True, slots=True)
class NetworkFlow:
    """Um registro de fluxo, no nível de detalhe que as quatro nuvens documentam."""

    flow_id: str                  # deterministic identity (UUIDv5)
    scope_id: str                 # account | subscription | project
    region: str
    log_resource_id: str          # interface-id | resourceId | vpc/subnet
    interface_mac: str | None     # Azure requires it; None where the cloud does not ask for it
    reported_by: str | None       # GCP reporter (SRC/DEST); who observed

    window_start: datetime        # UTC
    window_end: datetime          # UTC
    src_ip: str
    dst_ip: str
    src_port: int
    dst_port: int
    protocol_number: int          # IANA; the renderer converts to the cloud's shape
    direction: str                # canonical: ingress | egress
    decision: str                 # canonical: allowed | denied
    reject_reason: str | None

    packets: int
    bytes: int
    packets_reverse: int | None
    bytes_reverse: int | None

    flow_state: str | None        # B | C | E — NSG v2 only
    encryption: str | None
    tcp_flags: int | None
    address_family: str | None    # IPv4 | IPv6 (AWS `type`)
    translated_src_ip: str | None # AWS pkt-srcaddr
    translated_dst_ip: str | None
    acl_id: str | None            # Azure VNet
    rule: str | None              # Azure
    log_status: str | None        # AWS log-status
```

Usage rule: **the renderer emits the column and leaves it empty when the model does not have
the data**. What must not happen is filling it with a plausible value — that is exactly what this
project exists to prevent.

## What still needs to be decided before implementing

1. **Volume.** One record per flow per 5-minute window, for how many
   resources? AWS publishes every 5 minutes; Azure aggregates hourly in the blob. The
   `small` profile cannot turn into millions of rows.
2. **Address realism.** The IPs need to be consistent with the estate's VPCs,
   subnets and interfaces — a flow that leaves an interface that does not exist is orphan data,
   and the project gate (P2, no orphans) will reject it.
3. **Relation to the gate.** `validate/gate.py` requires findings and inventory to
   bind to an existing resource identity. Flows must follow the same rule.
4. **Determinism.** The flows need a randomness stream of their own, so as not to
   shift the numbers already stable in the other domains (there is a byte-to-byte stability test).
