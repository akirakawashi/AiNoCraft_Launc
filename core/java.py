"""
Java runtime detection and version parsing.

Used by :mod:`core.game` to find a suitable Java binary
before launching the game process.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

from config import JAVA_BIN, BuildPaths


_JAVA_VERSION_RE = re.compile(r'version\s+"([^"]+)"')


# ── Version parsing ──────────────────────────────────────────────────────────


def parse_java_major(version_str: str) -> int | None:
    """
    Extract the major version number from a Java version string.

    Examples::

        "1.8.0_362"  -> 8       (legacy format)
        "17.0.2"     -> 17      (modern format)
        "21"         -> 21
    """
    token = version_str.strip()
    if not token:
        return None

    # Legacy format: 1.8.0_xxx -> major is 8
    if token.startswith("1."):
        parts = token.split(".")
        if len(parts) >= 2 and parts[1].isdigit():
            return int(parts[1])
        return None

    # Modern format: 17.0.2 -> major is 17
    m = re.match(r"(\d+)", token)
    return int(m.group(1)) if m else None


# ── Runtime detection ────────────────────────────────────────────────────────


def detect_java_major(java_cmd: str) -> int | None:
    """Run ``java -version`` and return the major version, or *None* on failure."""
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
    if not raw:
        return None

    m = _JAVA_VERSION_RE.search(raw)
    if not m:
        return None

    return parse_java_major(m.group(1))


def read_required_java_major(version_json: Path) -> int | None:
    """Read the ``javaVersion.majorVersion`` field from a Minecraft version JSON."""
    try:
        with open(version_json, encoding="utf-8-sig") as f:
            version = json.load(f)
    except Exception:
        return None

    raw_major = version.get("javaVersion", {}).get("majorVersion")
    if raw_major is None:
        return None

    try:
        return int(float(raw_major))
    except (TypeError, ValueError):
        return None


def select_java_binary(
    paths: BuildPaths,
    version_json: Path,
) -> tuple[str | None, int | None, int | None, list[tuple[str, int]]]:
    """
    Find a suitable Java binary for the given build.

    Returns:
        ``(selected_cmd, selected_major, required_major, incompatible_candidates)``

    Search priority: build's own Java -> fallback :data:`JAVA_BIN` -> ``java`` in PATH.
    """
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
