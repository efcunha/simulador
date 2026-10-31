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

> **Status on 2026-10-29: the data reached the four renderers.** The model described here is
> implemented (`model/network.py` brings `NetworkSegment`, `NetworkInterface`, `NetworkFlow`,
> `NetworkSecurityGroup`/`SecurityRule` and the AWS/GCP families) and the **four flow log
> renderers project `NetworkFlow` today** — the surface stopped being "faithful and empty".
> Measured on this date:
>
> | Surface | What the artifact delivers today |
> |---|---|
> | `aws/vpc-flow-logs-s3` | all 54 columns are emitted; **18 always populated** + optional `instance-id`; one record per model flow (`tests/test_aws_security_network_fidelity.py:407-429`) |
> | `azure/nsg-flow-logs-v2` | the spec declares 39 names and **13 generatable**; `flowTuples` is a string with the positions in the documented order, flattened by the renderer; one record per flow window (`tests/test_azure_security_network_fidelity.py:986` and `:111`) |
> | `azure/vnet-flow-logs` | 127 names, **7 generatable** (the dates) — the ceiling is the **spec**, not the model (`tests/test_azure_security_network_fidelity.py:111`) |
> | `gcp/vpc-flow-logs-bigquery` | 181 paths, all generatable, **26 populated**; one record per GCP flow; the manifest records `records` = number of flows > 0 (`tests/test_gcp_security_network_fidelity.py:885-905`) |
>
> **Fixed on 2026-10-29.** The matrix note (`fidelity/matrix.py`) still said `format-only` and
> *"the manifest records records=0"* — a note that predated the network model and that the code
> (`render/gcp_flow_logs.py`) and the cited test already contradicted. In this round the entry was
> corrected: the surface is no longer classified as `format-only`, and the note now describes the
> **26 populated paths** and `records` > 0. The record stays here because the old note
> contradicted the artifact for as long as it was published.

Specification of what the simulator's model needs to carry so that the four flow log renderers
have **real data** to project. Written on 2026-10-14, derived from the specifications already
collected in `specs/` — no field here was invented; the "source" column says which spec each
group comes from.

It exists because column fidelity **is not** the same as data present: today the flow renderers
can come out faithful to the format with empty lists, since the canonical model has no type at
all for flow records.

*(The "today" of this sentence is 2026-10-14. Since then the model has the type and the four
renderers project it — see the status box at the top.)*

## The four surfaces, as each cloud actually delivers

| Surface | Documented delivery | Record shape | Fields |
|---|---|---|---|
| `aws/vpc-flow-logs-s3` | S3, gzip, text or Parquet | **named columns** | 54 |
| `azure/nsg-flow-logs-v2` | Blob, JSON, `PT1H.json` | envelope + **positional tuple** of 13 positions | 26 + 13 |
| `azure/vnet-flow-logs` | Blob, JSON | 23-field envelope + 13-position tuple, **plus** two analyzed-traffic tables (62 and 14) and the `blob-envelope` set (15) — **five** sets in the spec, **127** names summed | 127 |
| `gcp/vpc-flow-logs-bigquery` | Logging; BigQuery only as a **linked dataset** | named columns, many nested | 181 |

*(Correction of 2026-10-29: the sum cited before — 23 + 13 + 62 + 14 = 112 — did not add up to
the **127** in the "Fields" column. The spec declares **five** sets, and the fifth, `blob-envelope`,
has the 15 envelope names (the same `records`/`records[].time`… paths that the `blob` set also
names); 23 + 13 + 62 + 14 + 15 = **127**. Counted on this date in
`specs/azure/vnet-flow-logs.schema.json`.)*

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

*(Corrections of 2026-10-29, measured against the two specs: (1) Azure publishes **one** timestamp
per record — position 0 in both NSG v2 and VNet —, not a start/end pair; the model keeps the window
and the renderer derives the documented value. (2) The **decision does not exist** in the VNet
tuple: in the spec, NSG position 7 is `Traffic decision` while VNet position 7 is `Flow state`; the
VNet has no decision field. (3) The "region" row is the 2026-10-14 reading and coexists with the
correction in the next section: the ARM id does **not** carry the region — in NSG v2 there is no
region column, and in VNet the region visible in the blob path is the Network Watcher's
(`NETWORKWATCHER_{Region}`).)*

## Additional groups, by how many clouds carry them

**Reverse counters** (Azure NSG and VNet, positions 11–13: packets and bytes
received): `packets_reverse`, `bytes_reverse`. AWS expresses the reverse direction as
its own row, and GCP uses the `reporter` field (`SRC`/`DEST`) — the same flow can be reported by
both ends. They are three modelings of the same fact, and the model needs to keep enough for any
of them: who reported, and the counters of each direction.

**Flow state** (position **8** on the 0-based reading in NSG v2 and position **7** in VNet — the
VNet one comes before encryption): `B`
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

*(Correction of 2026-10-29: the estate **started modelling** both. `NetworkSegment` carries
`region_id`, `resource_group`, `network_security_group_id` and the `NetworkSecurityGroup` itself
(`model/network.py`), and the VNet is the `NetworkSegment` whose `segment_id` is the VNet's ARM id.
The sentence "does not model them" describes 2026-10-14.)*

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

**Status on 2026-10-29: implemented.** `model/network.py` has `NetworkSecurityGroup`
(subscription, resource group and rules ordered by priority) and `NetworkSegment` carries
`resource_group`, `network_security_group_id` and `network_security_group`;
`NetworkInterface.mac_address` exists, and the Azure blob path is assembled with
`RESOURCEGROUPS/{rg}`, `NETWORKSECURITYGROUPS/{nsg}` and `macAddress={mac}`
(`render/azure_nsg_flow_logs.py:255-274`). The four points this section listed as blockers have a
source today — the path segments stopped carrying the template token.

## Where the blockage is, per surface

Important correction relative to the first version: the blockage is **not the same** everywhere.
The table below was **re-measured on 2026-10-29**; the 2026-10-14 reading (which attributed a
model blockage to all four surfaces) stays recorded in the sentence above and in the note at the
end.

| Surface | What blocks it (2026-10-29) |
|---|---|
| `aws/vpc-flow-logs-s3` | **Nothing in the model.** All 54 columns come out in the artifact, **18 always populated** (`version`, `account-id`, `interface-id`, `srcaddr`/`dstaddr`, ports, `protocol`, `packets`, `bytes`, `start`/`end`, `action`, `log-status`, `vpc-id`, `subnet-id`, `region`, `flow-direction`) and optional `instance-id`; one record per model flow (`tests/test_aws_security_network_fidelity.py:407-429`). The other 36 (35 + the optional `instance-id`) remain empty because the model **does not carry the fact** (ECS, pre-NAT address, TCP flags, sub-location…), and empty is the correct answer. |
| `azure/nsg-flow-logs-v2` | **Nothing in the model.** The spec declares 39 names and **13 generatable** (`tests/test_azure_security_network_fidelity.py:111`); the record carries the 13 `flowTuples` positions flattened into the string, in the documented order. The 26 columns without a published type are positions inside a string — they are not JSON fields, so they do not enter as a column. |
| `azure/vnet-flow-logs` | **The spec**, not the model: 127 names, only **7 generatable** (the dates); the 120 blob fields are `example-only` and the lock refuses to derive a type for an undeclared field. Adding `NetworkFlow` does **not** unblock any new column here. |
| `gcp/vpc-flow-logs-bigquery` | **Nothing in the model.** 181 paths, all generatable, **26 populated**; one record per GCP flow (`tests/test_gcp_security_network_fidelity.py:885-905`). What still holds is the documented reading: the destination is **Cloud Logging**, and BigQuery is a linked dataset — the renderer emits the format, not an "export to BigQuery". |

*(The 36 AWS columns that are not always populated — 35 fixed + the optional `instance-id` — and
the 155 GCP ones — 181 − 26 — are the ones that depend on facts the model does not carry: service
metadata, RTT, `drop_reason`, GKE/PSC/load balancing. The closed list of what is populated is in the
cited tests, and it is closed on purpose: everything the spec publishes that is not in it must come
out empty.)*

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

*(The **implemented** type differs from this proposal, and the difference is measured on
2026-10-29 in `model/network.py:166`: the real `NetworkFlow` references the segment and the ends by
uuid (`segment_uuid`, `src_interface_uuid`, `dst_interface_uuid`) instead of keeping
`scope_id`/`region`/`interface_mac` in the flow; the MAC lives in `NetworkInterface`; and the flow
carries `account_id` and `log_resource_id`. The proposed `tcp_flags`, `address_family`,
`translated_*`, `reject_reason`, `acl_id`, `rule` and `log_status` fields **do not** exist in the
implemented type — that is why the corresponding columns come out empty in the artifact. The
proposal stays as the dated record of 2026-10-14.)*

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

**Status on 2026-10-29: the four decisions were taken together with the implementation**
(`generate/estate_builder.py:2256-2381`):

1. **Volume** — **12 windows of 5 minutes** (`FLOW_WINDOWS = 12`, `FLOW_WINDOW_MINUTES = 5`,
   `:492-493`), one flow per interface per window; the time window comes from `_flow_windows`.
2. **Address realism** — the IPs come from the estate's own `NetworkInterface` (`private_ip`), and
   the end that does not exist becomes `FLOW_ABSENT_ADDRESS`, never a plausible invented address.
3. **Relation to the gate** — the inventory → flow order is the code's
   (`_build_network` calls `_flows_for_segment` after creating the segment and interfaces), and the
   `model/network.py` docstring records the P2 gate rule (no orphans).
4. **Determinism** — each flow draws its randomness from its own stream, indexed by
   `(interface, window)`: `stream_rng(self.seed, f"flow/{interface_uuid}/{inicio}")`
   (`:2330`), so adding a flow does not shift the others.
