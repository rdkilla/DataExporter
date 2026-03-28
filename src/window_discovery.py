from typing import List

from pywinauto import Desktop

NOISY_CLASSES = {
    "IME",
    "MSCTFIME UI",
    "GDI+ Hook Window Class",
    "Chrome_WidgetWin_1",
    "DVREventWindowClass",
    "CNEventWindowClass",
    "Progman",
}


def list_windows(backend: str = "win32", include_hidden: bool = False) -> List:
    desktop = Desktop(backend=backend)
    windows = []
    seen_handles = set()

    for window in desktop.windows():
        try:
            title = str(window.window_text()).strip()
            if not title:
                continue
            info = window.element_info
            handle = getattr(info, "handle", None)
            if handle in seen_handles:
                continue
            seen_handles.add(handle)

            class_name = getattr(info, "class_name", "")
            is_visible = _safe_call(window, "is_visible")
            is_enabled = _safe_call(window, "is_enabled")
            if not include_hidden and (
                not is_visible or not is_enabled or class_name in NOISY_CLASSES
            ):
                continue

            windows.append(
                {
                    "wrapper": window,
                    "title": title,
                    "class_name": class_name,
                    "handle": handle,
                    "process_id": getattr(info, "process_id", None),
                    "visible": is_visible,
                    "enabled": is_enabled,
                }
            )
        except Exception:
            continue

    return windows


def _safe_call(window, method_name: str):
    method = getattr(window, method_name, None)
    if method is None:
        return None
    try:
        return method()
    except Exception:
        return None
