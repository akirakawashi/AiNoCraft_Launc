"""
Запуск игры.

Читает JSON выбранной сборки, собирает classpath и команду Java,
после чего запускает процесс в отдельном потоке.

Java-детекция вынесена в :mod:`core.java`.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import threading
from pathlib import Path

from config import (
    ASSETS_INDEX,
    AUTHLIB_INJECTOR_API_BASE_URL,
    AUTHLIB_INJECTOR_JAR_NAME,
    AUTHLIB_INJECTOR_JAR_PATH,
    DEFAULT_ACCESS_TOKEN,
    DEFAULT_CLIENT_ID,
    JAVA_BIN,
    LAUNCHER_DATA_DIR,
    LAUNCHER_DIR,
    LAUNCHER_NAME,
    LAUNCHER_VERSION,
    RAM_MAX_GB,
    RAM_MIN_GB,
    BuildPaths,
    get_build_paths,
    resolve_client_files,
)
from core.java import select_java_binary


# Глобальный процесс игры (один инстанс одновременно)
_process: subprocess.Popen | None = None


def is_running() -> bool:
    return _process is not None and _process.poll() is None


def get_pid() -> int | None:
    return _process.pid if is_running() else None


def _sanitize_child_env(env: dict[str, str]) -> dict[str, str]:
    """
    Remove PyInstaller/Python runtime variables before launching javaw.
    This helps avoid leaking launcher onefile context into child process.
    """
    clean = dict(env)
    prefixes = ("PYTHONNET", "_PYI", "PYI_", "PYINSTALLER", "_MEI")
    exact = {"PYTHONHOME", "PYTHONPATH"}

    for key in list(clean.keys()):
        upper = key.upper()
        if upper in exact or any(upper.startswith(prefix) for prefix in prefixes):
            clean.pop(key, None)

    path_keys = [key for key in clean.keys() if key.upper() == "PATH"]
    for path_key in path_keys:
        kept_parts: list[str] = []
        for part in clean[path_key].split(os.pathsep):
            if not part:
                continue
            if "_MEI" in part.upper():
                continue
            kept_parts.append(part)
        clean[path_key] = os.pathsep.join(kept_parts)

    return clean


# ── Сборка classpath ───────────────────────────────────────────────────────────

def _maven_to_path(name: str, libraries_dir: Path) -> Path | None:
    """Конвертирует Maven-координату group:artifact:version[:classifier] в путь jars."""
    parts = name.split(":")
    if len(parts) < 3:
        return None

    group, artifact, version = parts[0], parts[1], parts[2]
    classifier = parts[3] if len(parts) >= 4 else None
    jar = f"{artifact}-{version}-{classifier}.jar" if classifier else f"{artifact}-{version}.jar"
    return libraries_dir / group.replace(".", "/") / artifact / version / jar


def _rules_match(rules: list, features: dict) -> bool:
    """Проверяет rules-блок из version JSON (Windows)."""
    if not rules:
        return True

    result = False
    for rule in rules:
        action = rule.get("action") == "allow"
        os_rule = rule.get("os")
        feat_rule = rule.get("features")

        if os_rule:
            os_name = os_rule.get("name", "")
            if os_name and os_name != "windows":
                continue

        if feat_rule:
            if not all(features.get(k, False) == v for k, v in feat_rule.items()):
                continue

        result = action

    return result


def _subst(s: str, variables: dict) -> str:
    for k, v in variables.items():
        s = s.replace("${" + k + "}", v)
    return s


def _resolve_args(raw: list, variables: dict, features: dict) -> list[str]:
    """Разворачивает условный список аргументов из version JSON в плоский список строк."""
    out: list[str] = []
    for entry in raw:
        if isinstance(entry, str):
            out.append(_subst(entry, variables))
        elif isinstance(entry, dict):
            if _rules_match(entry.get("rules", []), features):
                for v in entry.get("values", []):
                    out.append(_subst(str(v), variables))
    return out


def _build_classpath(version: dict, paths: BuildPaths, client_jar: Path) -> str:
    parts: list[str] = []

    for lib in version.get("libraries", []):
        if not _rules_match(lib.get("rules", []), {}):
            continue

        artifact = lib.get("downloads", {}).get("artifact", {})
        rel_path = artifact.get("path", "")
        p = (paths.libraries_dir / rel_path) if rel_path else _maven_to_path(lib.get("name", ""), paths.libraries_dir)

        if p and p.exists():
            parts.append(str(p))

    parts.append(str(client_jar))
    return os.pathsep.join(parts)


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
    # Fallback: some environments may not expose _MEIPASS reliably.
    return any(part.upper().startswith("_MEI") for part in path.parts)


def _materialize_injector_from_meipass(source: Path) -> Path:
    """
    When running as onefile (.exe), avoid referencing javaagent jar from _MEI.
    Java keeps this jar open, which can block _MEI cleanup on launcher exit.
    """
    target = (LAUNCHER_DATA_DIR / "injector" / AUTHLIB_INJECTOR_JAR_NAME).resolve()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or target.stat().st_size != source.stat().st_size:
            shutil.copy2(source, target)
        return target
    except Exception:
        return source


def _resolve_authlib_injector_jar() -> Path:
    configured = str(AUTHLIB_INJECTOR_JAR_PATH or "").strip()
    candidates: list[Path] = []
    base_dir = _running_exe_dir()
    appdata_injector = (LAUNCHER_DATA_DIR / "injector" / AUTHLIB_INJECTOR_JAR_NAME).resolve()

    if configured:
        configured_path = Path(configured)
        if not configured_path.is_absolute():
            configured_path = (base_dir / configured_path).resolve()
        candidates.append(configured_path)

    # Prefer persistent location first (safe for onefile cleanup).
    candidates.append(appdata_injector)
    candidates.append((base_dir / AUTHLIB_INJECTOR_JAR_NAME).resolve())
    candidates.append((base_dir / "injector" / AUTHLIB_INJECTOR_JAR_NAME).resolve())

    # Keep LAUNCHER_DIR fallback for source runs or non-standard layouts.
    candidates.append((LAUNCHER_DIR / AUTHLIB_INJECTOR_JAR_NAME).resolve())
    candidates.append((LAUNCHER_DIR / "injector" / AUTHLIB_INJECTOR_JAR_NAME).resolve())

    meipass = str(getattr(sys, "_MEIPASS", "")).strip()
    if meipass:
        candidates.append((Path(meipass) / AUTHLIB_INJECTOR_JAR_NAME).resolve())
        candidates.append((Path(meipass) / "injector" / AUTHLIB_INJECTOR_JAR_NAME).resolve())

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


def _has_authlib_javaagent(jvm_args: list[str]) -> bool:
    for arg in jvm_args:
        normalized = str(arg).lower()
        if normalized.startswith("-javaagent:") and "authlib-injector" in normalized:
            return True
    return False


def _build_command(
    username: str,
    access_token: str | None,
    auth_uuid: str | None,
    client_id: str | None,
    user_type: str,
    ram: int,
    paths: BuildPaths,
    java_bin: str | Path,
    version_json: Path,
    client_jar: Path,
    effective_version_name: str,
) -> list[str]:
    import uuid as _uuid

    with open(version_json, encoding="utf-8-sig") as f:
        version = json.load(f)

    classpath = _build_classpath(version, paths, client_jar)
    version_id = str(version.get("id") or effective_version_name)
    # Делаем version_name равным stem JSON/JAR, чтобы ${version_name}.jar совпадал с реальным файлом.
    version_name_for_args = effective_version_name
    assets_index_name = str(version.get("assets") or ASSETS_INDEX)
    resolved_auth_uuid = str(auth_uuid or "").strip().replace("-", "")
    if access_token and not resolved_auth_uuid:
        raise ValueError(
            "Сервер авторизации не вернул UUID профиля (selectedProfile.id). "
            "Для online-mode сервера вход невозможен."
        )
    if not resolved_auth_uuid:
        resolved_auth_uuid = str(_uuid.uuid4()).replace("-", "")

    variables = {
        "natives_directory": str(paths.natives_dir),
        "launcher_name": LAUNCHER_NAME,
        "launcher_version": LAUNCHER_VERSION,
        "classpath": classpath,
        "library_directory": str(paths.libraries_dir),
        "classpath_separator": os.pathsep,
        "version_name": version_name_for_args,
        "version_id": version_id,
        "auth_player_name": username,
        "game_directory": str(paths.version_dir),
        "assets_root": str(paths.assets_dir),
        "assets_index_name": assets_index_name,
        "auth_uuid": resolved_auth_uuid,
        "auth_access_token": access_token or DEFAULT_ACCESS_TOKEN,
        "clientid": client_id or DEFAULT_CLIENT_ID,
        "auth_xuid": "",
        "user_type": user_type or "mojang",
        "version_type": "release",
    }

    main_class = version.get("mainClass", "cpw.mods.bootstraplauncher.BootstrapLauncher")
    arguments = version.get("arguments")

    if isinstance(arguments, dict):
        jvm_args = _resolve_args(arguments.get("jvm", []), variables, {})
        game_args = _resolve_args(arguments.get("game", []), variables, {})
    else:
        # Legacy JSON (например 1.7.10): нет блока arguments, используется minecraftArguments.
        raw_legacy_game_args = str(version.get("minecraftArguments", "")).strip()
        try:
            legacy_game_parts = shlex.split(raw_legacy_game_args, posix=False) if raw_legacy_game_args else []
        except ValueError:
            legacy_game_parts = raw_legacy_game_args.split() if raw_legacy_game_args else []

        game_args = [_subst(arg, variables) for arg in legacy_game_parts]
        jvm_args = [
            f"-Djava.library.path={paths.natives_dir}",
            "-Dfml.ignoreInvalidMinecraftCertificates=true",
            "-Dfml.ignorePatchDiscrepancies=true",
            "-cp",
            classpath,
        ]

    # Если в modern arguments classpath не задан, добавляем fallback.
    if "-cp" not in jvm_args and "--class-path" not in jvm_args:
        jvm_args += ["-cp", classpath]

    if access_token and AUTHLIB_INJECTOR_API_BASE_URL and not _has_authlib_javaagent(jvm_args):
        injector_jar = _resolve_authlib_injector_jar()
        if not injector_jar.exists():
            raise FileNotFoundError(
                "Не найден authlib-injector jar:\n"
                f"{injector_jar}\n\n"
                "Положите jar в корень лаунчера или в папку injector/, "
                "или задайте "
                "AINOCRAFT_AUTHLIB_INJECTOR_JAR."
            )
        jvm_args = [f"-javaagent:{injector_jar}={AUTHLIB_INJECTOR_API_BASE_URL}"] + jvm_args

    return [str(java_bin), f"-Xmx{ram}G", f"-Xms{max(1, ram // 2)}G"] + jvm_args + [main_class] + game_args


# ── Запуск ─────────────────────────────────────────────────────────────────────

def launch(
    build_id: str,
    username: str,
    ram: int,
    access_token: str | None = None,
    auth_uuid: str | None = None,
    client_id: str | None = None,
    user_type: str = "mojang",
    on_exit=None,
) -> dict:
    """
    Запускает выбранную сборку.
    Возвращает {"success": True, "pid": int} или {"success": False, "error": str}.
    on_exit(return_code: int) вызывается когда игра закрывается.
    """
    global _process

    if is_running():
        return {"success": False, "error": "Игра уже запущена"}

    try:
        ram = max(RAM_MIN_GB, min(RAM_MAX_GB, int(ram)))
    except (TypeError, ValueError):
        ram = RAM_MIN_GB

    try:
        paths = get_build_paths(build_id)
    except ValueError as exc:
        return {"success": False, "error": str(exc)}

    version_json, client_jar, effective_version_name = resolve_client_files(paths)

    for path, label in [
        (client_jar, f"{effective_version_name}.jar"),
        (version_json, f"{effective_version_name}.json"),
    ]:
        if not path.exists():
            return {"success": False, "error": f"{label} не найден:\n{path}"}

    java_bin, java_major, required_major, incompatible = select_java_binary(paths, version_json)
    if not java_bin:
        if required_major is not None:
            if incompatible:
                versions = ", ".join(f"{cmd} (Java {major})" for cmd, major in incompatible)
                detail = f"\nНайдены только несовместимые Java: {versions}"
            else:
                detail = ""
            return {
                "success": False,
                "error": (
                    f"Для сборки {paths.build_name} требуется Java {required_major}+.\n"
                    f"Подходящая Java не найдена (приоритет: {paths.java_bin} -> {JAVA_BIN} -> PATH)."
                    f"{detail}"
                ),
            }
        return {"success": False, "error": "Java не найдена"}

    if java_major is not None and required_major is not None and java_major < required_major:
        return {
            "success": False,
            "error": (
                f"Для сборки {paths.build_name} требуется Java {required_major}+, "
                f"но выбрана Java {java_major}: {java_bin}"
            ),
        }

    try:
        cmd = _build_command(
            username,
            access_token,
            auth_uuid,
            client_id,
            user_type,
            ram,
            paths,
            java_bin,
            version_json,
            client_jar,
            effective_version_name,
        )
    except Exception as exc:
        return {"success": False, "error": str(exc)}


    child_env = _sanitize_child_env(os.environ)

    try:
        launched_process = subprocess.Popen(
            cmd,
            cwd=str(paths.version_dir),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
            close_fds=True,
            env=child_env,
        )
        _process = launched_process
    except Exception as exc:
        return {"success": False, "error": str(exc)}

    def _watch(proc: subprocess.Popen) -> None:
        global _process
        rc = proc.wait()
        if _process is proc:
            _process = None
        if on_exit:
            on_exit(rc)

    threading.Thread(target=_watch, args=(launched_process,), daemon=True).start()
    return {"success": True, "pid": launched_process.pid}
