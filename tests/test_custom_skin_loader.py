"""Official CustomSkinLoader configuration tests."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from config.profiles import BuildPaths
from core import game
from core.custom_skin_loader import (
    CANONICAL_CONFIG,
    CustomSkinLoaderConfigurationError,
    ensure_custom_skin_loader_config,
)


def _build_paths(root: Path) -> BuildPaths:
    version_dir = root / "versions" / "Tech"
    version_dir.mkdir(parents=True)
    version_json = version_dir / "Tech.json"
    client_jar = version_dir / "Tech.jar"
    version_json.write_text("{}", encoding="utf-8")
    client_jar.write_bytes(b"client")
    return BuildPaths(
        build_id="tech",
        build_name="Tech",
        download_url="https://storage.example.test/downloads/Tech.zip",
        revision="test",
        game_dir=root,
        marker_file=root / ".installed.json",
        java_bin=root / "java" / "bin" / "javaw.exe",
        version_name="Tech",
        version_dir=version_dir,
        version_json=version_json,
        client_jar=client_jar,
        assets_dir=root / "assets",
        libraries_dir=root / "libraries",
        natives_dir=version_dir / "natives",
        settings_file=version_dir / "launcher_settings.json",
    )


def _install_loader(version_dir: Path, filename: str = "CustomSkinLoader_Universal-15.0.1.jar") -> Path:
    mods_dir = version_dir / "mods"
    mods_dir.mkdir(parents=True, exist_ok=True)
    jar_path = mods_dir / filename
    jar_path.write_bytes(b"test jar")
    return jar_path


class CustomSkinLoaderConfigTests(unittest.TestCase):
    def test_restores_game_profile_only_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            version_dir = Path(temp)
            _install_loader(version_dir)
            config_dir = version_dir / "CustomSkinLoader"
            config_dir.mkdir()
            config_path = config_dir / "CustomSkinLoader.json"
            config_path.write_text(
                json.dumps(
                    {
                        "loadlist": [
                            {"name": "LocalSkin", "type": "Legacy"},
                            {"name": "Mojang", "type": "MojangAPI"},
                        ]
                    }
                ),
                encoding="utf-8",
            )

            result = ensure_custom_skin_loader_config(version_dir)
            written = json.loads(result.read_text(encoding="utf-8"))

        self.assertEqual(result, config_path)
        self.assertEqual(written, CANONICAL_CONFIG)
        self.assertEqual(written["loadlist"], [{"name": "GameProfile", "type": "GameProfile"}])
        self.assertTrue(written["enableCape"])

    def test_missing_loader_is_an_explicit_build_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(CustomSkinLoaderConfigurationError, "отсутствует CustomSkinLoader"):
                ensure_custom_skin_loader_config(Path(temp))

    def test_incompatible_loader_is_an_explicit_build_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            version_dir = Path(temp)
            _install_loader(version_dir, "CustomSkinLoader_NeoForge-14.20.0.jar")

            with self.assertRaisesRegex(CustomSkinLoaderConfigurationError, "несовместимый"):
                ensure_custom_skin_loader_config(version_dir)

    def test_game_launch_restores_config_before_command_and_jvm(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            paths = _build_paths(Path(temp))
            _install_loader(paths.version_dir)
            process = Mock(pid=1234)

            def build_command(*_args: object, **_kwargs: object) -> list[str]:
                config = json.loads(
                    (paths.version_dir / "CustomSkinLoader" / "CustomSkinLoader.json").read_text(encoding="utf-8")
                )
                self.assertEqual(config, CANONICAL_CONFIG)
                return ["java", "main"]

            with (
                patch.object(game, "_process", None),
                patch("core.game.ram_limits", return_value={"ram_min_gb": 2, "ram_max_gb": 8}),
                patch("core.game.get_build_paths", return_value=paths),
                patch("core.game.select_java_binary", return_value=(Path("java"), 21, 21, [])),
                patch("core.game._build_command", side_effect=build_command),
                patch("core.game.subprocess.Popen", return_value=process) as popen,
                patch("core.game.threading.Thread") as thread,
            ):
                result = game.launch("tech", "Player", 4)

                popen_kwargs = popen.call_args.kwargs
                self.assertEqual(popen_kwargs["stderr"], game.subprocess.STDOUT)
                self.assertNotEqual(popen_kwargs["stdout"], game.subprocess.DEVNULL)
                self.assertTrue(popen_kwargs["stdout"].closed)
                log_text = (paths.game_dir / "logs" / "launcher-game.log").read_text(encoding="utf-8")
                self.assertIn("AiNoCraft game launch", log_text)
                self.assertIn("Build: tech (Tech)", log_text)
                self.assertIn("RAM: 4 GiB", log_text)

        self.assertEqual(result, {"success": True, "pid": 1234})
        popen.assert_called_once()
        thread.return_value.start.assert_called_once()

    def test_game_launch_does_not_start_with_missing_loader(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            paths = _build_paths(Path(temp))
            with (
                patch.object(game, "_process", None),
                patch("core.game.ram_limits", return_value={"ram_min_gb": 2, "ram_max_gb": 8}),
                patch("core.game.get_build_paths", return_value=paths),
                patch("core.game.select_java_binary", return_value=(Path("java"), 21, 21, [])),
                patch("core.game.subprocess.Popen") as popen,
            ):
                result = game.launch("tech", "Player", 4)

        self.assertFalse(result["success"])
        self.assertIn("отсутствует CustomSkinLoader", result["error"])
        popen.assert_not_called()
