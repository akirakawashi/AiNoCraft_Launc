"""Per-build launcher settings storage."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config import get_build_paths
from core.system_info import ram_limits


def _resolve_settings_file(build_id: str | None = None, settings_file: Path | None = None) -> Path:
    return settings_file if settings_file is not None else get_build_paths(build_id).settings_file


def _normalize_ram(value: Any) -> int:
    limits = ram_limits()
    try:
        raw = int(value)
    except (TypeError, ValueError):
        raw = limits["ram_default_gb"]
    return max(limits["ram_min_gb"], min(limits["ram_max_gb"], raw))


def normalize(data: dict[str, Any] | None) -> dict[str, Any]:
    """Return validated settings while preserving unknown forward-compatible keys."""
    merged: dict[str, Any] = {"ram": ram_limits()["ram_default_gb"]}
    if isinstance(data, dict):
        merged.update(data)
    merged["ram"] = _normalize_ram(merged.get("ram"))
    return merged


def load(build_id: str | None = None, *, settings_file: Path | None = None) -> dict[str, Any]:
    try:
        resolved = _resolve_settings_file(build_id, settings_file)
        if resolved.exists():
            saved = json.loads(resolved.read_text(encoding="utf-8"))
            return normalize(saved if isinstance(saved, dict) else None)
    except Exception:
        pass
    return normalize(None)


def save(data: dict[str, Any], build_id: str | None = None, *, settings_file: Path | None = None) -> bool:
    try:
        resolved = _resolve_settings_file(build_id, settings_file)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(json.dumps(normalize(data), ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except Exception:
        return False
