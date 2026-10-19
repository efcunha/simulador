"""The AWS Config projection: rule compliance, evaluated over the estate.

Config's purpose is to answer "which of my resources break this rule". The estate carries
no rule table, so the rules are **derived from facts the estate does assert**, and each
violation names the fact it came from:

* ``synth-required-tags`` — a resource missing a required tag key. The estate's tag
  policy is real data: ~15% of its resources carry no tags at all (FR-D2), so this rule
  has both sides to report.
* ``synth-iac-managed`` — a resource whose inventory asset is not managed by IaC. That
  is the estate's own ``InventoryAsset.managed_by_iac`` flag, the same input the C11
  drift scenario produces.

Two rules, not a catalog: a rule with no estate fact behind it would generate findings
FinOps acts on and nothing in the estate could justify.

The detail rows use the resource's **ARN** as ``ResourceId``. AWS Config uses whatever
identifier the resource type is known by (a bucket name, a function name, an ARN), and
the ARN is the one identifier this estate has for every resource — the same one the
tagging API and the per-service projections report, so a Config finding can be joined to
the rest of FinOps inventory.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.resource import Resource

from aws_sim import arns, scope

COMPLIANT = "COMPLIANT"
NON_COMPLIANT = "NON_COMPLIANT"

#: The tag keys an estate resource must carry. The estate's own generated tag set.
REQUIRED_TAG_KEYS: tuple[str, ...] = ("env", "owner")

#: estate ``resource_type`` -> the AWS Config resource type string. Only types AWS can
#: actually evaluate are listed, which is why ``data_transfer`` (a cost line, not a
#: resource) is absent rather than given an invented type: Config cannot report on a
#: resource that does not exist.
CONFIG_RESOURCE_TYPES: dict[str, str] = {
    "ec2_instance": "AWS::EC2::Instance",
    "ebs_volume": "AWS::EC2::Volume",
    "nat_gateway": "AWS::EC2::NatGateway",
    "elastic_ip": "AWS::EC2::EIP",
    "vpc": "AWS::EC2::VPC",
    "security_group": "AWS::EC2::SecurityGroup",
    "rds_instance": "AWS::RDS::DBInstance",
    "s3_bucket": "AWS::S3::Bucket",
    "dynamodb_table": "AWS::DynamoDB::Table",
    "eks_cluster": "AWS::EKS::Cluster",
    "lambda_function": "AWS::Lambda::Function",
    "ecs_cluster": "AWS::ECS::Cluster",
    "application_lb": "AWS::ElasticLoadBalancingV2::LoadBalancer",
    "cloudwatch_logs": "AWS::Logs::LogGroup",
}

#: A violation: the resource, and the reason Config would annotate it with.
Violation = tuple[Resource, str]
Evaluator = Callable[[CanonicalEstate], tuple[Violation, ...]]


@dataclass(frozen=True, slots=True)
class ConfigRule:
    """One synthetic Config rule and the estate fact it evaluates."""

    name: str
    description: str
    source_identifier: str
    evaluate: Evaluator


def evaluated_resources(estate: CanonicalEstate) -> tuple[Resource, ...]:
    """This provider's resources of a type AWS Config can evaluate, ordered."""
    return tuple(
        r
        for r in sorted(scope.resources(estate), key=lambda r: r.resource_name)
        if r.resource_type in CONFIG_RESOURCE_TYPES
    )


def _missing_tag_violations(estate: CanonicalEstate) -> tuple[Violation, ...]:
    violations: list[Violation] = []
    for resource in evaluated_resources(estate):
        present = {key for key, _ in resource.tags}
        missing = [key for key in REQUIRED_TAG_KEYS if key not in present]
        if missing:
            violations.append(
                (resource, f"Resource is missing required tag keys: {', '.join(missing)}."),
            )
    return tuple(violations)


def _unmanaged_violations(estate: CanonicalEstate) -> tuple[Violation, ...]:
    managed = {asset.resource_uuid: asset.managed_by_iac for asset, _ in scope.inventory(estate)}
    return tuple(
        (resource, "Resource is present in inventory but not managed by IaC.")
        for resource in evaluated_resources(estate)
        if managed.get(resource.identity.uuid) is False
    )


#: The rule set. Ordered, so ``DescribeComplianceByConfigRule`` answers in a stable order.
RULES: tuple[ConfigRule, ...] = (
    ConfigRule(
        name="synth-required-tags",
        description=f"Resources must carry the required tag keys: {', '.join(REQUIRED_TAG_KEYS)}.",
        source_identifier="REQUIRED_TAGS",
        evaluate=_missing_tag_violations,
    ),
    ConfigRule(
        name="synth-iac-managed",
        description="Resources must be managed by infrastructure as code.",
        source_identifier="CUSTOM_LAMBDA",
        evaluate=_unmanaged_violations,
    ),
)


def find_rule(name: str) -> ConfigRule | None:
    """Resolve a rule by name, or ``None`` (the API maps that onto ``NoSuchConfigRule``)."""
    return next((rule for rule in RULES if rule.name == name), None)


def _recorded_at(estate: CanonicalEstate) -> float:
    """When the rules were evaluated: the estate's own clock, as epoch seconds.

    JSON-1.1 timestamps are numbers, and the estate is frozen — the evaluation time is
    the sim's start day, not the host's now, so two calls cannot disagree.
    """
    start = estate.sim_start
    return datetime(start.year, start.month, start.day, tzinfo=UTC).timestamp()


def _matches(compliance_type: str, requested: Sequence[str] | None) -> bool:
    """Whether a compliance type passes the caller's filter (an absent filter passes all)."""
    if not requested:
        return True
    return compliance_type in {value.upper() for value in requested}


def compliance_by_rule(
    estate: CanonicalEstate,
    *,
    config_rule_names: Sequence[str] | None = None,
    compliance_types: Sequence[str] | None = None,
) -> tuple[dict[str, Any], ...]:
    """One ``ComplianceByConfigRules`` entry per rule whose verdict passes the filter."""
    wanted = {name for name in config_rule_names or ()}
    rows: list[dict[str, Any]] = []
    for rule in RULES:
        if wanted and rule.name not in wanted:
            continue
        violations = rule.evaluate(estate)
        compliance_type = NON_COMPLIANT if violations else COMPLIANT
        if not _matches(compliance_type, compliance_types):
            continue
        rows.append(
            {
                "ConfigRuleName": rule.name,
                "Compliance": {
                    "ComplianceType": compliance_type,
                    "ComplianceContributorCount": {
                        "CappedCount": len(violations),
                        "CapExceeded": False,
                    },
                },
            },
        )
    return tuple(rows)


def evaluation_results(
    estate: CanonicalEstate,
    rule: ConfigRule,
    *,
    compliance_types: Sequence[str] | None = None,
    limit: int | None = None,
) -> tuple[dict[str, Any], ...]:
    """The ``EvaluationResults`` rows for one rule, one per violating resource.

    A rule with no violation yields no row: there is nothing to evaluate non-compliant,
    and an empty ``EvaluationResults`` is what the caller's loop already handles.
    """
    if not _matches(NON_COMPLIANT, compliance_types):
        return ()
    recorded = _recorded_at(estate)
    rows: list[dict[str, Any]] = []
    for resource, annotation in rule.evaluate(estate):
        # Every type Config evaluates has an ARN (``CONFIG_RESOURCE_TYPES``), so the fallback
        # is the estate's own uuid and never the reused ``resource_name``: an id this endpoint
        # answers must not be a value two resources share (``aws_sim.ids``).
        arn = arns.resource_arn(resource) or resource.identity.uuid
        rows.append(
            {
                "EvaluationResultIdentifier": {
                    "EvaluationResultQualifier": {
                        "ConfigRuleName": rule.name,
                        "ResourceType": CONFIG_RESOURCE_TYPES[resource.resource_type],
                        "ResourceId": arn,
                    },
                    "OrderingTimestamp": recorded,
                },
                "ComplianceType": NON_COMPLIANT,
                "ResultRecordedTime": recorded,
                "ConfigRuleInvokedTime": recorded,
                "Annotation": annotation,
            },
        )
        if limit is not None and len(rows) >= limit:
            break
    return tuple(rows)
