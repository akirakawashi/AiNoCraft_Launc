"""
PyWebView bridge API.

Methods of this class are exposed to JavaScript via:
  window.pywebview.api.<method>(...)
All values must be JSON-serializable.
"""

from __future__ import annotations

import webbrowser
from typing import Any
from urllib.parse import urlparse

from config import DEFAULT_BUILD_ID, RAM_DEFAULT_GB, get_available_builds, get_build_paths, get_runtime_config
from core import auth, downloader, game, updater
from core import settings as cfg

_ALLOWED_EXTERNAL_URLS = {
    "https://ainocraft.com/register",
    "https://ainocraft.com/reset-password",
}



class LauncherAPI:
    """Single API entrypoint between JavaScript and Python."""

    def __init__(self) -> None:
        self._user: dict[str, Any] | None = None
        self._selected_build_id: str = DEFAULT_BUILD_ID
        self._window = None  # pywebview.Window, injected by launcher.py

    def set_window(self, window: Any) -> None:
        """Inject pywebview window instance without exposing it to JS API tree."""
        self._window = window

    def _resolve_build_id(self, build_id: str | None = None) -> str:
        resolved_id = (build_id or self._selected_build_id).strip().lower()
        get_build_paths(resolved_id)  # validation
        return resolved_id

    def _auth_required(self) -> dict[str, Any] | None:
        if self._ensure_user_session():
            return None
        return {"success": False, "error": "Необходима авторизация"}

    def _apply_auth_result(self, result: dict[str, Any], fallback_username: str = "") -> None:
        resolved_username = str(result.get("username") or result.get("login") or fallback_username).strip()
        access_token = str(result.get("token") or result.get("access_token") or "")
        client_token = str(result.get("client_token") or result.get("clientToken") or "").strip()
        selected_profile_id = str(
            result.get("selected_profile_id")
            or result.get("profile_id")
            or ""
        ).strip()
        self._user = {
            "username": resolved_username,
            "token": access_token,
            "client_token": client_token,
            "selected_profile_id": selected_profile_id,
            "token_type": str(result.get("token_type", "Bearer")),
            "expires_at": result.get("expires_at"),
            "user_type": str(result.get("user_type") or "mojang"),
        }
        result["username"] = resolved_username
        result["token"] = access_token

    def _ensure_user_session(self) -> bool:
        if self._user:
            validation = auth.validate_access_token(
                self._user.get("token"),
                self._user.get("client_token"),
            )
            if validation is True:
                return True
            # Если auth-сервер временно недоступен, не выкидываем пользователя локально.
            if validation is None and not auth.is_access_token_expiring(self._user.get("expires_at")):
                return True

        refreshed = auth.refresh_session()
        if refreshed.get("success"):
            self._apply_auth_result(refreshed)
            return True

        self._user = None
        return False

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def login(self, username: str, password: str) -> dict[str, Any]:
        result = auth.login(username.strip(), password)
        if result.get("success"):
            self._apply_auth_result(result, fallback_username=username)
        return result

    def logout(self) -> dict[str, Any]:
        result = auth.logout()
        self._user = None
        return result

    def get_current_user(self) -> dict[str, Any]:
        if self._ensure_user_session() and self._user:
            return {"logged_in": True, "username": self._user["username"]}
        return {"logged_in": False, "last_login": auth.get_saved_login()}

    def open_external_url(self, url: str) -> dict[str, Any]:
        candidate = str(url or "").strip()
        if not candidate:
            return {"success": False, "error": "Пустой URL"}

        parsed = urlparse(candidate)
        if parsed.scheme != "https":
            return {"success": False, "error": "Допустимы только HTTPS ссылки"}

        if candidate not in _ALLOWED_EXTERNAL_URLS:
            return {"success": False, "error": "Ссылка не разрешена"}

        try:
            opened = webbrowser.open_new_tab(candidate)
            if not opened:
                return {"success": False, "error": "Не удалось открыть ссылку"}
            return {"success": True}
        except Exception:
            return {"success": False, "error": "Не удалось открыть браузер"}

    # ------------------------------------------------------------------
    # Runtime/config
    # ------------------------------------------------------------------

    def get_runtime_config(self) -> dict[str, Any]:
        return {"success": True, **get_runtime_config()}

    # ------------------------------------------------------------------
    # Builds
    # ------------------------------------------------------------------

    def get_builds(self) -> dict[str, Any]:
        return {
            "success": True,
            "builds": get_available_builds(),
            "selected_build_id": self._selected_build_id,
        }

    def select_build(self, build_id: str) -> dict[str, Any]:
        try:
            resolved = self._resolve_build_id(build_id)
            paths = get_build_paths(resolved)
        except ValueError as exc:
            return {"success": False, "error": str(exc)}

        self._selected_build_id = resolved
        return {
            "success": True,
            "selected_build_id": resolved,
            "build_name": paths.build_name,
        }

    def get_selected_build(self) -> dict[str, Any]:
        try:
            paths = get_build_paths(self._selected_build_id)
        except ValueError:
            self._selected_build_id = DEFAULT_BUILD_ID
            paths = get_build_paths(self._selected_build_id)

        return {
            "success": True,
            "selected_build_id": paths.build_id,
            "build_name": paths.build_name,
        }

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def get_settings(self, build_id: str | None = None) -> dict[str, Any]:
        try:
            resolved = self._resolve_build_id(build_id)
        except ValueError as exc:
            return {"success": False, "error": str(exc), **cfg.normalize(None)}

        return {"success": True, **cfg.load(resolved)}

    def save_settings(self, data: dict[str, Any], build_id: str | None = None) -> dict[str, Any]:
        try:
            resolved = self._resolve_build_id(build_id)
        except ValueError as exc:
            return {"success": False, "error": str(exc)}

        ok = cfg.save(data, resolved)
        return {"success": ok}

    # ------------------------------------------------------------------
    # Game
    # ------------------------------------------------------------------

    def launch_game(self, build_id: str | None = None) -> dict[str, Any]:
        auth_error = self._auth_required()
        if auth_error:
            return auth_error

        try:
            resolved = self._resolve_build_id(build_id)
        except ValueError as exc:
            return {"success": False, "error": str(exc)}

        settings = cfg.load(resolved)
        ram = int(settings.get("ram", RAM_DEFAULT_GB))
        username = str(self._user["username"])  # type: ignore[index]
        token = str(self._user.get("token", "")) if self._user else ""
        profile_id = str(self._user.get("selected_profile_id", "")) if self._user else ""
        client_token = str(self._user.get("client_token", "")) if self._user else ""
        user_type = str(self._user.get("user_type", "mojang")) if self._user else "mojang"

        result = game.launch(
            resolved,
            username,
            ram,
            access_token=token,
            auth_uuid=profile_id,
            client_id=client_token,
            user_type=user_type,
            on_exit=lambda _rc: None,
        )
        if result.get("success") and self._window:
            self._window.destroy()
        return result

    def get_game_status(self) -> dict[str, Any]:
        return {"running": game.is_running(), "pid": game.get_pid()}

    # ------------------------------------------------------------------
    # Download/install
    # ------------------------------------------------------------------

    def check_game_installed(self, build_id: str | None = None) -> dict[str, Any]:
        try:
            resolved = self._resolve_build_id(build_id)
        except ValueError as exc:
            return {"success": False, "error": str(exc), "installed": False}
        return {"success": True, "installed": downloader.is_game_installed(resolved)}

    def start_download(self, build_id: str | None = None) -> dict[str, Any]:
        auth_error = self._auth_required()
        if auth_error:
            return {"success": False, "error": "Сначала войдите в аккаунт"}

        try:
            resolved = self._resolve_build_id(build_id)
            paths = get_build_paths(resolved)
        except ValueError as exc:
            return {"success": False, "error": str(exc)}

        return downloader.start(resolved, paths.download_url)

    def cancel_download(self) -> dict[str, Any]:
        return downloader.cancel()

    def get_download_progress(self) -> dict[str, Any]:
        return downloader.get_status()

    # ------------------------------------------------------------------
    # Self-update
    # ------------------------------------------------------------------

    def check_launcher_update(self) -> dict[str, Any]:
        """Check if a newer launcher version is available (synchronous).
        Returns available, remote_version, download_url, error."""
        result = updater.check_for_update()
        return {"success": True, **result}

    def start_launcher_update(self, download_url: str, sha256: str | None = None) -> dict[str, Any]:
        """Start downloading and applying the launcher update.
        download_url: direct link to new .exe on MinIO.
        sha256: optional expected checksum."""
        return updater.start_update(download_url, sha256)

    def get_launcher_update_progress(self) -> dict[str, Any]:
        """Poll download progress (state, percent, speed_mb, downloaded_mb, total_mb, error)."""
        return updater.get_status()
