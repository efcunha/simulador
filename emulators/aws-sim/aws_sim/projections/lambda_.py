"""The Lambda projection: ``ListFunctions`` over the estate's function resources.

``ListFunctions`` answers with a ``FunctionConfiguration`` per function. The estate
carries a name, a region, an account, a SKU and tags — so the projection reports what it
can derive and leaves the rest out rather than filling a configuration nobody could
verify:

* ``Runtime`` and ``MemorySize`` come from small AWS-native catalogs keyed on the
  resource's own uuid. The SKU (``aws-lambda-gb-second``) is a price basis, not a
  configuration, and a random pick would make two calls for the same function disagree.
* ``LastModified`` is the resource's earliest billed day in Lambda's own string format
  (``2026-01-01T00:00:00.000+0000`` — the model types this member as a **string**, not a
  timestamp, so a numeric epoch would reach the caller as a number where it expects a
  date). It is omitted for a function the estate has never billed.
* ``Role``, ``Handler`` and ``CodeSize`` are omitted: the estate carries no code, no
  handler and no IAM role, and inventing any of the three would put a value in
  FinOps inventory that no estate row backs.

``FunctionName`` is the resource's derived AWS id (``aws_sim.ids``), which is the same value
the function's ARN ends in: a Lambda name is scope-free and the estate reuses names across
accounts, so a row named after the resource would name several functions at once and a
caller correlating the name with ``GetFunction`` would reach the wrong one.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.resource import Resource

from aws_sim import arns, ids, scope

RESOURCE_TYPE = "lambda_function"

STATE_ACTIVE = "Active"
VERSION_LATEST = "$LATEST"

RUNTIMES: tuple[str, ...] = ("python3.12", "nodejs20.x", "java21")
MEMORY_MB: tuple[int, ...] = (128, 256, 512, 1024)
TIMEOUT_SECONDS = 30

#: Lambda's own ``LastModified`` format: ISO-8601 with milliseconds and a ``+0000``
#: offset, not a ``Z``. The member is a string in the model, so the caller sees this text.
_LAST_MODIFIED_FORMAT = "%Y-%m-%dT%H:%M:%S.000+0000"


def _bucket(key: str, count: int) -> int:
    """A stable catalog index for ``key`` (a resource uuid or a uuid-derived key)."""
    return int(arns.stable_digest(key, 8), 16) % count


def _function(resource: Resource, last_modified: datetime | None) -> dict[str, Any]:
    """One ``Functions`` entry for an estate Lambda function."""
    uuid = resource.identity.uuid
    row: dict[str, Any] = {
        "FunctionName": ids.resource_id(resource),
        "FunctionArn": arns.resource_arn(resource),
        "Runtime": RUNTIMES[_bucket(uuid, len(RUNTIMES))],
        "MemorySize": MEMORY_MB[_bucket(f"{uuid}:memory", len(MEMORY_MB))],
        "Timeout": TIMEOUT_SECONDS,
        "Version": VERSION_LATEST,
        "State": STATE_ACTIVE,
    }
    if last_modified is not None:
        row["LastModified"] = last_modified.astimezone(UTC).strftime(_LAST_MODIFIED_FORMAT)
    return row


def functions(estate: CanonicalEstate) -> tuple[dict[str, Any], ...]:
    """Every Lambda function the estate carries, ordered by name."""
    first_charge = scope.first_charge(estate)
    rows = [
        _function(resource, first_charge.get(resource.identity.uuid))
        for resource in scope.resources(estate)
        if resource.resource_type == RESOURCE_TYPE
    ]
    return tuple(sorted(rows, key=lambda row: row["FunctionName"]))
