"""Apply the 18 scenarios' INPUT conditions to a base estate (P1).

CRITICAL (P1 / FR-F4): this module applies ONLY ``emitted_inputs`` — cloud-native
INPUT conditions. It NEVER emits a FinOps-computed output (opportunity, drift
result, compliance result, tag score, anomaly, forecast). Those live only as
assertions in the gabarito. The AC-15 test scans artifacts to prove no computed
output leaks.

Each scenario transform is deterministic and returns a new ``CanonicalEstate``.
Transforms thread the SAME resource identity the base builder minted (P2); new
rows (spikes, restatements, k8s shares, C18 fresh resource) reuse existing uuids
or mint one new UUIDv5 via the identity factory.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_HALF_EVEN, Decimal

from tools.synthetic_clouds.clock import export_time_for, restatement_export_time_for
from tools.synthetic_clouds.generate import constants as const
from tools.synthetic_clouds.generate.estate_builder import (
    _finding_text,
    _finding_types,
    finding_provenance,
)
from tools.synthetic_clouds.model.billing import BillingLine
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.identity import IdentityFactory
from tools.synthetic_clouds.model.invoice import Invoice, InvoiceLine
from tools.synthetic_clouds.model.native import NativeFinding
from tools.synthetic_clouds.model.resource import Resource
from tools.synthetic_clouds.render.markers import (
    SOURCE_SYNTHETIC,
    source_fingerprint,
    synthetic_evidence,
)
from tools.synthetic_clouds.scenarios.catalog import CATALOG

_SIX = Decimal("0.000001")
_MIDDAY = time(12, 0, 0)
_AZURE_C07_FACTOR = Decimal("1.032")
_GCP_C07_FACTOR = Decimal("0.985")


def _q(value: Decimal) -> Decimal:
    return value.quantize(_SIX, ROUND_HALF_EVEN)


def _month_end(day: date) -> date:
    if day.month == 12:
        return date(day.year + 1, 1, 1)
    return date(day.year, day.month + 1, 1)


def apply_all(estate: CanonicalEstate) -> CanonicalEstate:
    """Apply all 28 scenario input conditions and return the final estate."""
    factory = IdentityFactory(seed=estate.seed)
    billing = list(estate.billing_lines)
    findings = list(estate.findings)

    billing = _apply_cost_spikes(estate, billing)
    billing = _apply_c05_unused_reservation(estate, billing, factory)
    billing = _apply_c16_committed_pricing(estate, billing)
    billing = _apply_c17_restatement(estate, billing, factory)
    billing = _apply_c15_k8s_shares(billing, factory)
    billing = _apply_a02_effective_discount(estate, billing)
    billing = _apply_a01_unused_aws_commitment(estate, billing, factory)
    billing = _apply_a10_marketplace_support(estate, billing, factory)
    billing = _apply_a06_restatement(estate, billing, factory)
    billing, c18_resource = _apply_c18_fresh_resource(estate, billing, factory)
    findings = _apply_c09_findings(estate, findings, factory)

    resources = list(estate.resources)
    if c18_resource is not None:
        resources.append(c18_resource)

    invoices = _apply_c07_invoice_divergence(estate, billing)

    return replace(
        estate,
        resources=tuple(resources),
        billing_lines=tuple(billing),
        findings=tuple(findings),
        invoices=tuple(invoices),
        scenario_ids=tuple(spec.id for spec in CATALOG),
    )


def _window_days(estate: CanonicalEstate, start_offset: int, end_offset: int) -> tuple[date, date]:
    """Resolve a scenario window (offsets) to concrete (start, end) dates."""
    start = estate.sim_now if start_offset == -1 else estate.sim_start + timedelta(days=start_offset)
    end = estate.sim_now if end_offset == -1 else estate.sim_start + timedelta(days=end_offset)
    return start, end


def _apply_cost_spikes(estate: CanonicalEstate, billing: list[BillingLine]) -> list[BillingLine]:
    """C01-C04: multiply billed/effective cost on matching service lines in-window.

    Mutating an existing Usage line's cost is still an INPUT condition (the cloud
    emits a higher cost); no computed anomaly record is produced (P1).
    """
    spike_specs = {
        "C01": ("Azure OpenAI", Decimal("6.0")),
        "C02": ("BigQuery", Decimal("9.0")),
        "C03": ("Compute Engine", Decimal("3.4")),
        "C04": ("Log Analytics", Decimal("2.2")),
    }
    windows: list[tuple[date, date, str, Decimal]] = []
    for spec in CATALOG:
        if spec.id in spike_specs:
            service, factor = spike_specs[spec.id]
            start, end = _window_days(estate, spec.window.start_offset, spec.window.end_offset)
            windows.append((start, end, service, factor))

    result: list[BillingLine] = []
    for line in billing:
        new_line = line
        charge_day = line.charge_period_start.date()
        for start, end, service, factor in windows:
            if line.service_name == service and start <= charge_day <= end:
                new_line = replace(
                    new_line,
                    billed_cost=_q(new_line.billed_cost * factor),
                    effective_cost=_q(new_line.effective_cost * factor),
                )
        result.append(new_line)
    return result


def _apply_c05_unused_reservation(
    estate: CanonicalEstate, billing: list[BillingLine], factory: IdentityFactory
) -> list[BillingLine]:
    """C05: append daily Purchase lines with CommitmentDiscountStatus=Unused.

    C05 lines are commitment-level Purchase lines (no backing resource); like FR-D5
    they are billing-only. The no-orphan gate exempts None ``resource_uuid``.
    """
    spec = next(s for s in CATALOG if s.id == "C05")
    start, end = _window_days(estate, spec.window.start_offset, spec.window.end_offset)
    azure_ba = next(b for b in estate.billing_accounts if b.provider == "azure")
    sub_id = estate.azure_mgmt_groups[0].subscriptions[0].subscription_id
    extra: list[BillingLine] = []
    day = start
    while day <= end and day <= estate.sim_now:
        line_id = factory.uuid_for(f"c05/unused/{day.isoformat()}")
        charge_start = datetime.combine(day, _MIDDAY, tzinfo=UTC)
        amount = Decimal("8.000000")
        extra.append(
            BillingLine(
                line_id=line_id,
                resource_uuid=None,
                billing_account_id=azure_ba.billing_account_id,
                sub_account_id=sub_id,
                invoice_id=None,
                service_name="Reservations",
                service_category="Compute",
                charge_category="Purchase",
                charge_period_start=charge_start,
                charge_period_end=charge_start + timedelta(days=1),
                billing_period_start=day.replace(day=1),
                billing_period_end=_month_end(day),
                export_time=export_time_for(day),
                is_restatement=False,
                restates_date=None,
                billed_cost=amount,
                effective_cost=amount,
                list_cost=amount,
                contracted_cost=amount,
                pricing_quantity=Decimal("1.000000"),
                pricing_unit="Reservation",
                pricing_category="Committed",
                region_id="eastus",
                region_name="East US",
                tags=(),
                commitment_discount_id=f"commit-{sub_id}",
                commitment_discount_status="Unused",
                currency=estate.currency,
                service_provider_name=const.PROVIDER_AZURE,
                is_duplicate=False,
                source_fingerprint=source_fingerprint(line_id),
            )
        )
        day += timedelta(days=1)
    return billing + extra


def _apply_c16_committed_pricing(estate: CanonicalEstate, billing: list[BillingLine]) -> list[BillingLine]:
    """C16: flip PricingCategory Standard->Committed on target VM lines after mid-period."""
    spec = next(s for s in CATALOG if s.id == "C16")
    start, _end = _window_days(estate, spec.window.start_offset, spec.window.end_offset)
    sub_id = estate.azure_mgmt_groups[0].subscriptions[1].subscription_id
    result: list[BillingLine] = []
    for line in billing:
        if (
            line.service_name == "Virtual Machines"
            and line.sub_account_id == sub_id
            and line.charge_period_start.date() >= start
        ):
            result.append(replace(line, pricing_category="Committed", commitment_discount_status="Used"))
        else:
            result.append(line)
    return result


def _apply_c17_restatement(
    estate: CanonicalEstate, billing: list[BillingLine], factory: IdentityFactory
) -> list[BillingLine]:
    """C17: append an Adjustment delta line for an earlier usage_date (original intact).

    The restatement is a signed ``Adjustment`` delta with a LATER export_time; the
    original Usage line is never mutated (FR-B3; design sec. 5.3). The delta lands
    in a different charge_category aggregation group than the original Usage line.
    """
    spec = next(s for s in CATALOG if s.id == "C17")
    start, _end = _window_days(estate, spec.window.start_offset, spec.window.end_offset)
    gcp_lines = [
        line
        for line in billing
        if line.service_provider_name == const.PROVIDER_GCP
        and line.charge_category == "Usage"
        and line.charge_period_start.date() == start
        and line.resource_uuid is not None
    ]
    if not gcp_lines:
        return billing
    original = sorted(gcp_lines, key=lambda line: line.line_id)[0]
    delta = _q(original.billed_cost * Decimal("0.10"))  # +10% correction
    restated_on = min(estate.sim_now, original.charge_period_start.date() + timedelta(days=7))
    line_id = factory.uuid_for(f"c17/adjustment/{original.line_id}")
    charge_start = datetime.combine(original.charge_period_start.date(), _MIDDAY, tzinfo=UTC)
    adj = replace(
        original,
        line_id=line_id,
        charge_category="Adjustment",
        is_restatement=True,
        restates_date=original.charge_period_start.date(),
        export_time=restatement_export_time_for(original.charge_period_start.date(), restated_on),
        charge_period_start=charge_start,
        charge_period_end=charge_start + timedelta(days=1),
        billed_cost=delta,
        effective_cost=delta,
        list_cost=delta,
        contracted_cost=delta,
        is_duplicate=False,
        source_fingerprint=source_fingerprint(line_id),
    )
    return billing + [adj]


def _apply_c15_k8s_shares(billing: list[BillingLine], factory: IdentityFactory) -> list[BillingLine]:
    """C15: split each AKS/GKE cluster line into per-namespace shares that sum to it.

    The dominant namespace holds a fixed majority share; the rest split the
    remainder. The sum of namespace shares equals the cluster's FOCUS cost exactly
    (6-dp Decimal) — the OA-7 coherence invariant the gate asserts. The original
    cluster Usage line is REPLACED by the namespace-tagged shares (same total).
    """
    cluster_services = ("Azure Kubernetes Service", "Kubernetes Engine")
    result: list[BillingLine] = []
    for line in billing:
        # Only split the original cluster Usage line. Benign FR-D4 duplicates
        # (is_duplicate) are left untouched — splitting them too would double the
        # partition and break the per-cluster-line coherence invariant.
        if line.service_name not in cluster_services or line.charge_category != "Usage" or line.is_duplicate:
            result.append(line)
            continue
        result.extend(_split_k8s_line(line, factory))
    return result


def _split_k8s_line(line: BillingLine, factory: IdentityFactory) -> list[BillingLine]:
    namespaces = const.K8S_NAMESPACES
    total = line.billed_cost
    dominant_amount = _q(total * const.K8S_DOMINANT_SHARE)
    others = namespaces[1:]
    per_other = _q((total - dominant_amount) / Decimal(len(others))) if others else Decimal("0")
    shares: list[tuple[str, Decimal]] = [(namespaces[0], dominant_amount)]
    allocated = dominant_amount
    for i, ns in enumerate(others):
        if i == len(others) - 1:
            amt = total - allocated  # last namespace absorbs rounding so sum == total exactly
        else:
            amt = per_other
            allocated += amt
        shares.append((ns, _q(amt)))
    lines: list[BillingLine] = []
    for ns, amt in shares:
        ns_line_id = factory.uuid_for(f"c15/{line.line_id}/{ns}")
        lines.append(
            replace(
                line,
                line_id=ns_line_id,
                billed_cost=amt,
                effective_cost=amt,
                list_cost=amt,
                contracted_cost=amt,
                k8s_namespace=ns,
                source_fingerprint=source_fingerprint(ns_line_id),
                is_duplicate=False,
            )
        )
    return lines


def _apply_c18_fresh_resource(
    estate: CanonicalEstate, billing: list[BillingLine], factory: IdentityFactory
) -> tuple[list[BillingLine], Resource | None]:
    """C18: a new resource created on the last simulated day with a fresh spike."""
    sub_id = estate.azure_mgmt_groups[0].subscriptions[2].subscription_id
    azure_ba = next(b for b in estate.billing_accounts if b.provider == "azure")
    ident = factory.for_path(f"azure/{sub_id}/virtual_machine/c18-fresh", "azure")
    resource = Resource(
        identity=ident,
        parent_scope_id=sub_id,
        service_name="Virtual Machines",
        service_category="Compute",
        resource_type="virtual_machine",
        resource_name="c18-fresh-vm",
        region_id="eastus",
        region_name="East US",
        tags=(("env", "prod"), ("scenario", "C18")),
        sku_id="azure-vm-d2s-v5",
        # C18's fresh VM is an Azure resource created mid-scenario, so it carries no
        # capacity reservation: the eligible set is per provider
        # (``constants.CAPACITY_RESERVATION_TYPES``) and only AWS's ``ec2_instance`` is
        # keyed, which is the parity decision ``focus_azure``'s docstring records.
        capacity_reservation=None,
    )
    day = estate.sim_now
    charge_start = datetime.combine(day, _MIDDAY, tzinfo=UTC)
    amount = _q(Decimal("0.096000") * Decimal("24") * Decimal("6.0"))  # 6x spike
    line_id = factory.uuid_for(f"line/{ident.uuid}/{day.isoformat()}/Usage")
    line = BillingLine(
        line_id=line_id,
        resource_uuid=ident.uuid,
        billing_account_id=azure_ba.billing_account_id,
        sub_account_id=sub_id,
        invoice_id=None,
        service_name="Virtual Machines",
        service_category="Compute",
        charge_category="Usage",
        charge_period_start=charge_start,
        charge_period_end=charge_start + timedelta(days=1),
        billing_period_start=day.replace(day=1),
        billing_period_end=_month_end(day),
        export_time=export_time_for(day),
        is_restatement=False,
        restates_date=None,
        billed_cost=amount,
        effective_cost=amount,
        list_cost=amount,
        contracted_cost=amount,
        pricing_quantity=Decimal("24.000000"),
        pricing_unit="Hours",
        pricing_category="Standard",
        region_id="eastus",
        region_name="East US",
        tags=resource.tags,
        commitment_discount_id=None,
        commitment_discount_status=None,
        currency=estate.currency,
        service_provider_name=const.PROVIDER_AZURE,
        is_duplicate=False,
        source_fingerprint=source_fingerprint(line_id),
    )
    return billing + [line], resource


def _apply_c09_findings(
    estate: CanonicalEstate, findings: list[NativeFinding], factory: IdentityFactory
) -> list[NativeFinding]:
    """C09: open NSG/firewall + public bucket + admin-no-MFA + old SA key findings.

    Each binds to an existing resource identity (P2 no-orphan). The findings are
    native INPUTS (status=open); FinOps computes compliance from them (P1).
    """
    azure_resources = [r for r in estate.resources if r.identity.provider == "azure"]
    gcp_resources = [r for r in estate.resources if r.identity.provider == "gcp"]
    if not azure_resources or not gcp_resources:
        return findings
    specs = (
        (azure_resources[0], "NETWORK", "CRITICAL", "open NSG/firewall"),
        (gcp_resources[0], "CONFIG", "HIGH", "public bucket"),
        (azure_resources[1 % len(azure_resources)], "IAM", "HIGH", "admin without MFA"),
        (gcp_resources[1 % len(gcp_resources)], "IAM", "MEDIUM", "old SA key"),
    )
    extra: list[NativeFinding] = []
    for res, category, severity, rule in specs:
        fid = factory.uuid_for(f"c09/{res.identity.uuid}/{rule}")
        titulo, descricao = _finding_text(category, res.resource_name)
        extra.append(
            NativeFinding(
                finding_id=fid,
                resource_uuid=res.identity.uuid,
                provider=res.identity.provider,
                category=category,
                severity=severity,
                status="open",
                raised_on=estate.sim_now,
                source=SOURCE_SYNTHETIC,
                evidence_json=synthetic_evidence(rule=rule, scenario="C09"),
                title=titulo,
                description=descricao,
                types=_finding_types(category),
                **finding_provenance(estate.seed, res.identity.uuid, estate.sim_now),
            )
        )
    return findings + extra


def _apply_c07_invoice_divergence(estate: CanonicalEstate, billing: list[BillingLine]) -> list[Invoice]:
    """C07: rebuild invoices; the earliest Azure + GCP issued invoices diverge.

    Azure diverges +3.2% (``*1.032``) and GCP -1.5% (``*0.985``) from the summed
    line cost, quantized 6-dp ROUND_HALF_EVEN (design sec. 9). Every other invoice
    stays ``total == sum(lines)`` exactly. These are the ONLY allowed divergences.
    """
    groups: dict[tuple[str, str, date, date], list[BillingLine]] = {}
    for line in billing:
        if line.invoice_id is None:
            continue
        key = (line.invoice_id, line.billing_account_id, line.billing_period_start, line.billing_period_end)
        groups.setdefault(key, []).append(line)

    provider_by_ba = {b.billing_account_id: b.provider for b in estate.billing_accounts}
    azure_c07 = _earliest_invoice_id(groups, provider_by_ba, "azure")
    gcp_c07 = _earliest_invoice_id(groups, provider_by_ba, "gcp")

    invoices: list[Invoice] = []
    for (invoice_id, ba, bp_start, bp_end), lines in sorted(groups.items()):
        inv_lines = tuple(
            InvoiceLine(invoice_id=invoice_id, billing_line_id=line.line_id, amount=line.billed_cost)
            for line in sorted(lines, key=lambda line: line.line_id)
        )
        line_sum = _q(sum((il.amount for il in inv_lines), Decimal("0")))
        if invoice_id == azure_c07:
            total, diverge = _q(line_sum * _AZURE_C07_FACTOR), True
        elif invoice_id == gcp_c07:
            total, diverge = _q(line_sum * _GCP_C07_FACTOR), True
        else:
            total, diverge = line_sum, False
        invoices.append(
            Invoice(
                invoice_id=invoice_id,
                billing_account_id=ba,
                billing_period_start=bp_start,
                billing_period_end=bp_end,
                invoice_issue_status="Issued",
                total=total,
                currency=estate.currency,
                lines=inv_lines,
                is_c07_divergence=diverge,
            )
        )
    return invoices


def _earliest_invoice_id(
    groups: dict[tuple[str, str, date, date], list[BillingLine]],
    provider_by_ba: dict[str, str],
    provider: str,
) -> str | None:
    candidates = [
        (bp_start, invoice_id) for (invoice_id, ba, bp_start, _bp_end) in groups if provider_by_ba.get(ba) == provider
    ]
    if not candidates:
        return None
    return sorted(candidates)[0][1]


# ── AWS scenarios (Phase 6) ──────────────────────────────────────────────────
#
# A03/A04/A05/A06 are S3 key/execution-shape conditions emitted by the renderer,
# and A07/A08 are control-plane conditions emitted by the aws-sim shim (a CUR x CE
# divergence and an AccessDenied). Neither layer exists in the estate, so neither
# has a transform here. A09 is satisfied by the base estate: ``eks_cluster`` and
# the ``data_transfer`` cross-AZ SKU are catalog services, and EKS/FOCUS
# coherence is asserted by ``validate.quality.check_k8s_coherence``.


def _aws_account_id(estate: CanonicalEstate, index: int) -> str:
    """Return the 12-digit account id for the ``aws:<index>`` scope hint."""
    return estate.aws_orgs[0].accounts[index].account_id


def _aws_billing_account_id(estate: CanonicalEstate) -> str:
    """Return the AWS payer billing-account id."""
    return next(b for b in estate.billing_accounts if b.provider == const.PROVIDER_KEY_AWS).billing_account_id


def _commitment_id(estate: CanonicalEstate, scope_id: str) -> str:
    """Return the estate's own commitment identity for ``scope_id``.

    Derived rather than minted: the base estate's coverage stamps THIS id on the usage
    the commitment covers, so a scenario that invented its own id (A01 used to write
    ``sp-<account>``) would put two commitment ids on one scope — the same Savings Plan
    read as two commitments, and its covered and unused halves unable to meet.
    """
    return next(c.identity.uuid for c in estate.commitments if c.scope_id == scope_id)


def _apply_a01_unused_aws_commitment(
    estate: CanonicalEstate, billing: list[BillingLine], factory: IdentityFactory
) -> list[BillingLine]:
    """A01: append daily RIFee lines for the unused half of an AWS Savings Plan scope.

    Mirrors C05's shape for AWS. The observable FOCUS signal for a PARTIALLY used
    commitment is a ``CommitmentDiscountStatus=Unused`` line beside the covered usage;
    the covered half is the base estate's own covered usage — the lines
    ``generate/estate_builder.py`` stamps with this same commitment id — which is what
    makes the scenario's declared input ("SavingsPlanCoveredUsage lines covering only
    part of the eligible usage") real. Both halves carry ONE id, so nothing is counted
    twice and the export shows a single, partially-used commitment. Like C05 this is a
    commitment-level Purchase line with no backing resource.
    """
    spec = next(s for s in CATALOG if s.id == "A01")
    start, end = _window_days(estate, spec.window.start_offset, spec.window.end_offset)
    account_id = _aws_account_id(estate, 0)
    commitment_id = _commitment_id(estate, account_id)
    ba_id = _aws_billing_account_id(estate)
    extra: list[BillingLine] = []
    day = start
    while day <= end and day <= estate.sim_now:
        line_id = factory.uuid_for(f"a01/unused-sp/{account_id}/{day.isoformat()}")
        charge_start = datetime.combine(day, _MIDDAY, tzinfo=UTC)
        amount = Decimal("6.000000")
        extra.append(
            BillingLine(
                line_id=line_id,
                resource_uuid=None,
                billing_account_id=ba_id,
                sub_account_id=account_id,
                invoice_id=None,
                service_name="AWS Savings Plans",
                service_category="Compute",
                charge_category="Purchase",
                charge_period_start=charge_start,
                charge_period_end=charge_start + timedelta(days=1),
                billing_period_start=day.replace(day=1),
                billing_period_end=_month_end(day),
                export_time=export_time_for(day),
                is_restatement=False,
                restates_date=None,
                billed_cost=amount,
                effective_cost=amount,
                list_cost=amount,
                contracted_cost=amount,
                pricing_quantity=Decimal("1.000000"),
                pricing_unit="SavingsPlan",
                pricing_category="Committed",
                region_id="us-east-1",
                region_name="US East (N. Virginia)",
                tags=(),
                commitment_discount_id=commitment_id,
                commitment_discount_status="Unused",
                currency=estate.currency,
                service_provider_name=const.PROVIDER_AWS,
                is_duplicate=False,
                source_fingerprint=source_fingerprint(line_id),
            )
        )
        day += timedelta(days=1)
    return billing + extra


def _apply_a02_effective_discount(estate: CanonicalEstate, billing: list[BillingLine]) -> list[BillingLine]:
    """A02: an AWS EDP/private discount lowers effective cost while billed holds.

    This is the one sanctioned AWS effective-vs-billed gap: ``billed_cost`` is
    what AWS invoices, ``effective_cost`` is what the discount makes it. Only
    ``effective_cost`` moves — nothing is recomputed downstream (P1).
    """
    spec = next(s for s in CATALOG if s.id == "A02")
    start, end = _window_days(estate, spec.window.start_offset, spec.window.end_offset)
    account_id = _aws_account_id(estate, 1)
    factor = Decimal("0.880000")
    result: list[BillingLine] = []
    for line in billing:
        charge_day = line.charge_period_start.date()
        if (
            line.service_provider_name == const.PROVIDER_AWS
            and line.sub_account_id == account_id
            and line.charge_category == "Usage"
            and start <= charge_day <= end
        ):
            result.append(replace(line, effective_cost=_q(line.billed_cost * factor)))
        else:
            result.append(line)
    return result


def _apply_a06_restatement(
    estate: CanonicalEstate, billing: list[BillingLine], factory: IdentityFactory
) -> list[BillingLine]:
    """A06: append an Adjustment delta for an earlier AWS usage_date (original intact).

    Mirrors C17 for AWS. The restatement is a signed ``Adjustment`` delta carrying a
    LATER ``export_time``; the original Usage line is never mutated (FR-B3).

    Because the delta arrives later, the period it belongs to was delivered at least
    twice, which is exactly scenario A04's condition ("create-new delivery, several
    executions in one period"). The renderer derives that from the data — it does not
    need a flag telling it to emit several executions. So the two scenarios are one
    mechanism, and A04 cannot silently stop being emitted if A06 changes.
    """
    spec = next(s for s in CATALOG if s.id == "A06")
    start, _end = _window_days(estate, spec.window.start_offset, spec.window.end_offset)
    aws_lines = [
        line
        for line in billing
        if line.service_provider_name == const.PROVIDER_AWS
        and line.charge_category == "Usage"
        and line.charge_period_start.date() == start
        and line.resource_uuid is not None
    ]
    if not aws_lines:
        return billing
    original = sorted(aws_lines, key=lambda line: line.line_id)[0]
    delta = _q(original.billed_cost * Decimal("0.10"))  # +10% correction
    restated_on = min(estate.sim_now, original.charge_period_start.date() + timedelta(days=7))
    line_id = factory.uuid_for(f"a06/adjustment/{original.line_id}")
    charge_start = datetime.combine(original.charge_period_start.date(), _MIDDAY, tzinfo=UTC)
    adjustment = replace(
        original,
        line_id=line_id,
        charge_category="Adjustment",
        is_restatement=True,
        restates_date=original.charge_period_start.date(),
        export_time=restatement_export_time_for(original.charge_period_start.date(), restated_on),
        charge_period_start=charge_start,
        charge_period_end=charge_start + timedelta(days=1),
        billed_cost=delta,
        effective_cost=delta,
        list_cost=delta,
        contracted_cost=delta,
        is_duplicate=False,
        source_fingerprint=source_fingerprint(line_id),
    )
    return billing + [adjustment]


def _apply_a10_marketplace_support(
    estate: CanonicalEstate, billing: list[BillingLine], factory: IdentityFactory
) -> list[BillingLine]:
    """A10: append billing-only AWS Marketplace and Support line items.

    Neither has a backing resource — the same billing-only construct as FR-D5 and
    C05 — so both carry ``resource_uuid=None`` and both are ``Tax`` or
    ``Purchase``: the invariant (asserted by the gate test) is that a
    resource-less line is never ``Usage``, because Usage implies consumption of a
    resource. Marketplace is therefore a Purchase charge, matching how AWS
    invoices a Marketplace subscription, and AWS Support is a Tax charge.
    """
    spec = next(s for s in CATALOG if s.id == "A10")
    start, end = _window_days(estate, spec.window.start_offset, spec.window.end_offset)
    account_id = _aws_account_id(estate, 0)
    ba_id = _aws_billing_account_id(estate)
    extra: list[BillingLine] = []
    day = start
    while day <= end and day <= estate.sim_now:
        charge_start = datetime.combine(day, _MIDDAY, tzinfo=UTC)
        for label, service_name, service_category, category, unit, amount in (
            ("marketplace", "AWS Marketplace", "Other", "Purchase", "Units", Decimal("15.000000")),
            ("support", "AWS Support", "Management", "Tax", "Months", Decimal("100.000000")),
        ):
            line_id = factory.uuid_for(f"a10/{label}/{account_id}/{day.isoformat()}")
            extra.append(
                BillingLine(
                    line_id=line_id,
                    resource_uuid=None,
                    billing_account_id=ba_id,
                    sub_account_id=account_id,
                    invoice_id=None,
                    service_name=service_name,
                    service_category=service_category,
                    charge_category=category,
                    charge_period_start=charge_start,
                    charge_period_end=charge_start + timedelta(days=1),
                    billing_period_start=day.replace(day=1),
                    billing_period_end=_month_end(day),
                    export_time=export_time_for(day),
                    is_restatement=False,
                    restates_date=None,
                    billed_cost=amount,
                    effective_cost=amount,
                    list_cost=amount,
                    contracted_cost=amount,
                    pricing_quantity=Decimal("1.000000"),
                    pricing_unit=unit,
                    pricing_category="Standard",
                    region_id="us-east-1",
                    region_name="US East (N. Virginia)",
                    tags=(),
                    commitment_discount_id=None,
                    commitment_discount_status=None,
                    currency=estate.currency,
                    service_provider_name=const.PROVIDER_AWS,
                    is_duplicate=False,
                    source_fingerprint=source_fingerprint(line_id),
                )
            )
        day += timedelta(days=1)
    return billing + extra
