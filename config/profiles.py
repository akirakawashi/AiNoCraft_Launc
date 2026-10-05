"""Build profile registry and per-build path resolution.

Profiles come from three sources, in priority order:

1. the backend launcher bootstrap endpoint (``apply_backend_builds``);
2. a local ``build_profiles.json`` (``AINOCRAFT_BUILD_PROFILES`` override);
3. built-in defaults.

Download URLs may be absolute or relative to the storage base URL, so the
backend never has to know where archives are mirrored in dev mode.
"""

from __future__ import annotations

import ipaddress
import json
import threading
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .constants import BUILD_MARKER_FILENAME
from .paths import BUILD_PROFILES_FILE, GAME_INSTANCES_DIR
from .runtime import RUNTIME


_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def _coerce_sha256(value: Any) -> str:
    """Return a lowercase 64-hex SHA-256, or an empty string when absent/invalid."""
    digest = str(value or "").strip().lower()
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        return ""
    return digest


def _coerce_size(value: Any) -> int:
    """Return a positive byte count, or zero when absent/invalid."""
    try:
        size = int(value or 0)
    except (TypeError, ValueError):
        return 0
    return size if size > 0 else 0


def is_download_url_allowed(url: str) -> bool:
    """Allow https anywhere; allow http only for loopback hosts (dev/local MinIO)."""
    parsed = urlparse(str(url or "").strip())
    if parsed.scheme == "https":
        return True
    if parsed.scheme != "http":
        return False
    host = (parsed.hostname or "").lower()
    if host in _LOOPBACK_HOSTS:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


@dataclass(frozen=True, slots=True)
class BuildProfile:
    id: str
    name: str
    title: str
    folder_name: str
    version_name: str
    download_url: str
    revision: str
    minecraft_version: str
    description: str
    glyph: str
    accent_color: str
    archive_sha256: str = ""
    archive_size_bytes: int = 0
    unpacked_size_bytes: int = 0


@dataclass(frozen=True, slots=True)
class BuildPaths:
    build_id: str
    build_name: str
    download_url: str
    revision: str
    game_dir: Path
    marker_file: Path
    java_bin: Path
    version_name: str
    version_dir: Path
    version_json: Path
    client_jar: Path
    assets_dir: Path
    libraries_dir: Path
    natives_dir: Path
    settings_file: Path
    archive_sha256: str = ""
    archive_size_bytes: int = 0
    unpacked_size_bytes: int = 0


def _default_profile(build_id: str, title: str, description: str, glyph: str, accent_color: str) -> BuildProfile:
    return BuildProfile(
        id=build_id,
        name=build_id,
        title=title,
        folder_name=f"AiNoCraft{title}",
        version_name=title,
        download_url=f"downloads/AiNoCraft{title}.zip",
        revision="",
        minecraft_version="1.20.1",
        description=description,
        glyph=glyph,
        accent_color=accent_color,
    )


DEFAULT_BUILD_PROFILES: dict[str, BuildProfile] = {
    profile.id: profile
    for profile in (
        _default_profile("tech", "Tech", "Технологии и автоматизация", "T", "#8fd5ff"),
        _default_profile("magic", "Magic", "Магия, ритуалы и развитие", "M", "#c98fff"),
        _default_profile("rpg", "Rpg", "Квесты, классы и приключения", "R", "#ffb86b"),
        _default_profile("classic", "Classic", "Классический сервер с улучшениями", "C", "#b8c6ff"),
    )
}

FALLBACK_DEFAULT_BUILD_ID = "tech"

_registry_lock = threading.Lock()


def _coerce_profile(raw_id: str, raw: dict[str, Any]) -> BuildProfile | None:
    build_id = str(raw_id or raw.get("id", "")).strip().lower()
    if not build_id:
        return None

    title = str(raw.get("title", "")).strip() or build_id.title()
    name = str(raw.get("name", "")).strip() or build_id
    folder_name = str(raw.get("folder_name", "")).strip() or f"AiNoCraft{title}"
    version_name = str(raw.get("version_name", "")).strip() or title
    download_url = str(raw.get("download_url", "")).strip()
    revision = str(raw.get("revision", "")).strip()
    minecraft_version = str(raw.get("minecraft_version", "")).strip() or "1.20.1"
    description = str(raw.get("description", "")).strip()
    glyph = (str(raw.get("glyph", "")).strip()[:1] or build_id[:1].upper() or "?")
    accent_color = str(raw.get("accent_color", "")).strip() or "#8fd5ff"
    archive_sha256 = _coerce_sha256(raw.get("sha256"))
    archive_size_bytes = _coerce_size(raw.get("archive_size_bytes"))
    unpacked_size_bytes = _coerce_size(raw.get("unpacked_size_bytes"))

    return BuildProfile(
        id=build_id,
        name=name,
        title=title,
        folder_name=folder_name,
        version_name=version_name,
        download_url=download_url,
        revision=revision,
        minecraft_version=minecraft_version,
        description=description,
        glyph=glyph,
        accent_color=accent_color,
        archive_sha256=archive_sha256,
        archive_size_bytes=archive_size_bytes,
        unpacked_size_bytes=unpacked_size_bytes,
    )


def _parse_profiles_payload(payload: Any) -> dict[str, BuildProfile]:
    profiles: dict[str, BuildProfile] = {}
    if isinstance(payload, dict) and isinstance(payload.get("builds"), list):
        iterable = ((str(item.get("id", "")), item) for item in payload["builds"] if isinstance(item, dict))
    elif isinstance(payload, list):
        iterable = ((str(item.get("id", "")), item) for item in payload if isinstance(item, dict))
    elif isinstance(payload, dict):
        iterable = ((str(key), item) for key, item in payload.items() if isinstance(item, dict))
    else:
        return profiles

    for build_id, item in iterable:
        profile = _coerce_profile(build_id, item)
        if profile:
            profiles[profile.id] = profile
    return profiles


def _load_profiles_from_file(path: Path) -> dict[str, BuildProfile]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
    return _parse_profiles_payload(payload)


def _initial_registry() -> tuple[dict[str, BuildProfile], str]:
    profiles = _load_profiles_from_file(BUILD_PROFILES_FILE) or dict(DEFAULT_BUILD_PROFILES)
    default_id = FALLBACK_DEFAULT_BUILD_ID if FALLBACK_DEFAULT_BUILD_ID in profiles else next(iter(profiles))
    return profiles, default_id


_BUILD_PROFILES, DEFAULT_BUILD_ID = _initial_registry()


def apply_backend_builds(builds: list[dict[str, Any]], default_build_id: str = "") -> bool:
    """Replace the profile registry with the backend build catalog.

    Returns ``False`` and keeps the current registry when the payload
    contains no usable builds.
    """
    global _BUILD_PROFILES, DEFAULT_BUILD_ID

    parsed = _parse_profiles_payload(builds)
    if not parsed:
        return False

    resolved_default = str(default_build_id or "").strip().lower()
    if resolved_default not in parsed:
        resolved_default = next(iter(parsed))

    with _registry_lock:
        _BUILD_PROFILES = parsed
        DEFAULT_BUILD_ID = resolved_default
    return True


def apply_build_manifest(payload: dict[str, Any]) -> int:
    """Merge remote revisions and archive URLs into the active build catalog.

    The MinIO manifest may expose ``builds`` either as an object keyed by build
    id or as a list containing explicit ``id`` fields. Unknown builds are
    ignored because their UI metadata and installation paths are not known to
    the launcher.
    """
    raw_builds = payload.get("builds")
    if isinstance(raw_builds, dict):
        items = ((str(build_id), raw) for build_id, raw in raw_builds.items())
    elif isinstance(raw_builds, list):
        items = (
            (str(raw.get("id", "")), raw)
            for raw in raw_builds
            if isinstance(raw, dict)
        )
    else:
        return 0

    updates: dict[str, tuple[str, str, str, int, int]] = {}
    for raw_id, raw in items:
        if not isinstance(raw, dict):
            continue
        build_id = raw_id.strip().lower()
        revision = str(raw.get("revision", "")).strip()
        download_url = str(raw.get("download_url", "")).strip()
        sha256 = _coerce_sha256(raw.get("sha256"))
        archive_size_bytes = _coerce_size(raw.get("archive_size_bytes"))
        unpacked_size_bytes = _coerce_size(raw.get("unpacked_size_bytes"))
        if build_id and revision and download_url:
            updates[build_id] = (
                revision,
                download_url,
                sha256,
                archive_size_bytes,
                unpacked_size_bytes,
            )

    if not updates:
        return 0

    applied = 0
    with _registry_lock:
        for build_id, update in updates.items():
            revision, download_url, sha256, archive_size_bytes, unpacked_size_bytes = update
            profile = _BUILD_PROFILES.get(build_id)
            if profile is None:
                continue
            _BUILD_PROFILES[build_id] = replace(
                profile,
                revision=revision,
                download_url=download_url,
                archive_sha256=sha256 or profile.archive_sha256,
                archive_size_bytes=archive_size_bytes,
                unpacked_size_bytes=unpacked_size_bytes,
            )
            applied += 1
    return applied


def get_default_build_id() -> str:
    return DEFAULT_BUILD_ID


def _profiles_snapshot() -> dict[str, BuildProfile]:
    with _registry_lock:
        return dict(_BUILD_PROFILES)


def _resolve_download_url(profile: BuildProfile) -> str:
    url = profile.download_url.strip()
    if not url:
        return RUNTIME.storage_url("downloads", f"{profile.folder_name}.zip")
    if url.startswith(("http://", "https://")):
        return url
    return RUNTIME.storage_url(url)


def get_available_builds() -> list[dict[str, str]]:
    """Return UI-facing build descriptors."""
    return [
        {
            "id": profile.id,
            "name": profile.name,
            "title": profile.title,
            "minecraft_version": profile.minecraft_version,
            "description": profile.description,
            "glyph": profile.glyph,
            "accent_color": profile.accent_color,
            "revision": profile.revision,
        }
        for profile in _profiles_snapshot().values()
    ]


def get_build_paths(build_id: str | None = None) -> BuildPaths:
    resolved_id = (build_id or DEFAULT_BUILD_ID).strip().lower()
    profile = _profiles_snapshot().get(resolved_id)
    if not profile:
        raise ValueError(f"Неизвестная сборка: {build_id}")

    instance_dir = GAME_INSTANCES_DIR / profile.folder_name
    version_dir = instance_dir / "versions" / profile.version_name
    return BuildPaths(
        build_id=profile.id,
        build_name=profile.name,
        download_url=_resolve_download_url(profile),
        revision=profile.revision,
        game_dir=instance_dir,
        marker_file=instance_dir / BUILD_MARKER_FILENAME,
        java_bin=instance_dir / "java" / "bin" / "javaw.exe",
        version_name=profile.version_name,
        version_dir=version_dir,
        version_json=version_dir / f"{profile.version_name}.json",
        client_jar=version_dir / f"{profile.version_name}.jar",
        assets_dir=instance_dir / "assets",
        libraries_dir=instance_dir / "libraries",
        natives_dir=version_dir / "natives",
        settings_file=version_dir / "launcher_settings.json",
        archive_sha256=profile.archive_sha256,
        archive_size_bytes=profile.archive_size_bytes,
        unpacked_size_bytes=profile.unpacked_size_bytes,
    )


def resolve_client_files(paths: BuildPaths) -> tuple[Path, Path, str]:
    if paths.version_json.exists() and paths.client_jar.exists():
        return paths.version_json, paths.client_jar, paths.version_json.stem

    if not paths.version_dir.exists():
        return paths.version_json, paths.client_jar, paths.version_name

    ignored_json = {"launcher_settings.json", "tlauncheradditional.json"}
    json_candidates = sorted(
        (path for path in paths.version_dir.glob("*.json") if path.name.lower() not in ignored_json),
        key=lambda path: path.name.lower(),
    )
    jar_candidates = sorted(paths.version_dir.glob("*.jar"), key=lambda path: path.name.lower())
    jars_by_stem = {path.stem.lower(): path for path in jar_candidates}

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
