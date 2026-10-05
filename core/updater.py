"""Optional self-update support for direct .exe launches.

The production update path is the external bootstrapper, which consumes
``https://storage.ainocraft.com/launcher/stable/manifest.json`` before this
launcher starts. This module is therefore disabled by default and can be
enabled with ``AINOCRAFT_LAUNCHER_SELF_UPDATE=1`` for direct .exe installs.
"""

from __future__ import annotations

import base64
import hashlib
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote, urljoin

from config import (
    DOWNLOAD_CHUNK_SIZE,
    DOWNLOAD_PROGRESS_INTERVAL_SEC,
    DOWNLOAD_TIMEOUT_SEC,
    LAUNCHER_MANIFEST_URL,
    LAUNCHER_UPDATE_ENABLED,
    LAUNCHER_VERSION,
    USER_AGENT,
    is_download_url_allowed,
)
from core.enums import UpdateState
from core.stream_download import DownloadProgress, download_to_file
from core.win_env import sanitize_child_env


@dataclass(slots=True)
class UpdateStatus:
    state: UpdateState = UpdateState.IDLE
    active: bool = False
    percent: float = 0.0
    downloaded_mb: float = 0.0
    total_mb: float = 0.0
    speed_mb: float = 0.0
    remote_version: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["state"] = self.state.value
        return payload


_lock = threading.Lock()
_thread: threading.Thread | None = None
_shutdown_callback: Callable[[], None] | None = None
_state = UpdateStatus()


def register_shutdown(callback: Callable[[], None]) -> None:
    global _shutdown_callback
    _shutdown_callback = callback


def _update(**kwargs: Any) -> None:
    with _lock:
        for key, value in kwargs.items():
            setattr(_state, key, value)


def get_status() -> dict[str, Any]:
    with _lock:
        return _state.to_dict()


def _current_exe() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve()
    return Path(sys.argv[0]).resolve()


def _is_frozen_exe() -> bool:
    exe = _current_exe()
    return bool(getattr(sys, "frozen", False)) and exe.suffix.lower() == ".exe"


def _safe_unlink(path: Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except Exception:
        pass


def _update_tmp_path() -> Path:
    return Path(tempfile.gettempdir()) / "AiNoCraftLauncher_update.exe"


def startup_cleanup() -> None:
    exe = _current_exe()
    _safe_unlink(exe.with_suffix(".exe.old"))
    _safe_unlink(_update_tmp_path())


def _is_same_version(remote_version: str) -> bool:
    current = str(LAUNCHER_VERSION or "").strip()
    remote = str(remote_version or "").strip()
    return bool(current and remote and current == remote)


def _ensure_url_dir(url: str) -> str:
    return url if url.endswith("/") else url + "/"


def _manifest_file_url(manifest_url: str, manifest: dict[str, Any], entrypoint: str) -> str:
    quoted_entrypoint = quote(entrypoint.replace("\\", "/"), safe="/")
    base_url = str(manifest.get("base_url") or "").strip()
    if base_url:
        if base_url.startswith(("http://", "https://")):
            return urljoin(_ensure_url_dir(base_url), quoted_entrypoint)
        return urljoin(urljoin(manifest_url, "."), _ensure_url_dir(base_url) + quoted_entrypoint)
    return urljoin(manifest_url, quoted_entrypoint)


def _extract_entrypoint_file(manifest: dict[str, Any]) -> tuple[str, str, int]:
    entrypoint = str(manifest.get("entrypoint") or "").strip().replace("\\", "/")
    files = manifest.get("files")
    if not entrypoint or not isinstance(files, list):
        raise ValueError("launcher manifest must contain entrypoint and files")
    for item in files:
        if not isinstance(item, dict):
            continue
        if str(item.get("path") or "").replace("\\", "/") != entrypoint:
            continue
        sha256 = str(item.get("sha256") or "").strip().lower()
        size = int(item.get("size") or 0)
        if len(sha256) != 64 or not size:
            raise ValueError("launcher manifest entrypoint has invalid hash or size")
        return entrypoint, sha256, size
    raise ValueError(f"launcher manifest does not include entrypoint file: {entrypoint}")


def check_for_update() -> dict[str, Any]:
    if not LAUNCHER_UPDATE_ENABLED or not _is_frozen_exe():
        _update(state=UpdateState.DISABLED, active=False)
        return {"available": False, "remote_version": None, "download_url": None, "sha256": None, "error": None}

    _update(state=UpdateState.CHECKING, active=True, error=None)
    try:
        request = urllib.request.Request(LAUNCHER_MANIFEST_URL, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT_SEC) as response:
            manifest = json_loads_bytes(response.read())
        if not isinstance(manifest, dict) or int(manifest.get("schema", 0)) != 1:
            raise ValueError("unsupported launcher manifest")

        remote_version = str(manifest.get("version") or "").strip()
        entrypoint, sha256, _size = _extract_entrypoint_file(manifest)
        download_url = _manifest_file_url(LAUNCHER_MANIFEST_URL, manifest, entrypoint)

        if not remote_version:
            raise ValueError("launcher manifest version is empty")

        if _is_same_version(remote_version):
            _update(state=UpdateState.UP_TO_DATE, active=False, remote_version=remote_version)
            return {"available": False, "remote_version": remote_version, "download_url": None, "sha256": None, "error": None}

        _update(state=UpdateState.AVAILABLE, active=False, remote_version=remote_version)
        return {"available": True, "remote_version": remote_version, "download_url": download_url, "sha256": sha256, "error": None}
    except Exception as exc:
        _update(state=UpdateState.ERROR, active=False, error=str(exc))
        return {"available": False, "remote_version": None, "download_url": None, "sha256": None, "error": str(exc)}


def start_update() -> dict[str, Any]:
    """Download and apply the update described by the trusted HTTPS manifest.

    The URL and hash come only from ``check_for_update`` (a fixed manifest
    URL), never from the caller, so a compromised UI cannot point the updater
    at an arbitrary executable.
    """
    global _thread

    if not LAUNCHER_UPDATE_ENABLED or not _is_frozen_exe():
        return {"success": False, "error": "Самообновление лаунчера отключено; используйте bootstrapper"}

    info = check_for_update()
    if info.get("error"):
        return {"success": False, "error": str(info["error"])}
    if not info.get("available"):
        return {"success": False, "error": "Обновление недоступно"}

    url = str(info.get("download_url") or "").strip()
    expected_sha = str(info.get("sha256") or "").strip().lower()
    if not url or not is_download_url_allowed(url):
        return {"success": False, "error": "Небезопасный URL обновления"}
    if len(expected_sha) != 64 or any(ch not in "0123456789abcdef" for ch in expected_sha):
        return {"success": False, "error": "В манифесте нет корректного sha256 обновления"}

    with _lock:
        if _thread is not None and _thread.is_alive():
            return {"success": False, "error": "Обновление уже выполняется"}
        dest = _update_tmp_path()
        _safe_unlink(dest)
        _thread = threading.Thread(
            target=_download_and_apply,
            args=(url, dest, _current_exe(), expected_sha),
            daemon=True,
            name="launcher-updater",
        )
        _thread.start()
    return {"success": True}


def _download_and_apply(download_url: str, dest: Path, current_exe: Path, expected_sha256: str | None) -> None:
    try:
        _update(
            state=UpdateState.DOWNLOADING,
            active=True,
            percent=0.0,
            downloaded_mb=0.0,
            total_mb=0.0,
            speed_mb=0.0,
            error=None,
        )
        def report_progress(progress: DownloadProgress) -> None:
            _update(
                percent=round(progress.percent, 1),
                downloaded_mb=round(progress.downloaded_bytes / 1_048_576, 2),
                total_mb=round(progress.total_bytes / 1_048_576, 2),
                speed_mb=round(progress.speed_bytes_per_sec / 1_048_576, 2),
            )

        result = download_to_file(
            download_url,
            dest,
            user_agent=USER_AGENT,
            timeout=DOWNLOAD_TIMEOUT_SEC,
            chunk_size=DOWNLOAD_CHUNK_SIZE,
            progress_interval=DOWNLOAD_PROGRESS_INTERVAL_SEC,
            on_progress=report_progress,
        )

        _verify_downloaded_exe(dest, expected_sha256, actual_sha256=result.sha256)
        _update(
            percent=100.0,
            downloaded_mb=round(result.downloaded_bytes / 1_048_576, 2),
            speed_mb=0.0,
        )
        _apply_update(dest, current_exe)
    except Exception as exc:
        _safe_unlink(dest)
        _update(state=UpdateState.ERROR, active=False, error=str(exc))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1_048_576), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_loads_bytes(data: bytes) -> Any:
    import json

    return json.loads(data.decode("utf-8-sig"))


def _verify_downloaded_exe(path: Path, expected_sha256: str, *, actual_sha256: str | None = None) -> None:
    if not path.exists():
        raise FileNotFoundError("Файл обновления не найден")
    if path.stat().st_size < 128 * 1024:
        raise ValueError("Скачанный файл слишком маленький для .exe")
    if path.read_bytes()[:2] != b"MZ":
        raise ValueError("Скачанный файл не является Windows .exe")
    expected = str(expected_sha256 or "").strip().lower()
    if len(expected) != 64:
        raise ValueError("Отсутствует ожидаемый sha256 обновления")
    if (actual_sha256 or _sha256_file(path)).lower() != expected:
        raise ValueError("SHA-256 скачанного файла не совпадает с manifest")


def _ps_quote(value: str) -> str:
    return value.replace("'", "''")


def _build_swap_script(current_exe: Path, new_exe: Path, backup_exe: Path, pid_to_wait: int) -> str:
    cur = _ps_quote(str(current_exe))
    new = _ps_quote(str(new_exe))
    bak = _ps_quote(str(backup_exe))
    return f"""
$ErrorActionPreference = 'Stop'
$pidToWait = {pid_to_wait}
$current = '{cur}'
$newExe = '{new}'
$backup = '{bak}'

for ($i = 0; $i -lt 1800; $i++) {{
    if (-not (Get-Process -Id $pidToWait -ErrorAction SilentlyContinue)) {{ break }}
    Start-Sleep -Milliseconds 100
}}

for ($i = 0; $i -lt 240; $i++) {{
    try {{
        if (Test-Path -LiteralPath $backup) {{
            Remove-Item -LiteralPath $backup -Force -ErrorAction Stop
        }}
        if (Test-Path -LiteralPath $current) {{
            Move-Item -LiteralPath $current -Destination $backup -Force -ErrorAction Stop
        }}
        Move-Item -LiteralPath $newExe -Destination $current -Force -ErrorAction Stop
        Start-Process -FilePath $current -WorkingDirectory (Split-Path -Path $current -Parent)
        break
    }} catch {{
        Start-Sleep -Milliseconds 250
    }}
}}
"""


def _spawn_swapper(current_exe: Path, new_exe: Path) -> None:
    backup_exe = current_exe.with_suffix(".exe.old")
    encoded = base64.b64encode(_build_swap_script(current_exe, new_exe, backup_exe, os.getpid()).encode("utf-16le")).decode("ascii")
    windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
    ps_exe = windir / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    ps_cmd = str(ps_exe if ps_exe.exists() else Path("powershell.exe"))
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen(
        [
            ps_cmd,
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-WindowStyle",
            "Hidden",
            "-EncodedCommand",
            encoded,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        cwd=str(current_exe.parent),
        creationflags=flags,
        close_fds=True,
        env=sanitize_child_env(os.environ),
    )


def _apply_update(new_exe: Path, current_exe: Path) -> None:
    _update(state=UpdateState.APPLYING, active=True)
    _spawn_swapper(current_exe, new_exe)
    _update(state=UpdateState.DONE, active=False)
    time.sleep(0.5)
    if _shutdown_callback is not None:
        try:
            _shutdown_callback()
            return
        except Exception:
            pass
    os._exit(0)
