import json
import os
from pathlib import Path

from loguru import logger

from .system_setting import systemSetting


class JavaSetting:
    version: str = "1.7.10"
    memory: str = "-Xmx2G -Xms1G"
    json_memory: str = ".LoliCraft/launcher_settings.json"


javaSetting = JavaSetting()


class JavaFuncSetting:
    def __init__(self):
        # Инициализируем systemSetting как атрибут
        self.systemSetting = systemSetting

    @property
    def minecraft_directory(self):
        return os.path.join(self.systemSetting.appdata, ".LoliCraft")

    @property
    def vesion_directory(self):
        return os.path.join(self.minecraft_directory, "versions", javaSetting.version)

    @property
    def jar_directory(self):
        return os.path.join(self.vesion_directory, f"{javaSetting.version}.jar")

    @property
    def java_serch(self):
        return os.path.join(self.systemSetting.appdata, ".LoliCraft", "java", "bin", "javaw.exe")

    def save_memory_setting(self, memory_mb: int):
        """
        save_memory_setting in settings.json.

        Also update javaSetting.memory.

        :param memory_mb: int - memory_mb

        :return: None
        """
        try:
            setting_path = Path(os.path.join(self.systemSetting.appdata, javaSetting.json_memory))
            setting_path.parent.mkdir(parents=True, exist_ok=True)
            logger.info(f"[CONFIG] Сохраняю настройки в: {setting_path}")
            setting_memory = {"memory_mb": memory_mb}

            with open(setting_path, "w", encoding="utf-8") as f:
                json.dump(setting_memory, f, indent=2, ensure_ascii=False)

            xms_value = 1024 if memory_mb // 2 < 1024 else memory_mb // 2
            javaSetting.memory = f"-Xmx{memory_mb}M -Xms{xms_value}M"
            logger.info(f"[CONFIG] Настройки сохранены: {memory_mb}MB")

        except Exception:
            logger.exception("[CONFIG] Ошибка сохранения")

    def load_settings(self) -> dict:
        """
        Load setting from settings.json.

        If settings.json exists and "memory_mb" is in settings.json,
        load memory_mb from settings.json and update javaSetting.memory.

        If settings.json does not exist or "memory_mb" is not in settings.json,
        use default setting {"memory_mb": 2048} and update javaSetting.memory.

        :return: dict - loaded setting or default setting
        """
        setting_path = Path(os.path.join(self.systemSetting.appdata, javaSetting.json_memory))
        try:
            if setting_path.exists():
                with open(setting_path, "r", encoding="utf-8") as f:
                    setting_memory = json.load(f)

                    if "memory_mb" in setting_memory:
                        memory_mb = setting_memory["memory_mb"]
                        xms_value = 1024 if memory_mb // 2 < 1024 else memory_mb // 2
                        javaSetting.memory = f"-Xmx{memory_mb}M -Xms{xms_value}M"

                    logger.info(f"[CONFIG] Загружено memory_mb: {memory_mb}MB")
                    return setting_memory
        except Exception:
            logger.exception("[CONFIG] Ошибка загрузки")

        # Настройки по умолчанию
        default_settings = {"memory_mb": 2048}
        javaSetting.memory = "-Xmx2048M -Xms1024M"
        logger.info(f"[CONFIG] Использую настройки по умолчанию: {default_settings}")
        return default_settings


javaFunc = JavaFuncSetting()
