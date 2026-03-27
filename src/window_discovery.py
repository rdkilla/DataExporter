from typing import List

from pywinauto import Desktop


def list_windows(backend: str = "win32") -> List:
    desktop = Desktop(backend=backend)
    windows = []

    for window in desktop.windows():
        try:
            title = str(window.window_text()).strip()
            if not title:
                continue
            info = window.element_info
            windows.append(
                {
                    "wrapper": window,
                    "title": title,
                    "class_name": getattr(info, "class_name", ""),
                    "handle": getattr(info, "handle", None),
                }
            )
        except Exception:
            continue

    return windows
