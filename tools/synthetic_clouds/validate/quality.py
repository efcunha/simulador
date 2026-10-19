"""Quality checks: invoice balance (+C07), credits bound, domains, K8s coherence.

All money arithmetic runs on canonical ``Decimal`` values (never the FLOAT64 GCP
projection), so the 6-dp invariants hold exactly (design sec. 8.3 / 9).

C07 is the ONLY allowed invoice/cost divergence. For a declared C07 invoice the
check recomputes the expected total with the IDENTICAL pinned formula
(``*1.032`` Azure / ``*0.985`` GCP, quantize 6-dp ROUND_HALF_EVEN) and asserts
exact equality. Every non-C07 invoice must satisfy ``total == sum(lines)`` exactly.
"""

from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal

from tools.synthetic_clouds.generate import constants as const
from tools.synthetic_clouds.generate.estate_builder import FINDING_TYPE_NAMESPACES
from tools.synthetic_clouds.model.estate import CanonicalEstate

_SIX = Decimal("0.000001")
# The declared C07 divergence factor per provider. AWS deliberately has NO entry:
# the base estate emits no AWS C07 invoice, and a provider with no declared factor
# must fail loudly rather than inherit another provider's. The previous binary
# ternary (``*1.032`` if azure else ``*0.985``) silently handed the GCP factor to
# any third provider.
_C07_FACTOR = {
    "azure": Decimal("1.032"),
    "gcp": Decimal("0.985"),
}


class QualityError(Exception):
    """Raised when a quality invariant is violated (fatal)."""


def _q(value: Decimal) -> Decimal:
    return value.quantize(_SIX, ROUND_HALF_EVEN)


#: Limites de comprimento que a documentacao do ASFF publica para estes dois
#: campos obrigatorios. Um titulo vazio ou longo demais seria recusado pelo
#: servico real, entao o simulador nao pode produzi-lo.
TITLE_MAX = 256
DESCRIPTION_MAX = 1024
GENERATOR_ID_MAX = 512
PRODUCT_NAME_MAX = 128


def check_finding_attributes(estate: CanonicalEstate) -> None:
    """Titulo, descricao, ``Types`` e procedencia dentro do que a documentacao exige.

    Os tres primeiros sao OBRIGATORIOS no ASFF e existem no modelo desde
    2026-10-14; ``GeneratorId`` tambem. Sem este check, esvaziar um deles passaria
    despercebido -- foi assim que ficaram vazios por tanto tempo.
    """
    for finding in estate.findings:
        if not finding.title or len(finding.title) > TITLE_MAX:
            raise QualityError(
                f"finding {finding.finding_id} com titulo fora de 1..{TITLE_MAX}: {finding.title!r}"
            )
        if not finding.description or len(finding.description) > DESCRIPTION_MAX:
            raise QualityError(
                f"finding {finding.finding_id} com descricao fora de 1..{DESCRIPTION_MAX}"
            )
        if not finding.types:
            raise QualityError(f"finding {finding.finding_id} sem 'types' (obrigatorio no ASFF)")
        for tipo in finding.types:
            namespace = tipo.split("/", 1)[0]
            if namespace not in FINDING_TYPE_NAMESPACES:
                raise QualityError(
                    f"finding {finding.finding_id}: namespace {namespace!r} fora da lista que o "
                    f"ASFF publica"
                )
        if not finding.generator_id or len(finding.generator_id) > GENERATOR_ID_MAX:
            raise QualityError(
                f"finding {finding.finding_id} com generator_id fora de 1..{GENERATOR_ID_MAX}"
            )
        for rotulo, valor in (("product_name", finding.product_name), ("company_name", finding.company_name)):
            if not valor or len(valor) > PRODUCT_NAME_MAX:
                raise QualityError(
                    f"finding {finding.finding_id} com {rotulo} fora de 1..{PRODUCT_NAME_MAX}"
                )
        for rotulo, numero in (("confidence", finding.confidence), ("criticality", finding.criticality)):
            if numero is not None and not 0 <= numero <= 100:
                raise QualityError(
                    f"finding {finding.finding_id}: {rotulo} fora da escala 0-100 ({numero})"
                )
        if finding.first_observed_at is not None:
            if not estate.sim_start <= finding.first_observed_at.date() <= estate.sim_now:
                raise QualityError(
                    f"finding {finding.finding_id} observado fora da janela: "
                    f"{finding.first_observed_at.isoformat()}"
                )
            if finding.first_observed_at.tzinfo is None:
                raise QualityError(
                    f"finding {finding.finding_id}: 'first_observed_at' precisa de fuso (UTC)"
                )


def check_invoice_balance(estate: CanonicalEstate) -> None:
    """Assert invoice total == sum(lines), except declared C07 invoices (AC-9).

    For a C07 invoice the expected total is the summed line cost times the pinned
    provider factor (recomputed, not re-derived as a percentage) — exact equality.
    """
    provider_by_ba = {b.billing_account_id: b.provider for b in estate.billing_accounts}
    for invoice in estate.invoices:
        line_sum = _q(sum((line.amount for line in invoice.lines), Decimal("0")))
        if invoice.is_c07_divergence:
            provider = provider_by_ba.get(invoice.billing_account_id)
            if provider not in _C07_FACTOR:
                raise QualityError(
                    f"C07 invoice {invoice.invoice_id}: no declared C07 factor for provider {provider!r}"
                )
            factor = _C07_FACTOR[provider]
            expected = _q(line_sum * factor)
            if invoice.total != expected:
                raise QualityError(
                    f"C07 invoice {invoice.invoice_id}: total {invoice.total} != expected {expected} "
                    f"(line_sum {line_sum} * {factor})"
                )
        elif invoice.total != line_sum:
            raise QualityError(f"invoice {invoice.invoice_id}: total {invoice.total} != sum(lines) {line_sum}")


def check_credits_bound(estate: CanonicalEstate) -> None:
    """Assert every credit amount <= its applicable cost (AC-10, FR-E2)."""
    for credit in estate.credits:
        if credit.amount > credit.applicable_cost:
            raise QualityError(
                f"credit {credit.identity.uuid}: amount {credit.amount} > applicable_cost {credit.applicable_cost}"
            )


def check_category_domain(estate: CanonicalEstate) -> None:
    """Assert every charge_category is in the FOCUS valid set (AC-12, FR-G1a)."""
    valid = set(const.VALID_CATEGORIES)
    for line in estate.billing_lines:
        if line.charge_category not in valid:
            raise QualityError(f"billing line {line.line_id}: invalid charge_category {line.charge_category!r}")


def check_provider_domain(estate: CanonicalEstate) -> None:
    """Assert every service_provider_name is a canonical FOCUS value (AC-12, FR-G1b).

    The valid set is derived from ``constants.FOCUS_PROVIDER_NAME`` — the same
    dispatch table the builder stamps lines from — so a provider added there can
    never be silently rejected here.
    """
    valid = set(const.FOCUS_PROVIDER_NAME.values())
    for line in estate.billing_lines:
        if line.service_provider_name not in valid:
            raise QualityError(
                f"billing line {line.line_id}: invalid service_provider_name {line.service_provider_name!r}"
            )


def check_k8s_coherence(estate: CanonicalEstate) -> None:
    """Assert per-cluster namespace shares sum to the cluster FOCUS cost (OA-7, C15).

    Namespace-share lines carry ``k8s_namespace`` and the SAME ``resource_uuid`` as
    the cluster line they were split from. They are grouped per cluster line by
    ``(resource_uuid, charge_period_start)`` — each cluster resource is distinct, so
    this isolates one cluster line's partition (grouping only by sub_account/service
    would wrongly merge sibling clusters sharing a charge day). The sum of the group's
    billed_cost is the cluster FOCUS cost for that charge day; the invariant is that
    the dominant namespace holds the majority share.
    """
    cluster_services = ("Azure Kubernetes Service", "Kubernetes Engine", "Amazon Elastic Kubernetes Service")
    groups: dict[tuple[str | None, str], list[tuple[str, Decimal]]] = {}
    for line in estate.billing_lines:
        if line.service_name in cluster_services and line.k8s_namespace is not None:
            key = (line.resource_uuid, line.charge_period_start.isoformat())
            groups.setdefault(key, []).append((line.k8s_namespace, line.billed_cost))
    for key, shares in groups.items():
        total = _q(sum((amt for _ns, amt in shares), Decimal("0")))
        if total <= Decimal("0"):
            raise QualityError(f"k8s cluster {key}: non-positive total {total}")
        dominant_ns, dominant_amt = max(shares, key=lambda pair: pair[1])
        if dominant_ns != const.K8S_NAMESPACES[0]:
            raise QualityError(
                f"k8s cluster {key}: dominant namespace is {dominant_ns!r}, expected {const.K8S_NAMESPACES[0]!r}"
            )
        if dominant_amt * Decimal("2") <= total:
            raise QualityError(f"k8s cluster {key}: dominant share {dominant_amt} is not a majority of {total}")
