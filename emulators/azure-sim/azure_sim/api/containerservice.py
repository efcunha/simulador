"""Container Service resource plane: ``managedClusters`` and the resources list (Phase 6).

The read ``service_discovery.py (modulo do consumidor):393`` makes through
``ContainerServiceClient.managed_clusters.list()``.

**The api-version strings below could NOT be verified in this environment**: that package
is not installed here (``azure-mgmt-containerservice`` is imported lazily inside the
discovery function's ``try`` and is not a declared dependency of the backend), so unlike
the Compute/Network/SQL/Storage gates in this package they are not read off a client. They
are emitted as a small tolerance set of the stable versions the service has shipped, which
is what the ``TODO-verificar`` flag records; the catalogue row this belongs to is
``docs/synthetic-clouds/UNVERIFIED.md`` (Phase 6 — Azure resource plane), which lives
outside the package this change was scoped to. A wrong string here is not silent: the gate
answers the Azure 400 envelope and the caller's own per-provider ``except`` logs the
failure, so the tolerance set exists precisely so that an unverified guess cannot disable
AKS discovery on its own.

**The list the FinOps Kubernetes discovery reads is the ARM RESOURCES list, not the typed
one.** The discovery does not call ``managed_clusters.list()``: it calls the ARM resources
list and filters it by resource type --
``ResourceManagementClient.resources.list(filter="resourceType eq
'Microsoft.ContainerService/managedClusters'")`` builds

    GET /subscriptions/{subscriptionId}/resources
        ?$filter=resourceType eq 'Microsoft.ContainerService/managedClusters'
        &api-version=2025-04-01

and that is the request the discovery makes. The emulator had no route at that path, so
the request answered ``404`` and the discovery failed on it before a single row was read
(the deployed stack's simulator logged that path as ``404 Not Found`` and the backend
logged ``cluster_discovery_azure_error`` with ``(NotFound) Not Found``). This router now
serves it, with the estate's Azure Kubernetes Service clusters of the subscription the
caller asks under -- the rows the typed route already publishes, unchanged.

The surface is the official one: "Resources - List", Microsoft Learn, consulted
2026-10-27, https://learn.microsoft.com/en-us/rest/api/resources/resources/list --
``GET https://management.azure.com/subscriptions/{subscriptionId}/resources`` with the
optional ``$filter``/``$expand``/``$top`` query parameters, answered a
``ResourceListResult`` (``nextLink`` + ``value``). The ``$filter`` this surface reads is
the one the reference publishes for a resource type
(``$filter=resourceType eq 'Microsoft.Network/virtualNetworks'``).

**The filter is read, not ignored.** ARM's resources list accepts a family of filters; this
surface reads the one the discovery sends and refuses what it cannot apply. An ignored
filter is a wrong answer, and a wrong answer about a subscription's resources is a silence
that reads as "this account owns nothing" -- the failure this phase exists to remove.
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Request

from azure_sim.api.common import (
    CODE_INVALID_REQUEST,
    AzureApiError,
    get_estate,
    require_api_version,
    value_page,
)
from azure_sim.projections import arm
from azure_sim.projections.containerservice import project_managed_clusters
from azure_sim.projections.scope import resource_group_in_scope

router = APIRouter()

# TODO-verificar: NOT read off an installed client (azure-mgmt-containerservice is absent);
# stable versions of the managedClusters list, pending confirmation.
_MANAGED_CLUSTER_VERSIONS: frozenset[str] = frozenset({"2024-09-01", "2025-01-01"})

#: The api-version of the ARM resources list (``Microsoft.Resources``). ``2025-04-01`` is
#: read off the installed client: it is the version the ``azure-mgmt-resource`` package
#: sends for ``resources.list``. ``2021-04-01`` is the version the operation is documented
#: with -- "Resources - List", Microsoft Learn, consulted 2026-10-27 --
#: https://learn.microsoft.com/en-us/rest/api/resources/resources/list -- which publishes
#: ``GET https://management.azure.com/subscriptions/{subscriptionId}/resources
#: ?$filter={$filter}&$expand={$expand}&$top={$top}&api-version=2021-04-01`` and answers a
#: ``ResourceListResult`` (``nextLink`` + ``value``), the envelope this route serves. It is
#: kept as tolerance because an older client must not be answered with a 400 that reads as
#: "this simulator does not serve the list".
_RESOURCES_VERSIONS: frozenset[str] = frozenset({"2025-04-01", "2021-04-01"})

#: The filter this surface reads: the resource type the caller asks for. ARM compares the
#: type case-insensitively, so the comparison is too.
_RESOURCE_TYPE_FILTER = re.compile(
    r"^\s*resourceType\s+eq\s+'(?P<resource_type>[^']+)'\s*$",
    re.IGNORECASE,
)


def _requested_resource_type(request: Request) -> str | None:
    """The resource type the ``$filter`` names, or ``None`` when it names none.

    A filter this surface cannot read is refused (a 400 ARM envelope) rather than
    ignored: the caller asked a question the emulator cannot answer, and answering with
    rows the filter would have narrowed is an answer about a set the caller never asked
    for.
    """
    raw = request.query_params.get("$filter")
    if raw is None or not raw.strip():
        return None
    match = _RESOURCE_TYPE_FILTER.match(raw)
    if match is None:
        raise AzureApiError(
            400,
            code=CODE_INVALID_REQUEST,
            message=(f"This simulator reads a resourceType filter only; got {raw!r}."),
        )
    return match.group("resource_type")


@router.get("/{scope:path}/providers/Microsoft.ContainerService/managedClusters")
async def managed_clusters(request: Request, scope: str = "") -> dict[str, Any]:
    """Return ``managed_clusters.list`` rows for the scope (``{value:[...]}``).

    The scope narrows the answer: the subscription it names decides which clusters are
    served, and so does the resource group it names. Every subscription of the estate
    reuses every cluster name, so an unnarrowed answer would hand the caller another
    subscription's rows under its own id.
    """
    require_api_version(request, _MANAGED_CLUSTER_VERSIONS)
    return value_page(
        request,
        project_managed_clusters(
            get_estate(request),
            arm.subscription_in_scope(scope),
            resource_group_in_scope(scope),
        ),
    )


@router.get("/subscriptions/{subscription_id}/resources")
async def subscription_resources(request: Request, subscription_id: str) -> dict[str, Any]:
    """Return the ARM resources list the Kubernetes discovery reads (``{value:[...]}``).

    The subscription is named in either spelling -- the GUID the served ids carry or the
    estate's own scope label -- and a subscription the estate does not carry answers no
    row, which is what the list surfaces do for a scope they do not have.
    """
    require_api_version(request, _RESOURCES_VERSIONS)
    resource_type = _requested_resource_type(request)
    if resource_type is not None and resource_type.casefold() != arm.MANAGED_CLUSTER_TYPE.casefold():
        raise AzureApiError(
            400,
            code=CODE_INVALID_REQUEST,
            message=(
                f"This surface serves {arm.MANAGED_CLUSTER_TYPE} only; the emulator "
                "publishes the other providers' resources through their own typed list "
                f"routes. Got {resource_type!r}."
            ),
        )
    return value_page(
        request,
        project_managed_clusters(get_estate(request), subscription_id),
    )
