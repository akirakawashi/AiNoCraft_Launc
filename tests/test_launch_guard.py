from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import launcher
from core.launch_guard import (
    TICKET_PATH_ENV,
    TOKEN_ENV,
    LaunchGuardResult,
    validate_bootstrap_launch,
)


class LaunchGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_directory.cleanup)
        self.root = Path(self.temp_directory.name)
        self.launcher_root = self.root / "Launcher"
        self.executable = self.launcher_root / "current" / "AiNoCraftLauncher.exe"
        self.run_directory = self.launcher_root / "data" / "run"
        self.run_directory.mkdir(parents=True)
        self.now = datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc)
        self.token = "test-bootstrap-token"

    def _write_ticket(
        self,
        *,
        token: str | None = None,
        issued_at: datetime | None = None,
        expires_at: datetime | None = None,
        launcher_path: Path | None = None,
    ) -> tuple[Path, dict[str, str]]:
        ticket_path = self.run_directory / f"launch-{'a' * 32}.ticket.json"
        ticket_token = self.token if token is None else token
        ticket = {
            "schema": 1,
            "token_sha256": hashlib.sha256(ticket_token.encode("utf-8")).hexdigest(),
            "issued_at": (issued_at or self.now - timedelta(seconds=1))
            .isoformat()
            .replace("+00:00", "Z"),
            "expires_at": (expires_at or self.now + timedelta(seconds=30))
            .isoformat()
            .replace("+00:00", "Z"),
            "launcher_path": str(launcher_path or self.executable),
        }
        ticket_path.write_text(json.dumps(ticket), encoding="utf-8")
        environment = {
            TICKET_PATH_ENV: str(ticket_path),
            TOKEN_ENV: self.token,
        }
        return ticket_path, environment

    def _validate(self, environment: dict[str, str]):
        return validate_bootstrap_launch(
            frozen=True,
            executable=self.executable,
            now=self.now,
            environ=environment,
        )

    def test_valid_ticket_is_consumed(self) -> None:
        ticket_path, environment = self._write_ticket()

        result = self._validate(environment)

        self.assertTrue(result.allowed)
        self.assertFalse(ticket_path.exists())
        self.assertEqual(list(self.run_directory.glob("*.consumed.*")), [])

    def test_missing_ticket_is_rejected(self) -> None:
        result = self._validate({})

        self.assertFalse(result.allowed)
        self.assertEqual(result.reason, "missing_ticket")

    def test_bad_token_is_rejected(self) -> None:
        ticket_path, environment = self._write_ticket(token="different-token")

        result = self._validate(environment)

        self.assertFalse(result.allowed)
        self.assertEqual(result.reason, "token_mismatch")
        self.assertFalse(ticket_path.exists())

    def test_expired_ticket_is_rejected(self) -> None:
        ticket_path, environment = self._write_ticket(
            issued_at=self.now - timedelta(minutes=1),
            expires_at=self.now - timedelta(seconds=1),
        )

        result = self._validate(environment)

        self.assertFalse(result.allowed)
        self.assertEqual(result.reason, "ticket_expired")
        self.assertFalse(ticket_path.exists())

    def test_ticket_for_another_executable_is_rejected(self) -> None:
        ticket_path, environment = self._write_ticket(
            launcher_path=self.root / "AnotherLauncher.exe"
        )

        result = self._validate(environment)

        self.assertFalse(result.allowed)
        self.assertEqual(result.reason, "launcher_path_mismatch")
        self.assertFalse(ticket_path.exists())

    def test_ticket_outside_run_directory_is_rejected_without_touching_file(self) -> None:
        ticket_path, environment = self._write_ticket()
        external_path = self.root / ticket_path.name
        ticket_path.replace(external_path)
        environment[TICKET_PATH_ENV] = str(external_path)

        result = self._validate(environment)

        self.assertFalse(result.allowed)
        self.assertEqual(result.reason, "invalid_ticket_path")
        self.assertTrue(external_path.exists())

    def test_unexpected_ticket_name_is_rejected_without_touching_file(self) -> None:
        ticket_path, environment = self._write_ticket()
        unexpected_path = self.run_directory / "launch-ticket.json"
        ticket_path.replace(unexpected_path)
        environment[TICKET_PATH_ENV] = str(unexpected_path)

        result = self._validate(environment)

        self.assertFalse(result.allowed)
        self.assertEqual(result.reason, "invalid_ticket_path")
        self.assertTrue(unexpected_path.exists())

    def test_ticket_cannot_be_reused(self) -> None:
        ticket_path, environment = self._write_ticket()
        first_environment = environment.copy()
        second_environment = environment.copy()

        first_result = self._validate(first_environment)
        second_result = self._validate(second_environment)

        self.assertTrue(first_result.allowed)
        self.assertFalse(second_result.allowed)
        self.assertEqual(second_result.reason, "ticket_unavailable")
        self.assertFalse(ticket_path.exists())

    def test_environment_is_cleared_after_validation(self) -> None:
        _, environment = self._write_ticket()
        environment["UNRELATED"] = "preserved"

        self._validate(environment)

        self.assertNotIn(TICKET_PATH_ENV, environment)
        self.assertNotIn(TOKEN_ENV, environment)
        self.assertEqual(environment["UNRELATED"], "preserved")

    def test_source_run_bypasses_ticket_and_clears_reserved_environment(self) -> None:
        environment = {
            TICKET_PATH_ENV: str(self.root / "does-not-exist.json"),
            TOKEN_ENV: self.token,
        }

        result = validate_bootstrap_launch(frozen=False, environ=environment)

        self.assertTrue(result.allowed)
        self.assertEqual(environment, {})

    @patch("launcher._show_bootstrap_required_dialog")
    @patch(
        "core.launch_guard.validate_bootstrap_launch",
        return_value=LaunchGuardResult(allowed=False, reason="missing_ticket"),
    )
    def test_main_rejects_before_importing_webview(
        self,
        _validate_mock,
        dialog_mock,
    ) -> None:
        with patch.dict(sys.modules, {"webview": None}):
            exit_code = launcher.main()

        self.assertEqual(exit_code, 20)
        dialog_mock.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
