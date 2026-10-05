"""Global (build-independent) user preferences.

Per-build settings such as RAM live in ``core.settings`` inside the build
folder. Preferences that must survive build deletion are stored here, in the
launcher data directory.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from .paths import LAUNCHER_DATA_DIR


USER_PREFS_FILE: Path = LAUNCHER_DATA_DIR / "launcher_prefs.json"

# `_cache` is only ever read or written while holding `_lock` (it is populated
# lazily on first read, which is a write). `_read_raw`/`_write_raw` assume the
# caller already holds `_lock`; public getters/setters take it.
_lock = threading.Lock()
_cache: dict[str, Any] | None = None


def _read_raw(prefs_file: Path = USER_PREFS_FILE) -> dict[str, Any]:
    """Return cached prefs, loading from disk on first use. Caller holds `_lock`."""
    global _cache
    if _cache is not None:
        return _cache
    try:
        raw = json.loads(prefs_file.read_text(encoding="utf-8"))
        _cache = raw if isinstance(raw, dict) else {}
    except Exception:
        _cache = {}
    return _cache


def _write_raw(data: dict[str, Any], prefs_file: Path = USER_PREFS_FILE) -> bool:
    """Persist prefs and refresh the cache. Caller holds `_lock`."""
    global _cache
    try:
        prefs_file.parent.mkdir(parents=True, exist_ok=True)
        prefs_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        _cache = dict(data)
        return True
    except Exception:
        _cache = None
        return False


def get_last_build_id() -> str:
    """Return the last selected build id, or empty when never selected."""
    with _lock:
        return str(_read_raw().get("last_build_id") or "").strip().lower()


def set_last_build_id(build_id: str) -> bool:
    """Persist the last selected build id."""
    with _lock:
        data = dict(_read_raw())
        cleaned = str(build_id or "").strip().lower()
        if cleaned:
            data["last_build_id"] = cleaned
        else:
            data.pop("last_build_id", None)
        return _write_raw(data)
