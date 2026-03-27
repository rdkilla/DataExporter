def list_controls(window) -> list:
    try:
        return window.descendants()
    except Exception:
        return []


def control_to_dict(control) -> dict:
    try:
        info = control.element_info
        rectangle = control.rectangle()
        children = control.children()
        return {
            "name": str(control.window_text()).strip(),
            "control_type": getattr(info, "control_type", ""),
            "class_name": getattr(info, "class_name", ""),
            "automation_id": getattr(info, "automation_id", ""),
            "enabled": _safe_call(control, "is_enabled"),
            "visible": _safe_call(control, "is_visible"),
            "rectangle": f"({rectangle.left},{rectangle.top},{rectangle.right},{rectangle.bottom})",
            "handle": getattr(info, "handle", None),
            "child_count": len(children),
            "readable_text": str(control.window_text()).strip(),
        }
    except Exception:
        return {
            "name": "",
            "control_type": "",
            "class_name": "",
            "automation_id": "",
            "enabled": None,
            "visible": None,
            "rectangle": "",
            "handle": None,
            "child_count": None,
            "readable_text": "",
        }


def _safe_call(control, method_name: str):
    method = getattr(control, method_name, None)
    if method is None:
        return None
    try:
        return method()
    except Exception:
        return None
