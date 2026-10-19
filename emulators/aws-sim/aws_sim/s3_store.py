"""The object store the single AWS endpoint serves: the rendered FOCUS artefacts.

**Why this exists at all, stated because the alternative is the obvious first idea.**
``AWS_SERVICE_ENDPOINT`` is ONE endpoint for every AWS service
(``endpoint.py (modulo do consumidor)``: the override injects a single
``endpoint_url`` into ``client()``/``resource()``, because ``boto3`` has no per-service
override). FinOps S3 client is built through that same choke point
(``AWSClient.client("s3")`` -> :class:`EndpointSession`), so it lands on THIS app — not on
the ``s3mock`` service that ``deploy/synthetic-clouds/compose.aws.yaml`` runs beside it on
its own port. The S3 surface therefore has to be reachable *through the one endpoint*.

Two honest ways to get there, and the trade-off is the choice this module records:

* **proxy** every S3 call to ``s3mock`` through ``S3_ENDPOINT``. One store, no second
  copy of the tree, and the image the compose file already runs becomes load-bearing.
  The cost is a network hop inside the plane, a new failure mode (the S3 surface goes
  down with a container that has no healthcheck), and — the part that decided it — a
  response whose content depends on whether an upload already ran, so the emulator's
  answer stops being a pure function of the rendered tree and can no longer be tested
  without bringing a container up.
* **serve it here**, over the very artefacts the uploader pushes (``aws_sim.upload``
  takes ``--dir /render/aws_focus``, i.e. the tree already on this container's own
  ``aws_sim_render`` volume). Chosen.

What the choice costs, said plainly: the rendered tree must be on *this* container's
volume, so ``AWS_SIM_S3_STORE_DIR`` has to point at it (``compose.aws.yaml`` sets it to
``/render/aws_focus``, the uploader's own source directory) and the two must not drift;
and ``s3mock`` now holds a second copy that only the uploader exercises. What it buys is
that the S3 answer is a pure function of the rendered tree — deterministic, identical
across restarts, testable with no container, and unaffected by ``s3mock`` being down.

**The store is one bucket.** ``upload.upload_tree`` maps a tree's relative paths onto the
keys of a single bucket, so the store root's contents *are* that bucket's objects; the
bucket name is ``AWS_SIM_BUCKET`` (``config.s3_bucket``). Nothing infers a bucket from the
tree: the layout under the root is ``{prefix}/{export_name}/…``, where ``export_name``
looks like a bucket name and is not one — it is the Data Export definition's name, and
reading it as the bucket would be a guess that a second export would break.

**Nothing is fabricated.** A key that is not on disk is absent; a bucket with no artefacts
lists empty; a tree that is not there contributes no bucket at all. The three sources of
per-object fact are the file itself (size, bytes, MD5), the file's own mtime, and the
execution stamp the renderer writes into the key — see :func:`_last_modified`.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

#: AWS's own default and ceiling for ``MaxKeys`` on ``ListObjectsV2``. Deliberately not
#: the sim-wide ``API_PAGE_SIZE``: ``MaxKeys`` is an S3 request parameter with its own
#: documented default, and the FOCUS reader — the one caller that paginates — sends no
#: ``MaxKeys`` at all, so it must get S3's page size rather than the emulator's.
DEFAULT_MAX_KEYS = 1000
MAX_KEYS_CEILING = 1000

#: A FOCUS execution directory, e.g. ``20260201T000000Z-80f388ff``. Both halves are
#: derived by the renderer from the delivery time (``render/focus_aws._execution_id``), so
#: the leading stamp IS the moment the export was delivered.
_EXECUTION = re.compile(r"^(?P<stamp>\d{8}T\d{6}Z)-[0-9a-f]{8}$")
_EXECUTION_STAMP = "%Y%m%dT%H%M%SZ"


@dataclass(frozen=True, slots=True)
class ObjectSummary:
    """One object's listing facts: its key, its size, its ETag and its last modification."""

    key: str
    size: int
    #: Bare lowercase MD5 hex — the quoting S3 sends belongs to the wire, not to the store.
    etag: str
    last_modified: datetime


@dataclass(frozen=True, slots=True)
class Listing:
    """One page of a ``ListObjectsV2`` answer, before it is rendered as XML."""

    objects: tuple[ObjectSummary, ...]
    common_prefixes: tuple[str, ...]
    is_truncated: bool
    next_token: str | None


@dataclass(frozen=True, slots=True)
class ObjectBody:
    """An object's bytes together with the facts S3 answers in headers."""

    summary: ObjectSummary
    body: bytes


def _last_modified(key: str, mtime: datetime) -> datetime:
    """The object's ``LastModified``: the export's own delivery time, else the file's mtime.

    ``LastModified`` is not decoration here. ``<modulo do consumidor>`` pins the newest
    execution per billing period by it, with a directory-path tie-break, and against real
    S3 the ordering comes from *upload* order (``aws_sim.upload``: sorted keys go up in
    order because the renderer makes execution ids sortable on purpose). A file store has
    no upload order to inherit, and a ``podman cp`` does not promise to preserve mtimes in
    tree order, so taking ``LastModified`` from the filesystem would make the reader's pin
    a function of copy order.

    The key already carries the answer: the execution directory is
    ``<delivery stamp>-<digest>``, and the renderer derives the stamp from the export time
    of the lines in that execution — the very moment ``upload_tree``'s ordering exists to
    preserve. Reading it back therefore reproduces the intended ordering exactly, makes it
    independent of how the tree got onto the volume, and makes it deterministic.

    A key with no execution directory (a layout the estate does not emit) falls back to
    the file's own mtime, which is a real fact about the artefact even though it is not a
    stable one.
    """
    for part in key.split("/")[:-1]:
        match = _EXECUTION.match(part)
        if match is not None:
            return datetime.strptime(match.group("stamp"), _EXECUTION_STAMP).replace(tzinfo=UTC)
    return mtime


def effective_max_keys(requested: int) -> int:
    """The page size S3 would actually use for ``requested``.

    Exposed so the wire can echo the number the page was built with: a response that
    echoes the caller's own ``MaxKeys`` while the page was cut at the ceiling would
    describe a page it did not send.
    """
    return max(1, min(int(requested), MAX_KEYS_CEILING))


def encode_token(value: str) -> str:
    """Opaque continuation token for ``value`` (the last entry on the page).

    Base64url, and **padding-stripped**, because the token has to survive the trip out and
    back unmangled. botocore's ``encoding-type=url`` after-call handler decodes ``Key``,
    ``Prefix``, ``Delimiter`` and ``StartAfter`` — and deliberately *not*
    ``NextContinuationToken``, which it treats as opaque. So a token whose text changed
    under percent-escaping (a trailing ``=`` is the padding of every third key length here)
    would be handed back to the server in its escaped form and fail to decode. A token with
    nothing to escape cannot be changed by the trip, whichever side escapes it.

    It stays a statement about a position in a sorted list — decoded with
    :func:`decode_token` and compared as a plain string — so nothing else has to keep a
    counter in step with it.
    """
    return base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii").rstrip("=")


def decode_token(token: str) -> str | None:
    """Decode a token produced by :func:`encode_token`, or ``None`` when it is not one."""
    if not token:
        return None
    try:
        # The padding stripped by ``encode_token`` is not information: it is a function of
        # the byte length, so it is restored rather than carried.
        return base64.urlsafe_b64decode(f"{token}{'=' * (-len(token) % 4)}").decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return None


class S3Store:
    """The rendered artefacts on disk, presented as the objects of one bucket.

    ``root`` is the directory the uploader was pointed at, so a path relative to it is a
    key verbatim — no rewrite, for the same reason ``upload.upload_tree`` rewrites none:
    a remapped key lands where the reader does not look. ``bucket`` is the name those
    objects belong to.
    """

    def __init__(self, root: Path | None, bucket: str) -> None:
        self._root = None if root is None else root.resolve()
        self._bucket = bucket.strip()

    @property
    def bucket(self) -> str:
        """The bucket this store holds, or ``""`` when none is configured."""
        return self._bucket

    @property
    def configured(self) -> bool:
        """Whether a bucket is named and its directory is actually there.

        A named bucket whose directory is missing contributes nothing: the estate does not
        have it, and listing an empty bucket that has no store behind it would be an
        assertion about the tree rather than a report of one.
        """
        return bool(self._bucket) and self._root is not None and self._root.is_dir()

    @property
    def buckets(self) -> tuple[str, ...]:
        """The bucket the store contributes to the estate's bucket list (0 or 1)."""
        return (self._bucket,) if self.configured else ()

    def lists(self, bucket: str) -> bool:
        """Whether ``bucket`` is the one this store holds."""
        return self.configured and bucket == self._bucket

    def listing(
        self,
        *,
        prefix: str = "",
        delimiter: str = "",
        max_keys: int = DEFAULT_MAX_KEYS,
        start_after: str = "",
    ) -> Listing:
        """One page of the bucket's objects, in S3's lexicographic key order.

        Matching S3's ordering is what makes the page boundaries and the continuation
        token meaningful: the entries are the sorted keys, with any group the delimiter
        rolls up appearing once, at the position of its first key. ``start_after`` (or the
        decoded continuation token, which the caller passes here) then means the same
        thing it means to S3 — resume strictly after that entry.
        """
        page_size = effective_max_keys(max_keys or DEFAULT_MAX_KEYS)
        index = dict(self._entries())
        entries: list[tuple[str, str]] = []
        rolled: set[str] = set()
        for key in sorted(index):
            if prefix and not key.startswith(prefix):
                continue
            rest = key[len(prefix) :]
            if delimiter and delimiter in rest:
                rolled_up = f"{prefix}{rest.split(delimiter, 1)[0]}{delimiter}"
                if rolled_up not in rolled:
                    rolled.add(rolled_up)
                    entries.append((rolled_up, "prefix"))
                continue
            entries.append((key, "object"))

        if start_after:
            entries = [entry for entry in entries if entry[0] > start_after]
        truncated = len(entries) > page_size
        page = entries[:page_size]

        objects = tuple(self._summarise(key, index[key]) for key, kind in page if kind == "object")
        prefixes = tuple(value for value, kind in page if kind == "prefix")
        return Listing(
            objects=objects,
            common_prefixes=prefixes,
            is_truncated=truncated,
            next_token=encode_token(page[-1][0]) if truncated and page else None,
        )

    def read(self, key: str) -> ObjectBody | None:
        """The object's bytes and facts, or ``None`` when the store does not hold it."""
        path = self._path_for(key)
        if path is None or not path.is_file():
            return None
        body = path.read_bytes()
        return ObjectBody(summary=self._summarise(key, path), body=body)

    # ── internals ────────────────────────────────────────────────────────────

    def _entries(self) -> tuple[tuple[str, Path], ...]:
        """Every object under the root as ``(key, path)``, sorted by key.

        Sorted here rather than by the caller because three answers depend on it: the
        listing order, the continuation token, and the roll-up position of a common
        prefix.
        """
        if self._root is None or not self._root.is_dir():
            return ()
        entries: list[tuple[str, Path]] = []
        for path in self._root.rglob("*"):
            if not path.is_file():
                continue
            # A symlink out of the tree is not an object of this bucket, and following one
            # would serve a file the volume was never given.
            if not path.resolve().is_relative_to(self._root):
                continue
            entries.append((path.relative_to(self._root).as_posix(), path))
        return tuple(sorted(entries, key=lambda entry: entry[0]))

    def _summarise(self, key: str, path: Path) -> ObjectSummary:
        """Read one object's listing facts from the file itself.

        The ETag is the MD5 of the bytes, which is what S3 answers for an object written
        by a single ``PutObject`` — the only way ``upload.upload_tree`` writes one.
        """
        body = path.read_bytes()
        stat = path.stat()
        return ObjectSummary(
            key=key,
            size=len(body),
            etag=hashlib.md5(body, usedforsecurity=False).hexdigest(),  # noqa: S324 - an ETag, not a signature
            last_modified=_last_modified(key, datetime.fromtimestamp(stat.st_mtime, tz=UTC)),
        )

    def _path_for(self, key: str) -> Path | None:
        """Resolve ``key`` inside the root, or ``None`` when it escapes it.

        The key arrives from the request path, so it is untrusted input: an absolute key,
        a backslash, or a ``..`` segment would otherwise read a file the volume never
        served — ``GET /bucket/../../etc/shadow`` is a path traversal, not a missing
        object. Rejecting the shapes outright and re-checking containment after
        ``resolve`` (which is what catches a symlink) keeps the answer to a bad key what
        it should be: nothing.
        """
        if self._root is None:
            return None
        if not key or key.startswith("/") or "\\" in key:
            return None
        parts = [part for part in key.split("/") if part not in ("", ".")]
        if not parts or any(part == ".." for part in parts):
            return None
        candidate = self._root.joinpath(*parts)
        if not candidate.resolve().is_relative_to(self._root):
            return None
        return candidate
