"""The provider boundary for every azure-sim projection and export.

azure-sim consumes the **multi-cloud** canonical estate, and each surface must answer
with its own provider's rows. That convention already holds on the renderer side —
``render/gcp_rest_fixtures.py:39,140,168`` and ``render/focus_azure.py:120`` both
filter, the latter with the leak it prevents written down — but the runtime
projections did not, so ``/providers/Microsoft.ResourceGraph/resources`` and
``/providers/Microsoft.Security/assessments`` returned Azure, GCP **and** AWS rows.
An Azure screen showing an AWS EC2 instance is the owner's fidelity requirement
inverted, and this is the one module that owns the boundary so a new projection cannot
forget it.

Filtering rules, each chosen because that is where the provider actually lives on the
model:

* resources carry ``ResourceIdentity.provider`` (the operational key, lowercase);
* findings and recommendations carry their own ``provider`` string;
* inventory assets carry **no** provider — they are keyed by ``resource_uuid``, so
  they are scoped through the resource index rather than by a field of their own;
* billing lines carry the FOCUS ``service_provider_name`` (``Microsoft Azure``), which
  is a different vocabulary from the operational key — the same two-axis distinction
  ``generate/constants.py:90-112`` documents.
"""

from __future__ import annotations

from tools.synthetic_clouds.generate.constants import PROVIDER_AZURE
from tools.synthetic_clouds.model.billing import BillingLine
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.iac import InventoryAsset
from tools.synthetic_clouds.model.identity import azure_subscription_guid
from tools.synthetic_clouds.model.metrics import MetricSeries
from tools.synthetic_clouds.model.native import NativeFinding, NativeRecommendation
from tools.synthetic_clouds.model.resource import Resource

#: The operational provider key (``ResourceIdentity.provider``), lowercase.
PROVIDER = "azure"


def resource_index(estate: CanonicalEstate) -> dict[str, Resource]:
    """Map this provider's resource uuid -> Resource."""
    return {r.identity.uuid: r for r in estate.resources if r.identity.provider == PROVIDER}


def resource_uuids(estate: CanonicalEstate) -> frozenset[str]:
    """The uuid set every provider-scoped projection filters against."""
    return frozenset(resource_index(estate))


def resources(estate: CanonicalEstate) -> tuple[Resource, ...]:
    """This provider's resources, in estate order."""
    return tuple(r for r in estate.resources if r.identity.provider == PROVIDER)


def of_type(estate: CanonicalEstate, resource_type: str) -> tuple[Resource, ...]:
    """This provider's resources of ONE ``resource_type``, ordered by name.

    The resource-plane services (compute, containerservice, sql, storage, web) each
    answer one or two ``resource_type`` values, and the provider filter is the part that
    must not be forgotten — so the type filter is applied HERE, on top of
    :func:`resources`, instead of being re-derived in every new projection. The
    ``resource_type`` vocabularies happen not to overlap across providers today, which is
    exactly why a missing provider filter would be invisible: the rows would look right.

    Ordered by ``resource_name`` (the estate's own name for the row) so a type's rows are
    stable across calls; the sort is stable, so estate order breaks ties between the
    scopes that reuse a name (``generate/estate_builder.py:292`` restarts its counter per
    scope, so ``virtual_machine-0000`` exists in more than one subscription).
    """
    return tuple(
        sorted(
            (r for r in resources(estate) if r.resource_type == resource_type),
            key=lambda r: r.resource_name,
        )
    )


def subscription_label(estate: CanonicalEstate, subscription_id: str) -> str | None:
    """The estate's scope label for a subscription id, or ``None``.

    Both spellings of a subscription are accepted: the GUID the served ids carry
    (``identity.azure_subscription_guid``) and the generator's own scope label
    (``sub-01``). That is the alias rule ``projections/subscription.py`` and
    ``projections/sql.py`` already follow, so a request built either way is answered
    rather than silently emptied -- and the caller never has to know which spelling
    the estate keeps its keys under.

    ``None`` means the estate carries no such subscription: a request for one answers
    nothing, which is what the list surfaces do for a scope the estate does not have.

    The GUID is minted here rather than read through ``arm.subscription_id`` because
    ``projections/arm.py`` imports THIS module: importing it back would close a cycle.
    """
    for group in estate.azure_mgmt_groups:
        for subscription in group.subscriptions:
            if subscription_id in (
                subscription.subscription_id,
                azure_subscription_guid(estate.seed, subscription.subscription_id),
            ):
                return subscription.subscription_id
    return None


def resource_group_in_scope(scope: str) -> str | None:
    """The resource group a request scope names, or ``None`` when it names none.

    Mirrors ``arm.subscription_in_scope``: the scope arrives as a path string, and the
    segment after ``resourceGroups`` is the group. Empty segments are dropped, so a
    doubled or trailing slash cannot shift the answer, and the comparison is
    case-insensitive because ARM paths are.
    """
    segments = [segment for segment in scope.split("/") if segment]
    for index, segment in enumerate(segments):
        if segment.lower() == "resourcegroups" and index + 1 < len(segments):
            return segments[index + 1]
    return None


def inventory(estate: CanonicalEstate) -> tuple[tuple[InventoryAsset, Resource | None], ...]:
    """This provider's inventory assets paired with their resource.

    Inventory assets have no provider field: an asset belongs to whichever provider
    owns its ``resource_uuid``. Pairing here keeps that indirection in one place
    instead of repeating ``index.get(...)`` in every projection.
    """
    index = resource_index(estate)
    return tuple(
        (asset, index.get(asset.resource_uuid))
        for asset in estate.inventory
        if asset.resource_uuid in index
    )


def findings(estate: CanonicalEstate) -> tuple[NativeFinding, ...]:
    """This provider's native findings."""
    return tuple(f for f in estate.findings if f.provider == PROVIDER)


def recommendations(estate: CanonicalEstate) -> tuple[NativeRecommendation, ...]:
    """This provider's native recommendations."""
    return tuple(r for r in estate.recommendations if r.provider == PROVIDER)


def metric_series(estate: CanonicalEstate) -> tuple[MetricSeries, ...]:
    """This provider's metric series.

    A series points at a resource, not at a provider, so it is scoped through the
    resource index — the estate meters GCP compute/SQL resources with the same
    ``cpu_utilization`` series name an Azure VM carries.
    """
    owned = resource_uuids(estate)
    return tuple(s for s in estate.metrics if s.resource_uuid in owned)


def billing_lines(estate: CanonicalEstate) -> tuple[BillingLine, ...]:
    """This provider's billing lines, matched on the FOCUS provider name."""
    return tuple(line for line in estate.billing_lines if line.service_provider_name == PROVIDER_AZURE)
