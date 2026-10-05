"""Shared backend `/me` launcher client tests."""

import json
import unittest
from unittest.mock import patch

from core import backend_client
from ui.api import LauncherAPI


class _JsonResponse:
    """Minimal urllib context response for deterministic client tests."""

    headers: dict[str, str] = {}

    def __init__(self, payload: dict) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> "_JsonResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body


def _account_payload() -> dict:
    return {
        "user_id": "00000000-0000-4000-8000-000000000001",
        "login": "Vadim",
        "avatar": {"url": "https://storage.ainocraft.com/avatars/id/avatar.webp"},
        "balance": {"aino_coins": 10, "aino_crystal": 20},
        "role": {"code": "staff_owner", "title": "Owner", "ring_color": "#B66CFF"},
        "staff": None,
    }


class CurrentAccountClientTests(unittest.TestCase):
    """Canonical account parsing and authenticated transport checks."""

    def test_normalize_current_account_uses_canonical_nested_contract(self) -> None:
        preview = backend_client.normalize_current_account(_account_payload())

        self.assertEqual(preview["username"], "Vadim")
        self.assertEqual(preview["role"], "staff_owner")
        self.assertEqual(preview["role_label"], "Owner")
        self.assertEqual(preview["ring_color"], "#b66cff")
        self.assertTrue(preview["avatar_url"].endswith("/avatars/id/avatar.webp"))

    def test_fetch_current_account_sends_game_access_token(self) -> None:
        response = _JsonResponse(_account_payload())
        with patch("urllib.request.urlopen", return_value=response) as urlopen:
            result = backend_client.fetch_current_account("game-token")

        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer game-token")
        self.assertIs(result["success"], True)
        self.assertEqual(result["role"], "staff_owner")
        self.assertEqual(result["ring_color"], "#b66cff")

    def test_invalid_server_ring_color_uses_safe_launcher_fallback(self) -> None:
        payload = _account_payload()
        payload["role"]["ring_color"] = "url(javascript:alert(1))"

        preview = backend_client.normalize_current_account(payload)

        self.assertEqual(preview["ring_color"], backend_client.DEFAULT_RING_COLOR)

    def test_launcher_bridge_exposes_backend_ring_color_to_web_ui(self) -> None:
        api = LauncherAPI()
        account = {
            "success": True,
            "account": _account_payload(),
            "username": "Vadim",
            "role": "staff_owner",
            "role_label": "Owner",
            "ring_color": "#b66cff",
            "avatar_url": "https://storage.ainocraft.com/avatars/id/avatar.webp",
        }
        auth_result = {
            "success": True,
            "username": "Vadim",
            "token": "game-token",
            "client_token": "client-token",
            "selected_profile_id": "profile-id",
        }

        with (
            patch("ui.api.backend_client.fetch_current_account", return_value=account),
            patch("ui.api.auth.validate_access_token", return_value=True),
        ):
            api._apply_auth_result(auth_result)
            current = api.get_current_user()

        self.assertEqual(current["ring_color"], "#b66cff")
