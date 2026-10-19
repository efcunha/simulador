"""The RDS projection: ``DescribeDBInstances`` over the estate's RDS resources.

The estate records a **cost basis**, not a database configuration: ``sku_id`` names the
instance family and size (``aws-rds-db-m5-lg``) and nothing else describes the instance.
So the instance class is READ out of the SKU, and the attributes the model cannot carry
at all — engine, engine version, storage size, multi-AZ — are picked from small
AWS-native catalogs keyed on the resource's own uuid. The key is the point: a random or
clock-derived choice would make two calls for the same instance disagree, and FinOps
correlates those answers across a scan (and against the tagging API's ARNs).

What is deliberately **not** emitted:

* ``InstanceCreateTime`` comes from the resource's earliest billed day, the only
  timestamp the estate asserts about a resource, and is omitted for a resource the
  estate has never billed rather than filled with the sim's clock.
* ``VpcSecurityGroups`` / ``DBSubnetGroup`` are omitted: the estate models no VPC
  topology, and attaching "the account's security groups" to an instance would be a
  claim the model does not make.
* ``Filters`` is not applied — the emulator refuses it in ``api/rds.py`` instead, because
  a filter answered with unfiltered rows is worse than a refusal.

An identifier is the resource's own **derived AWS id** (``aws_sim.ids.resource_id`` — see
that module for why a scope-free id cannot be the name), so it is unique across the estate
even though one endpoint serves every account, and ``DBInstanceArn`` is built from that same
value: the id ``DescribeDBInstances`` answers, the ``DBInstanceIdentifier`` dimension the
CloudWatch shim keys this instance's CPU series by, and the ``ResourceARN`` the tagging API
reports are one value. The estate's ``resource_name`` stays what it is — the resource's
display name, projected as FOCUS ``ResourceName`` and not as an identifier.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.resource import Resource

from aws_sim import arns, ids, scope

RESOURCE_TYPE = "rds_instance"

STATUS_AVAILABLE = "available"
STORAGE_TYPE = "gp3"

#: ``sku_id`` -> the instance class it names. A closed map: the SKU catalog is the
#: generator's, so an unmapped SKU is a code change upstream, and a KeyError names it.
CLASSES_BY_SKU: dict[str, str] = {
    "aws-rds-db-m5-lg": "db.m5.large",
}

#: engine, engine version, listening port.
ENGINES: tuple[tuple[str, str, int], ...] = (
    ("postgres", "15.4", 5432),
    ("mysql", "8.0.35", 3306),
    ("aurora-postgresql", "15.4", 5432),
)

ALLOCATED_STORAGE_GB: tuple[int, ...] = (20, 100, 200)


def _bucket(key: str, count: int) -> int:
    """A stable catalog index for ``key`` (a resource uuid or a uuid-derived key)."""
    return int(arns.stable_digest(key, 8), 16) % count


def _instance(resource: Resource, created: datetime | None) -> dict[str, Any]:
    """One ``DBInstances`` entry for an estate RDS resource."""
    uuid = resource.identity.uuid
    identifier = ids.resource_id(resource)
    engine, engine_version, port = ENGINES[_bucket(uuid, len(ENGINES))]
    endpoint_host = f"{identifier}.{resource.region_id}.rds.amazonaws.com"
    row: dict[str, Any] = {
        "DBInstanceIdentifier": identifier,
        "DBInstanceArn": arns.resource_arn(resource),
        "DBInstanceClass": CLASSES_BY_SKU[resource.sku_id],
        "Engine": engine,
        "EngineVersion": engine_version,
        "DBInstanceStatus": STATUS_AVAILABLE,
        "AvailabilityZone": f"{resource.region_id}a",
        "Endpoint": {"Address": endpoint_host, "Port": port},
        "AllocatedStorage": ALLOCATED_STORAGE_GB[_bucket(f"{uuid}:storage", len(ALLOCATED_STORAGE_GB))],
        "StorageType": STORAGE_TYPE,
        "StorageEncrypted": True,
        "MultiAZ": _bucket(f"{uuid}:multiaz", 2) == 0,
        "PubliclyAccessible": False,
        "DeletionProtection": False,
        "TagList": [{"Key": key, "Value": value} for key, value in resource.tags],
    }
    if created is not None:
        row["InstanceCreateTime"] = created
    return row


def instances(estate: CanonicalEstate) -> tuple[dict[str, Any], ...]:
    """Every RDS instance the estate carries, ordered by identifier."""
    first_charge = scope.first_charge(estate)
    rows = [
        _instance(resource, first_charge.get(resource.identity.uuid))
        for resource in scope.resources(estate)
        if resource.resource_type == RESOURCE_TYPE
    ]
    return tuple(sorted(rows, key=lambda row: row["DBInstanceIdentifier"]))


def find(estate: CanonicalEstate, identifier: str) -> dict[str, Any] | None:
    """Resolve one instance by its identifier, or ``None``."""
    return next((row for row in instances(estate) if row["DBInstanceIdentifier"] == identifier), None)
