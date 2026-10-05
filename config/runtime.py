"""Launcher runtime mode and base URL resolution.

Single source of truth for dev/prod configuration. The mode is resolved once
at import time with the following priority:

1. CLI argument: ``--mode dev`` / ``--mode=prod``
2. Environment variable: ``AINOCRAFT_ENV=dev|prod``
3. Legacy environment variable: ``AINOCRAFT_AUTH_PROFILE=dev|local|prod``
4. Default: ``prod``

Base URLs come from mode presets and can be overridden individually with
``AINOCRAFT_API_BASE_URL`` and ``AINOCRAFT_STORAGE_BASE_URL``.

In packaged (frozen) builds every CLI/env override above is ignored: the
launcher always uses the baked-in production endpoints so a tampered
environment cannot redirect it (credentials, catalog, updates) to another
server. Overrides remain available for source runs (``python launcher.py``).
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from enum import StrEnum


class LauncherMode(StrEnum):
    PROD = "prod"
    DEV = "dev"


@dataclass(frozen=True, slots=True)
class ModePreset:
    server_base_url: str
    storage_base_url: str
    web_base_url: str


_MODE_PRESETS: dict[LauncherMode, ModePreset] = {
    LauncherMode.PROD: ModePreset(
        server_base_url="https://api.ainocraft.com",
        storage_base_url="https://storage.ainocraft.com/",
        web_base_url="https://ainocraft.com",
    ),
    LauncherMode.DEV: ModePreset(
        server_base_url="http://127.0.0.1:8000",
        storage_base_url="http://127.0.0.1:9000/",
        web_base_url="http://localhost:3000",
    ),
}

_MODE_ALIASES = {
    "prod": LauncherMode.PROD,
    "production": LauncherMode.PROD,
    "dev": LauncherMode.DEV,
    "local": LauncherMode.DEV,
    "development": LauncherMode.DEV,
}

ENV_MODE = "AINOCRAFT_ENV"
ENV_LEGACY_AUTH_PROFILE = "AINOCRAFT_AUTH_PROFILE"
ENV_API_BASE_URL = "AINOCRAFT_API_BASE_URL"
ENV_LEGACY_AUTH_BASE_URL = "AINOCRAFT_AUTH_BASE_URL"
ENV_STORAGE_BASE_URL = "AINOCRAFT_STORAGE_BASE_URL"
ENV_WEB_BASE_URL = "AINOCRAFT_WEB_BASE_URL"

# True in PyInstaller-packaged builds. Used to freeze prod config and ignore
# every environment/CLI override so a tampered environment cannot redirect the
# launcher to an attacker-controlled server.
IS_FROZEN = bool(getattr(sys, "frozen", False))


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    """Resolved launcher runtime configuration."""

    mode: LauncherMode
    server_base_url: str
    """Backend origin, e.g. ``https://api.ainocraft.com``."""
    api_base_url: str
    """REST API root, e.g. ``https://api.ainocraft.com/api/v1/``."""
    minecraft_api_base_url: str
    """Yggdrasil-compatible API root used by authlib-injector."""
    storage_base_url: str
    """Public S3/MinIO base URL, e.g. ``https://storage.ainocraft.com/``."""
    web_base_url: str
    """Public website origin, e.g. ``https://ainocraft.com`` (dev: ``http://localhost:3000``)."""

    @property
    def is_dev(self) -> bool:
        return self.mode == LauncherMode.DEV

    def storage_url(self, *parts: str) -> str:
        """Join path parts onto the storage base URL."""
        tail = "/".join(part.strip("/") for part in parts if part)
        return self.storage_base_url + tail


def _parse_cli_mode(argv: list[str]) -> str:
    for index, arg in enumerate(argv):
        if arg == "--mode" and index + 1 < len(argv):
            return argv[index + 1]
        if arg.startswith("--mode="):
            return arg.split("=", 1)[1]
    return ""


def _resolve_mode(argv: list[str], environ: dict[str, str]) -> LauncherMode:
    for raw in (
        _parse_cli_mode(argv),
        environ.get(ENV_MODE, ""),
        environ.get(ENV_LEGACY_AUTH_PROFILE, ""),
    ):
        mode = _MODE_ALIASES.get(raw.strip().lower())
        if mode is not None:
            return mode
    return LauncherMode.PROD


def _normalize_base_url(value: str) -> str:
    resolved = value.strip().rstrip("/")
    for scheme in ("http://", "https://"):
        unroutable = f"{scheme}0.0.0.0"
        if resolved.startswith(unroutable):
            return f"{scheme}127.0.0.1" + resolved[len(unroutable) :]
    return resolved


def load_runtime_config(
    argv: list[str] | None = None,
    environ: dict[str, str] | None = None,
    frozen: bool | None = None,
) -> RuntimeConfig:
    """Resolve mode and base URLs from CLI args, environment, and presets.

    Packaged (frozen) builds ignore every CLI/env override and always use the
    production preset, so a tampered environment cannot redirect the launcher
    to another server.
    """
    resolved_argv = sys.argv[1:] if argv is None else argv
    resolved_environ = dict(os.environ) if environ is None else environ
    is_frozen = IS_FROZEN if frozen is None else frozen

    if is_frozen:
        mode = LauncherMode.PROD
        preset = _MODE_PRESETS[mode]
        server_base_url = _normalize_base_url(preset.server_base_url)
        storage_base_url = _normalize_base_url(preset.storage_base_url) + "/"
        web_base_url = _normalize_base_url(preset.web_base_url)
    else:
        mode = _resolve_mode(resolved_argv, resolved_environ)
        preset = _MODE_PRESETS[mode]

        server_override = (
            resolved_environ.get(ENV_API_BASE_URL, "").strip()
            or resolved_environ.get(ENV_LEGACY_AUTH_BASE_URL, "").strip()
        )
        server_base_url = _normalize_base_url(server_override or preset.server_base_url)

        storage_override = resolved_environ.get(ENV_STORAGE_BASE_URL, "").strip()
        storage_base_url = _normalize_base_url(storage_override or preset.storage_base_url) + "/"

        web_override = resolved_environ.get(ENV_WEB_BASE_URL, "").strip()
        web_base_url = _normalize_base_url(web_override or preset.web_base_url)

    return RuntimeConfig(
        mode=mode,
        server_base_url=server_base_url,
        api_base_url=f"{server_base_url}/api/v1/",
        minecraft_api_base_url=f"{server_base_url}/minecraft-server-api/",
        storage_base_url=storage_base_url,
        web_base_url=web_base_url,
    )


RUNTIME: RuntimeConfig = load_runtime_config()
