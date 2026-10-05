from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from config.runtime import LauncherMode, load_runtime_config


class FrozenRuntimeConfigTests(unittest.TestCase):
    """Packaged (frozen) builds must ignore every CLI/env override."""

    def test_frozen_ignores_overrides_and_forces_prod(self) -> None:
        env = {
            "AINOCRAFT_ENV": "dev",
            "AINOCRAFT_AUTH_PROFILE": "dev",
            "AINOCRAFT_API_BASE_URL": "http://evil.example",
            "AINOCRAFT_AUTH_BASE_URL": "http://evil.example",
            "AINOCRAFT_STORAGE_BASE_URL": "http://evil.example",
        }

        cfg = load_runtime_config(argv=["--mode", "dev"], environ=env, frozen=True)

        self.assertEqual(cfg.mode, LauncherMode.PROD)
        self.assertFalse(cfg.is_dev)
        self.assertEqual(cfg.server_base_url, "https://api.ainocraft.com")
        self.assertEqual(cfg.api_base_url, "https://api.ainocraft.com/api/v1/")
        self.assertEqual(cfg.minecraft_api_base_url, "https://api.ainocraft.com/minecraft-server-api/")
        self.assertEqual(cfg.storage_base_url, "https://storage.ainocraft.com/")
        self.assertNotIn("evil", cfg.api_base_url + cfg.minecraft_api_base_url + cfg.storage_base_url)

    def test_source_run_honors_url_overrides(self) -> None:
        env = {
            "AINOCRAFT_API_BASE_URL": "https://staging.example",
            "AINOCRAFT_STORAGE_BASE_URL": "https://cdn.example",
        }

        cfg = load_runtime_config(argv=[], environ=env, frozen=False)

        self.assertEqual(cfg.server_base_url, "https://staging.example")
        self.assertEqual(cfg.storage_base_url, "https://cdn.example/")

    def test_source_run_honors_mode_override(self) -> None:
        cfg = load_runtime_config(argv=["--mode", "dev"], environ={}, frozen=False)

        self.assertEqual(cfg.mode, LauncherMode.DEV)
        self.assertTrue(cfg.server_base_url.startswith("http://127.0.0.1"))


class FrozenInjectorTests(unittest.TestCase):
    def test_frozen_ignores_injector_api_base_override(self) -> None:
        from core import injector

        with patch.dict(os.environ, {injector.AUTHLIB_INJECTOR_API_BASE_ENV: "http://evil/api/"}):
            with patch.object(injector.sys, "frozen", True, create=True):
                frozen_result = injector.resolve_authlib_api_base_url()
            with patch.object(injector.sys, "frozen", False, create=True):
                source_result = injector.resolve_authlib_api_base_url()

        self.assertNotIn("evil", str(frozen_result or ""))
        self.assertEqual(source_result, "http://evil/api/")


if __name__ == "__main__":
    unittest.main()
