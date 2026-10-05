"""AiNoCraft Launcher desktop entrypoint."""

from __future__ import annotations

import os
import sys
import traceback
from datetime import datetime
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))


def _center_window_on_cursor_monitor(window: object) -> bool:
    """Center a native Windows window on the monitor containing the cursor."""
    if os.name != "nt":
        return False

    try:
        import ctypes
        from ctypes import wintypes

        class Point(ctypes.Structure):
            _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

        class Rect(ctypes.Structure):
            _fields_ = [
                ("left", wintypes.LONG),
                ("top", wintypes.LONG),
                ("right", wintypes.LONG),
                ("bottom", wintypes.LONG),
            ]

        class MonitorInfo(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("rcMonitor", Rect),
                ("rcWork", Rect),
                ("dwFlags", wintypes.DWORD),
            ]

        native_window = getattr(window, "native", None)
        native_handle = getattr(native_window, "Handle", None)
        if native_handle is None:
            return False

        hwnd = wintypes.HWND(native_handle.ToInt64())
        cursor = Point()
        window_rect = Rect()
        monitor_info = MonitorInfo()
        monitor_info.cbSize = ctypes.sizeof(MonitorInfo)

        user32 = ctypes.windll.user32
        monitor_handle_type = getattr(wintypes, "HMONITOR", wintypes.HANDLE)
        user32.GetCursorPos.argtypes = [ctypes.POINTER(Point)]
        user32.GetCursorPos.restype = wintypes.BOOL
        user32.MonitorFromPoint.argtypes = [Point, wintypes.DWORD]
        user32.MonitorFromPoint.restype = monitor_handle_type
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
        user32.MonitorFromWindow.restype = monitor_handle_type
        user32.GetMonitorInfoW.argtypes = [monitor_handle_type, ctypes.POINTER(MonitorInfo)]
        user32.GetMonitorInfoW.restype = wintypes.BOOL
        user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(Rect)]
        user32.GetWindowRect.restype = wintypes.BOOL
        user32.SetWindowPos.argtypes = [
            wintypes.HWND,
            wintypes.HWND,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.UINT,
        ]
        user32.SetWindowPos.restype = wintypes.BOOL

        if user32.GetCursorPos(ctypes.byref(cursor)):
            monitor = user32.MonitorFromPoint(cursor, 2)
        else:
            foreground_window = user32.GetForegroundWindow()
            monitor = user32.MonitorFromWindow(foreground_window or hwnd, 2)
        if not monitor:
            return False
        if not user32.GetMonitorInfoW(monitor, ctypes.byref(monitor_info)):
            return False
        if not user32.GetWindowRect(hwnd, ctypes.byref(window_rect)):
            return False

        monitor_rect = monitor_info.rcMonitor
        window_width = window_rect.right - window_rect.left
        window_height = window_rect.bottom - window_rect.top
        x = monitor_rect.left + (monitor_rect.right - monitor_rect.left - window_width) // 2
        y = monitor_rect.top + (monitor_rect.bottom - monitor_rect.top - window_height) // 2

        no_size = 0x0001
        no_z_order = 0x0004
        no_activate = 0x0010
        return bool(
            user32.SetWindowPos(
                hwnd,
                None,
                x,
                y,
                0,
                0,
                no_size | no_z_order | no_activate,
            )
        )
    except Exception:
        return False


def _crash_log_path() -> Path:
    local_appdata = Path(
        os.environ.get("LOCALAPPDATA")
        or os.environ.get("APPDATA")
        or str(Path.home())
    )
    data_dir = local_appdata / "AiNoCraft" / "Launcher" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "launcher_crash.log"


def _write_crash_log() -> Path:
    log_path = _crash_log_path()
    with log_path.open("a", encoding="utf-8") as file:
        file.write("=" * 80 + "\n")
        file.write(f"[{datetime.now().isoformat()}] Unhandled exception\n")
        file.write(traceback.format_exc())
        file.write("\n")
    return log_path


def _show_error_dialog(message: str) -> None:
    if os.name != "nt":
        return
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, message, "AiNoCraft Launcher", 0x10)
    except Exception:
        pass


def _show_bootstrap_required_dialog() -> None:
    message = (
        "AiNoCraft Launcher запускается через основной файл AiNoCraft.exe.\n\n"
        "Он проверяет и устанавливает обновления лаунчера перед запуском."
    )
    if os.name != "nt":
        print(message, file=sys.stderr)
        return

    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, message, "AiNoCraft Launcher", 0x40)
    except Exception:
        pass


def main() -> int:
    from core.launch_guard import validate_bootstrap_launch

    launch_result = validate_bootstrap_launch()
    if not launch_result.allowed:
        _show_bootstrap_required_dialog()
        return 20

    import webview

    from config import (
        UI_INDEX_FILE,
        WINDOW_BACKGROUND_COLOR,
        WINDOW_HEIGHT,
        WINDOW_RESIZABLE,
        WINDOW_WIDTH,
        LAUNCHER_WINDOW_TITLE,
    )
    from core import downloader
    from core.updater import register_shutdown, startup_cleanup
    from ui.api import LauncherAPI

    startup_cleanup()

    if not UI_INDEX_FILE.exists():
        raise FileNotFoundError(f"UI file was not found: {UI_INDEX_FILE}")

    api = LauncherAPI()
    api.warmup()
    window = webview.create_window(
        title=LAUNCHER_WINDOW_TITLE,
        url=UI_INDEX_FILE.as_uri(),
        js_api=api,
        width=WINDOW_WIDTH,
        height=WINDOW_HEIGHT,
        resizable=WINDOW_RESIZABLE,
        frameless=True,
        easy_drag=False,
        hidden=True,
        background_color=WINDOW_BACKGROUND_COLOR,
        text_select=False,
    )
    api._set_window(window)
    register_shutdown(window.destroy)

    shown_once = {"done": False}

    def _show_after_first_load(*_args: object) -> None:
        if shown_once["done"]:
            return
        shown_once["done"] = True
        _center_window_on_cursor_monitor(window)
        window.show()

    window.events.loaded += _show_after_first_load
    webview.start(gui="edgechromium", debug=False)
    downloader.cleanup_on_exit()
    return 0


if __name__ == "__main__":
    try:
        exit_code = main()
    except Exception as exc:
        log_path = _write_crash_log()
        message = f"Лаунчер завершился с ошибкой.\n\n{exc}\n\nПодробности записаны в:\n{log_path}"
        print(message, file=sys.stderr)
        print(traceback.format_exc(), file=sys.stderr)
        _show_error_dialog(message)
        sys.exit(1)
    else:
        sys.exit(exit_code)
