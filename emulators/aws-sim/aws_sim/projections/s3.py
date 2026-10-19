"""The S3 projection: what the estate says about buckets, as opposed to what it holds.

The estate's objects are not in the estate — they are the rendered FOCUS artefacts on the
volume (``aws_sim.s3_store``). What the estate *does* carry about S3 is its
``s3_bucket`` resources, and that is what this module projects: the bucket list, each
bucket's owning account and creation instant, and the three bucket-level settings the
auditing call sites ask for.

Five decisions, each one a place a plausible-looking alternative is wrong:

* **A bucket's NAME is its AWS id, not ``Resource.resource_name``.** The estate restarts
  its per-scope counter for every account (``generate/estate_builder.py``), so
  ``s3_bucket-0004`` exists in three accounts — and an S3 bucket name is *globally*
  unique, so three accounts answering that name is not a bucket the estate has three of,
  it is one name the estate cannot mean. ``ids.resource_id`` mints ``bucket-<17 hex>``
  from the resource's own identity, which is exactly the value ``arns.resource_arn``
  already publishes for an ``s3_bucket`` (``arn:aws:s3:::bucket-…``, region and account
  empty because the name is global). Answering the id therefore makes the name
  ``list_buckets`` reports and the ARN the tagging API reports ONE value, which is the
  discipline :mod:`aws_sim.ids` exists to hold. It is also the only addressable choice:
  ``resource_name`` is off-standard by design (FR-D3 — ``s3_bucket-0019 (do not delete)``
  is a real name in the estate), and ``boto3`` refuses that name outright
  (``botocore.handlers.validate_bucket_name``, regex ``^[a-zA-Z0-9.\\-_]{1,255}$``), so a
  caller handed it could not even issue the follow-up call.
* **``CreationDate`` is the earliest day the estate billed the bucket**, when it billed it
  at all. The canonical model carries no creation instant for a resource, and
  ``scope.first_charge`` exists for precisely this projection (its docstring names
  ``CreatedTime``/``CreatedAt``); the alternative candidate, ``sim_start``, would claim
  every bucket was created on the day the window opens. A bucket with no line is listed
  with no ``CreationDate`` — absence is absence, and real S3 always sending the element
  does not make inventing one honest.
* **``Owner`` is the account the request was SIGNED with**, decoded from the SigV4
  ``Credential`` by STS's own rule (``projections.sts.parse_access_key`` +
  ``account_from_access_key``) — the same key this shim minted for ``AssumeRole``. The
  buckets themselves are *not* filtered by it: one endpoint serves every account, and
  ``ec2.DescribeInstances`` answers the same way (every account's instances, each
  carrying its ``OwnerId``). Filtering here would hide two thirds of the estate from the
  security scan that lists buckets and audits each one. An unsigned request falls back to
  the estate's first account, which is the fallback ``GetCallerIdentity`` already uses.
* **Every bucket's ACL is the private default**, because the estate models no ACL. There
  is no ACL, bucket-policy or public-access vocabulary anywhere in
  ``tools/synthetic_clouds`` (``generate``, ``scenarios``, ``model``, ``seed`` all lack
  it), and the one "public bucket" the estate does declare is a **GCP** finding
  (``scenarios/emit.py::_apply_c09_findings`` binds it to a ``gcp`` resource), so there is
  no AWS bucket the estate says is public and no grant to invent. What is answered is the
  ACL S3 itself gives a bucket nobody has changed — the owner's ``FULL_CONTROL`` and
  nothing else. S3 has no such thing as a bucket without an ACL, which is why this one is
  derived rather than reported absent; the two *optional* settings below are the ones that
  are absent.
* **No bucket policy and no public access block exist**, so ``get_bucket_policy`` and
  ``get_public_access_block`` answer ``NoSuchBucketPolicy`` and
  ``NoSuchPublicAccessBlockConfiguration``. Those are not stubs: they are the two codes
  the auditing call sites branch on deliberately
  (``security.py (modulo do consumidor):218`` and ``:304``), they are what a real untouched bucket
  answers, and the alternative — four invented ``true`` settings or a synthesized policy
  document — would be this module asserting configuration the estate never expressed.

The ACL's canonical user id is DERIVED, in the shape AWS uses: 64 hex characters, minted
with ``arns.stable_digest`` from the account so that the same account reports the same id
in the bucket owner and in every grant. ``TODO-verificar``: as with
``model/identity.capacity_reservation_id``, this is a derived id in a documented shape,
not an official AWS identifier.
"""

from __future__ import annotations

from datetime import datetime

from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.resource import Resource

from aws_sim import arns, ids, scope
from aws_sim.projections import sts

#: The estate ``resource_type`` this module owns.
BUCKET_TYPE = "s3_bucket"

#: Length of an AWS canonical user id (it is the full SHA-256 hex digest).
CANONICAL_USER_ID_LENGTH = 64


def buckets(estate: CanonicalEstate) -> tuple[Resource, ...]:
    """The estate's S3 bucket resources, in the order their names sort."""
    owned = (r for r in scope.resources(estate) if r.resource_type == BUCKET_TYPE)
    return tuple(sorted(owned, key=bucket_name))


def bucket_name(resource: Resource) -> str:
    """The bucket name the estate means for ``resource`` (see the module docstring)."""
    return ids.resource_id(resource)


def names(estate: CanonicalEstate) -> tuple[str, ...]:
    """Every bucket name the estate carries, deduplicated and sorted.

    Deduplication is a consequence of the names being ids rather than labels: two
    ``s3_bucket`` resources are two buckets, so their ids differ, and the same name
    appearing twice could only mean one list entry emitted twice.
    """
    return tuple(sorted({bucket_name(resource) for resource in buckets(estate)}))


def owner_accounts(estate: CanonicalEstate) -> dict[str, str]:
    """Bucket name -> the AWS account that owns it."""
    return {bucket_name(resource): resource.parent_scope_id for resource in buckets(estate)}


def creation(estate: CanonicalEstate) -> dict[str, datetime]:
    """Bucket name -> the earliest charge period the estate billed it for.

    A bucket the estate never billed is absent from the mapping, and
    :func:`aws_sim.api.s3` leaves ``CreationDate`` out rather than filling it in —
    ``scope.first_charge`` returns what the estate asserts and nothing else.
    """
    first = scope.first_charge(estate)
    return {
        bucket_name(resource): first[resource.identity.uuid]
        for resource in buckets(estate)
        if resource.identity.uuid in first
    }


def canonical_user_id(account: str) -> str:
    """The canonical user id of ``account``, in AWS's 64-hex-character shape."""
    return arns.stable_digest(f"canonical-user:{account}", length=CANONICAL_USER_ID_LENGTH)


def caller_account(estate: CanonicalEstate, authorization: str | None) -> str:
    """The account the request was signed with, or the estate's first account.

    ``authorization`` is the raw SigV4 header. A key the shim did not mint (a smoke
    request signed with anything else) decodes to nothing, and the fallback is the same
    one ``GetCallerIdentity`` uses so the two never disagree about who the caller is.
    """
    access_key = sts.parse_access_key(authorization)
    account = sts.account_from_access_key(access_key) if access_key else None
    if account is not None:
        return account
    known = sorted(scope.scope_ids(estate))
    return known[0] if known else "000000000000"


def bucket_account(estate: CanonicalEstate, bucket: str, *, fallback: str) -> str:
    """The account to name as ``bucket``'s owner, the caller's account otherwise.

    A bucket the estate carries names its own owner; the artefact bucket (the uploader's
    target) belongs to no estate account, so it borrows the caller's — the only account
    the emulator can defensibly name for it.
    """
    return owner_accounts(estate).get(bucket, fallback)
