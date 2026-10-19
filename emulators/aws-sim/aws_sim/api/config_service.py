"""AWS Config over the AWS JSON protocol: rule compliance and its details.

Both operations FinOps Config check calls (``security (modulo do consumidor)``), in the
order it calls them: ``DescribeComplianceByConfigRule`` (filtered with
``ComplianceTypes=["NON_COMPLIANT"]``) for the rules that are failing, then
``GetComplianceDetailsByConfigRule`` for the resources behind each one.

``ComplianceTypes`` is honored on both — the caller's filter is the whole point of the
first call, and answering it with compliant rules as well would produce findings for
resources that are fine. ``Limit`` is honored on the detail call, and no ``NextToken`` is
emitted: the estate is one page, and an absent token ends the paginator's loop.
"""

from __future__ import annotations

from typing import Any

from tools.synthetic_clouds.model.estate import CanonicalEstate

from aws_sim import json_wire
from aws_sim.json_wire import JsonApiError
from aws_sim.projections import config_service

WIRE = json_wire.JsonWire("config")

_ACTIONS: frozenset[str] = frozenset({"DescribeComplianceByConfigRule", "GetComplianceDetailsByConfigRule"})

#: Config's own code for a rule this account does not have.
CODE_NO_SUCH_RULE = "NoSuchConfigRuleException"
CODE_INVALID_PARAMETER = "InvalidParameterValueException"


def supported_actions() -> tuple[str, ...]:
    """The operations this slice answers, sorted."""
    return tuple(sorted(_ACTIONS))


def _names(body: dict[str, Any], key: str) -> list[str]:
    value = body.get(key) or []
    return [str(item) for item in value]


def _rule(name: str) -> config_service.ConfigRule:
    rule = config_service.find_rule(name)
    if rule is None:
        raise JsonApiError(CODE_NO_SUCH_RULE, f"The Config rule {name!r} does not exist.")
    return rule


def dispatch(estate: CanonicalEstate, operation: str, body: dict[str, Any]) -> dict[str, Any]:
    """Answer one AWS Config JSON request, returning the result dict."""
    if operation == "DescribeComplianceByConfigRule":
        names = _names(body, "ConfigRuleNames")
        for name in names:
            _rule(name)
        rules = config_service.compliance_by_rule(
            estate,
            config_rule_names=names,
            compliance_types=_names(body, "ComplianceTypes"),
        )
        return {"ComplianceByConfigRules": list(rules)}

    if operation == "GetComplianceDetailsByConfigRule":
        name = str(body.get("ConfigRuleName") or "").strip()
        if not name:
            raise JsonApiError(CODE_INVALID_PARAMETER, "ConfigRuleName is required for this operation.")
        limit = body.get("Limit")
        return {
            "EvaluationResults": list(
                config_service.evaluation_results(
                    estate,
                    _rule(name),
                    compliance_types=_names(body, "ComplianceTypes"),
                    limit=int(limit) if limit else None,
                ),
            ),
        }

    raise JsonApiError(
        CODE_INVALID_PARAMETER,
        f"Operation {operation} is not served by the Config simulator. Supported: {', '.join(supported_actions())}.",
    )


def render(estate: CanonicalEstate, target: str | None, body: dict[str, Any]) -> str:
    """Render the JSON body for an ``X-Amz-Target`` request."""
    operation = WIRE.operation_for_target(target)
    if operation is None:
        raise JsonApiError(CODE_INVALID_PARAMETER, f"Target {target!r} is not served.")
    return WIRE.render_result(dispatch(estate, operation, body))
