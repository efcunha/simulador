"""Cloud hierarchy entities (FR-A1).

Azure management group -> subscriptions; GCP org -> folders -> projects; AWS
organization -> accounts; two billing accounts per provider. The nesting is
explicit so Phase 2/3 inventory renderers can project the hierarchy without
re-deriving it. All identifiers are fictional under ``contoso.example`` (FR-A4);
account-like names carry the ``[SYNTH]`` marker (NFR-3).
"""

from __future__ import annotations

from dataclasses import dataclass

from tools.synthetic_clouds.model.identity import ResourceIdentity


@dataclass(slots=True, frozen=True)
class BillingAccount:
    """A provider billing account (Azure billing account / GCP billingAccounts/*)."""

    identity: ResourceIdentity
    provider: str  # azure | gcp | aws
    billing_account_id: str
    name: str  # "[SYNTH] ..." prefix (NFR-3)
    currency: str  # BillingCurrency / currency


@dataclass(slots=True, frozen=True)
class AzureSubscription:
    """An Azure subscription scoped to a billing account."""

    identity: ResourceIdentity
    subscription_id: str  # fictional GUID
    billing_account_id: str  # FK -> BillingAccount.billing_account_id
    name: str


@dataclass(slots=True, frozen=True)
class AzureMgmtGroup:
    """An Azure management group owning subscriptions."""

    identity: ResourceIdentity
    tenant_id: str  # fictional GUID under contoso.example
    name: str
    subscriptions: tuple[AzureSubscription, ...]


@dataclass(slots=True, frozen=True)
class GcpProject:
    """A GCP project scoped to a billing account."""

    identity: ResourceIdentity
    project_id: str  # fictional, e.g. "contoso-prod-1a2b"
    billing_account_id: str  # FK -> BillingAccount.billing_account_id
    name: str


@dataclass(slots=True, frozen=True)
class GcpFolder:
    """A GCP folder owning projects."""

    identity: ResourceIdentity
    folder_id: str  # folders/NNNN
    projects: tuple[GcpProject, ...]


@dataclass(slots=True, frozen=True)
class GcpOrg:
    """A GCP organization owning folders."""

    identity: ResourceIdentity
    org_id: str  # organizations/NNNN (fictional)
    domain: str  # "contoso.example"
    folders: tuple[GcpFolder, ...]


@dataclass(slots=True, frozen=True)
class AwsAccount:
    """An AWS account scoped to a billing account.

    ``account_id`` is the 12-digit FOCUS ``SubAccountId``, minted by
    ``identity.aws_account_id`` so the renderer and the seed-side callers share
    one source of truth.
    """

    identity: ResourceIdentity
    account_id: str  # 12-digit, synthetic (leading 9 band)
    billing_account_id: str  # FK -> BillingAccount.billing_account_id
    name: str


@dataclass(slots=True, frozen=True)
class AwsOrg:
    """An AWS organization owning accounts.

    Models the ``organizations:ListAccounts`` topology the payer/member
    credential chain consumes. There is no folder level: AWS Organizations does
    have OUs, but nothing in FinOps AWS path reads them, and inventing a
    level no consumer projects would be fidelity theatre.
    """

    identity: ResourceIdentity
    org_id: str  # o-XXXXXXXXXX (fictional)
    accounts: tuple[AwsAccount, ...]
