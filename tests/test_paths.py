from __future__ import annotations

import unittest

import launcher

from config.paths import (
    APPDATA_DIR,
    DOWNLOAD_TEMP_DIR,
    GAME_INSTANCES_DIR,
    LAUNCHER_DATA_DIR,
    LAUNCHER_ROOT_DIR,
    LOCALAPPDATA_DIR,
)
from config.profiles import get_build_paths


class DataPathTests(unittest.TestCase):
    def test_launcher_data_uses_local_appdata(self) -> None:
        self.assertEqual(LAUNCHER_ROOT_DIR, LOCALAPPDATA_DIR / "AiNoCraft" / "Launcher")
        self.assertEqual(LAUNCHER_DATA_DIR, LAUNCHER_ROOT_DIR / "data")
        self.assertEqual(DOWNLOAD_TEMP_DIR, LAUNCHER_DATA_DIR / "temp")
        self.assertEqual(launcher._crash_log_path(), LAUNCHER_DATA_DIR / "launcher_crash.log")

    def test_game_instances_use_appdata(self) -> None:
        self.assertEqual(GAME_INSTANCES_DIR, APPDATA_DIR / "AiNoCraft")

    def test_profile_is_installed_under_game_instances_root(self) -> None:
        paths = get_build_paths("tech")
        self.assertEqual(paths.game_dir, GAME_INSTANCES_DIR / "AiNoCraftTech")


if __name__ == "__main__":
    unittest.main()
