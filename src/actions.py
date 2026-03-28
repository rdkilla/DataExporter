SUPPORTED_ACTIONS = [
    "click_input",
    "double_click_input",
    "right_click_input",
    "set_focus",
    "read_text",
    "set_text",
    "type_keys",
    "send_keys",
    "print_children",
    "print_control_identifiers",
]


DEFAULT_SECURITY_CONFIG = {
    "allow_global_send_keys": False,
    "interactive_confirmation_required": False,
    "require_focused_window_for_keyboard_input": True,
    "allow_unfocused_window_keyboard_input": False,
    "allow_dangerous_key_chords": False,
    "dangerous_key_chords_denylist": [
        "^%{DELETE}",
        "%{F4}",
        "#{l}",
        "#{r}",
        "^{ESC}",
        "#{d}",
    ],
}


def _normalize_chord(value: str) -> str:
    return "".join(value.split()).lower()


def _merge_security_config(security_config: dict | None) -> dict:
    merged = dict(DEFAULT_SECURITY_CONFIG)
    if isinstance(security_config, dict):
        merged.update(security_config)
    return merged


def _window_handle(window) -> int | None:
    handle = getattr(window, "handle", None)
    if handle:
        return int(handle)
    element_info = getattr(window, "element_info", None)
    if element_info is not None:
        info_handle = getattr(element_info, "handle", None)
        if info_handle:
            return int(info_handle)
    return None


def _window_title(window) -> str:
    try:
        return str(window.window_text())
    except Exception:
        return ""


def _foreground_window_handle() -> int | None:
    try:
        from ctypes import windll

        handle = int(windll.user32.GetForegroundWindow())
        return handle or None
    except Exception:
        return None


def _foreground_window_title() -> str:
    active_handle = _foreground_window_handle()
    if active_handle is None:
        return ""
    try:
        from pywinauto import Desktop

        active_window = Desktop(backend="win32").window(handle=active_handle)
        return _window_title(active_window)
    except Exception:
        return ""


def _ensure_keyboard_action_allowed(action: str, value: str, security_cfg: dict, expected_window) -> None:
    if bool(security_cfg.get("interactive_confirmation_required")):
        raise ValueError(
            "Blocked by security policy: keyboard action requires interactive confirmation. "
            "Set 'security.interactive_confirmation_required' to false to allow unattended runs."
        )

    if action == "send_keys" and not bool(security_cfg.get("allow_global_send_keys")):
        raise ValueError(
            "Blocked by security policy: global send_keys is disabled. "
            "Set 'security.allow_global_send_keys' to true only if this is intentionally required."
        )

    denylist = security_cfg.get("dangerous_key_chords_denylist", [])
    if not isinstance(denylist, list):
        denylist = []
    normalized_value = _normalize_chord(value)
    if not bool(security_cfg.get("allow_dangerous_key_chords")):
        for chord in denylist:
            if not isinstance(chord, str):
                continue
            if _normalize_chord(chord) and _normalize_chord(chord) in normalized_value:
                raise ValueError(
                    "Blocked by security policy: key sequence matches denylisted dangerous chord "
                    f"'{chord}'. Set 'security.allow_dangerous_key_chords' to true or adjust "
                    "'security.dangerous_key_chords_denylist' for explicit override."
                )

    require_focus = bool(security_cfg.get("require_focused_window_for_keyboard_input", True))
    allow_unfocused = bool(security_cfg.get("allow_unfocused_window_keyboard_input", False))
    if not require_focus or allow_unfocused:
        return

    if expected_window is None:
        raise ValueError(
            "Blocked by security policy: unable to verify focused window for keyboard input. "
            "Provide expected window context or set 'security.allow_unfocused_window_keyboard_input' to true."
        )

    expected_handle = _window_handle(expected_window)
    expected_title = _window_title(expected_window)
    active_handle = _foreground_window_handle()

    if expected_handle is not None and active_handle is not None and active_handle != expected_handle:
        raise ValueError(
            "Blocked by security policy: active window does not match expected target window "
            f"(expected_handle={expected_handle}, active_handle={active_handle}, "
            f"expected_title={expected_title!r})."
        )

    if expected_handle is None and expected_title:
        active_title = _foreground_window_title()
        if active_title != expected_title:
            raise ValueError(
                "Blocked by security policy: active window title does not match expected target window "
                f"(expected_title={expected_title!r}, active_title={active_title!r})."
            )


def perform_action(
    control,
    action: str,
    value: str | None = None,
    security_config: dict | None = None,
    expected_window=None,
) -> str:
    security_cfg = _merge_security_config(security_config)

    if action == "click_input":
        control.click_input()
        return "clicked"

    if action == "double_click_input":
        control.double_click_input()
        return "double clicked"

    if action == "right_click_input":
        control.right_click_input()
        return "right clicked"

    if action == "set_focus":
        control.set_focus()
        return "focused"

    if action == "read_text":
        text = control.window_text()
        return str(text)

    if action == "set_text":
        if value is None:
            raise ValueError("set_text requires a value")
        try:
            control.set_edit_text(value)
        except Exception:
            control.set_text(value)
        return "text set"

    if action == "type_keys":
        if value is None:
            raise ValueError("type_keys requires a value")
        expected = expected_window or control.top_level_parent()
        _ensure_keyboard_action_allowed(action, value, security_cfg, expected)
        control.type_keys(value, with_spaces=True, pause=0.05)
        return "keys typed"

    if action == "send_keys":
        if value is None:
            raise ValueError("send_keys requires a value")
        expected = expected_window or control.top_level_parent()
        _ensure_keyboard_action_allowed(action, value, security_cfg, expected)
        from pywinauto.keyboard import send_keys

        send_keys(value)
        return "global keys sent"

    if action == "print_children":
        lines = []
        for child in control.children():
            lines.append(str(child))
        return "\n".join(lines)

    if action == "print_control_identifiers":
        control.print_control_identifiers()
        return "control identifiers printed"

    raise ValueError(f"Unsupported action: {action}")
