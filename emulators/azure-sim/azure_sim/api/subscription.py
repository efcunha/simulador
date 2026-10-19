"""Subscriptions resource manager: ``subscriptions.get`` (Phase 6).

The read ``connection_validator.py (modulo do consumidor):117`` makes before
anything else happens with an account. Unlike every other route in this package it is not
resource-scoped — the subscription is the scope — so it is served at
``/subscriptions/{subscriptionId}`` and takes no ``{scope:path}``.

The api-version is read off the installed ``azure-mgmt-subscription``
``build_subscriptions_get_request`` (``2016-06-01``) — the exact string the client
``connection_validator.py:38`` imports sends, which is why it looks older than the
resource-plane versions elsewhere. ``2022-12-01`` is accepted as well for a caller built on
``azure-mgmt-resource``'s own ``SubscriptionClient``; that second string is the one flagged
below as unverified offline.

An unknown subscription answers ARM's 404 envelope rather than an empty body, and the
stored id is never echoed back unchecked: a caller that misconfigured its subscription id
hears so from the read it uses to validate the connection.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from azure_sim.api.common import AzureApiError, get_estate, require_api_version
from azure_sim.projections.subscription import find_subscription

router = APIRouter()

#: ``2016-06-01`` read off the installed ``azure-mgmt-subscription`` operation builder (the
#: package ``connection_validator.py`` imports).
# TODO-verificar §11.7: ``2022-12-01`` (azure-mgmt-resource's SubscriptionClient) is not
# offline-verifiable here; the catalogue row for error codes/api-versions is §11.7.
_SUBSCRIPTION_VERSIONS: frozenset[str] = frozenset({"2016-06-01", "2022-12-01"})

# TODO-verificar §11.7: ARM's own code for "no such subscription", emitted as part of the
# shared ``{error:{code,message}}`` envelope whose code vocabulary that row covers.
CODE_SUBSCRIPTION_NOT_FOUND = "SubscriptionNotFound"


@router.get("/subscriptions/{subscription_id}")
async def subscriptions_get(request: Request, subscription_id: str) -> dict[str, Any]:
    """Return the subscription ``subscription_id`` names (``subscriptions.get``)."""
    require_api_version(request, _SUBSCRIPTION_VERSIONS)
    row = find_subscription(get_estate(request), subscription_id)
    if row is None:
        raise AzureApiError(
            404,
            code=CODE_SUBSCRIPTION_NOT_FOUND,
            message=f"The subscription '{subscription_id}' could not be found.",
        )
    return row
