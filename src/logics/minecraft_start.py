import subprocess
from pathlib import Path

from loguru import logger

from src.config import javaFunc, javaSetting


class MinecraftManager:
    """start minecraft"""
    def __init__(self) -> None:
        javaFunc.load_settings()

    def find_java(self):
        """search java"""
        java_path = Path(javaFunc.java_serch)
        if java_path.exists():
            return str(java_path)
        return None

    def is_installed(self) -> bool:
        """check if installed"""
        return Path(javaFunc.jar_directory).exists()
    
    def launch(self, username: str, memory_mb: int) -> subprocess.Popen:
        """Запуск Minecraft"""
        command = self.prepare_command(username, memory_mb)
        
        process = subprocess.Popen(
            command,
            cwd=str(javaFunc.minecraft_directory),
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )

        return process
    
    def build_classpath(self) -> str:
        """Создание classpath"""
        jar_file = Path(javaFunc.jar_directory)
        if not jar_file.exists():
            raise FileNotFoundError(f"Файл Minecraft не найден: {jar_file}")

        classpath_items = [str(jar_file)]
        libraries_dir = Path(javaFunc.minecraft_directory) / "libraries"

        if libraries_dir.exists():
            for jar_file in libraries_dir.rglob("*.jar"):
                classpath_items.append(str(jar_file))

        return ";".join(classpath_items)

    def prepare_command(self, username: str, memory_mb: int) -> list:
        """Подготовка команды для запуска"""
        java_path = self.find_java()
        if not java_path:
            raise Exception("Java не найдена")

        classpath = self.build_classpath()
        minecraft_path = Path(javaFunc.minecraft_directory)
        natives_path = Path(javaFunc.vesion_directory) / "natives"
        assets_path = minecraft_path / "assets"

        if memory_mb is not None:
            xms_value = 1024 if memory_mb // 2 < 1024 else memory_mb // 2
            memory_args = [f"-Xmx{memory_mb}M", f"-Xms{xms_value}M"]
            logger.info(memory_args)
        else:
            memory_args = javaSetting.memory.split()
            logger.info(memory_args)

        command = [
            java_path,
            *memory_args,
            f"-Djava.library.path={natives_path}",
            "-cp",
            classpath,
            "net.minecraft.client.main.Main",
            "--version",
            javaSetting.version,
            "--gameDir",
            str(minecraft_path),
            "--assetsDir",
            str(assets_path),
            "--assetIndex",
            "1.7.10",
            "--accessToken",
            "0",
            "--userProperties",
            "{}",
            "--username",
            username,
        ]
        return command