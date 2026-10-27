"""Estate orchestration: hierarchy -> resources -> consumption -> ... -> estate.

Threads ONE ``ResourceIdentity.uuid`` end-to-end per resource (P2): the same uuid
appears on the resource, its daily consumption, its billing lines, its inventory
asset, any finding/recommendation/metric targeting it, and its IaC state. The
builder produces a base (pre-scenario) estate; ``scenarios/emit.py`` then applies
the 18 scenario INPUT conditions on top.

Realism (``realism.py``) and the base-cost model (``consumption.py``) are applied
here. All randomness flows through named ``stream_rng`` streams (determinism,
NFR-1).
"""

from __future__ import annotations

import hashlib
import math
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from tools.synthetic_clouds.clock import SimClock, export_time_for
from tools.synthetic_clouds.determinism import stream_rng
from tools.synthetic_clouds.generate import constants as const
from tools.synthetic_clouds.generate.constants import S3RegionalAccessSpec
from tools.synthetic_clouds.generate.consumption import daily_quantity
from tools.synthetic_clouds.generate.realism import (
    apply_untagged,
    duplicate_billing_lines,
    make_null_resource_line,
    off_standard_name,
)
from tools.synthetic_clouds.model.audit import (
    AwsAuditPosture,
    AwsCloudTrail,
    AwsSecurityHubEnrollment,
    AwsVpcFlowLog,
)
from tools.synthetic_clouds.model.billing import (
    BillingLine,
    ContractedPrice,
    DailyConsumption,
    ListPrice,
)
from tools.synthetic_clouds.model.capacity import CapacityReservation
from tools.synthetic_clouds.model.commitments import Commitment, Credit, Tax
from tools.synthetic_clouds.model.compute import STATE_RUNNING, STATE_STOPPED, InstanceProfile
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.hierarchy import (
    AwsAccount,
    AwsOrg,
    AzureMgmtGroup,
    AzureSubscription,
    BillingAccount,
    GcpFolder,
    GcpOrg,
    GcpProject,
)
from tools.synthetic_clouds.model.iac import IacResourceState, IacStateSnapshot, InventoryAsset
from tools.synthetic_clouds.model.iam import (
    AwsAccessKey,
    AwsIamUser,
    AwsIdentityPosture,
    AwsPasswordPolicy,
    AwsRootAccountMfa,
)
from tools.synthetic_clouds.model.identity import (
    IdentityFactory,
    ResourceIdentity,
    aws_account_id,
    aws_resource_id,
    azure_subscription_guid,
    capacity_reservation_id,
)
from tools.synthetic_clouds.model.invoice import Invoice, InvoiceLine
from tools.synthetic_clouds.model.metrics import MetricPoint, MetricSeries
from tools.synthetic_clouds.model.native import (
    ASSESSMENT_HEALTH_HEALTHY,
    ASSESSMENT_HEALTH_NOT_APPLICABLE,
    ASSESSMENT_HEALTH_UNHEALTHY,
    AzureDefenderAssessment,
    NativeFinding,
    NativeRecommendation,
)
from tools.synthetic_clouds.model.network import (
    AWS_DEFAULT_SECURITY_GROUP_DESCRIPTION,
    AWS_DEFAULT_SECURITY_GROUP_NAME,
    DECISION_ALLOWED,
    DECISION_DENIED,
    DIRECTION_EGRESS,
    DIRECTION_INGRESS,
    GCP_FIREWALL_INGRESS,
    GCP_FIREWALL_LOG_INCLUDE_ALL,
    AwsIpPermission,
    AwsIpRange,
    AwsSecurityGroup,
    GcpFirewallEntry,
    GcpFirewallRule,
    NetworkFlow,
    NetworkInterface,
    NetworkSecurityGroup,
    NetworkSegment,
    SecurityRule,
)
from tools.synthetic_clouds.model.resource import Resource
from tools.synthetic_clouds.model.storage import (
    AwsAclOwner,
    AwsBucketGrant,
    AwsBucketPolicy,
    AwsBucketPosture,
    AwsPolicyStatement,
    AwsPublicAccessBlock,
    AwsRegionalAccessBlock,
)
from tools.synthetic_clouds.render.markers import (
    FICTIONAL_DOMAIN,
    RECOMMENDATION_MODEL,
    SOURCE_SYNTHETIC,
    source_fingerprint,
    synth_name,
    synthetic_evidence,
    synthetic_metadata,
)

_MIDDAY = time(12, 0, 0)
_BASE_DAILY_UNITS = Decimal("24")
# The window every caller generated before FR-22 existed. Naming it turns
# ``build_estate``'s hardcoded first day into a default, which is what makes the
# window a parameter without moving a single existing byte: with ``sim_start`` unset
# the clock is identical to the literal it replaced.
CANONICAL_EPOCH = date(2026, 1, 1)
# How far into the window a finding may be dated. A finding whose day is still in the
# future is not emitted yet, so a month-to-date window shows alerts accumulating
# across the month rather than all of them on day one (FR-22.3). Bounded by the
# shortest profile window (45 days) so the default build never drops a finding.
RAISED_ON_SPAN_DAYS = 30
# Measured end-to-end row expansion from base billing lines to the final
# post-scenario FOCUS row count (duplicates + C05 + C15 k8s split + C17 + C18 +
# the AWS A01/A10 append lines). Used to size the base so the FINAL count lands
# in the AC-17 band.
#
# Re-measured at 1.25 for the three-provider (Azure + GCP + AWS) composition. The
# previous 1.4 was measured with two providers and under-sized the base once AWS
# joined: the small profile landed 7 rows BELOW the AC-17 floor (35993 against
# [36000, 44000]). At 1.25 the small profile lands at 40108 — mid-band. This ratio
# depends on the provider count, so re-measure when it changes rather than
# widening the band.
_SCENARIO_EXPANSION = 1.25
# Scopes each provider contributes. The per-scope resource count is derived from
# the TOTAL scope count (see ``_resources_per_scope``) so the post-scenario FOCUS
# row band (AC-17 / OA-8) holds regardless of how many providers the estate
# carries — previously the total was the literal ``6``.
_SCOPES_PER_PROVIDER = 3

# ── metering ─────────────────────────────────────────────────────────────────
#
# Which resource types carry a ``MetricSeries``, and therefore which ones a provider's
# observability endpoint can answer about. The set is driven by the CONSUMERS, not by
# the catalog: a type is metered only when the reader that would ask for it exists and
# the projection that would answer it can name the metric honestly. Metering a type no
# reader asks for buys nothing; metering a type no projection can name forces the
# projection to guess a namespace, which is the fabrication the estate forbids.
#
# Each entry, and the fact that justifies it:
#
#   * ``virtual_machine`` / ``sql_database`` (Azure), ``compute_instance`` / ``cloud_sql``
#     (GCP) — the four types this module metered before the AWS slice joined. Two
#     renderers project them: ``render/gcp_rest_fixtures.py::_MONITORED_RESOURCE`` maps
#     the GCP pair onto Cloud Monitoring descriptors, and the Azure metric readers take
#     ``virtual_machine`` / ``sql_database`` (``coverage/inventory.py`` records the two
#     evidence sites).
#
#   * ``ec2_instance`` and ``rds_instance`` (AWS) — the two types the two AWS consumers
#     AGREE on, which is a tighter test than either alone:
#
#       - what the shim can answer:
#         ``emulators/aws-sim/aws_sim/projections/cloudwatch.py::_NAMESPACE`` can express
#         exactly these two families (``AWS/EC2`` dimensioned by ``InstanceId``, ``AWS/RDS``
#         by ``DBInstanceIdentifier``), plus ``CWAgent`` for ``ec2_instance``'s memory
#         series. The shim derives the namespace from the RESOURCE and the METRIC, so no
#         namespace column is needed on ``MetricSeries`` — see the note below.
#
#       - what the client asks for:
#         ``aws_metrics.py (modulo do consumidor)`` builds its queries from the
#         ``aws_ec2`` / ``aws_rds`` dashboard templates
#         (``templates.py (modulo do consumidor)``), which carry those same two namespace/dimension
#         pairs, and the rightsizing path (``<modulo do consumidor>/
#         cloudwatch_metrics_provider.py``) asks ``AWS/EC2`` + ``CPUUtilization`` +
#         ``InstanceId`` for the CPU percentiles. ``service_discovery.py (modulo do consumidor)``
#         fills the dimension value with the id ``DescribeInstances`` /
#         ``DescribeDBInstances`` reported — and both projections report the estate's
#         ``resource_name`` as that id, so the value the shim answers with is the value
#         the client just sent.
#
#     The other AWS catalog types are deliberately NOT metered: ``lambda_function``,
#     ``application_lb``, ``ecs_cluster``, ``dynamodb_table`` and ``s3_bucket`` are read
#     by clients whose namespaces ``_NAMESPACE`` does not map, so a series for them would
#     be data no endpoint could report.
#
# ``MetricSeries`` carries only ``metric_name`` because that is sufficient: the namespace
# and the dimension name are a function of the resource the series points at (through
# ``resource_uuid``) and of the metric, and both consumers already derive them that way
# (the shim from ``_NAMESPACE``, FinOps from its template registry and its metrics
# provider). Adding a namespace column would duplicate those onto every point's series.
#
# The metric vocabulary is the estate's own; each consumer maps it into its provider's
# naming (``_METRIC_NAME`` maps ``cpu_utilization`` -> ``CPUUtilization``).
_METERED_RESOURCE_TYPES: frozenset[str] = frozenset({
    "virtual_machine",
    "sql_database",
    "compute_instance",
    "cloud_sql",
    "ec2_instance",
    "rds_instance",
})

_CPU_UTILIZATION = "cpu_utilization"

#: The memory series, metered only for the AWS type the rightsizing consumer asks memory
#: for — see the ``memory_utilization`` domain below.
_MEMORY_UTILIZATION = "memory_utilization"

#: Which metered types carry a ``memory_utilization`` series.
#:
#: One entry, and it is the consumer's own scope rather than the catalog's:
#: ``rightsizing_detector.py (modulo do consumidor)::_inventory_to_specs`` builds
#: ``ResourceSpec`` rows from ``inventory["EC2"]`` only, so an ``rds_instance`` (or any
#: Azure/GCP type) is never handed to a metrics provider that would ask for memory. A
#: memory series for a type nobody asks memory about is data no reader consumes.
_MEMORY_METERED_RESOURCE_TYPES: frozenset[str] = frozenset({"ec2_instance"})

# ── the metric cadence: HOURLY (24 points per day) ────────────────────────────
#
# Every series is sampled once per HOUR of every simulated day, on the hour, in UTC.
# That is the grain the consumer reads at, so it is the grain the estate has to
# report: ``cloudwatch_metrics_provider.py (modulo do consumidor)`` queries
# CloudWatch with ``Period=3600`` and then prices the window in the same unit —
#
#     expected_samples = max(1, int((end - start).total_seconds() // 3600))  # HOURS
#     telemetry_coverage_percent = min(100.0, sample_count / expected_samples * 100)
#     if telemetry_coverage_percent < settings.MIN_COVERAGE_PERCENT:
#         return None
#
# — so a series carrying ONE point per day is structurally capped at 1/24 = 4.17%
# coverage and is refused before the analyzer ever sees it. No daily cadence can pass
# that floor, which is exactly how the AWS right-sizing path came out empty. The
# estate's "one point per day at noon" was the deviation, not the norm.
#
# 24 samples a day is also the day the estate already bills these resources on: every
# type in :data:`_METERED_RESOURCE_TYPES` is priced in ``Hours`` on a 24-unit day base
# (:data:`_BASE_DAILY_UNITS`), so the meter and the bill stop describing one resource-day
# in two different ways.
_METRIC_HOURS_PER_DAY = 24

#: The intra-day shape: one multiplier per UTC hour (index 0 = 00:00), applied to the
#: sample drawn from that resource's workload band. Without it the day would be 24
#: draws from one band with no structure at all, which is not what a meter reports: a
#: machine does not carry the same load at 04:00 and at 15:00.
#:
#: The curve is a single smooth diurnal cycle — ``0.55`` at its 03:00 trough, rising
#: to exactly ``1.0`` at its 15:00 peak (a ~1.8x swing, the ordinary business-hours
#: shape) — and both endpoints matter to a consumer:
#:
#: * **the peak is normalized to 1.0**, because ``RightsizingAnalyzer`` judges a
#:   resource on the window's PEAK sample (``avg_cpu_pct`` is fed the CloudWatch p95
#:   and ``_fetch_metrics`` keeps the ``max()``). With the peak factor at 1.0 the
#:   series maximum stays at the top of the resource's band, which is the ceiling
#:   :data:`_CPU_UTILIZATION_BANDS` / :data:`_MEMORY_UTILIZATION_BANDS` were placed
#:   against — the mixture keeps deciding the verdict, and a factor above 1.0 would
#:   push every band over its threshold and give the whole estate one answer again.
#: * **the trough is 0.55, not 0.0**, because the low point of a running instance is
#:   idle overhead, not a shutdown, and the estate's idle classes
#:   (``dormant`` / ``under-used``) have to stay reachable at their own peak hour.
#:
#: One shared curve for the whole estate on purpose: the estate models no per-region
#: or per-resource timezone, so a per-resource phase would assert something it does
#: not know AND cost a second draw on each resource's stream. The per-resource drawing
#: that DOES carry meaning is the workload band, one draw before the samples.
_METRIC_INTRADAY_SHAPE: tuple[float, ...] = tuple(
    round(0.55 + 0.45 * (1.0 + math.cos(2.0 * math.pi * (hour - 15) / 24.0)) / 2.0, 6)
    for hour in range(_METRIC_HOURS_PER_DAY)
)


def _metric_grid(days: list[date]) -> tuple[tuple[datetime, float], ...]:
    """Every ``(timestamp, intra-day factor)`` the meter reports for ``days``, in order.

    One entry per hour of every simulated day: the day's hours in ascending order,
    the on-the-hour UTC instants within them, and the shape factor that hour carries.
    The order IS the draw order ``_build_metrics`` uses, so a series stays a pure
    function of ``(seed, resource, position in the window)``.
    """
    return tuple(
        (
            datetime.combine(day, time(hour, 0, 0), tzinfo=UTC),
            _METRIC_INTRADAY_SHAPE[hour],
        )
        for day in days
        for hour in range(_METRIC_HOURS_PER_DAY)
    )


# ── the ``cpu_utilization`` domain ────────────────────────────────────────────
#
# A sample is a PERCENTAGE of the resource's CPU capacity (0..100), which is what every
# consumer of this series declares it to be:
#
#   * ``emulators/aws-sim/aws_sim/projections/cloudwatch.py`` maps the estate's
#     ``cpu_utilization`` onto CloudWatch ``CPUUtilization`` and answers ``float(point.value)``
#     unchanged, while the callers asking for it declare ``"Unit": "Percent"``:
#     ``aws_metrics.py (modulo do consumidor)``'s ``(namespace, metric) -> unit`` table
#     and its ``templates.py`` dashboard registry both say ``Percent`` for ``CPUUtilization``
#     on ``AWS/EC2`` and ``AWS/RDS``, and
#     ``cloudwatch_metrics_provider.py (modulo do consumidor)`` sends that unit verbatim.
#   * ``emulators/azure-sim/azure_sim/projections/metrics.py`` labels the same series
#     ``("CPU utilization", "Percent")`` and copies ``point.value`` into Monitor's datapoint
#     ``average``.
#   * ``render/gcp_rest_fixtures.py`` reports it as the ``doubleValue`` of a Cloud Monitoring
#     point, the field the GCP metric readers take as a percentage.
#
# None of them rescales or re-labels, so the value emitted here IS the percentage the
# operator reads. This module used to emit a FRACTION (``uniform(0.02, 0.9)``) underneath
# those ``Percent`` declarations — off by 100x, and read by the rightsizing analyzer as an
# estate in which every metered resource sits below 1% CPU.
#
# The bands below are a per-resource mixture rather than one uniform percentage range,
# because the consumers decide on the resource's PEAK sample, not on its typical one.
# ``RightsizingAnalyzer(cpu_threshold_pct=20.0)``
# (``analyzer.py (modulo do consumidor)``) refuses to flag a resource whose
# ``avg_cpu_pct >= 20``, and that field is filled with the CloudWatch **p95**
# (``cloudwatch_metrics_provider.py`` passes ``avg_cpu_pct=cpu_p95`` and ``_fetch_metrics``
# keeps ``max()`` over the datapoints). The shim buckets this series hour by hour, one
# sample per hourly bucket, so the figure the detector compares is the resource's highest
# hourly sample in the window — its peak hour. One uniform 0..100 range would therefore
# push every resource toward the top of the range and hand the whole estate a single
# verdict — a detector that cannot be shown to discriminate. A band per resource makes the
# verdict a property of the resource, which is what the mixture encodes.
#
# Each ``(weight, low, high)`` entry is a workload class, placed so it lands on one side of a
# threshold the consumers genuinely apply:
#
#   * ``dormant`` — under the 20% rightsizing threshold and under ``_classify_severity``'s
#     HIGH ceiling (8%): the idle machine rightsizing exists to find, and what an unclaimed
#     box that boots, holds its licence and serves nothing looks like;
#   * ``under-used`` — ``_classify_severity``'s MEDIUM band (8, 14]: dev/test and low-traffic
#     services;
#   * ``low-traffic`` — its LOW band (14, 20): flagged, but a downsize call at the edge;
#   * ``steady`` — ordinary production, above 20%, so the analyzer refuses to flag it. This
#     half is what makes a finding mean anything: a wholly idle estate cannot show whether
#     the detector discriminates;
#   * ``saturated`` — 60..88%: the busy end, so the estate also carries machines whose
#     correct verdict is "do not downsize".
#
# The three flagged classes total 30% of resources, and the split also straddles
# ``seed.py (modulo do consumidor)``'s ``input.metrics.cpu_utilization_avg_7d < 10``
# idle rule with resources on both sides of it.
#
# The band is drawn from the resource's OWN ``metric/<uuid>`` stream and costs exactly one
# draw before its samples, so a resource's class and its samples stay a pure function of
# ``(seed, resource, day index)``.
_CPU_UTILIZATION_BANDS: tuple[tuple[float, float, float], ...] = (
    (0.08, 0.4, 7.5),
    (0.10, 8.5, 13.5),
    (0.12, 14.5, 19.5),
    (0.50, 25.0, 55.0),
    (0.20, 60.0, 88.0),
)


def _cpu_utilization_band(rng: random.Random) -> tuple[float, float]:
    """Return the ``(low, high)`` percent band the resource drawn from ``rng`` belongs to.

    A weighted draw over :data:`_CPU_UTILIZATION_BANDS`, consumed from the caller's own
    per-resource stream. The class is per resource rather than per sample because a
    machine's workload does not change shape day to day, and because the consumers'
    thresholds are read off the resource's peak — see the block above.
    """
    draw = rng.random()
    cumulative = 0.0
    for weight, low, high in _CPU_UTILIZATION_BANDS:
        cumulative += weight
        if draw < cumulative:
            return low, high
    return _CPU_UTILIZATION_BANDS[-1][1], _CPU_UTILIZATION_BANDS[-1][2]


# ── the ``memory_utilization`` domain ─────────────────────────────────────────
#
# The second metric, and it exists for ONE consumer fact rather than for symmetry:
# ``cloudwatch_metrics_provider.py (modulo do consumidor)`` refuses to return a window
# at all unless the memory lookup answered —
#
#     if cpu_sample_count == 0 or memory_sample_count == 0:
#         return None
#
# and ``RightsizingAnalyzer._evaluate_resource`` then refuses to judge a window whose
# ``avg_memory_pct`` is None. Memory is therefore the PRECONDITION of every CPU
# rightsizing verdict: with no memory series the whole CPU path fails closed and the
# detector emits nothing, which is what the estate did before this series existed.
#
# The namespace/metric/dimension the consumer asks for are ITS OWN, read from the query
# it builds (``cloudwatch_metrics_provider.py``): namespace ``CWAgent``, metric name
# ``MemoryUtilization``, dimension ``InstanceId``, statistic p50 and p95, unit
# ``Percent``. ``emulators/aws-sim/aws_sim/projections/cloudwatch.py`` answers exactly that
# pair, with the dimension value the EC2 projection already answers for the instance.
#
# Scale: a PERCENTAGE of the instance's memory capacity (0..100), the unit inside that
# same ``"Unit": "Percent"`` query — not bytes, and not a fraction.
#
# The mixture, and the consumer facts that drove it. Memory is drawn per resource from
# its OWN band, INDEPENDENTLY of the CPU class: a box can idle on CPU while being
# memory-heavy, which is precisely the asymmetry the platform's memory detector exists to
# find. The bands are placed to straddle the thresholds the consumer applies to this
# very field:
#
#   * ``light`` (4..12) — below both ceilings ``_classify_severity`` reads off
#     ``max(avg_cpu_pct, avg_memory_pct)`` (8 for HIGH, 14 for MEDIUM) and far below the
#     40% over-provisioning line ``MemoryOverprovisionedDetector`` names
#     (``memory_threshold_pct=40.0``). This class is what keeps the CPU path's HIGH and
#     MEDIUM verdicts reachable once memory joins the ``max()``: with memory absent the
#     ceiling was decided by CPU alone, and a realistic memory floor (a running OS
#     resident footprint) would otherwise push every flagged machine into LOW.
#   * ``moderate`` (20..38) — under 40%, the ordinary over-provisioned-candidate band.
#   * ``heavy`` (48..78) — above 40%, so the estate also carries instances the memory
#     verdict must NOT flag, and ``max()`` is exercised from both sides.
#
# The band is drawn from the resource's OWN ``metric/<uuid>`` stream, AFTER that
# resource's CPU band and samples, which is what keeps every pre-existing
# ``cpu_utilization`` series byte-identical while the memory series is added.
_MEMORY_UTILIZATION_BANDS: tuple[tuple[float, float, float], ...] = (
    (0.45, 4.0, 12.0),
    (0.35, 20.0, 38.0),
    (0.20, 48.0, 78.0),
)


def _memory_utilization_band(rng: random.Random) -> tuple[float, float]:
    """Return the ``(low, high)`` percent band the resource drawn from ``rng`` belongs to.

    A weighted draw over :data:`_MEMORY_UTILIZATION_BANDS`, consumed from the caller's own
    per-resource stream in the same shape as :func:`_cpu_utilization_band` — see the block
    above for the consumer thresholds the bands straddle.
    """
    draw = rng.random()
    cumulative = 0.0
    for weight, low, high in _MEMORY_UTILIZATION_BANDS:
        cumulative += weight
        if draw < cumulative:
            return low, high
    return _MEMORY_UTILIZATION_BANDS[-1][1], _MEMORY_UTILIZATION_BANDS[-1][2]


def _q(value: Decimal) -> Decimal:
    """Quantize to FOCUS 6-dp (banker's rounding)."""
    return value.quantize(const.SIX_DP)


def _month_end(day: date) -> date:
    if day.month == 12:
        return date(day.year + 1, 1, 1)
    return date(day.year, day.month + 1, 1)


#: Recursos que de fato carregam interface de rede. Os nomes sao os do catalogo
#: de cada provedor (``AWS_SERVICES``/``AZURE_SERVICES``/``GCP_SERVICES``), e nao
#: um vocabulario inventado: o resto do catalogo nao tem ENI/NIC, e dar uma a ele
#: seria dado sem lastro.
NETWORK_ATTACHABLE_TYPES: tuple[str, ...] = (
    # AWS
    "ec2_instance",
    "rds_instance",
    "eks_cluster",
    "application_lb",
    "nat_gateway",
    "ecs_cluster",
    # Azure
    "virtual_machine",
    "aks_cluster",
    # GCP
    "compute_instance",
    "gke_cluster",
    "cloud_sql",
)

#: Cobertura de fluxo: as ultimas ``FLOW_WINDOWS`` janelas de
#: ``FLOW_WINDOW_MINUTES`` do ultimo dia. A AWS publica a cada 5 minutos, o que
#: daria 288 janelas por dia; uma hora e o bastante para os renderers exercitarem
#: o formato sem inflar o artefato.
FLOW_WINDOW_MINUTES = 5
FLOW_WINDOWS = 12

#: Numeros IANA que as quatro nuvens documentam. O NSG da Azure escreve ``T``/
#: ``U``; a conversao e do renderer, a partir da spec.
FLOW_PROTOCOLS: tuple[int, ...] = (6, 17, 1)  # TCP, UDP, ICMP

#: Portas de destino bem conhecidas, para o fluxo parecer tráfego de nuvem.
FLOW_DEST_PORTS: tuple[int, ...] = (443, 80, 22, 5432, 6379, 3306)

#: Endereco de ponta ausente num fluxo sem par conhecido, na forma que a AWS
#: publica. NAO e bind de servidor -- a regra S104 do ruff confunde os dois, e o
#: noqa existe para dizer que a confusao foi considerada.
FLOW_ABSENT_ADDRESS = "0.0.0.0"  # noqa: S104

#: Tipo de instancia documentado, por SKU do catalogo. Tabela EXPLICITA, e nao
#: regra de transformacao de texto: a forma publicada da Azure
#: (``Standard_D2s_v5``) nao sai de manipular ``azure-vm-d2s-v5`` sem adivinhar a
#: caixa das letras, e adivinhar caixa e inventar. SKU sem entrada aqui produz
#: ``instance_type = None``, e a coluna sai vazia -- falha fechada.
INSTANCE_TYPE_BY_SKU: dict[str, str] = {
    "aws-ec2-m5-large": "m5.large",
    "azure-vm-d2s-v5": "Standard_D2s_v5",
    "gcp-ce-e2-standard-2": "e2-standard-2",
}

#: Tipo de disco raiz documentado, por tipo de recurso de disco do catalogo.
DISK_TYPE_BY_SKU: dict[str, str] = {
    "ebs_volume": "gp3",
    "persistent_disk": "pd-ssd",
}


#: Chaves de provedor como o ESCOPO as usa (minusculas). Nao confundir com
#: ``const.PROVIDER_AZURE``, que e o nome de exibicao ("Microsoft Azure") usado
#: nas linhas de fatura -- comparar com ele nunca casa, e o defeito e silencioso:
#: todas as branches caem no caso errado sem levantar erro.
SCOPE_PROVIDER_AWS = "aws"
SCOPE_PROVIDER_AZURE = "azure"
SCOPE_PROVIDER_GCP = "gcp"


def _mac_for(uuid: str) -> str:
    """MAC unicast de administracao local, derivado do uuid (deterministico)."""
    digest = hashlib.sha256(f"mac:{uuid}".encode()).digest()
    return "02:00:" + ":".join(f"{byte:02x}" for byte in digest[:4])


def _zone_for(provider: str, region: str, uuid: str) -> str:
    """Zona de disponibilidade, na forma que cada nuvem publica.

    AWS escreve ``us-east-1a``, o GCP ``us-central1-a`` e a Azure usa numero
    (``"1"``). A letra sai do uuid, entao e estavel, mas o CONJUNTO de zonas de
    cada regiao nao esta modelado -- e uma simplificacao declarada, nao uma
    afirmacao sobre a topologia real.
    """
    letra = "abc"[hashlib.sha256(f"zone:{uuid}".encode()).digest()[0] % 3]
    if provider == SCOPE_PROVIDER_AZURE:
        return str(1 + "abc".index(letra))
    if provider == SCOPE_PROVIDER_GCP:
        return f"{region}-{letra}"
    return f"{region}{letra}"


def _public_ip_for(uuid: str) -> str:
    """IP publico na faixa de documentacao (RFC 5737), para nao implicar host real."""
    digest = hashlib.sha256(f"public-ip:{uuid}".encode()).digest()
    bloco = "198.51.100" if digest[0] % 2 else "203.0.113"
    return f"{bloco}.{digest[1] or 1}"


def _private_ip_for(uuid: str) -> str:
    """Endereco privado RFC 1918, derivado do uuid (deterministico)."""
    digest = hashlib.sha256(f"ip:{uuid}".encode()).digest()
    return f"10.{digest[0] % 64}.{digest[1]}.{digest[2] or 1}"


def _security_rules() -> tuple[SecurityRule, ...]:
    """As regras do NSG Azure, na ordem de prioridade que a documentacao define.

    As regras vem de ``const.NSG_SECURITY_RULES`` (uma postura declarada, nao um sorteio) na
    forma posicional, e nao em dicionario: um ``dict`` nao diz ao verificador de tipos QUAL
    campo cada posicao alimenta, entao um nome trocado (``access`` no lugar de ``direction``)
    so apareceria em tempo de execucao. A ordem e por ``priority`` porque menor numero e maior
    prioridade -- a ordem do artefato e, entao, uma afirmacao do provedor.
    """
    return tuple(
        sorted(
            (
                SecurityRule(
                    name=nome,
                    priority=prioridade,
                    direction=direcao,
                    access=acesso,
                    protocol=protocolo,
                    source_address_prefix=prefixo_origem,
                    destination_address_prefix=prefixo_destino,
                    source_port_range=faixa_porta_origem,
                    destination_port_range=faixa_porta_destino,
                )
                for (
                    nome,
                    prioridade,
                    direcao,
                    acesso,
                    protocolo,
                    prefixo_origem,
                    prefixo_destino,
                    faixa_porta_origem,
                    faixa_porta_destino,
                ) in const.NSG_SECURITY_RULES
            ),
            key=lambda rule: rule.priority,
        )
    )


def _aws_permission(
    protocolo: str, from_port: int | None, to_port: int | None, origem_ipv4: str, descricao: str
) -> AwsIpPermission:
    """Uma regra de SG da AWS, na forma de ``IpPermission``.

    A DIRECAO nao entra aqui de proposito: na AWS ela e o NOME da lista que contem a regra
    (``IpPermissions`` / ``IpPermissionsEgress``), nao um membro da regra. Por isso a postura a
    carrega como primeiro campo posicional -- para o chamador saber em qual das duas listas
    colocar -- e o construtor a descarta.

    ``from_port``/``to_port`` chegam ja como ``None`` quando a regra nao os publica -- o caso
    de ``-1``, em que a documentacao diz que as portas nao se aplicam e a amostra oficial da
    acao traz a regra sem nenhum dos dois. Nao ha conversao de protocolo para numero: a
    pagina aceita nome OU numero, entao guardar o valor publicado preserva o dominio.
    """
    return AwsIpPermission(
        ip_protocol=protocolo,
        from_port=from_port,
        to_port=to_port,
        ip_ranges=(AwsIpRange(cidr_ip=origem_ipv4, description=descricao),),
    )


def _aws_security_groups(
    resources: Sequence[Resource], segments: Sequence[NetworkSegment]
) -> tuple[AwsSecurityGroup, ...]:
    """Os security groups da AWS com as REGRAS que ``ec2.describe_security_groups`` publica.

    Este e o Incremento 2: ate aqui os 15 recursos ``security_group`` existiam mas NAO
    tinham regra nenhuma, e as tres regras gerenciadas de rede do AWS Config
    (``restricted-ssh``, ``restricted-common-ports`` e ``vpc-default-security-group-closed``)
    respondiam ``INSUFFICIENT_DATA`` por falta do fato -- nao por duvida sobre a regra.

    A postura vem de :data:`const.AWS_SG_RULES`, declarada e nao sorteada (ver a justificativa
    la). A distribuicao e deterministica e NAO e uma escolha estetica: ela e o que garante que
    os dois lados de cada regra aparecam no mesmo escopo de (conta, regiao), senao o estado so
    ensinaria um dos vereditos e o consumidor nao teria como provar que os distingue.

    ``vpc_id`` e o campo derivado que merece a atencao. O estate nao modela qual VPC pertence
    a qual grupo -- os recursos ``vpc`` vivem em outra regiao que os ``security_group``, e
    nenhum par conta/regiao tem os dois. O que existe e o SEGMENTO: um ``NetworkSegment`` por
    (conta, regiao), e ``segment_id`` ja e o id nativo ``vpc-...`` que este modelo publica. A
    associacao e portanto a funcao do proprio agrupamento do modelo, e nao uma escolha sobre a
    semantica do provedor. Falta a verificacao contra a relacao VPC<->SG de uma conta real, e
    a pende de o modelo passar a carregar essa relacao -- ate la e uma derivacao declarada.
    """
    # A VPC de um escopo: um segmento AWS por (conta, regiao), e ``segment_id`` ja e o id
    # nativo. A ordem de insercao nao importa porque a chave e unica por construcao.
    vpc_por_escopo: dict[tuple[str, str], str] = {
        (segment.scope_id, segment.region_id): segment.segment_id
        for segment in segments
        if segment.provider == SCOPE_PROVIDER_AWS
    }

    por_conta: dict[tuple[str, str], list[Resource]] = {}
    for resource in resources:
        if resource.identity.provider != const.PROVIDER_KEY_AWS or resource.resource_type != "security_group":
            continue
        por_conta.setdefault((resource.parent_scope_id, resource.region_id), []).append(resource)

    grupos: list[AwsSecurityGroup] = []
    for indice_conta, ((conta, regiao), recursos) in enumerate(sorted(por_conta.items())):
        vpc_id = vpc_por_escopo.get((conta, regiao))
        if vpc_id is None:
            # Fecha-fail: sem o segmento nao ha como preencher um membro documentado do
            # ``SecurityGroup``, e um ``vpcId`` vazio faria a regra
            # ``vpc-default-security-group-closed`` responder sobre uma VPC que nao existe.
            raise ValueError(
                f"security group em {conta}/{regiao} sem segmento AWS: o id de VPC do grupo "
                "vem do segmento e nao ha como deriva-lo"
            )
        # Grupo PADRAO e rotacao saem da MESMA paridade de conta: e o que faz um escopo inteiro
        # ficar COMPLIANT e o outro ficar exposto, em vez de todo escopo receber os quatro
        # perfis e nenhum conseguir ser avaliado como conforme.
        paridade = indice_conta % len(const.AWS_SG_ROTATIONS)
        rotacao = const.AWS_SG_ROTATIONS[paridade]
        ordenados = sorted(recursos, key=lambda item: item.identity.logical_path)
        for slot, resource in enumerate(ordenados):
            # Slot 0 de cada conta e o grupo PADRAO da VPC: a amostra oficial da acao o
            # identifica por ``groupName = "default"``, e e o grupo que
            # ``vpc-default-security-group-closed`` avalia.
            padrao = slot == 0
            perfil = (
                const.AWS_SG_DEFAULT_PROFILE_BY_ACCOUNT[
                    paridade % len(const.AWS_SG_DEFAULT_PROFILE_BY_ACCOUNT)
                ]
                if padrao
                else rotacao[(slot - 1) % len(rotacao)]
            )
            ingress: list[AwsIpPermission] = []
            egress: list[AwsIpPermission] = []
            for direcao, protocolo, from_port, to_port, origem, descricao in const.AWS_SG_RULES[perfil]:
                (ingress if direcao == DIRECTION_INGRESS else egress).append(
                    _aws_permission(protocolo, from_port, to_port, origem, descricao)
                )
            # Todo grupo recem-criado nasce com a regra de egress que libera tudo; so um
            # grupo que teve essa regra REMOVIDA chega a lista vazia -- que e a remediacao
            # que ``vpc-default-security-group-closed`` pede.
            if perfil != const.AWS_SG_CLOSED_PROFILE:
                # A postura de egress padrao tem a direcao no primeiro campo, como toda a
                # postura; aqui ela e fixa e a regra vai sempre para a lista de saida. Os
                # nomes sao distintos dos de cima porque ESTA regra tem as portas em None --
                # e o tipo declarado de cada postura nao e o mesmo.
                _saida, protocolo_saida, porta_de, porta_ate, origem_saida, descricao_saida = (
                    const.AWS_SG_DEFAULT_EGRESS
                )
                egress.append(
                    _aws_permission(protocolo_saida, porta_de, porta_ate, origem_saida, descricao_saida)
                )

            grupos.append(
                AwsSecurityGroup(
                    resource_uuid=resource.identity.uuid,
                    group_id=aws_resource_id("security_group", resource.identity.uuid),
                    group_name=(
                        AWS_DEFAULT_SECURITY_GROUP_NAME
                        if padrao
                        else resource.resource_name
                    ),
                    # A descricao do grupo padrao e a que a amostra oficial publica; nos
                    # demais e o nome que o proprio modelo ja deu ao recurso, para nao
                    # inventar uma frase que nenhuma fonte do estate afirma.
                    group_description=(
                        AWS_DEFAULT_SECURITY_GROUP_DESCRIPTION
                        if padrao
                        else resource.resource_name
                    ),
                    owner_id=resource.parent_scope_id,
                    vpc_id=vpc_id,
                    ingress=tuple(ingress),
                    egress=tuple(egress),
                )
            )
    return tuple(grupos)


def _gcp_firewall_entries(entradas: Sequence[const.GcpFirewallEntrySpec]) -> tuple[GcpFirewallEntry, ...]:
    """As tuplas protocolo/porta de uma regra, na forma que ``allowed[]``/``denied[]`` publicam.

    ``ports`` e a lista de STRINGS que a GCP publica -- ``["22"]`` ou ``["12345-12349"]`` -- e
    fica VAZIA quando a regra vale para qualquer porta, que e o que a pagina declara. Nao ha
    conversao para numero: a fonte aceita faixa como texto e escolher um par de numeros seria
    trocar a sintaxe da GCP pela da AWS.
    """
    return tuple(GcpFirewallEntry(ip_protocol=protocolo, ports=tuple(portas)) for protocolo, portas in entradas)


def _gcp_firewall_rules(segments: Sequence[NetworkSegment]) -> tuple[GcpFirewallRule, ...]:
    """As regras de firewall da GCP que ``compute.firewalls.list`` publica.

    Este e o Incremento 6: antes dele o estate nao tinha NENHUMA regra de firewall GCP -- as
    trinta e tantas de rede do modelo eram segmentos sem regra nenhuma -- e o consumidor de
    seguranca nao tinha o que ler. OSegmento ja carregava ``segment_id`` na forma
    ``projects/<p>/global/networks/<n>``, que e EXATAMENTE o valor que ``Firewall.network``
    publica; por isso aqui nao ha derivacao nenhuma, ao contrario do ``vpcId`` do security group
    da AWS.

    A postura vem de :data:`const.GCP_FIREWALL_RULES_BY_PROJECT`, declarada e nao sorteada (ver a
    justificativa la), e e o que garante que os DOIS lados da verificacao aparecam no mesmo
    estado: com um perfil so, todo projeto ficaria exposto e o veredito seria unico.

    Duas decisoes de MODELO, ambas declaradas na proveniencia do renderer:

    * **a lista e por PROJETO, nao por (projeto, regiao).** O caminho da acao e
      ``projects/<p>/global/firewalls`` -- global, sem regiao. Um envelope por regiao seria um
      recorte que a API nao faz;
    * **as regras pre-populadas vao para a PRIMEIRA rede do projeto.** A documentacao diz que elas
      existem na rede ``default``; o modelo nao tem uma rede ``default`` (ele da uma por
      (projeto, regiao), como se fosse a VPC da AWS), entao elas vao para a rede de indice 0 na
      ordem por ``segment_id``. E uma derivacao declarada, e nao um fato lido da GCP.
    """
    redes_por_projeto: dict[str, list[NetworkSegment]] = {}
    for segment in segments:
        if segment.provider != SCOPE_PROVIDER_GCP:
            continue
        redes_por_projeto.setdefault(segment.scope_id, []).append(segment)

    regras: list[GcpFirewallRule] = []
    for indice_projeto, (projeto, redes) in enumerate(sorted(redes_por_projeto.items())):
        if not redes:
            raise ValueError(f"projeto GCP {projeto} sem rede: a regra de firewall publica a rede que protege")
        # Ordenar por segment_id e o que torna a escolha da rede de indice 0 ESTAVEL: sem isso a
        # rede "default" seria a que o gerador construiu por ultimo, e a derivacao mudaria com a
        # ordem de insercao.
        ordenadas = sorted(redes, key=lambda item: item.segment_id)
        if len(ordenadas) <= const.GCP_FIREWALL_DEFAULT_NETWORK_SLOT:
            raise ValueError(
                f"projeto GCP {projeto} sem rede no slot {const.GCP_FIREWALL_DEFAULT_NETWORK_SLOT} "
                "para as regras pre-populadas"
            )
        posture = const.GCP_FIREWALL_RULES_BY_PROJECT[indice_projeto % len(const.GCP_FIREWALL_RULES_BY_PROJECT)]
        # As pre-populadas ficam todas na rede de indice 0; as demais se distribuem pelas outras,
        # em ordem, para que a lista do projeto carregue regras de mais de uma rede -- que e o
        # que firewalls.list devolve: a pagina nao restringe a uma rede.
        outras = ordenadas[const.GCP_FIREWALL_DEFAULT_NETWORK_SLOT + 1 :] or ordenadas[:1]
        cursor = 0
        for nome, direcao, prioridade, origens, permitidos, negados, desabilitada, log_ativo, descricao in posture:
            pre_populada = nome.startswith("default-allow-")
            if pre_populada:
                rede = ordenadas[const.GCP_FIREWALL_DEFAULT_NETWORK_SLOT]
            else:
                rede = outras[cursor % len(outras)]
                cursor += 1
            is_ingress = direcao == GCP_FIREWALL_INGRESS
            regras.append(
                GcpFirewallRule(
                    segment_uuid=rede.segment_uuid,
                    scope_id=projeto,
                    rule_name=nome,
                    # ``segment_id`` VERBATIM: e a URL que Firewall.network publica.
                    network_url=rede.segment_id,
                    direction=direcao,
                    priority=prioridade,
                    description=descricao,
                    disabled=desabilitada,
                    # A origem vale para INGRESS e o destino para EGRESS; a mesma regra nao
                    # preenche os dois, porque a GCP os separa em dois membros.
                    source_ranges=tuple(origens) if is_ingress else (),
                    destination_ranges=() if is_ingress else tuple(origens),
                    allowed=_gcp_firewall_entries(permitidos),
                    denied=_gcp_firewall_entries(negados),
                    log_enabled=log_ativo,
                    log_metadata=GCP_FIREWALL_LOG_INCLUDE_ALL if log_ativo else None,
                )
            )
    return tuple(regras)


def _azure_defender_assessments(
    segments: Sequence[NetworkSegment],
    seed: int,
    identity: IdentityFactory,
    sim_start: date,
) -> tuple[AzureDefenderAssessment, ...]:
    """As verificacoes de SAUDE do Defender for Cloud sobre cada segmento Azure.

    Este e o Incremento 8. Antes dele o estate so tinha ACHADOS, e o consumidor do FinOps
    filtra ``assessments.list`` por ``status.code == "Healthy"``: um ``NativeFinding`` -- que
    por definicao e um problema -- nao representa o ramo DESCARTADO. A postura vem de
    :data:`const.AZURE_DEFENDER_ASSESSMENT_POSTURES`, DECLARADA e nao sorteada.

    A DECISAO que importa aqui foi medida, nao presumida. A primeira versao desta funcao
    derivava o estado dos ACHADOS: o segmento ficava ``Unhealthy`` quando o escopo tinha um
    achado Azure de categoria REDE. Rodada no perfil ``small``/seed 123, ela produziu
    ``Counter({'Unhealthy': 6, 'NotApplicable': 6})`` -- **nenhum ``Healthy``**. O consumidor
    so descarta ``status.code == "Healthy"``, entao o artefato nunca exercise o descarte: um
    check que nunca ve o ramo que ele tem de decidir nao treina nada.

    A segunda versao alternava pelo indice do ESCOPO, e falhou por um motivo mensuravel: os
    segmentos se agrupam em assinaturas e nao em indices de escopo, entao duas assinaturas
    ficaram so com escopos de indice PAR. Medido no mesmo perfil, o consumidor descartava
    ``[0, 0, 2]`` -- dois envelopes de tres sem nenhum descarte. Da veio a alternancia pelo
    indice do segmento DENTRO DA ASSINATURA, que e a unidade que a resposta entrega (um
    envelope por assinatura): com dois ou mais segmentos por assinatura, cada envelope carrega
    os dois lados. E a mesma disciplina que :func:`_gcp_firewall_rules` usa para garantir os dois
    lados de uma verificacao no mesmo estado.

    Os instantes de ``properties.status`` saem de um stream PROPRIO indexado pelo segmento
    (mesma disciplina de ``finding_provenance``): uma postura de seguranca tem de ser
    EXATAMENTE a mesma entre execucoes, e ``now()`` nao e um valor de estado.
    """
    por_assinatura: dict[str, list[NetworkSegment]] = {}
    for segmento in segments:
        if segmento.provider != SCOPE_PROVIDER_AZURE:
            continue
        # A assinatura e a MESMA funcao que compoe o ``segment_id`` (``azure_subscription_guid``),
        # e nao uma segunda grafia do mesmo token.
        assinatura = azure_subscription_guid(seed, segmento.scope_id)
        por_assinatura.setdefault(assinatura, []).append(segmento)

    assessments: list[AzureDefenderAssessment] = []
    for assinatura in sorted(por_assinatura):
        # Ordenar por uuid antes de enumerar e o que torna a escolha ESTAVEL: sem isso o par
        # (Unhealthy, Healthy) dependeria da ordem de insercao das redes.
        for indice, segmento in enumerate(sorted(por_assinatura[assinatura], key=lambda item: item.segment_uuid)):
            for postura, saude, severidade_padrao in const.AZURE_DEFENDER_ASSESSMENT_POSTURES:
                if saude == const.SAUDE_NAO_APLICAVEL:
                    health = ASSESSMENT_HEALTH_NOT_APPLICABLE
                elif indice % 2 == 0:
                    health = ASSESSMENT_HEALTH_UNHEALTHY
                else:
                    health = ASSESSMENT_HEALTH_HEALTHY
                unhealthy = health == ASSESSMENT_HEALTH_UNHEALTHY
                instantes = stream_rng(seed, f"azure-assessment/{segmento.segment_uuid}/{postura}")
                avaliado_em = datetime.combine(
                    sim_start, time(hour=instantes.randrange(24), minute=instantes.randrange(60)), tzinfo=UTC
                )
                mudou_em = avaliado_em + timedelta(hours=instantes.randrange(1, 24))
                assessments.append(
                    AzureDefenderAssessment(
                        segment_uuid=segmento.segment_uuid,
                        assessment_id=identity.uuid_for(f"azure-assessment/{segmento.segment_uuid}/{postura}"),
                        posture=postura,
                        health=health,
                        severity=severidade_padrao if unhealthy else "",
                        first_evaluated_at=avaliado_em,
                        status_changed_at=mudou_em,
                    )
                )
    return tuple(assessments)


def _aws_bucket_grants(
    perfil_grants: Sequence[const.S3GrantSpec], owner_canonical_id: str
) -> tuple[AwsBucketGrant, ...]:
    """Os grants ARMAZADOS de um bucket, a partir da canned ACL do perfil.

    A tabela de canned ACLs da AWS diz quem recebe o que em cada ACL predefinida, entao o
    perfil nomeia a ACL e aqui os grants sao montados com o ``Grantee`` que ela descreve:
    um grant de grupo carrega o ``URI`` do grupo e nada mais, e o grant do owner
    carrega o ``ID`` canonico da conta -- que e o que a resposta de exemplo do
    ``GetBucketAcl`` mostra no ``<Grantee xsi:type="CanonicalUser">``.
    """
    grants: list[AwsBucketGrant] = []
    for permission, grantee_type, uri in perfil_grants:
        if grantee_type == "Group":
            grants.append(
                AwsBucketGrant(permission=permission, grantee_type=grantee_type, uri=uri)
            )
        else:
            grants.append(
                AwsBucketGrant(
                    permission=permission,
                    grantee_type=grantee_type,
                    grantee_id=owner_canonical_id,
                )
            )
    return tuple(grants)


def _aws_bucket_policy(
    perfil_policy: const.S3PolicySpec | None, bucket_name: str
) -> AwsBucketPolicy | None:
    """O documento de bucket policy do perfil, com o bucket de verdade no ``Resource``.

    Os placeholders ``BUCKET`` da tabela viram o NOME do bucket, e nao o ARN: o
    template ja traz o prefixo ``arn:aws:s3:::/`` entao -- um ARN completo aqui
    produziria ``arn:aws:s3:::arn:aws:s3:::nome``, que nao e ARN de bucket nenhum.
    """
    if perfil_policy is None:
        return None
    policy_id, version, statements = perfil_policy
    return AwsBucketPolicy(
        version=version,
        policy_id=policy_id,
        statements=tuple(
            AwsPolicyStatement(
                effect=effect,
                actions=actions,
                principals=principals,
                resources=tuple(recurso.replace("BUCKET", bucket_name) for recurso in resources),
                sid=sid,
            )
            for sid, effect, actions, principals, resources in statements
        ),
    )


def _aws_bucket_creation_date(seed: int, resource_uuid: str) -> str:
    """A ``CreationDate`` do bucket, em ISO-8601 UTC, derivada do proprio recurso.

    Um bucket nao e medido -- ``s3_bucket`` esta entre os tipos que o estate nao fatura
    (``test_metrics_metering`` exige isso explicitamente) -- entao nao ha linha de consumo
    de onde a data viesse. Ela e derivada do ``resource_uuid`` num intervalo fixo e
    anterior a janela de simulacao, para ser estavel entre execucoes.

    ``TODO-verificar``: data DERIVADA. O ``CreationDate`` real e um timestamp que a AWS
    atribuiu no ``CreateBucket``; a entropia e a data sao verificaveis so contra a API.
    """
    digest = hashlib.sha256(f"s3-bucket-created:{seed}:{resource_uuid}".encode()).hexdigest()
    base = date(2021, 1, 1)
    dia = base + timedelta(days=int(digest[:8], 16) % 900)
    momento = datetime.combine(dia, time(9, 30), tzinfo=UTC)
    return momento.isoformat()


def _aws_cloudtrail_trail(
    conta: str, regiao: str, sufixo: str, multi_regiao: bool, tem_s3: bool, tem_logs: bool, tem_sns: bool
) -> AwsCloudTrail:
    """Uma trilha CloudTrail da conta, com os identificadores derivados do proprio escopo.

    O ARN e o bucket saem do par (conta, regiao) e do sufixo do perfil, nunca de um literal: um
    id de ARN escrito a mao seria o mesmo nas tres contas, e a colecao de trilhas perderia a
    propriedade que a torna util -- ser a lista DE TRILHAS DESSA CONTA.

    As tres bandeiras do perfil decidem os tres parametros OPCIONAIS da regra. Uma trilha de
    entrega so no S3 e uma configuracao real (e a minima que o servico exige de qualquer
    trilha); as tres ao mesmo tempo e a trilha que o operador liga quando quer que a auditoria
    chegue a S3, ao CloudWatch Logs e ao SNS.
    """
    nome = f"contoso-{sufixo}"
    return AwsCloudTrail(
        trail_name=nome,
        trail_arn=f"arn:aws:cloudtrail:{regiao}:{conta}:trail/{nome}",
        home_region=regiao,
        is_multi_region_trail=multi_regiao,
        s3_bucket_name=f"contoso-auditoria-{conta}" if tem_s3 else None,
        cloud_watch_logs_group_arn=(
            f"arn:aws:logs:{regiao}:{conta}:log-group:cloudtrail-{nome}" if tem_logs else None
        ),
        sns_topic_arn=f"arn:aws:sns:{regiao}:{conta}:auditoria-alertas" if tem_sns else None,
    )


def _aws_audit_postures(orgs: Sequence[AwsOrg], regiao_por_conta: Mapping[str, str]) -> tuple[AwsAuditPosture, ...]:
    """A postura de AUDITORIA de cada conta -- trilhas CloudTrail e inscricao do Security Hub.

    Este e o Incremento 4.3: ``cloudtrail-enabled`` e ``securityhub-enabled`` respondiam
    ``INSUFFICIENT_DATA`` em TODOS os escopos por falta do fato -- o estate nao carregava nem
    trilha nem inscricao.

    A chave e a CONTA, e nao um recurso, porque e isso que as duas paginas publicam: trigger
    ``Periodic`` e NENHUM "Resource Types". CloudTrail e Security Hub sao avaliados na conta, e
    por isso o veredito se repete nas tres regioes dela em vez de diferir.

    A regiao de cada trilha e a do ESCOPO (conta, regiao) em que a conta tem recursos, e nao um
    literal: o ``homeRegion`` de uma trilha e o mesmo em qualquer numero de trilhas.
    """
    contas = sorted((conta for org in orgs for conta in org.accounts), key=lambda item: item.account_id)
    posturas: list[AwsAuditPosture] = []
    for indice, conta in enumerate(contas):
        eixo_trail, eixo_hub = const.AWS_AUDIT_ROTATIONS[indice % len(const.AWS_AUDIT_ROTATIONS)]
        regiao = regiao_por_conta.get(conta.account_id, "")
        trilhas = tuple(
            _aws_cloudtrail_trail(conta.account_id, regiao, sufixo, multi_regiao, tem_s3, tem_logs, tem_sns)
            for sufixo, multi_regiao, tem_s3, tem_logs, tem_sns in const.AWS_CLOUDTRAIL_TRAILS[eixo_trail]
        )
        hub_ativo = const.AWS_SECURITYHUB_ENABLED[eixo_hub]
        posturas.append(
            AwsAuditPosture(
                account_id=conta.account_id,
                cloudtrail=trilhas,
                security_hub=AwsSecurityHubEnrollment(
                    enabled=hub_ativo,
                    hub_arn=(
                        f"arn:aws:securityhub:{regiao}:{conta.account_id}:hub/default" if hub_ativo else None
                    ),
                ),
            )
        )
    return tuple(posturas)


def _aws_vpc_flow_logs(seed: int, resources: Sequence[Resource]) -> tuple[AwsVpcFlowLog, ...]:
    """A configuracao de flow logs de cada VPC -- o que ``vpc-flow-logs-enabled`` le.

    Este e o Incremento 4.3 pelo lado por RECURSO: ate aqui o estate tinha as 15 VPCs e nenhuma
    delas carregava se tinha flow log, e a regra respondia ``INSUFFICIENT_DATA`` em todo escopo.

    A chave e o recurso ``vpc``, e nao o ``NetworkSegment``: a pagina da regra publica
    ``Resource Types: AWS::EC2::VPC`` e o veredito e por VPC avaliada. O segmento de rede e a
    estrutura multi-provedor, e meter um campo so de AWS dentro dela obrigaria os outros tres a
    conhecerem um campo que so um preenche.

    A rotacao e POR ESCOPO (conta, regiao), e nao por conta, porque e o escopo que e a unidade de
    resposta da regra: e dentro de um escopo que uma VPC sem log derruba o veredito das suas
    irmas. Os tres perfis sao escolhidos para que os tres casos aparecam -- todas com log (o
    escopo CONFORME), nenhuma com log (o escopo sem trilha nenhuma) e um MISTURADO, em que uma
    VPC com log convive com uma sem na mesma conta. O misturado e o que prova a granularidade: um
    renderizador que lesse a conta em vez da VPC responderia o MESMO veredito nele.

    O id da trilha e derivado com a MESMA formula do renderer ``render/vpc_flow_logs.py``, para
    que a postura e a superficie de entrega nao tenham duas respostas diferentes para "qual e o id
    desta trilha". O recurso de log da entrega e a ENI, e o da postura e a VPC -- sao alvos
    diferentes, como os tres alvos que a AWS documenta, e por isso os ids nao coincidem.
    """
    por_escopo: dict[tuple[str, str], list[Resource]] = {}
    for resource in resources:
        if resource.identity.provider != const.PROVIDER_KEY_AWS or resource.resource_type != "vpc":
            continue
        por_escopo.setdefault((resource.parent_scope_id, resource.region_id), []).append(resource)

    configuracoes: list[AwsVpcFlowLog] = []
    for indice_escopo, ((conta, regiao), vpcs) in enumerate(sorted(por_escopo.items())):
        perfil = const.AWS_VPC_FLOW_LOG_ROTATIONS[indice_escopo % len(const.AWS_VPC_FLOW_LOG_ROTATIONS)]
        bandeiras = const.AWS_VPC_FLOW_LOG_PROFILES[perfil]
        for slot, resource in enumerate(sorted(vpcs, key=lambda item: item.identity.logical_path)):
            vpc_id = aws_resource_id("vpc", resource.identity.uuid)
            tem_log = bandeiras[slot % len(bandeiras)]
            digest = hashlib.sha256(f"{seed}:vpc-flow-log:{vpc_id}".encode()).hexdigest()
            tipos = (
                (const.AWS_VPC_FLOW_LOG_TRAFFIC_TYPES[slot % len(const.AWS_VPC_FLOW_LOG_TRAFFIC_TYPES)],)
                if tem_log
                else ()
            )
            configuracoes.append(
                AwsVpcFlowLog(
                    resource_uuid=resource.identity.uuid,
                    vpc_id=vpc_id,
                    account_id=conta,
                    region_id=regiao,
                    flow_log_ids=(f"fl-{digest[:17]}",) if tem_log else (),
                    traffic_types=tipos,
                )
            )
    return tuple(configuracoes)


def _aws_bucket_postures(seed: int, resources: Sequence[Resource]) -> tuple[AwsBucketPosture, ...]:
    """A POSTURA dos buckets S3 -- ACL, bucket policy e public access block.

    Este e o Incremento 3: ate aqui os 15 recursos ``s3_bucket`` existiam e eram
    inventariados e faturados, mas o estate nao carregava a postura que
    ``GetBucketAcl`` / ``GetBucketPolicy`` / ``GetPublicAccessBlock`` publicam, e as tres
    regras gerenciadas sobre exposicao publica (``s3-bucket-public-read-prohibited``,
    ``s3-bucket-public-write-prohibited`` e ``s3-bucket-level-public-access-prohibited``)
    respondiam ``INSUFFICIENT_DATA`` por falta do fato.

    A postura vem de :data:`const.S3_BUCKET_PROFILES`, DECLARADA e nao sorteada, e os
    grants vem da tabela de canned ACLs da AWS -- que e onde a propria AWS diz quem
    recebe cada permissao em cada ACL predefinida.

    A distribuicao e deterministica e NAO e estetica: a conta PAR recebe a rotacao
    restrita e a IMPAR a exposta (o mesmo split de :data:`const.S3_BUCKET_ROTATIONS` que
    o Incremento 2 usou para os security groups), e sem ele o estado so ensinaria um dos
    vereditos de cada regra -- o consumidor nao teria como provar que distingue COMPLIANT
    de NON_COMPLIANT, porque nunca veria os dois.

    O ``IgnorePublicAcls`` fica num perfil proprio porque e o unico caso em que a ACL
    ARMAZADA e a ACL EFETIVA divergem, e a divergencia e o que a pagina de Block Public
    Access documenta. Um consumidor que le a resposta do ``GetBucketAcl`` e outro que le a
    ACL armazenada dao respostas diferentes nesse bucket -- e so nesse.
    """
    por_conta: dict[tuple[str, str], list[Resource]] = {}
    for resource in resources:
        if resource.identity.provider != const.PROVIDER_KEY_AWS or resource.resource_type != "s3_bucket":
            continue
        por_conta.setdefault((resource.parent_scope_id, resource.region_id), []).append(resource)

    posturas: list[AwsBucketPosture] = []
    for indice_conta, ((conta, _regiao), recursos) in enumerate(sorted(por_conta.items())):
        paridade = indice_conta % len(const.S3_BUCKET_ROTATIONS)
        rotacao = const.S3_BUCKET_ROTATIONS[paridade]
        # O ID canonico do owner e por CONTA, nao por bucket: a resposta de exemplo do
        # ``GetBucketAcl`` traz um hex de 64 caracteres, e o mesmo owner reaparece no
        # ``ListBuckets``. Derivar uma vez por conta deixa a invariante "um dono so" estrutural
        # em vez de coincidencial.
        owner_id = hashlib.sha256(f"aws-canonical-user:{conta}".encode()).hexdigest()
        ordenados = sorted(recursos, key=lambda item: item.identity.logical_path)
        for slot, resource in enumerate(ordenados):
            perfil = rotacao[slot % len(rotacao)]
            grants, policy, pab = const.S3_BUCKET_PROFILES[perfil]
            block, ignore, block_policy, restrict = pab
            posturas.append(
                AwsBucketPosture(
                    resource_uuid=resource.identity.uuid,
                    bucket_name=resource.resource_name,
                    account_id=conta,
                    region_id=resource.region_id,
                    creation_date=_aws_bucket_creation_date(seed, resource.identity.uuid),
                    owner=AwsAclOwner(display_name=None, id=owner_id),
                    acl_grants=_aws_bucket_grants(grants, owner_id),
                    policy=_aws_bucket_policy(policy, resource.resource_name),
                    public_access_block=AwsPublicAccessBlock(
                        block_public_acls=block,
                        ignore_public_acls=ignore,
                        block_public_policy=block_policy,
                        restrict_public_buckets=restrict,
                    ),
                    regional_access_block=_aws_regional_access_block(
                        const.S3_REGIONAL_ACCESS_BLOCK_ROTATION[slot % len(const.S3_REGIONAL_ACCESS_BLOCK_ROTATION)],
                        resource.region_id,
                    ),
                )
            )
    return tuple(posturas)


def _aws_regional_access_block(perfil: S3RegionalAccessSpec | None, region_id: str) -> AwsRegionalAccessBlock | None:
    """O bloco por REGIAO do bucket, ou ``None`` quando o perfil e ``None``.

    A rotacao e por SLOT dentro do perfil de bucket, e nao por conta: o bloco por regiao e uma
    configuracao de CONTA que o operador pode ter aplicado a alguns buckets do mesmo perfil de
    exposicao. Casar os dois nao diria nada, e o ``None`` aqui e o estado que importa -- uma
    conta que nunca configurou o bloco por regiao.

    O ``RegionPrefix`` sai da REGIAO DO PROPRIO BUCKET, e nao da constante: um bloco que nomeia
    um prefixo onde o bucket nao esta seria um bloco que nao se aplica a ele, e um consumidor nao
    distinguiria "nao configurado" de "configurado para outra regiao". Os dois membros de
    LOCALIZACAO precisam concordar entre si, e concordar com o bucket.
    """
    if perfil is None:
        return None
    block, ignore, block_policy, restrict = perfil
    return AwsRegionalAccessBlock(
        region_id=region_id,
        region_prefix=region_id,
        block_public_acls=block,
        ignore_public_acls=ignore,
        block_public_policy=block_policy,
        restrict_public_buckets=restrict,
    )


#: O sufixo do caminho IAM do gerador. Entra no digest das chaves para que dois usuarios com
#: o mesmo nome em contas diferentes nao compartilhem o mesmo ``AccessKeyId``.
_IAM_KEY_NAMESPACE = "aws-iam-access-key"


def _aws_access_key_id(seed: int, account_id: str, user_name: str, indice: int) -> str:
    """Um ``AccessKeyId`` com a forma que a AWS publica: ``AKIA`` + 16 caracteres.

    O prefixo ``AKIA`` e o que a API devolve para uma chave de longa vida do usuario, e o
    resto do e uppercase alfanumerico de 16. O valor em si e DERIVADO do
    ``(seed, conta, usuario, indice)`` -- uma chave de verdade e uma string que a AWS
    atribuiu, e um simulador que a sorteasse repetiria a mesma chave entre execucoes.
    """
    digest = hashlib.sha256(f"{_IAM_KEY_NAMESPACE}:{seed}:{account_id}:{user_name}:{indice}".encode()).hexdigest()
    alfabeto = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
    corpo = "".join(alfabeto[int(digest[pos : pos + 2], 16) % len(alfabeto)] for pos in range(0, 32, 2))
    return f"AKIA{corpo}"


def _aws_access_keys(
    seed: int, account_id: str, user_name: str, perfil: str, sim_now: date
) -> tuple[AwsAccessKey, ...]:
    """As chaves de um usuario, com as datas resolvidas a partir de ``sim_now``.

    As idades vem DECLARADAS em :data:`const.AWS_IAM_KEY_PROFILES` e sao contadas para tras
    de ``sim_now``. E o que faz ``access-keys-rotated`` ser um teste de idade: se as datas
    fossem soltas e a janela fosse um literal, bastaria o ``sim_now`` do estate passar da
    data da chave para o veredito virar sem que nada no estado tivesse mudado.
    """
    return tuple(
        AwsAccessKey(
            access_key_id=_aws_access_key_id(seed, account_id, user_name, indice),
            status=status,
            create_date=(sim_now - timedelta(days=idade)).isoformat(),
            last_used_date=None if ultimo_uso is None else (sim_now - timedelta(days=ultimo_uso)).isoformat(),
        )
        for indice, (status, idade, ultimo_uso) in enumerate(const.AWS_IAM_KEY_PROFILES[perfil])
    )


def _aws_iam_user(
    seed: int,
    account_id: str,
    user_name: str,
    *,
    path: str,
    tem_senha: bool,
    mfa_ativo: bool,
    perfil_chaves: str,
    sim_now: date,
) -> AwsIamUser:
    """Um usuario IAM com o ARN na forma que a AWS publica.

    O ARN leva o caminho: ``arn:aws:iam::<conta>:user[/<caminho>]<nome>``. O caminho do IAM
    comeca com barra (``/servico/``), mas no ARN a barra depois de ``user/`` ja e a do
    proprio ARN -- entao um caminho ``/`` produz ``...:user/<nome>`` e um caminho
    ``/servico/`` produz ``...:user/servico/<nome>``. Repetir a barra inicial daria
    ``...:user//servico/<nome>``, que nenhum ARN de usuario tem.

    As tres datas sao as que o credential report publica, e as DUAS de senha sao ``None``
    quando o usuario nao tem senha -- o report escreve ``N/A`` nesse caso, e um usuario de
    API sem senha e o caso comum, nao a excecao.
    """
    caminho = path.lstrip("/")
    chaves = _aws_access_keys(seed, account_id, user_name, perfil_chaves, sim_now)
    # O nascimento e derivado do proprio nome, para ser estavel entre execucoes e diferente
    # entre usuarios da mesma conta -- e a data mais antiga que a conta carrega.
    nascimento = hashlib.sha256(f"iam-user-created:{account_id}:{user_name}".encode()).hexdigest()
    criado = sim_now - timedelta(days=180 + int(nascimento[:8], 16) % 900)
    if tem_senha:
        senha_mudada = sim_now - timedelta(days=30 + int(nascimento[8:16], 16) % 400)
        senha_usada = sim_now - timedelta(days=1 + int(nascimento[16:24], 16) % 60)
    else:
        senha_mudada = None
        senha_usada = None
    return AwsIamUser(
        user_name=user_name,
        arn=f"arn:aws:iam::{account_id}:user/{caminho}{user_name}",
        path=path,
        password_enabled=tem_senha,
        mfa_active=mfa_ativo,
        access_keys=chaves,
        user_creation_time=criado.isoformat(),
        password_last_used=None if senha_usada is None else senha_usada.isoformat(),
        password_last_changed=None if senha_mudada is None else senha_mudada.isoformat(),
    )


def _aws_identity_postures(
    seed: int, orgs: Sequence[AwsOrg], sim_now: date
) -> tuple[AwsIdentityPosture, ...]:
    """A postura de IDENTIDADE de cada conta -- MFA do root, senha e chaves.

    Este e o Incremento 4: ate aqui as tres regras gerenciadas de identidade
    (``root-account-mfa-enabled``, ``iam-password-policy`` e ``access-keys-rotated``)
    respondiam ``INSUFFICIENT_DATA`` por falta do fato -- o estate nao carregava nenhum
    dado de IAM.

    A chave e a CONTA e nao um recurso, porque IAM e global: a senha, o MFA do root e as
    chaves nao tem regiao. Por isso a postura nao se repete por escopo regional, e por isso
    que a regra de IAM responde o MESMO veredito nas tres regioes de uma conta.

    Os tres eixos sao independentes DE PROPOSITO, e o estate tem exatamente tres contas em
    qualquer perfil (``_SCOPES_PER_PROVIDER = 3``): cada eixo reprova numa conta e cada
    reprovacao cai numa conta DIFERENTE. E o que torna os tres vereditos distinguiveis -- se
    duas regras reprovassem na mesma conta, um renderizador que as trocasse de lugar
    receberia a mesma resposta e passaria.

    Cada conta recebe ainda os tres usuarios fixos de :data:`const.AWS_IAM_FIXED_USERS`,
    identicos em todas as contas, para que nenhum dos tres eixos possa reprovar sozinho: a
    regra de chaves precisa de alguem que a aprove na conta que ela reprova, e o perfil
    ``inativa-antiga`` obriga a regra a olhar o ``status`` da chave.
    """
    contas = sorted((conta for org in orgs for conta in org.accounts), key=lambda item: item.account_id)
    posturas: list[AwsIdentityPosture] = []
    for indice, conta in enumerate(contas):
        eixo_root, eixo_senha, eixo_chaves = const.AWS_IAM_ROTATIONS[indice % len(const.AWS_IAM_ROTATIONS)]
        (
            minimo,
            simbolos,
            numeros,
            maiusculas,
            minusculas,
            pode_mudar,
            expira,
            max_dias,
        ) = const.AWS_IAM_PASSWORD_POLICIES[eixo_senha]
        root_ativo = eixo_root == const.AWS_IAM_ROOT_MFA_ACTIVE
        servico_user = _aws_iam_user(
            seed,
            conta.account_id,
            const.AWS_IAM_SERVICE_USER_NAME,
            path="/servico/",
            tem_senha=const.AWS_IAM_SERVICE_USER_HAS_PASSWORD,
            mfa_ativo=True,
            perfil_chaves=eixo_chaves,
            sim_now=sim_now,
        )
        roster = const.AWS_IAM_FIXED_USERS if root_ativo else (
            *const.AWS_IAM_FIXED_USERS,
            *const.AWS_IAM_ROOT_MFA_INACTIVE_ACCOUNT_USERS,
        )
        fixos = tuple(
            _aws_iam_user(
                seed,
                conta.account_id,
                user_name,
                path=path,
                tem_senha=tem_senha,
                mfa_ativo=mfa_ativo,
                perfil_chaves=perfil,
                sim_now=sim_now,
            )
            for user_name, path, tem_senha, mfa_ativo, perfil in roster
        )
        posturas.append(
            AwsIdentityPosture(
                account_id=conta.account_id,
                # A conta root so recebe chaves de longa vida em pares: 0 quando a conta
                # nao tem nenhuma, 2 no par que a AWS cria. Um numero impar nao existe.
                root_mfa=AwsRootAccountMfa(
                    mfa_active=root_ativo,
                    root_access_keys=0 if root_ativo else 2,
                    # A conta root nasce com a conta de usuario do estate -- e o que o report
                    # publica, e uma data que antecede todo o resto da identidade dela.
                    user_creation_time=(sim_now - timedelta(days=1460)).isoformat(),
                    root_access_key_last_rotated=(
                        None if root_ativo else (sim_now - timedelta(days=640)).isoformat()
                    ),
                ),
                password_policy=AwsPasswordPolicy(
                    minimum_password_length=minimo,
                    require_symbols=simbolos,
                    require_numbers=numeros,
                    require_uppercase=maiusculas,
                    require_lowercase=minusculas,
                    allow_users_to_change_password=pode_mudar,
                    hard_expiry=expira,
                    max_password_age_days=max_dias,
                    password_reuse_prevention=24 if expira else None,
                ),
                users=(servico_user, *fixos),
            )
        )
    return tuple(posturas)


def _flow_windows(sim_now: date) -> tuple[tuple[datetime, datetime], ...]:
    """As ultimas janelas de fluxo do ultimo dia do estado, em UTC."""
    fim_do_dia = datetime.combine(sim_now + timedelta(days=1), time(0, 0), tzinfo=UTC)
    passo = timedelta(minutes=FLOW_WINDOW_MINUTES)
    return tuple(
        (fim_do_dia - passo * (indice + 1), fim_do_dia - passo * indice)
        for indice in reversed(range(FLOW_WINDOWS))
    )


#: Namespaces que o ASFF publica para ``Types``. Lista FECHADA na spec, e a unica
#: parte da forma ``namespace/category/classifier`` que a documentacao restringe;
#: os outros dois segmentos sao a classificacao do provedor.
FINDING_TYPE_NAMESPACES: tuple[str, ...] = (
    "Software and Configuration Checks",
    "TTPs",
    "Effects",
    "Unusual Behaviors",
    "Sensitive Data Identifications",
)

#: Titulo e descricao por categoria nativa. Sao strings que o PROVEDOR geraria --
#: o ASFF permite boilerplate -- e existem porque `Title` e `Description` sao
#: obrigatorios no ASFF e saiam vazios.
FINDING_TEXT_BY_CATEGORY: dict[str, tuple[str, str]] = {
    "NETWORK": (
        "Network exposure detected on {recurso}",
        "Um caminho de rede do recurso {recurso} esta alcancavel a partir de uma origem "
        "que a linha de base considera indevida.",
    ),
    "IAM": (
        "Over-permissive identity policy on {recurso}",
        "A politica de identidade associada a {recurso} concede mais permissao do que a "
        "linha de base da organizacao permite.",
    ),
    "CONFIG": (
        "Configuration drifted from baseline on {recurso}",
        "A configuracao declarada de {recurso} difere da linha de base registrada para o "
        "tipo de recurso.",
    ),
}

#: Classificador neutro por categoria, para o terceiro segmento de ``Types``.
FINDING_CLASSIFIER_BY_CATEGORY: dict[str, str] = {
    "NETWORK": "Network Exposure",
    "IAM": "Identity Permissions",
    "CONFIG": "Configuration Baseline",
}


#: Procedencia da finding. A documentacao publica os limites (generator 1-512,
#: nome e empresa 1-128); os VALORES sao nossos, porque somos o produto que gera.
FINDING_GENERATOR_ID = "synthetic-clouds/baseline"
FINDING_PRODUCT_NAME = "Synthetic Cloud Simulator"
FINDING_COMPANY_NAME = "Synthetic Clouds"


def finding_provenance(seed: int, resource_uuid: str, raised_on: date) -> dict[str, Any]:
    """Procedencia e escalas da finding, deterministas por recurso.

    Sai de um stream PROPRIO, indexado pelo recurso: usar o stream posicional
    deslocaria os sorteios seguintes e mudaria artefatos ja estaveis byte a byte.
    O ajudante existe para o gerador base e o C09 nao divergirem sobre o mesmo
    fato -- o cenario cria findings por outro caminho.
    """
    attrs = stream_rng(seed, f"finding-attrs/{resource_uuid}")
    observado_em = datetime.combine(
        raised_on, time(hour=attrs.randrange(24), minute=attrs.randrange(60)), tzinfo=UTC
    )
    return {
        "generator_id": FINDING_GENERATOR_ID,
        "product_name": FINDING_PRODUCT_NAME,
        "company_name": FINDING_COMPANY_NAME,
        "first_observed_at": observado_em,
        "confidence": attrs.randint(50, 99),
        "criticality": attrs.randint(1, 100),
    }


def _finding_types(category: str) -> tuple[str, ...]:
    """``Types`` na forma documentada, com o namespace da lista fechada da spec."""
    classificador = FINDING_CLASSIFIER_BY_CATEGORY.get(category, "Baseline")
    return (f"{FINDING_TYPE_NAMESPACES[0]}/Cloud Best Practices/{classificador}",)


def _finding_text(category: str, resource_name: str) -> tuple[str, str]:
    """Titulo e descricao do finding, com o nome do recurso interpolado."""
    titulo, descricao = FINDING_TEXT_BY_CATEGORY.get(
        category,
        ("Baseline control not met on {recurso}", "O recurso {recurso} nao atende a linha de base."),
    )
    return titulo.format(recurso=resource_name), descricao.format(recurso=resource_name)


def _resources_per_scope(profile: str) -> int:
    """Return the per-scope resource count that targets each profile's row band.

    FOCUS rows are dominated by daily billing lines (~1 per resource per day), but
    scenario emission multiplies the base: FR-D4 duplicates, C05 daily Unused lines,
    the C15 K8s per-namespace split, C17 restatement, and C18. The base per-scope
    count is divided by ``_SCENARIO_EXPANSION`` so the FINAL (post-scenario) FOCUS
    row count lands within the +/-10% band (AC-17 / OA-8).
    """
    window = const.PROFILE_WINDOW_DAYS[profile]
    target = const.PROFILE_TARGET_ROWS[profile]
    scopes = len(const.PROVIDER_KEYS) * _SCOPES_PER_PROVIDER
    return max(1, round(target / (scopes * window * _SCENARIO_EXPANSION)))


@dataclass(slots=True, frozen=True)
class _ScopedResource:
    """A resource plus the billing-account + provider context it was built in."""

    resource: Resource
    billing_account_id: str
    provider: str
    service_name: str
    service_category: str
    sku_id: str
    unit: str
    list_unit_price: Decimal


class EstateBuilder:
    """Builds a ``CanonicalEstate`` deterministically from ``(seed, profile, currency)``."""

    def __init__(
        self,
        seed: int,
        profile: str,
        currency: str,
        sim_start: date | None = None,
        window_days: int | None = None,
    ) -> None:
        if profile not in const.PROFILE_WINDOW_DAYS:
            raise ValueError(f"unknown profile {profile!r}")
        if currency not in ("USD", "BRL"):
            raise ValueError(f"unknown currency {currency!r}")
        self.seed = seed
        self.profile = profile
        self.currency = currency
        self.identity = IdentityFactory(seed=seed)
        self.clock = SimClock.starting_at(
            sim_start or CANONICAL_EPOCH,
            window_days or const.PROFILE_WINDOW_DAYS[profile],
        )
        self._seen_paths: set[str] = set()

    # ── hierarchy ────────────────────────────────────────────────────────────

    def _path(self, logical_path: str, provider: str) -> ResourceIdentity:
        if logical_path in self._seen_paths:
            raise ValueError(f"duplicate logical_path collision: {logical_path}")
        self._seen_paths.add(logical_path)
        return self.identity.for_path(logical_path, provider)

    def _build_hierarchy(
        self,
    ) -> tuple[
        tuple[BillingAccount, ...],
        tuple[AzureMgmtGroup, ...],
        tuple[GcpOrg, ...],
        tuple[AwsOrg, ...],
        list[tuple[str, str, str]],
    ]:
        """Return billing accounts, Azure MGs, GCP orgs, AWS orgs, and scope descriptors.

        A scope descriptor is ``(provider, scope_id, billing_account_id)`` — the
        3 Azure subscriptions + 3 GCP projects + 3 AWS accounts resources attach to.
        """
        accounts: list[BillingAccount] = []
        scopes: list[tuple[str, str, str]] = []

        azure_ba = [f"ba-azure-{i}" for i in (1, 2)]
        gcp_ba = [f"ba-gcp-{i}" for i in (1, 2)]
        for i, ba in enumerate(azure_ba, start=1):
            accounts.append(
                BillingAccount(
                    identity=self._path(f"azure/billing-account/{ba}", "azure"),
                    provider="azure",
                    billing_account_id=ba,
                    name=synth_name(f"Azure Billing {i}"),
                    currency=self.currency,
                )
            )
        for i, ba in enumerate(gcp_ba, start=1):
            accounts.append(
                BillingAccount(
                    identity=self._path(f"gcp/billing-account/{ba}", "gcp"),
                    provider="gcp",
                    billing_account_id=ba,
                    name=synth_name(f"GCP Billing {i}"),
                    currency=self.currency,
                )
            )

        subs: list[AzureSubscription] = []
        for i in range(1, 4):
            sub_id = f"sub-{i:02d}"
            ba = azure_ba[(i - 1) % len(azure_ba)]
            subs.append(
                AzureSubscription(
                    identity=self._path(f"azure/subscription/{sub_id}", "azure"),
                    subscription_id=sub_id,
                    billing_account_id=ba,
                    name=synth_name(f"Azure Sub {i}"),
                )
            )
            scopes.append(("azure", sub_id, ba))
        mgmt = AzureMgmtGroup(
            identity=self._path("azure/mgmt-group/root", "azure"),
            tenant_id="00000000-0000-0000-0000-00000000c047",  # fictional contoso tenant
            name=synth_name("Root Management Group"),
            subscriptions=tuple(subs),
        )

        projects: list[GcpProject] = []
        for i in range(1, 4):
            proj_id = f"contoso-prod-{i:02d}"
            ba = gcp_ba[(i - 1) % len(gcp_ba)]
            projects.append(
                GcpProject(
                    identity=self._path(f"gcp/project/{proj_id}", "gcp"),
                    project_id=proj_id,
                    billing_account_id=ba,
                    name=synth_name(f"GCP Project {i}"),
                )
            )
            scopes.append(("gcp", proj_id, ba))
        folder = GcpFolder(
            identity=self._path("gcp/folder/eng", "gcp"),
            folder_id="folders/100100100",
            projects=tuple(projects),
        )
        org = GcpOrg(
            identity=self._path("gcp/org/contoso", "gcp"),
            org_id="organizations/900900900",
            domain=FICTIONAL_DOMAIN,
            folders=(folder,),
        )

        aws_ba = [f"ba-aws-{i}" for i in (1, 2)]
        for i, ba in enumerate(aws_ba, start=1):
            accounts.append(
                BillingAccount(
                    identity=self._path(f"aws/billing-account/{ba}", "aws"),
                    provider="aws",
                    billing_account_id=ba,
                    name=synth_name(f"AWS Billing {i}"),
                    currency=self.currency,
                )
            )

        # The scope id IS the 12-digit account id, mirroring Azure (scope id ==
        # subscription id) and GCP (scope id == project id). Keeping one id means
        # ``Resource.parent_scope_id``, ``BillingLine.sub_account_id`` and the
        # FOCUS ``SubAccountId`` are the same value, and the minting stays in
        # ``identity.aws_account_id`` rather than being redone at render time.
        aws_accounts: list[AwsAccount] = []
        for i in range(1, _SCOPES_PER_PROVIDER + 1):
            account_id = aws_account_id(self.seed, f"acct-{i:02d}")
            ba = aws_ba[(i - 1) % len(aws_ba)]
            aws_accounts.append(
                AwsAccount(
                    identity=self._path(f"aws/account/{account_id}", "aws"),
                    account_id=account_id,
                    billing_account_id=ba,
                    name=synth_name(f"AWS Account {i}"),
                )
            )
            scopes.append(("aws", account_id, ba))
        aws_org = AwsOrg(
            identity=self._path("aws/org/contoso", "aws"),
            # A realistic AWS organization id shape (``o-`` + 10 lowercase alnum). It used to
            # read ``o-9synth0001``, which put the word "synth" inside a real field of the
            # ``ListAccounts`` response (the account ARN path).
            org_id="o-8f2c1a9b7d",
            accounts=tuple(aws_accounts),
        )
        return tuple(accounts), (mgmt,), (org,), (aws_org,), scopes

    # ── resources ────────────────────────────────────────────────────────────

    def _build_resources(self, scopes: list[tuple[str, str, str]]) -> list[_ScopedResource]:
        per_scope = _resources_per_scope(self.profile)
        name_rng = stream_rng(self.seed, "off-standard-names")
        scoped: list[_ScopedResource] = []
        for provider, scope_id, ba in scopes:
            services = const.PROVIDER_SERVICES[provider]
            regions = const.PROVIDER_REGIONS[provider]
            for n in range(per_scope):
                resource_type, service_name, service_category, sku_id, unit, list_price = services[n % len(services)]
                region_id, region_name = regions[n % len(regions)]
                res_name = off_standard_name(f"{resource_type}-{n:04d}", name_rng)
                ident = self._path(f"{provider}/{scope_id}/{resource_type}/{n:04d}", provider)
                tags = tuple((k, f"{k}-{scope_id}") for k in const.STANDARD_TAG_KEYS)
                scoped.append(
                    _ScopedResource(
                        resource=Resource(
                            identity=ident,
                            parent_scope_id=scope_id,
                            service_name=service_name,
                            service_category=service_category,
                            resource_type=resource_type,
                            resource_name=res_name,
                            region_id=region_id,
                            region_name=region_name,
                            tags=tags,
                            sku_id=sku_id,
                            # Attached by ``_attach_capacity_reservations`` once the
                            # resource set exists: eligibility and the two draws are one
                            # decision, and it reads better in one place than in this loop.
                            capacity_reservation=None,
                        ),
                        billing_account_id=ba,
                        provider=provider,
                        service_name=service_name,
                        service_category=service_category,
                        sku_id=sku_id,
                        unit=unit,
                        list_unit_price=list_price,
                    )
                )
        untagged_rng = stream_rng(self.seed, "untagged")
        stripped = apply_untagged([sr.resource for sr in scoped], untagged_rng)
        return [replace(sr, resource=r) for sr, r in zip(scoped, stripped, strict=True)]

    # ── capacity reservations ─────────────────────────────────────────────────

    def _capacity_reservation(self, sr: _ScopedResource) -> CapacityReservation | None:
        """Return the capacity reservation this resource carries, or ``None``.

        Three conditions, all read off the model or off a table rather than invented
        here: the resource's type must be one the provider's
        ``const.CAPACITY_RESERVATION_TYPES`` lists (an AWS capacity reservation is an
        EC2 construct, so storage, network and the other compute services are not
        eligible), the resource must win the coverage draw, and the reservation must
        win the status draw. The last two come from NAMED streams keyed per resource
        (``capacity-reservation/<resource uuid>`` — the Slice 1 discipline), which makes
        both a pure function of ``(seed, resource)``: the same seed reproduces the same
        reservations whatever order resources are visited in and whatever window is
        generated, so the daily and the one-shot surfaces agree.

        Coverage is deliberately partial (``const.CAPACITY_RESERVATION_COVERAGE``) and so
        is the used share (``const.CAPACITY_RESERVATION_USED_SHARE``): an estate with
        every instance reserved, or with every reservation consumed, would make the
        ``Unused`` half of the FOCUS column unreachable — and the two states are what a
        reservation-coverage reader has to see.

        The period is the window being generated, like ``Commitment.period_start``/
        ``period_end``: the reservation is in force for the days this estate covers.
        """
        eligible = const.CAPACITY_RESERVATION_TYPES.get(sr.provider, ())
        if sr.resource.resource_type not in eligible:
            return None
        uuid = sr.resource.identity.uuid
        if stream_rng(self.seed, f"capacity-reservation/{uuid}").random() >= const.CAPACITY_RESERVATION_COVERAGE:
            return None
        used_status, unused_status = const.CAPACITY_RESERVATION_STATUSES
        status = (
            used_status
            if stream_rng(self.seed, f"capacity-reservation-status/{uuid}").random()
            < const.CAPACITY_RESERVATION_USED_SHARE
            else unused_status
        )
        return CapacityReservation(
            reservation_id=capacity_reservation_id(self.seed, uuid),
            resource_uuid=uuid,
            scope_id=sr.resource.parent_scope_id,
            period_start=self.clock.sim_start,
            period_end=self.clock.sim_now,
            status=status,
        )

    def _attach_capacity_reservations(self, scoped: list[_ScopedResource]) -> list[_ScopedResource]:
        """Put each resource's reservation on the resource the FOCUS columns project from.

        A post-pass rather than a step inside ``_build_resources`` so the eligibility and
        the two draws read as one decision (``_capacity_reservation``) instead of being
        scattered through the resource loop — the same shape ``apply_untagged`` uses.
        """
        return [
            replace(sr, resource=replace(sr.resource, capacity_reservation=self._capacity_reservation(sr)))
            for sr in scoped
        ]

    # ── prices ───────────────────────────────────────────────────────────────

    def _build_prices(self, scoped: list[_ScopedResource]) -> tuple[list[ListPrice], list[ContractedPrice]]:
        seen: dict[str, _ScopedResource] = {}
        for sr in scoped:
            seen.setdefault(sr.sku_id, sr)
        list_prices: list[ListPrice] = []
        contracted: list[ContractedPrice] = []
        for sku_id, sr in sorted(seen.items()):
            list_prices.append(ListPrice(sku_id, sr.unit, _q(sr.list_unit_price), self.currency))
            contracted.append(
                ContractedPrice(sku_id, sr.unit, _q(sr.list_unit_price * const.CONTRACTED_DISCOUNT), self.currency, None)
            )
        return list_prices, contracted

    # ── consumption + billing ──────────────────────────────────────────────────

    def _covering_commitment(
        self, sr: _ScopedResource, commitments: dict[str, Commitment]
    ) -> Commitment | None:
        """Return the commitment that covers this resource's usage, or ``None``.

        Two conditions, both read off the model rather than invented here: the
        resource's scope must HAVE a commitment, and the resource's metered unit must be
        the unit that commitment kind covers (``const.COMMITMENT_UNIT`` — compute
        hours). Which of the eligible resources a commitment actually covers is then
        drawn from the named ``commitment-coverage/<resource uuid>`` stream: a pure
        function of ``(seed, resource)``, so the same seed reproduces the same coverage
        whatever order resources are visited in, and the choice follows the RESOURCE for
        the whole period instead of alternating by day — which is what a Savings Plan or
        a reservation actually does.

        Coverage is deliberately partial (``const.COMMITMENT_COVERAGE``): an estate with
        every eligible hour committed is as unfaithful as one with none, and the covered
        and uncovered halves together are what a commitment-coverage engine has to read.

        The id this stamps lands in the AWS FOCUS and Azure FOCUS
        ``CommitmentDiscount*`` columns, which both renderers project. The GCP BigQuery
        export carries no commitment columns by design — its CUD surfaces through the
        ``credits`` array (``render/gcp_bigquery_topology.py``) — so there is no third
        projection to keep in step.
        """
        commitment = commitments.get(sr.resource.parent_scope_id)
        if commitment is None or sr.unit != commitment.unit:
            return None
        draw = stream_rng(self.seed, f"commitment-coverage/{sr.resource.identity.uuid}").random()
        return commitment if draw < const.COMMITMENT_COVERAGE else None

    def _build_consumption_and_billing(
        self, scoped: list[_ScopedResource], commitments: dict[str, Commitment]
    ) -> tuple[list[DailyConsumption], list[BillingLine], dict[str, Decimal]]:
        """Emit daily consumption and a billing line for the billed resources.

        A resource whose list price is **zero** gets consumption but **no billing line**.
        That is how the catalog models a resource AWS does not charge for — a VPC, a
        security group — without inventing a rate: real FOCUS output carries no line for
        them either, so emitting a zero-cost line would be less faithful than emitting
        none, not more.

        Returns the covered quantity per scope as well: it is the amount the scope's
        commitment covers, i.e. ``Commitment.quantity``, and only the usage lines know
        it. Summed here, before ``duplicate_billing_lines`` copies ~2% of the lines, so a
        benign FR-D4 duplicate does not inflate the commitment it belongs to.
        """
        days = self.clock.days()
        consumption: list[DailyConsumption] = []
        billing: list[BillingLine] = []
        covered_quantity: dict[str, Decimal] = {}
        jitter_rng = stream_rng(self.seed, "consumption-jitter")
        for sr in scoped:
            contracted_unit = _q(sr.list_unit_price * const.CONTRACTED_DISCOUNT)
            billable = sr.list_unit_price != 0
            commitment = self._covering_commitment(sr, commitments)
            for day_index, day in enumerate(days):
                qty = daily_quantity(_BASE_DAILY_UNITS, day.weekday(), day_index, jitter_rng)
                export_time = export_time_for(day)
                consumption.append(
                    DailyConsumption(
                        resource_uuid=sr.resource.identity.uuid,
                        usage_date=day,
                        export_time=export_time,
                        quantity=_q(qty),
                        unit=sr.unit,
                        is_restatement=False,
                        restates_date=None,
                    )
                )
                if billable:
                    if commitment is not None:
                        # Accumulated at the SAME 6-dp as the line's own
                        # ``pricing_quantity``, so the commitment's quantity is exactly
                        # the sum of the quantities its rows carry.
                        covered_quantity[commitment.scope_id] = (
                            covered_quantity.get(commitment.scope_id, Decimal("0")) + _q(qty)
                        )
                    billing.append(
                        self._billing_line(
                            sr=sr,
                            day=day,
                            qty=qty,
                            contracted_unit=contracted_unit,
                            export_time=export_time,
                            commitment=commitment,
                        )
                    )
        return consumption, billing, covered_quantity

    def _billing_line(
        self,
        *,
        sr: _ScopedResource,
        day: date,
        qty: Decimal,
        contracted_unit: Decimal,
        export_time: datetime,
        commitment: Commitment | None,
    ) -> BillingLine:
        res = sr.resource
        list_cost = _q(sr.list_unit_price * qty)
        contracted_cost = _q(contracted_unit * qty)
        line_id = self.identity.uuid_for(f"line/{res.identity.uuid}/{day.isoformat()}/Usage")
        charge_start = datetime.combine(day, _MIDDAY, tzinfo=UTC)
        provider_name = const.FOCUS_PROVIDER_NAME[sr.provider]
        return BillingLine(
            line_id=line_id,
            resource_uuid=res.identity.uuid,
            billing_account_id=sr.billing_account_id,
            sub_account_id=res.parent_scope_id,
            invoice_id=None,
            service_name=sr.service_name,
            service_category=sr.service_category,
            charge_category="Usage",
            charge_period_start=charge_start,
            charge_period_end=charge_start + timedelta(days=1),
            billing_period_start=day.replace(day=1),
            billing_period_end=_month_end(day),
            export_time=export_time,
            is_restatement=False,
            restates_date=None,
            billed_cost=contracted_cost,
            effective_cost=contracted_cost,
            list_cost=list_cost,
            contracted_cost=contracted_cost,
            pricing_quantity=_q(qty),
            pricing_unit=sr.unit,
            pricing_category="Standard",
            region_id=res.region_id,
            region_name=res.region_name,
            tags=res.tags,
            # A covered line carries the id of the commitment that covers it and the
            # status that says so; an uncovered line carries neither rather than a
            # placeholder. ``Unused`` stays reachable through the scenario emitters
            # (C05/A01), which is where a commitment's unused half belongs.
            commitment_discount_id=None if commitment is None else commitment.identity.uuid,
            commitment_discount_status=None if commitment is None else "Used",
            currency=self.currency,
            service_provider_name=provider_name,
            is_duplicate=False,
            source_fingerprint=source_fingerprint(line_id),
        )

    # ── correlated entities (bound to identity, P2) ────────────────────────────

    def _build_inventory(self, scoped: list[_ScopedResource]) -> list[InventoryAsset]:
        iac_rng = stream_rng(self.seed, "iac-managed")
        return [
            InventoryAsset(
                resource_uuid=sr.resource.identity.uuid,
                asset_type=f"{sr.provider}/{sr.resource.resource_type}",
                config_json=synthetic_metadata(region=sr.resource.region_id),
                managed_by_iac=iac_rng.random() > 0.2,
            )
            for sr in scoped
        ]

    def _build_findings(self, scoped: list[_ScopedResource]) -> list[NativeFinding]:
        """One baseline finding per flagged resource, dated for the daily cadence.

        ``raised_on`` is drawn from a **per-resource** stream, so it is a pure function
        of ``(seed, resource)``: the same resource raises the same finding on the same
        day whichever window is generated. The finding is skipped while its day is
        still in the future, which is what makes alerts accumulate across a month
        instead of all existing from day one (FR-22.3).

        The skip/choice draws stay on the positional ``findings`` stream. That is safe
        here because ``scoped`` does not depend on the window — the resource set is
        static — so any two windows with the same seed/profile/currency see the same
        draw sequence, and the existing artifact stays byte-identical.
        """
        rng = stream_rng(self.seed, "findings")
        findings: list[NativeFinding] = []
        for sr in scoped:
            if rng.random() > 0.25:
                continue
            uuid = sr.resource.identity.uuid
            raised_on = self.clock.sim_start + timedelta(
                days=stream_rng(self.seed, f"raised-on/{uuid}").randrange(RAISED_ON_SPAN_DAYS),
            )
            if raised_on > self.clock.sim_now:
                continue
            # A ORDEM dos sorteios e preservada (categoria, depois severidade):
            # trocar a ordem deslocaria o stream posicional e mudaria artefatos ja
            # estaveis byte a byte.
            categoria = rng.choice(("NETWORK", "IAM", "CONFIG"))
            severidade = rng.choice(("CRITICAL", "HIGH", "MEDIUM", "LOW"))
            titulo, descricao = _finding_text(categoria, sr.resource.resource_name)
            findings.append(
                NativeFinding(
                    finding_id=self.identity.uuid_for(f"finding/{uuid}/baseline"),
                    resource_uuid=uuid,
                    provider=sr.provider,
                    category=categoria,
                    severity=severidade,
                    status="open",
                    raised_on=raised_on,
                    source=SOURCE_SYNTHETIC,
                    evidence_json=synthetic_evidence(rule="baseline"),
                    title=titulo,
                    description=descricao,
                    types=_finding_types(categoria),
                    **finding_provenance(self.seed, uuid, raised_on),
                )
            )
        return findings

    def _build_recommendations(self, scoped: list[_ScopedResource]) -> list[NativeRecommendation]:
        rng = stream_rng(self.seed, "recommendations")
        recs: list[NativeRecommendation] = []
        for sr in scoped:
            if rng.random() > 0.2:
                continue
            uuid = sr.resource.identity.uuid
            recs.append(
                NativeRecommendation(
                    recommendation_id=self.identity.uuid_for(f"rec/{uuid}/baseline"),
                    resource_uuid=uuid,
                    provider=sr.provider,
                    kind=rng.choice(("rightsize", "idle", "sku_change")),
                    recommendation_model=RECOMMENDATION_MODEL,
                    detail_json=synthetic_metadata(kind="baseline"),
                )
            )
        return recs

    def _build_metrics(self, scoped: list[_ScopedResource]) -> list[MetricSeries]:
        """One ``cpu_utilization`` series per metered resource, plus memory where asked.

        **Cadence: HOURLY.** Each series carries one point per hour of every simulated
        day — 24 points per day, on the hour, in UTC (:func:`_metric_grid`) — because
        that is the grain the consumer queries at (``Period=3600``) and therefore the
        grain its coverage gate can accept; see the cadence block above for the gate
        itself and for why one point per day is structurally unreadable. The daily and
        the one-shot surfaces both build the grid from the window's own days, so they
        agree for the same window.

        **Shape: the workload band, drawn once, then an intra-day cycle.** A resource's
        sample at hour ``h`` is ``uniform(band_low, band_high) * shape[h]`` — a fresh
        draw inside the resource's band (see :data:`_CPU_UTILIZATION_BANDS`), scaled by
        the hour's factor from :data:`_METRIC_INTRADAY_SHAPE`, which peaks at exactly
        1.0. The window's maximum therefore lands on the top of the band at the
        resource's peak hour, which is the number the rightsizing detector reads: it
        compares the PEAK, not the mean. Between the two factors the day is a real
        load curve rather than 24 identical values, and the verdict stays a property of
        the resource's class rather than of the hour it was sampled in.

        Values come from a stream keyed **per resource** (``metric/<resource uuid>`` —
        the Slice 1 discipline ``_capacity_reservation`` and ``_build_findings`` already
        follow) instead of one positional stream shared by the metered resources in visit
        order. Two properties follow, and both are why this is keyed rather than positional:

        * adding a resource TYPE cannot shift the values another type already had. Under
          the positional stream the draws were consumed in visit order, so metering a new
          type anywhere but last re-rolled every series after it — the AWS types this
          module now meters would have silently rewritten Azure's and GCP's;
        * a resource's series is a pure function of ``(seed, resource, position in the
          window)``, so the daily and the one-shot surfaces agree for the same window
          without either having to know what the other generated.

        Non-AWS series' VALUES DID CHANGE when this was keyed. That is expected: at that
        point the value distribution was untouched and the series set was unchanged — only
        a different stream supplied each series. Nothing pinned the old values, then or
        now — no test, no golden file. The same holds for the grain change to hourly: the
        series each resource reports is a different, longer one, and nothing pinned the
        midday-only sample except the test that pinned the old cadence, which was
        re-expressed for this grain.

        Samples are PERCENTAGES of the resource's CPU, drawn from the per-resource
        workload band :func:`_cpu_utilization_band` picks out of
        :data:`_CPU_UTILIZATION_BANDS` — see that block for the consumers' unit and
        thresholds this domain answers to, and for why the mixture is per resource.

        The types in :data:`_MEMORY_METERED_RESOURCE_TYPES` get a SECOND series in the
        same pass — ``memory_utilization``, same cadence, same per-resource stream, drawn
        after that resource's CPU draws so the CPU series keep their existing bytes. See
        the ``memory_utilization`` domain above for the consumer gate that requires it.
        """
        grid = _metric_grid(self.clock.days())
        series: list[MetricSeries] = []
        for sr in scoped:
            resource_type = sr.resource.resource_type
            if resource_type not in _METERED_RESOURCE_TYPES:
                continue
            resource_uuid = sr.resource.identity.uuid
            rng = stream_rng(self.seed, f"metric/{resource_uuid}")
            low, high = _cpu_utilization_band(rng)
            points = tuple(
                MetricPoint(ts=ts, value=round(rng.uniform(low, high) * shape, 4)) for ts, shape in grid
            )
            series.append(
                MetricSeries(
                    resource_uuid=resource_uuid,
                    metric_name=_CPU_UTILIZATION,
                    points=points,
                )
            )
            if resource_type not in _MEMORY_METERED_RESOURCE_TYPES:
                continue
            memory_low, memory_high = _memory_utilization_band(rng)
            series.append(
                MetricSeries(
                    resource_uuid=resource_uuid,
                    metric_name=_MEMORY_UTILIZATION,
                    points=tuple(
                        MetricPoint(ts=ts, value=round(rng.uniform(memory_low, memory_high) * shape, 4))
                        for ts, shape in grid
                    ),
                )
            )
        return series

    def _build_iac(self, scoped: list[_ScopedResource], inventory: list[InventoryAsset]) -> list[IacStateSnapshot]:
        managed_uuids = {a.resource_uuid for a in inventory if a.managed_by_iac}
        captured = datetime.combine(self.clock.sim_now, _MIDDAY, tzinfo=UTC)
        # Garante pelo menos um drift por (provider, escopo): sem isso um projeto
        # inteiro podia ficar sem diff e a emulação daquela conta responderia lista
        # vazia, que é indistinguível de "não há drift". A âncora é o menor uuid
        # com tags, então a escolha é determinística.
        first_by_scope: dict[tuple[str, str, str], str] = {}
        for sr in scoped:
            if sr.resource.identity.uuid not in managed_uuids:
                continue
            provider = sr.resource.identity.provider
            if provider not in (const.PROVIDER_KEY_GCP, const.PROVIDER_KEY_AZURE):
                continue
            if not sr.resource.tags:
                continue
            key = (provider, sr.resource.parent_scope_id, sr.resource.resource_type)
            atual = first_by_scope.get(key)
            if atual is None or sr.resource.identity.uuid < atual:
                first_by_scope[key] = sr.resource.identity.uuid
        by_scope: dict[str, list[IacResourceState]] = {}
        for sr in scoped:
            if sr.resource.identity.uuid not in managed_uuids:
                continue
            declared: dict[str, Any] = {
                "type": sr.resource.resource_type,
                "region": sr.resource.region_id,
            }
            # C11: o snapshot carrega as TAGS declaradas. Para um subconjunto
            # determinístico, uma chave é omitida -- é o input de drift (o
            # consumidor compara com as tags que o inventário publica), não um
            # veredito. A chave omitida é sempre a primeira em ordem, então o
            # mesmo seed produz o mesmo diff.
            if sr.resource.identity.provider in (const.PROVIDER_KEY_GCP, const.PROVIDER_KEY_AZURE):
                tags = dict(sorted(sr.resource.tags))
                digest = int(hashlib.sha256(sr.resource.identity.uuid.encode()).hexdigest(), 16)
                anchor = first_by_scope.get(
                    (sr.resource.identity.provider, sr.resource.parent_scope_id, sr.resource.resource_type)
                )
                if tags and (digest % 5 == 0 or sr.resource.identity.uuid == anchor):
                    tags.pop(next(iter(tags)))
                declared["tags"] = tags
            by_scope.setdefault(sr.resource.parent_scope_id, []).append(
                IacResourceState(
                    resource_uuid=sr.resource.identity.uuid,
                    declared_config=declared,
                )
            )
        return [
            IacStateSnapshot(
                snapshot_id=self.identity.uuid_for(f"iac/{scope_id}/snapshot"),
                scope_id=scope_id,
                captured_at=captured,
                resource_states=tuple(by_scope[scope_id]),
                metadata=synthetic_metadata(scope=scope_id),
            )
            for scope_id in sorted(by_scope)
        ]

    # ── rede: inventario primeiro, fluxo depois (docs/MODELO-REDE.md) ─────────

    def _segment(self, provider: str, scope_id: str, region: str, segment_uuid: str) -> NetworkSegment:
        """O segmento de rede do escopo, com os ids nativos que a nuvem usa.

        Os ids nao sao decoracao: o caminho documentado do blob da Azure exige
        resource group, VNet e NSG, e o ``systemId`` do NSG e o GUID da NSG --
        nao a assinatura. Inventar isso no renderer seria inventar identidade.
        """
        nome = f"synthetic-net-{segment_uuid[:8]}"
        # A NSG tambem e por REGIAO: se o segmento passa a ser regional, uma NSG por
        # escopo faria tres segmentos reivindicarem a MESMA NSG -- e o id dela e uma
        # afirmacao sobre o provedor, nao um apelido.
        nsg_uuid = self.identity.uuid_for(f"network-nsg/{provider}/{scope_id}/{region}")

        if provider == SCOPE_PROVIDER_AZURE:
            grupo = f"synthetic-rg-{scope_id[:8]}"
            # O ARM id leva o GUID da assinatura, NAO o rotulo do escopo: o FOCUS
            # ja estampa ``azure_subscription_guid`` no SubAccountId e o promotor
            # da Azure valida a forma 8-4-4-4-12. Embutir ``sub-01`` aqui criava
            # duas grafias da MESMA assinatura -- e um id ARM e uma afirmacao sobre
            # o provedor, nao um apelido interno.
            assinatura = azure_subscription_guid(self.seed, scope_id)
            base = (
                f"/subscriptions/{assinatura}/resourceGroups/{grupo}"
                f"/providers/Microsoft.Network"
            )
            nsg_name = f"{nome}-nsg"
            nsg = NetworkSecurityGroup(
                subscription_id=assinatura,
                resource_group=grupo,
                name=nsg_name,
                rules=_security_rules(),
            )
            return NetworkSegment(
                segment_uuid=segment_uuid,
                scope_id=scope_id,
                provider=provider,
                region_id=region,
                segment_id=f"{base}/virtualNetworks/{nome}",
                subnet_id=f"{base}/virtualNetworks/{nome}/subnets/{nome}-default",
                name=nome,
                resource_group=grupo,
                # O id sai do PROPRIO objeto do NSG (``arm_id()``), e nao de uma segunda
                # composicao da mesma string: duas grafias do mesmo id e o defeito que este
                # modulo ja evita em outros lugares.
                network_security_group_id=nsg.arm_id(),
                network_security_group_uuid=nsg_uuid,
                network_security_group=nsg,
            )

        if provider == SCOPE_PROVIDER_GCP:
            return NetworkSegment(
                segment_uuid=segment_uuid,
                scope_id=scope_id,
                provider=provider,
                region_id=region,
                segment_id=f"projects/{scope_id}/global/networks/{nome}",
                subnet_id=f"projects/{scope_id}/regions/{region}/subnetworks/{nome}-default",
                name=nome,
                resource_group=None,
                network_security_group_id=None,
                network_security_group_uuid=None,
            )

        hexdigest = segment_uuid.replace("-", "")
        return NetworkSegment(
            segment_uuid=segment_uuid,
            scope_id=scope_id,
            provider=provider,
            region_id=region,
            segment_id=f"vpc-{hexdigest[:17]}",
            subnet_id=f"subnet-{hexdigest[:17]}",
            name=nome,
            resource_group=None,
            network_security_group_id=f"sg-{hexdigest[:17]}",
            network_security_group_uuid=nsg_uuid,
        )

    def _interface_id(self, provider: str, segment: NetworkSegment, resource_uuid: str) -> str:
        """O id nativo da interface, na forma que a nuvem publica."""
        curto = resource_uuid.replace("-", "")
        if provider == SCOPE_PROVIDER_AZURE:
            return (
                f"{self._arm_prefix(segment)}"
                f"/providers/Microsoft.Network/networkInterfaces/nic-{curto[:12]}"
            )
        if provider == SCOPE_PROVIDER_GCP:
            return f"projects/{segment.scope_id}/regions/{segment.region_id}/instances/vm-{curto[:12]}"
        return f"eni-{curto[:17]}"

    def _build_network(
        self, scoped: list[_ScopedResource]
    ) -> tuple[list[NetworkSegment], list[NetworkInterface], list[NetworkFlow]]:
        """Inventario de rede e, so depois, o fluxo.

        A ordem e a mesma do documento porque a dependencia e real: sem segmento e
        interface, o ``log_resource_id`` do fluxo seria dado orfao -- e o gate do
        projeto recusa orfaos --, os segmentos de caminho do blob nao teriam
        valor, e nao existiria MAC, que a Azure exige por grupo de fluxo.

        O agrupamento e por (provedor, escopo, REGIAO), e nao por escopo. Uma VPC
        da AWS e regional e uma VNet da Azure vive numa regiao: com um segmento por
        escopo, a VPC do escopo herdava a regiao do PRIMEIRO recurso enquanto as
        ENIs do mesmo escopo ficavam em tres regioes -- e um registro de fluxo (ou
        o ``vpcId`` de uma instancia) nomeava a VPC de uma regiao para uma interface
        de outra. Dois agentes mediram isso de forma independente (48 de 72
        interfaces GCP e boa parte das ENIs AWS fora da regiao do segmento).
        """
        por_escopo: dict[tuple[str, str, str], list[_ScopedResource]] = {}
        for sr in scoped:
            chave = (sr.provider, sr.resource.parent_scope_id, sr.resource.region_id)
            por_escopo.setdefault(chave, []).append(sr)

        segments: list[NetworkSegment] = []
        interfaces: list[NetworkInterface] = []
        flows: list[NetworkFlow] = []

        for (provider, scope_id, region), membros in sorted(por_escopo.items()):
            candidatos = sorted(
                (sr for sr in membros if sr.resource.resource_type in NETWORK_ATTACHABLE_TYPES),
                key=lambda sr: sr.resource.identity.uuid,
            )
            if not candidatos:
                continue  # escopo sem recurso ligado a rede nao gera segmento

            segment_uuid = self.identity.uuid_for(f"network-segment/{provider}/{scope_id}/{region}")
            segment = self._segment(provider, scope_id, region, segment_uuid)
            segments.append(segment)

            do_segmento: list[NetworkInterface] = []
            for sr in candidatos:
                uuid = sr.resource.identity.uuid
                interface = NetworkInterface(
                    interface_uuid=self.identity.uuid_for(f"network-interface/{uuid}"),
                    resource_uuid=uuid,
                    segment_uuid=segment_uuid,
                    interface_id=self._interface_id(provider, segment, uuid),
                    mac_address=_mac_for(uuid),
                    private_ip=_private_ip_for(uuid),
                    region_id=sr.resource.region_id,
                )
                interfaces.append(interface)
                do_segmento.append(interface)

            flows.extend(self._flows_for_segment(segment, do_segmento))

        return segments, interfaces, flows

    def _flows_for_segment(
        self, segment: NetworkSegment, interfaces: list[NetworkInterface]
    ) -> list[NetworkFlow]:
        """Um fluxo por interface por janela, com as marcas que cada nuvem pede.

        Cada fluxo tira a sua aleatoriedade de um stream proprio, indexado por
        ``(interface, janela)``: assim a ordem de iteracao nao influencia o
        resultado e acrescentar um fluxo nao desloca os outros.
        """
        if not interfaces:
            return []

        flows: list[NetworkFlow] = []
        for indice, interface in enumerate(interfaces):
            par = interfaces[(indice + 1) % len(interfaces)] if len(interfaces) > 1 else None
            for inicio, fim in _flow_windows(self.clock.sim_now):
                rng = stream_rng(self.seed, f"flow/{interface.interface_uuid}/{inicio.isoformat()}")
                de_entrada = rng.random() < 0.5
                permitido = rng.random() < 0.85
                protocolo = rng.choice(FLOW_PROTOCOLS)
                destino_servico = rng.choice(FLOW_DEST_PORTS)
                pacotes = rng.randint(1, 5000)

                origem = par if de_entrada else interface
                destino = interface if de_entrada else par
                src_ip = FLOW_ABSENT_ADDRESS if origem is None else origem.private_ip
                dst_ip = FLOW_ABSENT_ADDRESS if destino is None else destino.private_ip
                log_resource_id = (
                    segment.network_security_group_id or segment.segment_id
                    if segment.provider == SCOPE_PROVIDER_AZURE
                    else interface.interface_id
                )

                flows.append(
                    NetworkFlow(
                        flow_id=self.identity.uuid_for(
                            f"flow/{interface.interface_uuid}/{inicio.isoformat()}"
                        ),
                        segment_uuid=segment.segment_uuid,
                        src_interface_uuid=None if origem is None else origem.interface_uuid,
                        dst_interface_uuid=None if destino is None else destino.interface_uuid,
                        window_start=inicio,
                        window_end=fim,
                        src_ip=src_ip,
                        dst_ip=dst_ip,
                        src_port=rng.randint(1024, 65535),
                        dst_port=destino_servico if permitido else rng.choice(FLOW_DEST_PORTS),
                        protocol_number=protocolo,
                        direction=DIRECTION_INGRESS if de_entrada else DIRECTION_EGRESS,
                        decision=DECISION_ALLOWED if permitido else DECISION_DENIED,
                        packets=pacotes,
                        bytes=pacotes * rng.randint(60, 1500),
                        log_resource_id=log_resource_id,
                        account_id=segment.scope_id,
                        # Marcas por nuvem, sem uniformizar: o estado do fluxo e da
                        # Azure (o VNet acrescenta ``D``, que o renderer do NSG
                        # filtra), os contadores reversos sao da Azure, e o
                        # ``reporter`` por ponta e do GCP.
                        flow_state=rng.choice(("B", "C", "E")) if segment.provider == SCOPE_PROVIDER_AZURE else None,
                        encryption=None,
                        reported_by=rng.choice(("SRC", "DEST")) if segment.provider == SCOPE_PROVIDER_GCP else None,
                        packets_reverse=rng.randint(1, 5000) if segment.provider == SCOPE_PROVIDER_AZURE else None,
                        bytes_reverse=(
                            rng.randint(60, 1500) * pacotes if segment.provider == SCOPE_PROVIDER_AZURE else None
                        ),
                    )
                )
        return flows

    # ── instancias: o que cada nuvem documenta sobre a instancia de computo ──

    def _build_instance_profiles(
        self,
        scoped: list[_ScopedResource],
        interfaces: list[NetworkInterface],
        segments: list[NetworkSegment],
    ) -> list[InstanceProfile]:
        """Perfil por instancia, COERENTE com a interface que a rede criou.

        O IP privado vem da mesma interface do mesmo recurso: uma instancia com IP
        diferente do IP da sua propria NIC seria estado incoerente, e o gate
        recusa. O tipo sai do catalogo de SKU; quando ele nao diz, sai ``None``.
        """
        segmento_por_uuid = {segment.segment_uuid: segment for segment in segments}
        interface_por_recurso = {interface.resource_uuid: interface for interface in interfaces}
        perfis: list[InstanceProfile] = []

        for sr in sorted(scoped, key=lambda item: item.resource.identity.uuid):
            if sr.resource.resource_type not in NETWORK_ATTACHABLE_TYPES:
                continue
            interface = interface_por_recurso.get(sr.resource.identity.uuid)
            if interface is None:
                continue  # sem interface nao ha IP nem zona coerentes a afirmar

            uuid = sr.resource.identity.uuid
            segmento = segmento_por_uuid[interface.segment_uuid]
            rng = stream_rng(self.seed, f"instance/{uuid}")
            perfis.append(
                InstanceProfile(
                    resource_uuid=uuid,
                    provider=sr.provider,
                    native_id=self._instance_native_id(
                        sr.provider, segmento, uuid, sr.resource.resource_type
                    ),
                    instance_type=INSTANCE_TYPE_BY_SKU.get(sr.sku_id),
                    zone=_zone_for(sr.provider, sr.resource.region_id, uuid),
                    state=STATE_RUNNING if rng.random() < 0.8 else STATE_STOPPED,
                    private_ip=interface.private_ip,
                    public_ip=_public_ip_for(uuid) if rng.random() < 0.3 else None,
                    image_id=self._image_id(sr.provider, segmento, uuid),
                    launch_time=datetime.combine(
                        self.clock.sim_start
                        + timedelta(days=rng.randrange(max(1, (self.clock.sim_now - self.clock.sim_start).days + 1))),
                        time(hour=rng.randrange(24), minute=rng.randrange(60)),
                        tzinfo=UTC,
                    ),
                    root_volume_size_gb=rng.choice((32, 64, 128, 256)),
                    root_volume_type=DISK_TYPE_BY_SKU.get(sr.resource.resource_type),
                    segment_uuid=segmento.segment_uuid,
                    interface_uuid=interface.interface_uuid,
                )
            )
        return perfis

    def _arm_prefix(self, segment: NetworkSegment) -> str:
        """Prefixo ARM com o GUID da assinatura -- nunca o rotulo do escopo.

        Tres superficies Azure ja montavam o id por conta propria com
        ``azure_subscription_guid``; o modelo de rede montava com ``scope_id``
        (``sub-01``). Eram duas grafias da MESMA assinatura no mesmo estado, e um
        id ARM e afirmacao sobre o provedor. Uma correcao aqui alinha as cinco.
        """
        assinatura = azure_subscription_guid(self.seed, segment.scope_id)
        return f"/subscriptions/{assinatura}/resourceGroups/{segment.resource_group}"

    def _instance_native_id(
        self, provider: str, segment: NetworkSegment, resource_uuid: str, resource_type: str
    ) -> str:
        """O id nativo da instancia, na forma que a nuvem publica.

        Na AWS isto DELEGA para ``aws_resource_id``: derivar o id aqui de outro
        jeito dava DOIS ids para a mesma instancia (``instance_profiles.native_id``
        != ``aws_resource_id``), e os renderers de ARM e GCP leriam um enquanto as
        superficies AWS liam o outro. Identidade se cunha num lugar so.
        """
        curto = resource_uuid.replace("-", "")
        if provider == SCOPE_PROVIDER_AZURE:
            return (
                f"{self._arm_prefix(segment)}"
                f"/providers/Microsoft.Compute/virtualMachines/vm-{curto[:12]}"
            )
        if provider == SCOPE_PROVIDER_GCP:
            # O ``id`` do Compute e uint64; derivamos um inteiro estavel do uuid.
            return str(int(curto[:15], 16))
        return aws_resource_id(resource_type, resource_uuid)

    def _image_id(self, provider: str, segment: NetworkSegment, resource_uuid: str) -> str:
        """Id da imagem, na forma documentada por nuvem."""
        curto = resource_uuid.replace("-", "")
        if provider == SCOPE_PROVIDER_AZURE:
            return (
                f"{self._arm_prefix(segment)}"
                f"/providers/Microsoft.Compute/images/img-{curto[:12]}"
            )
        if provider == SCOPE_PROVIDER_GCP:
            return f"projects/{segment.scope_id}/global/images/img-{curto[:12]}"
        return f"ami-{curto[:17]}"

    def _commitment_rows(self, scopes: list[tuple[str, str, str]]) -> dict[str, Commitment]:
        """One commitment per scope, keyed by scope id, before coverage sizes it.

        ``quantity`` and ``status`` are the two fields only the billing lines can answer
        — how much of the commitment the scope's usage consumes — so they are filled by
        ``_build_commitments_credits_taxes`` once coverage has run. Identity, kind, name
        and unit are known here, which is what lets the coverage step stamp the
        commitment's id on the lines it covers.
        """
        start = self.clock.sim_start
        end = self.clock.sim_now
        rows: dict[str, Commitment] = {}
        for provider, scope_id, _ba in scopes:
            kind = const.COMMITMENT_KIND[provider]
            rows[scope_id] = Commitment(
                identity=self._path(f"{provider}/commitment/{scope_id}", provider),
                kind=kind,
                scope_id=scope_id,
                period_start=start,
                period_end=end,
                committed_amount=_q(Decimal("500.000000")),
                status="Used",
                name=synth_name(f"{const.COMMITMENT_LABEL[kind]} {scope_id}"),
                quantity=Decimal("0.000000"),
                unit=const.COMMITMENT_UNIT[kind],
            )
        return rows

    def _build_commitments_credits_taxes(
        self,
        scopes: list[tuple[str, str, str]],
        commitment_rows: dict[str, Commitment],
        covered_quantity: dict[str, Decimal],
    ) -> tuple[list[Commitment], list[Credit], list[Tax]]:
        """Size each commitment from the usage it covers, and build credits and taxes.

        ``quantity`` is the metered amount the commitment covers over its period, which
        is a projection of the covered lines the builder just emitted — not a second,
        independent number. ``status`` follows the same fact: a commitment the scope's
        usage fully consumed is ``Used``, one that covered nothing is ``Unused``.
        """
        commitments: list[Commitment] = []
        credits_: list[Credit] = []
        taxes: list[Tax] = []
        start = self.clock.sim_start
        end = self.clock.sim_now
        for provider, scope_id, _ba in scopes:
            quantity = _q(covered_quantity.get(scope_id, Decimal("0")))
            commitments.append(
                replace(
                    commitment_rows[scope_id],
                    quantity=quantity,
                    status="Used" if quantity > 0 else "Unused",
                )
            )
            credits_.append(
                Credit(
                    identity=self._path(f"{provider}/credit/{scope_id}", provider),
                    scope_id=scope_id,
                    name=synth_name(f"Promo Credit {scope_id}"),
                    amount=_q(Decimal("100.000000")),
                    applicable_cost=_q(Decimal("1000.000000")),
                    period_start=start,
                    period_end=end,
                )
            )
            taxes.append(Tax(scope_id, start.replace(day=1), _q(Decimal("25.000000")), self.currency))
        return commitments, credits_, taxes

    # ── invoices ───────────────────────────────────────────────────────────────

    def _stamp_invoice_ids(self, billing: list[BillingLine]) -> list[BillingLine]:
        """Populate ``invoice_id`` on billing lines whose period is Issued (closed)."""
        now = self.clock.sim_now
        updated: list[BillingLine] = []
        for line in billing:
            issued = (line.billing_period_start.year, line.billing_period_start.month) < (now.year, now.month)
            invoice_id = (
                self.identity.uuid_for(f"invoice/{line.billing_account_id}/{line.billing_period_start.isoformat()}")
                if issued
                else None
            )
            updated.append(replace(line, invoice_id=invoice_id))
        return updated

    def _assemble_invoices(self, billing: list[BillingLine]) -> list[Invoice]:
        groups: dict[tuple[str, str, date, date], list[BillingLine]] = {}
        for line in billing:
            if line.invoice_id is None:
                continue
            key = (line.invoice_id, line.billing_account_id, line.billing_period_start, line.billing_period_end)
            groups.setdefault(key, []).append(line)
        invoices: list[Invoice] = []
        for (invoice_id, ba, bp_start, bp_end), lines in sorted(groups.items()):
            inv_lines = tuple(
                InvoiceLine(invoice_id=invoice_id, billing_line_id=line.line_id, amount=line.billed_cost)
                for line in sorted(lines, key=lambda line: line.line_id)
            )
            total = _q(sum((line.amount for line in inv_lines), Decimal("0")))
            invoices.append(
                Invoice(
                    invoice_id=invoice_id,
                    billing_account_id=ba,
                    billing_period_start=bp_start,
                    billing_period_end=bp_end,
                    invoice_issue_status="Issued",
                    total=total,
                    currency=self.currency,
                    lines=inv_lines,
                    is_c07_divergence=False,
                )
            )
        return invoices

    # ── top-level build ──────────────────────────────────────────────────────

    def build(self) -> CanonicalEstate:
        """Build the base (pre-scenario) canonical estate."""
        accounts, mgmt_groups, orgs, aws_orgs, scopes = self._build_hierarchy()
        commitment_rows = self._commitment_rows(scopes)
        scoped = self._build_resources(scopes)
        scoped = self._attach_capacity_reservations(scoped)
        list_prices, contracted = self._build_prices(scoped)
        consumption, billing, covered_quantity = self._build_consumption_and_billing(scoped, commitment_rows)

        billing = duplicate_billing_lines(billing, stream_rng(self.seed, "duplicate-lines"))
        billing.append(
            make_null_resource_line(
                identity=self.identity,
                billing_account_id=accounts[0].billing_account_id,
                sub_account_id=scopes[0][1],
                day=self.clock.sim_start,
                currency=self.currency,
                provider_name=const.PROVIDER_AZURE,
            )
        )

        billing = self._stamp_invoice_ids(billing)
        inventory = self._build_inventory(scoped)
        findings = self._build_findings(scoped)
        recommendations = self._build_recommendations(scoped)
        metrics = self._build_metrics(scoped)
        iac = self._build_iac(scoped, inventory)
        network_segments, network_interfaces, network_flows = self._build_network(scoped)
        instance_profiles = self._build_instance_profiles(scoped, network_interfaces, network_segments)
        aws_security_groups = _aws_security_groups(
            [item.resource for item in scoped], network_segments
        )
        aws_bucket_postures = _aws_bucket_postures(self.seed, [item.resource for item in scoped])
        aws_identity_postures = _aws_identity_postures(self.seed, aws_orgs, self.clock.sim_now)
        # O Incremento 4.3 fecha as tres ultimas regras do Config: as duas de CONTA (trilha
        # CloudTrail e inscricao do Security Hub) e a de VPC (flow log). A regiao de cada conta e
        # a de um escopo seu qualquer -- e a mesma regiao que entra no ARN da trilha e do Hub,
        # e nao um literal.
        regiao_por_conta = {
            resource.parent_scope_id: resource.region_id
            for resource in (item.resource for item in scoped)
            if resource.identity.provider == const.PROVIDER_KEY_AWS
        }
        aws_audit_postures = _aws_audit_postures(aws_orgs, regiao_por_conta)
        aws_vpc_flow_logs = _aws_vpc_flow_logs(self.seed, [item.resource for item in scoped])
        gcp_firewall_rules = _gcp_firewall_rules(network_segments)
        azure_defender_assessments = _azure_defender_assessments(
            network_segments, self.seed, self.identity, self.clock.sim_start
        )
        commitments, credits_, taxes = self._build_commitments_credits_taxes(
            scopes, commitment_rows, covered_quantity
        )
        invoices = self._assemble_invoices(billing)

        conversion = const.BRL_CONVERSION_RATE if self.currency == "BRL" else None
        return CanonicalEstate(
            seed=self.seed,
            profile=self.profile,
            currency=self.currency,
            currency_conversion_rate=conversion,
            sim_start=self.clock.sim_start,
            sim_now=self.clock.sim_now,
            billing_accounts=accounts,
            azure_mgmt_groups=mgmt_groups,
            gcp_orgs=orgs,
            aws_orgs=aws_orgs,
            resources=tuple(sr.resource for sr in scoped),
            consumption=tuple(consumption),
            billing_lines=tuple(billing),
            list_prices=tuple(list_prices),
            contracted_prices=tuple(contracted),
            commitments=tuple(commitments),
            credits=tuple(credits_),
            taxes=tuple(taxes),
            invoices=tuple(invoices),
            inventory=tuple(inventory),
            findings=tuple(findings),
            recommendations=tuple(recommendations),
            metrics=tuple(metrics),
            iac_snapshots=tuple(iac),
            scenario_ids=(),
            network_segments=tuple(network_segments),
            network_interfaces=tuple(network_interfaces),
            network_flows=tuple(network_flows),
            instance_profiles=tuple(instance_profiles),
            aws_security_groups=aws_security_groups,
            aws_bucket_postures=aws_bucket_postures,
            aws_identity_postures=aws_identity_postures,
            aws_audit_postures=aws_audit_postures,
            aws_vpc_flow_logs=aws_vpc_flow_logs,
            gcp_firewall_rules=gcp_firewall_rules,
            azure_defender_assessments=azure_defender_assessments,
        )


def build_estate(
    seed: int,
    profile: str,
    currency: str,
    sim_start: date | None = None,
    window_days: int | None = None,
) -> CanonicalEstate:
    """Convenience: build a base estate for ``(seed, profile, currency)``.

    ``sim_start`` and ``window_days`` both default to what every pre-FR-22 caller and
    the whole existing test suite is built on: :data:`CANONICAL_EPOCH` and the
    profile's own window. Overriding them is what makes generation day-addressable —
    the daily cadence asks for a month-to-date window ending on the day it emits.

    The two are independent on purpose. ``_resources_per_scope`` still sizes the
    estate from the *profile's* window, so a day-addressable build keeps the resource
    set the profile implies instead of collapsing to a single day's worth.
    """
    return EstateBuilder(
        seed=seed,
        profile=profile,
        currency=currency,
        sim_start=sim_start,
        window_days=window_days,
    ).build()
