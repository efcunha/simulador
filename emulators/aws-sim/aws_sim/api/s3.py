"""The S3 surface, served on the ONE endpoint every AWS client is pointed at.

**The architectural crux, and the choice made about it.** ``AWS_SERVICE_ENDPOINT``
(``endpoint.py (modulo do consumidor)``) is a single endpoint for every AWS
service — ``boto3`` accepts ``endpoint_url`` per ``client()``/``resource()`` and nowhere
else, so there is no per-service override available to give S3 one of its own. FinOps
S3 client (``AWSClient.client("s3")``, used by ``<modulo do consumidor>``,
``<modulo do consumidor>``, ``<modulo do consumidor>``, ``<modulo do consumidor>``
and the security policy engine) therefore lands **here**, on the port that already serves
Query, JSON-1.1, JSON-1.0 and RPC-v2 CBOR. The ``s3mock`` container beside it in
``deploy/synthetic-clouds/compose.aws.yaml`` is unreachable from a client built that way.

Between proxying S3 to ``s3mock`` and serving it here over the artefacts the uploader
already put on this container's own volume, this module serves it here;
:mod:`aws_sim.s3_store` records the trade-off (a second copy of the tree, and a store
setting that has to stay pointed at the uploader's source directory, in exchange for an
answer that is a pure function of the rendered tree — deterministic, testable with no
container, and unaffected by ``s3mock`` being down).

**Routing is by path, because that is what S3 is.** The three wires already here dispatch
on a form ``Action`` or an ``X-Amz-Target`` header; S3 carries the operation in the URL,
which is why this is a separate router rather than another branch of ``/``:

* ``GET /`` -> ``ListBuckets``
* ``GET /{bucket}?list-type=2`` -> ``ListObjectsV2``
* ``GET /{bucket}?acl`` / ``?policy`` / ``?publicAccessBlock`` -> that bucket's settings
* ``GET /{bucket}/{key}`` -> ``GetObject`` (path-style addressing, which is the shape
  ``AWS_S3_FORCE_PATH_STYLE`` puts the client in and the only shape that can work when
  the endpoint is a host with a single name)

**This router is registered LAST, and that order is load-bearing.** ``GET
/federation/credentials`` (SSO), ``GET /clusters`` (EKS) and Lambda's
``GET /2015-03-31/functions/`` are REST-JSON paths that are also ``/{bucket}`` or
``/{bucket}/{key}`` as far as a template match is concerned, and Starlette resolves in
registration order. Registering this router last lets each service answer its own path;
the alternative — sniffing the request for an S3 marker — would have to guess, and a wrong
guess hands an SSO caller an XML error.

**Absence is answered as absence, in the shape the caller reads it.** ``list_buckets``
returns the estate's buckets (never a fabricated one, and a well-formed empty ``Buckets``
when the estate has none). ``list_objects_v2`` reads the store: a bucket with no artefacts
gets ``KeyCount 0`` and no ``Contents``, and a bucket the estate does not have at all gets
the same well-formed empty page rather than ``NoSuchBucket`` — the reader
``CurS3Reader`` is constructed with a bucket name from configuration, so "no exports under
that prefix" is exactly the statement the estate is making, and inventing an object (or a
bucket name) is what this refuses. ``get_object`` is the one that must not answer empty:
its caller parses the body as the export, so a missing key is ``NoSuchKey`` rather than
zero bytes, which would read as a bill with no rows instead of as a missing file. The
asymmetry is deliberate and its cost is stated: a typo'd bucket name is not detectable from
the listing, where real S3 would refuse it.

The two ``NoSuch*`` codes the auditing callers branch on — ``NoSuchBucketPolicy``
(``security.py (modulo do consumidor):304``) and ``NoSuchPublicAccessBlockConfiguration``
(``:218``, and ``security_policy_engine.py (modulo do consumidor):99``) — are answered for every
bucket, because the estate declares neither setting anywhere;
:mod:`aws_sim.projections.s3` records that reading and what an invented one would cost.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import Response
from tools.synthetic_clouds.model.estate import CanonicalEstate

from aws_sim import s3_rest_xml as wire
from aws_sim.projections import s3 as projection
from aws_sim.s3_store import DEFAULT_MAX_KEYS, Listing, S3Store, decode_token, effective_max_keys

router = APIRouter()

#: What ``PutObject`` with no ``ContentType`` stores, which is how ``aws_sim.upload``
#: writes every artefact — so this is the type the tree was uploaded with rather than a
#: guess from the file extension.
_UPLOADED_CONTENT_TYPE = "binary/octet-stream"


def _xml(content: str, status_code: int = 200) -> Response:
    return Response(content=content, media_type=wire.CONTENT_TYPE, status_code=status_code)


def _error(error: wire.S3Error) -> Response:
    return _xml(error.render(), error.status_code)


def _empty_page() -> Listing:
    """The page a bucket with no artefacts in it answers."""
    return Listing(objects=(), common_prefixes=(), is_truncated=False, next_token=None)


def _store(request: Request) -> S3Store:
    """The artefact store this app was configured with (an unset setting -> no store)."""
    settings = request.app.state.settings
    root = Path(settings.s3_store_dir) if settings.s3_store_dir else None
    return S3Store(root, settings.s3_bucket)


def _known_buckets(estate: CanonicalEstate, store: S3Store) -> tuple[str, ...]:
    """Every bucket this plane has: the estate's, plus the one the store holds."""
    return tuple(sorted(set(projection.names(estate)) | set(store.buckets)))


def _max_keys(raw: str | None) -> int | None:
    """``MaxKeys`` as an effective page size, or ``None`` when the caller sent nonsense.

    ``None`` rather than a fallback so the caller answers ``InvalidArgument``: a parameter
    that arrived and could not be read is not the same request as one that never arrived.
    """
    if raw is None or not raw.strip():
        return effective_max_keys(DEFAULT_MAX_KEYS)
    try:
        return effective_max_keys(int(raw))
    except ValueError:
        return None


@router.get("/")
async def list_buckets(request: Request) -> Response:
    """``ListBuckets`` — the estate's buckets, in name order.

    ``Owner`` names the account the request was signed with (STS's own decode of the
    SigV4 credential); the buckets are not filtered by it, for the reason
    :mod:`aws_sim.projections.s3` records.
    """
    estate: CanonicalEstate = request.app.state.estate
    created = projection.creation(estate)
    listed = [(name, created.get(name)) for name in _known_buckets(estate, _store(request))]
    owner = projection.caller_account(estate, request.headers.get("authorization"))
    return _xml(wire.render_list_buckets(listed, owner_id=owner))


@router.get("/{bucket}")
async def bucket_request(request: Request, bucket: str) -> Response:
    """The bucket-level operations, told apart by the query parameter S3 uses for each."""
    params = request.query_params
    if "publicAccessBlock" in params:
        return _public_access_block(request, bucket)
    if "acl" in params:
        return _bucket_acl(request, bucket)
    if "policy" in params:
        return _bucket_policy(request, bucket)
    if params.get("list-type") == "2":
        return _list_objects_v2(request, bucket)
    return _error(
        wire.invalid_request(
            "This simulator serves GET /{bucket} with list-type=2, acl, policy or "
            f"publicAccessBlock; got {sorted(params.keys())} for bucket {bucket}.",
        ),
    )


@router.get("/{bucket}/{key:path}")
async def get_object(request: Request, bucket: str, key: str) -> Response:
    """``GetObject`` — the artefact's bytes, or ``NoSuchKey``.

    The bytes are the file on the volume, verbatim: nothing here re-encodes or re-renders
    them, because the caller parses them as the provider's export.
    """
    estate: CanonicalEstate = request.app.state.estate
    store = _store(request)
    if bucket not in _known_buckets(estate, store):
        return _error(wire.no_such_bucket(bucket))
    found = store.read(key)
    if found is None:
        return _error(wire.no_such_key(bucket, key))
    return Response(
        content=found.body,
        media_type=_UPLOADED_CONTENT_TYPE,
        headers={
            "ETag": wire.etag_of(found.summary.etag),
            "Last-Modified": wire.http_date(found.summary.last_modified),
            "Accept-Ranges": "bytes",
            "Content-Length": str(found.summary.size),
        },
    )


def _list_objects_v2(request: Request, bucket: str) -> Response:
    """``ListObjectsV2`` — the store's objects under ``prefix``, in S3's page shape."""
    params = request.query_params
    prefix = params.get("prefix", "")
    delimiter = params.get("delimiter", "")
    encoding_type = params.get("encoding-type", "")
    continuation = params.get("continuation-token", "")
    start_after = params.get("start-after", "")
    max_keys = _max_keys(params.get("max-keys"))
    if max_keys is None:
        return _error(wire.invalid_argument("max-keys", params.get("max-keys", "")))

    estate: CanonicalEstate = request.app.state.estate
    store = _store(request)
    # The continuation token wins over ``start-after`` when both are present, which is what
    # S3 specifies: the token already encodes where the last page stopped.
    resume = (decode_token(continuation) if continuation else None) or start_after

    if bucket in _known_buckets(estate, store) and store.lists(bucket):
        listing = store.listing(prefix=prefix, delimiter=delimiter, max_keys=max_keys, start_after=resume)
    else:
        # No bucket, or the estate's bucket that the artefact store does not hold: both
        # are the estate having nothing there, which is an empty page — not a fabricated
        # object and not an error the reader would have to special-case.
        listing = _empty_page()

    return _xml(
        wire.render_list_objects_v2(
            listing,
            bucket=bucket,
            prefix=prefix,
            delimiter=delimiter,
            max_keys=max_keys,
            encoding_type=encoding_type,
            continuation_token=continuation,
            start_after=start_after,
        ),
    )


def _bucket_acl(request: Request, bucket: str) -> Response:
    """``GetBucketAcl`` — the private default; see :mod:`aws_sim.projections.s3`."""
    estate: CanonicalEstate = request.app.state.estate
    if bucket not in _known_buckets(estate, _store(request)):
        return _error(wire.no_such_bucket(bucket))
    caller = projection.caller_account(estate, request.headers.get("authorization"))
    owner = projection.bucket_account(estate, bucket, fallback=caller)
    return _xml(wire.render_access_control_policy(projection.canonical_user_id(owner)))


def _bucket_policy(request: Request, bucket: str) -> Response:
    """``GetBucketPolicy`` — no bucket in the estate declares a policy."""
    estate: CanonicalEstate = request.app.state.estate
    if bucket not in _known_buckets(estate, _store(request)):
        return _error(wire.no_such_bucket(bucket))
    return _error(wire.no_such_bucket_policy(bucket))


def _public_access_block(request: Request, bucket: str) -> Response:
    """``GetPublicAccessBlock`` — no bucket in the estate declares a configuration."""
    estate: CanonicalEstate = request.app.state.estate
    if bucket not in _known_buckets(estate, _store(request)):
        return _error(wire.no_such_bucket(bucket))
    return _error(wire.no_such_public_access_block(bucket))
