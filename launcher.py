"""
AiNoCraft Лаунчер — точка входа.

Запуск:  python launcher.py
Сборка:  pyinstaller --noconfirm --clean launcher.spec
"""

import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

# Гарантируем что папка launcher/ в sys.path при любом способе запуска
sys.path.insert(0, str(Path(__file__).parent))


# ── Запуск ────────────────────────────────────────────────────────────────────

def _get_crash_log_path() -> Path:
    appdata = Path(os.environ.get("APPDATA", str(Path.home())))
    data_dir = appdata / "AiNoCraftLauncher"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "launcher_crash.log"


def _write_crash_log(exc: Exception) -> Path:
    log_path = _get_crash_log_path()
    with open(log_path, "a", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write(f"[{datetime.now().isoformat()}] Unhandled exception\n")
        f.write(traceback.format_exc())
        f.write("\n")
    return log_path


def _show_error_dialog(message: str) -> None:
    try:
        if os.name == "nt":
            import ctypes

            MB_ICONERROR = 0x10
            MB_OK = 0x00000000
            ctypes.windll.user32.MessageBoxW(0, message, "AiNoCraft Launcher", MB_OK | MB_ICONERROR)
    except Exception:
        pass


def main() -> None:
    import webview
    from config import (
        LAUNCHER_DIR,
        LAUNCHER_WINDOW_TITLE,
        WINDOW_BACKGROUND_COLOR,
        WINDOW_HEIGHT,
        WINDOW_RESIZABLE,
        WINDOW_WIDTH,
    )
    from core.updater import register_shutdown, startup_cleanup
    from ui.api import LauncherAPI

    # Delete leftover .exe.old from a previous self-update (if any)
    startup_cleanup()

    api = LauncherAPI()

    index_html = LAUNCHER_DIR / "ui" / "web" / "index.html"
    if not index_html.exists():
        raise FileNotFoundError(f"Не найден UI-файл: {index_html}")

    window = webview.create_window(
        title            = LAUNCHER_WINDOW_TITLE,
        url              = index_html.as_uri(),
        js_api           = api,
        width            = WINDOW_WIDTH,
        height           = WINDOW_HEIGHT,
        resizable        = WINDOW_RESIZABLE,
        hidden           = True,
        background_color = WINDOW_BACKGROUND_COLOR,
        text_select      = False,
    )

    # Передаём ссылку на окно в API (нужна для колбэка on_exit)
    api.set_window(window)

    # Чистое завершение при авто-обновлении: destroy закрывает окно и webview-подпроцессы
    register_shutdown(window.destroy)

    # EdgeChromium — современный движок на Windows 10/11
    shown_once = {"done": False}

    def _show_after_first_load(*_args) -> None:
        if shown_once["done"]:
            return
        shown_once["done"] = True
        window.show()

    window.events.loaded += _show_after_first_load

    webview.start(gui="edgechromium", debug=False)

    # ── После webview.start(): WebView2 полностью мёртв ───────────────────────────────

    # Окно закрыто — гарантированно чистим незавершённые загрузки
    from core import downloader
    downloader.cleanup_on_exit()



if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        log_path = _write_crash_log(exc)
        message = (
            "Лаунчер завершился с ошибкой.\n\n"
            f"{exc}\n\n"
            f"Подробности записаны в:\n{log_path}"
        )
        print(message, file=sys.stderr)
        print(traceback.format_exc(), file=sys.stderr)
        _show_error_dialog(message)
        sys.exit(1)
