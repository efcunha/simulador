"""Env-driven settings with fail-closed validation (design §4.6/§4.8).

``config.py`` is the single entry both ``serve`` and ``export`` pass through, so
it owns the invariant that every env/CLI input is validated BEFORE any serve or
blob write. On any bad input it raises :class:`ConfigError` (fatal, non-zero
exit at the ``__main__`` boundary) and never produces a partial write.

All enums/charsets/numeric bounds come straight from the design:
  * ``SEED``             int
  * ``PROFILE``          small | medium | large
  * ``CURRENCY``         USD | BRL
  * ``AGREEMENT``        mca | ea
  * ``EXPORTS``          non-empty subset of {focus, actual, amortized}
  * ``FORMAT``           non-empty subset of {csv, parquet}
  * ``SCHEDULE``         daily | monthly | one-time
  * ``LATENCY_HOURS``    int >= 0
  * ``MAX_ROWS_PER_PART``int >= 1
  * ``BLOB_CONTAINER``   charset [A-Za-z0-9-/_]
  * ``ROOT_DIRECTORY``   charset [A-Za-z0-9-/_]
  * ``AZURE_BLOB_ENDPOINT`` str (Azurite dev endpoint)
  * ``API_PAGE_SIZE``    int >= 1
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass

PROFILES: frozenset[str] = frozenset({"small", "medium", "large"})
CURRENCIES: frozenset[str] = frozenset({"USD", "BRL"})
AGREEMENTS: frozenset[str] = frozenset({"mca", "ea"})
EXPORT_TYPES: frozenset[str] = frozenset({"focus", "actual", "amortized"})
FORMATS: frozenset[str] = frozenset({"csv", "parquet"})
SCHEDULES: frozenset[str] = frozenset({"daily", "monthly", "one-time"})

# Blob path safety: container/root segments must stay within this charset so a
# crafted env value cannot escape the intended prefix (design §4.8).
_PATH_CHARSET = re.compile(r"^[A-Za-z0-9\-/_]+$")

# Defaults (design §4.1/§4.6): FOCUS exercises both ingestion paths; the dev
# Azurite account uses the well-known public emulator endpoint (not a secret).
_DEFAULT_EXPORTS = ("focus",)
_DEFAULT_FORMAT = ("csv", "parquet")
_DEFAULT_BLOB_ENDPOINT = "http://127.0.0.1:10000/devstoreaccount1"


class ConfigError(ValueError):
    """Raised on any invalid env/CLI input — fatal, fail-closed before any write."""


@dataclass(slots=True, frozen=True)
class Settings:
    """Validated, immutable simulator settings."""

    seed: int
    profile: str
    # Length of the simulated window in days. ``None`` keeps the profile's own window, so an
    # unset value behaves exactly as before; setting it is how a demo asks for a window that
    # reaches "today" (e.g. 282 days covers the canonical epoch through 2026-10-09).
    window_days: int | None
    currency: str
    agreement: str
    exports: tuple[str, ...]
    formats: tuple[str, ...]
    schedule: str
    latency_hours: int
    max_rows_per_part: int
    blob_container: str
    root_directory: str
    azure_blob_endpoint: str
    api_page_size: int


def _require_int(env: Mapping[str, str], key: str, default: str) -> int:
    raw = env.get(key, default).strip()
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{key} must be an integer, got {raw!r}") from exc


def _optional_positive_int(env: Mapping[str, str], key: str) -> int | None:
    """Return a positive int from ``env``, or ``None`` when the key is unset or empty."""
    raw = env.get(key, "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{key} must be an integer, got {raw!r}") from exc
    if value < 1:
        raise ConfigError(f"{key} must be >= 1, got {value}")
    return value


def _require_enum(env: Mapping[str, str], key: str, default: str, allowed: frozenset[str]) -> str:
    value = env.get(key, default).strip()
    if value not in allowed:
        raise ConfigError(f"{key} must be one of {sorted(allowed)}, got {value!r}")
    return value


def _require_subset(
    env: Mapping[str, str], key: str, default: tuple[str, ...], allowed: frozenset[str]
) -> tuple[str, ...]:
    raw = env.get(key)
    items = (
        tuple(part.strip() for part in raw.split(",") if part.strip())
        if raw is not None and raw.strip()
        else default
    )
    if not items:
        raise ConfigError(f"{key} must list at least one of {sorted(allowed)}")
    bad = [item for item in items if item not in allowed]
    if bad:
        raise ConfigError(f"{key} contains invalid value(s) {bad}; allowed {sorted(allowed)}")
    # Deduplicate while preserving first-seen order (deterministic).
    seen: dict[str, None] = {}
    for item in items:
        seen.setdefault(item, None)
    return tuple(seen)


def _require_path_segment(env: Mapping[str, str], key: str, default: str) -> str:
    value = env.get(key, default).strip()
    if not _PATH_CHARSET.match(value):
        raise ConfigError(f"{key} must match [A-Za-z0-9-/_], got {value!r}")
    return value


def load_settings(env: Mapping[str, str] | None = None, **overrides: object) -> Settings:
    """Load and validate settings from ``env`` (defaults to ``os.environ``).

    ``overrides`` lets the ``__main__ export`` CLI replace specific env values
    (design §4.6) before validation runs; a ``None`` override is ignored so an
    unset CLI flag falls through to the env/default. All validation happens here
    so both ``serve`` and ``export`` fail closed on bad input.
    """
    base: dict[str, str] = dict(os.environ if env is None else env)
    for key, value in overrides.items():
        if value is not None:
            base[key.upper()] = str(value)

    seed = _require_int(base, "SEED", "42")
    profile = _require_enum(base, "PROFILE", "small", PROFILES)
    window_days = _optional_positive_int(base, "WINDOW_DAYS")
    currency = _require_enum(base, "CURRENCY", "USD", CURRENCIES)
    agreement = _require_enum(base, "AGREEMENT", "mca", AGREEMENTS)
    exports = _require_subset(base, "EXPORTS", _DEFAULT_EXPORTS, EXPORT_TYPES)
    formats = _require_subset(base, "FORMAT", _DEFAULT_FORMAT, FORMATS)
    schedule = _require_enum(base, "SCHEDULE", "one-time", SCHEDULES)

    latency_hours = _require_int(base, "LATENCY_HOURS", "4")
    if latency_hours < 0:
        raise ConfigError(f"LATENCY_HOURS must be >= 0, got {latency_hours}")

    max_rows_per_part = _require_int(base, "MAX_ROWS_PER_PART", "1000000")
    if max_rows_per_part < 1:
        raise ConfigError(f"MAX_ROWS_PER_PART must be >= 1, got {max_rows_per_part}")

    blob_container = _require_path_segment(base, "BLOB_CONTAINER", "exports")
    root_directory = _require_path_segment(base, "ROOT_DIRECTORY", "cost-exports")
    azure_blob_endpoint = base.get("AZURE_BLOB_ENDPOINT", _DEFAULT_BLOB_ENDPOINT).strip()
    if not azure_blob_endpoint:
        raise ConfigError("AZURE_BLOB_ENDPOINT must not be empty")

    api_page_size = _require_int(base, "API_PAGE_SIZE", "1000")
    if api_page_size < 1:
        raise ConfigError(f"API_PAGE_SIZE must be >= 1, got {api_page_size}")

    return Settings(
        seed=seed,
        profile=profile,
        window_days=window_days,
        currency=currency,
        agreement=agreement,
        exports=exports,
        formats=formats,
        schedule=schedule,
        latency_hours=latency_hours,
        max_rows_per_part=max_rows_per_part,
        blob_container=blob_container,
        root_directory=root_directory,
        azure_blob_endpoint=azure_blob_endpoint,
        api_page_size=api_page_size,
    )
