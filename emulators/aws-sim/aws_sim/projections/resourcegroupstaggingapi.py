"""The Resource Groups Tagging API projection: every AWS resource, with its tags.

This is the endpoint FinOps tag governance reads (``scanner (modulo do consumidor)``),
and it is the one place where **every** AWS resource appears regardless of type — the
per-service projections only show the type they own. The ARN therefore comes from
``aws_sim.arns`` like everybody else's, which is what lets the scanner's ARN be matched
later against ``DescribeDBInstances`` or ``DescribeLoadBalancers`` output.

Tag *pairs*, not tag sets: the estate stores ``(key, value)`` tuples in order, so the
wire keeps that order instead of re-sorting into a map the caller would have to unpack.

One consequence of keying on the ARN is worth stating: a bucket name is global in AWS but
this estate names buckets per account, so a few names repeat across accounts and their
``arn:aws:s3:::<name>`` collides. Both rows are returned rather than one being dropped —
the tags differ between them, and hiding one would turn a conflict in the data into a
missing resource. The ARN cannot carry the account; that is what makes it global.

Nothing is filtered here — the emulator returns the estate's resources and the caller
narrows. The two filters the API defines are handled in ``api/resourcegroupstaggingapi.py``,
one by applying it and one by refusing it, so a filtered request never silently returns
an unfiltered answer.
"""

from __future__ import annotations

from typing import Any

from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.resource import Resource

from aws_sim import arns, scope


def tag_pairs(resource: Resource) -> list[dict[str, str]]:
    """The resource's tags in the wire shape both this API and ELBv2 use."""
    return [{"Key": key, "Value": value} for key, value in resource.tags]


def resources(estate: CanonicalEstate) -> tuple[dict[str, Any], ...]:
    """One ``ResourceTagMappingList`` entry per AWS resource that has an ARN, by ARN.

    A resource type with no ARN in AWS (``data_transfer``, a cost line rather than an
    object) is left out: the mapping is keyed by ARN, so there is no honest way to
    include it.
    """
    rows: list[dict[str, Any]] = []
    for resource in scope.resources(estate):
        arn = arns.resource_arn(resource)
        if arn is None:
            continue
        rows.append({"ResourceARN": arn, "Tags": tag_pairs(resource)})
    return tuple(sorted(rows, key=lambda row: row["ResourceARN"]))
