"""Remote MinIO manifest for build revisions and archive URLs."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from config import (
    BOOTSTRAP_TIMEOUT_SEC,
    BUILDS_MANIFEST_URL,
    USER_AGENT,
    apply_build_manifest,
)


def fetch_and_apply(timeout: float = BOOTSTRAP_TIMEOUT_SEC) -> dict[str, Any]:
    """Fetch ``downloads/builds.json`` and merge it into build profiles."""
    request = urllib.request.Request(
        BUILDS_MANIFEST_URL,
        headers={
            "Accept": "application/json",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "User-Agent": USER_AGENT,
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return {"success": False, "error": f"HTTP {exc.code}"}
    except Exception:
        return {"success": False, "error": "Manifest сборок недоступен"}

    if not isinstance(payload, dict):
        return {"success": False, "error": "Некорректный manifest сборок"}

    applied = apply_build_manifest(payload)
    if applied <= 0:
        return {"success": False, "error": "Manifest не содержит известных сборок"}
    return {"success": True, "applied": applied, "format": payload.get("format")}
