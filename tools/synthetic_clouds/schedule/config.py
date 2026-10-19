"""Scheduler configuration: WHEN the daily generation runs, and with what.

The daily cadence (:mod:`tools.synthetic_clouds.daily`) deliberately reads no wall
clock -- a day's artifact is a pure function of its date, and that is exactly what
makes a re-run reproducible. Deciding *which* day is "today" is therefore a separate
concern, and this module is where that decision is CONFIGURED instead of being a flag
somebody has to remember to pass.

Three properties are load-bearing, and each has a reason:

* **Fail closed.** A schedule that cannot be understood is refused at load time, not
  at 06:30 when nobody is watching. An unknown key is refused rather than ignored:
  ``"hour": "06:30"`` next to a default ``time`` would otherwise run at the wrong
  hour while the file claims otherwise.
* **The write boundary survives (NFR-4).** The config lives under the package.
  Reading a config from elsewhere is allowed; :func:`save_config` refuses to write
  outside the package tree.
* **No new dependency.** ``zoneinfo`` + ``tzdata`` are already in the environment, so
  a timezone written the way a human writes it resolves to the IANA rules -- DST
  included -- instead of a fixed offset frozen at install time.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

#: Default config path -- under the package, the only tree this project writes to
#: (NFR-4). ``--config`` may point anywhere for READING; ``save_config`` refuses the rest.
CONFIG_PATH = Path(__file__).resolve().parents[1] / "schedule" / "config.json"

_PROFILES = ("small", "medium", "large")
_CURRENCIES = ("USD", "BRL")
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")

#: Every accepted key. A key outside this set is a refusal, not a no-op -- see the
#: module docstring for why "hour" next to "time" must not be silently ignored.
_KNOWN_KEYS = frozenset(
    {
        "time",
        "time_zone",
        "seed",
        "profile",
        "currency",
        "lag_days",
        "backfill_max_days",
        "retention_days",
        "renderers",
        "enabled",
    }
)

_PACKAGE_ROOT = Path(__file__).resolve().parents[1]


class ConfigError(Exception):
    """Raised when the schedule cannot be understood. Never ignored, never defaulted."""


def _require_time(raw: Any) -> time:
    """Parse ``"HH:MM"`` (24 h) into a :class:`~datetime.time`, or refuse."""
    if not isinstance(raw, str):
        raise ConfigError(f"time must be a string 'HH:MM', got {type(raw).__name__}")
    match = _TIME_RE.match(raw)
    if match is None:
        raise ConfigError(f"time must match HH:MM in 24-hour form (00:00..23:59), got {raw!r}")
    return time(hour=int(match.group(1)), minute=int(match.group(2)))


def _require_zone(raw: Any) -> str:
    """Accept an IANA timezone name that actually resolves, or refuse.

    A typo here is the failure a silent default would hide: the job would keep running
    and silently generate the wrong day. Resolving it at load time turns that into a
    startup error.
    """
    if not isinstance(raw, str) or not raw:
        raise ConfigError(f"time_zone must be a non-empty IANA name, got {raw!r}")
    try:
        ZoneInfo(raw)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ConfigError(f"time_zone {raw!r} does not resolve to an IANA timezone") from exc
    return raw


def _require_int(raw: Any, *, name: str, minimum: int) -> int:
    # bool is an int in Python and would silently pass as 0/1 -- refused on purpose.
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise ConfigError(f"{name} must be an integer, got {type(raw).__name__}")
    if raw < minimum:
        raise ConfigError(f"{name} must be >= {minimum}, got {raw}")
    return raw


def _require_choice(raw: Any, *, name: str, allowed: tuple[str, ...]) -> str:
    if not isinstance(raw, str) or raw not in allowed:
        raise ConfigError(f"{name} must be one of {', '.join(allowed)}, got {raw!r}")
    return raw


@dataclass(frozen=True, slots=True)
class ScheduleConfig:
    """The persisted schedule: when each run fires, and what it generates.

    ``lag_days`` is not a fudge factor. FR-B2 (:mod:`tools.synthetic_clouds.clock`)
    states that a charge dated day ``D`` is first exported at ``D + 1`` at ``00:00
    UTC``; the newest day whose export is complete on wall day ``W`` is therefore
    ``W - 1``. Generating ``W`` itself would ask for a day whose export does not exist
    yet, so the default is 1 rather than 0.

    ``retention_days`` is ``None`` by default, which keeps everything. When set to N,
    the ledger keeps the N most recent days ending at the target and the older day
    directories are deleted -- measured at ~61 MB per day for the ``small`` profile and
    ~281 MB for ``medium`` at a 13-day month-to-date window (and more as the window
    grows within the month), so an unattended job that never prunes fills a disk
    quietly. A pruned day is REMOVED from the
    ledger rather than kept as complete, so the ledger never claims an artifact that
    is not on disk; backfill cannot resurrect it either, because backfill only ever
    fills the gap *after* the newest known day.
    """

    time: time
    time_zone: str
    seed: int
    profile: str
    currency: str = "USD"
    lag_days: int = 1
    backfill_max_days: int = 31
    retention_days: int | None = None
    renderers: tuple[str, ...] | None = None
    enabled: bool = True

    def zone(self) -> ZoneInfo:
        """Return the configured timezone as a :class:`~zoneinfo.ZoneInfo`."""
        return ZoneInfo(self.time_zone)

    @property
    def time_text(self) -> str:
        """``"HH:MM"`` -- the form the config file and the CLI both use."""
        return f"{self.time.hour:02d}:{self.time.minute:02d}"

    def to_document(self) -> dict[str, Any]:
        """Return the JSON-ready mapping, with a stable key order."""
        return {
            "enabled": self.enabled,
            "time": self.time_text,
            "time_zone": self.time_zone,
            "lag_days": self.lag_days,
            "backfill_max_days": self.backfill_max_days,
            "retention_days": self.retention_days,
            "seed": self.seed,
            "profile": self.profile,
            "currency": self.currency,
            "renderers": list(self.renderers) if self.renderers is not None else None,
        }

    def replace(self, **changes: Any) -> ScheduleConfig:
        """Return a copy with ``changes`` applied, revalidating the result.

        ``dataclasses.replace`` bypasses ``from_document``, so it would happily build a
        config that ``load_config`` would refuse. This one cannot: the change is
        round-tripped through the same validation every load goes through.
        """
        return ScheduleConfig.from_document({**self.to_document(), **changes})

    def validate_renderers(self, valid: Iterable[str]) -> None:
        """Refuse a renderer selection that names something that does not exist.

        The valid set is passed in rather than imported: discovering renderers imports
        pandas, pyarrow and every renderer module, and ``status``/``config show`` must
        stay cheap enough to run from a shell prompt.
        """
        if self.renderers is None:
            return
        known = set(valid)
        unknown = sorted(name for name in self.renderers if name not in known)
        if unknown:
            raise ConfigError(f"unknown renderer(s): {', '.join(unknown)}; valid: {', '.join(sorted(known))}")
        if not self.renderers:
            raise ConfigError("renderers must be null (all) or a non-empty list")

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> ScheduleConfig:
        """Validate a raw mapping into a config, refusing anything not understood."""
        unknown = sorted(set(document) - _KNOWN_KEYS)
        if unknown:
            raise ConfigError(
                f"unknown key(s) in the schedule: {', '.join(unknown)}; accepted: {', '.join(sorted(_KNOWN_KEYS))}"
            )
        missing = sorted({"time", "time_zone", "seed", "profile"} - set(document))
        if missing:
            raise ConfigError(f"missing required key(s): {', '.join(missing)}")

        raw_renderers = document.get("renderers")
        if raw_renderers is None:
            renderers: tuple[str, ...] | None = None
        elif isinstance(raw_renderers, list) and all(isinstance(item, str) for item in raw_renderers):
            renderers = tuple(raw_renderers)
        else:
            raise ConfigError("renderers must be null or a list of renderer names")

        raw_enabled = document.get("enabled", True)
        if not isinstance(raw_enabled, bool):
            raise ConfigError(f"enabled must be a boolean, got {type(raw_enabled).__name__}")

        raw_retention = document.get("retention_days")
        retention: int | None
        if raw_retention is None:
            retention = None
        else:
            retention = _require_int(raw_retention, name="retention_days", minimum=1)

        return cls(
            time=_require_time(document["time"]),
            time_zone=_require_zone(document["time_zone"]),
            seed=_require_int(document["seed"], name="seed", minimum=0),
            profile=_require_choice(document["profile"], name="profile", allowed=_PROFILES),
            currency=_require_choice(document.get("currency", "USD"), name="currency", allowed=_CURRENCIES),
            lag_days=_require_int(document.get("lag_days", 1), name="lag_days", minimum=0),
            backfill_max_days=_require_int(document.get("backfill_max_days", 31), name="backfill_max_days", minimum=1),
            retention_days=retention,
            renderers=renderers,
            enabled=raw_enabled,
        )

    @classmethod
    def default(cls) -> ScheduleConfig:
        """The schedule a fresh install starts from: 06:30 in the machine's own zone."""
        return cls.from_document(
            {
                "time": "06:30",
                "time_zone": _machine_zone_name(),
                "seed": 123,
                "profile": "small",
            }
        )


def _machine_zone_name() -> str:
    """Best-effort IANA name for the machine's timezone, for a first-run default.

    Falls back to UTC rather than guessing: a wrong zone would move the job's day
    boundary, and UTC at least announces itself in ``config show``.
    """
    local = os.environ.get("TZ")
    if local:
        try:
            ZoneInfo(local)
        except (ZoneInfoNotFoundError, ValueError):
            pass
        else:
            return local
    # ``datetime.now().astimezone().tzinfo`` is a fixed offset, not an IANA rule set,
    # so it is deliberately NOT used: it would freeze DST at install time.
    return "UTC"


def guard_within_package(path: Path) -> Path:
    """Resolve ``path``, refusing anything outside the package tree (NFR-4)."""
    resolved = path.resolve()
    package = _PACKAGE_ROOT.resolve()
    if resolved != package and package not in resolved.parents:
        raise ConfigError(f"{resolved} must be under {package} (NFR-4 write boundary)")
    return resolved


def load_config(path: Path | None = None) -> ScheduleConfig:
    """Read and validate the schedule from ``path`` (default :data:`CONFIG_PATH`)."""
    target = CONFIG_PATH if path is None else path
    try:
        raw = target.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ConfigError(f"no schedule config at {target}; run `config init` first") from exc
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{target} is not valid JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise ConfigError(f"{target} must hold a JSON object, got {type(document).__name__}")
    return ScheduleConfig.from_document(document)


def save_config(config: ScheduleConfig, path: Path | None = None) -> Path:
    """Write ``config`` to ``path`` atomically; return the resolved path.

    Written through a same-directory temp file and ``os.replace`` so a crash mid-write
    cannot leave a half-file that the next tick would refuse as malformed.
    """
    target = guard_within_package(CONFIG_PATH if path is None else path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(config.to_document(), indent=2, sort_keys=True) + "\n"
    temporary = target.with_name(f"{target.name}.{os.getpid()}.tmp")
    temporary.write_text(payload, encoding="utf-8")
    os.replace(temporary, target)
    return target


__all__ = [
    "CONFIG_PATH",
    "ConfigError",
    "ScheduleConfig",
    "guard_within_package",
    "load_config",
    "save_config",
]
