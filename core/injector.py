"""authlib-injector JVM argument helper.

The launcher uses authlib-injector as a client-side Java agent so Minecraft
authenticates against the AiNoCraft Yggdrasil-compatible API. The API base
URL comes from the central config layer (dev/prod aware). The jar-location and
API-base env overrides apply to source runs only; packaged (frozen) builds
ignore them so a tampered environment cannot redirect the game's auth.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from config import AUTHLIB_INJECTOR_API_BASE_URL, LAUNCHER_DATA_DIR, LAUNCHER_DIR


AUTHLIB_INJECTOR_JAR_NAME = "authlib-injector-1.2.7.jar"
AUTHLIB_INJECTOR_JAR_ENV = "AINOCRAFT_AUTHLIB_INJECTOR_JAR"
AUTHLIB_INJECTOR_API_BASE_ENV = "AINOCRAFT_AUTHLIB_INJECTOR_API_BASE_URL"


def resolve_authlib_api_base_url() -> str | None:
    """Return the API root used after the ``=`` in the javaagent argument."""
    if not getattr(sys, "frozen", False):
        explicit = str(os.environ.get(AUTHLIB_INJECTOR_API_BASE_ENV, "")).strip()
        if explicit:
            return explicit.rstrip("/") + "/"
    return AUTHLIB_INJECTOR_API_BASE_URL


def _path_is_under(path: Path, root: Path) -> bool:
    try:
        resolved_path = path.resolve()
        resolved_root = root.resolve()
    except Exception:
        resolved_path = path
        resolved_root = root
    return resolved_path == resolved_root or resolved_root in resolved_path.parents


def _running_exe_dir() -> Path:
    if getattr(sys, "frozen", False):
        try:
            return Path(sys.executable).resolve().parent
        except Exception:
            pass
    return LAUNCHER_DIR


def _meipass_dir() -> Path | None:
    value = str(getattr(sys, "_MEIPASS", "")).strip()
    if not value:
        return None
    try:
        return Path(value).resolve()
    except Exception:
        return Path(value)


def _is_meipass_path(path: Path) -> bool:
    mei_root = _meipass_dir()
    if mei_root and _path_is_under(path, mei_root):
        return True
    return any(part.upper().startswith("_MEI") for part in path.parts)


def _materialize_injector_from_meipass(source: Path) -> Path:
    """Copy the bundled jar out of PyInstaller's temp dir before Java opens it."""
    target = (LAUNCHER_DATA_DIR / "injector" / AUTHLIB_INJECTOR_JAR_NAME).resolve()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or target.stat().st_size != source.stat().st_size:
            shutil.copy2(source, target)
        return target
    except Exception:
        return source


def resolve_authlib_injector_jar(configured_path: str | Path | None = None) -> Path:
    """Find authlib-injector, preferring configured, appdata, then bundled copies."""
    env_jar = "" if getattr(sys, "frozen", False) else os.environ.get(AUTHLIB_INJECTOR_JAR_ENV, "")
    configured = str(configured_path or env_jar).strip()
    candidates: list[Path] = []
    base_dir = _running_exe_dir()
    appdata_injector = (LAUNCHER_DATA_DIR / "injector" / AUTHLIB_INJECTOR_JAR_NAME).resolve()

    if configured:
        custom_path = Path(configured)
        if not custom_path.is_absolute():
            custom_path = (base_dir / custom_path).resolve()
        candidates.append(custom_path)

    candidates.append(appdata_injector)
    candidates.append((base_dir / AUTHLIB_INJECTOR_JAR_NAME).resolve())
    candidates.append((base_dir / "injector" / AUTHLIB_INJECTOR_JAR_NAME).resolve())
    candidates.append((LAUNCHER_DIR / AUTHLIB_INJECTOR_JAR_NAME).resolve())
    candidates.append((LAUNCHER_DIR / "injector" / AUTHLIB_INJECTOR_JAR_NAME).resolve())

    meipass = _meipass_dir()
    if meipass:
        candidates.append((meipass / AUTHLIB_INJECTOR_JAR_NAME).resolve())
        candidates.append((meipass / "injector" / AUTHLIB_INJECTOR_JAR_NAME).resolve())

    unique_candidates: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate).lower()
        if key in seen:
            continue
        seen.add(key)
        unique_candidates.append(candidate)

    for candidate in unique_candidates:
        if candidate.exists():
            if _is_meipass_path(candidate):
                return _materialize_injector_from_meipass(candidate)
            return candidate

    return unique_candidates[0] if unique_candidates else (base_dir / AUTHLIB_INJECTOR_JAR_NAME).resolve()


def has_authlib_javaagent(jvm_args: list[str]) -> bool:
    """Check whether JVM args already include authlib-injector."""
    for arg in jvm_args:
        normalized = str(arg).lower()
        if normalized.startswith("-javaagent:") and "authlib-injector" in normalized:
            return True
    return False


def build_authlib_javaagent_arg(
    api_base_url: str | None = None,
    jar_path: str | Path | None = None,
) -> str:
    """Build ``-javaagent:<jar>=<api>`` and fail clearly when the jar is missing."""
    resolved_api_base_url = (api_base_url or resolve_authlib_api_base_url() or "").strip()
    if not resolved_api_base_url:
        raise ValueError("authlib-injector API base URL is not configured")

    injector_jar = resolve_authlib_injector_jar(jar_path)
    if not injector_jar.exists():
        raise FileNotFoundError(
            "authlib-injector jar was not found:\n"
            f"{injector_jar}\n\n"
            "Put the jar in the launcher root, in injector/, or set "
            f"{AUTHLIB_INJECTOR_JAR_ENV}."
        )

    return f"-javaagent:{injector_jar}={resolved_api_base_url.rstrip('/')}/"


def add_authlib_javaagent(
    jvm_args: list[str],
    api_base_url: str | None = None,
    jar_path: str | Path | None = None,
) -> list[str]:
    """Prepend authlib-injector javaagent unless it is already present."""
    if has_authlib_javaagent(jvm_args):
        return list(jvm_args)
    return [build_authlib_javaagent_arg(api_base_url, jar_path)] + list(jvm_args)


def add_authlib_javaagent_for_token(
    jvm_args: list[str],
    access_token: str | None,
    api_base_url: str | None = None,
    jar_path: str | Path | None = None,
) -> list[str]:
    """Inject only for authenticated launches."""
    if not access_token:
        return list(jvm_args)
    return add_authlib_javaagent(jvm_args, api_base_url, jar_path)
