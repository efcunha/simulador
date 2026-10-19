"""The S3 REST-XML wire — the fourth protocol this one AWS endpoint speaks.

The other three are already here: :mod:`aws_sim.json_wire` (JSON-1.1),
:mod:`aws_sim.query_xml` (Query, plus the ec2 variant of it) and
:mod:`aws_sim.smithy_rpc` (JSON-1.0 and RPC-v2 CBOR). S3 is none of them: it is
**REST-XML**, so the operation is carried by the request *path* and method rather than by
an ``Action`` form field or an ``X-Amz-Target`` header — see :mod:`aws_sim.api.s3` for
the routes — and the answer is an XML document.

Three properties of this framing decide what the documents below look like, and each of
them is something a hand-written envelope gets wrong in a way no shape list reveals:

* **The root element name is not read.** botocore's ``RestXMLParser`` walks the output
  shape and looks each member up by its ``locationName`` among the root's children, so
  the document is parsed by *member* name, not by document type. The real names are used
  anyway (``ListAllMyBucketsResult``, ``ListBucketResult``, ``AccessControlPolicy``) —
  a consumer that logs the body, and a human reading it, should see what S3 sends — they
  are simply not what makes the parse work.
* **``EncodingType: url`` is an obligation, not a hint.** ``boto3`` sets
  ``encoding-type=url`` itself when the caller does not, and its after-call handler
  decodes ``Key``/``Prefix``/``Delimiter``/``StartAfter`` **only when the response echoes
  ``<EncodingType>url</EncodingType>``**. So the echo and the escaping ship together:
  echoing without escaping would give the caller a string with the percent-escapes still
  in it, and escaping without the echo would give it one it then decodes a second time.
  Neither shows up on this estate until a key carries a reserved character — and the FOCUS
  layout does (``billing_period=2026-01``).
* **Errors are ``<Error>``, not ``<ErrorResponse>``.** The rest-xml parser branches on the
  root tag: only ``<Error>`` yields the bare code the S3 callers branch on
  (``NoSuchKey``, ``NoSuchBucketPolicy``, ``NoSuchPublicAccessBlockConfiguration``). The
  Query envelope ``query_xml.render_error`` renders would reach them as a generic
  ``Unknown``, which is why the two cannot share a renderer.

Timestamps: body members are ISO-8601 (the rest-xml default) and the ``Last-Modified``
header is RFC 822, because botocore parses headers with the header format and the body
with the body format — the one value that appears in both, and it is not the same string.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import format_datetime
from urllib.parse import quote
from xml.sax.saxutils import escape

from aws_sim.s3_store import Listing, ObjectSummary

#: The S3 XML namespace. Declared on every success document (real S3 does); deliberately
#: absent from the error document, which real S3 sends without one.
NAMESPACE = "http://s3.amazonaws.com/doc/2006-03-01/"

#: The XSI namespace ``Grantee`` carries: its ``Type`` is serialized as the ``xsi:type``
#: *attribute* (``botocore``'s model marks it ``xmlAttribute`` with ``locationName``
#: ``xsi:type``), so the prefix has to be bound on the document.
XSI_NAMESPACE = "http://www.w3.org/2001/XMLSchema-instance"

CONTENT_TYPE = "application/xml"

#: The URL encoding marker S3 echoes. See the module docstring for why echoing it and
#: escaping the values are the same decision.
ENCODING_URL = "url"

#: The storage class every object in the estate's single bucket is served as. The store is
#: one tree rendered by one exporter, so there is no per-object class to read.
STORAGE_CLASS = "STANDARD"


def _document(root: str, body: str) -> str:
    """Wrap ``body`` in the S3 success envelope for ``root``."""
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<{root} xmlns="{NAMESPACE}">{body}</{root}>'


def _tag(name: str, value: str) -> str:
    """One element holding TEXT, XML-escaped."""
    return f"<{name}>{escape(value)}</{name}>"


def _wrap(name: str, body: str) -> str:
    """One element holding already-rendered XML.

    Distinct from :func:`_tag` because escaping is not idempotent: wrapping a rendered
    child with ``_tag`` escapes its angle brackets and emits the markup as text.
    """
    return f"<{name}>{body}</{name}>"


def _encoded_tag(name: str, value: str, encoding_type: str) -> str:
    """One element URL-encoded when the request asked for it (see the docstring)."""
    rendered = quote(value, safe="") if encoding_type == ENCODING_URL else value
    return _tag(name, rendered)


def iso8601(moment: datetime) -> str:
    """The body timestamp format: ``2026-01-31T00:00:00.000Z``.

    Normalised to UTC first: the trailing ``Z`` is a claim about the offset, and a value
    that carried another one would be read as the wrong instant.
    """
    utc = moment.astimezone(UTC)
    return utc.strftime("%Y-%m-%dT%H:%M:%S.") + f"{utc.microsecond // 1000:03d}Z"


def http_date(moment: datetime) -> str:
    """The header timestamp format S3 sends on ``Last-Modified`` (same UTC caveat)."""
    return format_datetime(moment.astimezone(UTC), usegmt=True)


def etag_of(digest: str) -> str:
    """Quote a bare hex digest the way S3 quotes an ETag (quotes included, as AWS sends)."""
    return f'"{digest}"'


def render_list_buckets(buckets: Sequence[tuple[str, datetime | None]], *, owner_id: str) -> str:
    """``ListBuckets`` — ``<ListAllMyBucketsResult>``.

    ``CreationDate`` is emitted only when the estate asserts one (see
    :func:`aws_sim.projections.s3.bucket_creation`); a bucket with no such instant is
    listed without the element rather than with the emulator's clock in it.
    """
    entries = "".join(
        _wrap(
            "Bucket",
            _tag("Name", name) + ("" if created is None else _tag("CreationDate", iso8601(created))),
        )
        for name, created in buckets
    )
    owner = _wrap("Owner", _tag("ID", owner_id)) if owner_id else ""
    return _document("ListAllMyBucketsResult", f"{owner}{_wrap('Buckets', entries)}")


def render_list_objects_v2(
    listing: Listing,
    *,
    bucket: str,
    prefix: str,
    delimiter: str,
    max_keys: int,
    encoding_type: str,
    continuation_token: str,
    start_after: str,
) -> str:
    """``ListObjectsV2`` — ``<ListBucketResult>``.

    ``Contents`` and ``CommonPrefixes`` are *flattened* in the model, so each object is a
    sibling ``<Contents>`` element and each rolled-up directory a sibling
    ``<CommonPrefixes>`` — there is no wrapper element, and emitting one would parse as a
    single malformed object.
    """
    head = (
        _tag("Name", bucket)
        + _encoded_tag("Prefix", prefix, encoding_type)
        + _encoded_tag("Delimiter", delimiter, encoding_type)
        + _tag("MaxKeys", str(max_keys))
        + _tag("KeyCount", str(len(listing.objects) + len(listing.common_prefixes)))
        + _tag("IsTruncated", "true" if listing.is_truncated else "false")
    )
    if encoding_type:
        head += _tag("EncodingType", encoding_type)
    if continuation_token:
        head += _encoded_tag("ContinuationToken", continuation_token, encoding_type)
    if start_after:
        head += _encoded_tag("StartAfter", start_after, encoding_type)
    if listing.next_token is not None:
        # ``_tag``, not ``_encoded_tag``: botocore's encoding-type=url handler decodes
        # ``Key``/``Prefix``/``Delimiter``/``StartAfter`` and NOT the continuation tokens,
        # so an escaped token would come back escaped. The token is URL-safe by
        # construction (``s3_store.encode_token``), which is what makes the plain form safe.
        head += _tag("NextContinuationToken", listing.next_token)

    contents = "".join(_object_element(obj, encoding_type) for obj in listing.objects)
    prefixes = "".join(
        _wrap("CommonPrefixes", _encoded_tag("Prefix", value, encoding_type)) for value in listing.common_prefixes
    )
    return _document("ListBucketResult", f"{head}{contents}{prefixes}")


def _object_element(obj: ObjectSummary, encoding_type: str) -> str:
    """One ``<Contents>`` entry: key, last modification, ETag, size, storage class."""
    return _wrap(
        "Contents",
        _encoded_tag("Key", obj.key, encoding_type)
        + _tag("LastModified", iso8601(obj.last_modified))
        + _tag("ETag", etag_of(obj.etag))
        + _tag("Size", str(obj.size))
        + _tag("StorageClass", STORAGE_CLASS),
    )


def render_access_control_policy(owner_canonical_id: str, *, owner_display_name: str = "") -> str:
    """``GetBucketAcl`` — the private default an untouched bucket answers.

    ``Grantee`` carries ``xsi:type="CanonicalUser"`` as an *attribute*, so the document has
    to bind the ``xsi`` prefix for the parser to find the type it requires.
    """
    display = _tag("DisplayName", owner_display_name) if owner_display_name else ""
    identity = _wrap("ID", escape(owner_canonical_id)) + display
    grantee = f'<Grantee xmlns:xsi="{XSI_NAMESPACE}" xsi:type="CanonicalUser">{identity}</Grantee>'
    grant = _wrap("Grant", grantee + _tag("Permission", "FULL_CONTROL"))
    return _document(
        "AccessControlPolicy",
        _wrap("Owner", identity) + _wrap("AccessControlList", grant),
    )


@dataclass(frozen=True, slots=True)
class S3Error:
    """One S3 error answer: its code, its message, and the HTTP status it travels with."""

    code: str
    message: str
    status_code: int
    bucket: str = ""
    key: str = ""

    def render(self) -> str:
        """The ``<Error>`` document the rest-xml parser reads the code out of."""
        members = _tag("Code", self.code) + _tag("Message", self.message)
        if self.bucket:
            members += _tag("BucketName", self.bucket)
        if self.key:
            members += _tag("Key", self.key)
        return f'<?xml version="1.0" encoding="UTF-8"?>\n<Error>{members}</Error>'


def no_such_bucket(bucket: str) -> S3Error:
    """The bucket the estate does not have."""
    return S3Error("NoSuchBucket", f"The specified bucket does not exist: {bucket}", 404, bucket=bucket)


def no_such_key(bucket: str, key: str) -> S3Error:
    """The object the store does not hold. Absence is an error here, never an empty body.

    ``get_object``'s callers read ``Body`` as the export: an empty body would parse as a
    bill with no rows, which is a different claim from "that object does not exist".
    """
    return S3Error("NoSuchKey", f"The specified key does not exist: {key}", 404, bucket=bucket, key=key)


def no_such_bucket_policy(bucket: str) -> S3Error:
    """No policy is attached — the code ``security.py:304`` branches on."""
    return S3Error(
        "NoSuchBucketPolicy",
        f"The bucket policy does not exist for bucket: {bucket}",
        404,
        bucket=bucket,
    )


def no_such_public_access_block(bucket: str) -> S3Error:
    """No configuration is attached — the code ``security.py:218`` branches on."""
    return S3Error(
        "NoSuchPublicAccessBlockConfiguration",
        "The public access block configuration was not found",
        404,
        bucket=bucket,
    )


def invalid_request(message: str) -> S3Error:
    """A request whose shape this endpoint does not serve."""
    return S3Error("InvalidRequest", message, 400)


def invalid_argument(name: str, value: str) -> S3Error:
    """A parameter that is present and unreadable — S3's own code for it.

    Answered rather than absorbed: substituting a default for a value the caller did send
    would make the emulator's page size silently disagree with what the caller asked for.
    """
    return S3Error("InvalidArgument", f"Invalid value {value!r} for parameter {name}.", 400)
