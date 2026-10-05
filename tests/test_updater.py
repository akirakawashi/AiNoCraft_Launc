from __future__ import annotations

import hashlib
import inspect
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from core import updater


class StartUpdateTests(unittest.TestCase):
    """start_update must derive url+sha from the trusted manifest, not the caller."""

    def setUp(self) -> None:
        self._patches = [
            patch.object(updater, "LAUNCHER_UPDATE_ENABLED", True),
            patch.object(updater, "_is_frozen_exe", return_value=True),
            patch.object(updater, "_current_exe", return_value=Path("C:/app/AiNoCraftLauncher.exe")),
        ]
        for p in self._patches:
            p.start()
        updater._thread = None

    def tearDown(self) -> None:
        if updater._thread is not None:
            updater._thread.join(timeout=5)
        for p in self._patches:
            p.stop()
        updater._thread = None

    def _run(self, check_result: dict) -> tuple[dict, dict]:
        captured: dict = {}
        done = threading.Event()

        def fake_apply(url, dest, current_exe, sha):
            captured["args"] = (url, dest, current_exe, sha)
            done.set()

        with patch.object(updater, "check_for_update", return_value=check_result), \
                patch.object(updater, "_download_and_apply", side_effect=fake_apply):
            result = updater.start_update()
            if updater._thread is not None:
                updater._thread.join(timeout=5)
        captured["done"] = done.is_set()
        return result, captured

    def test_signature_accepts_no_arguments(self) -> None:
        self.assertEqual(list(inspect.signature(updater.start_update).parameters), [])

    def test_uses_manifest_url_and_sha_not_caller(self) -> None:
        sha = "a" * 64
        check = {
            "available": True,
            "remote_version": "2.0.0",
            "download_url": "https://storage.ainocraft.com/launcher/releases/2.0.0/AiNoCraftLauncher.exe",
            "sha256": sha,
            "error": None,
        }
        result, captured = self._run(check)

        self.assertTrue(result["success"])
        self.assertTrue(captured["done"])
        url, _dest, _exe, passed_sha = captured["args"]
        self.assertEqual(url, check["download_url"])
        self.assertEqual(passed_sha, sha)

    def test_no_update_available_does_not_download(self) -> None:
        check = {"available": False, "remote_version": "1.0.0", "download_url": None, "sha256": None, "error": None}
        result, captured = self._run(check)

        self.assertFalse(result["success"])
        self.assertNotIn("args", captured)

    def test_manifest_error_is_returned(self) -> None:
        check = {"available": False, "remote_version": None, "download_url": None, "sha256": None, "error": "Backend недоступен"}
        result, captured = self._run(check)

        self.assertFalse(result["success"])
        self.assertNotIn("args", captured)

    def test_rejects_insecure_manifest_url(self) -> None:
        check = {"available": True, "remote_version": "2.0.0", "download_url": "http://evil.example/x.exe", "sha256": "a" * 64, "error": None}
        result, captured = self._run(check)

        self.assertFalse(result["success"])
        self.assertNotIn("args", captured)

    def test_rejects_missing_manifest_sha(self) -> None:
        check = {"available": True, "remote_version": "2.0.0", "download_url": "https://storage/x.exe", "sha256": "", "error": None}
        result, captured = self._run(check)

        self.assertFalse(result["success"])
        self.assertNotIn("args", captured)

    def test_disabled_when_flag_off(self) -> None:
        with patch.object(updater, "LAUNCHER_UPDATE_ENABLED", False):
            result = updater.start_update()
        self.assertFalse(result["success"])


class VerifyDownloadedExeTests(unittest.TestCase):
    """The exe hash check is mandatory (no more optional sha bypass)."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _write(self, data: bytes) -> Path:
        path = self.root / "update.exe"
        path.write_bytes(data)
        return path

    def test_requires_sha(self) -> None:
        path = self._write(b"MZ" + b"\x00" * (200 * 1024))
        with self.assertRaises(ValueError):
            updater._verify_downloaded_exe(path, "", actual_sha256="a" * 64)

    def test_rejects_small_file(self) -> None:
        path = self._write(b"MZ")
        with self.assertRaises(ValueError):
            updater._verify_downloaded_exe(path, "a" * 64, actual_sha256="a" * 64)

    def test_rejects_non_mz(self) -> None:
        data = b"XX" + b"\x00" * (200 * 1024)
        path = self._write(data)
        with self.assertRaises(ValueError):
            updater._verify_downloaded_exe(path, hashlib.sha256(data).hexdigest())

    def test_rejects_hash_mismatch(self) -> None:
        path = self._write(b"MZ" + b"\x00" * (200 * 1024))
        with self.assertRaises(ValueError):
            updater._verify_downloaded_exe(path, "b" * 64, actual_sha256="a" * 64)

    def test_accepts_matching(self) -> None:
        data = b"MZ" + b"\x00" * (200 * 1024)
        path = self._write(data)
        digest = hashlib.sha256(data).hexdigest()
        updater._verify_downloaded_exe(path, digest, actual_sha256=digest)


if __name__ == "__main__":
    unittest.main()
