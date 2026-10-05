"""Filesystem paths for source and PyInstaller runtime modes."""

from __future__ import annotations

import os
import sys
from pathlib import Path


LAUNCHER_DIR: Path = Path(__file__).resolve().parent.parent


def _resource_root() -> Path:
    frozen_root = str(getattr(sys, "_MEIPASS", "")).strip()
    if frozen_root:
        return Path(frozen_root).resolve()
    return LAUNCHER_DIR


RESOURCE_DIR: Path = _resource_root()


def resource_path(*parts: str) -> Path:
    """Return a bundled resource path in source or frozen mode."""
    return RESOURCE_DIR.joinpath(*parts)


def _appdata_dir() -> Path:
    if os.name == "nt":
        return Path(os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA") or str(Path.home()))
    return Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share"))


def _local_appdata_dir() -> Path:
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or str(Path.home()))
    return Path(os.environ.get("XDG_STATE_HOME") or (Path.home() / ".local" / "state"))


APPDATA_DIR: Path = _appdata_dir()
LOCALAPPDATA_DIR: Path = _local_appdata_dir()

# These paths intentionally mirror the bootstrapper's default installation
# layout. The bootstrapper owns ``Launcher/current``; the launcher owns only
# the adjacent ``Launcher/data`` directory.
LAUNCHER_ROOT_DIR: Path = LOCALAPPDATA_DIR / "AiNoCraft" / "Launcher"
LAUNCHER_DATA_DIR: Path = LAUNCHER_ROOT_DIR / "data"

# Minecraft instances are the only launcher data stored in Roaming AppData.
# One folder is created per profile's ``folder_name`` below this root.
GAME_INSTANCES_DIR: Path = APPDATA_DIR / "AiNoCraft"

DOWNLOAD_TEMP_DIR: Path = LAUNCHER_DATA_DIR / "temp"

UI_INDEX_FILE: Path = resource_path("ui", "web", "index.html")
BUILD_METADATA_FILE: Path = resource_path("build_metadata.json")
BUILD_PROFILES_FILE: Path = Path(
    ("" if getattr(sys, "frozen", False) else os.environ.get("AINOCRAFT_BUILD_PROFILES", ""))
    or resource_path("build_profiles.json")
)

JAVA_BIN: Path = LAUNCHER_DATA_DIR / "java" / "bin" / "javaw.exe"
