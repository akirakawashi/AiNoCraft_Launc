import os
import sys


class SystemSetting:
    appdata = os.getenv("APPDATA")


systemSetting = SystemSetting()


def resource_path(relative_path: str) -> str:
    """
    return path to resource file

    Args:
        relative_path: relative path to resource ("src/assets/img/background.png")

    Returns:
        abs_path: full_path_resource
    """
    try:
        base_path = sys._MEIPASS # type: ignore[attr-defined]
    except AttributeError:
        base_path = os.path.abspath(".")
    full_path = os.path.join(base_path, relative_path)
    return os.path.normpath(full_path)


def is_frozen() -> bool:
    """
    Проверяет, запущено ли приложение в собранном виде (PyInstaller).

    Returns:
        True если приложение собрано PyInstaller, False если запущен скрипт Python
    """
    return getattr(sys, "frozen", False)


def get_base_path() -> str:
    """
    Возвращает базовый путь к ресурсам в зависимости от режима запуска.

    Returns:
        Путь к папке с ресурсами
    """
    if is_frozen():
        return sys._MEIPASS # type: ignore[attr-defined]
    return os.path.abspath(".")
