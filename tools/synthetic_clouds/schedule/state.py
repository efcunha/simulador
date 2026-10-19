"""Run ledger: which simulated days have already been generated.

Idempotency is not a nicety here, it is what makes an unattended job safe. The
scheduled task can fire twice in a day (the daily trigger plus the logon catch-up),
the machine can be off at the configured hour, and a re-run must never be a
coin flip: a day already marked complete is skipped, and a day that is missing is
generated from its own window alone -- which
:mod:`tools.synthetic_clouds.daily.emit` guarantees is the same tree the first run
would have produced.

The ledger holds wall-clock instants, and that is deliberate: it is an operational
record, not an artifact. Nothing written here reaches a Parquet or a JSON export --
those must stay byte-deterministic, and ``serialize/store.py`` keeps run metadata in
``meta.json`` for the same reason.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

#: Default ledger path -- beside the daily output it describes, and inside the
#: package, which is the only tree this project writes to (NFR-4).
STATE_PATH = Path(__file__).resolve().parents[1] / "out" / "daily" / "_state" / "state.json"

#: Bumped only when the on-disk shape changes incompatibly. An unknown version is
#: refused rather than guessed at, so an older binary cannot silently misread a newer
#: ledger and decide that days are missing that are not.
STATE_VERSION = 1

_STATUS_COMPLETE = "complete"


class StateError(Exception):
    """Raised when the ledger cannot be read or understood."""


@dataclass(frozen=True, slots=True)
class DayRecord:
    """One generated day: how many artifacts it wrote, and when it finished."""

    artifacts: int
    completed_at: str

    def to_document(self) -> dict[str, Any]:
        return {"status": _STATUS_COMPLETE, "artifacts": self.artifacts, "completed_at": self.completed_at}

    @classmethod
    def from_document(cls, day: str, document: Mapping[str, Any]) -> DayRecord:
        status = document.get("status")
        if status != _STATUS_COMPLETE:
            raise StateError(f"day {day}: unknown status {status!r}")
        artifacts = document.get("artifacts")
        if isinstance(artifacts, bool) or not isinstance(artifacts, int) or artifacts < 0:
            raise StateError(f"day {day}: artifacts must be a non-negative integer")
        completed_at = document.get("completed_at")
        if not isinstance(completed_at, str):
            raise StateError(f"day {day}: completed_at must be a string")
        return cls(artifacts=artifacts, completed_at=completed_at)


@dataclass(frozen=True, slots=True)
class RunRecord:
    """The outcome of the most recent tick, kept for `status` and for support."""

    at: str
    target_day: str
    status: str
    generated: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    pruned: tuple[str, ...] = ()

    def to_document(self) -> dict[str, Any]:
        return {
            "at": self.at,
            "target_day": self.target_day,
            "status": self.status,
            "generated": list(self.generated),
            "errors": list(self.errors),
            "pruned": list(self.pruned),
        }

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> RunRecord:
        def _text(key: str) -> str:
            value = document.get(key)
            if not isinstance(value, str):
                raise StateError(f"last_run.{key} must be a string")
            return value

        def _texts(key: str) -> tuple[str, ...]:
            value = document.get(key, [])
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                raise StateError(f"last_run.{key} must be a list of strings")
            return tuple(value)

        return cls(
            at=_text("at"),
            target_day=_text("target_day"),
            status=_text("status"),
            generated=_texts("generated"),
            errors=_texts("errors"),
            pruned=_texts("pruned"),
        )


@dataclass(frozen=True, slots=True)
class RunState:
    """The ledger: every completed day, plus the last run's outcome."""

    days: Mapping[str, DayRecord] = field(default_factory=dict)
    last_run: RunRecord | None = None

    def is_complete(self, day: date) -> bool:
        """True when ``day`` has already been generated and recorded."""
        return day.isoformat() in self.days

    def completed_days(self) -> tuple[date, ...]:
        """Every completed day, oldest first."""
        return tuple(sorted(date.fromisoformat(day) for day in self.days))

    def with_day(self, day: date, *, artifacts: int, at: str) -> RunState:
        """Return a copy with ``day`` recorded complete."""
        record = DayRecord(artifacts=artifacts, completed_at=at)
        return RunState(days={**self.days, day.isoformat(): record}, last_run=self.last_run)

    def with_run(self, record: RunRecord) -> RunState:
        """Return a copy whose ``last_run`` is ``record``."""
        return RunState(days=dict(self.days), last_run=record)

    def without_days(self, days: tuple[date, ...]) -> RunState:
        """Return a copy with ``days`` removed from the ledger.

        Removal, not a status change, is what keeps the ledger honest after retention
        deletes a directory: ``is_complete`` must not answer "yes" for a day whose
        artifact is gone. Backfill cannot resurrect the day either, because it only ever
        fills the gap after the newest known day.
        """
        dropped = {day.isoformat() for day in days}
        return RunState(days={key: value for key, value in self.days.items() if key not in dropped}, last_run=self.last_run)

    def to_document(self) -> dict[str, Any]:
        return {
            "version": STATE_VERSION,
            "days": {day: self.days[day].to_document() for day in sorted(self.days)},
            "last_run": None if self.last_run is None else self.last_run.to_document(),
        }

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> RunState:
        version = document.get("version")
        if version != STATE_VERSION:
            raise StateError(f"unsupported ledger version {version!r}; expected {STATE_VERSION}")
        raw_days = document.get("days", {})
        if not isinstance(raw_days, dict):
            raise StateError("days must be an object")
        days: dict[str, DayRecord] = {}
        for day, record in raw_days.items():
            if not isinstance(day, str) or not isinstance(record, dict):
                raise StateError(f"days[{day!r}] must be an object keyed by ISO date")
            try:
                date.fromisoformat(day)
            except ValueError as exc:
                raise StateError(f"days key {day!r} is not an ISO date") from exc
            days[day] = DayRecord.from_document(day, record)
        raw_run = document.get("last_run")
        if raw_run is not None and not isinstance(raw_run, dict):
            raise StateError("last_run must be null or an object")
        return cls(days=days, last_run=None if raw_run is None else RunRecord.from_document(raw_run))


def load_state(path: Path | None = None) -> RunState:
    """Read the ledger; a missing file is an empty ledger, a malformed one is refused.

    The asymmetry is intentional. "No ledger yet" is the normal first run. "Ledger I
    cannot parse" means the record of what was generated is gone, and continuing would
    silently regenerate days -- or worse, skip days whose artifacts were deleted. Only
    a human deleting the file on purpose should produce a fresh start.
    """
    target = STATE_PATH if path is None else path
    try:
        raw = target.read_text(encoding="utf-8")
    except FileNotFoundError:
        return RunState()
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise StateError(f"{target} is not valid JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise StateError(f"{target} must hold a JSON object, got {type(document).__name__}")
    return RunState.from_document(document)


def save_state(state: RunState, path: Path | None = None) -> Path:
    """Write ``state`` atomically; return the resolved path.

    Same-directory temp file plus ``os.replace``: a tick killed mid-write must not
    leave a truncated ledger that the next tick refuses to parse.
    """
    target = STATE_PATH if path is None else path
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(state.to_document(), indent=2, sort_keys=True) + "\n"
    temporary = target.with_name(f"{target.name}.{os.getpid()}.tmp")
    temporary.write_text(payload, encoding="utf-8")
    os.replace(temporary, target)
    return target


__all__ = [
    "STATE_PATH",
    "STATE_VERSION",
    "DayRecord",
    "RunRecord",
    "RunState",
    "StateError",
    "load_state",
    "save_state",
]
