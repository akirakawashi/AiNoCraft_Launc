"""
Build profiles: dataclasses, loading, and path resolution.

A *build profile* describes one modpack variant (Tech, RPG, Magic, …).
Profiles are loaded from JSON at import time; if no file is found
the hardcoded :data:`DEFAULT_BUILD_PROFILES` are used.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config.constants import (
    APP_NAME,
    AUTH_SERVER_BASE_URL,
    AUTH_SERVER_PROFILE,
    LAUNCHER_NAME,
    LAUNCHER_VERSION,
    RAM_DEFAULT_GB,
    RAM_MAX_GB,
    RAM_MIN_GB,
)
from config.paths import APPDATA_DIR, BUILD_PROFILES_FILE



# ── Data classes ─────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class BuildProfile:
    """Metadata for a single modpack variant."""

    id: str
    name: str
    folder_name: str
    version_name: str
    download_url: str
    glyph: str
    accent_color: str


@dataclass(frozen=True, slots=True)
class BuildPaths:
    """Resolved filesystem paths for a selected build."""

    build_id: str
    build_name: str
    download_url: str
    game_dir: Path
    java_bin: Path
    version_name: str
    version_dir: Path
    version_json: Path
    client_jar: Path
    assets_dir: Path
    libraries_dir: Path
    natives_dir: Path
    settings_file: Path


# ── Hardcoded default profiles ───────────────────────────────────────────────

DEFAULT_BUILD_PROFILES: dict[str, BuildProfile] = {
    "tech": BuildProfile(
        id="tech",
        name="AiNoCraftTech",
        folder_name="AiNoCraftTech",
        version_name="Tech",
        download_url="https://storage.ainocraft.com/downloads/AiNoCraftTech.zip",
        glyph="T",
        accent_color="#8fd5ff",
    ),
    "rpg": BuildProfile(
        id="rpg",
        name="AiNoCraftRPG",
        folder_name="AiNoCraftRPG",
        version_name="RPG",
        download_url="https://storage.ainocraft.com/downloads/AiNoCraftRPG.zip",
        glyph="R",
        accent_color="#9df0bf",
    ),
    "magic": BuildProfile(
        id="magic",
        name="AiNoCraftMagic",
        folder_name="AiNoCraftMagic",
        version_name="Magic",
        download_url="https://storage.ainocraft.com/downloads/AiNoCraftMagic.zip",
        glyph="M",
        accent_color="#ffc4f0",
    ),
    "sky": BuildProfile(
        id="sky",
        name="AiNoCraftSky",
        folder_name="AiNoCraftSky",
        version_name="Sky",
        download_url="https://storage.ainocraft.com/downloads/AiNoCraftSky.zip",
        glyph="S",
        accent_color="#9edcff",
    ),
}
DEFAULT_BUILD_ID = "tech"


# ── Profile coercion & parsing ───────────────────────────────────────────────


def _coerce_profile(raw_id: str, raw: dict[str, Any]) -> BuildProfile | None:
    """Validate and normalise a single profile dict into a :class:`BuildProfile`."""
    build_id = str(raw_id or "").strip().lower()
    if not build_id:
        return None

    name = str(raw.get("name", "")).strip() or f"{APP_NAME}{build_id.title()}"
    folder_name = str(raw.get("folder_name", "")).strip() or name
    version_name = str(raw.get("version_name", "")).strip() or build_id.title()
    download_url = str(raw.get("download_url", "")).strip()

    glyph_raw = str(raw.get("glyph", "")).strip()
    glyph = (glyph_raw[:1] if glyph_raw else build_id[:1].upper()) or "?"

    accent_color = str(raw.get("accent_color", "")).strip() or "#8fd5ff"

    return BuildProfile(
        id=build_id,
        name=name,
        folder_name=folder_name,
        version_name=version_name,
        download_url=download_url,
        glyph=glyph,
        accent_color=accent_color,
    )


def _parse_profiles_payload(payload: Any) -> dict[str, BuildProfile]:
    """Accept several JSON shapes and return a *build_id -> profile* mapping."""
    profiles: dict[str, BuildProfile] = {}

    # Shape: {"builds": [{...}, ...]}
    if isinstance(payload, dict) and isinstance(payload.get("builds"), list):
        for item in payload["builds"]:
            if not isinstance(item, dict):
                continue
            build_id = str(item.get("id", "")).strip().lower()
            profile = _coerce_profile(build_id, item)
            if profile:
                profiles[profile.id] = profile
        return profiles

    # Shape: [{...}, ...]
    if isinstance(payload, list):
        for item in payload:
            if not isinstance(item, dict):
                continue
            build_id = str(item.get("id", "")).strip().lower()
            profile = _coerce_profile(build_id, item)
            if profile:
                profiles[profile.id] = profile
        return profiles

    # Shape: {"tech": {...}, "rpg": {...}}
    if isinstance(payload, dict):
        for build_id, item in payload.items():
            if not isinstance(item, dict):
                continue
            profile = _coerce_profile(str(build_id), item)
            if profile:
                profiles[profile.id] = profile
        return profiles

    return profiles


def _load_profiles_from_file(path: Path) -> dict[str, BuildProfile]:
    """Try to parse a JSON file into profiles; return empty dict on failure."""
    if not path.exists():
        return {}

    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            payload = json.load(f)
    except Exception as exc:
        return {}

    parsed = _parse_profiles_payload(payload)
    return parsed


def _load_build_profiles() -> dict[str, BuildProfile]:
    """Load profiles from JSON file, falling back to hardcoded defaults."""
    loaded = _load_profiles_from_file(BUILD_PROFILES_FILE)
    if loaded:
        return loaded
    return dict(DEFAULT_BUILD_PROFILES)


# ── Module-level singletons ─────────────────────────────────────────────────

BUILD_PROFILES: dict[str, BuildProfile] = _load_build_profiles()
if not BUILD_PROFILES:
    raise RuntimeError("No build profiles configured")

if DEFAULT_BUILD_ID not in BUILD_PROFILES:
    DEFAULT_BUILD_ID = next(iter(BUILD_PROFILES))


# ── Public helpers ───────────────────────────────────────────────────────────


def get_runtime_config() -> dict[str, Any]:
    """Returns runtime config consumed by UI and backend."""
    return {
        "app_name": APP_NAME,
        "launcher_name": LAUNCHER_NAME,
        "launcher_version": LAUNCHER_VERSION,
        "auth_server_profile": AUTH_SERVER_PROFILE,
        "auth_server_base_url": AUTH_SERVER_BASE_URL,
        "ram_min_gb": RAM_MIN_GB,
        "ram_max_gb": RAM_MAX_GB,
        "ram_default_gb": RAM_DEFAULT_GB,
    }


def resolve_client_files(paths: BuildPaths) -> tuple[Path, Path, str]:
    """
    Returns ``(version_json, client_jar, effective_version_name)`` for a build.

    Priority:
      1. Explicit profile paths (``paths.version_json`` / ``paths.client_jar``)
      2. Auto-detect matching pair ``*.json`` + ``*.jar`` with the same stem
      3. First found ``*.json`` and ``*.jar``
    """
    if paths.version_json.exists() and paths.client_jar.exists():
        return paths.version_json, paths.client_jar, paths.version_json.stem

    if not paths.version_dir.exists():
        return paths.version_json, paths.client_jar, paths.version_name

    ignored_json = {"launcher_settings.json", "tlauncheradditional.json"}
    json_candidates = sorted(
        [
            p
            for p in paths.version_dir.glob("*.json")
            if p.name.lower() not in ignored_json
        ],
        key=lambda p: p.name.lower(),
    )
    jar_candidates = sorted(
        paths.version_dir.glob("*.jar"), key=lambda p: p.name.lower()
    )

    # Prefer files with the same stem (RPG.json + RPG.jar)
    jars_by_stem = {p.stem.lower(): p for p in jar_candidates}
    for json_file in json_candidates:
        matched_jar = jars_by_stem.get(json_file.stem.lower())
        if matched_jar:
            return json_file, matched_jar, json_file.stem

    if json_candidates and jar_candidates:
        return json_candidates[0], jar_candidates[0], json_candidates[0].stem

    if json_candidates:
        stem = json_candidates[0].stem
        return json_candidates[0], paths.version_dir / f"{stem}.jar", stem

    if jar_candidates:
        stem = jar_candidates[0].stem
        return paths.version_dir / f"{stem}.json", jar_candidates[0], stem

    return paths.version_json, paths.client_jar, paths.version_name


def get_available_builds() -> list[dict[str, str]]:
    """Build list used by UI."""
    return [
        {
            "id": profile.id,
            "name": profile.name,
            "glyph": profile.glyph,
            "accent_color": profile.accent_color,
        }
        for profile in BUILD_PROFILES.values()
    ]


def get_build_paths(build_id: str | None = None) -> BuildPaths:
    """
    Returns resolved paths for selected build.
    Raises ``ValueError`` if build is unknown.
    """
    resolved_id = (build_id or DEFAULT_BUILD_ID).strip().lower()
    profile = BUILD_PROFILES.get(resolved_id)
    if not profile:
        raise ValueError(f"Неизвестная сборка: {build_id}")

    instance_dir = APPDATA_DIR / profile.folder_name
    version_dir = instance_dir / "versions" / profile.version_name

    return BuildPaths(
        build_id=profile.id,
        build_name=profile.name,
        download_url=profile.download_url,
        game_dir=instance_dir,
        java_bin=instance_dir / "java" / "bin" / "javaw.exe",
        version_name=profile.version_name,
        version_dir=version_dir,
        version_json=version_dir / f"{profile.version_name}.json",
        client_jar=version_dir / f"{profile.version_name}.jar",
        assets_dir=instance_dir / "assets",
        libraries_dir=instance_dir / "libraries",
        natives_dir=version_dir / "natives",
        settings_file=version_dir / "launcher_settings.json",
    )
