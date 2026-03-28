def list_controls(window) -> list:
    try:
        return window.descendants()
    except Exception:
        return []


def control_to_dict(control) -> dict:
    info = _safe_attr(control, "element_info")
    name = _safe_text(control)
    control_type = _safe_attr(info, "control_type", default="")
    class_name = _safe_attr(info, "class_name", default="")
    automation_id = _safe_attr(info, "automation_id", default="")
    control_id = _safe_attr(info, "control_id", default=None)
    framework_id = _safe_attr(info, "framework_id", default="")
    process_id = _safe_attr(info, "process_id", default=None)
    handle = _safe_attr(info, "handle", default=None)
    enabled = _safe_call(control, "is_enabled")
    visible = _safe_call(control, "is_visible")
    rectangle = _safe_call(control, "rectangle")
    click_point = None
    rect_text = ""

    if rectangle is not None:
        rect_text = f"({rectangle.left},{rectangle.top},{rectangle.right},{rectangle.bottom})"
        center = _safe_call(rectangle, "mid_point")
        if center is not None:
            click_point = {"x": center.x, "y": center.y}

    children = _safe_call(control, "children")
    child_count = len(children) if children is not None else None

    return {
        "name": name,
        "control_type": control_type,
        "class_name": class_name,
        "automation_id": automation_id,
        "control_id": control_id,
        "framework_id": framework_id,
        "process_id": process_id,
        "enabled": enabled,
        "visible": visible,
        "rectangle": rect_text,
        "click_point": click_point,
        "handle": handle,
        "child_count": child_count,
        "readable_text": name,
    }


def _safe_call(control, method_name: str):
    method = getattr(control, method_name, None)
    if method is None:
        return None
    try:
        return method()
    except Exception:
        return None


def _safe_attr(obj, attr_name: str, default=None):
    if obj is None:
        return default
    try:
        return getattr(obj, attr_name, default)
    except Exception:
        return default


def _safe_text(control) -> str:
    raw = _safe_call(control, "window_text")
    if raw is None:
        return ""
    return str(raw).strip()
