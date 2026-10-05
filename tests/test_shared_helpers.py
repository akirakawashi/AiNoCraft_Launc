from __future__ import annotations

import base64
import hashlib
import inspect
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from threading import Event, Thread
from unittest.mock import patch

from core import auth, updater
from core.stream_download import DownloadProgress, download_to_file
from core.win_env import sanitize_child_env
from ui.api import LauncherAPI


class ChildEnvironmentTests(unittest.TestCase):
    def test_removes_frozen_python_environment_without_mutating_source(self) -> None:
        source = {
            "Path": os.pathsep.join((r"C:\Windows", r"C:\Temp\_MEI123", r"C:\Tools")),
            "PYTHONPATH": r"C:\launcher\python",
            "pythonhome": r"C:\launcher",
            "_PYI_APPLICATION_HOME_DIR": r"C:\Temp\_MEI123",
            "PYTHONNET_RUNTIME": "coreclr",
            "UNCHANGED": "value",
        }

        clean = sanitize_child_env(source)

        self.assertEqual(clean["Path"], os.pathsep.join((r"C:\Windows", r"C:\Tools")))
        self.assertEqual(clean["UNCHANGED"], "value")
        self.assertNotIn("PYTHONPATH", clean)
        self.assertNotIn("pythonhome", clean)
        self.assertNotIn("_PYI_APPLICATION_HOME_DIR", clean)
        self.assertNotIn("PYTHONNET_RUNTIME", clean)
        self.assertIn("PYTHONPATH", source)


class StreamDownloadTests(unittest.TestCase):
    def test_streams_file_reports_progress_and_hashes_content(self) -> None:
        payload = b"download-payload"
        response = io.BytesIO(payload)
        response.headers = {"content-length": str(len(payload))}  # type: ignore[attr-defined]
        progress: list[DownloadProgress] = []

        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / "nested" / "file.bin"
            with (
                patch("core.stream_download.urllib.request.urlopen", return_value=response),
                patch("core.stream_download.time.monotonic", side_effect=[0.0, 1.0, 2.0, 3.0, 4.0]),
            ):
                result = download_to_file(
                    "https://storage.example/file.bin",
                    destination,
                    user_agent="test-agent",
                    timeout=5,
                    chunk_size=4,
                    progress_interval=0,
                    on_progress=progress.append,
                )

            self.assertEqual(destination.read_bytes(), payload)

        self.assertFalse(result.cancelled)
        self.assertEqual(result.downloaded_bytes, len(payload))
        self.assertEqual(result.total_bytes, len(payload))
        self.assertEqual(result.sha256, hashlib.sha256(payload).hexdigest())
        self.assertEqual(progress[0].total_bytes, len(payload))
        self.assertEqual(progress[-1].downloaded_bytes, len(payload))

    def test_rejects_content_length_above_limit_before_writing(self) -> None:
        response = io.BytesIO(b"12345678")
        response.headers = {"content-length": "8"}  # type: ignore[attr-defined]

        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / "file.bin"
            with (
                patch("core.stream_download.urllib.request.urlopen", return_value=response),
                self.assertRaisesRegex(ValueError, "превышает допустимый лимит"),
            ):
                download_to_file(
                    "https://storage.example/file.bin",
                    destination,
                    user_agent="test-agent",
                    timeout=5,
                    chunk_size=4,
                    progress_interval=1,
                    max_bytes=7,
                )

            self.assertFalse(destination.exists())

    def test_enforces_limit_when_content_length_is_missing(self) -> None:
        response = io.BytesIO(b"123456789")
        response.headers = {}  # type: ignore[attr-defined]

        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / "file.bin"
            with (
                patch("core.stream_download.urllib.request.urlopen", return_value=response),
                self.assertRaisesRegex(ValueError, "превышает допустимый лимит"),
            ):
                download_to_file(
                    "https://storage.example/file.bin",
                    destination,
                    user_agent="test-agent",
                    timeout=5,
                    chunk_size=4,
                    progress_interval=1,
                    max_bytes=8,
                )

            self.assertEqual(destination.read_bytes(), b"12345678")

    def test_cancellation_returns_partial_download(self) -> None:
        cancel_event = Event()

        class CancellingResponse(io.BytesIO):
            headers = {"content-length": "8"}

            def read(self, size: int = -1) -> bytes:
                chunk = super().read(size)
                if chunk:
                    cancel_event.set()
                return chunk

        response = CancellingResponse(b"12345678")
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / "file.bin"
            with patch("core.stream_download.urllib.request.urlopen", return_value=response):
                result = download_to_file(
                    "https://storage.example/file.bin",
                    destination,
                    user_agent="test-agent",
                    timeout=5,
                    chunk_size=4,
                    progress_interval=1,
                    cancel_event=cancel_event,
                )

            self.assertEqual(destination.read_bytes(), b"1234")

        self.assertTrue(result.cancelled)
        self.assertEqual(result.downloaded_bytes, 4)

    def test_updater_uses_streamed_hash_for_downloaded_exe(self) -> None:
        payload = b"MZ" + bytes(128 * 1024 - 2)
        expected_sha256 = hashlib.sha256(payload).hexdigest()
        response = io.BytesIO(payload)
        response.headers = {"content-length": str(len(payload))}  # type: ignore[attr-defined]

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            destination = root / "update.exe"
            current_exe = root / "current.exe"
            with (
                patch("core.stream_download.urllib.request.urlopen", return_value=response),
                patch("core.updater._apply_update") as apply_update,
            ):
                updater._download_and_apply(
                    "https://storage.example/update.exe",
                    destination,
                    current_exe,
                    expected_sha256,
                )

            self.assertEqual(destination.read_bytes(), payload)
            apply_update.assert_called_once_with(destination, current_exe)


class SynchronousAuthTests(unittest.TestCase):
    def test_auth_entrypoints_are_synchronous(self) -> None:
        self.assertFalse(inspect.iscoroutinefunction(auth.login))
        self.assertFalse(inspect.iscoroutinefunction(auth.refresh_session))
        self.assertFalse(inspect.iscoroutinefunction(auth.logout))
        self.assertFalse(inspect.iscoroutinefunction(auth.validate_access_token))

    def test_ui_login_uses_auth_result_directly(self) -> None:
        api = LauncherAPI()
        auth_result = {"success": False, "error": "rejected"}

        with patch("ui.api.auth.login", return_value=auth_result) as login:
            result = api.login(" user ", "password")

        self.assertIs(result, auth_result)
        login.assert_called_once_with("user", "password")

    def test_game_texture_is_never_used_as_launcher_avatar(self) -> None:
        texture_payload = base64.b64encode(
            json.dumps(
                {
                    "textures": {
                        "SKIN": {
                            "url": "https://storage.example.test/skin-media/skins/knight.png",
                        }
                    }
                }
            ).encode("utf-8")
        ).decode("ascii")

        result = auth.AuthService()._normalize_auth_response(
            {
                "accessToken": "game-access-token",
                "clientToken": "client-token",
                "user": {
                    "id": "profile-id",
                    "properties": [{"name": "textures", "value": texture_payload}],
                },
            },
            "Player",
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["avatar_url"], "")


class LauncherAPIConcurrencyTests(unittest.TestCase):
    def test_logout_waits_for_refresh_and_clears_refreshed_user(self) -> None:
        api = LauncherAPI()
        api._user = {
            "username": "Alice",
            "token": "old-access",
            "client_token": "client-token",
            "selected_profile_id": "profile-id",
            "user_type": "mojang",
        }
        refresh_entered = Event()
        release_refresh = Event()
        logout_attempted = Event()
        server_logout_entered = Event()
        outcomes: dict[str, object] = {}
        errors: list[BaseException] = []

        def refresh_session() -> dict[str, object]:
            refresh_entered.set()
            if not release_refresh.wait(1):
                raise AssertionError("refresh was not released")
            return {
                "success": True,
                "username": "Alice",
                "token": "new-access",
                "client_token": "client-token",
                "selected_profile_id": "profile-id",
                "user_type": "mojang",
            }

        def logout_service() -> dict[str, object]:
            server_logout_entered.set()
            return {"success": True}

        def restore_user() -> None:
            try:
                outcomes["user"] = api.get_current_user()
            except BaseException as exc:  # pragma: no cover - reported by the main test thread
                errors.append(exc)

        def logout_user() -> None:
            logout_attempted.set()
            try:
                outcomes["logout"] = api.logout()
            except BaseException as exc:  # pragma: no cover - reported by the main test thread
                errors.append(exc)

        with (
            patch("ui.api.auth.validate_access_token", return_value=False),
            patch("ui.api.auth.refresh_session", side_effect=refresh_session),
            patch("ui.api.auth.logout", side_effect=logout_service),
        ):
            restore_thread = Thread(target=restore_user)
            restore_thread.start()
            self.assertTrue(refresh_entered.wait(1))

            logout_thread = Thread(target=logout_user)
            logout_thread.start()
            self.assertTrue(logout_attempted.wait(1))
            self.assertFalse(server_logout_entered.wait(0.05))
            self.assertTrue(logout_thread.is_alive())

            release_refresh.set()
            restore_thread.join(1)
            logout_thread.join(1)

        self.assertFalse(restore_thread.is_alive())
        self.assertFalse(logout_thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(outcomes["user"], {
            "logged_in": True,
            "username": "Alice",
            "role": "default",
            "role_label": "Default",
            "ring_color": "#aab1c2",
            "avatar_url": "",
        })
        self.assertEqual(outcomes["logout"], {"success": True})
        self.assertIsNone(api._user)

    def test_launch_uses_complete_user_snapshot_when_logout_follows(self) -> None:
        api = LauncherAPI()
        api._user = {
            "username": "Alice",
            "token": "access-token",
            "client_token": "client-token",
            "selected_profile_id": "profile-id",
            "user_type": "mojang",
        }
        launch_entered = Event()
        release_launch = Event()
        logout_done = Event()
        captured: dict[str, object] = {}
        outcomes: dict[str, object] = {}
        errors: list[BaseException] = []

        def launch_service(*args: object, **kwargs: object) -> dict[str, object]:
            captured["args"] = args
            captured["kwargs"] = kwargs
            launch_entered.set()
            if not release_launch.wait(1):
                raise AssertionError("launch was not released")
            return {"success": True, "pid": 123}

        def launch_game() -> None:
            try:
                outcomes["launch"] = api.launch_game("tech")
            except BaseException as exc:  # pragma: no cover - reported by the main test thread
                errors.append(exc)

        def logout_user() -> None:
            try:
                outcomes["logout"] = api.logout()
            except BaseException as exc:  # pragma: no cover - reported by the main test thread
                errors.append(exc)
            finally:
                logout_done.set()

        with (
            patch("ui.api.auth.validate_access_token", return_value=True),
            patch("ui.api.downloader.get_build_state", return_value={"installed": True, "update_available": False}),
            patch("ui.api.cfg.load", return_value={"ram": 6}),
            patch("ui.api.ram_limits", return_value={"ram_default_gb": 6}),
            patch("ui.api.game.launch", side_effect=launch_service),
            patch("ui.api.auth.logout", return_value={"success": True}),
        ):
            launch_thread = Thread(target=launch_game)
            launch_thread.start()
            self.assertTrue(launch_entered.wait(1))

            logout_thread = Thread(target=logout_user)
            logout_thread.start()
            self.assertTrue(logout_done.wait(1))
            self.assertIsNone(api._user)

            release_launch.set()
            launch_thread.join(1)
            logout_thread.join(1)

        self.assertFalse(launch_thread.is_alive())
        self.assertFalse(logout_thread.is_alive())
        self.assertEqual(errors, [])
        launch_args = captured["args"]
        launch_kwargs = captured["kwargs"]
        self.assertIsInstance(launch_args, tuple)
        self.assertIsInstance(launch_kwargs, dict)
        self.assertEqual(launch_args[1], "Alice")
        self.assertEqual(launch_kwargs["access_token"], "access-token")
        self.assertEqual(launch_kwargs["auth_uuid"], "profile-id")
        self.assertEqual(launch_kwargs["client_id"], "client-token")
        self.assertEqual(outcomes["launch"], {"success": True, "pid": 123})
        self.assertEqual(outcomes["logout"], {"success": True})

    def test_select_build_waits_for_lazy_selection_resolution(self) -> None:
        api = LauncherAPI()
        read_entered = Event()
        release_read = Event()
        preference_written = Event()
        select_attempted = Event()
        outcomes: dict[str, object] = {}
        errors: list[BaseException] = []

        def get_last_build_id() -> str:
            read_entered.set()
            if not release_read.wait(1):
                raise AssertionError("preference read was not released")
            return "tech"

        def set_last_build_id(build_id: str) -> bool:
            outcomes["persisted"] = build_id
            preference_written.set()
            return True

        def resolve_selection() -> None:
            try:
                outcomes["resolved"] = api._resolve_selected_build_id()
            except BaseException as exc:  # pragma: no cover - reported by the main test thread
                errors.append(exc)

        def select_build() -> None:
            select_attempted.set()
            try:
                outcomes["selected"] = api.select_build("magic")
            except BaseException as exc:  # pragma: no cover - reported by the main test thread
                errors.append(exc)

        with (
            patch.object(api, "_ensure_bootstrap", return_value=None),
            patch("ui.api.user_prefs.get_last_build_id", side_effect=get_last_build_id),
            patch("ui.api.user_prefs.set_last_build_id", side_effect=set_last_build_id),
            patch("ui.api.downloader.get_build_state", return_value={}),
        ):
            resolve_thread = Thread(target=resolve_selection)
            resolve_thread.start()
            self.assertTrue(read_entered.wait(1))

            select_thread = Thread(target=select_build)
            select_thread.start()
            self.assertTrue(select_attempted.wait(1))
            self.assertFalse(preference_written.wait(0.05))
            self.assertTrue(select_thread.is_alive())

            release_read.set()
            resolve_thread.join(1)
            select_thread.join(1)

        self.assertFalse(resolve_thread.is_alive())
        self.assertFalse(select_thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(outcomes["resolved"], "tech")
        self.assertEqual(outcomes["persisted"], "magic")
        self.assertEqual(outcomes["selected"]["selected_build_id"], "magic")
        self.assertEqual(api._selected_build_id, "magic")


if __name__ == "__main__":
    unittest.main()
