"""The STS projection: ``AssumeRole`` and ``GetCallerIdentity`` over the frozen estate.

Design decisions, each stated because a plausible-looking wrong one here would still pass
a shallow test:

* **The emulator is stateless.** A real STS keeps a session table; this one encodes the
  target account into the minted ``AccessKeyId`` and decodes it back from the caller's
  signed request. Two calls for the same role therefore cannot disagree, and there is no
  session store to leak or expire. The access key is ``ASIA`` + the 12-digit account + a
  fixed suffix (20 chars, the AWS shape), and ``GetCallerIdentity`` reads the account
  straight out of ``access_key[4:16]``.
* **The account comes from the ``RoleArn``**, ``arn:aws:iam::<account>:role/<name>`` —
  the only place a cross-account ``AssumeRole`` names its target.
* **A08 — a denied account.** ``AssumeRole`` refuses the configured account with a
  realistic ``AccessDenied``, so the surfaces that read ``connection_status='failed'``
  can be exercised. An account the estate does not own is refused the same way, because a
  role that does not exist is exactly what ``AccessDenied`` means to the caller.
* **The confused-deputy guard is the point of ``GetCallerIdentity``.** FinOps calls
  it with the *assumed* credentials and asserts the reported account matches the one it
  asked for; the decode is what makes that assertion pass instead of fail.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any

from tools.synthetic_clouds.model.estate import CanonicalEstate

from aws_sim import scope

#: AWS access-key-id shape: a 4-char prefix, 16 more chars. ``ASIA`` marks temporary
#: credentials (what ``AssumeRole`` returns), which is also what the guard expects.
ACCESS_KEY_PREFIX = "ASIA"
ACCESS_KEY_SUFFIX = "SYNT"  # noqa: S105 - a marker, not a credential
ACCESS_KEY_LENGTH = 20

DEFAULT_DURATION_SECONDS = 3600
MIN_DURATION_SECONDS = 900

#: The role FinOps assumes (``config.py:528``).
ROLE_SESSION_PREFIX = "FinOps-"

_ROLE_ARN = re.compile(r"^arn:aws:iam::(?P<account>\d{12}):role/(?P<name>[A-Za-z0-9+=,.@_/-]+)$")
#: SigV4: ``Credential=<access-key>/<date>/<region>/<service>/aws4_request``.
_CREDENTIAL = re.compile(r"Credential=(?P<access_key>[A-Za-z0-9]+)/")


class StsError(Exception):
    """Base for STS emulation errors; the router maps the code onto the XML envelope."""

    code = "ValidationError"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class AccessDeniedError(StsError):
    """The named role is not assumable — the realistic STS refusal."""

    code = "AccessDenied"


def account_from_role_arn(role_arn: str) -> str:
    """Return the 12-digit account named by ``role_arn``, or raise ``ValidationError``."""
    match = _ROLE_ARN.match((role_arn or "").strip())
    if match is None:
        raise StsError(f"RoleArn {role_arn!r} is not a valid IAM role ARN.")
    return match.group("account")


def access_key_for_account(account: str) -> str:
    """Mint the deterministic temporary access key id for ``account``."""
    return f"{ACCESS_KEY_PREFIX}{account}{ACCESS_KEY_SUFFIX}"


def account_from_access_key(access_key: str) -> str | None:
    """Decode ``account`` from a minted access key id, or ``None`` if it is not ours."""
    if len(access_key) != ACCESS_KEY_LENGTH or not access_key.startswith(ACCESS_KEY_PREFIX):
        return None
    account = access_key[len(ACCESS_KEY_PREFIX) : ACCESS_KEY_LENGTH - len(ACCESS_KEY_SUFFIX)]
    return account if account.isdigit() and len(account) == 12 else None


def parse_access_key(authorization: str | None) -> str | None:
    """Extract the access key id from a SigV4 ``Authorization`` header, if present."""
    if not authorization:
        return None
    match = _CREDENTIAL.search(authorization)
    return match.group("access_key") if match else None


def _now() -> datetime:
    return datetime.now(UTC)


def assume_role(
    estate: CanonicalEstate,
    *,
    role_arn: str,
    role_session_name: str,
    duration_seconds: int,
    denied_account: str,
) -> dict[str, Any]:
    """Return the ``AssumeRole`` result, or raise :class:`AccessDenied`."""
    account = account_from_role_arn(role_arn)
    if denied_account and account == denied_account:
        raise AccessDeniedError(
            f"User: arn:aws:iam::{account}:role/{ROLE_SESSION_PREFIX}... is not authorized "
            "to perform: sts:AssumeRole on resource: " + role_arn,
        )
    known = scope.scope_ids(estate)
    if account not in known:
        raise AccessDeniedError(
            "Not authorized to perform sts:AssumeRole: the role does not exist in "
            f"account {account}.",
        )

    duration = max(int(duration_seconds or DEFAULT_DURATION_SECONDS), MIN_DURATION_SECONDS)
    expiration = _now() + timedelta(seconds=duration)
    access_key = access_key_for_account(account)
    role_name = role_arn.rsplit("role/", 1)[-1]
    assumed_role_arn = f"arn:aws:sts::{account}:assumed-role/{role_name}/{role_session_name}"
    return {
        "Credentials": {
            "AccessKeyId": access_key,
            "SecretAccessKey": f"synthetic-secret-{account}",
            "SessionToken": f"synthetic-session-{account}",
            "Expiration": expiration,
        },
        "AssumedRoleUser": {
            "AssumedRoleId": f"AROASYNTH{account}:{role_session_name}",
            "Arn": assumed_role_arn,
        },
    }


def caller_identity(estate: CanonicalEstate, *, access_key: str | None, region: str) -> dict[str, Any]:
    """Return the ``GetCallerIdentity`` result for the request's access key.

    Falls back to the estate's first AWS account when the caller presents no decodable
    key (an unsigned smoke request), so the operation answers rather than failing on a
    detail the emulator cannot see.
    """
    account = account_from_access_key(access_key) if access_key else None
    if account is None:
        known = sorted(scope.scope_ids(estate))
        account = known[0] if known else "000000000000"
    return {
        "UserId": f"AROASYNTH{account}:session",
        "Account": account,
        "Arn": f"arn:aws:sts::{account}:assumed-role/{ROLE_SESSION_PREFIX}session/session",
    }
