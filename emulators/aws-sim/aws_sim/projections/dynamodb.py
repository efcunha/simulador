"""The DynamoDB projection: table names, one per estate table resource.

``ListTables`` answers with names alone, so this projection stops there: a
``TableDescription`` would be a fabrication (the estate records no keys, no capacity
mode), and a caller that needs one has to ask ``DescribeTable`` for the name it was
given.

A table name is the resource's derived AWS id (``aws_sim.ids``), the value the ARN the
tagging API reports ends in, and NOT the estate's ``resource_name``: a DynamoDB table name
is scope-free while the estate reuses a name across accounts, so a name read from the estate
would answer one table for several resources sharing it. ``Resource.resource_name`` stays
what it is — the display name the FOCUS export carries.
"""

from __future__ import annotations

from tools.synthetic_clouds.model.estate import CanonicalEstate

from aws_sim import ids, scope

RESOURCE_TYPE = "dynamodb_table"


def tables(estate: CanonicalEstate) -> tuple[str, ...]:
    """Every table name the estate carries, ordered."""
    return tuple(
        sorted(
            ids.resource_id(r) for r in scope.resources(estate) if r.resource_type == RESOURCE_TYPE
        ),
    )
