"""Application constants derived from the resolved runtime configuration."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from .paths import BUILD_METADATA_FILE, LAUNCHER_DATA_DIR
from .runtime import RUNTIME, IS_FROZEN


APP_NAME = "AiNoCraft"
LAUNCHER_NAME = "AiNoCraft-Launcher"
LAUNCHER_WINDOW_TITLE = "AiNoCraft Launcher"

WINDOW_WIDTH = 1264
WINDOW_HEIGHT = 771
WINDOW_RESIZABLE = False
WINDOW_BACKGROUND_COLOR = "#05080d"

ASSETS_INDEX = "17"
RAM_MIN_GB = 2
RAM_DEFAULT_GB = 6

DEFAULT_ACCESS_TOKEN = "0"
DEFAULT_CLIENT_ID = "00000000-0000-0000-0000-000000000000"

AUTH_TIMEOUT_SEC = 10
BOOTSTRAP_TIMEOUT_SEC = 10
DOWNLOAD_TIMEOUT_SEC = 30
DOWNLOAD_CHUNK_SIZE = 65_536
DOWNLOAD_PROGRESS_INTERVAL_SEC = 0.4
MAX_GAME_ARCHIVE_BYTES = 16 * 1024**3
MAX_GAME_UNPACKED_BYTES = 64 * 1024**3
MAX_GAME_ARCHIVE_FILES = 250_000
MAX_GAME_SINGLE_FILE_BYTES = 8 * 1024**3
MIN_DISK_RESERVE_BYTES = 2 * 1024**3
BUILD_MARKER_FILENAME = "ainocraft-build.json"


def _read_version(default: str = "0.0.0") -> str:
    for path in (
        BUILD_METADATA_FILE,
        Path(__file__).resolve().parent.parent / "version.json",
    ):
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        version = str(payload.get("version", "")).strip()
        if version and re.fullmatch(r"[A-Za-z0-9_.+-]+", version):
            return version
    return default


LAUNCHER_VERSION = _read_version()
USER_AGENT = f"{LAUNCHER_NAME}/{LAUNCHER_VERSION}"

# REST API root (dev/prod aware), e.g. https://api.ainocraft.com/api/v1/
API_BASE_URL = RUNTIME.api_base_url
LAUNCHER_BOOTSTRAP_URL = f"{API_BASE_URL}launcher/bootstrap"
CURRENT_ACCOUNT_URL = f"{API_BASE_URL}me"
BUILDS_MANIFEST_URL = (
    ("" if IS_FROZEN else str(os.environ.get("AINOCRAFT_BUILDS_MANIFEST_URL", "")).strip())
    or RUNTIME.storage_url("downloads", "builds.json")
)

# Yggdrasil-compatible auth endpoints used by login and authlib-injector.
AUTHLIB_INJECTOR_API_BASE_URL = RUNTIME.minecraft_api_base_url
_AUTHSERVER_BASE_URL = f"{RUNTIME.minecraft_api_base_url}authserver"
AUTH_AUTHENTICATE_URL = f"{_AUTHSERVER_BASE_URL}/authenticate"
AUTH_REFRESH_URL = f"{_AUTHSERVER_BASE_URL}/refresh"
AUTH_INVALIDATE_URL = f"{_AUTHSERVER_BASE_URL}/invalidate"
AUTH_VALIDATE_URL = f"{_AUTHSERVER_BASE_URL}/validate"

LAUNCHER_MANIFEST_URL = (
    ("" if IS_FROZEN else str(os.environ.get("AINOCRAFT_LAUNCHER_MANIFEST_URL", "")).strip())
    or RUNTIME.storage_url("launcher", "stable", "manifest.json")
)
LAUNCHER_UPDATE_ENABLED = str(os.environ.get("AINOCRAFT_LAUNCHER_SELF_UPDATE", "0")).strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

LAUNCHER_DATA_DIR.mkdir(parents=True, exist_ok=True)
