"""Client for the backend launcher bootstrap endpoint."""

from __future__ import annotations

import asyncio
import json
import re
import urllib.error
import urllib.request
from typing import Any, TypedDict
from urllib.parse import urlparse

from config import (
    BOOTSTRAP_TIMEOUT_SEC,
    CURRENT_ACCOUNT_URL,
    AUTH_TIMEOUT_SEC,
    LAUNCHER_BOOTSTRAP_URL,
    RUNTIME,
    USER_AGENT,
    apply_backend_builds,
)


class CurrentAccountPreview(TypedDict):
    """Launcher-facing subset of the canonical backend account contract."""

    username: str
    role: str
    role_label: str
    ring_color: str
    avatar_url: str


DEFAULT_RING_COLOR = "#aab1c2"


def normalize_ring_color(value: Any, default: str = DEFAULT_RING_COLOR) -> str:
    """Accept only canonical six-digit hex colors from account presentation data."""
    candidate = str(value or "").strip().lower()
    return candidate if re.fullmatch(r"#[0-9a-f]{6}", candidate) else default


def _get_json(
    url: str, timeout: float, headers: dict[str, str] | None = None
) -> dict[str, Any]:
    request_headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    request_headers.update(headers or {})
    request = urllib.request.Request(
        url,
        headers=request_headers,
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        parsed = json.loads(response.read())
        return parsed if isinstance(parsed, dict) else {}


def fetch_bootstrap(timeout: float = BOOTSTRAP_TIMEOUT_SEC) -> dict[str, Any]:
    """Fetch aggregated launcher state from the backend.

    Returns ``{"success": False, "error": ...}`` when the backend is
    unreachable so callers can fall back to local build profiles.
    """
    try:
        payload = _get_json(LAUNCHER_BOOTSTRAP_URL, timeout)
    except urllib.error.HTTPError as exc:
        return {"success": False, "error": f"HTTP {exc.code}"}
    except Exception:
        return {"success": False, "error": "Backend недоступен"}
    return {"success": True, **payload}


async def fetch_bootstrap_async(
    timeout: float = BOOTSTRAP_TIMEOUT_SEC,
) -> dict[str, Any]:
    return await asyncio.to_thread(fetch_bootstrap, timeout)


def _rebase_storage_url_for_dev(url: str) -> str:
    """Use launcher-local storage origin while running against the dev backend."""
    if not url or not RUNTIME.is_dev:
        return url
    path = urlparse(url).path.strip("/")
    return RUNTIME.storage_url(path) if path else url


def normalize_current_account(payload: dict[str, Any]) -> CurrentAccountPreview:
    """Extract the stable launcher profile fields from the shared `/me` payload."""
    role = payload.get("role") if isinstance(payload.get("role"), dict) else {}
    avatar = payload.get("avatar") if isinstance(payload.get("avatar"), dict) else {}
    role_code = str(role.get("code") or "default").strip() or "default"
    role_title = str(role.get("title") or "Common").strip() or "Common"
    avatar_url = _rebase_storage_url_for_dev(str(avatar.get("url") or "").strip())
    return {
        "username": str(payload.get("login") or "").strip(),
        "role": role_code,
        "role_label": role_title,
        "ring_color": normalize_ring_color(role.get("ring_color")),
        "avatar_url": avatar_url,
    }


def fetch_current_account(
    access_token: str, timeout: float = AUTH_TIMEOUT_SEC
) -> dict[str, Any]:
    """Fetch the canonical account projection with a browser or game access token."""
    token = str(access_token or "").strip()
    if not token:
        return {"success": False, "error": "Пустой access token"}
    try:
        payload = _get_json(
            CURRENT_ACCOUNT_URL,
            timeout,
            headers={"Authorization": f"Bearer {token}"},
        )
    except urllib.error.HTTPError as exc:
        return {"success": False, "error": f"HTTP {exc.code}"}
    except Exception:
        return {"success": False, "error": "Не удалось загрузить профиль"}
    return {"success": True, "account": payload, **normalize_current_account(payload)}


def apply_bootstrap(payload: dict[str, Any]) -> bool:
    """Apply the backend build catalog to the local profile registry."""
    builds = payload.get("builds")
    if not isinstance(builds, list):
        return False
    return apply_backend_builds(builds, str(payload.get("default_build_id") or ""))
