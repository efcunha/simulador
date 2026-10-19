"""Synthetic marker helpers (NFR-3).

Every synthetic artifact carries uniform markers so a reader (and the AC-18 test)
can prove the data is synthetic and references no real secret. All fictional
identities live under ``contoso.example``.
"""

from __future__ import annotations

from typing import Any

SYNTH_NAME_PREFIX = "[SYNTH] "
SOURCE_SYNTHETIC = "synthetic"
RECOMMENDATION_MODEL = "synthetic.seed.v1"
SOURCE_FINGERPRINT_PREFIX = "synth:"
FICTIONAL_DOMAIN = "contoso.example"


def synth_name(label: str) -> str:
    """Prefix an account-like name with the ``[SYNTH]`` marker."""
    return f"{SYNTH_NAME_PREFIX}{label}"


def unmarked_name(name: str) -> str:
    """Return ``name`` without the ``[SYNTH] `` marker (cloud-export projection).

    The marker is a **FinOps-side** discriminator, so it stays on the canonical estate
    and on everything written into FinOps own database.

    A cloud export is not FinOps storage, though. No real AWS/Azure/GCP export
    carries ``[SYNTH] `` in an account, credit or display name, so a renderer projecting
    such a name into an export column must strip the marker here rather than write
    FinOps storage discriminator into the cloud's own field. That includes the
    names a discovered account is stored under: the AWS simulator serves the account name
    through this function and ``org_discovery.py (modulo do consumidor)`` persists the served name
    verbatim.

    Nothing decides synthetic vs real by the name any more. The never-mix gate
    (``seed/workspace.py::_assert_no_real_rows``) recognises an account registered through
    the application by its credential/authorization material — stored credentials,
    ``role_arn``/``write_role_arn``, or the ``parent_account_id`` of an ``org_member``
    account — and the cleanup (``seed/cleanup.py``) scopes its deletes by ``workspace_id``
    alone, behind that gate.
    """
    if name.startswith(SYNTH_NAME_PREFIX):
        return name[len(SYNTH_NAME_PREFIX) :]
    return name


def source_fingerprint(logical: str) -> str:
    """Return a ``synth:``-prefixed source fingerprint for a logical key."""
    return f"{SOURCE_FINGERPRINT_PREFIX}{logical}"


def synthetic_metadata(**extra: Any) -> dict[str, Any]:
    """Return a metadata dict with ``synthetic=true`` plus any extra keys."""
    return {"synthetic": True, **extra}


def synthetic_evidence(**extra: Any) -> dict[str, Any]:
    """Return an evidence_json dict with ``synthetic=true`` plus any extra keys."""
    return {"synthetic": True, **extra}
