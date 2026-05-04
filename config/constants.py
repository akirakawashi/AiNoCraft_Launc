"""
Application-wide constants: metadata, runtime defaults, authentication.

Values here are never modified at runtime. They are imported by other
modules and by the UI through :func:`~config.profiles.get_runtime_config`.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

# ── App metadata ─────────────────────────────────────────────────────────────

APP_NAME: str = "AiNoCraft"
LAUNCHER_NAME: str = "AiNoCraft-Launcher"


def _read_launcher_version(default: str = "0.0.0") -> str:
    version_path = Path(__file__).resolve().parent.parent / "version.json"
    try:
        payload = json.loads(version_path.read_text(encoding="utf-8-sig"))
        version = str(payload.get("version", "")).strip()
        if re.fullmatch(r"\d+(?:\.\d+)*", version):
            return version
    except Exception:
        pass
    return default


LAUNCHER_VERSION: str = _read_launcher_version()
LAUNCHER_WINDOW_TITLE: str = "AiNoCraft Launcher"

# LAUNCHER_UPDATE_URL: str | None = None
LAUNCHER_UPDATE_URL: str | None = "https://storage.ainocraft.com/downloads/version.json"
WINDOW_WIDTH: int = 1000
WINDOW_HEIGHT: int = 620
WINDOW_RESIZABLE: bool = False
WINDOW_BACKGROUND_COLOR: str = "#0a0e1a"

# ── Minecraft / game defaults ────────────────────────────────────────────────

ASSETS_INDEX: str = "17"

RAM_MIN_GB: int = 1
RAM_MAX_GB: int = 16
RAM_DEFAULT_GB: int = 2

DEFAULT_SETTINGS: dict[str, int] = {
    "ram": RAM_DEFAULT_GB,
}

# Minecraft auth placeholders for offline launch mode
DEFAULT_ACCESS_TOKEN: str = "0"
DEFAULT_CLIENT_ID: str = "00000000-0000-0000-0000-000000000000"

# ── Network ──────────────────────────────────────────────────────────────────

AUTH_TIMEOUT_SEC: int = 10
DOWNLOAD_TIMEOUT_SEC: int = 30
DOWNLOAD_CHUNK_SIZE: int = 65_536
DOWNLOAD_PROGRESS_INTERVAL_SEC: float = 0.4

# ── Authentication ───────────────────────────────────────────────────────────

AUTH_SERVER_PRESETS: dict[str, str] = {
    "prod": "https://api.ainocraft.com",
    "local": "http://127.0.0.1:8000",
}

# Переключение окружения:
#   AINOCRAFT_AUTH_PROFILE=prod|local (по умолчанию prod)
# Дополнительно можно переопределить base URL напрямую:
#   AINOCRAFT_AUTH_BASE_URL=https://example.com
AUTH_SERVER_PROFILE: str = str(os.environ.get("AINOCRAFT_AUTH_PROFILE", "prod")).strip().lower() or "prod"
_AUTH_SERVER_BASE_BY_PROFILE = AUTH_SERVER_PRESETS.get(AUTH_SERVER_PROFILE, AUTH_SERVER_PRESETS["prod"])
_AUTH_SERVER_BASE_OVERRIDE = str(os.environ.get("AINOCRAFT_AUTH_BASE_URL", "")).strip()
_AUTH_SERVER_BASE_RESOLVED = (_AUTH_SERVER_BASE_OVERRIDE or _AUTH_SERVER_BASE_BY_PROFILE).strip()
# 0.0.0.0 is a server bind address, not a routable client destination.
if _AUTH_SERVER_BASE_RESOLVED.startswith("http://0.0.0.0"):
    _AUTH_SERVER_BASE_RESOLVED = "http://127.0.0.1" + _AUTH_SERVER_BASE_RESOLVED[len("http://0.0.0.0") :]
elif _AUTH_SERVER_BASE_RESOLVED.startswith("https://0.0.0.0"):
    _AUTH_SERVER_BASE_RESOLVED = "https://127.0.0.1" + _AUTH_SERVER_BASE_RESOLVED[len("https://0.0.0.0") :]

AUTH_SERVER_BASE_URL: str | None = _AUTH_SERVER_BASE_RESOLVED.rstrip("/") or None

AUTH_API_BASE_URL: str | None = (
    f"{AUTH_SERVER_BASE_URL}/minecraft-server-api/authserver" if AUTH_SERVER_BASE_URL else None
)
AUTHLIB_INJECTOR_API_BASE_URL: str | None = (
    f"{AUTH_SERVER_BASE_URL}/minecraft-server-api/" if AUTH_SERVER_BASE_URL else None
)

# Локальный jar для client-side authlib-injector.
AUTHLIB_INJECTOR_JAR_NAME: str = "authlib-injector-1.2.7.jar"
# Можно указать кастомный путь (абсолютный или относительно корня лаунчера):
#   AINOCRAFT_AUTHLIB_INJECTOR_JAR=path/to/authlib-injector.jar
AUTHLIB_INJECTOR_JAR_PATH: str | None = str(os.environ.get("AINOCRAFT_AUTHLIB_INJECTOR_JAR", "")).strip() or None

AUTH_AUTHENTICATE_URL: str | None = f"{AUTH_API_BASE_URL}/authenticate" if AUTH_API_BASE_URL else None
AUTH_REFRESH_URL: str | None = f"{AUTH_API_BASE_URL}/refresh" if AUTH_API_BASE_URL else None
AUTH_SIGNOUT_URL: str | None = f"{AUTH_API_BASE_URL}/signout" if AUTH_API_BASE_URL else None
AUTH_INVALIDATE_URL: str | None = f"{AUTH_API_BASE_URL}/invalidate" if AUTH_API_BASE_URL else None
AUTH_VALIDATE_URL: str | None = f"{AUTH_API_BASE_URL}/validate" if AUTH_API_BASE_URL else None

# Backward-compatible aliases for older imports.
AUTH_LOGIN_URL: str | None = AUTH_AUTHENTICATE_URL
AUTH_LOGOUT_URL: str | None = AUTH_INVALIDATE_URL








