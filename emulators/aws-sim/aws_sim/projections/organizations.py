"""The Organizations projection: the organization and its member accounts.

The estate models one AWS organization (``AwsOrg``) with its member accounts, which is
exactly what ``ListAccounts`` returns and what ``org_discovery.py`` consumes. The
management account is the first account in the org (deterministic).

``Name`` is the account's own name with the FinOps ``[SYNTH] `` marker stripped
(``render/markers.py::unmarked_name``). No real ``ListAccounts`` response carries a
simulator marker, and FinOps stores the served ``Name`` verbatim into
``cloud_accounts.name`` (``org_discovery.py (modulo do consumidor)``), so the marker belongs to
FinOps own storage and never to the cloud's field. The never-mix gate reads the
account's credential material rather than its name for the same reason
(``tools/synthetic_clouds/seed/workspace.py::_assert_no_real_rows``).

Records follow the Organizations wire shape: ``JoinedTimestamp`` is an **epoch seconds**
float (the JSON-1.1 timestamp form), not an ISO string.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.render.markers import FICTIONAL_DOMAIN, unmarked_name

STATUS_ACTIVE = "ACTIVE"
JOINED_METHOD = "INVITED"
FEATURE_SET_ALL = "ALL"


def _org(estate: CanonicalEstate) -> Any:
    return estate.aws_orgs[0] if estate.aws_orgs else None


def _joined_timestamp(estate: CanonicalEstate) -> float:
    """Epoch seconds for the sim's start day — the JSON-1.1 timestamp form."""
    return datetime.combine(estate.sim_start, datetime.min.time(), tzinfo=UTC).timestamp()


def master_account_id(estate: CanonicalEstate) -> str:
    """The management account id: the org's first account, deterministically."""
    org = _org(estate)
    return str(org.accounts[0].account_id) if org is not None and org.accounts else ""


def account_arn(estate: CanonicalEstate, account_id: str) -> str:
    """The account's organization ARN."""
    org = _org(estate)
    org_id = str(org.org_id) if org is not None else "o-synthetic"
    return f"arn:aws:organizations::{master_account_id(estate)}:account/{org_id}/{account_id}"


def account_email(account_id: str) -> str:
    """A fictional account email under ``contoso.example`` (NFR-3)."""
    return f"aws-{account_id}@{FICTIONAL_DOMAIN}"


def accounts(estate: CanonicalEstate) -> tuple[dict[str, Any], ...]:
    """One ``Accounts`` entry per member account."""
    org = _org(estate)
    if org is None:
        return ()
    joined = _joined_timestamp(estate)
    return tuple(
        {
            "Id": str(account.account_id),
            "Arn": account_arn(estate, str(account.account_id)),
            "Email": account_email(str(account.account_id)),
            # The account's own name: the FinOps marker is stripped at this export
            # boundary rather than served (see the module docstring).
            "Name": unmarked_name(str(account.name)),
            "Status": STATUS_ACTIVE,
            "JoinedMethod": JOINED_METHOD,
            "JoinedTimestamp": joined,
        }
        for account in org.accounts
    )


def find_account(estate: CanonicalEstate, account_id: str) -> dict[str, Any] | None:
    """Resolve one account by its 12-digit id."""
    for account in accounts(estate):
        if account["Id"] == account_id:
            return account
    return None


def organization_document(estate: CanonicalEstate) -> dict[str, Any]:
    """The ``DescribeOrganization`` result."""
    org = _org(estate)
    if org is None:
        return {}
    master = master_account_id(estate)
    return {
        "Organization": {
            "Id": str(org.org_id),
            "Arn": f"arn:aws:organizations::{master}:organization/{org.org_id}",
            "FeatureSet": FEATURE_SET_ALL,
            "MasterAccountArn": account_arn(estate, master),
            "MasterAccountId": master,
            "MasterAccountEmail": account_email(master),
        },
    }
