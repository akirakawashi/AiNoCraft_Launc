"""
Filesystem paths used across the launcher.

Build profiles file is resolved once at import time with this priority:
  1) ``AINOCRAFT_BUILD_PROFILES`` environment variable
  2) ``<project_root>/build_profiles.json``
  3) ``%APPDATA%/AiNoCraftLauncher/build_profiles.json``
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

# ── Core directories ─────────────────────────────────────────────────────────

LAUNCHER_DIR: Path = Path(__file__).parent.parent.resolve()
APPDATA_DIR: Path = Path(os.environ.get("APPDATA", str(Path.home())))
LAUNCHER_DATA_DIR: Path = APPDATA_DIR / "AiNoCraftLauncher"
DOWNLOAD_TEMP_DIR: Path = Path(tempfile.gettempdir()) / "AiNoCraftLauncher"
GAME_DIR: Path = DOWNLOAD_TEMP_DIR  # legacy alias used for temp files
JAVA_BIN: Path = LAUNCHER_DATA_DIR / "java" / "bin" / "javaw.exe"  # fallback Java

# ── Build profiles file ─────────────────────────────────────────────────────

_BUILD_PROFILES_ENV = os.environ.get("AINOCRAFT_BUILD_PROFILES")


def _resolve_profiles_file() -> Path:
    """Return the path to ``build_profiles.json``, checking env → local → appdata."""
    if _BUILD_PROFILES_ENV:
        return Path(_BUILD_PROFILES_ENV)

    local_file = LAUNCHER_DIR / "build_profiles.json"
    if local_file.exists():
        return local_file

    return LAUNCHER_DATA_DIR / "build_profiles.json"


BUILD_PROFILES_FILE: Path = _resolve_profiles_file()
