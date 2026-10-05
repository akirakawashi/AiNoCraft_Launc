"""Auth service for the AiNoCraft Yggdrasil-compatible API."""

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
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config import (
    AUTH_AUTHENTICATE_URL,
    AUTH_INVALIDATE_URL,
    AUTH_REFRESH_URL,
    AUTH_TIMEOUT_SEC,
    AUTH_VALIDATE_URL,
    LAUNCHER_DATA_DIR,
    USER_AGENT,
)


_ACCESS_TOKEN_REFRESH_LEEWAY_SEC = 45
_AUTH_SESSION_FILE: Path = LAUNCHER_DATA_DIR / "auth_session.json"
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


@dataclass(slots=True)
class AuthProfile:
    id: str
    name: str

    def to_dict(self) -> dict[str, str]:
        return {"id": self.id, "name": self.name}


@dataclass(slots=True)
class AuthSession:
    login: str = ""
    access_token: str | None = None
    refresh_token: str | None = None
    client_token: str | None = None
    selected_profile: AuthProfile | None = None
    user: dict[str, Any] | None = None
    updated_at: int | None = None


def _blob_from_bytes(data: bytes) -> tuple[Any, Any]:
    raw = ctypes.create_string_buffer(data, len(data))
    blob = _DATA_BLOB(cbData=len(data), pbData=ctypes.cast(raw, ctypes.POINTER(ctypes.c_byte)))
    return blob, raw


def _protect_bytes(data: bytes) -> bytes:
    if not data or not _IS_WINDOWS:
        return data
    in_blob, _in_raw = _blob_from_bytes(data)
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
    if not data or not _IS_WINDOWS:
        return data
    in_blob, _in_raw = _blob_from_bytes(data)
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


def _encode_secret(value: str | None) -> str | None:
    cleaned = str(value or "").strip()
    if not cleaned:
        return None
    return base64.b64encode(_protect_bytes(cleaned.encode("utf-8"))).decode("ascii")


def _decode_secret(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        protected = base64.b64decode(value.encode("ascii"))
        decoded = _unprotect_bytes(protected).decode("utf-8").strip()
    except Exception:
        return None
    return decoded or None


def _normalize_profile(profile: Any) -> AuthProfile | None:
    if not isinstance(profile, dict):
        return None
    profile_id = str(profile.get("id") or "").strip()
    profile_name = str(profile.get("name") or "").strip()
    if not profile_id and not profile_name:
        return None
    return AuthProfile(id=profile_id, name=profile_name)


def _normalize_user_properties(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    result: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        value = str(item.get("value") or "").strip()
        signature = str(item.get("signature") or "").strip()
        if not name or not value:
            continue
        entry = {"name": name, "value": value}
        if signature:
            entry["signature"] = signature
        result.append(entry)
    return result


def _normalize_user_info(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    user_id = str(raw.get("id") or "").strip()
    properties = _normalize_user_properties(raw.get("properties"))
    if not user_id and not properties:
        return None
    return {"id": user_id, "properties": properties}


class SessionStore:
    def __init__(self, session_file: Path = _AUTH_SESSION_FILE) -> None:
        self.session_file = session_file

    def load(self) -> AuthSession:
        try:
            raw = json.loads(self.session_file.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raw = {}
        except Exception:
            raw = {}

        return AuthSession(
            login=str(raw.get("login") or "").strip(),
            access_token=_decode_secret(raw.get("access_token")),
            refresh_token=_decode_secret(raw.get("refresh_token")),
            client_token=str(raw.get("client_token") or "").strip() or None,
            selected_profile=_normalize_profile(raw.get("selected_profile")),
            user=_normalize_user_info(raw.get("user")),
            updated_at=raw.get("updated_at"),
        )

    def save(self, session: AuthSession) -> None:
        payload: dict[str, Any] = {
            "login": session.login.strip(),
            "updated_at": int(time.time()),
        }
        access_token = _encode_secret(session.access_token)
        refresh_token = _encode_secret(session.refresh_token)
        if access_token:
            payload["access_token"] = access_token
        if refresh_token:
            payload["refresh_token"] = refresh_token
        if session.client_token:
            payload["client_token"] = session.client_token
        if session.selected_profile:
            payload["selected_profile"] = session.selected_profile.to_dict()
        if session.user:
            payload["user"] = session.user

        self.session_file.parent.mkdir(parents=True, exist_ok=True)
        self.session_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def clear(self) -> None:
        try:
            self.session_file.unlink()
        except FileNotFoundError:
            pass
        except Exception:
            pass


def _compact_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


def _parse_http_error(exc: urllib.error.HTTPError) -> str:
    try:
        data = json.loads(exc.read())
    except Exception:
        return f"HTTP {exc.code}"
    if not isinstance(data, dict):
        return f"HTTP {exc.code}"
    detail = data.get("detail")
    if isinstance(detail, list):
        return "; ".join(str(item) for item in detail) or f"HTTP {exc.code}"
    return str(detail or data.get("errorMessage") or data.get("error") or data.get("message") or f"HTTP {exc.code}")


def _post_json(url: str, payload: dict[str, Any] | None = None) -> tuple[dict[str, Any], Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload or {}).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=AUTH_TIMEOUT_SEC) as response:
        raw = response.read()
        if not raw:
            return {}, response.headers
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}, response.headers


class AuthService:
    def __init__(self, store: SessionStore | None = None) -> None:
        self.store = store or SessionStore()

    def get_saved_login(self) -> str:
        return self.store.load().login

    @staticmethod
    def is_access_token_expiring(expires_at: Any, leeway_sec: int = _ACCESS_TOKEN_REFRESH_LEEWAY_SEC) -> bool:
        if expires_at in (None, ""):
            return False
        try:
            exp_ts = int(expires_at)
        except (TypeError, ValueError):
            return True
        return int(time.time()) >= exp_ts - int(leeway_sec)

    def login(self, username: str, password: str) -> dict[str, Any]:
        if not username or not password:
            return {"success": False, "error": "Введите логин и пароль"}
        if not AUTH_AUTHENTICATE_URL:
            return {"success": False, "error": "AUTH_AUTHENTICATE_URL не настроен"}

        try:
            stored = self.store.load()
            client_token = stored.client_token or str(uuid.uuid4())
            body, _headers = _post_json(
                AUTH_AUTHENTICATE_URL,
                {
                    "username": username,
                    "password": password,
                    "clientToken": client_token,
                    "requestUser": True,
                    "agent": {"name": "Minecraft", "version": 1},
                },
            )
            result = self._normalize_auth_response(body, username, fallback_client_token=client_token)
            if result.get("success"):
                self._persist_result(result, username)
            return result
        except urllib.error.HTTPError as exc:
            return {"success": False, "error": _parse_http_error(exc)}
        except Exception:
            return {"success": False, "error": "Не удалось подключиться к серверу"}

    def refresh_session(self) -> dict[str, Any]:
        if not AUTH_REFRESH_URL:
            return {"success": False, "error": "Сессия недоступна"}

        stored = self.store.load()
        if not stored.refresh_token and not stored.access_token:
            return {"success": False, "error": "Сохраненная сессия не найдена"}

# TODO: при некст пушу убрать коментарий. он был добавлен для теста
        try:
            body, _headers = _post_json(
                AUTH_REFRESH_URL,
                _compact_payload(
                    {
                        "accessToken": stored.access_token,
                        "refreshToken": stored.refresh_token,
                        "clientToken": stored.client_token,
                        "requestUser": True,
                        "selectedProfile": stored.selected_profile.to_dict() if stored.selected_profile else None,
                    }
                ),
            )
            result = self._normalize_auth_response(
                body,
                stored.login,
                fallback_client_token=stored.client_token,
                fallback_selected_profile=stored.selected_profile,
                fallback_refresh_token=stored.refresh_token,
            )
            if result.get("success"):
                self._persist_result(result, stored.login)
            return result
        except urllib.error.HTTPError as exc:
            if exc.code in (400, 401, 403):
                self.store.clear()
            return {"success": False, "error": _parse_http_error(exc)}
        except Exception:
            return {"success": False, "error": "Не удалось обновить сессию"}

    def logout(self) -> dict[str, Any]:
        stored = self.store.load()
        server_error = ""
        if AUTH_INVALIDATE_URL and (stored.access_token or stored.refresh_token):
            try:
                _post_json(
                    AUTH_INVALIDATE_URL,
                    _compact_payload(
                        {
                            "accessToken": stored.access_token,
                            "refreshToken": stored.refresh_token,
                            "clientToken": stored.client_token,
                        }
                    ),
                )
            except urllib.error.HTTPError as exc:
                if exc.code not in (400, 401, 403, 404):
                    server_error = _parse_http_error(exc)
            except Exception:
                server_error = "Не удалось связаться с сервером"

        self.store.clear()
        if server_error:
            return {"success": True, "warning": f"Локальная сессия очищена, но сервер logout завершился с ошибкой: {server_error}"}
        return {"success": True}

    def validate_access_token(self, access_token: Any, client_token: Any = None) -> bool | None:
        token = str(access_token or "").strip()
        if not token:
            return False
        if not AUTH_VALIDATE_URL:
            return True
        try:
            _post_json(
                AUTH_VALIDATE_URL,
                _compact_payload(
                    {
                        "accessToken": token,
                        "clientToken": str(client_token or "").strip() or None,
                    }
                ),
            )
            return True
        except urllib.error.HTTPError as exc:
            if exc.code in (400, 401, 403):
                return False
            return None
        except Exception:
            return None

    def _normalize_auth_response(
        self,
        body: dict[str, Any],
        fallback_login: str,
        fallback_client_token: str | None = None,
        fallback_selected_profile: AuthProfile | None = None,
        fallback_refresh_token: str | None = None,
    ) -> dict[str, Any]:
        resolved_login = str(body.get("login") or body.get("username") or fallback_login).strip()
        access_token = str(body.get("accessToken") or body.get("access_token") or body.get("token") or "").strip()
        refresh_token = str(body.get("refreshToken") or body.get("refresh_token") or "").strip() or fallback_refresh_token
        client_token = str(body.get("clientToken") or body.get("client_token") or "").strip() or fallback_client_token

        available_profiles: list[AuthProfile] = []
        raw_profiles = body.get("availableProfiles") or body.get("available_profiles")
        if isinstance(raw_profiles, list):
            for item in raw_profiles:
                profile = _normalize_profile(item)
                if profile:
                    available_profiles.append(profile)

        selected_profile = _normalize_profile(body.get("selectedProfile") or body.get("selected_profile"))
        if not selected_profile:
            selected_profile = fallback_selected_profile or (available_profiles[0] if available_profiles else None)

        user_info = _normalize_user_info(body.get("user"))
        role = str(body.get("role") or body.get("user_role") or "").strip()
        role_label = str(body.get("role_label") or body.get("rank_label") or "").strip()
        if not access_token:
            return {"success": False, "error": "Сервер авторизации вернул пустой токен"}
        if not client_token:
            client_token = str(uuid.uuid4())
        if selected_profile and selected_profile.name:
            resolved_login = selected_profile.name

        return {
            "success": True,
            "username": resolved_login,
            "login": resolved_login,
            "token": access_token,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "client_token": client_token,
            "token_type": "Bearer",
            "expires_at": body.get("expires_at"),
            "selected_profile_id": selected_profile.id if selected_profile else "",
            "selected_profile_name": selected_profile.name if selected_profile else "",
            "selected_profile": selected_profile.to_dict() if selected_profile else None,
            "available_profiles": [profile.to_dict() for profile in available_profiles],
            "user": user_info,
            "avatar_url": "",
            "user_type": "mojang",
            "role": role,
            "role_label": role_label,
        }

    def _persist_result(self, result: dict[str, Any], fallback_login: str = "") -> None:
        selected_profile = _normalize_profile(result.get("selected_profile"))
        self.store.save(
            AuthSession(
                login=str(result.get("login") or result.get("username") or fallback_login).strip(),
                access_token=str(result.get("access_token") or result.get("token") or "").strip() or None,
                refresh_token=str(result.get("refresh_token") or "").strip() or None,
                client_token=str(result.get("client_token") or "").strip() or None,
                selected_profile=selected_profile,
                user=_normalize_user_info(result.get("user")),
            )
        )


_service = AuthService()


def get_saved_login() -> str:
    return _service.get_saved_login()


def is_access_token_expiring(expires_at: Any, leeway_sec: int = _ACCESS_TOKEN_REFRESH_LEEWAY_SEC) -> bool:
    return _service.is_access_token_expiring(expires_at, leeway_sec)


def login(username: str, password: str) -> dict[str, Any]:
    return _service.login(username.strip(), password)


def refresh_session() -> dict[str, Any]:
    return _service.refresh_session()


def logout() -> dict[str, Any]:
    return _service.logout()


def validate_access_token(access_token: Any, client_token: Any = None) -> bool | None:
    return _service.validate_access_token(access_token, client_token)
