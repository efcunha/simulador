"""CloudFormation over the Query protocol (design sec. 22.1).

One route, because the Query protocol has one: the client POSTs form-encoded
``Action=<Operation>&Version=2010-05-15&<params>`` to the endpoint root and expects XML
back. There is no per-operation path to hang a router off, which is precisely why the
azure-sim shape could not be copied.

Only the five read-only drift operations are served (design sec. 22.4). The seven
stack-set operations are the second slice, and the request for one of them is answered
with ``InvalidAction`` rather than a 404 — that is what the service model says an
unknown action means, and it tells a caller the difference between "this emulator does
not serve it yet" and "you reached the wrong place".
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import parse_qs

from tools.synthetic_clouds.model.estate import CanonicalEstate

from aws_sim import query_xml
from aws_sim.projections import cloudformation

#: Query-protocol error codes. ``ValidationError`` is the one CloudFormation itself uses
#: for a stack that does not exist, so an emulated miss reads like a real one.
CODE_VALIDATION_ERROR = "ValidationError"
CODE_INVALID_ACTION = "InvalidAction"
CODE_INVALID_PARAMETER = "InvalidParameterValue"
CODE_MISSING_PARAMETER = "MissingParameter"

Handler = Callable[[CanonicalEstate, str, Mapping[str, str]], dict[str, Any]]


class AwsApiError(Exception):
    """An error that renders as the Query-protocol ``<ErrorResponse>`` envelope."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def _require(params: Mapping[str, str], key: str) -> str:
    value = params.get(key, "").strip()
    if not value:
        raise AwsApiError(CODE_MISSING_PARAMETER, f"{key} is required for this operation.")
    return value


def _require_stack(estate: CanonicalEstate, region: str, name: str) -> cloudformation.Stack:
    stack = cloudformation.find_stack(estate, region, name)
    if stack is None:
        raise AwsApiError(CODE_VALIDATION_ERROR, f"Stack with id {name} does not exist")
    return stack


def _list_stacks(estate: CanonicalEstate, region: str, params: Mapping[str, str]) -> dict[str, Any]:
    """``ListStacks`` — every synthetic stack.

    ``StackStatusFilter`` is accepted and ignored: the estate has one stack status, and
    filtering it would be a no-op dressed up as a feature.
    """
    return {"StackSummaries": [cloudformation.stack_summary(stack) for stack in cloudformation.stacks(estate, region)]}


def _detect_stack_drift(estate: CanonicalEstate, region: str, params: Mapping[str, str]) -> dict[str, Any]:
    """``DetectStackDrift`` — returns the detection id the caller then polls."""
    stack = _require_stack(estate, region, _require(params, "StackName"))
    return {"StackDriftDetectionId": stack.snapshot_id}


def _describe_stack_drift_detection_status(
    estate: CanonicalEstate,
    region: str,
    params: Mapping[str, str],
) -> dict[str, Any]:
    """``DescribeStackDriftDetectionStatus`` — resolves immediately on a frozen estate."""
    detection_id = _require(params, "StackDriftDetectionId")
    stack = cloudformation.stack_by_detection_id(estate, region, detection_id)
    if stack is None:
        raise AwsApiError(CODE_VALIDATION_ERROR, f"Stack drift detection {detection_id} does not exist")
    return cloudformation.drift_detection_status(stack)


def _describe_stack_resource_drifts(
    estate: CanonicalEstate,
    region: str,
    params: Mapping[str, str],
) -> dict[str, Any]:
    """``DescribeStackResourceDrifts`` — the per-resource drift input."""
    stack = _require_stack(estate, region, _require(params, "StackName"))
    return {
        "StackResourceDrifts": [cloudformation.resource_drift_row(stack, drift) for drift in stack.resources],
    }


def _list_stack_resources(estate: CanonicalEstate, region: str, params: Mapping[str, str]) -> dict[str, Any]:
    """``ListStackResources`` — the declared resources of a stack."""
    stack = _require_stack(estate, region, _require(params, "StackName"))
    return {
        "StackResourceSummaries": [
            cloudformation.stack_resource_summary(stack, drift) for drift in stack.resources
        ],
    }


_HANDLERS: dict[str, Handler] = {
    "ListStacks": _list_stacks,
    "DetectStackDrift": _detect_stack_drift,
    "DescribeStackDriftDetectionStatus": _describe_stack_drift_detection_status,
    "DescribeStackResourceDrifts": _describe_stack_resource_drifts,
    "ListStackResources": _list_stack_resources,
}


def supported_actions() -> tuple[str, ...]:
    """The actions this slice answers, sorted. Used by tests and by ``InvalidAction``."""
    return tuple(sorted(_HANDLERS))


def dispatch_form(estate: CanonicalEstate, region: str, form: Mapping[str, str]) -> str:
    """Answer one Query-protocol request, returning the XML body.

    Split out from the route so the whole protocol path is testable without HTTP.
    """
    action = form.get("Action", "").strip()
    if not action:
        raise AwsApiError(CODE_MISSING_PARAMETER, "Action is required.")

    version = form.get("Version", "").strip()
    if version != query_xml.api_version():
        raise AwsApiError(
            CODE_INVALID_PARAMETER,
            f"Version {version!r} is not supported; expected {query_xml.api_version()!r}.",
        )

    handler = _HANDLERS.get(action)
    if handler is None:
        raise AwsApiError(
            CODE_INVALID_ACTION,
            f"Action {action} is not served by this simulator. Supported: {', '.join(supported_actions())}.",
        )

    result = handler(estate, region, form)
    return query_xml.render_result(action, result, f"synth-{uuid.uuid4().hex[:8]}")


def parse_query_body(raw: bytes) -> dict[str, str]:
    """Parse an ``application/x-www-form-urlencoded`` Query-protocol body.

    Deliberately **not** ``await request.form()``. Starlette's form parsing requires the
    ``python-multipart`` package, and when it is absent the request raises ``AssertionError``
    at runtime — an error no in-process test can catch, because the development venv has the
    package installed. It was found by running the container:

        AssertionError: The `python-multipart` library must be installed to use form parsing.

    The Query protocol is a plain urlencoded body, so :func:`urllib.parse.parse_qs` from the
    standard library does the job and removes both the dependency and the failure mode.
    Repeated keys keep their first value, the conventional Query semantic; every parameter
    this slice reads is a single value.
    """
    text = raw.decode("utf-8", errors="replace")
    return {key: values[0] for key, values in parse_qs(text, keep_blank_values=True).items()}
