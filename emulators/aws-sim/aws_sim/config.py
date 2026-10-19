"""Env-driven settings with fail-closed validation (mirrors azure-sim's config).

Every env input is validated BEFORE anything is served, and a bad value raises
:class:`ConfigError` — fatal at the ``__main__`` boundary, never a half-configured
service. Deliberately small: this slice answers five read-only operations, so there is
no export schedule, no blob container and no partition sizing to configure.

``AWS_SIM_API_VERSION`` is **not** configurable and defaults to the version read from
botocore's service model. It is exposed as a setting only so a test can prove the
service rejects a mismatched ``Version`` parameter; letting an operator pin a different
version would let the emulator disagree with the client it exists to serve.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

PROFILES: frozenset[str] = frozenset({"small", "medium", "large"})
CURRENCIES: frozenset[str] = frozenset({"USD", "BRL"})


class ConfigError(ValueError):
    """Raised on any invalid env input — fatal, fail-closed before serving."""


@dataclass(slots=True, frozen=True)
class Settings:
    """Validated, immutable simulator settings."""

    seed: int
    profile: str
    currency: str
    region: str
    api_page_size: int
    denied_account: str = ""
    # A09: the S3 surface (``api/s3.py``) is served on this same endpoint, because
    # ``AWS_SERVICE_ENDPOINT`` is one endpoint for every service. These two name the
    # rendered artefact tree it serves and the bucket that tree's objects belong to.
    # Both default UNSET, and unset changes nothing: the S3 routes answer the estate's
    # bucket list with every object listing empty, which is the same estate answer the
    # rest of this slice gives for a service with nothing to project.
    s3_store_dir: str = ""
    s3_bucket: str = ""


def _require_int(env: Mapping[str, str], key: str, default: str) -> int:
    raw = env.get(key, default).strip()
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{key} must be an integer, got {raw!r}") from exc


def _require_enum(env: Mapping[str, str], key: str, default: str, allowed: frozenset[str]) -> str:
    value = env.get(key, default).strip()
    if value not in allowed:
        raise ConfigError(f"{key} must be one of {sorted(allowed)}, got {value!r}")
    return value


def load_settings(env: Mapping[str, str] | None = None, **overrides: object) -> Settings:
    """Load and validate settings from ``env`` (defaults to ``os.environ``)."""
    base: dict[str, str] = dict(os.environ if env is None else env)
    for key, value in overrides.items():
        if value is not None:
            base[key.upper()] = str(value)

    seed = _require_int(base, "SEED", "42")
    profile = _require_enum(base, "PROFILE", "small", PROFILES)
    currency = _require_enum(base, "CURRENCY", "USD", CURRENCIES)

    region = base.get("AWS_SIM_REGION", "us-east-1").strip()
    if not region:
        raise ConfigError("AWS_SIM_REGION must not be empty")

    api_page_size = _require_int(base, "API_PAGE_SIZE", "100")
    if api_page_size < 1:
        raise ConfigError(f"API_PAGE_SIZE must be >= 1, got {api_page_size}")

    # A08: the one member account STS refuses with AccessDenied, so the failed-connection
    # surfaces can be exercised. Empty means no account is denied.
    denied_account = base.get("AWS_SIM_DENIED_ACCOUNT", "").strip()
    if denied_account and (len(denied_account) != 12 or not denied_account.isdigit()):
        raise ConfigError(
            f"AWS_SIM_DENIED_ACCOUNT must be a 12-digit account id, got {denied_account!r}"
        )

    return Settings(
        seed=seed,
        profile=profile,
        currency=currency,
        region=region,
        api_page_size=api_page_size,
        denied_account=denied_account,
        # Neither is validated for existence on purpose: compose starts this container
        # before ``aws-up.ps1`` copies the rendered tree into the volume, so a store
        # directory that is not there yet is the normal state at startup, not a
        # misconfiguration. An unreadable or missing tree simply contributes no bucket.
        s3_store_dir=base.get("AWS_SIM_S3_STORE_DIR", "").strip(),
        s3_bucket=base.get("AWS_SIM_BUCKET", "").strip(),
    )
