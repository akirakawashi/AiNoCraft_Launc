"""Minecraft command construction and process launch."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import threading
import traceback
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, BinaryIO, Callable

from config import (
    ASSETS_INDEX,
    DEFAULT_ACCESS_TOKEN,
    DEFAULT_CLIENT_ID,
    JAVA_BIN,
    LAUNCHER_NAME,
    LAUNCHER_VERSION,
    BuildPaths,
    get_build_paths,
    resolve_client_files,
)
from core.custom_skin_loader import ensure_custom_skin_loader_config
from core.injector import add_authlib_javaagent_for_token
from core.java import select_java_binary
from core.system_info import ram_limits
from core.win_env import sanitize_child_env


_process: subprocess.Popen[Any] | None = None

_GAME_LOG_MAX_BYTES = 10 * 1024 * 1024
_GAME_LOG_BACKUPS = 3


def _game_log_path(paths: BuildPaths) -> Path:
    """Return the console log stored inside the selected game instance."""
    return paths.game_dir / "logs" / "launcher-game.log"


def _rotate_game_log(log_path: Path) -> None:
    """Keep a few previous console logs without letting them grow forever."""
    try:
        if not log_path.exists() or log_path.stat().st_size < _GAME_LOG_MAX_BYTES:
            return

        oldest = log_path.with_name(f"{log_path.name}.{_GAME_LOG_BACKUPS}")
        if oldest.exists():
            oldest.unlink()
        for index in range(_GAME_LOG_BACKUPS - 1, 0, -1):
            source = log_path.with_name(f"{log_path.name}.{index}")
            if source.exists():
                source.replace(log_path.with_name(f"{log_path.name}.{index + 1}"))
        log_path.replace(log_path.with_name(f"{log_path.name}.1"))
    except OSError:
        # A previous JVM may still have the file open. Appending is safer than
        # failing the next game launch merely because rotation was unavailable.
        pass


def _open_game_log(paths: BuildPaths, java_bin: Path, ram: int) -> tuple[Path, BinaryIO]:
    log_path = _game_log_path(paths)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    _rotate_game_log(log_path)
    stream = log_path.open("ab")
    started_at = datetime.now().astimezone().isoformat(timespec="seconds")
    header = (
        f"\n{'=' * 80}\n"
        f"[{started_at}] AiNoCraft game launch\n"
        f"Build: {paths.build_id} ({paths.build_name})\n"
        f"Java: {java_bin}\n"
        f"RAM: {ram} GiB\n"
        f"Working directory: {paths.version_dir}\n"
        "Java stdout/stderr:\n"
    )
    stream.write(header.encode("utf-8", errors="replace"))
    stream.flush()
    return log_path, stream


def _append_game_log(log_path: Path, message: str) -> None:
    try:
        with log_path.open("ab") as stream:
            stream.write(message.encode("utf-8", errors="replace"))
    except OSError:
        pass


def is_running() -> bool:
    return _process is not None and _process.poll() is None


def get_pid() -> int | None:
    return _process.pid if is_running() else None


def _maven_to_path(name: str, libraries_dir: Path) -> Path | None:
    parts = name.split(":")
    if len(parts) < 3:
        return None
    group, artifact, version = parts[0], parts[1], parts[2]
    classifier = parts[3] if len(parts) >= 4 else None
    jar = f"{artifact}-{version}-{classifier}.jar" if classifier else f"{artifact}-{version}.jar"
    return libraries_dir / group.replace(".", "/") / artifact / version / jar


def _rules_match(rules: list[Any], features: dict[str, bool]) -> bool:
    if not rules:
        return True
    result = False
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        action = rule.get("action") == "allow"
        os_rule = rule.get("os")
        feat_rule = rule.get("features")
        if isinstance(os_rule, dict):
            os_name = os_rule.get("name", "")
            if os_name and os_name != "windows":
                continue
        if isinstance(feat_rule, dict) and not all(features.get(key, False) == value for key, value in feat_rule.items()):
            continue
        result = action
    return result


def _subst(value: str, variables: dict[str, str]) -> str:
    for key, replacement in variables.items():
        value = value.replace("${" + key + "}", replacement)
    return value


def _resolve_args(raw: list[Any], variables: dict[str, str], features: dict[str, bool]) -> list[str]:
    result: list[str] = []
    for entry in raw:
        if isinstance(entry, str):
            result.append(_subst(entry, variables))
        elif isinstance(entry, dict) and _rules_match(entry.get("rules", []), features):
            values = entry.get("values", [])
            if isinstance(values, str):
                values = [values]
            for value in values:
                result.append(_subst(str(value), variables))
    return result


def _build_classpath(version: dict[str, Any], paths: BuildPaths, client_jar: Path) -> str:
    parts: list[str] = []
    for lib in version.get("libraries", []):
        if not isinstance(lib, dict) or not _rules_match(lib.get("rules", []), {}):
            continue
        artifact = lib.get("downloads", {}).get("artifact", {}) if isinstance(lib.get("downloads"), dict) else {}
        rel_path = artifact.get("path", "") if isinstance(artifact, dict) else ""
        candidate = paths.libraries_dir / rel_path if rel_path else _maven_to_path(str(lib.get("name", "")), paths.libraries_dir)
        if candidate and candidate.exists():
            parts.append(str(candidate))
    parts.append(str(client_jar))
    return os.pathsep.join(parts)


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
    version = json.loads(version_json.read_text(encoding="utf-8-sig"))
    classpath = _build_classpath(version, paths, client_jar)
    version_id = str(version.get("id") or effective_version_name)
    assets_index_name = str(version.get("assets") or ASSETS_INDEX)

    resolved_auth_uuid = str(auth_uuid or "").strip().replace("-", "")
    if access_token and not resolved_auth_uuid:
        raise ValueError("Сервер авторизации не вернул UUID профиля. Для online-mode вход невозможен.")
    if not resolved_auth_uuid:
        resolved_auth_uuid = str(uuid.uuid4()).replace("-", "")

    variables = {
        "natives_directory": str(paths.natives_dir),
        "launcher_name": LAUNCHER_NAME,
        "launcher_version": LAUNCHER_VERSION,
        "classpath": classpath,
        "library_directory": str(paths.libraries_dir),
        "classpath_separator": os.pathsep,
        "version_name": effective_version_name,
        "version_id": version_id,
        "auth_player_name": username,
        "game_directory": str(paths.version_dir),
        "assets_root": str(paths.assets_dir),
        "assets_index_name": assets_index_name,
        "auth_uuid": resolved_auth_uuid,
        # Accepted risk (S3): Minecraft receives the access token via
        # --accessToken on the command line, so other local processes can read
        # it (e.g. Win32_Process.CommandLine). This is inherent to vanilla
        # Minecraft and matches the official launcher; only a short-lived
        # session token is exposed locally — never the password or refresh
        # token. See LAUNCHER_SECURITY_REVIEW.md.
        "auth_access_token": access_token or DEFAULT_ACCESS_TOKEN,
        "clientid": client_id or DEFAULT_CLIENT_ID,
        "auth_xuid": "",
        "user_type": user_type or "mojang",
        "version_type": "release",
    }

    main_class = str(version.get("mainClass") or "cpw.mods.bootstraplauncher.BootstrapLauncher")
    arguments = version.get("arguments")
    if isinstance(arguments, dict):
        jvm_args = _resolve_args(arguments.get("jvm", []), variables, {})
        game_args = _resolve_args(arguments.get("game", []), variables, {})
    else:
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

    if "-cp" not in jvm_args and "--class-path" not in jvm_args:
        jvm_args += ["-cp", classpath]

    # On some Windows machines the JVM's IPv6 socket options are blocked (by AV/firewall
    # software), so connecting to "localhost" - which resolves to ::1 before 127.0.0.1 -
    # fails with "Permission denied: getsockopt" even though IPv4 works fine. Forcing the
    # IPv4 stack sidesteps this; it's a safe default for a server that doesn't need IPv6.
    if "-Djava.net.preferIPv4Stack=true" not in jvm_args:
        jvm_args = ["-Djava.net.preferIPv4Stack=true"] + jvm_args

    jvm_args = add_authlib_javaagent_for_token(jvm_args, access_token)
    return [str(java_bin), f"-Xmx{ram}G", f"-Xms{max(1, ram // 2)}G"] + jvm_args + [main_class] + game_args


def launch(
    build_id: str,
    username: str,
    ram: int,
    access_token: str | None = None,
    auth_uuid: str | None = None,
    client_id: str | None = None,
    user_type: str = "mojang",
    on_exit: Callable[[int], None] | None = None,
) -> dict[str, Any]:
    global _process

    if is_running():
        return {"success": False, "error": "Игра уже запущена"}

    limits = ram_limits()
    try:
        resolved_ram = max(limits["ram_min_gb"], min(limits["ram_max_gb"], int(ram)))
    except (TypeError, ValueError):
        resolved_ram = limits["ram_min_gb"]

    try:
        paths = get_build_paths(build_id)
    except ValueError as exc:
        return {"success": False, "error": str(exc)}

    version_json, client_jar, effective_version_name = resolve_client_files(paths)
    for path, label in ((client_jar, f"{effective_version_name}.jar"), (version_json, f"{effective_version_name}.json")):
        if not path.exists():
            return {"success": False, "error": f"{label} не найден:\n{path}"}

    java_bin, java_major, required_major, incompatible = select_java_binary(paths, version_json)
    if not java_bin:
        if required_major is not None:
            detail = ""
            if incompatible:
                versions = ", ".join(f"{cmd} (Java {major})" for cmd, major in incompatible)
                detail = f"\nНайдены только несовместимые Java: {versions}"
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
            "error": f"Для сборки {paths.build_name} требуется Java {required_major}+, но выбрана Java {java_major}: {java_bin}",
        }

    try:
        ensure_custom_skin_loader_config(paths.version_dir)
        cmd = _build_command(
            username,
            access_token,
            auth_uuid,
            client_id,
            user_type,
            resolved_ram,
            paths,
            java_bin,
            version_json,
            client_jar,
            effective_version_name,
        )
    except Exception as exc:
        return {"success": False, "error": str(exc)}

    game_log_path: Path | None = None
    game_log_stream: BinaryIO | None = None
    try:
        game_log_path, game_log_stream = _open_game_log(paths, Path(java_bin), resolved_ram)
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        launched_process = subprocess.Popen(
            cmd,
            cwd=str(paths.version_dir),
            stdout=game_log_stream,
            stderr=subprocess.STDOUT,
            creationflags=creationflags,
            close_fds=True,
            env=sanitize_child_env(os.environ),
        )
        _process = launched_process
    except Exception as exc:
        if game_log_stream is not None:
            game_log_stream.write(
                f"Launcher failed to start Java:\n{traceback.format_exc()}\n".encode(
                    "utf-8",
                    errors="replace",
                )
            )
            game_log_stream.flush()
        elif game_log_path is not None:
            _append_game_log(
                game_log_path,
                f"Launcher failed to start Java:\n{traceback.format_exc()}\n",
            )
        return {"success": False, "error": str(exc)}
    finally:
        if game_log_stream is not None:
            game_log_stream.close()

    def _watch(proc: subprocess.Popen[Any]) -> None:
        global _process
        try:
            rc = proc.wait()
        except Exception:
            if game_log_path is not None:
                _append_game_log(
                    game_log_path,
                    f"Launcher failed while waiting for Java:\n{traceback.format_exc()}\n",
                )
            return
        if _process is proc:
            _process = None
        if game_log_path is not None:
            finished_at = datetime.now().astimezone().isoformat(timespec="seconds")
            _append_game_log(
                game_log_path,
                f"\n[{finished_at}] Java process exited with code {rc}.\n",
            )
        if on_exit:
            on_exit(rc)

    threading.Thread(target=_watch, args=(launched_process,), daemon=True, name="minecraft-watch").start()
    return {"success": True, "pid": launched_process.pid}
