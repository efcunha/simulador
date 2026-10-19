"""STS over the Query protocol: ``AssumeRole`` and ``GetCallerIdentity``.

Same single-route shape as CloudFormation (the Query protocol has one route), but this
module holds no route of its own: a single endpoint override serves every AWS service, so
the route lives once in ``api.app`` and dispatches by ``Action``. This module owns the
STS action set and its XML rendering.

``GetCallerIdentity`` reads the account from the caller's signed request (see
``projections/sts.py``), so ``authorization`` is threaded in rather than read here — a
handler that reaches for the raw request would be untestable without HTTP.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from tools.synthetic_clouds.model.estate import CanonicalEstate

from aws_sim import query_xml
from aws_sim.api.cloudformation import CODE_INVALID_ACTION, CODE_INVALID_PARAMETER, CODE_MISSING_PARAMETER, AwsApiError
from aws_sim.projections import sts

_ACTIONS: frozenset[str] = frozenset({"AssumeRole", "GetCallerIdentity"})


def supported_actions() -> tuple[str, ...]:
    """The actions this slice answers, sorted. Used by tests and by ``InvalidAction``."""
    return tuple(sorted(_ACTIONS))


def _require(params: Mapping[str, str], key: str) -> str:
    value = params.get(key, "").strip()
    if not value:
        raise AwsApiError(CODE_MISSING_PARAMETER, f"{key} is required for this operation.")
    return value


def _assume_role(estate: CanonicalEstate, params: Mapping[str, str], *, denied_account: str) -> dict[str, Any]:
    try:
        return sts.assume_role(
            estate,
            role_arn=_require(params, "RoleArn"),
            role_session_name=_require(params, "RoleSessionName"),
            duration_seconds=int(params.get("DurationSeconds") or sts.DEFAULT_DURATION_SECONDS),
            denied_account=denied_account,
        )
    except sts.StsError as exc:
        raise AwsApiError(exc.code, exc.message) from exc


def dispatch_form(
    estate: CanonicalEstate,
    region: str,
    form: Mapping[str, str],
    *,
    authorization: str | None,
    denied_account: str,
) -> str:
    """Answer one STS Query-protocol request, returning the XML body."""
    action = form.get("Action", "").strip()
    if not action:
        raise AwsApiError(CODE_MISSING_PARAMETER, "Action is required.")

    version = form.get("Version", "").strip()
    if version != query_xml.STS.api_version():
        raise AwsApiError(
            CODE_INVALID_PARAMETER,
            f"Version {version!r} is not supported; expected {query_xml.STS.api_version()!r}.",
        )

    if action == "AssumeRole":
        result = _assume_role(estate, form, denied_account=denied_account)
    elif action == "GetCallerIdentity":
        result = sts.caller_identity(
            estate, access_key=sts.parse_access_key(authorization), region=region
        )
    else:
        raise AwsApiError(
            CODE_INVALID_ACTION,
            f"Action {action} is not served by the STS simulator. Supported: {', '.join(supported_actions())}.",
        )

    return query_xml.STS.render_result(action, result, f"synth-{uuid.uuid4().hex[:8]}")
