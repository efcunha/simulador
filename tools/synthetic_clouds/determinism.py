"""Deterministic identity + sampling primitives (NFR-1).

Every identifier in the canonical model is a UUIDv5 over a *logical path* string,
so ids are stable across runs for a given seed and carry no hidden ordering
dependence. Distribution sampling uses ``random.Random`` whose integer seed is a
``hashlib.sha256`` digest of ``(seed, stream_name)`` — deterministic across
processes, unlike Python's built-in ``hash()`` which is salted per-process and is
therefore banned here (a source-scanning test, AC-6, enforces this).
"""

from __future__ import annotations

import hashlib
import random
import uuid

# A fixed, well-known RFC 4122 example namespace UUID used as a constant salt.
# Combined with the run seed to produce a per-run namespace.
_ROOT_NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


def run_namespace(seed: int) -> uuid.UUID:
    """Return the stable per-run UUIDv5 namespace for ``seed``."""
    return uuid.uuid5(_ROOT_NS, f"synthetic-clouds:seed={seed}")


def identity_for(seed: int, logical_path: str) -> str:
    """Return the stable UUIDv5 identity string for ``(seed, logical_path)``.

    The same ``(seed, logical_path)`` always yields the same UUID; different
    seeds or paths yield different UUIDs. This is the single identity source
    threaded end-to-end through the estate (P2).
    """
    return str(uuid.uuid5(run_namespace(seed), logical_path))


def stream_rng(seed: int, stream: str) -> random.Random:
    """Return a ``random.Random`` deterministically seeded for a named stream.

    Each logical concern (seasonality jitter, untagged selection, off-standard
    names, ...) gets its own named stream so adding a new realism feature cannot
    perturb an existing stream's sequence (idempotency across versions, NFR-2).
    The integer seed is derived via ``hashlib.sha256`` so it is reproducible
    across processes — ``hash()`` is never used.
    """
    digest = hashlib.sha256(f"{seed}:{stream}".encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))  # noqa: S311 - not crypto; deterministic sim sampling
