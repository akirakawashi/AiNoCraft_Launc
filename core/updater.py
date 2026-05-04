"""
Self-update module for the Windows launcher executable.

Update flow:
  1. check_for_update() reads remote version.json and compares versions.
  2. start_update() downloads a new executable in background.
  3. A detached PowerShell helper waits for current PID to exit,
     replaces the executable, starts new version, and exits.

No .bat/.vbs files are created.
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
from collections.abc import Callable
from pathlib import Path
from typing import Any

import requests

from config import DOWNLOAD_CHUNK_SIZE, DOWNLOAD_TIMEOUT_SEC, LAUNCHER_UPDATE_URL, LAUNCHER_VERSION

#  State machine

STATE_IDLE = "idle"
STATE_CHECKING = "checking"
STATE_AVAILABLE = "available"
STATE_UP_TO_DATE = "up_to_date"
STATE_DOWNLOADING = "downloading"
STATE_APPLYING = "applying"
STATE_DONE = "done"
STATE_ERROR = "error"
STATE_DISABLED = "disabled"

_lock = threading.Lock()
_thread: threading.Thread | None = None
_shutdown_callback: "Callable[[], None] | None" = None


def register_shutdown(cb: "Callable[[], None]") -> None:
    """Register window shutdown callback (e.g. window.destroy)."""
    global _shutdown_callback
    _shutdown_callback = cb


def _initial_state() -> dict[str, Any]:
    return {
        "state": STATE_IDLE,
        "active": False,
        "percent": 0.0,
        "downloaded_mb": 0.0,
        "total_mb": 0.0,
        "speed_mb": 0.0,
        "remote_version": None,
        "error": None,
    }


_state: dict[str, Any] = _initial_state()


def _update(**kwargs: Any) -> None:
    with _lock:
        _state.update(kwargs)


def get_status() -> dict[str, Any]:
    with _lock:
        return dict(_state)


#  Version helpers

def _parse_version(v: str) -> tuple[int, ...]:
    parts = []
    for p in v.strip().split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def _is_newer(remote: str, current: str) -> bool:
    return _parse_version(remote) > _parse_version(current)


#  Current executable helpers

def _current_exe() -> Path:
    """Path to the running entrypoint."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve()
    return Path(sys.argv[0]).resolve()


def _is_frozen_exe() -> bool:
    """True only for packaged Windows .exe builds."""
    exe = _current_exe()
    return bool(getattr(sys, "frozen", False)) and exe.suffix.lower() == ".exe"


def _safe_unlink(path: Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except Exception:
        pass


def _update_tmp_path() -> Path:
    """Temporary path used to download the update (in system %TEMP%, not next to launcher)."""
    return Path(tempfile.gettempdir()) / "AiNoCraftLauncher_update.exe"


def startup_cleanup() -> None:
    """
    Remove leftovers from previous updates.
    Call once at startup before UI.
    """
    exe = _current_exe()
    _safe_unlink(exe.with_suffix(".exe.old"))
    # Legacy path (next to exe) — clean up just in case.
    _safe_unlink(exe.parent / "_ainocraft_update_new.exe")
    # Current temp path.
    _safe_unlink(_update_tmp_path())


def check_for_update() -> dict[str, Any]:
    """
    Synchronous check against LAUNCHER_UPDATE_URL.

    Returns:
      {"available": bool, "remote_version": str|None, "download_url": str|None,
       "sha256": str|None, "error": str|None}
    """
    if not LAUNCHER_UPDATE_URL:
        _update(state=STATE_DISABLED, active=False)
        return {"available": False, "remote_version": None, "download_url": None, "sha256": None, "error": None}

    if not _is_frozen_exe():
        # Guard against source-run update attempts that can corrupt launcher.py.
        _update(state=STATE_DISABLED, active=False)
        return {"available": False, "remote_version": None, "download_url": None, "sha256": None, "error": None}

    _update(state=STATE_CHECKING, active=True, error=None)
    try:
        resp = requests.get(LAUNCHER_UPDATE_URL, timeout=DOWNLOAD_TIMEOUT_SEC)
        resp.raise_for_status()
        data = resp.json()

        remote_ver = str(data.get("version", "")).strip()
        download_url = str(data.get("download_url", "")).strip()
        sha256 = str(data.get("sha256", "")).strip().lower() or None

        if not remote_ver or not download_url:
            raise ValueError("version.json must contain 'version' and 'download_url'")
        if sha256 and (len(sha256) != 64 or any(ch not in "0123456789abcdef" for ch in sha256)):
            raise ValueError("version.json has invalid 'sha256' value")

        if _is_newer(remote_ver, LAUNCHER_VERSION):
            _update(state=STATE_AVAILABLE, active=False, remote_version=remote_ver)
            return {
                "available": True,
                "remote_version": remote_ver,
                "download_url": download_url,
                "sha256": sha256,
                "error": None,
            }

        _update(state=STATE_UP_TO_DATE, active=False, remote_version=remote_ver)
        return {
            "available": False,
            "remote_version": remote_ver,
            "download_url": None,
            "sha256": None,
            "error": None,
        }

    except Exception as exc:
        msg = str(exc)
        _update(state=STATE_ERROR, active=False, error=msg)
        return {"available": False, "remote_version": None, "download_url": None, "sha256": None, "error": msg}


def start_update(download_url: str, sha256: str | None = None) -> dict[str, Any]:
    """
    Start background download + apply.

    download_url: direct link to the new .exe
    sha256: optional expected SHA-256 checksum
    """
    global _thread

    if not _is_frozen_exe():
        return {"success": False, "error": "Самообновление доступно только в собранной .exe версии лаунчера"}

    url = (download_url or "").strip()
    if not url:
        return {"success": False, "error": "Пустой URL обновления"}

    expected_sha = (sha256 or "").strip().lower() or None
    if expected_sha and (len(expected_sha) != 64 or any(ch not in "0123456789abcdef" for ch in expected_sha)):
        return {"success": False, "error": "Некорректный SHA-256 для обновления"}

    with _lock:
        if _thread is not None and _thread.is_alive():
            return {"success": False, "error": "Обновление уже выполняется"}

    current_exe = _current_exe()
    dest = _update_tmp_path()
    _safe_unlink(dest)

    _thread = threading.Thread(
        target=_download_and_apply,
        args=(url, dest, current_exe, expected_sha),
        daemon=True,
        name="launcher-updater",
    )
    _thread.start()
    return {"success": True}


#  Internal

def _download_and_apply(download_url: str, dest: Path, current_exe: Path, expected_sha256: str | None) -> None:
    try:
        _update(
            state=STATE_DOWNLOADING,
            active=True,
            percent=0.0,
            downloaded_mb=0.0,
            total_mb=0.0,
            speed_mb=0.0,
            error=None,
        )

        with requests.get(download_url, stream=True, timeout=DOWNLOAD_TIMEOUT_SEC) as resp:
            resp.raise_for_status()

            total = int(resp.headers.get("content-length", 0))
            total_mb = total / 1_048_576 if total > 0 else 0.0
            downloaded = 0
            last_time = time.monotonic()
            last_bytes = 0

            with open(dest, "wb") as f:
                for chunk in resp.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
                    if not chunk:
                        continue
                    f.write(chunk)
                    downloaded += len(chunk)

                    now = time.monotonic()
                    dt = now - last_time
                    if dt >= 0.4:
                        speed_mb = (downloaded - last_bytes) / 1_048_576 / dt
                        pct = (downloaded / total * 100) if total > 0 else 0.0
                        _update(
                            percent=round(pct, 1),
                            downloaded_mb=round(downloaded / 1_048_576, 2),
                            total_mb=round(total_mb, 2),
                            speed_mb=round(speed_mb, 2),
                        )
                        last_time = now
                        last_bytes = downloaded

        _verify_downloaded_exe(dest, expected_sha256)
        _update(percent=100.0, downloaded_mb=round(dest.stat().st_size / 1_048_576, 2))
        _apply_update(dest, current_exe)

    except Exception as exc:
        _safe_unlink(dest)
        _update(state=STATE_ERROR, active=False, error=str(exc))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1_048_576), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_downloaded_exe(path: Path, expected_sha256: str | None) -> None:
    if not path.exists():
        raise FileNotFoundError("Файл обновления не найден")

    size = path.stat().st_size
    if size < 128 * 1024:
        raise ValueError("Скачанный файл слишком маленький для .exe, возможно получена ошибка/HTML вместо бинарника")

    with open(path, "rb") as f:
        mz = f.read(2)
    if mz != b"MZ":
        raise ValueError("Скачанный файл не является валидным Windows .exe")

    if expected_sha256:
        actual = _sha256_file(path)
        if actual.lower() != expected_sha256.lower():
            raise ValueError("SHA-256 скачанного файла не совпадает с version.json")


def _ps_quote(value: str) -> str:
    """Escape string for single-quoted PowerShell literal."""
    return value.replace("'", "''")


def _sanitize_launch_env(env: dict[str, str]) -> tuple[dict[str, str], list[str], int]:
    """
    Remove env vars that can leak onefile/pyinstaller runtime context
    into the relaunched executable and break startup.
    """
    clean = dict(env)
    removed: list[str] = []
    removed_path_entries = 0

    prefixes = ("PYTHONNET", "_PYI", "PYI_", "PYINSTALLER", "_MEI")
    exact = {"PYTHONHOME", "PYTHONPATH"}

    for key in list(clean.keys()):
        upper = key.upper()
        if upper in exact or any(upper.startswith(pref) for pref in prefixes):
            removed.append(key)
            clean.pop(key, None)

    path_key = next((k for k in clean.keys() if k.upper() == "PATH"), None)
    if path_key:
        kept: list[str] = []
        for part in clean[path_key].split(os.pathsep):
            if not part:
                continue
            if "_MEI" in part.upper():
                removed_path_entries += 1
                continue
            kept.append(part)
        clean[path_key] = os.pathsep.join(kept)

    return clean, removed, removed_path_entries


def _build_swap_script(current_exe: Path, new_exe: Path, backup_exe: Path, pid_to_wait: int) -> str:
    cur = _ps_quote(str(current_exe))
    new = _ps_quote(str(new_exe))
    bak = _ps_quote(str(backup_exe))
    return f"""
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$pidToWait = {pid_to_wait}
$current = '{cur}'
$newExe = '{new}'
$backup = '{bak}'

if (-not (Test-Path -LiteralPath $newExe)) {{
    exit 1
}}
$expectedLen = (Get-Item -LiteralPath $newExe).Length

for ($i = 0; $i -lt 1800; $i++) {{
    if (-not (Get-Process -Id $pidToWait -ErrorAction SilentlyContinue)) {{ break }}
    Start-Sleep -Milliseconds 100
}}

# Ensure relaunched launcher starts with clean env, similar to manual double-click.
Get-ChildItem Env: | Where-Object {{
    $_.Name -like 'PYTHONNET*' -or
    $_.Name -eq 'PYTHONHOME' -or
    $_.Name -eq 'PYTHONPATH' -or
    $_.Name -like '_PYI*' -or
    $_.Name -like 'PYI_*' -or
    $_.Name -like 'PYINSTALLER*' -or
    $_.Name -like '_MEI*'
}} | ForEach-Object {{
    Remove-Item -LiteralPath ("Env:" + $_.Name) -ErrorAction SilentlyContinue
}}
if ($env:Path) {{
    $parts = $env:Path -split ';'
    $kept = @()
    foreach ($entry in $parts) {{
        if ([string]::IsNullOrWhiteSpace($entry)) {{ continue }}
        if ($entry -like '*_MEI*') {{ continue }}
        $kept += $entry
    }}
    $env:Path = ($kept -join ';')
}}

$swapped = $false
for ($i = 0; $i -lt 240; $i++) {{
    try {{
        if (-not (Test-Path -LiteralPath $newExe)) {{
            throw 'Downloaded update file is missing'
        }}
        if (Test-Path -LiteralPath $backup) {{
            Remove-Item -LiteralPath $backup -Force -ErrorAction Stop
        }}
        if (Test-Path -LiteralPath $current) {{
            Move-Item -LiteralPath $current -Destination $backup -Force -ErrorAction Stop
        }}
        Move-Item -LiteralPath $newExe -Destination $current -Force -ErrorAction Stop
        if (Test-Path -LiteralPath $current) {{
            $len = (Get-Item -LiteralPath $current).Length
            if ($len -ne $expectedLen) {{
                throw "size mismatch after swap: expected=$expectedLen actual=$len"
            }}
        }}
        Start-Sleep -Milliseconds 1500
        $launched = $false
        for ($j = 0; $j -lt 5; $j++) {{
            try {{
                $proc = Start-Process -FilePath $current -WorkingDirectory (Split-Path -Path $current -Parent) -PassThru -ErrorAction Stop
                Start-Sleep -Milliseconds 1200
                if (-not $proc.HasExited) {{
                    $launched = $true
                    break
                }}
            }} catch {{}}
            Start-Sleep -Milliseconds 700
        }}
        if (-not $launched) {{
            throw "Updated launcher exited immediately after all launch retries"
        }}
        $swapped = $true
        break
    }} catch {{
        Start-Sleep -Milliseconds 250
    }}
}}
if (-not $swapped) {{
    if ((-not (Test-Path -LiteralPath $current)) -and (Test-Path -LiteralPath $backup)) {{
        try {{
            Move-Item -LiteralPath $backup -Destination $current -Force -ErrorAction Stop
        }} catch {{}}
    }}
}}
"""


def _spawn_swapper(current_exe: Path, new_exe: Path) -> None:
    backup_exe = current_exe.with_suffix(".exe.old")
    script = _build_swap_script(current_exe, new_exe, backup_exe, os.getpid())
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")

    windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
    ps_exe = windir / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    ps_cmd = str(ps_exe if ps_exe.exists() else Path("powershell.exe"))

    flags = 0
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        flags |= subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
    if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        flags |= subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]

    # Prevent leaking python/pythonnet/pyinstaller runtime env vars into helper/new launcher process.
    clean_env, _, _ = _sanitize_launch_env(os.environ)

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
        env=clean_env,
    )


def _apply_update(new_exe: Path, current_exe: Path) -> None:
    """
    Start detached replacer process and terminate current launcher.
    """
    _update(state=STATE_APPLYING, active=True)
    _spawn_swapper(current_exe, new_exe)

    _update(state=STATE_DONE, active=False)
    time.sleep(0.5)  # let UI observe state=done

    if _shutdown_callback is not None:
        try:
            _shutdown_callback()
            # Let main thread exit gracefully after webview closes.
            return
        except Exception:
            pass
    # Fallback when callback is absent/failed.
    os._exit(0)
