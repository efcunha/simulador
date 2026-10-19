"""The 28-scenario catalog C01..C18 (Azure/GCP) + A01..A10 (AWS) (design sec.
10.3; FR-F).

Each ``ScenarioSpec`` cleanly separates **emitted inputs** (the cloud-native
INPUT conditions the generator emits) from **expected engine output** (what
FinOps MUST compute — an ASSERTION ONLY, never emitted). This is the P1
separation: ``scenarios/emit.py`` applies only ``emitted_inputs``;
``expected_engine_output`` lives in the gabarito as an assertion for FinOps
engines (FR-F4).

The windows are expressed relative to the simulation window so they stay valid
for any profile; ``scenarios/emit.py`` resolves them against the estate's
``sim_start``/``sim_now``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class ScenarioTarget:
    """The resource/service/scope a scenario touches."""

    provider: str | None  # "azure" | "gcp" | "aws" | None
    service: str | None  # service name hint
    scope_hint: str | None  # subscription/project index hint, e.g. "azure:0"


@dataclass(slots=True, frozen=True)
class ExpectedEngineOutput:
    """What FinOps MUST compute. ASSERTION ONLY — never an emitted artifact."""

    engine: str | None  # rightsizing|drift|compliance|anomaly|tag_score|forecast|budget|reconciliation
    assertion: str


@dataclass(slots=True, frozen=True)
class Evidence:
    """The FinOps screen/report/engine that evidences the scenario (FR-F2)."""

    screen: str | None
    report: str | None
    engine: str | None


@dataclass(slots=True, frozen=True)
class ScenarioWindow:
    """A window expressed as day offsets from sim_start, resolved at emit time.

    ``start_offset`` / ``end_offset`` are day counts from ``sim_start``. A negative
    ``end_offset`` of -1 means "ends at sim_now" (used by C18).
    """

    start_offset: int
    end_offset: int  # -1 => sim_now (the last simulated day)


@dataclass(slots=True, frozen=True)
class ScenarioSpec:
    """A single stable scenario (C01..C18, A01..A10)."""

    id: str
    title: str
    window: ScenarioWindow
    target: ScenarioTarget
    emitted_inputs: tuple[str, ...]  # the INPUT conditions the generator emits
    expected_effect: str  # human description of expected outcome
    expected_engine_output: ExpectedEngineOutput  # ASSERTION (never emitted)
    evidence: Evidence


# The 28 scenarios. C01..C18 are exactly per design sec. 10.3; A01..A10 are the
# Phase 6 AWS set. IDs are stable and disjoint across the two series.
CATALOG: tuple[ScenarioSpec, ...] = (
    ScenarioSpec(
        id="C01",
        title="Azure OpenAI retry loop",
        window=ScenarioWindow(5, 8),
        target=ScenarioTarget("azure", "Azure OpenAI", "azure:0"),
        emitted_inputs=("5-7x cost spike on OpenAI SKU for 4 days",),
        expected_effect="anomaly detected on OpenAI spend",
        expected_engine_output=ExpectedEngineOutput("anomaly", "spike anomaly flagged for window"),
        evidence=Evidence("Anomalies", None, "anomaly"),
    ),
    ScenarioSpec(
        id="C02",
        title="BigQuery query without partition",
        window=ScenarioWindow(10, 12),
        target=ScenarioTarget("gcp", "BigQuery", "gcp:0"),
        emitted_inputs=("~9x BigQuery scan-cost spike for 2 days (no partition)",),
        expected_effect="anomaly detected on BigQuery scan cost",
        expected_engine_output=ExpectedEngineOutput("anomaly", "spike anomaly flagged for window"),
        evidence=Evidence("Anomalies", None, "anomaly"),
    ),
    ScenarioSpec(
        id="C03",
        title="GCP anomalous egress",
        window=ScenarioWindow(14, 17),
        target=ScenarioTarget("gcp", "Compute Engine", "gcp:1"),
        emitted_inputs=("~3.4x egress cost spike for 3 days",),
        expected_effect="anomaly detected on egress",
        expected_engine_output=ExpectedEngineOutput("anomaly", "spike anomaly flagged for window"),
        evidence=Evidence("Anomalies", None, "anomaly"),
    ),
    ScenarioSpec(
        id="C04",
        title="Forgotten debug logging / Log Analytics",
        window=ScenarioWindow(8, 20),
        target=ScenarioTarget("azure", "Log Analytics", "azure:1"),
        emitted_inputs=("+120% Log Analytics ingest for 12 days",),
        expected_effect="cost-trend / anomaly alert on logging spend",
        expected_engine_output=ExpectedEngineOutput("anomaly", "sustained cost-trend alert for window"),
        evidence=Evidence("Anomalies", None, "anomaly"),
    ),
    ScenarioSpec(
        id="C05",
        title="Underused Azure reservation",
        window=ScenarioWindow(0, 44),
        target=ScenarioTarget("azure", "Virtual Machines", "azure:0"),
        emitted_inputs=("daily Unused reservation lines (CommitmentDiscountStatus=Unused)",),
        expected_effect="underused-reservation opportunity computed",
        expected_engine_output=ExpectedEngineOutput("rightsizing", "underused reservation opportunity"),
        evidence=Evidence("FinOps", None, "rightsizing"),
    ),
    ScenarioSpec(
        id="C06",
        title="Credits running out",
        window=ScenarioWindow(20, 25),
        target=ScenarioTarget("gcp", None, "gcp:0"),
        emitted_inputs=("credit period_end reached -> cost jump when credit ends",),
        expected_effect="budget/forecast reaction to credit expiry",
        expected_engine_output=ExpectedEngineOutput("forecast", "forecast reacts to credit expiry"),
        evidence=Evidence("FinOps", None, "forecast"),
    ),
    ScenarioSpec(
        id="C07",
        title="Invoice diverges from cost",
        window=ScenarioWindow(0, 30),
        target=ScenarioTarget(None, None, None),
        emitted_inputs=("Azure invoice total +3.2%", "GCP invoice total -1.5%"),
        expected_effect="parity variance surfaced (the only allowed invoice/cost divergence)",
        expected_engine_output=ExpectedEngineOutput("reconciliation", "parity variance surfaced"),
        evidence=Evidence("Costs", None, "reconciliation"),
    ),
    ScenarioSpec(
        id="C08",
        title="Budgets in varied states",
        window=ScenarioWindow(0, 44),
        target=ScenarioTarget(None, None, None),
        emitted_inputs=("budget inputs at 70/85/95% of threshold",),
        expected_effect="budget alerts at tiers",
        expected_engine_output=ExpectedEngineOutput("budget", "budget alerts at 70/85/95 tiers"),
        evidence=Evidence("FinOps", None, "budget"),
    ),
    ScenarioSpec(
        id="C09",
        title="Open findings: NSG, bucket, MFA, SA key",
        window=ScenarioWindow(2, 44),
        target=ScenarioTarget(None, None, None),
        emitted_inputs=(
            "open NSG/firewall finding",
            "public bucket finding",
            "admin without MFA finding",
            "old SA key finding",
        ),
        expected_effect="critical/high findings open across providers",
        expected_engine_output=ExpectedEngineOutput("compliance", "critical/high findings surfaced"),
        evidence=Evidence("Security", None, "compliance"),
    ),
    ScenarioSpec(
        id="C10",
        title="Scan failing by permission",
        window=ScenarioWindow(0, 44),
        target=ScenarioTarget("gcp", None, "gcp:2"),
        emitted_inputs=("native scan failing by permission (baseline stale)",),
        expected_effect="stale-baseline / scan-health flag",
        expected_engine_output=ExpectedEngineOutput("compliance", "stale-baseline / scan-health flag"),
        evidence=Evidence("Security", None, "compliance"),
    ),
    ScenarioSpec(
        id="C11",
        title="Drift: firewall + removed + unmanaged",
        window=ScenarioWindow(0, 44),
        target=ScenarioTarget("azure", None, "azure:2"),
        emitted_inputs=(
            "firewall changed outside IaC (inventory vs IaC snapshot differ)",
            "resource removed from IaC but present in inventory",
            "unmanaged resource present (not in IaC snapshot)",
        ),
        expected_effect="drift + finding + compliance failure simultaneously",
        expected_engine_output=ExpectedEngineOutput("drift", "drift + finding + compliance failure simultaneously"),
        evidence=Evidence("Drift", None, "drift"),
    ),
    ScenarioSpec(
        id="C12",
        title="Idle/orphan resources",
        window=ScenarioWindow(0, 44),
        target=ScenarioTarget(None, None, None),
        emitted_inputs=("orphan disks/IPs", "idle VMs (low metrics)", "idle DB (low metrics)"),
        expected_effect="rightsizing/idle opportunities computed",
        expected_engine_output=ExpectedEngineOutput("rightsizing", "idle/orphan opportunities"),
        evidence=Evidence("Opportunities", None, "rightsizing"),
    ),
    ScenarioSpec(
        id="C13",
        title="Tag governance evolving",
        window=ScenarioWindow(0, 44),
        target=ScenarioTarget(None, None, None),
        emitted_inputs=("weekly tag coverage evolving (raw tags over time)",),
        expected_effect="tag score series computed",
        expected_engine_output=ExpectedEngineOutput("tag_score", "tag score series"),
        evidence=Evidence("Tag Governance", None, "tag_score"),
    ),
    ScenarioSpec(
        id="C14",
        title="Estimate -> final invoice",
        window=ScenarioWindow(0, 30),
        target=ScenarioTarget(None, None, None),
        emitted_inputs=(
            "Estimated invoice snapshot at export_time T0",
            "Issued invoice snapshot at export_time T1 with post-close Adjustment deltas",
        ),
        expected_effect="estimate->final transition computed from two snapshots",
        expected_engine_output=ExpectedEngineOutput("reconciliation", "estimate->final transition"),
        evidence=Evidence("FinOps", None, "reconciliation"),
    ),
    ScenarioSpec(
        id="C15",
        title="Kubernetes cost with dominant namespace",
        window=ScenarioWindow(0, 44),
        target=ScenarioTarget("azure", "Azure Kubernetes Service", "azure:0"),
        emitted_inputs=("AKS/GKE cost with dominant namespace, coherent with cluster FOCUS cost",),
        expected_effect="K8s cost breakdown computed",
        expected_engine_output=ExpectedEngineOutput("k8s_finops", "namespace cost breakdown"),
        evidence=Evidence("K8s FinOps", None, "k8s_finops"),
    ),
    ScenarioSpec(
        id="C16",
        title="Savings Plan/CUD purchased mid-period",
        window=ScenarioWindow(15, 44),
        target=ScenarioTarget("azure", "Virtual Machines", "azure:1"),
        emitted_inputs=("PricingCategory Standard->Committed mid-period",),
        expected_effect="commitment coverage change computed",
        expected_engine_output=ExpectedEngineOutput("rightsizing", "commitment coverage change"),
        evidence=Evidence("FinOps", None, "rightsizing"),
    ),
    ScenarioSpec(
        id="C17",
        title="Retroactive adjustment/credit",
        window=ScenarioWindow(5, 25),
        target=ScenarioTarget("gcp", None, "gcp:1"),
        emitted_inputs=("retroactive Adjustment delta line (later export_time; original cost intact)",),
        expected_effect="restatement handled, parity stable",
        expected_engine_output=ExpectedEngineOutput("reconciliation", "restatement handled, parity stable"),
        evidence=Evidence("Costs", None, "reconciliation"),
    ),
    ScenarioSpec(
        id="C18",
        title="Runtime injection (fresh at SIM_NOW)",
        window=ScenarioWindow(-1, -1),  # start and end at sim_now
        target=ScenarioTarget("azure", "Virtual Machines", "azure:2"),
        emitted_inputs=(
            "new resource created on the last simulated day",
            "5-7x cost spike on that resource's SKU on usage_date == SIM_NOW",
        ),
        expected_effect="detection on the latest window",
        expected_engine_output=ExpectedEngineOutput("anomaly", "spike anomaly flagged on the latest window"),
        evidence=Evidence("Dashboard", None, "anomaly"),
    ),
    # ── AWS scenarios A01..A10 (Phase 6) ─────────────────────────────────────
    #
    # Where each one's input condition is emitted — the same layering the C-series
    # already uses, so no entry claims a condition nothing produces:
    #   * estate layer (emit.py):  A01, A02, A10
    #   * base estate / renderer:  A09 (EKS cluster + cross-AZ SKU are catalog
    #     services; K8s coherence is asserted by validate.quality)
    #   * renderer layout:         A03, A04, A05, A06 (S3 key/execution shape)
    #   * control-plane shim:      A07 (CUR x CE divergence), A08 (AccessDenied)
    ScenarioSpec(
        id="A01",
        title="Partially-used AWS Savings Plan / RI",
        window=ScenarioWindow(0, 44),
        target=ScenarioTarget("aws", "Amazon Elastic Compute Cloud", "aws:0"),
        emitted_inputs=(
            "SavingsPlanCoveredUsage lines covering only part of the eligible usage",
            "daily RIFee lines for the uncovered share",
        ),
        expected_effect="underused AWS commitment opportunity computed",
        expected_engine_output=ExpectedEngineOutput("rightsizing", "underused SP/RI opportunity"),
        evidence=Evidence("FinOps", None, "rightsizing"),
    ),
    ScenarioSpec(
        id="A02",
        title="AWS EDP/private discount, effective != billed",
        window=ScenarioWindow(10, 30),
        target=ScenarioTarget("aws", None, "aws:1"),
        emitted_inputs=("EDP/private discount where effective cost < billed cost on AWS Usage lines",),
        expected_effect="effective-vs-billed discount surfaced without changing billed cost",
        expected_engine_output=ExpectedEngineOutput("reconciliation", "effective != billed discount surfaced"),
        evidence=Evidence("Costs", None, "reconciliation"),
    ),
    ScenarioSpec(
        id="A03",
        title="New export version with added columns",
        window=ScenarioWindow(0, 44),
        target=ScenarioTarget(None, None, None),
        emitted_inputs=("a later export version carrying extra FOCUS columns",),
        expected_effect="schema change detected on the next ingestion run",
        expected_engine_output=ExpectedEngineOutput("reconciliation", "schema fingerprint change detected"),
        evidence=Evidence("Costs", None, "reconciliation"),
    ),
    ScenarioSpec(
        id="A04",
        title="Create-new delivery, several executions in one period",
        window=ScenarioWindow(0, 44),
        target=ScenarioTarget(None, None, None),
        emitted_inputs=("multiple execution directories within one billing period",),
        expected_effect="only the newest execution per period is ingested",
        expected_engine_output=ExpectedEngineOutput("reconciliation", "execution pinning: newest only, never summed"),
        evidence=Evidence("Costs", None, "reconciliation"),
    ),
    ScenarioSpec(
        id="A05",
        title="Export shrinks, excess chunks overwritten empty",
        window=ScenarioWindow(0, 44),
        target=ScenarioTarget(None, None, None),
        emitted_inputs=("a later execution with fewer chunks, excess overwritten with empty data",),
        expected_effect="shrunken export replaces the period without orphan rows",
        expected_engine_output=ExpectedEngineOutput("reconciliation", "period replaced; empty chunk tolerated"),
        evidence=Evidence("Costs", None, "reconciliation"),
    ),
    ScenarioSpec(
        id="A06",
        title="Prior-month restatement after close",
        window=ScenarioWindow(5, 25),
        target=ScenarioTarget("aws", None, "aws:0"),
        emitted_inputs=("restated AWS Usage line with a later export_time; original row intact",),
        expected_effect="restatement handled, period REPLACEd",
        expected_engine_output=ExpectedEngineOutput("reconciliation", "restatement handled, parity stable"),
        evidence=Evidence("Costs", None, "reconciliation"),
    ),
    ScenarioSpec(
        id="A07",
        title="CUR and Cost Explorer disagree",
        window=ScenarioWindow(0, 44),
        target=ScenarioTarget(None, None, None),
        emitted_inputs=("CUR total and Cost Explorer total disagree beyond the parity tolerance",),
        expected_effect="shadow parity variance surfaced as a divergence",
        expected_engine_output=ExpectedEngineOutput("reconciliation", "parity variance outside tolerance surfaced"),
        evidence=Evidence("Costs", None, "reconciliation"),
    ),
    ScenarioSpec(
        id="A08",
        title="Member account role lacks permission",
        window=ScenarioWindow(0, 44),
        target=ScenarioTarget("aws", None, "aws:2"),
        emitted_inputs=("member account whose role returns AccessDenied from STS and Cost Explorer",),
        expected_effect="account shows a failed connection with an actionable reason",
        expected_engine_output=ExpectedEngineOutput("compliance", "connection failure surfaced with reason"),
        evidence=Evidence("Cloud Accounts", None, "compliance"),
    ),
    ScenarioSpec(
        id="A09",
        title="EKS cost with dominant namespace and cross-AZ transfer",
        window=ScenarioWindow(0, 44),
        target=ScenarioTarget("aws", "Amazon Elastic Kubernetes Service", "aws:0"),
        emitted_inputs=(
            "EKS cluster cost with dominant namespace, coherent with cluster FOCUS cost",
            "cross-AZ data transfer cost lines",
        ),
        expected_effect="K8s cost breakdown computed for EKS",
        expected_engine_output=ExpectedEngineOutput("k8s_finops", "namespace cost breakdown for EKS"),
        evidence=Evidence("K8s FinOps", None, "k8s_finops"),
    ),
    ScenarioSpec(
        id="A10",
        title="AWS Marketplace and support line items",
        window=ScenarioWindow(0, 44),
        target=ScenarioTarget("aws", "AWS Marketplace", "aws:0"),
        emitted_inputs=(
            "AWS Marketplace charge line with no backing resource (Purchase)",
            "AWS Support fee line as a Tax charge",
        ),
        expected_effect="billing-only AWS line items present in cost without a resource",
        expected_engine_output=ExpectedEngineOutput("reconciliation", "billing-only lines reconciled, no orphan resource"),
        evidence=Evidence("Costs", None, "reconciliation"),
    ),
)

# Scenarios whose expected effect is a FinOps-COMPUTED output (P1 / FR-F4):
# the generator emits ONLY their input conditions. Used by the AC-15 test as the
# cross-check that no computed output leaks into an artifact.
COMPUTED_OUTPUT_SCENARIOS = frozenset(
    {"C01", "C02", "C03", "C04", "C05", "C06", "C08", "C11", "C12", "C13", "C16", "A01"}
)


def catalog_ids() -> tuple[str, ...]:
    """Return the stable ordered scenario ids C01..C18 then A01..A10."""
    return tuple(spec.id for spec in CATALOG)
