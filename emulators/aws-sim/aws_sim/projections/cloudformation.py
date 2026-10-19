"""The CloudFormation drift projection: stacks, their resources, and the drift input.

Everything here is **derived from the estate**, and the derivation is the one the
canonical model already documents (``model/iac.py``): *a resource that is in inventory
but absent from the IaC snapshot is the drift INPUT*. FinOps computes the drift
verdict from it (P1, FR-18) — this module never emits a verdict of its own, it emits
what CloudFormation would say about the resources.

Mapping decisions, each stated because a wrong one here would look plausible:

* **A stack is an AWS account.** The estate's ``IacStateSnapshot.scope_id`` groups
  resources exactly the way a stack groups its declared resources, and it is the only
  grouping the generator produces. One snapshot per account ⇒ one stack per account.
* **The stack's region** is the lowest ``region_id`` among its resources: deterministic,
  and honest about the estate spanning regions per account rather than pretending to a
  per-stack region the model does not have.
* ``ExpectedProperties`` is the **declared** config and ``ActualProperties`` the
  **observed** one, both serialized as JSON **strings** — the verified wire type
  (design sec. 22.2). Emitting objects would be parsed as garbage.
* ``ActualProperties`` is built from the **estate resource** (:func:`resource_properties`):
  a drift row reports the resource's own properties, so every value is an attribute
  ``model/resource.py`` really carries and an attribute the estate does not model is simply
  absent. ``InventoryAsset.config_json`` is deliberately **not** projected: it is the
  FinOps marker bag (``markers.synthetic_metadata``: ``{"synthetic": true, "region":
  …}``), and a ``synthetic`` key inside a CloudFormation property blob is exactly the
  invented field the fidelity requirement forbids.
* ``StackResourceDriftStatus`` is ``IN_SYNC`` for a resource the snapshot declares and
  ``MODIFIED`` for one it does not. CloudFormation's fourth value, ``DELETED``, is
  unreachable here because estate inventory is 1:1 with resources, so it is not
  implemented rather than left as dead code.
* ``NextToken`` is not emitted: these operations return one page, and the paginators
  FinOps uses treat an absent token as the end. Recorded so a future second page is
  a deliberate change.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.resource import Resource

from aws_sim import scope

#: Stack name prefix. Every synthetic artefact carries a marker (NFR-3) and a stack name
#: is the one identifier a human reads in the CloudFormation console.
STACK_NAME_PREFIX = "synth-"

DRIFT_IN_SYNC = "IN_SYNC"
DRIFT_MODIFIED = "MODIFIED"

DETECTION_COMPLETE = "DETECTION_COMPLETE"
STACK_DRIFTED = "DRIFTED"
STACK_STATUS_CREATE_COMPLETE = "CREATE_COMPLETE"
RESOURCE_STATUS_CREATE_COMPLETE = "CREATE_COMPLETE"
#: CloudFormation's own sentinel for a stack that has never been checked.
STACK_DRIFT_NOT_CHECKED = "NOT_CHECKED"


@dataclass(frozen=True, slots=True)
class ResourceDrift:
    """One resource as CloudFormation sees it, with its declared/observed configs."""

    logical_id: str
    physical_id: str
    resource_type: str
    status: str
    expected: dict[str, Any]
    actual: dict[str, Any]
    timestamp: datetime

    @property
    def differences(self) -> list[dict[str, Any]]:
        """Property-level differences over keys both sides declare.

        Derived rather than authored: a key absent from either side is not a property
        difference, it is a shape difference, and inventing one would put a value in
        FinOps drift screen that nothing in the estate supports.
        """
        rows: list[dict[str, Any]] = []
        for key in sorted(set(self.expected) & set(self.actual)):
            if self.expected[key] != self.actual[key]:
                rows.append(
                    {
                        "PropertyPath": key,
                        "ExpectedValue": json.dumps(self.expected[key], sort_keys=True),
                        "ActualValue": json.dumps(self.actual[key], sort_keys=True),
                        "DifferenceType": "NOT_EQUAL",
                    },
                )
        return rows


@dataclass(frozen=True, slots=True)
class Stack:
    """One synthetic CloudFormation stack, derived from an AWS account's IaC snapshot."""

    snapshot_id: str
    account_id: str
    name: str
    arn: str
    region: str
    created: datetime
    resources: tuple[ResourceDrift, ...]

    @property
    def drifted(self) -> tuple[ResourceDrift, ...]:
        return tuple(r for r in self.resources if r.status != DRIFT_IN_SYNC)

    @property
    def drift_status(self) -> str:
        return STACK_DRIFTED if self.drifted else DRIFT_IN_SYNC


def _stack_name(account_id: str) -> str:
    return f"{STACK_NAME_PREFIX}{account_id}"


def _stack_arn(region: str, account_id: str, name: str, snapshot_id: str) -> str:
    return f"arn:aws:cloudformation:{region}:{account_id}:stack/{name}/{snapshot_id}"


def resource_properties(resource: Resource) -> dict[str, Any]:
    """The ``ActualProperties`` bag a drift row reports for an estate resource.

    CloudFormation reports the **resource's own** properties, so this is derived from the
    estate's ``Resource`` and nothing else: the type, the resource's ``sku_id``, its region
    (id and name) and its real ``(key, value)`` tag pairs in AWS's ``Tags`` wire shape.

    Every attribute the canonical model does not carry is left out rather than filled in —
    the estate records no network, no image id and no runtime configuration, so a bag with
    those keys would be FinOps reading its own invention back as the resource's state.

    ``InventoryAsset.config_json`` is not used here on purpose: it holds
    ``synthetic_metadata`` (``{"synthetic": true, "region": …}``), FinOps own marker
    bag, and no real ``DescribeStackResourceDrifts`` answer contains a ``synthetic`` key.
    """
    return {
        "resource_type": resource.resource_type,
        "sku_id": resource.sku_id,
        "region_id": resource.region_id,
        "region_name": resource.region_name,
        "tags": [{"Key": key, "Value": value} for key, value in resource.tags],
    }


def _build_resources(
    snapshot_states: dict[str, dict[str, Any]],
    asset_types: dict[str, str],
    resources: dict[str, Resource],
    captured_at: datetime,
) -> tuple[ResourceDrift, ...]:
    # ``LogicalResourceId`` is a TEMPLATE-level name and a stack is per account, so the
    # estate's reused ``resource_name`` is not the scope-free-id hazard the Describe
    # projections carry (``aws_sim.ids``): a stack holds one account's resources and that
    # account names each of them once. ``PhysicalResourceId`` is the estate's own uuid, which
    # is what the drift store keys on and the one identity the estate vouches for without
    # inventing an AWS id.
    rows: list[ResourceDrift] = []
    for uuid, resource in sorted(resources.items(), key=lambda item: item[1].resource_name):
        declared = snapshot_states.get(uuid)
        rows.append(
            ResourceDrift(
                logical_id=resource.resource_name,
                physical_id=uuid,
                resource_type=asset_types.get(uuid, resource.resource_type),
                status=DRIFT_IN_SYNC if declared is not None else DRIFT_MODIFIED,
                expected=dict(declared or {}),
                actual=resource_properties(resource),
                timestamp=captured_at,
            ),
        )
    return tuple(rows)


def stacks(estate: CanonicalEstate, region: str) -> tuple[Stack, ...]:
    """Return one stack per AWS account with an IaC snapshot, ordered by name."""
    # Only the asset's own type is read off the inventory: its ``config_json`` is a
    # FinOps marker bag and never reaches a CloudFormation property blob.
    asset_types: dict[str, str] = {
        asset.resource_uuid: asset.asset_type
        for asset, resource in scope.inventory(estate)
        if resource is not None
    }

    resources_by_scope: dict[str, dict[str, Resource]] = {}
    for resource in scope.resources(estate):
        resources_by_scope.setdefault(resource.parent_scope_id, {})[resource.identity.uuid] = resource

    built: list[Stack] = []
    for snapshot in scope.iac_snapshots(estate):
        owned = resources_by_scope.get(snapshot.scope_id, {})
        if not owned:
            # A snapshot with no resources of this provider cannot be a stack; skipping
            # is correct rather than emitting an empty one the caller would have to
            # filter.
            continue
        declared = {state.resource_uuid: state.declared_config for state in snapshot.resource_states}
        stack_region = min(resource.region_id for resource in owned.values()) or region
        name = _stack_name(snapshot.scope_id)
        built.append(
            Stack(
                snapshot_id=snapshot.snapshot_id,
                account_id=snapshot.scope_id,
                name=name,
                arn=_stack_arn(stack_region, snapshot.scope_id, name, snapshot.snapshot_id),
                region=stack_region,
                created=snapshot.captured_at,
                resources=_build_resources(declared, asset_types, owned, snapshot.captured_at),
            ),
        )
    return tuple(sorted(built, key=lambda stack: stack.name))


def find_stack(estate: CanonicalEstate, region: str, name_or_arn: str) -> Stack | None:
    """Resolve a ``StackName`` argument, which FinOps may pass as a name or an ARN."""
    for stack in stacks(estate, region):
        if name_or_arn in (stack.name, stack.arn, stack.snapshot_id):
            return stack
    return None


def stack_by_detection_id(estate: CanonicalEstate, region: str, detection_id: str) -> Stack | None:
    """Resolve a ``StackDriftDetectionId``.

    The estate is frozen, so detection is instantaneous and the id is the snapshot's own
    uuid: ``DescribeStackDriftDetectionStatus`` then needs no mutable state, and two
    calls for the same stack cannot disagree.
    """
    for stack in stacks(estate, region):
        if stack.snapshot_id == detection_id:
            return stack
    return None


def stack_summary(stack: Stack) -> dict[str, Any]:
    """One ``StackSummaries`` entry for ``ListStacks``."""
    return {
        "StackId": stack.arn,
        "StackName": stack.name,
        "StackStatus": STACK_STATUS_CREATE_COMPLETE,
        "CreationTime": stack.created,
        "LastUpdatedTime": stack.created,
        "DriftInformation": {
            "StackDriftStatus": stack.drift_status,
            "LastCheckTimestamp": stack.created,
        },
    }


def drift_detection_status(stack: Stack) -> dict[str, Any]:
    """The ``DescribeStackDriftDetectionStatus`` result for ``stack``.

    ``DETECTION_COMPLETE`` on the first poll is the honest answer for a frozen estate —
    there is nothing to wait for — and it is what the caller's poll loop terminates on.
    """
    return {
        "StackId": stack.arn,
        "StackDriftDetectionId": stack.snapshot_id,
        "StackDriftStatus": stack.drift_status,
        "DetectionStatus": DETECTION_COMPLETE,
        "DriftedStackResourceCount": len(stack.drifted),
        "Timestamp": stack.created,
    }


def resource_drift_row(stack: Stack, drift: ResourceDrift) -> dict[str, Any]:
    """One ``StackResourceDrifts`` entry.

    ``ExpectedProperties``/``ActualProperties`` are JSON **strings** (design sec. 22.2).
    """
    row: dict[str, Any] = {
        "StackId": stack.arn,
        "LogicalResourceId": drift.logical_id,
        "PhysicalResourceId": drift.physical_id,
        "ResourceType": drift.resource_type,
        "ExpectedProperties": json.dumps(drift.expected, sort_keys=True),
        "ActualProperties": json.dumps(drift.actual, sort_keys=True),
        "StackResourceDriftStatus": drift.status,
        "Timestamp": drift.timestamp,
    }
    differences = drift.differences
    if differences:
        row["PropertyDifferences"] = differences
    return row


def stack_resource_summary(stack: Stack, drift: ResourceDrift) -> dict[str, Any]:
    """One ``StackResourceSummaries`` entry for ``ListStackResources``."""
    return {
        "LogicalResourceId": drift.logical_id,
        "PhysicalResourceId": drift.physical_id,
        "ResourceType": drift.resource_type,
        "LastUpdatedTimestamp": drift.timestamp,
        "ResourceStatus": RESOURCE_STATUS_CREATE_COMPLETE,
        "DriftInformation": {
            "StackResourceDriftStatus": drift.status,
            "LastCheckTimestamp": drift.timestamp,
        },
    }
