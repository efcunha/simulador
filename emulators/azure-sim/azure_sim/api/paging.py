"""Shared continuation-token paging helper (design §5.2).

ONE helper that takes a deterministically-sorted row list, a page size, and the
request URL, and returns ``(page_rows, continuation_or_none)``. Continuation is an
opaque base64 offset token; the caller embeds it under the API-specific field
name (``nextLink`` for Cost Management / Advisor / Graph, ``$skipToken`` for
Resource Graph, ``NextPageLink`` for Retail Prices).

The token encodes only an integer offset into the already-sorted list, so paging
is deterministic and stable across calls (the sort key is the caller's canonical
order). A malformed token raises :class:`BadContinuationToken`, which the app
exception handler maps to a 400 Azure error envelope (§5.3).
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

_TOKEN_PREFIX = "offset:"  # noqa: S105 - a token-format prefix, not a credential


class BadContinuationTokenError(ValueError):
    """Raised on a malformed/garbage continuation token (-> 400 envelope)."""


@dataclass(slots=True, frozen=True)
class Page:
    """One page of rows plus the raw next offset (``None`` when exhausted)."""

    rows: list[object]
    next_offset: int | None


def encode_token(offset: int) -> str:
    """Return an opaque base64 continuation token for ``offset``."""
    raw = f"{_TOKEN_PREFIX}{offset}".encode()
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_token(token: str) -> int:
    """Return the offset encoded in ``token`` or raise :class:`BadContinuationToken`."""
    try:
        raw = base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise BadContinuationTokenError(f"malformed continuation token: {token!r}") from exc
    if not raw.startswith(_TOKEN_PREFIX):
        raise BadContinuationTokenError(f"malformed continuation token: {token!r}")
    try:
        offset = int(raw[len(_TOKEN_PREFIX) :])
    except ValueError as exc:
        raise BadContinuationTokenError(f"malformed continuation token: {token!r}") from exc
    if offset < 0:
        raise BadContinuationTokenError(f"negative offset in token: {token!r}")
    return offset


def paginate(rows: list[object], *, page_size: int, token: str | None) -> Page:
    """Slice ``rows`` into one page starting at ``token``'s offset.

    ``rows`` MUST already be in the caller's canonical sort order. Returns the
    page plus the next offset (``None`` when the page reaches the end). Raises
    :class:`BadContinuationToken` on a bad token.
    """
    offset = decode_token(token) if token else 0
    if page_size < 1:  # defensive; config guarantees >= 1
        page_size = len(rows) or 1
    page = rows[offset : offset + page_size]
    next_offset = offset + page_size
    has_more = next_offset < len(rows)
    return Page(rows=page, next_offset=next_offset if has_more else None)


def _replace_query_param(url: str, key: str, value: str) -> str:
    """Return ``url`` with ``key`` set to ``value`` in its query string."""
    parts = urlsplit(url)
    query = parse_qs(parts.query, keep_blank_values=True)
    query[key] = [value]
    flat = urlencode(query, doseq=True)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, flat, parts.fragment))


def build_next_link(request_url: str, *, field: str, next_offset: int) -> str:
    """Return a next-link URL carrying the continuation token in query param ``field``.

    Used for ``nextLink`` / ``NextPageLink`` where the continuation is a full URL
    with the token as a query parameter.
    """
    return _replace_query_param(request_url, field, encode_token(next_offset))


def page_rows_and_link(
    rows: list[object], *, page_size: int, request_url: str, token_field: str
) -> tuple[list[object], str | None]:
    """Paginate ``rows`` and build the next-link URL in one step.

    Reads the continuation token from the ``token_field`` query param of
    ``request_url``, returns the current page and the full next-link URL (or
    ``None`` when exhausted). Centralizes the per-router paging boilerplate so
    every list endpoint pages identically.
    """
    parts = urlsplit(request_url)
    token = parse_qs(parts.query, keep_blank_values=True).get(token_field, [None])[0]
    page = paginate(rows, page_size=page_size, token=token)
    next_link = (
        build_next_link(request_url, field=token_field, next_offset=page.next_offset)
        if page.next_offset is not None
        else None
    )
    return page.rows, next_link
