from pywinauto.keyboard import send_keys


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


def perform_action(control, action: str, value: str | None = None) -> str:
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
        control.type_keys(value, with_spaces=True, pause=0.05)
        return "keys typed"

    if action == "send_keys":
        if value is None:
            raise ValueError("send_keys requires a value")
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
