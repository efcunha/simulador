"""The AWS id every aws-sim projection answers for an estate resource.

**One resource, one id, whichever call reports it.** AWS ids are what FinOps
correlates across a scan: the tag scanner stores the ``ResourceARN`` the Resource Groups
Tagging API returned and compares it later with ``DBInstanceArn``, ``LoadBalancerArn`` or
the id a service's ``Describe*`` reported; the observability path takes the id
``DescribeInstances`` answered and sends it straight back as the ``InstanceId`` dimension
of a CloudWatch query. So the id a read answers and the id a metric read is keyed by have
to be one value, and they are not if either side reads ``Resource.resource_name``.

**Why the name cannot be that id.** The canonical estate deliberately reuses
``resource_name`` across scopes — ``generate/estate_builder.py`` restarts its per-scope
counter for every account, so ``ec2_instance-0018`` exists in three subscriptions and 18
EC2 instances carry 11 distinct names. An AWS ``InstanceId`` is scope-free, so a
projection answering the name answers the *same* value for every resource sharing it: the
CloudWatch shim then matches the first row it finds and judges several instances on one
resource's samples, which is mis-attribution, not a display-name collision. The metric
series are keyed per ``resource_uuid`` (the generator meters one series per resource), so
the fault is entirely in the value the projections publish, and this module is the one
place that fixes it.

**Where the id comes from.** ``model/identity.aws_resource_id`` mints it from the
resource's own ``ResourceIdentity.uuid`` in the shape AWS's own id for that
``resource_type`` carries (``i-``, ``vol-``, ``sg-`` …). It is therefore unique per
resource by construction, deterministic for a ``(seed, logical_path)``, and in a documented
character class. There is no scope segment to fall back on: unlike an Azure ARM id (which
embeds the subscription and resource group) or a GCP ``projects/<p>/...`` path (which
embeds the project), an EC2 ``InstanceId`` carries no scope at all, which is exactly why
one has to be derived.
"""

from __future__ import annotations

from tools.synthetic_clouds.model.identity import aws_resource_id
from tools.synthetic_clouds.model.resource import Resource


def resource_id(resource: Resource) -> str:
    """The AWS id of ``resource``, in the shape its own ``resource_type`` uses.

    Every projection that reports an id — ``InstanceId``, ``VolumeId``, ``VpcId``,
    ``GroupId``, ``NatGatewayId``, ``AllocationId``, ``DBInstanceIdentifier``,
    ``FunctionName``, a cluster or table name, and the ARN built from one — asks here, so
    the same resource cannot end up with two identities in two answers.
    """
    resource_id: str = aws_resource_id(resource.resource_type, resource.identity.uuid)
    return resource_id
