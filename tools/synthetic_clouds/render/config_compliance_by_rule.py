"""AWS Config ``DescribeComplianceByConfigRule`` response renderer (conformidade por regra).

Projects the canonical estate's AWS resources into the **11 documented fields** of
``specs/aws/config-describe-compliance-by-config-rule.schema.json`` -- the 2 top-level
response elements, the 2 members of ``ComplianceByConfigRule``, the 2 of ``Compliance``, the
2 of ``ComplianceContributorCount`` and the 3 documented request parameters.

WHY THIS SURFACE IS NOT THE CONFIG SNAPSHOT
-------------------------------------------
``render/aws_config_snapshot.py`` renders the other AWS Config surface: the durable export of
CONFIGURATION ITEMS (one row per resource, in the S3 layout Config publishes). This one is a
different surface, with a different granularity and a different question. ``DescribeComplianceByConfigRule``
answers "what did the rules say?", one item PER RULE, not one item per resource -- so it is
the surface a posture screen consumes when it wants a rule-level verdict rather than a
resource-level fact. The two are deliberately not merged: a configuration item and a rule
compliance summary are different records with different documented shapes.

THE FORMAT DECISION
-------------------
``delivery.kind`` is ``read_api`` and ``delivery.format`` is ``json``. AWS Config publishes no
durable artifact for this action and the API Reference publishes the response as **JSON**
(section ``Response Syntax``), so -- unlike ``render/ec2_instances.py``, whose API Reference
publishes XML only -- here the delivered encoding IS the documented one. There is no encoding
divergence to declare.

``NextToken`` is null in every envelope: that is the documented value for "there are no more
items to return", and this fixture carries each scope's whole rule set in one page.

WHAT THE RULE NAMES ARE, AND WHERE THEY CAME FROM
-------------------------------------------------
Every ``ConfigRuleName`` written here is a REAL AWS Config **managed rule**, not an invented
identifier. This matters because the product side reads this API: ``FinOps``'s
``emulators/aws-sim`` uses synthetic ``synth-*`` rule names, which is defensible for a stub but
would make this surface useless for checking a real posture screen. So the catalog below was
read out of the official list of AWS Config managed rules
(https://docs.aws.amazon.com/config/latest/developerguide/managed-rules-by-aws-config.html,
838 rule names, read on 2026-10-16) and every name was checked against that list before being
written. Nothing here is invented; :func:`catalog_names` is the assertion that keeps it that
way.

THE FOUR DOMAINS
-----------------
The catalog spans the four domains a posture screen expects, and each rule carries the MODEL
GAP that stops it from being evaluated (see ``gap`` on :class:`_Rule`):

* **S3 public exposure** -- ``s3-bucket-public-read-prohibited``,
  ``s3-bucket-public-write-prohibited``, ``s3-bucket-level-public-access-prohibited``;
* **network** -- ``restricted-ssh``, ``restricted-common-ports``,
  ``vpc-default-security-group-closed``, ``vpc-flow-logs-enabled``;
* **identity** -- ``root-account-mfa-enabled``, ``iam-password-policy``, ``access-keys-rotated``;
* **audit/guardrails** -- ``cloudtrail-enabled``, ``securityhub-enabled``.

Two more are in the catalog because the estate CAN evaluate them (below): ``s3-bucket-tagged``
and ``lambda-function-tagged``. **As of the Increment 4.3 NONE of the twelve rules above carries
a live model gap**: the three network rules lost theirs in the Increment 2 (security-group
RULES), the three S3 exposure rules in the Increment 3 (bucket ACL, policy and public-access-
block), the three identity rules in the Increment 4 (the ``AwsIdentityPosture`` of each account)
and the last three -- ``vpc-flow-logs-enabled``, ``cloudtrail-enabled`` and
``securityhub-enabled`` -- in the Increment 4.3 (the per-VPC flow-log configuration and the
``AwsAuditPosture`` of each account).

THE HONEST PART: ALL FOURTEEN RULES ARE EVALUATED NOW
-----------------------------------------------------
This is the core of the surface and it is stated here rather than hidden in a gap list. Every
number in this section was MEASURED by rendering ``build_estate(seed=123, profile="small",
currency="USD")`` and counting the emitted items -- and the same counts are written by the
renderer into the sibling ``_provenance.json`` under ``counts``, so this prose and the
machine-readable report cannot drift apart without one of them being wrong.

The shape of the surface is fourteen managed rules over nine (account, region) scopes, which
is 126 ``ComplianceByConfigRule`` items:

* **45 COMPLIANT**;
* **27 NON_COMPLIANT**;
* **54 INSUFFICIENT_DATA**.

Before the Increment 4.3 it was 32 / 19 / 75, with three rules that never answered at all, in
any scope:

* ``cloudtrail-enabled`` -- CloudTrail is not a resource type in the estate: the 237 AWS
  entities are of fifteen types and none of them is an audit trail;
* ``securityhub-enabled`` -- the estate has no service-enrolment entity, so it cannot assert
  whether Security Hub is enabled on the account;
* ``vpc-flow-logs-enabled`` -- the estate has 15 VPCs but does not carry the fact the rule
  reads (whether the VPC has flow logs); the logging activity is a resource of the log
  stream, not an attribute of the VPC.

All three now answer from the state. The catalog once carried nine model gaps; they were closed
by evidence rather than by prose -- the three network rules by the Increment 2, the three S3
exposure rules by the Increment 3, the three identity rules by the Increment 4 and these three
by the Increment 4.3. What each increment added to the estate:

* **Increment 2** gave the fifteen ``security_group`` resources their ingress and egress
  RULES, which the three network rules read (:func:`_violacoes_rede`);
* **Increment 3** gave the fifteen buckets their ACL grants, bucket policy and
  public-access-block (``AwsBucketPosture.acl_grants``/``.policy``/``.public_access_block``),
  which the three S3 exposure rules read (:func:`_violacoes_s3`);
* **Increment 4** added the identity entities (``estate.aws_identity_postures``, one
  :class:`AwsIdentityPosture` per account) that the three IAM rules read, through the shared
  evaluators in :mod:`tools.synthetic_clouds.render._config_evaluators`;
* **Increment 4.3** added ``estate.aws_audit_postures`` (one :class:`AwsAuditPosture` per
  account: its CloudTrail trails and its Security Hub enrolment) and ``estate.aws_vpc_flow_logs``
  (one :class:`AwsVpcFlowLog` per ``vpc`` resource). It is the only increment whose rules split
  by GRANULARITY -- two of the three read the account, the third reads a resource.

WHY THE 54 INSUFFICIENT_DATA ITEMS ARE 48 + 6
----------------------------------------------
The 54 is not one population and it splits cleanly by CAUSE. Both causes are the *collapse*,
and there is no longer a third one for a missing fact:

* **48 = 8 resource rules x 6 scopes.** Each resource type lives in exactly one region per
  account, so of the nine scopes only three hold a resource of the type and the other six have
  nothing to evaluate. The API reports an all-``NOT_APPLICABLE`` rule as
  ``INSUFFICIENT_DATA`` (:data:`_GAP_NOT_APPLICABLE`).
* **6 = ``vpc-flow-logs-enabled`` x the 6 scopes with no VPC.** The same collapse, on the ninth
  resource rule: the estate places its fifteen ``vpc`` resources in one region per account, so
  the rule answers in the three scopes that hold a VPC and collapses in the other six.

Nothing is left from a model gap, and that is the difference from the 75 this section used to
explain: **27 of those items (3 never-answering rules x 9 scopes) were a missing fact and are
now gone**, replaced by the 6 collapse items ``vpc-flow-logs-enabled`` contributes -- which is
why the total falls by 21 and not by 27.

The eleven rules the first three increments produced split the same way: they answer in the
three scopes that hold their resource and are ``INSUFFICIENT_DATA`` in the other six -- 2
COMPLIANT + 1 NON_COMPLIANT + 6 ``INSUFFICIENT_DATA`` each. The five ACCOUNT-level ones (three
identity, two audit) answer in all nine, 0 ``INSUFFICIENT_DATA`` each, because their facts are
per account.

Nine rules read a RESOURCE and are evaluated from a fact the estate carries. The first two of them
are the tagged ones, ``s3-bucket-tagged`` and ``lambda-function-tagged``, whose own pages
state the condition verbatim:

    "The rule is NON_COMPLIANT if there are no tags or if the specified tag keys are not
    present. The rule does not check for tags starting with 'aws:'."
    -- https://docs.aws.amazon.com/config/latest/developerguide/s3-bucket-tagged.html

``requiredKeyTags`` is an OPTIONAL rule parameter. This renderer passes none, so the rule
reduces to the condition the page states unconditionally: NON_COMPLIANT iff the resource has no
countable tag. ``Resource.tags`` is exactly that fact.

The next three are the NETWORK rules the Increment 2 unblocked: ``restricted-ssh``,
``restricted-common-ports`` and ``vpc-default-security-group-closed``. They were
``INSUFFICIENT_DATA`` for a MODEL reason -- the estate carried fifteen ``security_group``
resources and not one rule -- and the Increment 2 gave those groups their ingress and egress
rules, so each rule now applies its own published text (see :func:`_violacoes_rede`). Two
measurement notes that belong here rather than in a gap list:

* ``restricted-common-ports`` takes OPTIONAL parameters (``blockedPort1``..``blockedPort5``,
  ``blockedPorts``). This renderer passes none, so the rule reduces to the page's own DEFAULTS
  -- 20, 21, 3389, 3306 and 4333 (:data:`DEFAULT_BLOCKED_PORTS`) -- the same reduction the
  tagged rules make for ``requiredKeyTags``;
* an all-protocol ingress rule (``ipProtocol`` ``-1``) counts as admitting the port. The
  ``IpPermission`` page says ``-1`` "allows traffic on all ports, regardless of any port range
  you specify", so reading it as "not TCP" would let a rule that plainly exposes SSH pass.

The last three are the S3 EXPOSURE rules the Increment 3 unblocked:
``s3-bucket-public-read-prohibited``, ``s3-bucket-public-write-prohibited`` and
``s3-bucket-level-public-access-prohibited``. They read :class:`AwsBucketPosture` -- the ACL
grants, the bucket policy and the public-access-block -- and the renderer FAILS CLOSED on the
join: an ``s3_bucket`` resource with no matching posture raises :class:`RenderError` instead of
answering about a bucket whose exposure it cannot see (see :func:`verdict`).

The ``aws:`` tag exclusion is applied explicitly in :func:`countable_tags` rather than assumed
away.

THE LAST THREE, AND WHY THEY SPLIT BY GRANULARITY
-------------------------------------------------
The Increment 4.3 closed the residue, and it is the only increment whose rules do NOT share a
granularity. The split is not a design choice: it is what the three pages publish.

``cloudtrail-enabled`` -- ACCOUNT. The page carries trigger ``Periodic`` and NO "Resource
Types", and states "Checks if an AWS CloudTrail trail is enabled in your AWS account. The rule
is NON_COMPLIANT if a trail is not enabled." It takes three OPTIONAL parameters
(``cloudWatchLogsLogGroupArn``, ``s3BucketName``, ``snsTopicArn``); this renderer passes none,
so the rule REDUCES to the page's unconditional clause -- a trail exists in the account. The
names of the three parameters stay in :data:`const.AWS_AUDIT_RULE_PARAMETERS` so that "not
passed" is a declared choice rather than an absence.

    The name trap this rule sets: the page says so in a box of its own that "the rule
    identifier (CLOUD_TRAIL_ENABLED) and rule name (cloudtrail-enabled) are different". The
    IDENTIFIER is the underscored one; the NAME has no hyphen between "cloud" and "trail". The
    catalog carries the NAME, because ``ConfigRuleName`` is what the API publishes, and the
    ``high_patterns`` list of FinOps ``security.py::_config_rule_severity`` still carries
    the hyphenated ``cloud-trail-enabled``, which matches nothing in this catalog.

``securityhub-enabled`` -- ACCOUNT. Same shape, and the simplest rule of the residue: "Checks if
AWS Security Hub is enabled for an AWS Account. The rule is NON_COMPLIANT if AWS Security Hub is
not enabled", with "Parameters: None". No reduction to declare, because there is no optional
parameter to reduce.

``vpc-flow-logs-enabled`` -- RESOURCE. The only rule here that names a resource type:
``Resource Types: AWS::EC2::VPC``. Its page says the rule is NON_COMPLIANT "if flow logs are not
enabled for at least one Amazon VPC", and that aggregate is what makes it the only rule of this
catalog that turns ONE violating resource out of several into a NON_COMPLIANT rule. Its one
OPTIONAL parameter (``trafficType``) is not passed, so it reduces to the page's unconditional
"flow logs are found and enabled" -- and the traffic types each log collects stay in
:attr:`AwsVpcFlowLog.traffic_types` precisely so that reduction is inspectable.

The state separation is what makes the two halves untangleable: identity reads
``estate.aws_identity_postures``, audit reads ``estate.aws_audit_postures``. Both are per-account
booleans, so a renderer that answered a CloudTrail verdict out of the IAM posture would look
perfect and be wrong, and nothing but the split collections and the golden test can tell.

THE THREE STATES THAT LOOK LIKE ONE
-----------------------------------
``INSUFFICIENT_DATA`` in this surface now has exactly ONE cause -- the ``NOT_APPLICABLE``
collapse -- and two neighbours that must not be confused with it:

* a scope with no VPC at all is ``INSUFFICIENT_DATA``: nothing was evaluated;
* a VPC with an EMPTY ``flow_log_ids`` is ``NON_COMPLIANT``: the estate is asserting the VPC has
  no flow log, which is a KNOWN violation and not an absence of knowledge. Collapsing the empty
  list into the third value would hide a real finding behind an "I don't know";
* an account with no CloudTrail trail is ``NON_COMPLIANT`` on the same grounds, and names the
  account as the contributor.

The renderer FAILS CLOSED rather than answering ``INSUFFICIENT_DATA`` for a missing posture: a
scope whose account has no :class:`AwsAuditPosture`, or whose ``vpc`` resource has no
:class:`AwsVpcFlowLog`, raises :class:`RenderError` instead of answering about a fact it cannot
see (see :func:`verdict` and :meth:`ConfigComplianceByRuleRenderer.render`).

THE VERDICT IS THE PUBLISHED ONE, NOT A LOCAL INVENTION
--------------------------------------------------------
``ComplianceType`` is filled by applying the semantics the ``Compliance`` page publishes, not
a rule of this module's own:

* "A rule is compliant if all of the resources that the rule evaluates comply with it. A rule
  is noncompliant if any of these resources do not comply." -> any violating resource makes the
  rule NON_COMPLIANT (:func:`verdict`);
* "AWS Config returns the INSUFFICIENT_DATA value when no evaluation results are available for
  the AWS Config rule." -> no result is ``INSUFFICIENT_DATA``;
* "The number of AWS resources or AWS Config rules that **cause a result of NON_COMPLIANT**"
  (:class:`ComplianceContributorCount`) -> ``CappedCount`` counts the resources that DID cause
  the non-compliance, so a COMPLIANT rule carries ``0``. Counting every evaluated resource here
  would be a different, and undocumented, number.

``CapExceeded`` IS ALWAYS NULL, and this is a gap rather than an omission
-------------------------------------------------------------------------
``CapExceeded`` is documented as "Indicates whether the maximum count is reached", but the
``ComplianceContributorCount`` page never publishes that maximum -- it only says "up to a maximum
number". The comparison is therefore not reproducible from the documentation, and a boolean
derived from an unpublished ceiling would be a value this package cannot justify. ``CappedCount``
stays real (it is a model count); ``CapExceeded`` stays null. The gap is listed in
``REQUIRED_EMPTY_GAPS``-style prose here and counted in the sibling ``_provenance.json``.

WHY A SCOPE WITH NO RESOURCE OF THE RIGHT TYPE IS *ALSO* INSUFFICIENT_DATA
--------------------------------------------------------------------------
This is the one place where a plausible-looking shortcut was deliberately refused.

The estate places each AWS resource type in a single region per account (buckets in
``us-west-2``, Lambda functions in ``sa-east-1``, security groups in ``us-east-1``), so this
renderer produces nine (account, region) scopes and most of them hold no bucket at all. Writing
``COMPLIANT`` there would be wrong -- a rule with nothing to evaluate has not evaluated
everything. And ``NOT_APPLICABLE`` is not available either: the ``Compliance`` page says so
outright, "AWS Config does not support the NOT_APPLICABLE value for the Compliance data type",
and ``DescribeComplianceByConfigRule`` documents that a rule whose Lambda returned
``NOT_APPLICABLE`` for every result is reported as ``INSUFFICIENT_DATA``. So an empty scope is
``INSUFFICIENT_DATA`` with that reason (:func:`verdict`), which is both the honest answer and
the one the documentation prescribes.

WHAT STAYS EMPTY, AND WHY
-------------------------
* the whole ``request-parameters`` set: those three names belong to the REQUEST side of the
  action, and the estate models no captured request. The document is emitted with null values
  so the request vocabulary is present and the gap is testable, exactly as
  ``render/ec2_instances.py`` does for its own request set. Note the difference from
  ``NextToken``: the request's PARAMETERS are facts about a call nobody captured;
* ``CapExceeded``: the ceiling it compares against is unpublished (above).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from tools.synthetic_clouds.fidelity.spec import SurfaceSpec, load_spec
from tools.synthetic_clouds.generate.constants import PROVIDER_KEY_AWS
from tools.synthetic_clouds.model.audit import AwsAuditPosture, AwsVpcFlowLog
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.iam import AwsIdentityPosture
from tools.synthetic_clouds.model.network import (
    AWS_IP_PROTOCOL_ALL,
    AwsIpPermission,
    AwsSecurityGroup,
)
from tools.synthetic_clouds.model.resource import Resource
from tools.synthetic_clouds.model.storage import (
    S3_PUBLIC_GROUP_URIS,
    S3_PUBLIC_READ_PERMISSIONS,
    S3_PUBLIC_WRITE_PERMISSIONS,
    AwsBucketPosture,
)
from tools.synthetic_clouds.render._config_evaluators import (
    ACCOUNT_AUDIT_RULE_EVALUATORS,
    IAM_RULE_EVALUATORS,
    VPC_FLOW_LOG_RULE_EVALUATORS,
)
from tools.synthetic_clouds.render.base import RenderError

# The surface this renderer produces, as the spec names it.
SURFACE = "aws/config-describe-compliance-by-config-rule"

# The cited specification: the source of truth for this surface.
SPEC_PATH = Path(__file__).resolve().parents[3] / "specs" / "aws" / "config-describe-compliance-by-config-rule.schema.json"

# The rendered directory under ``out_dir``.
RENDER_DIR = "config_compliance_by_rule"

#: The sibling provenance report, written beside the data (never inside it).
PROVENANCE_PATH = "_provenance.json"

# The sets of the cited specification, by name.
RESPONSE_SCOPE = "describe-compliance-by-config-rule-response"
ITEM_SCOPE = "compliance-by-config-rule"
COMPLIANCE_SCOPE = "compliance"
CONTRIBUTOR_SCOPE = "compliance-contributor-count"
REQUEST_SCOPE = "request-parameters"

#: The official list every rule name in :data:`CATALOG` was checked against.
MANAGED_RULES_URL = "https://docs.aws.amazon.com/config/latest/developerguide/managed-rules-by-aws-config.html"

#: The prefix the tagged managed rules explicitly do not count, per their own pages
#: ("The rule does not check for tags starting with 'aws:'").
RESERVED_TAG_PREFIX = "aws:"


#: The semantics a rule is answered with. This is NOT a local taxonomy: each value names the
#: published rule text :func:`verdict` applies, and the module docstring quotes it. A rule with
#: no semantics is answered only by its model gap.
SEMANTICS_TAGGED = "tagged"
SEMANTICS_RESTRICTED_SSH = "restricted-ssh"
SEMANTICS_RESTRICTED_COMMON_PORTS = "restricted-common-ports"
SEMANTICS_DEFAULT_GROUP_CLOSED = "default-group-closed"
# The three S3 exposure rules, answerable since the Increment 3: the estate now carries the
# ACL, the bucket policy and the Block Public Access configuration of every bucket.
SEMANTICS_S3_PUBLIC_READ_PROHIBITED = "s3-public-read-prohibited"
SEMANTICS_S3_PUBLIC_WRITE_PROHIBITED = "s3-public-write-prohibited"
SEMANTICS_S3_BUCKET_LEVEL_PUBLIC_ACCESS = "s3-bucket-level-public-access"
# The three identity rules, answerable since the Increment 4: the estate now carries each
# account's root MFA, password policy, IAM users and access keys. They do NOT read a
# ``Resource``, so they carry no ``resource_type`` -- and they are the only rules answered
# through ``_config_evaluators``, which the retrospective diagnostic also calls.
SEMANTICS_IDENTITY = "identity"
# The two ACCOUNT-level audit rules, answerable since the Increment 4.3: the estate now carries
# each account's CloudTrail trails and its Security Hub enrolment. Like the identity rules they
# do NOT read a ``Resource`` -- their own pages publish trigger ``Periodic`` and NO "Resource
# Types" -- so they carry no ``resource_type`` and answer once per account, repeated in each of
# the account's regions. They read the AUDIT posture, not the identity one: an MFA on the root
# says nothing about whether a trail exists.
SEMANTICS_CLOUDTRAIL = "cloudtrail"
SEMANTICS_SECURITY_HUB = "securityhub"
# The one VPC-level rule the Increment 4.3 added. Unlike the two above it DOES read a resource:
# its page publishes ``Resource Types: AWS::EC2::VPC``. It is the only rule in this catalog that
# answers NON_COMPLIANT because ONE sibling resource out of several is violating, which is what
# "at least one Amazon VPC" in the published text means.
SEMANTICS_VPC_FLOW_LOGS = "vpc-flow-logs"

#: The semantics a rule is answered with when it reads the ACCOUNT rather than a resource. Kept
#: as a set, not as a chain of ``==``: the renderer dispatches on membership, and a rule added
#: here without a matching evaluator fails loudly at the registry lookup instead of quietly
#: answering through the wrong branch.
_ACCOUNT_SEMANTICS: frozenset[str] = frozenset(
    {SEMANTICS_IDENTITY, SEMANTICS_CLOUDTRAIL, SEMANTICS_SECURITY_HUB}
)

#: The action prefixes AWS's Service Authorization Reference files under the read and write
#: categories, plus the two ways a policy can grant everything. A policy that names only
#: fixed values is not public; one that reaches a principal with a wildcard IS -- see
#: ``_policy_e_publico``.
S3_READ_ACTION_PREFIXES = ("s3:Get", "s3:List", "s3:Describe", "s3:Head")
S3_WRITE_ACTION_PREFIXES = (
    "s3:Put",
    "s3:Delete",
    "s3:Create",
    "s3:Restore",
    "s3:Replicate",
    "s3:AbortMultipartUpload",
)
#: The principal value that reaches EVERYONE. The bucket policy page says Amazon S3 "begins
#: by assuming that the policy is public" and only stops when the grant names a fixed value,
#: so the wildcard is the value that makes a grant public.
S3_PRINCIPAL_WILDCARD = "*"

#: The default blocked TCP ports of ``restricted-common-ports``, as its own page publishes them
#: (``blockedPort1``..``blockedPort5``). This renderer passes NO rule parameters, so the rule
#: reduces to the condition the page states unconditionally -- the same reduction increment 1
#: already makes for ``requiredKeyTags`` on the tagged rules. Source:
#: https://docs.aws.amazon.com/config/latest/developerguide/restricted-common-ports.html
DEFAULT_BLOCKED_PORTS: tuple[int, ...] = (20, 21, 3389, 3306, 4333)

#: The two sources the published rule texts name as "all addresses". A source equal to either is
#: unrestricted; anything else is restricted. Both appear verbatim in the three rule pages.
CIDR_ALL_IPV4 = "0.0.0.0/0"
CIDR_ALL_IPV6 = "::/0"


@dataclass(frozen=True, slots=True)
class _Rule:
    """One managed rule of the catalog, and what it would take to answer it.

    ``resource_type`` is the estate's own ``Resource.resource_type`` the rule reads. It is set
    ONLY for the rules the estate can evaluate -- the two tagged ones and the three network ones
    the Increment 2 unblocked. For the rest it stays ``None`` even though AWS publishes a
    resource type on each rule page: this renderer does not claim a resource type it did not
    read, and it has no use for one it cannot evaluate.

    ``semantics`` is which published condition :func:`verdict` applies. It is empty exactly for
    the rules that are answered from state and have one; a rule with a gap has no semantics,
    because there is nothing to apply them to.

    ``gap`` is the MODEL GAP that stops evaluation -- a sentence about the estate, not about
    AWS. It is empty exactly for the rules that are answered from state.
    """

    name: str
    source_url: str
    gap: str
    resource_type: str | None = None
    semantics: str = ""


#: The catalog: 14 REAL managed rules, every name verified in :data:`MANAGED_RULES_URL` on
#: 2026-10-16. **ALL FOURTEEN are evaluated from the estate** as of the Increment 4.3, and
#: NONE is answered ``INSUFFICIENT_DATA`` with a model gap -- the catalog used to carry nine of
#: those gaps and the last three closed with the audit entities. What is left in the surface's
#: ``INSUFFICIENT_DATA`` is the *NOT_APPLICABLE collapse* below, which is a different thing: a
#: scope with no resource of the rule's type, not a missing fact.
#:
#: The eleven rules the first three increments produced read a RESOURCE and answer in the three
#: scopes that hold one; the five account-level ones (``SEMANTICS_IDENTITY`` and the two audit
#: semantics) read the ACCOUNT and answer in all nine.
CATALOG: tuple[_Rule, ...] = (
    # -- S3 public exposure -------------------------------------------------------
    # These three were INSUFFICIENT_DATA until the Increment 3: the estate had the fifteen
    # s3_bucket RESOURCES and none of the ACL, bucket policy or Block Public Access they read.
    # The gap they carried is gone -- see ``_violacoes_s3`` for the published text each applies.
    _Rule(
        name="s3-bucket-public-read-prohibited",
        source_url="https://docs.aws.amazon.com/config/latest/developerguide/s3-bucket-public-read-prohibited.html",
        gap="",
        resource_type="s3_bucket",
        semantics=SEMANTICS_S3_PUBLIC_READ_PROHIBITED,
    ),
    _Rule(
        name="s3-bucket-public-write-prohibited",
        source_url="https://docs.aws.amazon.com/config/latest/developerguide/s3-bucket-public-write-prohibited.html",
        gap="",
        resource_type="s3_bucket",
        semantics=SEMANTICS_S3_PUBLIC_WRITE_PROHIBITED,
    ),
    _Rule(
        name="s3-bucket-level-public-access-prohibited",
        source_url="https://docs.aws.amazon.com/config/latest/developerguide/s3-bucket-level-public-access-prohibited.html",
        gap="",
        resource_type="s3_bucket",
        semantics=SEMANTICS_S3_BUCKET_LEVEL_PUBLIC_ACCESS,
    ),
    # -- network ------------------------------------------------------------------
    # These three were INSUFFICIENT_DATA until the Increment 2: the estate had the fifteen
    # security_group RESOURCES and none of the RULES the managed rules read. The gap they
    # carried is gone -- see ``SEMANTICS_*`` below for the published text each applies.
    _Rule(
        name="restricted-ssh",
        source_url="https://docs.aws.amazon.com/config/latest/developerguide/restricted-ssh.html",
        gap="",
        resource_type="security_group",
        semantics=SEMANTICS_RESTRICTED_SSH,
    ),
    _Rule(
        name="restricted-common-ports",
        source_url="https://docs.aws.amazon.com/config/latest/developerguide/restricted-common-ports.html",
        gap="",
        resource_type="security_group",
        semantics=SEMANTICS_RESTRICTED_COMMON_PORTS,
    ),
    _Rule(
        name="vpc-default-security-group-closed",
        source_url="https://docs.aws.amazon.com/config/latest/developerguide/vpc-default-security-group-closed.html",
        gap="",
        resource_type="security_group",
        semantics=SEMANTICS_DEFAULT_GROUP_CLOSED,
    ),
    # The FOURTH network rule, and the only one that reads the VPC rather than its groups. It was
    # the last network-shaped gap, closed by the Increment 4.3: the estate had fifteen ``vpc``
    # resources and none of them carried whether flow logging was configured on them. The page
    # publishes ``Resource Types: AWS::EC2::VPC``, so this is the one rule of the catalog that
    # answers NON_COMPLIANT because ONE sibling out of several is violating.
    _Rule(
        name="vpc-flow-logs-enabled",
        source_url="https://docs.aws.amazon.com/config/latest/developerguide/vpc-flow-logs-enabled.html",
        gap="",
        resource_type="vpc",
        semantics=SEMANTICS_VPC_FLOW_LOGS,
    ),
    # -- identity -----------------------------------------------------------------
    # These three were INSUFFICIENT_DATA until the Increment 4: the estate had NO identity
    # entity at all -- no root account, no IAM user, no password policy. The gap they carried
    # is gone, and unlike every other rule in this catalog they are answered from the ACCOUNT
    # rather than from a resource: IAM is global, so the same verdict is correct in each of the
    # account's regions. Their semantics live in ``_config_evaluators``, not here, because the
    # retrospective diagnostic has to reach them without duplicating the meaning.
    _Rule(
        name="root-account-mfa-enabled",
        source_url="https://docs.aws.amazon.com/config/latest/developerguide/root-account-mfa-enabled.html",
        gap="",
        semantics=SEMANTICS_IDENTITY,
    ),
    _Rule(
        name="iam-password-policy",
        source_url="https://docs.aws.amazon.com/config/latest/developerguide/iam-password-policy.html",
        gap="",
        semantics=SEMANTICS_IDENTITY,
    ),
    _Rule(
        name="access-keys-rotated",
        source_url="https://docs.aws.amazon.com/config/latest/developerguide/access-keys-rotated.html",
        gap="",
        semantics=SEMANTICS_IDENTITY,
    ),
    # -- audit / guardrails -------------------------------------------------------
    # These two were INSUFFICIENT_DATA until the Increment 4.3: the estate carried neither a
    # CloudTrail trail nor a Security Hub enrolment, so the estate could not assert either fact.
    # They are ACCOUNT-level -- both pages publish trigger ``Periodic`` and NO "Resource Types"
    # -- so they answer from ``estate.aws_audit_postures``, once per account, and repeat in each
    # of the account's regions exactly as the identity rules do.
    #
    # NOTE the name: the rule NAME is ``cloudtrail-enabled`` (no hyphen between "cloud" and
    # "trail"). The page says so in a box of its own -- "the rule identifier (CLOUD_TRAIL_ENABLED)
    # and rule name (cloudtrail-enabled) are different" -- because the IDENTIFIER is the
    # underscored one. This URL is the ``cloudtrail-enabled.html`` page, not the
    # ``cloud-trail-*.html`` one.
    _Rule(
        name="cloudtrail-enabled",
        source_url="https://docs.aws.amazon.com/config/latest/developerguide/cloudtrail-enabled.html",
        gap="",
        semantics=SEMANTICS_CLOUDTRAIL,
    ),
    _Rule(
        name="securityhub-enabled",
        source_url="https://docs.aws.amazon.com/config/latest/developerguide/securityhub-enabled.html",
        gap="",
        semantics=SEMANTICS_SECURITY_HUB,
    ),
    # -- evaluated from the estate ------------------------------------------------
    _Rule(
        name="s3-bucket-tagged",
        source_url="https://docs.aws.amazon.com/config/latest/developerguide/s3-bucket-tagged.html",
        gap="",
        resource_type="s3_bucket",
        semantics=SEMANTICS_TAGGED,
    ),
    _Rule(
        name="lambda-function-tagged",
        source_url="https://docs.aws.amazon.com/config/latest/developerguide/lambda-function-tagged.html",
        gap="",
        resource_type="lambda_function",
        semantics=SEMANTICS_TAGGED,
    ),
)


def catalog_names() -> tuple[str, ...]:
    """The catalog's rule names, in catalog order, with duplicates refused.

    This is the assertion that keeps the catalog honest: a repeated ``ConfigRuleName`` would
    mean the response lists the same rule twice for one scope, which the action does not do.
    """
    names = tuple(rule.name for rule in CATALOG)
    repeated = sorted({name for name in names if names.count(name) > 1})
    if repeated:
        raise RenderError(f"{RENDER_DIR}: regras repetidas no catalogo: {repeated}")
    return names


def specification() -> SurfaceSpec:
    """Load the cited specification for ``aws/config-describe-compliance-by-config-rule``."""
    return load_spec(SPEC_PATH)


def _names_of(scope: str) -> tuple[str, ...]:
    """Return a set's column names in documentation order, refusing to drop one.

    A column the documentation describes without contracting it must never reach an
    artifact, and a documented column must never be dropped: both are hard errors.
    """
    columns = specification().columns_for(scope)
    refused = tuple(column.name for column in columns if not column.belongs_to_schema)
    if refused:
        raise RenderError(
            f"{RENDER_DIR}: o conjunto {scope!r} da especificacao {SURFACE} marcou colunas "
            f"documentadas como fora do formato: {list(refused)}"
        )
    return tuple(column.name for column in columns)


# The five sets, in documentation order -- derived, not retyped.
_RESPONSE_COLUMNS: tuple[str, ...] = _names_of(RESPONSE_SCOPE)
_ITEM_COLUMNS: tuple[str, ...] = _names_of(ITEM_SCOPE)
_COMPLIANCE_COLUMNS: tuple[str, ...] = _names_of(COMPLIANCE_SCOPE)
_CONTRIBUTOR_COLUMNS: tuple[str, ...] = _names_of(CONTRIBUTOR_SCOPE)
_REQUEST_COLUMNS: tuple[str, ...] = _names_of(REQUEST_SCOPE)

#: The model facts each set may project. A non-null value anywhere else is a value the
#: canonical model does not carry -- :func:`_require_projection` fails closed on it. These sets
#: are therefore also the DEFINITIVE list of what this renderer is able to fill: a name absent
#: from one of them is emitted empty, by construction rather than by discipline.
_RESPONSE_PROJECTED: frozenset[str] = frozenset({"ComplianceByConfigRules"})
_ITEM_PROJECTED: frozenset[str] = frozenset({"ConfigRuleName", "Compliance"})
_COMPLIANCE_PROJECTED: frozenset[str] = frozenset({"ComplianceType", "ComplianceContributorCount"})
_CONTRIBUTOR_PROJECTED: frozenset[str] = frozenset({"CappedCount"})
_REQUEST_PROJECTED: frozenset[str] = frozenset()

#: Columns that belong to the file and may never receive a value (``evidence: null-empty``).
#: Empty for this surface: the nulls this renderer emits are MODEL gaps, argued in the module
#: docstring, not documentation claims.
_NULL_EMPTY: frozenset[str] = specification().null_empty_names

#: The verdicts this renderer writes, from the ``ComplianceType`` Valid Values. ``NOT_APPLICABLE``
#: is deliberately absent: the ``Compliance`` page states the type does not support it.
COMPLIANT = "COMPLIANT"
NON_COMPLIANT = "NON_COMPLIANT"
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"

#: The three documented reasons ``DescribeComplianceByConfigRule`` gives for INSUFFICIENT_DATA.
#: Only the first is an honest description of this simulator, and it is the one used below.
_GAP_NO_RESULTS = "no current evaluation results for the rule (INSUFFICIENT_DATA case 1)"
_GAP_NOT_APPLICABLE = "the rule has no resource of its type in this scope, so every evaluation is NOT_APPLICABLE, which the API reports as INSUFFICIENT_DATA (case 3)"

#: This renderer never writes ``NOT_APPLICABLE``, and the constant says so in code rather than
#: only in prose. The ``Compliance`` field lists it under Valid Values and the SAME page then
#: states that "AWS Config does not support the NOT_APPLICABLE value for the Compliance data
#: type"; ``DescribeComplianceByConfigRule`` documents that an all-NOT_APPLICABLE rule is
#: reported as ``INSUFFICIENT_DATA``. The request-side ``ComplianceTypes`` filter does accept
#: the value, which is exactly why the two are easy to conflate.
NOT_APPLICABLE_EMITTED = False


def _is_empty(value: Any) -> bool:
    """True when ``value`` is this fixture's shape for "no value" (never for zero).

    Zero is a REAL value here: ``CappedCount`` is 0 for a compliant rule and 0 for a rule with
    no results. Treating it as empty would hide both.
    """
    return value is None or value == "" or value == {} or value == []


def _require_projection(
    record: dict[str, Any],
    columns: tuple[str, ...],
    projected: frozenset[str],
    where: str,
) -> None:
    """Fail closed when a document is not exactly the set's members, or fills a gap.

    Two failures: a divergent member set (a documented member dropped, or a key no
    documentation defines) and a non-null value outside the model-backed ``projected`` names.
    The second is the fabrication rule of this package expressed in code.
    """
    fields = set(record)
    expected = set(columns)
    if fields != expected:
        raise RenderError(
            f"{RENDER_DIR}: {where} com campos diferentes do conjunto emitido: "
            f"sobram={sorted(fields - expected)} faltam={sorted(expected - fields)}"
        )
    filled = sorted(name for name in _NULL_EMPTY & fields if not _is_empty(record[name]))
    if filled:
        raise RenderError(f"{RENDER_DIR}: colunas null-empty receberam valor: {filled}")
    invented = sorted(name for name in fields if not _is_empty(record[name]) and name not in projected)
    if invented:
        raise RenderError(
            f"{RENDER_DIR}: {where} preencheu colunas sem fonte no modelo canonico "
            f"(lacuna, nao valor): {invented}"
        )


def countable_tags(resource: Resource) -> tuple[tuple[str, str], ...]:
    """The resource's tags the tagged managed rules are allowed to count.

    Both rule pages state "The rule does not check for tags starting with 'aws:'", so those are
    excluded here rather than assumed absent. The estate's own tags never start with ``aws:``,
    which means this filter does not change today's counts -- it is applied because the rule
    defines it, and a future estate that carried a reserved tag would otherwise be answered
    wrongly.
    """
    return tuple((key, value) for key, value in resource.tags if not key.lower().startswith(RESERVED_TAG_PREFIX))


@dataclass(frozen=True, slots=True)
class _Verdict:
    """One rule's answer for one (account, region) scope, and why."""

    compliance_type: str
    capped_count: int
    reason: str


def _permite_porta(rule: AwsIpPermission, porta: int) -> bool:
    """True when this INGRESS rule admits TCP ``porta``.

    Two cases, both published:

    * an explicit ``tcp`` rule, whose ``fromPort``/``toPort`` range covers the port. A missing
      bound means the range is open-ended on that side;
    * an all-protocol rule (``-1``), which the ``IpPermission`` page says "allows traffic on all
      ports, regardless of any port range you specify". Reading ``-1`` as "not TCP" would let a
      rule that plainly admits SSH pass the check.
    """
    if rule.ip_protocol == AWS_IP_PROTOCOL_ALL:
        return True
    if rule.ip_protocol != "tcp":
        return False
    if rule.from_port is not None and porta < rule.from_port:
        return False
    if rule.to_port is not None and porta > rule.to_port:
        return False
    return True


def _fontes_ipv4_de(rule: AwsIpPermission) -> tuple[str, ...]:
    """The IPv4 sources this ingress rule admits.

    Only ``IpRanges`` is read, and that is the whole of this estate's declared posture: no rule
    here resolves its source as IPv6, as a security-group reference or as a prefix list. A rule
    with no ``IpRanges`` admits nothing this check can see, which is what the published condition
    asks -- it tests "the IP addresses of the incoming traffic", and a SG-reference rule does not
    name one.
    """
    return tuple(entry.cidr_ip for entry in rule.ip_ranges)


def _violacoes_rede(semantics: str, groups: Sequence[AwsSecurityGroup]) -> tuple[list[str], str]:
    """The security groups that violate ``semantics``, and the published reason.

    Each branch applies ONE rule's own page, quoted above:

    ``restricted-ssh``
        "The rule is COMPLIANT if the IP addresses of the incoming SSH traffic in the security
        groups are restricted (CIDR other than 0.0.0.0/0 or ::/0). Otherwise, NON_COMPLIANT."

    ``restricted-common-ports``
        COMPLIANT if port access is blocked to all TCP traffic, or open only through Inbound
        rules whose source "does not cover all IPv4 addresses (0.0.0.0/0)" / "all IPv6 addresses
        (::/0)". With no rule parameters passed, the blocked ports are the page's own defaults
        (:data:`DEFAULT_BLOCKED_PORTS`).

    ``vpc-default-security-group-closed``
        "The rule is NON_COMPLIANT if the default security group has one or more inbound or
        outbound traffic rules." Only the DEFAULT group is evaluated -- the page scopes the rule
        to "the default security group of any Amazon Virtual Private Cloud" -- and AWS has no
        DENY rule, so the test is over BOTH lists.
    """
    violando: list[str] = []
    for group in groups:
        if semantics == SEMANTICS_DEFAULT_GROUP_CLOSED:
            if not group.is_default:
                continue  # so o grupo padrao que a regra avalia
            if group.ingress or group.egress:
                violando.append(group.group_id)
            continue
        portas = (22,) if semantics == SEMANTICS_RESTRICTED_SSH else DEFAULT_BLOCKED_PORTS
        for ingress in group.ingress:
            if not any(_permite_porta(ingress, item) for item in portas):
                continue
            if any(fonte in (CIDR_ALL_IPV4, CIDR_ALL_IPV6) for fonte in _fontes_ipv4_de(ingress)):
                violando.append(group.group_id)
                break

    if semantics == SEMANTICS_DEFAULT_GROUP_CLOSED:
        razao = (
            "a regra e NON_COMPLIANT se o grupo padrao da VPC tiver uma ou mais regras de entrada ou "
            "de saida, e a AWS nao publica regra de negacao, entao a verificacao e sobre as DUAS listas"
        )
    elif semantics == SEMANTICS_RESTRICTED_SSH:
        razao = (
            "a regra e COMPLIANT quando o trafego de SSH de entrada vem de um CIDR que nao cobre todos os "
            f"enderecos ({CIDR_ALL_IPV4} / {CIDR_ALL_IPV6})"
        )
    else:
        razao = (
            "a regra e COMPLIANT quando a porta bloqueada fica bloqueada para todo o trafego TCP, ou e "
            f"aberta so por Inbound rules cuja origem nao cobre {CIDR_ALL_IPV4} nem {CIDR_ALL_IPV6}"
        )
    return violando, razao


def _acl_concede_publica(posture: AwsBucketPosture, permissoes: frozenset[str]) -> bool:
    """``True`` when the bucket's EFFECTIVE ACL grants one of ``permissoes`` to everyone.

    The test is on the RECEIVER, not on the permission's name, because that is how the AWS
    page words it: "Amazon S3 considers a bucket or object ACL public if it grants any
    permissions to members of the predefined AllUsers or AuthenticatedUsers groups."

    It reads ``effective_grants()``, so a bucket whose ``IgnorePublicAcls`` is on is judged
    on the ACL the service ENFORCES -- the same ACL ``GetBucketAcl`` publishes. A consumer
    that read the STORED ACL instead would disagree on exactly those buckets, which is why
    the estate carries both and the rule reads the effective one.
    """
    publicos = frozenset(S3_PUBLIC_GROUP_URIS)
    return any(
        grant.uri in publicos and grant.permission in permissoes
        for grant in posture.effective_grants()
    )


def _policy_e_publico(posture: AwsBucketPosture, prefixos: tuple[str, ...]) -> bool:
    """``True`` when the bucket policy allows a matching action to a wildcard principal.

    ``AWS`` applies the evaluation as: "Amazon S3 begins by assuming that the policy is
    public. It then evaluates the policy to determine whether it qualifies as non-public."
    A grant that names the wildcard principal is public; a grant that names an account or a
    role ARN does not. Only ``Allow`` matters -- a ``Deny`` to ``*`` narrows access rather
    than granting it, and the rule asks whether public access is ALLOWED.
    """
    if posture.policy is None:
        return False
    for statement in posture.policy.statements:
        if statement.effect != "Allow":
            continue
        if S3_PRINCIPAL_WILDCARD not in statement.principals:
            continue
        if any(
            action in ("*", "s3:*") or action.startswith(prefixos) for action in statement.actions
        ):
            return True
    return False


def _violacoes_s3(
    semantics: str, postures: Sequence[AwsBucketPosture]
) -> tuple[list[str], str]:
    """The buckets that violate ``semantics``, and the published reason.

    Each branch applies ONE rule's own page. The two ``prohibited`` rules share one
    condition structure and differ only in the direction:

        "The rule is compliant when both of the following are true:
         + The Block Public Access setting restricts public policies OR the bucket policy
           does not allow public read access.
         + The Block Public Access setting restricts public ACLs OR the bucket ACL does not
           allow public read access."

    So the Block Public Access setting is the SHORT-CIRCUIT: when it restricts, the policy
    and the ACL are never consulted. That is why a bucket with ``BlockPublicPolicy`` on is
    COMPLIANT even while carrying a wildcard policy, and why the rule is a conjunction of
    two disjunctions rather than a check of the posture.

    ``s3-bucket-level-public-access-prohibited`` is the third form: "NON_COMPLIANT if an S3
    bucket is not listed in the ``excludedPublicBuckets`` parameter and bucket level settings
    are public". This renderer passes NO rule parameters, so the exclusion list is empty and
    the condition reduces to the settings being public -- in either direction.
    """
    leitura = semantics == SEMANTICS_S3_PUBLIC_READ_PROHIBITED
    permissao_acl, prefixos_policy = (
        (S3_PUBLIC_READ_PERMISSIONS, S3_READ_ACTION_PREFIXES)
        if leitura
        else (S3_PUBLIC_WRITE_PERMISSIONS, S3_WRITE_ACTION_PREFIXES)
    )
    violando: list[str] = []
    for posture in postures:
        if semantics == SEMANTICS_S3_BUCKET_LEVEL_PUBLIC_ACCESS:
            publico = (
                _acl_concede_publica(posture, S3_PUBLIC_READ_PERMISSIONS)
                or _acl_concede_publica(posture, S3_PUBLIC_WRITE_PERMISSIONS)
                or _policy_e_publico(posture, S3_READ_ACTION_PREFIXES)
                or _policy_e_publico(posture, S3_WRITE_ACTION_PREFIXES)
            )
            if publico:
                violando.append(posture.bucket_name)
            continue
        # Cada metade da conjuncao e um "ou" cujo primeiro termo e o block. O block nao
        # restringe -> o Config avalia o fato; o block restringe -> a metade passa.
        por_policy = not posture.public_access_block.restricts_public_policies and _policy_e_publico(
            posture, prefixos_policy
        )
        por_acl = not posture.public_access_block.restricts_public_acls and _acl_concede_publica(
            posture, permissao_acl
        )
        if por_policy or por_acl:
            violando.append(posture.bucket_name)
    if semantics == SEMANTICS_S3_BUCKET_LEVEL_PUBLIC_ACCESS:
        razao = (
            "a regra e NON_COMPLIANT se os settings de nivel de bucket forem publicos, e este renderer "
            "nao passa o parametro excludedPublicBuckets, entao nao ha bucket excluido"
        )
    elif semantics == SEMANTICS_S3_PUBLIC_READ_PROHIBITED:
        razao = (
            "a regra e COMPLIANT quando o BlockPublicPolicy restringe a policy OU ela nao da leitura publica, E o "
            "BlockPublicAcls restringe a ACL OU ela nao da leitura publica"
        )
    else:
        razao = (
            "a regra e COMPLIANT quando o BlockPublicPolicy restringe a policy OU ela nao da escrita publica, E o "
            "BlockPublicAcls restringe a ACL OU ela nao da escrita publica"
        )
    return violando, razao


def verdict(
    rule: _Rule,
    resources: list[Resource],
    groups_by_resource: Mapping[str, AwsSecurityGroup],
    postures_by_resource: Mapping[str, AwsBucketPosture],
    identity: AwsIdentityPosture | None = None,
    audit: AwsAuditPosture | None = None,
    flow_logs_by_resource: Mapping[str, AwsVpcFlowLog] | None = None,
    sim_now: date | None = None,
) -> _Verdict:
    """Answer ``rule`` over ``resources`` by applying the semantics AWS publishes.

    * a rule with no resource of its type has NOT evaluated anything, and the API reports that
      as ``INSUFFICIENT_DATA`` (:data:`_GAP_NOT_APPLICABLE`);
    * a rule the estate cannot read at all is ``INSUFFICIENT_DATA`` by the model gap;
    * otherwise the rule's own page decides -- :func:`_violacoes_rede` for the three network
      rules, the tag count below for the two tagged ones -- and the ``Compliance`` page's own
      wording turns a per-resource answer into a rule verdict: "A rule is compliant if all of the
      resources that the rule evaluates comply with it. A rule is noncompliant if any of these
      resources do not comply."

    THE ACCOUNT-LEVEL RULES ARE THE ONE CASE THAT DOES NOT GO THROUGH ``resources``. Five rules
    read the ACCOUNT rather than a resource -- the three identity ones (root MFA, password
    policy, access keys) and the two audit ones (CloudTrail, Security Hub) -- and the difference
    is published, not chosen: those five pages carry trigger ``Periodic`` and NO "Resource Types".
    IAM and both guardrails are configured per account, so each rule answers once per account and
    repeats the same verdict in each of that account's regions. A rule reading a global fact and
    returning a different verdict per region would be reporting something the AWS does not have.
    """
    if rule.semantics in _ACCOUNT_SEMANTICS:
        # The two account-level families are kept apart all the way through -- posture AND
        # evaluator -- rather than unified behind one variable. Both postures are per-account
        # state, so a merge point here is exactly where a rule could be answered out of the
        # other's facts without any type complaining: they have different types, but nothing
        # downstream would notice a swap.
        if rule.semantics == SEMANTICS_IDENTITY:
            if identity is None or sim_now is None:
                raise RenderError(
                    f"{RENDER_DIR}: a regra {rule.name} e por conta, e o escopo nao entregou "
                    "a postura de identidade nem o sim_now que a avalia"
                )
            answer = IAM_RULE_EVALUATORS[rule.name](identity, sim_now)
        else:
            if audit is None:
                raise RenderError(
                    f"{RENDER_DIR}: a regra {rule.name} e por conta, e o escopo nao entregou a "
                    "postura de auditoria que a avalia"
                )
            answer = ACCOUNT_AUDIT_RULE_EVALUATORS[rule.name](audit, sim_now)
        return _Verdict(
            compliance_type=answer.compliance_type,
            capped_count=len(answer.contributors),
            reason=answer.reason,
        )

    if not resources:
        return _Verdict(compliance_type=INSUFFICIENT_DATA, capped_count=0, reason=_GAP_NOT_APPLICABLE)
    if rule.gap:
        return _Verdict(compliance_type=INSUFFICIENT_DATA, capped_count=0, reason=rule.gap)

    if rule.semantics == SEMANTICS_TAGGED:
        violando = [resource for resource in resources if not countable_tags(resource)]
        razao = (
            "a regra e NON_COMPLIANT se o recurso nao tem tags; "
            f"{len(violando)} de {len(resources)} recursos do escopo nao tem tag contavel"
        )
        razao_ok = "a regra e COMPLIANT quando todos os recursos que ela avalia tem tags"
    elif rule.semantics == SEMANTICS_VPC_FLOW_LOGS:
        # Fail closed on the join, for the reason the VPC rule is different from the other three:
        # a ``vpc`` resource with no flow-log configuration would make the rule answer about a
        # VPC whose logging it cannot see -- and would turn a KNOWN non-compliance (a VPC with no
        # flow log) into an unmeasurable one. The empty ``flow_log_ids`` is the NON_COMPLIANT
        # fact; a MISSING posture is a hole in the estate, and those are two different states.
        if flow_logs_by_resource is None:
            raise RenderError(
                f"{RENDER_DIR}: a regra {rule.name} le VPCs e o escopo nao entregou a tabela de "
                "flow logs"
            )
        ausentes = [item for item in resources if item.identity.uuid not in flow_logs_by_resource]
        if ausentes:
            raise RenderError(
                f"{RENDER_DIR}: {len(ausentes)} recursos vpc do escopo nao tem configuracao de "
                "flow log correspondente em estate.aws_vpc_flow_logs; a regra leria uma VPC sem fato"
            )
        logs = [flow_logs_by_resource[item.identity.uuid] for item in resources]
        # UMA avaliacao por VPC, pelo avaliador COMPARTILHADO -- o mesmo modulo que responde as
        # regras de identidade e de auditoria, e pelo mesmo motivo: a semantica mora em um lugar
        # so. O agregado ("at least one Amazon VPC") e trabalho do renderer, e vem da pagina do
        # ``Compliance``, nao do avaliador -- que por sua vez devolve COMPLIANT ou NON_COMPLIANT
        # de UMA VPC e nunca o terceiro valor.
        respostas = [VPC_FLOW_LOG_RULE_EVALUATORS[rule.name](log, sim_now) for log in logs]
        reprovadas = [
            log.vpc_id
            for log, resposta in zip(logs, respostas, strict=True)
            if resposta.compliance_type == NON_COMPLIANT
        ]
        violando = [item for item, log in zip(resources, logs, strict=True) if log.vpc_id in reprovadas]
        if reprovadas:
            razao = (
                "a regra e NON_COMPLIANT se o flow log nao esta habilitado para pelo menos uma "
                f"VPC; {len(reprovadas)} de {len(logs)} VPC(s) do escopo nao tem flow log: "
                + ", ".join(reprovadas)
            )
        else:
            razao = (
                "a regra e COMPLIANT quando todas as VPCs que ela avalia tem flow log habilitado; "
                f"as {len(logs)} VPC(s) do escopo tem"
            )
        razao_ok = razao
    elif rule.resource_type == "s3_bucket":
        # Fail closed on the join: an s3_bucket resource with no posture in the estate would
        # make the rule answer about a bucket whose ACL, policy and block it cannot see.
        ausentes = [item for item in resources if item.identity.uuid not in postures_by_resource]
        if ausentes:
            raise RenderError(
                f"{RENDER_DIR}: {len(ausentes)} recursos s3_bucket do escopo nao tem postura "
                "correspondente em estate.aws_bucket_postures; a regra leria um recurso sem fato"
            )
        violando_nomes, razao = _violacoes_s3(
            rule.semantics, [postures_by_resource[item.identity.uuid] for item in resources]
        )
        culpados = set(violando_nomes)
        violando = [
            item
            for item in resources
            if postures_by_resource[item.identity.uuid].bucket_name in culpados
        ]
        razao_ok = razao
    else:
        # Fail closed on the join: a security_group resource with no rule in the estate would
        # make the rule answer about a group whose posture it cannot see.
        ausentes = [item for item in resources if item.identity.uuid not in groups_by_resource]
        if ausentes:
            raise RenderError(
                f"{RENDER_DIR}: {len(ausentes)} recursos security_group do escopo nao tem regra "
                "correspondente em estate.aws_security_groups; a regra leria um recurso sem fato"
            )
        violando_ids, razao = _violacoes_rede(
            rule.semantics, [groups_by_resource[item.identity.uuid] for item in resources]
        )
        culpados = set(violando_ids)
        violando = [
            item for item in resources if groups_by_resource[item.identity.uuid].group_id in culpados
        ]
        razao_ok = razao

    if violando:
        return _Verdict(compliance_type=NON_COMPLIANT, capped_count=len(violando), reason=razao)
    return _Verdict(compliance_type=COMPLIANT, capped_count=0, reason=razao_ok)


def _resources_by_scope(estate: CanonicalEstate) -> dict[tuple[str, str], list[Resource]]:
    """The estate's AWS resources grouped by (account, region), in deterministic order.

    One group per (account, region) because that is the scope of an AWS Config call: the
    recorder and the rules are configured per account AND per region, so one account's resources
    in three regions are three rule sets, not one. This is the same granularity
    ``render/ec2_instances.py`` uses for the same reason.
    """
    grouped: dict[tuple[str, str], list[Resource]] = {}
    for resource in estate.resources:
        if resource.identity.provider != PROVIDER_KEY_AWS:
            continue
        grouped.setdefault((resource.parent_scope_id, resource.region_id), []).append(resource)
    return {
        scope: sorted(items, key=lambda item: item.identity.logical_path)
        for scope, items in sorted(grouped.items())
    }


def _contributor_count(capped_count: int) -> dict[str, Any]:
    """Return the documented ``ComplianceContributorCount`` object.

    ``CappedCount`` is the model's own count of the resources that CAUSE the NON_COMPLIANT
    result, which is how the ``Compliance`` page describes this object -- not a total of the
    resources evaluated.

    ``CapExceeded`` is null by construction. The ``ComplianceContributorCount`` page says only
    "up to a maximum number" and never publishes that maximum, so the boolean it documents --
    "Indicates whether the maximum count is reached" -- cannot be computed from the
    documentation. Writing ``false`` here would assert that no ceiling was reached, which is a
    claim about an unpublished number.
    """
    return {"CapExceeded": None, "CappedCount": capped_count}


def _compliance(answer: _Verdict) -> dict[str, Any]:
    """Return the documented ``Compliance`` object of one rule."""
    record: dict[str, Any] = {
        "ComplianceType": answer.compliance_type,
        "ComplianceContributorCount": _contributor_count(answer.capped_count),
    }
    _require_projection(record, _COMPLIANCE_COLUMNS, _COMPLIANCE_PROJECTED, f"Compliance {answer.compliance_type}")
    return record


def _item(
    rule: _Rule,
    resources: list[Resource],
    groups_by_resource: Mapping[str, AwsSecurityGroup],
    postures_by_resource: Mapping[str, AwsBucketPosture],
    identity: AwsIdentityPosture | None = None,
    audit: AwsAuditPosture | None = None,
    flow_logs_by_resource: Mapping[str, AwsVpcFlowLog] | None = None,
    sim_now: date | None = None,
) -> dict[str, Any]:
    """Return the 2-member ``ComplianceByConfigRule`` object of one rule in one scope."""
    record: dict[str, Any] = {
        "ConfigRuleName": rule.name,
        "Compliance": _compliance(
            verdict(
                rule,
                resources,
                groups_by_resource,
                postures_by_resource,
                identity,
                audit,
                flow_logs_by_resource,
                sim_now,
            )
        ),
    }
    _require_projection(record, _ITEM_COLUMNS, _ITEM_PROJECTED, f"regra {rule.name}")
    return record


def _request_parameters() -> dict[str, Any]:
    """Return the documented request parameters as a SHAPE fixture (all values null).

    These three names belong to the REQUEST side of the action; the estate models no captured
    request, so every value is null. The document exists so the request vocabulary is present
    and the gap is testable rather than silently absent. ``ConfigRuleNames`` is NOT filled with
    the catalog: the rules this renderer evaluates are its own scope, not a request anybody
    captured.
    """
    document: dict[str, Any] = dict.fromkeys(_REQUEST_COLUMNS)
    _require_projection(document, _REQUEST_COLUMNS, _REQUEST_PROJECTED, "parametros de requisicao")
    return document


def _write_text(path: Path, text: str, written: list[Path]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if path not in written:
        written.append(path)


class ConfigComplianceByRuleRenderer:
    """Renders the canonical estate's AWS posture as DescribeComplianceByConfigRule fixtures."""

    name = "config_compliance_by_rule"

    def render(self, estate: CanonicalEstate, out_dir: Path) -> list[Path]:
        """Write the fixtures under ``out_dir/config_compliance_by_rule/``; return written paths."""
        target = out_dir / RENDER_DIR
        written: list[Path] = []
        responses: list[dict[str, Any]] = []
        items: list[dict[str, Any]] = []
        compliances: list[dict[str, Any]] = []
        counts: list[dict[str, Any]] = []
        names = catalog_names()
        # The Increment 2 made the three network rules answerable: the estate now carries the
        # RULES of its security groups, keyed by the resource they belong to.
        groups_by_resource: dict[str, AwsSecurityGroup] = {
            group.resource_uuid: group for group in estate.aws_security_groups
        }
        # The Increment 3 gave the three S3 exposure rules their missing fact: the ACL, the
        # bucket policy and the Block Public Access configuration of every bucket.
        postures_by_resource: dict[str, AwsBucketPosture] = {
            posture.resource_uuid: posture for posture in estate.aws_bucket_postures
        }

        # The Increment 4 gave the three identity rules their missing fact: each account's root
        # MFA, password policy, IAM users and access keys. IAM is GLOBAL, so the posture is
        # keyed by account and NOT repeated per region -- the account's regions read the same
        # verdict, which is what the AWS would report.
        identities_by_account: dict[str, AwsIdentityPosture] = {
            posture.account_id: posture for posture in estate.aws_identity_postures
        }
        # The Increment 4.3 added the other account-level half: the CloudTrail trails and the
        # Security Hub enrolment of each account. Keyed by account for the same reason as the
        # identity postures -- both audit rules publish trigger ``Periodic`` and NO "Resource
        # Types", so they are configured per ACCOUNT and their verdict repeats in each region.
        audits_by_account: dict[str, AwsAuditPosture] = {
            posture.account_id: posture for posture in estate.aws_audit_postures
        }
        # ...and the VPC-level rule: flow-log configuration per ``vpc`` RESOURCE, the join the
        # S3 and security-group rules already use.
        flow_logs_by_resource: dict[str, AwsVpcFlowLog] = {
            log.resource_uuid: log for log in estate.aws_vpc_flow_logs
        }

        for (account_id, _region), scope_resources in _resources_by_scope(estate).items():
            if account_id not in identities_by_account:
                raise RenderError(
                    f"{RENDER_DIR}: a conta {account_id} do escopo nao tem postura de identidade "
                    "em estate.aws_identity_postures; as regras de IAM leriam uma conta sem fato"
                )
            if account_id not in audits_by_account:
                raise RenderError(
                    f"{RENDER_DIR}: a conta {account_id} do escopo nao tem postura de auditoria em "
                    "estate.aws_audit_postures; as regras de CloudTrail e Security Hub leriam uma "
                    "conta sem fato"
                )
            posture_identidade = identities_by_account[account_id]
            postura_auditoria = audits_by_account[account_id]
            scope_items: list[dict[str, Any]] = []
            for rule in CATALOG:
                relevant = (
                    []
                    if rule.resource_type is None
                    else [item for item in scope_resources if item.resource_type == rule.resource_type]
                )
                record = _item(
                    rule,
                    relevant,
                    groups_by_resource,
                    postures_by_resource,
                    posture_identidade,
                    postura_auditoria,
                    flow_logs_by_resource,
                    estate.sim_now,
                )
                scope_items.append(record)
                items.append(record)
                compliances.append(record["Compliance"])
                counts.append(record["Compliance"]["ComplianceContributorCount"])
            responses.append(
                {
                    "ComplianceByConfigRules": scope_items,
                    # The documented value for "there are no more items to return": each
                    # envelope carries its scope's whole rule set in one page.
                    "NextToken": None,
                }
            )

        for response in responses:
            _require_projection(response, _RESPONSE_COLUMNS, _RESPONSE_PROJECTED, "envelope de resposta")
        for count in counts:
            _require_projection(count, _CONTRIBUTOR_COLUMNS, _CONTRIBUTOR_PROJECTED, "ComplianceContributorCount")

        _write_text(
            target / "describe-compliance-by-config-rule-response.json",
            json.dumps(responses, indent=2, ensure_ascii=False) + "\n",
            written,
        )
        _write_text(
            target / "compliance-by-config-rule.json",
            json.dumps(items, indent=2, ensure_ascii=False) + "\n",
            written,
        )
        _write_text(
            target / "compliance.json",
            json.dumps(compliances, indent=2, ensure_ascii=False) + "\n",
            written,
        )
        _write_text(
            target / "compliance-contributor-count.json",
            json.dumps(counts, indent=2, ensure_ascii=False) + "\n",
            written,
        )
        _write_text(
            target / "request-parameters.json",
            json.dumps(_request_parameters(), indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            written,
        )
        written.append(self._write_provenance(target, estate, len(responses), len(names)))
        return written

    def _write_provenance(self, target: Path, estate: CanonicalEstate, scopes: int, rules: int) -> Path:
        """Write the sibling provenance report: the spec, the mechanism, the counts, the gaps.

        The reasons live HERE and not in the artifact: an ingestor of the fixture must not see a
        key no cloud documents. It is this file that says which twelve rules could not be
        answered and why, which is the most important thing this surface produced.
        """
        report: dict[str, Any] = {
            "kind": "provenance",
            "surface": SURFACE,
            "spec": "specs/aws/config-describe-compliance-by-config-rule.schema.json",
            "artifacts": [
                "describe-compliance-by-config-rule-response.json",
                "compliance-by-config-rule.json",
                "compliance.json",
                "compliance-contributor-count.json",
                "request-parameters.json",
            ],
            "mechanism": {
                "action": "config:DescribeComplianceByConfigRule",
                "granularity": "one ComplianceByConfigRule item per managed rule per (account, region) scope",
                "scope": "the estate's own (account, region) grouping: AWS Config configures recorder and rules per account and region",
                "verdict_source": "the Compliance page's published semantics, not a local rule",
                "not_applicable": "never emitted: the Compliance page states the type does not support NOT_APPLICABLE",
                "managed_rules_checked_against": MANAGED_RULES_URL,
            },
            "counts": {
                "rules": rules,
                "scopes": scopes,
                "items": rules * scopes,
                "evaluated_rules": [rule.name for rule in CATALOG if not rule.gap],
                "unevaluable_rules": [rule.name for rule in CATALOG if rule.gap],
            },
            "model_gaps": [
                {"rule": rule.name, "reason": rule.gap, "source_url": rule.source_url}
                for rule in CATALOG
                if rule.gap
            ]
            + [
                {
                    "field": "ComplianceContributorCount.CapExceeded",
                    "reason": (
                        "a pagina ComplianceContributorCount descreve CapExceeded como 'Indicates whether "
                        "the maximum count is reached', mas nao publica esse maximo -- so diz 'up to a "
                        "maximum number'. A comparacao nao e reproduzivel a partir da documentacao, e o "
                        "booleano fica null."
                    ),
                    "source_url": "https://docs.aws.amazon.com/config/latest/APIReference/API_ComplianceContributorCount.html",
                },
                {
                    "field": "request-parameters",
                    "reason": (
                        "ComplianceTypes, ConfigRuleNames e NextToken pertencem ao lado de REQUISICAO da "
                        "acao; o estate nao modela nenhuma requisicao capturada, entao os tres vao null. "
                        "ConfigRuleNames NAO e preenchido com o catalogo deste renderer: as regras "
                        "avaliadas aqui sao o escopo dele, nao uma requisicao que alguem fez."
                    ),
                    "source_url": "https://docs.aws.amazon.com/config/latest/APIReference/API_DescribeComplianceByConfigRule.html",
                },
                {
                    "field": f"{RESPONSE_SCOPE}.NextToken",
                    "reason": _GAP_NO_RESULTS
                    + " -- aqui a ausencia de paginacao e o valor documentado para 'nao ha mais itens'.",
                    "source_url": "https://docs.aws.amazon.com/config/latest/APIReference/API_DescribeComplianceByConfigRule.html",
                },
            ],
            "not_generated": [],
        }
        path = target / PROVENANCE_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return path