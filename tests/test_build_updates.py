from __future__ import annotations

import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from config import profiles
from config.profiles import BuildPaths
from core import downloader
from core.enums import DownloadState

def make_paths(root: Path, revision: str = "2", archive_sha256: str = "") -> BuildPaths:
    game_dir = root / "AiNoCraftTech"
    version_dir = game_dir / "versions" / "Tech"
    return BuildPaths(
        build_id="tech",
        build_name="tech",
        download_url="https://storage.example/downloads/AiNoCraftTech-2.zip",
        revision=revision,
        game_dir=game_dir,
        marker_file=game_dir / "ainocraft-build.json",
        java_bin=game_dir / "java" / "bin" / "javaw.exe",
        version_name="Tech",
        version_dir=version_dir,
        version_json=version_dir / "Tech.json",
        client_jar=version_dir / "Tech.jar",
        assets_dir=game_dir / "assets",
        libraries_dir=game_dir / "libraries",
        natives_dir=version_dir / "natives",
        settings_file=version_dir / "launcher_settings.json",
        archive_sha256=archive_sha256,
    )


def write_valid_build(paths: BuildPaths, revision: str) -> None:
    paths.version_dir.mkdir(parents=True, exist_ok=True)
    paths.version_json.write_text("{}", encoding="utf-8")
    paths.client_jar.write_bytes(b"jar")
    paths.marker_file.write_text(
        json.dumps({"build_id": paths.build_id, "revision": revision}),
        encoding="utf-8",
    )


class ManifestTests(unittest.TestCase):
    def test_shared_manifest_updates_known_profile(self) -> None:
        original = profiles._BUILD_PROFILES["tech"]
        try:
            applied = profiles.apply_build_manifest(
                {
                    "format": 1,
                    "builds": {
                        "tech": {
                            "revision": "2026.07.10-01",
                            "download_url": "downloads/AiNoCraftTech-2026.07.10-01.zip",
                            "archive_size_bytes": 123,
                            "unpacked_size_bytes": 456,
                        }
                    },
                }
            )
            paths = profiles.get_build_paths("tech")
        finally:
            with profiles._registry_lock:
                profiles._BUILD_PROFILES["tech"] = original

        self.assertEqual(applied, 1)
        self.assertEqual(paths.revision, "2026.07.10-01")
        self.assertTrue(paths.download_url.endswith("downloads/AiNoCraftTech-2026.07.10-01.zip"))
        self.assertEqual(paths.archive_size_bytes, 123)
        self.assertEqual(paths.unpacked_size_bytes, 456)


class BuildStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.manager = downloader.DownloadManager()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def state_for(self, paths: BuildPaths) -> dict[str, object]:
        with patch.object(downloader, "get_build_paths", return_value=paths):
            return self.manager.get_build_state(paths.build_id)

    def test_current_build(self) -> None:
        paths = make_paths(self.root, revision="2")
        write_valid_build(paths, revision="2")

        state = self.state_for(paths)

        self.assertTrue(state["installed"])
        self.assertTrue(state["up_to_date"])
        self.assertFalse(state["update_available"])
        self.assertEqual(state["install_state"], "current")

    def test_outdated_build(self) -> None:
        paths = make_paths(self.root, revision="2")
        write_valid_build(paths, revision="1")

        state = self.state_for(paths)

        self.assertTrue(state["installed"])
        self.assertTrue(state["update_available"])
        self.assertEqual(state["local_revision"], "1")
        self.assertEqual(state["remote_revision"], "2")

    def test_valid_build_can_run_when_manifest_is_unavailable(self) -> None:
        paths = make_paths(self.root, revision="")
        write_valid_build(paths, revision="1")

        state = self.state_for(paths)

        self.assertTrue(state["installed"])
        self.assertFalse(state["update_known"])
        self.assertEqual(state["install_state"], "offline")

    def test_missing_marker_is_damaged(self) -> None:
        paths = make_paths(self.root, revision="2")
        paths.version_dir.mkdir(parents=True)
        paths.version_json.write_text("{}", encoding="utf-8")
        paths.client_jar.write_bytes(b"jar")

        state = self.state_for(paths)

        self.assertFalse(state["installed"])
        self.assertTrue(state["damaged"])


class StagedInstallTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.manager = downloader.DownloadManager()
        self.paths = make_paths(self.root, revision="2")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_staging_revision_must_match_manifest(self) -> None:
        staging = self.manager._staging_path_for(self.paths)
        staged_paths = self.manager._rebase_paths(self.paths, staging)
        write_valid_build(staged_paths, revision="1")

        with self.assertRaisesRegex(ValueError, "не совпадает"):
            self.manager._validate_staging(self.paths, staging)

    def test_activation_replaces_old_build(self) -> None:
        write_valid_build(self.paths, revision="1")
        (self.paths.game_dir / "old.txt").write_text("old", encoding="utf-8")
        staging = self.manager._staging_path_for(self.paths)
        staged_paths = self.manager._rebase_paths(self.paths, staging)
        write_valid_build(staged_paths, revision="2")
        (staging / "new.txt").write_text("new", encoding="utf-8")

        self.manager._activate_staging(self.paths, staging)

        self.assertFalse((self.paths.game_dir / "old.txt").exists())
        self.assertTrue((self.paths.game_dir / "new.txt").exists())
        self.assertFalse(self.manager._backup_path_for(self.paths).exists())

    @staticmethod
    def archive_bytes(revision: str) -> bytes:
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr(
                "ainocraft-build.json",
                json.dumps({"build_id": "tech", "revision": revision}),
            )
            archive.writestr("versions/Tech/Tech.json", "{}")
            archive.writestr("versions/Tech/Tech.jar", b"jar")
            archive.writestr("new.txt", "new")
        return output.getvalue()

    def run_worker_with_archive(self, archive_data: bytes, expected_sha256: str | None = None) -> None:
        if expected_sha256 is None:
            expected_sha256 = hashlib.sha256(archive_data).hexdigest()
        self.paths = replace(self.paths, archive_sha256=expected_sha256)
        response = io.BytesIO(archive_data)
        response.headers = {"content-length": str(len(archive_data))}  # type: ignore[attr-defined]
        with (
            patch("core.stream_download.urllib.request.urlopen", return_value=response),
            patch.object(downloader, "MIN_DISK_RESERVE_BYTES", 0),
        ):
            self.manager._worker(
                self.paths,
                self.paths.download_url,
                self.root / "download.zip",
            )

    def test_worker_preserves_settings_and_installs_matching_revision(self) -> None:
        write_valid_build(self.paths, revision="1")
        self.paths.settings_file.write_text('{"ram": 8}', encoding="utf-8")

        self.run_worker_with_archive(self.archive_bytes("2"))

        self.assertEqual(self.manager.get_status()["state"], DownloadState.DONE.value)
        self.assertEqual(self.paths.settings_file.read_text(encoding="utf-8"), '{"ram": 8}')
        self.assertTrue((self.paths.game_dir / "new.txt").exists())
        marker = json.loads(self.paths.marker_file.read_text(encoding="utf-8"))
        self.assertEqual(marker["revision"], "2")

    def test_worker_keeps_old_build_when_archive_revision_is_wrong(self) -> None:
        write_valid_build(self.paths, revision="1")
        (self.paths.game_dir / "old.txt").write_text("old", encoding="utf-8")

        self.run_worker_with_archive(self.archive_bytes("wrong"))

        status = self.manager.get_status()
        self.assertEqual(status["state"], DownloadState.ERROR.value)
        self.assertIn("не совпадает", str(status["error"]))
        self.assertTrue((self.paths.game_dir / "old.txt").exists())
        self.assertFalse((self.paths.game_dir / "new.txt").exists())

    def test_worker_rejects_tampered_archive(self) -> None:
        write_valid_build(self.paths, revision="1")
        (self.paths.game_dir / "old.txt").write_text("old", encoding="utf-8")

        self.run_worker_with_archive(self.archive_bytes("2"), expected_sha256="0" * 64)

        status = self.manager.get_status()
        self.assertEqual(status["state"], DownloadState.ERROR.value)
        self.assertIn("SHA-256", str(status["error"]))
        self.assertTrue((self.paths.game_dir / "old.txt").exists())
        self.assertFalse((self.paths.game_dir / "new.txt").exists())

    def test_worker_requires_hash_in_prod(self) -> None:
        write_valid_build(self.paths, revision="1")
        (self.paths.game_dir / "old.txt").write_text("old", encoding="utf-8")

        with patch.object(downloader, "RUNTIME", SimpleNamespace(is_dev=False)):
            self.run_worker_with_archive(self.archive_bytes("2"), expected_sha256="")

        status = self.manager.get_status()
        self.assertEqual(status["state"], DownloadState.ERROR.value)
        self.assertIn("sha256", str(status["error"]).lower())
        self.assertTrue((self.paths.game_dir / "old.txt").exists())
        self.assertFalse((self.paths.game_dir / "new.txt").exists())

    def test_worker_allows_missing_hash_in_dev(self) -> None:
        with patch.object(downloader, "RUNTIME", SimpleNamespace(is_dev=True)):
            self.run_worker_with_archive(self.archive_bytes("2"), expected_sha256="")

        self.assertEqual(self.manager.get_status()["state"], DownloadState.DONE.value)
        self.assertTrue((self.paths.game_dir / "new.txt").exists())

    def test_worker_rejects_archive_over_unpacked_limit(self) -> None:
        write_valid_build(self.paths, revision="1")
        (self.paths.game_dir / "old.txt").write_text("old", encoding="utf-8")

        with patch.object(downloader, "MAX_GAME_UNPACKED_BYTES", 10):
            self.run_worker_with_archive(self.archive_bytes("2"))

        status = self.manager.get_status()
        self.assertEqual(status["state"], DownloadState.ERROR.value)
        self.assertIn("Суммарный размер", str(status["error"]))
        self.assertTrue((self.paths.game_dir / "old.txt").exists())
        self.assertFalse((self.paths.game_dir / "new.txt").exists())

    def test_worker_rejects_too_many_archive_entries(self) -> None:
        with patch.object(downloader, "MAX_GAME_ARCHIVE_FILES", 2):
            self.run_worker_with_archive(self.archive_bytes("2"))

        status = self.manager.get_status()
        self.assertEqual(status["state"], DownloadState.ERROR.value)
        self.assertIn("слишком много файлов", str(status["error"]))

    def test_worker_verifies_manifest_sizes(self) -> None:
        archive_data = self.archive_bytes("2")
        with zipfile.ZipFile(io.BytesIO(archive_data), "r") as archive:
            unpacked_size = sum(member.file_size for member in archive.infolist())
        self.paths = replace(
            self.paths,
            archive_size_bytes=len(archive_data),
            unpacked_size_bytes=unpacked_size,
        )

        self.run_worker_with_archive(archive_data)

        self.assertEqual(self.manager.get_status()["state"], DownloadState.DONE.value)

    def test_worker_rejects_wrong_manifest_archive_size(self) -> None:
        archive_data = self.archive_bytes("2")
        self.paths = replace(self.paths, archive_size_bytes=len(archive_data) + 1)

        self.run_worker_with_archive(archive_data)

        status = self.manager.get_status()
        self.assertEqual(status["state"], DownloadState.ERROR.value)
        self.assertIn("Размер архива не совпадает", str(status["error"]))

    def test_worker_rejects_wrong_manifest_unpacked_size(self) -> None:
        archive_data = self.archive_bytes("2")
        self.paths = replace(self.paths, unpacked_size_bytes=1)

        self.run_worker_with_archive(archive_data)

        status = self.manager.get_status()
        self.assertEqual(status["state"], DownloadState.ERROR.value)
        self.assertIn("Распакованный размер", str(status["error"]))

    def test_worker_keeps_zip_slip_protection_during_streamed_extraction(self) -> None:
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("../escaped.txt", "escaped")
            archive.writestr(
                "ainocraft-build.json",
                json.dumps({"build_id": "tech", "revision": "2"}),
            )
            archive.writestr("versions/Tech/Tech.json", "{}")
            archive.writestr("versions/Tech/Tech.jar", b"jar")

        self.run_worker_with_archive(output.getvalue())

        status = self.manager.get_status()
        self.assertEqual(status["state"], DownloadState.ERROR.value)
        self.assertIn("Unsafe archive path", str(status["error"]))
        self.assertFalse((self.root / "escaped.txt").exists())

    def test_free_space_check_keeps_reserve(self) -> None:
        with (
            patch.object(downloader, "MIN_DISK_RESERVE_BYTES", 100),
            patch("core.downloader.shutil.disk_usage", return_value=SimpleNamespace(free=149)),
            self.assertRaisesRegex(OSError, "Недостаточно места"),
        ):
            self.manager._ensure_free_space(self.root, 50, "теста")


class DownloadUrlPolicyTests(unittest.TestCase):
    def test_scheme_policy(self) -> None:
        from config import is_download_url_allowed

        self.assertTrue(is_download_url_allowed("https://storage.example/x.zip"))
        self.assertTrue(is_download_url_allowed("http://127.0.0.1:9000/x.zip"))
        self.assertTrue(is_download_url_allowed("http://localhost:9000/x.zip"))
        self.assertFalse(is_download_url_allowed("http://evil.example/x.zip"))
        self.assertFalse(is_download_url_allowed("ftp://storage.example/x.zip"))

    def test_start_rejects_insecure_url(self) -> None:
        manager = downloader.DownloadManager()
        with tempfile.TemporaryDirectory() as temp:
            paths = replace(
                make_paths(Path(temp)),
                download_url="http://evil.example/AiNoCraftTech.zip",
            )
            with patch.object(downloader, "get_build_paths", return_value=paths):
                result = manager.start("tech")

        self.assertFalse(result["success"])
        self.assertIn("Небезопасный", result["error"])


if __name__ == "__main__":
    unittest.main()
