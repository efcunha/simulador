"""aws-sim: the AWS control-plane shim for FinOps synthetic clouds (Phase 6).

A **consumer** of the Phase 1 generator, exactly like ``azure-sim``: it never
reinvents estate construction, it builds the gated canonical estate once and projects
from it. What differs is the wire protocol. Azure and GCP are reached over JSON REST,
so their sims are per-operation FastAPI routers; **CloudFormation is the Query
protocol** — form-encoded `Action=...` requests answered with XML (design sec. 22.1) —
so this package carries a shape-driven XML renderer instead.

First slice (design sec. 22.4): the five read-only drift operations
(`ListStacks`, `DetectStackDrift`, `DescribeStackDriftDetectionStatus`,
`DescribeStackResourceDrifts`, `ListStackResources`). The seven stack-set operations
are the second slice; two of them write, which needs a decision about mutating a frozen
estate first.

No real AWS credential is ever used, and the process refuses to start if it detects
one (``aws_sim.guard``, FR-15).
"""

from __future__ import annotations

from aws_sim.config import Settings, load_settings
from aws_sim.estate import build_simulated_estate
from aws_sim.guard import SafetyRefusalError, assert_no_real_credentials

__all__ = [
    "SafetyRefusalError",
    "Settings",
    "assert_no_real_credentials",
    "build_simulated_estate",
    "load_settings",
]
