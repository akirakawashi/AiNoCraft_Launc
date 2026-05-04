"""
Game files downloader.

Downloads the selected build ZIP archive and extracts it into the build folder.
Supports cancellation and progress reporting for UI polling.
"""

from __future__ import annotations

import shutil
import threading
import time
import zipfile
from pathlib import Path
from typing import Any

import requests

from config import (
    DOWNLOAD_CHUNK_SIZE,
    DOWNLOAD_PROGRESS_INTERVAL_SEC,
    DOWNLOAD_TEMP_DIR,
    DOWNLOAD_TIMEOUT_SEC,
    BuildPaths,
    get_build_paths,
    resolve_client_files,
)

STATE_IDLE = "idle"
STATE_DOWNLOADING = "downloading"
STATE_EXTRACTING = "extracting"
STATE_DONE = "done"
STATE_ERROR = "error"
STATE_CANCELLED = "cancelled"

_lock = threading.Lock()
_cancel_event = threading.Event()
_thread: threading.Thread | None = None
_active_zip_path: Path | None = None


def _initial_state() -> dict[str, Any]:
    return {
        "active": False,
        "state": STATE_IDLE,
        "percent": 0.0,
        "downloaded_mb": 0.0,
        "total_mb": 0.0,
        "speed_mb": 0.0,
        "build_id": None,
        "build_name": None,
        "error": None,
    }


_state: dict[str, Any] = _initial_state()


def _update(**kwargs: Any) -> None:
    with _lock:
        _state.update(kwargs)


def _zip_path_for(paths: BuildPaths) -> Path:
    return DOWNLOAD_TEMP_DIR / f"_download_{paths.build_id}.zip"


def is_game_installed(build_id: str) -> bool:
    """True if key files of selected build exist."""
    try:
        paths = get_build_paths(build_id)
    except ValueError:
        return False
    version_json, client_jar, _ = resolve_client_files(paths)
    return version_json.exists() and client_jar.exists()


def get_status() -> dict[str, Any]:
    """Returns a copy of current download status."""
    with _lock:
        return dict(_state)


def start(build_id: str, url: str | None = None) -> dict[str, Any]:
    """
    Starts download + installation in background thread.
    Returns {"success": True} or {"success": False, "error": "..."}.
    """
    global _thread, _active_zip_path

    try:
        paths = get_build_paths(build_id)
    except ValueError as exc:
        return {"success": False, "error": str(exc)}

    resolved_url = (url or paths.download_url).strip()
    if not resolved_url:
        return {"success": False, "error": f"Не задана ссылка загрузки для {paths.build_name}"}

    with _lock:
        if _state["active"]:
            return {"success": False, "error": "Загрузка уже идёт"}
        _cancel_event.clear()

    _active_zip_path = _zip_path_for(paths)
    _update(
        active=True,
        state=STATE_DOWNLOADING,
        percent=0.0,
        downloaded_mb=0.0,
        total_mb=0.0,
        speed_mb=0.0,
        build_id=paths.build_id,
        build_name=paths.build_name,
        error=None,
    )
    _thread = threading.Thread(target=_worker, args=(paths, resolved_url, _active_zip_path), daemon=True)
    _thread.start()
    return {"success": True}


def cancel() -> dict[str, Any]:
    """Requests cancellation for the active operation."""
    with _lock:
        if not _state["active"]:
            return {"success": False, "error": "Нет активной загрузки"}
    _cancel_event.set()
    return {"success": True}


def cleanup_on_exit(timeout: float = 30.0) -> None:
    """Stops active worker and removes unfinished download artifacts."""
    global _active_zip_path

    _cancel_event.set()
    if _thread is not None and _thread.is_alive():
        _thread.join(timeout=timeout)

    build_id: str | None = None
    state: str = STATE_IDLE
    with _lock:
        build_id = _state.get("build_id")
        state = str(_state.get("state") or STATE_IDLE)

    # If launcher closed during extraction, ensure partial files are removed.
    if build_id and state == STATE_EXTRACTING:
        try:
            _cleanup_game(get_build_paths(build_id))
        except Exception:
            pass

    if _active_zip_path is not None:
        _cleanup_zip(_active_zip_path)
        _active_zip_path = None

    with _lock:
        _state.clear()
        _state.update(_initial_state())


def _cleanup_zip(path: Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except Exception:
        pass


def _cleanup_game(paths: BuildPaths) -> None:
    """
    Clears build folder while preserving launcher settings.
    """
    if not paths.game_dir.exists():
        return

    settings_backup: bytes | None = None
    if paths.settings_file.exists():
        try:
            settings_backup = paths.settings_file.read_bytes()
        except Exception:
            settings_backup = None

    for item in paths.game_dir.iterdir():
        try:
            shutil.rmtree(item) if item.is_dir() else item.unlink()
        except Exception:
            pass

    if settings_backup is not None:
        try:
            paths.settings_file.parent.mkdir(parents=True, exist_ok=True)
            paths.settings_file.write_bytes(settings_backup)
        except Exception:
            pass


def _worker(paths: BuildPaths, url: str, zip_path: Path) -> None:
    global _active_zip_path

    try:
        zip_path.parent.mkdir(parents=True, exist_ok=True)

        with requests.get(url, stream=True, timeout=DOWNLOAD_TIMEOUT_SEC) as resp:
            resp.raise_for_status()

            try:
                total_bytes = int(resp.headers.get("content-length", 0))
            except (TypeError, ValueError):
                total_bytes = 0

            _update(total_mb=round(total_bytes / 1_048_576, 1))

            downloaded = 0
            last_bytes = 0
            last_time = time.monotonic()

            with open(zip_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
                    if _cancel_event.is_set():
                        break
                    if not chunk:
                        continue
                    f.write(chunk)
                    downloaded += len(chunk)

                    now = time.monotonic()
                    dt = now - last_time
                    if dt >= DOWNLOAD_PROGRESS_INTERVAL_SEC:
                        speed_mb = (downloaded - last_bytes) / dt / 1_048_576
                        last_time = now
                        last_bytes = downloaded
                        percent = downloaded / total_bytes * 100 if total_bytes else 0
                        _update(
                            percent=round(percent, 1),
                            downloaded_mb=round(downloaded / 1_048_576, 1),
                            speed_mb=round(speed_mb, 2),
                        )

        if _cancel_event.is_set():
            _cleanup_zip(zip_path)
            _update(active=False, state=STATE_CANCELLED, percent=0.0)
            return

        _update(
            percent=100.0,
            downloaded_mb=round(downloaded / 1_048_576, 1),
            speed_mb=0.0,
        )

        _update(state=STATE_EXTRACTING, percent=0.0)
        _cleanup_game(paths)
        paths.game_dir.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(zip_path, "r") as zf:
            members = zf.infolist()
            total_files = max(len(members), 1)
            for index, member in enumerate(members, start=1):
                if _cancel_event.is_set():
                    break
                zf.extract(member, paths.game_dir)
                _update(percent=round(index / total_files * 100, 1))

        _cleanup_zip(zip_path)

        if _cancel_event.is_set():
            _cleanup_game(paths)
            _update(active=False, state=STATE_CANCELLED, percent=0.0)
            return

        _update(active=False, state=STATE_DONE, percent=100.0)

    except Exception as exc:
        _cleanup_zip(zip_path)
        _update(active=False, state=STATE_ERROR, error=str(exc))
    finally:
        _active_zip_path = None
