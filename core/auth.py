"""
Auth flow for launcher (authlib-injector compatible):
1) login via /authenticate
2) persist access/refresh/client tokens locally (Windows DPAPI)
3) restore session via /refresh between launcher restarts
4) validate access token via /validate
5) logout via /invalidate and clear local session
"""

from __future__ import annotations

import base64
import ctypes
import json
import os
import time
import urllib.error
import urllib.request
import uuid
from ctypes import wintypes
from pathlib import Path
from typing import Any

from config import (
    AUTH_AUTHENTICATE_URL,
    AUTH_INVALIDATE_URL,
    AUTH_REFRESH_URL,
    AUTH_TIMEOUT_SEC,
    AUTH_VALIDATE_URL,
    LAUNCHER_DATA_DIR,
    LAUNCHER_NAME,
    LAUNCHER_VERSION,
)

_ACCESS_TOKEN_REFRESH_LEEWAY_SEC = 45
_AUTH_SESSION_FILE: Path = LAUNCHER_DATA_DIR / "auth_session.json"
_USER_AGENT = f"{LAUNCHER_NAME}/{LAUNCHER_VERSION}"
_IS_WINDOWS = os.name == "nt"


if _IS_WINDOWS:
    _CRYPTPROTECT_UI_FORBIDDEN = 0x01
    _crypt32 = ctypes.windll.crypt32
    _kernel32 = ctypes.windll.kernel32
    _kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    _kernel32.LocalFree.restype = ctypes.c_void_p

    class _DATA_BLOB(ctypes.Structure):
        _fields_ = [
            ("cbData", wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_byte)),
        ]


def _blob_from_bytes(data: bytes) -> tuple[Any, Any]:
    raw = ctypes.create_string_buffer(data, len(data))
    blob = _DATA_BLOB(
        cbData=len(data),
        pbData=ctypes.cast(raw, ctypes.POINTER(ctypes.c_byte)),
    )
    return blob, raw


def _protect_bytes(data: bytes) -> bytes:
    if not data:
        return b""
    if not _IS_WINDOWS:
        return data

    in_blob, in_raw = _blob_from_bytes(data)
    out_blob = _DATA_BLOB()

    ok = _crypt32.CryptProtectData(
        ctypes.byref(in_blob),
        "AiNoCraft Launcher Refresh Token",
        None,
        None,
        None,
        _CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(out_blob),
    )
    if not ok:
        raise ctypes.WinError()

    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        _kernel32.LocalFree(ctypes.cast(out_blob.pbData, ctypes.c_void_p))


def _unprotect_bytes(data: bytes) -> bytes:
    if not data:
        return b""
    if not _IS_WINDOWS:
        return data

    in_blob, in_raw = _blob_from_bytes(data)
    out_blob = _DATA_BLOB()

    ok = _crypt32.CryptUnprotectData(
        ctypes.byref(in_blob),
        None,
        None,
        None,
        None,
        _CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(out_blob),
    )
    if not ok:
        raise ctypes.WinError()

    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        _kernel32.LocalFree(ctypes.cast(out_blob.pbData, ctypes.c_void_p))


def _read_session_file() -> dict[str, Any]:
    try:
        with open(_AUTH_SESSION_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_session_file(data: dict[str, Any]) -> None:
    _AUTH_SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_AUTH_SESSION_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _clear_session_file() -> None:
    try:
        _AUTH_SESSION_FILE.unlink()
    except FileNotFoundError:
        pass
    except Exception:
        pass


def _encode_secret(value: str | None) -> str | None:
    cleaned = str(value or "").strip()
    if not cleaned:
        return None
    encoded = _protect_bytes(cleaned.encode("utf-8"))
    return base64.b64encode(encoded).decode("ascii")


def _decode_secret(value: Any) -> str | None:
    if not value or not isinstance(value, str):
        return None
    try:
        protected = base64.b64decode(value.encode("ascii"))
        decoded = _unprotect_bytes(protected).decode("utf-8").strip()
        return decoded or None
    except Exception:
        return None


def _normalize_profile(profile: Any) -> dict[str, str] | None:
    if not isinstance(profile, dict):
        return None
    profile_id = str(profile.get("id") or "").strip()
    profile_name = str(profile.get("name") or "").strip()
    if not profile_id and not profile_name:
        return None
    return {
        "id": profile_id,
        "name": profile_name,
    }


def _normalize_user_properties(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    normalized: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        value = str(item.get("value") or "").strip()
        signature_raw = item.get("signature")
        signature = str(signature_raw).strip() if signature_raw is not None else ""
        if not name or not value:
            continue
        entry = {"name": name, "value": value}
        if signature:
            entry["signature"] = signature
        normalized.append(entry)
    return normalized


def _normalize_user_info(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    user_id = str(raw.get("id") or "").strip()
    properties = _normalize_user_properties(raw.get("properties"))
    if not user_id and not properties:
        return None
    return {"id": user_id, "properties": properties}


def _load_session() -> dict[str, Any]:
    raw = _read_session_file()
    session: dict[str, Any] = {
        "login": str(raw.get("login") or "").strip(),
        "updated_at": raw.get("updated_at"),
    }

    access_token = _decode_secret(raw.get("access_token"))
    refresh_token = _decode_secret(raw.get("refresh_token"))
    client_token = str(raw.get("client_token") or "").strip() or None
    selected_profile = _normalize_profile(raw.get("selected_profile"))
    user_info = _normalize_user_info(raw.get("user"))

    if access_token:
        session["access_token"] = access_token
    if refresh_token:
        session["refresh_token"] = refresh_token
    if client_token:
        session["client_token"] = client_token
    if selected_profile:
        session["selected_profile"] = selected_profile
    if user_info:
        session["user"] = user_info
    return session


def _save_full_session(
    login_value: str,
    access_token: str | None,
    refresh_token: str | None,
    client_token: str | None,
    selected_profile: dict[str, str] | None,
    user_info: dict[str, Any] | None,
) -> None:
    payload: dict[str, Any] = {
        "login": str(login_value).strip(),
        "updated_at": int(time.time()),
    }
    encoded_access = _encode_secret(access_token)
    encoded_refresh = _encode_secret(refresh_token)
    if encoded_access:
        payload["access_token"] = encoded_access
    if encoded_refresh:
        payload["refresh_token"] = encoded_refresh

    client = str(client_token or "").strip()
    if client:
        payload["client_token"] = client

    profile = _normalize_profile(selected_profile)
    if profile:
        payload["selected_profile"] = profile

    normalized_user = _normalize_user_info(user_info)
    if normalized_user:
        payload["user"] = normalized_user

    _write_session_file(payload)


def get_saved_login() -> str:
    session = _load_session()
    return str(session.get("login", "")).strip()


def is_access_token_expiring(expires_at: Any, leeway_sec: int = _ACCESS_TOKEN_REFRESH_LEEWAY_SEC) -> bool:
    if expires_at in (None, ""):
        return False
    try:
        exp_ts = int(expires_at)
    except (TypeError, ValueError):
        return True
    return int(time.time()) >= exp_ts - int(leeway_sec)


def _parse_http_error(exc: urllib.error.HTTPError) -> str:
    try:
        err_data: Any = json.loads(exc.read())
        if isinstance(err_data, dict):
            detail = err_data.get("detail")
            if isinstance(detail, list):
                return "; ".join(str(item) for item in detail) or f"HTTP {exc.code}"
            if detail:
                return str(detail)
            return str(
                err_data.get("errorMessage")
                or err_data.get("error")
                or err_data.get("message")
                or f"HTTP {exc.code}"
            )
        return f"HTTP {exc.code}"
    except Exception:
        return f"HTTP {exc.code}"


def _compact_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


def _post_json(
    url: str,
    payload: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], Any]:
    headers = {
        "Accept": "application/json",
        "User-Agent": _USER_AGENT,
        "Content-Type": "application/json",
    }

    data = json.dumps(payload or {}).encode("utf-8")

    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=AUTH_TIMEOUT_SEC) as resp:
        raw = resp.read()
        body: dict[str, Any]
        if raw:
            parsed = json.loads(raw)
            body = parsed if isinstance(parsed, dict) else {}
        else:
            body = {}
        return body, resp.headers


def _normalize_auth_response(
    body: dict[str, Any],
    fallback_login: str,
    fallback_client_token: str | None = None,
    fallback_selected_profile: dict[str, str] | None = None,
    fallback_refresh_token: str | None = None,
) -> dict[str, Any]:
    resolved_login = str(body.get("login") or body.get("username") or fallback_login).strip()
    access_token = str(body.get("accessToken") or body.get("access_token") or body.get("token") or "").strip()
    refresh_token = str(body.get("refreshToken") or body.get("refresh_token") or "").strip() or fallback_refresh_token
    client_token = str(body.get("clientToken") or body.get("client_token") or "").strip() or fallback_client_token

    available_profiles_raw = body.get("availableProfiles") or body.get("available_profiles")
    available_profiles: list[dict[str, str]] = []
    if isinstance(available_profiles_raw, list):
        for item in available_profiles_raw:
            normalized = _normalize_profile(item)
            if normalized:
                available_profiles.append(normalized)

    selected_profile = _normalize_profile(
        body.get("selectedProfile") or body.get("selected_profile") or fallback_selected_profile
    )
    if not selected_profile and available_profiles:
        selected_profile = available_profiles[0]

    user_info = _normalize_user_info(body.get("user"))
    expires_at = body.get("expires_at")

    if not access_token:
        return {"success": False, "error": "Сервер авторизации вернул пустой токен"}

    if not client_token:
        client_token = str(uuid.uuid4())

    if selected_profile:
        selected_name = str(selected_profile.get("name") or "").strip()
        if selected_name:
            resolved_login = selected_name

    return {
        "success": True,
        "username": resolved_login,
        "login": resolved_login,
        "token": access_token,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "client_token": client_token,
        "token_type": "Bearer",
        "expires_at": expires_at,
        "selected_profile_id": str(selected_profile.get("id") if selected_profile else ""),
        "selected_profile_name": str(selected_profile.get("name") if selected_profile else ""),
        "selected_profile": selected_profile,
        "available_profiles": available_profiles,
        "user": user_info,
        "user_type": "mojang",
    }


def _persist_auth_result(result: dict[str, Any], fallback_login: str = "") -> None:
    resolved_login = str(result.get("login") or result.get("username") or fallback_login).strip()
    _save_full_session(
        login_value=resolved_login,
        access_token=str(result.get("access_token") or result.get("token") or "").strip() or None,
        refresh_token=str(result.get("refresh_token") or "").strip() or None,
        client_token=str(result.get("client_token") or "").strip() or None,
        selected_profile=_normalize_profile(result.get("selected_profile")),
        user_info=_normalize_user_info(result.get("user")),
    )


def login(username: str, password: str) -> dict[str, Any]:
    if not username or not password:
        return {"success": False, "error": "Введите логин и пароль"}

    if not AUTH_AUTHENTICATE_URL:
        return {"success": False, "error": "AUTH_AUTHENTICATE_URL не настроен"}
    return _api_login(username, password)


def refresh_session() -> dict[str, Any]:
    if not AUTH_REFRESH_URL:
        return {"success": False, "error": "Сессия недоступна"}

    stored = _load_session()
    fallback_login = str(stored.get("login") or "").strip()
    access_token = str(stored.get("access_token") or "").strip() or None
    refresh_token = str(stored.get("refresh_token") or "").strip() or None
    client_token = str(stored.get("client_token") or "").strip() or None
    selected_profile = _normalize_profile(stored.get("selected_profile"))

    if not refresh_token and not access_token:
        return {"success": False, "error": "Сохраненная сессия не найдена"}

    try:
        payload = _compact_payload(
            {
                "accessToken": access_token,
                "refreshToken": refresh_token,
                "clientToken": client_token,
                "requestUser": True,
                "selectedProfile": selected_profile,
            }
        )
        body, _headers = _post_json(AUTH_REFRESH_URL, payload=payload)
        result = _normalize_auth_response(
            body,
            fallback_login=fallback_login,
            fallback_client_token=client_token,
            fallback_selected_profile=selected_profile,
            fallback_refresh_token=refresh_token,
        )
        if not result.get("success"):
            return result

        _persist_auth_result(result, fallback_login=fallback_login)
        return result
    except urllib.error.HTTPError as exc:
        if exc.code in (400, 401, 403):
            _clear_session_file()
        return {"success": False, "error": _parse_http_error(exc)}
    except Exception:
        return {"success": False, "error": "Не удалось обновить сессию"}


def logout() -> dict[str, Any]:
    stored = _load_session()
    access_token = str(stored.get("access_token") or "").strip() or None
    refresh_token = str(stored.get("refresh_token") or "").strip() or None
    client_token = str(stored.get("client_token") or "").strip() or None
    server_error = ""

    if AUTH_INVALIDATE_URL and (access_token or refresh_token):
        try:
            payload = _compact_payload(
                {
                    "accessToken": access_token,
                    "refreshToken": refresh_token,
                    "clientToken": client_token,
                }
            )
            _post_json(AUTH_INVALIDATE_URL, payload=payload)
        except urllib.error.HTTPError as exc:
            # Даже если токен уже истек/отозван — локально всё равно выходим.
            if exc.code not in (400, 401, 403, 404):
                server_error = _parse_http_error(exc)
        except Exception:
            server_error = "Не удалось связаться с сервером"

    _clear_session_file()

    if server_error:
        return {
            "success": True,
            "warning": f"Локальная сессия очищена, но сервер logout завершился с ошибкой: {server_error}",
        }
    return {"success": True}


def validate_access_token(access_token: Any, client_token: Any = None) -> bool | None:
    token = str(access_token or "").strip()
    if not token:
        return False

    if not AUTH_VALIDATE_URL:
        return True

    payload = _compact_payload(
        {
            "accessToken": token,
            "clientToken": str(client_token or "").strip() or None,
        }
    )
    try:
        _post_json(AUTH_VALIDATE_URL, payload=payload)
        return True
    except urllib.error.HTTPError as exc:
        if exc.code in (400, 401, 403):
            return False
        return None
    except Exception:
        return None


# ── REST API ──────────────────────────────────────────────────────────────────

def _api_login(username: str, password: str) -> dict[str, Any]:
    try:
        stored = _load_session()
        client_token = str(stored.get("client_token") or "").strip() or str(uuid.uuid4())
        body, _headers = _post_json(
            AUTH_AUTHENTICATE_URL,
            payload={
                "username": username,
                "password": password,
                "clientToken": client_token,
                "requestUser": True,
                "agent": {"name": "Minecraft", "version": 1},
            },
        )
        result = _normalize_auth_response(
            body,
            fallback_login=username,
            fallback_client_token=client_token,
        )
        if not result.get("success"):
            return result

        _persist_auth_result(result, fallback_login=username)
        return result
    except urllib.error.HTTPError as exc:
        return {"success": False, "error": _parse_http_error(exc)}
    except Exception:
        return {"success": False, "error": "Не удалось подключиться к серверу"}
