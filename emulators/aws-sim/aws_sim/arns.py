"""The ARN constructor every aws-sim projection shares.

An ARN is the only identifier that survives a hop between two AWS services, and
FinOps relies on exactly that: the tag scanner records ``ResourceARN`` from the
Resource Groups Tagging API and correlates it later with ``DBInstanceArn`` (RDS),
``LoadBalancerArn`` (ELBv2) or the ECS/DynamoDB ARNs. Two modules building the same ARN
independently is how one estate resource ends up with two identities, so the shape is
written once here and every service asks for it — the tagging endpoint and the
resource-specific endpoint cannot disagree by construction.

The ARN's resource part is the resource's **AWS id** (``aws_sim.ids.resource_id``,
minted in the shape its own ``resource_type`` uses), NOT ``Resource.resource_name``: the
estate reuses a name across scopes, so an ARN built from the name would give two EC2
instances in two accounts the same ``instance/<name>`` while their ids differ — one
resource with two identities, which is the failure this module exists to prevent. The ARN
and the id a ``Describe*`` reports are therefore the same value, and a caller that rebuilds
an ARN from region + account + id (``security (modulo do consumidor)`` does exactly
that with ``security-group/<GroupId>``) lands on the ARN the sim published.

Three conventions, stated because the wire does not forgive a wrong one:

* ``arn:aws:<service>:<region>:<account>:<resource>``. An S3 bucket name is globally
  unique, and the real ARN leaves the region and account fields empty
  (``arn:aws:s3:::``); reproducing that keeps FinOps ``region_id`` derivation
  honest about a global resource instead of inventing a region for it.
* An Application Load Balancer's ARN ends in a 16-character id AWS derives from the
  balancer's own configuration. The emulator cannot re-derive AWS's value, so it derives
  ITS OWN from the balancer's id (:func:`stable_digest`): the same balancer reports the
  same ARN on every call and in every service, and an id that is obviously synthetic
  beats one that pretends to be AWS's.
* A resource type the estate models as a **cost line rather than a live object**
  (``data_transfer``) has no ARN in AWS, so :func:`resource_arn` returns ``None`` and
  the callers leave the resource out. Absence is absence, not an invented identifier.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from tools.synthetic_clouds.model.resource import Resource

from aws_sim import ids


@dataclass(frozen=True, slots=True)
class ArnShape:
    """Where one estate ``resource_type`` sits inside an AWS ARN."""

    service: str
    #: The resource part, formatted with ``id`` (the resource's AWS id —
    #: ``aws_sim.ids.resource_id``) and ``digest`` (a 16-character digest of that id, the
    #: opaque second segment AWS's own ELB ARN carries).
    resource: str
    #: A globally unique name (S3): the ARN carries neither region nor account.
    globally_unique: bool = False


#: estate ``resource_type`` -> its ARN. The estate's types are the generator's closed
#: catalog, so a missing key is a code change upstream, not a runtime condition.
_TYPE_ARNS: dict[str, ArnShape] = {
    "ec2_instance": ArnShape("ec2", "instance/{id}"),
    "ebs_volume": ArnShape("ec2", "volume/{id}"),
    "nat_gateway": ArnShape("ec2", "natgateway/{id}"),
    "elastic_ip": ArnShape("ec2", "eip-allocation/{id}"),
    "vpc": ArnShape("ec2", "vpc/{id}"),
    "security_group": ArnShape("ec2", "security-group/{id}"),
    "rds_instance": ArnShape("rds", "db:{id}"),
    "s3_bucket": ArnShape("s3", "{id}", globally_unique=True),
    "dynamodb_table": ArnShape("dynamodb", "table/{id}"),
    "eks_cluster": ArnShape("eks", "cluster/{id}"),
    "ecs_cluster": ArnShape("ecs", "cluster/{id}"),
    "lambda_function": ArnShape("lambda", "function:{id}"),
    "application_lb": ArnShape("elasticloadbalancing", "loadbalancer/app/{id}/{digest}"),
    "cloudwatch_logs": ArnShape("logs", "log-group:{id}"),
}


def stable_digest(value: str, length: int = 16) -> str:
    """A deterministic hex digest of an estate value.

    Used wherever AWS derives an opaque id from a resource's own configuration and the
    emulator must do the same from the only inputs it has (the resource's AWS id or uuid).
    Same value in, same id out — which a random or clock-derived id could not promise,
    and FinOps correlates these ids across a scan.
    """
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def arn(service: str, region: str, account: str, resource: str) -> str:
    """Build ``arn:aws:<service>:<region>:<account>:<resource>``."""
    return f"arn:aws:{service}:{region}:{account}:{resource}"


def has_arn(resource_type: str) -> bool:
    """Whether AWS exposes a resource of this type as an ARN-addressable object."""
    return resource_type in _TYPE_ARNS


def arn_for_type(resource_type: str, resource_id: str, region: str, account: str) -> str | None:
    """Build the ARN of a resource from its parts, or ``None`` if AWS has no ARN for it."""
    shape = _TYPE_ARNS.get(resource_type)
    if shape is None:
        return None
    part = shape.resource.format(id=resource_id, digest=stable_digest(resource_id))
    if shape.globally_unique:
        return arn(shape.service, "", "", part)
    return arn(shape.service, region, account, part)


def resource_arn(resource: Resource) -> str | None:
    """The resource's ARN, or ``None`` for a type AWS does not expose as an ARN.

    The type is checked BEFORE the id is minted: a type with no ARN is a cost line rather
    than a live object (``data_transfer``), so it has no id either, and asking for one would
    be answering about a resource the estate says does not exist.
    """
    if not has_arn(resource.resource_type):
        return None
    return arn_for_type(
        resource.resource_type,
        ids.resource_id(resource),
        resource.region_id,
        resource.parent_scope_id,
    )
