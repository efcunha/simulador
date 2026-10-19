"""AWS Config JSON-protocol tests, parsed with botocore's own parser.

The load-bearing assertion is that the violation set is the estate's, not a fixture: the
resources the required-tags rule reports non-compliant are exactly the estate resources
that are missing a required tag key.
"""

from __future__ import annotations

import json

import botocore.session
from botocore.parsers import create_parser

from aws_sim import arns, scope
from aws_sim.projections import config_service

_MODEL = botocore.session.get_session().get_service_model("config")
_PARSER = create_parser("json")


def _parse(client, operation: str, body: dict | None = None):
    target = f"{_MODEL.metadata['targetPrefix']}.{operation}"
    response = client.post("/", content=json.dumps(body or {}), headers={"X-Amz-Target": target})
    raw = {"status_code": response.status_code, "headers": dict(response.headers), "body": response.content}
    shape = _MODEL.operation_model(operation).output_shape
    if response.status_code != 200:
        return _PARSER._do_error_parse(raw, shape)
    return _PARSER.parse(raw, shape)


def _expected_tag_violations(app) -> set[str]:
    return {
        arns.resource_arn(resource) or resource.resource_name
        for resource in config_service.evaluated_resources(app.state.estate)
        if [key for key in config_service.REQUIRED_TAG_KEYS if key not in {k for k, _ in resource.tags}]
    }


def test_only_the_filtered_compliance_type_comes_back(api_client) -> None:
    client, _ = api_client
    rules = _parse(client, "DescribeComplianceByConfigRule", {"ComplianceTypes": ["NON_COMPLIANT"]})[
        "ComplianceByConfigRules"
    ]
    assert rules
    for rule in rules:
        assert rule["Compliance"]["ComplianceType"] == "NON_COMPLIANT"
        assert rule["Compliance"]["ComplianceContributorCount"]["CappedCount"] > 0

    everything = _parse(client, "DescribeComplianceByConfigRule")["ComplianceByConfigRules"]
    assert len(everything) == len(config_service.RULES)


def test_the_required_tags_rule_reports_the_estates_untagged_resources(api_client) -> None:
    client, app = api_client
    results = _parse(
        client,
        "GetComplianceDetailsByConfigRule",
        {"ConfigRuleName": "synth-required-tags", "ComplianceTypes": ["NON_COMPLIANT"]},
    )["EvaluationResults"]

    assert results
    reported = {
        row["EvaluationResultIdentifier"]["EvaluationResultQualifier"]["ResourceId"]
        for row in results
    }
    assert reported == _expected_tag_violations(app)
    for row in results:
        qualifier = row["EvaluationResultIdentifier"]["EvaluationResultQualifier"]
        assert qualifier["ResourceType"].startswith("AWS::")
        assert row["ComplianceType"] == "NON_COMPLIANT"
        assert "required tag keys" in row["Annotation"]
        assert row["ResultRecordedTime"] is not None


def test_the_iac_rule_reports_the_estates_unmanaged_resources(api_client) -> None:
    client, app = api_client
    estate = app.state.estate
    rows = _parse(client, "DescribeComplianceByConfigRule")["ComplianceByConfigRules"]
    assert [row["ConfigRuleName"] for row in rows] == [rule.name for rule in config_service.RULES]

    results = _parse(
        client,
        "GetComplianceDetailsByConfigRule",
        {"ConfigRuleName": "synth-iac-managed"},
    )["EvaluationResults"]
    managed = {asset.resource_uuid: asset.managed_by_iac for asset, _ in scope.inventory(estate)}
    expected = {
        arns.resource_arn(resource) or resource.resource_name
        for resource in config_service.evaluated_resources(estate)
        if managed.get(resource.identity.uuid) is False
    }
    assert expected
    reported = {
        row["EvaluationResultIdentifier"]["EvaluationResultQualifier"]["ResourceId"] for row in results
    }
    assert reported == expected


def test_limit_and_unknown_rules(api_client) -> None:
    client, _ = api_client
    limited = _parse(
        client,
        "GetComplianceDetailsByConfigRule",
        {"ConfigRuleName": "synth-required-tags", "Limit": 2},
    )["EvaluationResults"]
    assert len(limited) == 2

    error = _parse(client, "GetComplianceDetailsByConfigRule", {"ConfigRuleName": "nope"})
    assert error["Error"]["Code"] == "NoSuchConfigRuleException"

    missing = _parse(client, "GetComplianceDetailsByConfigRule")
    assert missing["Error"]["Code"] == "InvalidParameterValueException"
