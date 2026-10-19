"""Refusal guard: never start against real AWS credential material (FR-15, AC-15).

The Phase A0 audit recorded that this guard **does not exist anywhere in the tree**,
and that every ``AKIA``/``ASIA`` occurrence in the repository is a test fixture. Without
it, an operator with a populated ``~/.aws`` can launch the simulator and have the real
client chain resolve real credentials before anyone notices.

Two detections, both on **shape and configuration, never on a value**:

* an access-key-id shape (``AKIA``/``ASIA`` + 16 alphanumerics) in any of the standard
  environment variables or in ``AWS_SHARED_CREDENTIALS_FILE``;
* an ``AWS_PROFILE`` that names a profile actually present in the shared config file —
  the simulator never means to assume one.

**The refusal names the offending variable and never its value.** A message that echoes
a credential into a log is itself the leak this guard exists to prevent.

Invoked from ``__main__`` **before** any server binding, so a refusal costs no port and
no request. Mirrors the Phase 5 DSN gate's ``SAFETY REFUSAL`` / exit-2 behaviour.
"""

from __future__ import annotations

import configparser
import os
import re
from collections.abc import Mapping
from pathlib import Path

#: Access-key-id shapes. ``AKIA`` is a long-lived key, ``ASIA`` a temporary one.
_ACCESS_KEY_SHAPE = re.compile(r"^(AKIA|ASIA)[A-Z0-9]{16}$")

#: The variables boto3 itself reads before falling back to the profile chain.
_CREDENTIAL_ENV_VARS = (
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "AWS_SECURITY_TOKEN",
    "AWS_SHARED_CREDENTIALS_FILE",
)

#: Exit code for a refusal. 2 matches the Phase 5 DSN gate's contract.
REFUSAL_EXIT_CODE = 2


class SafetyRefusalError(RuntimeError):
    """Raised when real credential material is present. Fatal, before any bind."""


def _access_key_offences(env: Mapping[str, str]) -> list[str]:
    """Names of variables carrying an access-key-id shape (never their values)."""
    return [key for key in _CREDENTIAL_ENV_VARS if _ACCESS_KEY_SHAPE.match(env.get(key, "").strip())]


def _offending_profile(env: Mapping[str, str]) -> str | None:
    """Return the ``AWS_PROFILE`` value when it names a profile that exists.

    A profile name is not a secret, so it is safe to echo — and it is the only detail
    that lets an operator act on the refusal.
    """
    profile = env.get("AWS_PROFILE", "").strip()
    if not profile:
        return None
    config_path = Path(env.get("AWS_CONFIG_FILE", str(Path.home() / ".aws" / "config")))
    if not config_path.is_file():
        return None
    parser = configparser.ConfigParser()
    try:
        parser.read(config_path, encoding="utf-8")
    except (configparser.Error, OSError, UnicodeDecodeError):
        # An unreadable config cannot be shown to name a real profile, and treating a
        # parse failure as "safe" is right here: the guard blocks on evidence, and a
        # false refusal on a corrupt file would be its own failure mode.
        return None
    sections = set(parser.sections())
    return profile if f"profile {profile}" in sections or profile in sections else None


def assert_no_real_credentials(env: Mapping[str, str] | None = None) -> None:
    """Raise :class:`SafetyRefusalError` when real AWS credential material is detected.

    Called before any network or container work. Never returns a value, and never
    includes a credential in the message.
    """
    source: Mapping[str, str] = os.environ if env is None else env

    offences = _access_key_offences(source)
    if offences:
        raise SafetyRefusalError(
            "SAFETY REFUSAL: real AWS access-key material detected in "
            + ", ".join(sorted(offences))
            + ". This simulator must run with synthetic credentials only "
            "(see deploy/synthetic-clouds/.env.example). Values are never printed.",
        )

    profile = _offending_profile(source)
    if profile is not None:
        raise SafetyRefusalError(
            f"SAFETY REFUSAL: AWS_PROFILE={profile!r} names a profile present in the shared "
            "config. This simulator must not assume a real profile; unset AWS_PROFILE.",
        )
