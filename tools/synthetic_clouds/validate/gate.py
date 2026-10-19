"""The pre-publish gate: run ALL referential-integrity + quality checks (fail-closed).

``run`` executes every check in ``integrity`` and ``quality`` on the in-memory
estate BEFORE any artifact or scenarios.json is written (design sec. 9). A single
violation raises ``IntegrityError``/``QualityError`` and nothing is published —
except the scenarios that deliberately diverge (C07), which are modeled as
expected and are validated against their pinned formula, not treated as errors.
"""

from __future__ import annotations

from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.validate.integrity import check_no_orphans, check_resource_scoping
from tools.synthetic_clouds.validate.quality import (
    check_category_domain,
    check_credits_bound,
    check_finding_attributes,
    check_invoice_balance,
    check_k8s_coherence,
    check_provider_domain,
)


def run(estate: CanonicalEstate) -> None:
    """Run all pre-publish checks; raise on the first violation (fail-closed)."""
    check_no_orphans(estate)
    check_resource_scoping(estate)
    check_invoice_balance(estate)
    check_credits_bound(estate)
    check_category_domain(estate)
    check_provider_domain(estate)
    check_k8s_coherence(estate)
    check_finding_attributes(estate)
