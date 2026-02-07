from loguru import logger
from PyQt5.QtWidgets import QApplication

from src.config.system_setting import is_frozen, resource_path


class StyleManager:
    @staticmethod
    def load_styles(widget=None):
        """load styles from file"""
        try:
            style_path = resource_path("src/style/style.css")
            mode = "EXE MODE" if is_frozen() else "DEV MODE"
            logger.info(f"[{mode}] Загружаю стили из: {style_path}")

            # Чтение файла стилей
            with open(style_path, "r", encoding="utf-8") as f:
                style = f.read()

            if widget:
                widget.setStyleSheet(style)
            else:
                QApplication.instance().setStyleSheet(style)

            return True

        except FileNotFoundError:
            logger.error(f"Файл стилей не найден по пути: {style_path}")
            return False
        except Exception as e:
            logger.error(f"Ошибка загрузки стилей: {e}")
            return False
