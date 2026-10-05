"""Canonical CustomSkinLoader configuration for official game builds."""

from __future__ import annotations

import json
import os
import re
import tempfile
import zipfile
from pathlib import Path
from typing import Any


SUPPORTED_VERSION = "15.0.1"
SUPPORTED_BUILD_NUMBER = 40

CANONICAL_CONFIG: dict[str, Any] = {
    "version": SUPPORTED_VERSION,
    "buildNumber": SUPPORTED_BUILD_NUMBER,
    "loadlist": [
        {
            "name": "GameProfile",
            "type": "GameProfile",
        }
    ],
    "enableTransparentSkin": True,
    "forceLoadAllTextures": False,
    "enableCape": True,
    "threadPoolSize": 8,
    "enableLogStdOut": True,
    "cacheExpiry": 30,
    "forceUpdateSkull": False,
    "enableLocalProfileCache": False,
    "enableCacheAutoClean": False,
    "forceDisableCache": True,
}


class CustomSkinLoaderConfigurationError(RuntimeError):
    """The installed game build cannot use the authoritative skin profile."""


def _is_custom_skin_loader_jar(path: Path) -> bool:
    normalized_name = re.sub(r"[^a-z0-9]", "", path.stem.lower())
    return "customskinloader" in normalized_name


def _manifest_version(jar_path: Path) -> str:
    try:
        with zipfile.ZipFile(jar_path) as jar:
            raw_manifest = jar.read("META-INF/MANIFEST.MF").decode("utf-8", errors="replace")
    except (KeyError, OSError, zipfile.BadZipFile):
        return ""

    unfolded = raw_manifest.replace("\r\n ", "").replace("\n ", "")
    for line in unfolded.splitlines():
        name, separator, value = line.partition(":")
        if separator and name.strip().lower() in {
            "implementation-version",
            "specification-version",
        }:
            return value.strip()
    return ""


def _jar_version(jar_path: Path) -> str:
    filename_versions = re.findall(r"(?<!\d)(\d+\.\d+\.\d+)(?!\d)", jar_path.stem)
    if SUPPORTED_VERSION in filename_versions:
        return SUPPORTED_VERSION
    manifest_version = _manifest_version(jar_path)
    if manifest_version:
        return manifest_version
    return filename_versions[-1] if filename_versions else ""


def _resolve_supported_mod(version_dir: Path) -> Path:
    mods_dir = version_dir / "mods"
    jars = sorted(
        (path for path in mods_dir.glob("*.jar") if _is_custom_skin_loader_jar(path)),
        key=lambda path: path.name.lower(),
    )
    if not jars:
        raise CustomSkinLoaderConfigurationError(
            "Сборка повреждена: в папке mods отсутствует CustomSkinLoader 15.0.1. "
            "Переустановите или обновите сборку."
        )
    if len(jars) != 1:
        names = ", ".join(path.name for path in jars)
        raise CustomSkinLoaderConfigurationError(
            f"Сборка повреждена: найдено несколько JAR CustomSkinLoader ({names}). "
            "Переустановите сборку."
        )

    jar_path = jars[0]
    if "common" in jar_path.stem.lower():
        raise CustomSkinLoaderConfigurationError(
            "Сборка повреждена: CustomSkinLoader-Common.jar нельзя устанавливать "
            "как мод. Требуется оригинальный bootstrap/universal JAR."
        )

    installed_version = _jar_version(jar_path)
    if installed_version != SUPPORTED_VERSION:
        display_version = installed_version or "неизвестная версия"
        raise CustomSkinLoaderConfigurationError(
            f"Сборка содержит несовместимый CustomSkinLoader ({display_version}). "
            f"Требуется версия {SUPPORTED_VERSION}, build {SUPPORTED_BUILD_NUMBER}."
        )
    return jar_path


def _canonical_json() -> str:
    return json.dumps(CANONICAL_CONFIG, ensure_ascii=False, indent=2) + "\n"


def ensure_custom_skin_loader_config(version_dir: Path) -> Path:
    """Validate the official mod and atomically restore its GameProfile-only config."""
    _resolve_supported_mod(version_dir)

    config_dir = version_dir / "CustomSkinLoader"
    config_path = config_dir / "CustomSkinLoader.json"
    expected = _canonical_json()
    try:
        if config_path.read_text(encoding="utf-8") == expected:
            return config_path
    except (FileNotFoundError, OSError, UnicodeError):
        pass

    config_dir.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=".CustomSkinLoader.",
        suffix=".tmp",
        dir=config_dir,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="\n") as temporary_file:
            temporary_file.write(expected)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, config_path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
    return config_path
