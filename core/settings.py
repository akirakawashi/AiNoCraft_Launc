"""
Управление настройками лаунчера.

Настройки хранятся отдельно для каждой сборки:
<instance>/versions/<BuildName>/launcher_settings.json
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config import DEFAULT_SETTINGS, RAM_MAX_GB, RAM_MIN_GB, get_build_paths



def _resolve_settings_file(build_id: str | None = None, settings_file: Path | None = None) -> Path:
    if settings_file is not None:
        return settings_file
    return get_build_paths(build_id).settings_file


def _normalize_ram(value: Any) -> int:
    try:
        raw = int(value)
    except (TypeError, ValueError):
        raw = int(DEFAULT_SETTINGS.get("ram", RAM_MIN_GB))
    return max(RAM_MIN_GB, min(RAM_MAX_GB, raw))


def normalize(data: dict[str, Any] | None) -> dict[str, Any]:
    """
    Returns a validated settings dict.
    Unknown keys are preserved to keep forward compatibility.
    """
    merged = dict(DEFAULT_SETTINGS)
    if isinstance(data, dict):
        merged.update(data)

    merged["ram"] = _normalize_ram(merged.get("ram"))
    return merged


def load(build_id: str | None = None, *, settings_file: Path | None = None) -> dict[str, Any]:
    """Загружает настройки сборки. Возвращает DEFAULT_SETTINGS, если файла нет."""
    try:
        resolved = _resolve_settings_file(build_id, settings_file)
        if resolved.exists():
            with open(resolved, "r", encoding="utf-8") as f:
                saved = json.load(f)
            return normalize(saved)
    except Exception:
        pass
    return normalize(None)


def save(
    data: dict[str, Any],
    build_id: str | None = None,
    *,
    settings_file: Path | None = None,
) -> bool:
    """Сохраняет настройки сборки. Возвращает True при успехе."""
    try:
        resolved = _resolve_settings_file(build_id, settings_file)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        normalized = normalize(data)
        with open(resolved, "w", encoding="utf-8") as f:
            json.dump(normalized, f, indent=2, ensure_ascii=False)
        return True
    except Exception as exc:
        return False
