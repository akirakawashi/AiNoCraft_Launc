"""Build archive downloader and installer."""

from __future__ import annotations

import hmac
import json
import shutil
import threading
import zipfile
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from config import (
    BUILD_MARKER_FILENAME,
    DOWNLOAD_CHUNK_SIZE,
    DOWNLOAD_PROGRESS_INTERVAL_SEC,
    DOWNLOAD_TEMP_DIR,
    DOWNLOAD_TIMEOUT_SEC,
    MAX_GAME_ARCHIVE_BYTES,
    MAX_GAME_ARCHIVE_FILES,
    MAX_GAME_SINGLE_FILE_BYTES,
    MAX_GAME_UNPACKED_BYTES,
    MIN_DISK_RESERVE_BYTES,
    RUNTIME,
    USER_AGENT,
    BuildPaths,
    get_build_paths,
    is_download_url_allowed,
    resolve_client_files,
)
from core.enums import DownloadState
from core.stream_download import DownloadProgress, download_to_file


@dataclass(slots=True)
class DownloadStatus:
    active: bool = False
    state: DownloadState = DownloadState.IDLE
    percent: float = 0.0
    downloaded_mb: float = 0.0
    total_mb: float = 0.0
    speed_mb: float = 0.0
    build_id: str | None = None
    build_name: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["state"] = self.state.value
        return payload


class DownloadManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cancel_event = threading.Event()
        self._thread: threading.Thread | None = None
        # Temp artifacts of the in-flight download, so cleanup_on_exit can remove
        # a half-finished zip/staging tree. Ownership contract: these two fields
        # are only ever read or written while holding `_lock`. The worker owns
        # them for the duration of the download; cleanup_on_exit takes ownership
        # only after join()-ing the worker (join-first), so it never deletes a
        # staging tree the worker is still writing.
        self._active_zip_path: Path | None = None
        self._active_staging_path: Path | None = None
        self._status = DownloadStatus()

    @staticmethod
    def _read_build_marker(marker_file: Path, expected_build_id: str) -> tuple[str, str | None]:
        if not marker_file.exists():
            return "", "Файл ревизии отсутствует"
        try:
            payload = json.loads(marker_file.read_text(encoding="utf-8-sig"))
        except Exception:
            return "", "Файл ревизии поврежден"
        if not isinstance(payload, dict):
            return "", "Файл ревизии имеет неверный формат"

        build_id = str(payload.get("build_id", "")).strip().lower()
        revision = str(payload.get("revision", "")).strip()
        if build_id != expected_build_id:
            return "", "Файл ревизии относится к другой сборке"
        if not revision:
            return "", "В файле ревизии не указана revision"
        return revision, None

    def get_build_state(self, build_id: str) -> dict[str, Any]:
        try:
            paths = get_build_paths(build_id)
        except ValueError:
            return {
                "installed": False,
                "damaged": False,
                "update_available": False,
                "update_known": False,
                "up_to_date": False,
                "install_state": "not_installed",
                "local_revision": "",
                "remote_revision": "",
            }

        version_json, client_jar, _effective_name = resolve_client_files(paths)
        core_ready = version_json.exists() and client_jar.exists()
        local_revision, marker_error = self._read_build_marker(paths.marker_file, paths.build_id)
        installed = core_ready and marker_error is None
        update_known = bool(paths.revision)
        update_available = installed and update_known and local_revision != paths.revision
        up_to_date = installed and update_known and local_revision == paths.revision
        damaged = paths.game_dir.exists() and not installed

        if damaged:
            install_state = "damaged"
        elif not installed:
            install_state = "not_installed"
        elif update_available:
            install_state = "update_available"
        elif up_to_date:
            install_state = "current"
        else:
            install_state = "offline"

        return {
            "installed": installed,
            "damaged": damaged,
            "update_available": update_available,
            "update_known": update_known,
            "up_to_date": up_to_date,
            "install_state": install_state,
            "local_revision": local_revision,
            "remote_revision": paths.revision,
            "marker_error": marker_error,
        }

    def is_game_installed(self, build_id: str) -> bool:
        return bool(self.get_build_state(build_id)["installed"])

    def get_status(self) -> dict[str, Any]:
        with self._lock:
            return self._status.to_dict()

    def start(self, build_id: str, url: str | None = None) -> dict[str, Any]:
        try:
            paths = get_build_paths(build_id)
        except ValueError as exc:
            return {"success": False, "error": str(exc)}

        resolved_url = (url or paths.download_url).strip()
        if not resolved_url:
            return {"success": False, "error": f"Не задана ссылка загрузки для {paths.build_name}"}
        if not is_download_url_allowed(resolved_url):
            return {"success": False, "error": f"Небезопасный URL загрузки (нужен https): {resolved_url}"}

        with self._lock:
            if self._status.active:
                return {"success": False, "error": "Загрузка уже идет"}
            self._cancel_event.clear()
            zip_path = self._zip_path_for(paths)
            self._active_zip_path = zip_path
            self._active_staging_path = None
            self._status = DownloadStatus(
                active=True,
                state=DownloadState.DOWNLOADING,
                build_id=paths.build_id,
                build_name=paths.build_name,
            )

        self._thread = threading.Thread(
            target=self._worker,
            args=(paths, resolved_url, zip_path),
            daemon=True,
            name=f"download-{paths.build_id}",
        )
        self._thread.start()
        return {"success": True}

    def cancel(self) -> dict[str, Any]:
        with self._lock:
            if not self._status.active:
                return {"success": False, "error": "Нет активной загрузки"}
        self._cancel_event.set()
        return {"success": True}

    def delete_build(self, build_id: str) -> dict[str, Any]:
        """Delete all installed files of one build, including its settings."""
        try:
            paths = get_build_paths(build_id)
        except ValueError as exc:
            return {"success": False, "error": str(exc)}

        with self._lock:
            if self._status.active:
                return {"success": False, "error": "Дождитесь завершения загрузки"}

        candidates = (paths.game_dir, self._staging_path_for(paths), self._backup_path_for(paths))
        if not any(path.exists() for path in candidates):
            return {"success": True, "deleted": False}

        try:
            for path in candidates:
                self._cleanup_tree(path)
        except Exception as exc:
            return {"success": False, "error": f"Не удалось удалить файлы: {exc}"}

        self._cleanup_zip(self._zip_path_for(paths))
        return {"success": True, "deleted": True}

    def cleanup_on_exit(self, timeout: float = 30.0) -> None:
        self._cancel_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                # The daemon will stop with the process. Do not race it by
                # removing a file or staging directory that it may still use.
                return

        # Worker has finished (join-first above), so take ownership of the temp
        # artifacts under the lock and act on the snapshot outside it.
        with self._lock:
            zip_path = self._active_zip_path
            staging_path = self._active_staging_path
            self._active_zip_path = None
            self._active_staging_path = None

        if zip_path is not None:
            self._cleanup_zip(zip_path)
        if staging_path is not None:
            try:
                self._cleanup_tree(staging_path)
            except Exception:
                pass

        with self._lock:
            self._status = DownloadStatus()

    def _update(self, **kwargs: Any) -> None:
        with self._lock:
            for key, value in kwargs.items():
                setattr(self._status, key, value)

    @staticmethod
    def _zip_path_for(paths: BuildPaths) -> Path:
        return DOWNLOAD_TEMP_DIR / f"_download_{paths.build_id}.zip"

    @staticmethod
    def _staging_path_for(paths: BuildPaths) -> Path:
        return paths.game_dir.with_name(f".{paths.game_dir.name}.ainocraft-new")

    @staticmethod
    def _backup_path_for(paths: BuildPaths) -> Path:
        return paths.game_dir.with_name(f".{paths.game_dir.name}.ainocraft-old")

    @staticmethod
    def _cleanup_zip(path: Path) -> None:
        try:
            if path.exists():
                path.unlink()
        except Exception:
            pass

    @staticmethod
    def _cleanup_tree(path: Path) -> None:
        if not path.exists():
            return
        shutil.rmtree(path)

    @staticmethod
    def _rebase_paths(paths: BuildPaths, game_dir: Path) -> BuildPaths:
        version_dir = game_dir / "versions" / paths.version_name
        return replace(
            paths,
            game_dir=game_dir,
            marker_file=game_dir / BUILD_MARKER_FILENAME,
            java_bin=game_dir / "java" / "bin" / "javaw.exe",
            version_dir=version_dir,
            version_json=version_dir / f"{paths.version_name}.json",
            client_jar=version_dir / f"{paths.version_name}.jar",
            assets_dir=game_dir / "assets",
            libraries_dir=game_dir / "libraries",
            natives_dir=version_dir / "natives",
            settings_file=version_dir / "launcher_settings.json",
        )

    def _validate_staging(self, paths: BuildPaths, staging_dir: Path) -> BuildPaths:
        staged_paths = self._rebase_paths(paths, staging_dir)
        local_revision, marker_error = self._read_build_marker(staged_paths.marker_file, paths.build_id)
        if marker_error:
            raise ValueError(f"{BUILD_MARKER_FILENAME}: {marker_error}")
        if paths.revision and local_revision != paths.revision:
            raise ValueError(
                f"Ревизия архива {local_revision} не совпадает с ожидаемой {paths.revision}"
            )

        version_json, client_jar, _effective_name = resolve_client_files(staged_paths)
        if not version_json.exists() or not client_jar.exists():
            raise ValueError("В архиве не найдены JSON и JAR клиентской версии")
        return staged_paths

    def _activate_staging(self, paths: BuildPaths, staging_dir: Path) -> None:
        backup_dir = self._backup_path_for(paths)

        # Recover or remove leftovers from a launcher interruption before a new swap.
        if backup_dir.exists():
            if paths.game_dir.exists():
                self._cleanup_tree(backup_dir)
            else:
                backup_dir.replace(paths.game_dir)

        moved_old = False
        if paths.game_dir.exists():
            paths.game_dir.replace(backup_dir)
            moved_old = True

        try:
            staging_dir.replace(paths.game_dir)
        except Exception as exc:
            rollback_error: Exception | None = None
            if moved_old and backup_dir.exists() and not paths.game_dir.exists():
                try:
                    backup_dir.replace(paths.game_dir)
                except Exception as restore_exc:
                    rollback_error = restore_exc
            if rollback_error is not None:
                raise RuntimeError(f"Не удалось установить сборку и восстановить старую: {rollback_error}") from exc
            raise

        if backup_dir.exists():
            try:
                self._cleanup_tree(backup_dir)
            except Exception:
                # The new build is already active. A leftover backup is safer
                # than reporting a failed update and touching the new files.
                pass

    @staticmethod
    def _safe_member_path(member: zipfile.ZipInfo, target_dir: Path) -> Path:
        target_root = target_dir.resolve()
        target_path = (target_root / member.filename).resolve()
        if target_path != target_root and target_root not in target_path.parents:
            raise ValueError(f"Unsafe archive path: {member.filename}")
        if target_path == target_root and not member.is_dir():
            raise ValueError(f"Unsafe archive path: {member.filename}")
        return target_path

    @staticmethod
    def _required_free_bytes(payload_bytes: int) -> int:
        return payload_bytes + max(MIN_DISK_RESERVE_BYTES, payload_bytes // 10)

    @classmethod
    def _ensure_free_space(cls, directory: Path, payload_bytes: int, operation: str) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        required = cls._required_free_bytes(payload_bytes)
        free = shutil.disk_usage(directory).free
        if free < required:
            raise OSError(
                f"Недостаточно места на диске для {operation}: "
                f"нужно {required / 1024**3:.1f} ГиБ, свободно {free / 1024**3:.1f} ГиБ"
            )

    @staticmethod
    def _download_limit(paths: BuildPaths) -> int:
        expected = paths.archive_size_bytes
        if expected > MAX_GAME_ARCHIVE_BYTES:
            raise ValueError(
                "Размер архива из builds.json превышает допустимый лимит "
                f"({MAX_GAME_ARCHIVE_BYTES / 1024**3:.0f} ГиБ)"
            )
        return expected or MAX_GAME_ARCHIVE_BYTES

    @staticmethod
    def _verify_archive_size(paths: BuildPaths, actual_size: int) -> None:
        expected = paths.archive_size_bytes
        if expected and actual_size != expected:
            raise ValueError(
                f"Размер архива не совпадает с builds.json: ожидалось {expected} байт, "
                f"получено {actual_size} байт"
            )

    @staticmethod
    def _inspect_archive(
        archive: zipfile.ZipFile,
        paths: BuildPaths,
    ) -> tuple[list[zipfile.ZipInfo], int]:
        members = archive.infolist()
        if len(members) > MAX_GAME_ARCHIVE_FILES:
            raise ValueError(
                f"В архиве слишком много файлов: {len(members)} "
                f"(лимит {MAX_GAME_ARCHIVE_FILES})"
            )

        total_unpacked = 0
        for member in members:
            if member.flag_bits & 0x1:
                raise ValueError(f"Зашифрованные ZIP-файлы не поддерживаются: {member.filename}")
            if member.file_size > MAX_GAME_SINGLE_FILE_BYTES:
                raise ValueError(
                    f"Файл {member.filename} после распаковки превышает допустимый лимит"
                )
            total_unpacked += member.file_size
            if total_unpacked > MAX_GAME_UNPACKED_BYTES:
                raise ValueError(
                    "Суммарный размер распакованных файлов превышает допустимый лимит "
                    f"({MAX_GAME_UNPACKED_BYTES / 1024**3:.0f} ГиБ)"
                )

        expected = paths.unpacked_size_bytes
        if expected > MAX_GAME_UNPACKED_BYTES:
            raise ValueError(
                "Распакованный размер из builds.json превышает допустимый лимит "
                f"({MAX_GAME_UNPACKED_BYTES / 1024**3:.0f} ГиБ)"
            )
        if expected and total_unpacked != expected:
            raise ValueError(
                f"Распакованный размер архива не совпадает с builds.json: "
                f"ожидалось {expected} байт, получено {total_unpacked} байт"
            )
        return members, total_unpacked

    def _extract_archive(
        self,
        archive: zipfile.ZipFile,
        members: list[zipfile.ZipInfo],
        target_dir: Path,
        expected_total: int,
    ) -> None:
        total_written = 0
        total_files = max(len(members), 1)

        for index, member in enumerate(members, start=1):
            if self._cancel_event.is_set():
                return

            target_path = self._safe_member_path(member, target_dir)
            if member.is_dir():
                target_path.mkdir(parents=True, exist_ok=True)
            else:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                member_written = 0
                with archive.open(member, "r") as source, target_path.open("wb") as destination:
                    while True:
                        if self._cancel_event.is_set():
                            return
                        chunk = source.read(DOWNLOAD_CHUNK_SIZE)
                        if not chunk:
                            break
                        member_written += len(chunk)
                        total_written += len(chunk)
                        if member_written > MAX_GAME_SINGLE_FILE_BYTES:
                            raise ValueError(
                                f"Файл {member.filename} при распаковке превысил допустимый лимит"
                            )
                        if total_written > MAX_GAME_UNPACKED_BYTES or total_written > expected_total:
                            raise ValueError("Архив при распаковке превысил допустимый размер")
                        destination.write(chunk)

                if member_written != member.file_size:
                    raise ValueError(
                        f"Размер файла {member.filename} не совпадает с метаданными ZIP"
                    )

            self._update(percent=round(index / total_files * 100, 1))

        if total_written != expected_total:
            raise ValueError("Фактический распакованный размер не совпадает с метаданными ZIP")

    @staticmethod
    def _verify_archive_hash(paths: BuildPaths, actual_sha256: str) -> None:
        """Fail closed on a mismatched (or, in prod, missing) archive digest."""
        expected = (paths.archive_sha256 or "").strip().lower()
        if expected:
            if not hmac.compare_digest(actual_sha256, expected):
                raise ValueError(f"SHA-256 архива не совпадает с ожидаемым для {paths.build_name}")
            return
        if not RUNTIME.is_dev:
            raise ValueError(
                f"Для сборки {paths.build_name} не задан sha256 в builds.json — установка запрещена"
            )

    def _worker(self, paths: BuildPaths, url: str, zip_path: Path) -> None:
        staging_dir = self._staging_path_for(paths)
        try:
            download_limit = self._download_limit(paths)
            self._cleanup_zip(zip_path)
            zip_path.parent.mkdir(parents=True, exist_ok=True)
            if paths.archive_size_bytes:
                self._ensure_free_space(zip_path.parent, paths.archive_size_bytes, "загрузки архива")

            def report_progress(progress: DownloadProgress) -> None:
                self._update(
                    percent=round(progress.percent, 1),
                    downloaded_mb=round(progress.downloaded_bytes / 1_048_576, 1),
                    total_mb=round(progress.total_bytes / 1_048_576, 1),
                    speed_mb=round(progress.speed_bytes_per_sec / 1_048_576, 2),
                )

            result = download_to_file(
                url,
                zip_path,
                user_agent=USER_AGENT,
                timeout=DOWNLOAD_TIMEOUT_SEC,
                chunk_size=DOWNLOAD_CHUNK_SIZE,
                progress_interval=DOWNLOAD_PROGRESS_INTERVAL_SEC,
                on_progress=report_progress,
                cancel_event=self._cancel_event,
                max_bytes=download_limit,
            )

            if result.cancelled:
                self._cleanup_zip(zip_path)
                self._update(active=False, state=DownloadState.CANCELLED, percent=0.0)
                return

            self._verify_archive_size(paths, result.downloaded_bytes)
            self._verify_archive_hash(paths, result.sha256)

            self._update(
                percent=100.0,
                downloaded_mb=round(result.downloaded_bytes / 1_048_576, 1),
                speed_mb=0.0,
            )
            self._update(state=DownloadState.EXTRACTING, percent=0.0)

            with zipfile.ZipFile(zip_path, "r") as archive:
                members, total_unpacked = self._inspect_archive(archive, paths)
                self._ensure_free_space(staging_dir.parent, total_unpacked, "распаковки сборки")
                self._cleanup_tree(staging_dir)
                staging_dir.mkdir(parents=True, exist_ok=True)
                with self._lock:
                    self._active_staging_path = staging_dir
                self._extract_archive(archive, members, staging_dir, total_unpacked)

            self._cleanup_zip(zip_path)
            if self._cancel_event.is_set():
                self._cleanup_tree(staging_dir)
                self._update(active=False, state=DownloadState.CANCELLED, percent=0.0)
                return

            staged_paths = self._validate_staging(paths, staging_dir)
            if paths.settings_file.exists():
                try:
                    settings_backup = paths.settings_file.read_bytes()
                    staged_paths.settings_file.parent.mkdir(parents=True, exist_ok=True)
                    staged_paths.settings_file.write_bytes(settings_backup)
                except Exception as exc:
                    raise RuntimeError(f"Не удалось сохранить настройки сборки: {exc}") from exc

            self._activate_staging(paths, staging_dir)

            self._update(active=False, state=DownloadState.DONE, percent=100.0)
        except Exception as exc:
            self._cleanup_zip(zip_path)
            try:
                self._cleanup_tree(staging_dir)
            except Exception:
                pass
            self._update(active=False, state=DownloadState.ERROR, error=str(exc))
        finally:
            with self._lock:
                self._active_zip_path = None
                self._active_staging_path = None


_manager = DownloadManager()


def is_game_installed(build_id: str) -> bool:
    return _manager.is_game_installed(build_id)


def get_build_state(build_id: str) -> dict[str, Any]:
    return _manager.get_build_state(build_id)


def get_status() -> dict[str, Any]:
    return _manager.get_status()


def start(build_id: str, url: str | None = None) -> dict[str, Any]:
    return _manager.start(build_id, url)


def cancel() -> dict[str, Any]:
    return _manager.cancel()


def delete_build(build_id: str) -> dict[str, Any]:
    return _manager.delete_build(build_id)


def cleanup_on_exit(timeout: float = 30.0) -> None:
    _manager.cleanup_on_exit(timeout)
