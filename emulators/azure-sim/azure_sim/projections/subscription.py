"""Azure subscriptions: ``subscriptions.get`` (Phase 6).

This is the first Azure read FinOps makes about an account:
``connection_validator.py (modulo do consumidor):117`` calls
``subscriptions.get(subscription_id)`` and keeps ``subscription.display_name`` as the
account's name, failing the connection when the call does not answer. It is also the one
projection here that needs no provider filter, because the entity it projects
(``AzureMgmtGroup.subscriptions``, ``model/hierarchy.py:29``) exists only for Azure — the
multi-cloud estate cannot leak into rows whose source type is Azure-only.

``id`` and ``subscriptionId`` are the GUID ``identity.azure_subscription_guid`` mints from
the scope label: the id the caller holds is the one its cost rows are keyed on, and that is
the FOCUS ``SubAccountId`` the same function stamps (``render/focus_azure.py:117``,
``model/hierarchy.py:33``). The label itself (``sub-01``) is the generator's internal scope
key; :func:`find_subscription` accepts it too, so either spelling answers, but the two
served ids are never a label.

``state`` is ``Enabled`` — Azure's vocabulary, and the read of an estate whose subscriptions
are all in use. ``authorizationSource`` and ``subscriptionPolicies`` are left out: the
estate records no authorization model and no placement policy, and a value there would be
read as configuration.

``displayName`` is the subscription's own name with the FinOps ``[SYNTH] `` marker
stripped (``markers.unmarked_name``). That prefix is FinOps **storage** discriminator
— ``seed/cleanup.py`` recognises the seed's own ``cloud_accounts`` rows by
``name LIKE '[SYNTH] %'`` — so it stays on the canonical estate and on everything written
into FinOps database. A cloud export is not that storage: a real
``subscriptions.get`` returns the subscription's own display name and never a simulator
marker, and the validator that reads this row keeps it as the account's name. The same rule
``render/focus_azure.py:152`` applies to ``BillingAccountName``/``SubAccountName``.
"""

from __future__ import annotations

from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.hierarchy import AzureSubscription
from tools.synthetic_clouds.render.markers import unmarked_name

from azure_sim.projections import arm

#: Azure's state vocabulary for a subscription that is in use (the alternatives are
#: Warned/PastDue/Disabled, none of which the estate can express).
SUBSCRIPTION_STATE_ENABLED = "Enabled"


def _subscription_row(estate: CanonicalEstate, subscription: AzureSubscription) -> dict[str, object]:
    """One ``subscriptions.get`` row for an estate subscription."""
    served = arm.subscription_id(estate, subscription.subscription_id)
    return {
        "id": f"/subscriptions/{served}",
        "subscriptionId": served,
        # The subscription's own name: the FinOps marker is stripped at this export
        # boundary rather than served (see the module docstring).
        "displayName": unmarked_name(subscription.name),
        "state": SUBSCRIPTION_STATE_ENABLED,
    }


def project_subscriptions(estate: CanonicalEstate) -> list[dict[str, object]]:
    """Return every Azure subscription the estate carries, ordered by subscription id."""
    rows = [
        _subscription_row(estate, subscription)
        for group in estate.azure_mgmt_groups
        for subscription in group.subscriptions
    ]
    return sorted(rows, key=lambda row: str(row["subscriptionId"]))


def find_subscription(
    estate: CanonicalEstate,
    subscription_id: str,
) -> dict[str, object] | None:
    """The subscription ``subscription_id`` names, or ``None`` if the estate has none.

    Both spellings of a subscription are accepted on lookup — the GUID the served ids carry
    (what a configured CloudAccount holds) and the generator's own scope label (the value
    in ``Resource.parent_scope_id``, which a hand-built request may carry).

    ``None`` rather than a placeholder row, so the router can answer the 404 ARM answers for
    a subscription it does not know: a synthesized row would be read by a caller as a real
    subscription with an empty name, which is how a misconfigured account stops looking
    misconfigured.
    """
    for group in estate.azure_mgmt_groups:
        for subscription in group.subscriptions:
            if subscription_id in {
                subscription.subscription_id,
                arm.subscription_id(estate, subscription.subscription_id),
            }:
                return _subscription_row(estate, subscription)
    return None
