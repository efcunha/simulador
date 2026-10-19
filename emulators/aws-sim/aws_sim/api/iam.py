"""IAM over the Query protocol: the account credential report.

Two operations, both what FinOps IAM check calls (``security (modulo do consumidor)``):

* ``GenerateCredentialReport`` -> ``COMPLETE``. The real service generates
  asynchronously and answers ``STARTED`` while it works, but a **frozen estate has
  nothing to compute**: answering ``STARTED`` would send every caller into a polling
  loop for a report that already exists, and it would need mutable state to ever finish
  — the one thing this emulator deliberately does not have.
* ``GetCredentialReport`` -> the CSV for the **calling account**, decoded from the
  caller's own access key the way ``sts.GetCallerIdentity`` does. The report is
  per-account, so reading the account from the request (rather than reporting the whole
  estate) keeps the emulator's one account-from-credential rule in the one place it
  already lives.

``authorization`` is threaded in rather than read from the raw request, so the whole
protocol path stays testable without HTTP.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from tools.synthetic_clouds.model.estate import CanonicalEstate

from aws_sim import query_xml
from aws_sim.api.cloudformation import (
    CODE_INVALID_ACTION,
    CODE_INVALID_PARAMETER,
    CODE_MISSING_PARAMETER,
    AwsApiError,
)
from aws_sim.projections import iam, sts

WIRE = query_xml.IAM

#: The report is ready from the first call; see the module docstring.
STATE_COMPLETE = "COMPLETE"

_ACTIONS: frozenset[str] = frozenset({"GenerateCredentialReport", "GetCredentialReport"})


def supported_actions() -> tuple[str, ...]:
    """The actions this slice answers, sorted. Used by tests and by ``InvalidAction``."""
    return tuple(sorted(_ACTIONS))


def account_for(estate: CanonicalEstate, authorization: str | None) -> str:
    """The account the request speaks for, decoded from its SigV4 credential."""
    access_key = sts.parse_access_key(authorization)
    account = sts.account_from_access_key(access_key) if access_key else None
    return account or iam.covered_account(estate, "")


def dispatch_form(
    estate: CanonicalEstate,
    region: str,
    form: Mapping[str, str],
    *,
    authorization: str | None,
) -> str:
    """Answer one IAM Query-protocol request, returning the XML body."""
    action = form.get("Action", "").strip()
    if not action:
        raise AwsApiError(CODE_MISSING_PARAMETER, "Action is required.")

    version = form.get("Version", "").strip()
    if version != WIRE.api_version():
        raise AwsApiError(
            CODE_INVALID_PARAMETER,
            f"Version {version!r} is not supported; expected {WIRE.api_version()!r}.",
        )

    account = account_for(estate, authorization)
    if action == "GenerateCredentialReport":
        result: dict[str, Any] = {
            "State": STATE_COMPLETE,
            "Description": (
                f"Credential report for account {account} is ready "
                f"({len(iam.users(estate, account))} user rows)."
            ),
        }
    elif action == "GetCredentialReport":
        result = iam.report(estate, account)
    else:
        raise AwsApiError(
            CODE_INVALID_ACTION,
            f"Action {action} is not served by the IAM simulator. Supported: {', '.join(supported_actions())}.",
        )

    return WIRE.render_result(action, result, f"synth-{uuid.uuid4().hex[:8]}")
