"""Java runtime detection and Minecraft version requirements."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

from config import JAVA_BIN, BuildPaths


_JAVA_VERSION_RE = re.compile(r'version\s+"([^"]+)"')


def parse_java_major(version_str: str) -> int | None:
    token = version_str.strip()
    if not token:
        return None
    if token.startswith("1."):
        parts = token.split(".")
        return int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else None
    match = re.match(r"(\d+)", token)
    return int(match.group(1)) if match else None


def detect_java_major(java_cmd: str) -> int | None:
    try:
        proc = subprocess.run(
            [java_cmd, "-version"],
            capture_output=True,
            text=True,
            timeout=6,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        return None

    raw = ((proc.stderr or "") + "\n" + (proc.stdout or "")).strip()
    match = _JAVA_VERSION_RE.search(raw)
    return parse_java_major(match.group(1)) if match else None


def read_required_java_major(version_json: Path) -> int | None:
    try:
        version = json.loads(version_json.read_text(encoding="utf-8-sig"))
    except Exception:
        return None

    raw_major = version.get("javaVersion", {}).get("majorVersion")
    try:
        return int(float(raw_major))
    except (TypeError, ValueError):
        return None


def select_java_binary(paths: BuildPaths, version_json: Path) -> tuple[str | None, int | None, int | None, list[tuple[str, int]]]:
    """Return selected Java command, its major, required major, and incompatible candidates."""
    required_major = read_required_java_major(version_json)
    candidates: list[str] = []
    if paths.java_bin.exists():
        candidates.append(str(paths.java_bin))
    if JAVA_BIN.exists():
        candidates.append(str(JAVA_BIN))
    candidates.append("java")

    incompatible: list[tuple[str, int]] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = os.path.normcase(candidate)
        if key in seen:
            continue
        seen.add(key)

        major = detect_java_major(candidate)
        if major is None:
            continue
        if required_major is None or major >= required_major:
            return candidate, major, required_major, incompatible
        incompatible.append((candidate, major))

    return None, None, required_major, incompatible
