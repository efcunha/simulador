"""The IAM projection: the account credential report, built from the estate's findings.

IAM users do not exist in the canonical model, and the emulator will not invent a user
list — so the report is derived from the one identity-shaped signal the estate does
carry: **IAM-category findings**, which the C09 scenario emits ("admin without MFA
finding"). One row per IAM finding, named after the resource the finding sits on, so
every row in the CSV traces back to an estate row a reviewer can point at.

The mapping from finding to report row, stated because it is an interpretation:

* the finding's **severity** is what decides MFA. ``HIGH``/``CRITICAL`` IAM findings are
  the case C09 describes, so they become console users with ``mfa_active=false``; lower
  severities become MFA-enabled users. The report's violations are therefore a function
  of the estate's own severities rather than of a coin flip.
* ``password_enabled`` is always ``true``: the console access an IAM control has to
  answer for is exactly what a finding against a resource stands for, and a report of
  only-``not_supported`` rows would erase the estate's signal.

A row is keyed by the resource's ``resource_name`` **inside one account**, and that is not
the scope-free-name hazard the other projections carry (``aws_sim.ids``): the report is
requested for one account and the estate names each resource once per scope
(``generate/estate_builder.py`` restarts its counter for every account), so two rows can only
merge if two resources of one account share a name — which the generator's per-scope counter
makes impossible. Indeed IAM user names are account-scoped in AWS for the same reason, and
the ``arn:aws:iam::<account>:user/<name>`` this report publishes carries the account.

The CSV is written by hand rather than through ``csv``: the header and the row shape are
copied from the report AWS emits, no value contains a comma, and ``csv`` would quote
anything it thought needed quoting — which FinOps line-splitting reader would then
read as a different column. Columns a row does not set are written as ``not_supported``,
which is also AWS's own word for them.
"""

from __future__ import annotations

import base64
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from tools.synthetic_clouds.model.estate import CanonicalEstate

from aws_sim import scope

#: The report's column set, in AWS's order. FinOps reads ``user``, ``arn``,
#: ``password_enabled`` and ``mfa_active``; the rest is filled the way AWS fills it for a
#: user that has only console access and no keys.
HEADER: tuple[str, ...] = (
    "user",
    "arn",
    "user_creation_time",
    "password_enabled",
    "password_last_used",
    "password_last_changed",
    "password_next_rotation",
    "mfa_active",
    "access_key_1_active",
    "access_key_1_last_rotated",
    "access_key_1_last_used_date",
    "access_key_1_last_used_region",
    "access_key_1_last_used_service",
    "access_key_2_active",
    "access_key_2_last_rotated",
    "access_key_2_last_used_date",
    "access_key_2_last_used_region",
    "access_key_2_last_used_service",
    "cert_1_active",
    "cert_1_last_rotated",
    "cert_2_active",
    "cert_2_last_rotated",
    "root_account_mfa_enabled",
)

NOT_SUPPORTED = "not_supported"
NO_INFORMATION = "no_information"
NOT_AVAILABLE = "N/A"

ROOT_USER = "<root_account>"

#: Severities that stand for the C09 "admin without MFA" case.
MFA_VIOLATION_SEVERITIES: frozenset[str] = frozenset({"HIGH", "CRITICAL"})

REPORT_FORMAT = "text/csv"


@dataclass(frozen=True, slots=True)
class ReportUser:
    """One credential-report row derived from an IAM finding."""

    name: str
    arn: str
    created: date
    mfa_active: bool


def covered_account(estate: CanonicalEstate, account: str) -> str:
    """The account the report covers: the caller's, or the estate's first as a fallback.

    The same fallback ``sts.caller_identity`` uses, for the same reason: an unsigned
    smoke request still has to reach an answer, and the estate's first account is a
    deterministic one to reach.
    """
    known = scope.scope_ids(estate)
    if account in known:
        return account
    return min(known) if known else "000000000000"


def user_arn(account: str, name: str) -> str:
    """The IAM user ARN FinOps stores as an IAM finding's ``resource_id``."""
    return f"arn:aws:iam::{account}:user/{name}"


def users(estate: CanonicalEstate, account: str) -> tuple[ReportUser, ...]:
    """The report's user rows: one per IAM finding on a resource of ``account``.

    A resource with several IAM findings appears once, and the row keeps the harshest
    verdict: the report is about users, and a user is not less without MFA because
    another finding about it is milder.
    """
    index = scope.resource_index(estate)
    by_name: dict[str, ReportUser] = {}
    for finding in estate.findings:
        if finding.provider != scope.PROVIDER or finding.category != "IAM":
            continue
        resource = index.get(finding.resource_uuid)
        if resource is None or resource.parent_scope_id != account:
            continue
        existing = by_name.get(resource.resource_name)
        if existing is not None and not existing.mfa_active:
            continue
        by_name[resource.resource_name] = ReportUser(
            name=resource.resource_name,
            arn=user_arn(account, resource.resource_name),
            created=finding.raised_on,
            mfa_active=finding.severity not in MFA_VIOLATION_SEVERITIES,
        )
    return tuple(by_name[name] for name in sorted(by_name))


def generated_time(estate: CanonicalEstate) -> datetime:
    """The report's ``GeneratedTime``: the estate's own clock, not the host's.

    The estate is frozen. A wall-clock timestamp would make two calls for the same
    report disagree, and a caller that stores ``GeneratedTime`` would see the report age
    with the emulator's host instead of with the data it describes.
    """
    now = estate.sim_now
    return datetime(now.year, now.month, now.day, tzinfo=UTC)


def _created_text(created: date) -> str:
    """A report timestamp: the AWS report writes them as ``YYYY-MM-DDTHH:MM:SS+00:00``."""
    return datetime(created.year, created.month, created.day, tzinfo=UTC).isoformat()


def _root_row(account: str) -> dict[str, str]:
    """The report's first row, always the account root rather than a resource-derived one."""
    return {
        "user": ROOT_USER,
        "arn": f"arn:aws:iam::{account}:root",
        "mfa_active": "true",
        "root_account_mfa_enabled": "true",
    }


def _user_row(user: ReportUser) -> dict[str, str]:
    created = _created_text(user.created)
    return {
        "user": user.name,
        "arn": user.arn,
        "user_creation_time": created,
        "password_enabled": "true",
        "password_last_used": NO_INFORMATION,
        "password_last_changed": created,
        "mfa_active": "true" if user.mfa_active else "false",
        "access_key_1_active": "false",
        "access_key_1_last_rotated": NOT_AVAILABLE,
        "access_key_1_last_used_date": NO_INFORMATION,
        "access_key_1_last_used_region": NO_INFORMATION,
        "access_key_1_last_used_service": NO_INFORMATION,
        "access_key_2_active": "false",
        "access_key_2_last_rotated": NOT_AVAILABLE,
        "access_key_2_last_used_date": NO_INFORMATION,
        "access_key_2_last_used_region": NO_INFORMATION,
        "access_key_2_last_used_service": NO_INFORMATION,
        "cert_1_active": "false",
        "cert_1_last_rotated": NOT_AVAILABLE,
        "cert_2_active": "false",
        "cert_2_last_rotated": NOT_AVAILABLE,
    }


def _line(values: Mapping[str, str]) -> str:
    """One CSV line, with every column the row left out written as ``not_supported``."""
    return ",".join(values.get(column, NOT_SUPPORTED) for column in HEADER)


def credential_report_csv(estate: CanonicalEstate, account: str) -> str:
    """The credential report for ``account``, as the CSV text AWS returns.

    The header row is not decoration: FinOps reader takes ``lines[0]`` as the column
    index, so a report without it would be read as a report with one bogus user.
    """
    covered = covered_account(estate, account)
    rows = [
        ",".join(HEADER),
        _line(_root_row(covered)),
        *(_line(_user_row(user)) for user in users(estate, covered)),
    ]
    return "\n".join(rows) + "\n"


def report(estate: CanonicalEstate, account: str) -> dict[str, Any]:
    """The ``GetCredentialReport`` result, with ``Content`` base64-encoded.

    The Query protocol carries a blob member base64-encoded, which is what botocore's
    blob parser decodes back to bytes — the bytes FinOps ``.decode("utf-8")``
    expects.
    """
    content = credential_report_csv(estate, account).encode("utf-8")
    return {
        "Content": base64.b64encode(content).decode("ascii"),
        "ReportFormat": REPORT_FORMAT,
        "GeneratedTime": generated_time(estate),
    }
