"""PyWebView bridge exposed as ``window.pywebview.api``."""

from __future__ import annotations

import threading
import webbrowser
from typing import Any
from urllib.parse import urlparse

from config import (
    LAUNCHER_VERSION,
    RUNTIME,
    get_available_builds,
    get_build_paths,
    get_default_build_id,
    user_prefs,
)
from core import auth, backend_client, build_manifest, downloader, game, updater
from core import settings as cfg
from core.system_info import ram_limits


_ALLOWED_EXTERNAL_URLS = {
    "https://ainocraft.com/register",
    "https://ainocraft.com/reset-password",
}


def _allowed_external_url_prefixes() -> tuple[str, ...]:
    """Site sections whose pages are safe to open externally (mode-aware)."""
    return (f"{RUNTIME.web_base_url}/news/",)

_LOCAL_PROFILE_PREVIEW = {
    "role": "default",
    "role_label": "Common",
    "ring_color": backend_client.DEFAULT_RING_COLOR,
    "avatar_url": "",
}


def _extract_profile_preview(result: dict[str, Any]) -> dict[str, str]:
    user_info = result.get("user") if isinstance(result.get("user"), dict) else {}
    role = str(
        result.get("role")
        or result.get("user_role")
        or user_info.get("role")
        or user_info.get("rank")
        or _LOCAL_PROFILE_PREVIEW["role"]
    ).strip()
    role_label = str(
        result.get("role_label")
        or user_info.get("role_label")
        or user_info.get("rank_label")
        or role.title()
        or _LOCAL_PROFILE_PREVIEW["role_label"]
    ).strip()
    ring_color = backend_client.normalize_ring_color(
        result.get("ring_color")
        or result.get("role_color")
        or user_info.get("ring_color")
        or user_info.get("role_color")
    )
    avatar_url = str(
        result.get("avatar_url")
        or result.get("avatar")
        or user_info.get("avatar_url")
        or user_info.get("avatar")
        or _LOCAL_PROFILE_PREVIEW["avatar_url"]
    ).strip()
    return {
        "role": role or _LOCAL_PROFILE_PREVIEW["role"],
        "role_label": role_label or _LOCAL_PROFILE_PREVIEW["role_label"],
        "ring_color": ring_color,
        "avatar_url": avatar_url,
    }


class LauncherAPI:
    """Single entrypoint between JavaScript and Python services."""

    def __init__(self) -> None:
        self._user: dict[str, Any] | None = None
        self._selected_build_id = ""
        self._window: Any = None
        self._auth_lock = threading.RLock()
        self._build_selection_lock = threading.RLock()
        self._warmup_started = False
        self._warmup_lock = threading.Lock()
        self._bootstrap_lock = threading.Lock()
        self._bootstrap: dict[str, Any] | None = None
        self._bootstrap_attempted = False
        self._build_manifest_lock = threading.Lock()
        self._build_manifest: dict[str, Any] | None = None
        self._build_manifest_attempted = False

    def _set_window(self, window: Any) -> None:
        # Underscore-prefixed so pywebview does NOT expose it to JS: this is
        # internal wiring (called once from launcher.py), and letting JS call it
        # would overwrite `_window` and break the window controls.
        self._window = window

    # ------------------------------------------------------------------ setup

    def warmup(self) -> dict[str, Any]:
        with self._warmup_lock:
            if self._warmup_started:
                return {"success": True, "already_started": True}
            self._warmup_started = True

        threading.Thread(target=self._warmup_worker, name="launcher-warmup", daemon=True).start()
        return {"success": True}

    def _warmup_worker(self) -> None:
        try:
            self._ensure_bootstrap()
            self._ensure_build_manifest()
            with self._auth_lock:
                auth.get_saved_login()
            selected = self._resolve_selected_build_id()
            get_build_paths(selected)
            cfg.load(selected)
            downloader.is_game_installed(selected)
            downloader.get_status()
            updater.get_status()
        except Exception:
            pass

    def _ensure_bootstrap(self) -> dict[str, Any] | None:
        """Fetch the backend bootstrap once and apply the build catalog.

        A failed attempt is remembered so UI calls do not stall repeatedly
        on an unreachable backend; local build profiles stay in effect.
        """
        with self._bootstrap_lock:
            if self._bootstrap is not None or self._bootstrap_attempted:
                return self._bootstrap
            self._bootstrap_attempted = True
            result = backend_client.fetch_bootstrap()
            if not result.get("success"):
                return None
            backend_client.apply_bootstrap(result)
            self._bootstrap = result
            return self._bootstrap

    def _ensure_build_manifest(self) -> dict[str, Any] | None:
        """Fetch the shared MinIO build revision manifest once per launch."""
        # Backend profiles define folders and version names. Apply them before
        # merging the MinIO revision/URL overlay, including for direct API calls.
        self._ensure_bootstrap()
        with self._build_manifest_lock:
            if self._build_manifest is not None or self._build_manifest_attempted:
                return self._build_manifest
            self._build_manifest_attempted = True
            result = build_manifest.fetch_and_apply()
            if not result.get("success"):
                return None
            self._build_manifest = result
            return self._build_manifest

    def _resolve_selected_build_id(self) -> str:
        with self._build_selection_lock:
            if self._selected_build_id:
                return self._selected_build_id

            candidate = user_prefs.get_last_build_id()
            try:
                get_build_paths(candidate or None)
            except ValueError:
                candidate = ""
            self._selected_build_id = candidate or get_default_build_id()
            return self._selected_build_id

    def get_app_state(self) -> dict[str, Any]:
        """Aggregated launcher state for one UI init call."""
        bootstrap = self._ensure_bootstrap()
        manifest = self._ensure_build_manifest()
        features = bootstrap.get("features") if isinstance(bootstrap, dict) else None
        if not isinstance(features, dict):
            features = {"news_enabled": False, "builds_from_backend": False}

        news = bootstrap.get("news") if isinstance(bootstrap, dict) else None
        if not isinstance(news, list):
            news = []

        selected = self._resolve_selected_build_id()
        return {
            "success": True,
            "mode": RUNTIME.mode.value,
            "dev": RUNTIME.is_dev,
            "api_base_url": RUNTIME.api_base_url,
            "storage_base_url": RUNTIME.storage_base_url,
            "web_base_url": RUNTIME.web_base_url,
            "launcher_version": LAUNCHER_VERSION,
            "backend_available": bootstrap is not None,
            "build_manifest_available": manifest is not None,
            "features": features,
            "news": news,
            "builds": self._builds_with_state(),
            "selected_build_id": selected,
            "default_build_id": get_default_build_id(),
            **ram_limits(),
        }

    # ----------------------------------------------------------------- window

    def minimize_window(self) -> dict[str, Any]:
        if not self._window:
            return {"success": False, "error": "Окно еще не готово"}
        self._window.minimize()
        return {"success": True}

    def close_window(self) -> dict[str, Any]:
        if not self._window:
            return {"success": False, "error": "Окно еще не готово"}
        self._window.destroy()
        return {"success": True}

    def move_window_delta(self, delta_x: int, delta_y: int) -> dict[str, Any]:
        if not self._window:
            return {"success": False, "error": "Окно еще не готово"}
        self._window.move(self._window.x + int(delta_x), self._window.y + int(delta_y))
        return {"success": True}

    # ------------------------------------------------------------------- auth

    def _apply_auth_result(self, result: dict[str, Any], fallback_username: str = "") -> None:
        with self._auth_lock:
            resolved_username = str(result.get("username") or result.get("login") or fallback_username).strip()
            access_token = str(result.get("token") or result.get("access_token") or "")
            client_token = str(result.get("client_token") or result.get("clientToken") or "").strip()
            selected_profile_id = str(result.get("selected_profile_id") or result.get("profile_id") or "").strip()
            account_result = backend_client.fetch_current_account(access_token)
            profile_preview = (
                {
                    "role": str(account_result["role"]),
                    "role_label": str(account_result["role_label"]),
                    "ring_color": str(account_result["ring_color"]),
                    "avatar_url": str(account_result["avatar_url"]),
                }
                if account_result.get("success")
                else _extract_profile_preview(result)
            )
            account = account_result.get("account") if isinstance(account_result.get("account"), dict) else None
            if account_result.get("username"):
                resolved_username = str(account_result["username"])
            self._user = {
                "username": resolved_username,
                "token": access_token,
                "client_token": client_token,
                "selected_profile_id": selected_profile_id,
                "token_type": str(result.get("token_type", "Bearer")),
                "expires_at": result.get("expires_at"),
                "user_type": str(result.get("user_type") or "mojang"),
                "account": account,
                **profile_preview,
            }
            result["username"] = resolved_username
            result["token"] = access_token
            result["account"] = account
            result.update(profile_preview)

    def _get_valid_user_snapshot(self) -> dict[str, Any] | None:
        with self._auth_lock:
            if self._user:
                validation = auth.validate_access_token(
                    self._user.get("token"),
                    self._user.get("client_token"),
                )
                if validation is True:
                    return dict(self._user)
                if validation is None and not auth.is_access_token_expiring(self._user.get("expires_at")):
                    return dict(self._user)

            refreshed = auth.refresh_session()
            if refreshed.get("success"):
                self._apply_auth_result(refreshed)
                return dict(self._user) if self._user else None

            self._user = None
            return None

    def login(self, username: str, password: str) -> dict[str, Any]:
        cleaned_username = username.strip()
        with self._auth_lock:
            result = auth.login(cleaned_username, password)
            if result.get("success"):
                self._apply_auth_result(result, username)
            return result

    def logout(self) -> dict[str, Any]:
        with self._auth_lock:
            try:
                return auth.logout()
            finally:
                self._user = None

    def get_current_user(self) -> dict[str, Any]:
        with self._auth_lock:
            user = self._get_valid_user_snapshot()
            if user:
                response: dict[str, Any] = {
                    "logged_in": True,
                    "username": user["username"],
                    "role": user.get("role", _LOCAL_PROFILE_PREVIEW["role"]),
                    "role_label": user.get("role_label", _LOCAL_PROFILE_PREVIEW["role_label"]),
                    "ring_color": user.get("ring_color", _LOCAL_PROFILE_PREVIEW["ring_color"]),
                    "avatar_url": user.get("avatar_url", _LOCAL_PROFILE_PREVIEW["avatar_url"]),
                }
                if isinstance(user.get("account"), dict):
                    response["account"] = user["account"]
                return response
            return {"logged_in": False, "last_login": auth.get_saved_login()}

    def open_external_url(self, url: str) -> dict[str, Any]:
        candidate = str(url or "").strip()
        if not candidate:
            return {"success": False, "error": "Пустой URL"}
        parsed = urlparse(candidate)
        if parsed.scheme not in ("https", "http"):
            return {"success": False, "error": "Недопустимая ссылка"}
        allowed = candidate in _ALLOWED_EXTERNAL_URLS or any(
            candidate.startswith(prefix) for prefix in _allowed_external_url_prefixes()
        )
        if not allowed:
            return {"success": False, "error": "Ссылка не разрешена"}
        try:
            return {"success": bool(webbrowser.open_new_tab(candidate))}
        except Exception:
            return {"success": False, "error": "Не удалось открыть браузер"}

    # ----------------------------------------------------------------- builds

    def _builds_with_state(self) -> list[dict[str, Any]]:
        builds = []
        for build in get_available_builds():
            build_id = str(build.get("id") or "")
            builds.append({**build, **downloader.get_build_state(build_id)})
        return builds

    def _resolve_build_id(self, build_id: str | None = None) -> str:
        resolved = (build_id or self._resolve_selected_build_id()).strip().lower()
        get_build_paths(resolved)
        return resolved

    def get_builds(self) -> dict[str, Any]:
        self._ensure_build_manifest()
        return {
            "success": True,
            "builds": self._builds_with_state(),
            "selected_build_id": self._resolve_selected_build_id(),
        }

    def select_build(self, build_id: str) -> dict[str, Any]:
        self._ensure_bootstrap()
        try:
            with self._build_selection_lock:
                resolved = self._resolve_build_id(build_id)
                paths = get_build_paths(resolved)
                self._selected_build_id = resolved
                user_prefs.set_last_build_id(resolved)
        except ValueError as exc:
            return {"success": False, "error": str(exc)}
        return {
            "success": True,
            "selected_build_id": resolved,
            "build_name": paths.build_name,
            **downloader.get_build_state(resolved),
        }

    def get_selected_build(self) -> dict[str, Any]:
        resolved = self._resolve_selected_build_id()
        paths = get_build_paths(resolved)
        return {"success": True, "selected_build_id": paths.build_id, "build_name": paths.build_name}

    # --------------------------------------------------------------- settings

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
        return {"success": cfg.save(data, resolved)}

    # ------------------------------------------------------------------- game

    def launch_game(self, build_id: str | None = None) -> dict[str, Any]:
        user = self._get_valid_user_snapshot()
        if not user:
            return {"success": False, "error": "Необходима авторизация"}

        try:
            resolved = self._resolve_build_id(build_id)
        except ValueError as exc:
            return {"success": False, "error": str(exc)}

        build_state = downloader.get_build_state(resolved)
        if not build_state.get("installed"):
            return {"success": False, "error": "Сборка не установлена или повреждена"}
        if build_state.get("update_available"):
            return {"success": False, "error": "Сначала обновите сборку"}

        settings = cfg.load(resolved)
        ram = int(settings.get("ram", ram_limits()["ram_default_gb"]))
        result = game.launch(
            resolved,
            str(user.get("username") or ""),
            ram,
            access_token=str(user.get("token") or ""),
            auth_uuid=str(user.get("selected_profile_id") or ""),
            client_id=str(user.get("client_token") or ""),
            user_type=str(user.get("user_type") or "mojang"),
            on_exit=lambda _rc: None,
        )
        if result.get("success") and self._window:
            self._window.destroy()
        return result

    def get_game_status(self) -> dict[str, Any]:
        return {"running": game.is_running(), "pid": game.get_pid()}

    def check_game_installed(self, build_id: str | None = None) -> dict[str, Any]:
        try:
            resolved = self._resolve_build_id(build_id)
        except ValueError as exc:
            return {"success": False, "error": str(exc), "installed": False}
        return {"success": True, **downloader.get_build_state(resolved)}

    # -------------------------------------------------------------- downloads

    def start_download(self, build_id: str | None = None) -> dict[str, Any]:
        if not self._get_valid_user_snapshot():
            return {"success": False, "error": "Сначала войдите в аккаунт"}
        if game.is_running():
            return {"success": False, "error": "Сначала закройте игру"}
        self._ensure_build_manifest()
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

    def delete_build_files(self, build_id: str | None = None) -> dict[str, Any]:
        """Delete installed files of a build; a separate explicit user action."""
        try:
            resolved = self._resolve_build_id(build_id)
        except ValueError as exc:
            return {"success": False, "error": str(exc)}
        if game.is_running():
            return {"success": False, "error": "Сначала закройте игру"}
        return downloader.delete_build(resolved)

    # ---------------------------------------------------------------- updater

    def check_launcher_update(self) -> dict[str, Any]:
        info = updater.check_for_update()
        return {
            "success": True,
            "available": bool(info.get("available")),
            "remote_version": info.get("remote_version"),
            "error": info.get("error"),
        }

    def start_launcher_update(self) -> dict[str, Any]:
        return updater.start_update()

    def get_launcher_update_progress(self) -> dict[str, Any]:
        return updater.get_status()
