"""Validate one-time bootstrap launch tickets for packaged launcher builds."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import string
import sys
import uuid
from collections.abc import MutableMapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


TICKET_PATH_ENV = "AINOCRAFT_LAUNCH_TICKET_PATH"
TOKEN_ENV = "AINOCRAFT_LAUNCH_TOKEN"
TICKET_SCHEMA = 1
MAX_TICKET_SIZE_BYTES = 64 * 1024
TICKET_FILENAME_PATTERN = re.compile(r"launch-[0-9a-f]{32}\.ticket\.json", re.ASCII)


@dataclass(frozen=True, slots=True)
class LaunchGuardResult:
    """Result of checking whether this launcher process may continue."""

    allowed: bool
    reason: str | None = None


def _parse_utc_timestamp(value: object) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("timestamp is missing")

    normalized = value.strip()
    if normalized.endswith(("Z", "z")):
        normalized = normalized[:-1] + "+00:00"

    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must include a UTC offset")
    return parsed.astimezone(timezone.utc)


def _normalized_path(value: str | os.PathLike[str]) -> str:
    path = os.path.abspath(os.path.realpath(os.fspath(value)))
    return os.path.normcase(os.path.normpath(path))


def _take_ticket(ticket_path: Path) -> Path:
    """Atomically take ownership of a ticket so no second process can use it."""

    consumed_path = ticket_path.with_name(
        f"{ticket_path.name}.consumed.{os.getpid()}.{uuid.uuid4().hex}"
    )
    os.replace(ticket_path, consumed_path)
    return consumed_path


def _is_expected_ticket_path(
    ticket_path: Path,
    executable: str | os.PathLike[str],
) -> bool:
    """Limit ticket consumption to the launcher's dedicated run directory."""

    if not ticket_path.is_absolute():
        return False
    if TICKET_FILENAME_PATTERN.fullmatch(ticket_path.name) is None:
        return False

    executable_path = Path(os.path.abspath(os.fspath(executable)))
    expected_run_directory = executable_path.parent.parent / "data" / "run"
    return _normalized_path(ticket_path.parent) == _normalized_path(
        expected_run_directory
    )


def _deny(reason: str) -> LaunchGuardResult:
    return LaunchGuardResult(allowed=False, reason=reason)


def validate_bootstrap_launch(
    *,
    frozen: bool | None = None,
    executable: str | os.PathLike[str] | None = None,
    now: datetime | None = None,
    environ: MutableMapping[str, str] | None = None,
) -> LaunchGuardResult:
    """Validate and consume the bootstrap ticket for a packaged launcher.

    The token is removed from the process environment before any validation so
    it cannot be inherited by Minecraft or another child process. Source runs
    are intentionally allowed and do not require a ticket.

    ``frozen``, ``executable``, ``now`` and ``environ`` are injectable to keep
    the security-sensitive behavior deterministic in unit tests.
    """

    process_environment = os.environ if environ is None else environ
    ticket_path_value = process_environment.pop(TICKET_PATH_ENV, None)
    token = process_environment.pop(TOKEN_ENV, None)

    is_frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    if not is_frozen:
        return LaunchGuardResult(allowed=True)

    if not ticket_path_value or not token:
        return _deny("missing_ticket")

    expected_executable = executable if executable is not None else sys.executable
    try:
        ticket_path = Path(ticket_path_value)
        if not _is_expected_ticket_path(ticket_path, expected_executable):
            return _deny("invalid_ticket_path")
    except (OSError, TypeError, ValueError):
        return _deny("invalid_ticket_path")

    consumed_path: Path | None = None
    try:
        consumed_path = _take_ticket(ticket_path)
    except (OSError, ValueError):
        return _deny("ticket_unavailable")

    try:
        if consumed_path.stat().st_size > MAX_TICKET_SIZE_BYTES:
            return _deny("invalid_ticket")

        with consumed_path.open("r", encoding="utf-8") as ticket_file:
            ticket = json.load(ticket_file)

        if not isinstance(ticket, dict) or ticket.get("schema") != TICKET_SCHEMA:
            return _deny("invalid_ticket")

        expected_hash = ticket.get("token_sha256")
        if (
            not isinstance(expected_hash, str)
            or len(expected_hash) != 64
            or any(character not in string.hexdigits for character in expected_hash)
        ):
            return _deny("invalid_ticket")

        actual_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        if not hmac.compare_digest(actual_hash, expected_hash.lower()):
            return _deny("token_mismatch")

        issued_at = _parse_utc_timestamp(ticket.get("issued_at"))
        expires_at = _parse_utc_timestamp(ticket.get("expires_at"))
        current_time = now or datetime.now(timezone.utc)
        if current_time.tzinfo is None or current_time.utcoffset() is None:
            current_time = current_time.replace(tzinfo=timezone.utc)
        else:
            current_time = current_time.astimezone(timezone.utc)

        if expires_at < issued_at or current_time < issued_at or current_time > expires_at:
            return _deny("ticket_expired")

        launcher_path = ticket.get("launcher_path")
        if not isinstance(launcher_path, str) or not launcher_path.strip():
            return _deny("invalid_ticket")
        if _normalized_path(launcher_path) != _normalized_path(expected_executable):
            return _deny("launcher_path_mismatch")

        return LaunchGuardResult(allowed=True)
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
        return _deny("invalid_ticket")
    finally:
        try:
            consumed_path.unlink(missing_ok=True)
        except OSError:
            pass
