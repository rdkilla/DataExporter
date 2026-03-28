import sys
from pathlib import Path

from src.actions import SUPPORTED_ACTIONS, perform_action
from src.cli_theme import CliTheme, build_theme
from src.config_io import save_json
from src.config_schema import make_base_config, make_workflow_step
from src.control_discovery import control_to_dict, list_controls
from src.utils import ask_float, ask_int
from src.window_discovery import list_windows


RESET = "\033[0m"
STYLES = {
    "heading": "\033[1;36m",
    "success": "\033[1;32m",
    "error": "\033[1;31m",
    "hint": "\033[0;33m",
    "row": "\033[0;37m",
}


def _should_use_color(no_color: bool) -> bool:
    if no_color:
        return False
    return sys.stdout.isatty()


def _style(text: str, tone: str, use_color: bool) -> str:
    if not use_color:
        return text
    return f"{STYLES[tone]}{text}{RESET}"


def print_heading(text: str, *, use_color: bool) -> None:
    print(_style(f"\n{text}:\n", "heading", use_color))


def print_row(text: str, *, use_color: bool) -> None:
    print(_style(text, "row", use_color))


def print_success(text: str, *, use_color: bool) -> None:
    print(_style(text, "success", use_color))


def print_error(text: str, *, use_color: bool) -> None:
    print(_style(text, "error", use_color))


def print_hint(text: str, *, use_color: bool) -> None:
    print(_style(text, "hint", use_color))


def run_trainer(backend: str = "win32", no_color: bool = False) -> int:
    use_color = _should_use_color(no_color)
    windows = list_windows(backend=backend, include_hidden=False)
    if not windows:
        windows = list_windows(backend=backend, include_hidden=True)
    if not windows:
        print_error("No windows found.", use_color=use_color)
        return 1

    print_heading("Open windows", use_color=use_color)
    if backend == "win32":
        print_hint("Tip: If controls look empty on Windows 11, retry with '--backend uia'.", use_color=use_color)
    for i, window in enumerate(windows):
        print_row(
            f"[{i}] title='{window['title']}' "
            f"class='{window['class_name']}' handle='{window['handle']}' "
            f"pid='{window['process_id']}' visible={window['visible']}",
            use_color=use_color,
        )
        ui.emit(f"{ui.status_pill(str(i), 'accent')} {window_summary}", "primary")

    try:
        selected_window = windows[ask_int(f"\n{ui.status_pill('SELECT', 'accent')} window number: ")]
    except Exception:
        print_error("Invalid selection.", use_color=use_color)
        return 1
    selected_window = windows[selected_index]

    wrapper = selected_window["wrapper"]
    controls = list_controls(wrapper)
    if not controls:
        print_error("No controls found.", use_color=use_color)
        return 1

    workflow_steps = []
    filter_text = ""
    page_size = 25
    page = 0
    while True:
        print_heading("Controls", use_color=use_color)
        for i, control in enumerate(controls[:300]):
            info = control_to_dict(control)
            display_name = info["name"] or "<no name>"
            display_type = info["control_type"] or "<unknown>"
            display_class = info["class_name"] or "<unknown>"
            print_row(
                f"[{i}] Name='{display_name}' | Type='{display_type}' | "
                f"Class='{display_class}' | AutomationId='{info['automation_id']}' | "
                f"Enabled={info['enabled']} Visible={info['visible']}",
                use_color=use_color,
            )
            choice = input(
                "\nSelect control index | commands: [n]ext [p]rev [f]ilter [d]etails [s]ave [q]uit: "
            ).strip().lower()
        else:
            print("\nControls:\n")
            for i, control in enumerate(controls[:300]):
                info = control_to_dict(control)
                display_name = info["name"] or "<no name>"
                display_type = info["control_type"] or "<unknown>"
                display_class = info["class_name"] or "<unknown>"
                print(
                    f"[{i}] Name='{display_name}' | Type='{display_type}' | "
                    f"Class='{display_class}' | AutomationId='{info['automation_id']}' | "
                    f"Enabled={info['enabled']} Visible={info['visible']}"
                )
            choice = input("\nSelect control index, or [s]ave/[q]uit: ").strip().lower()

        if choice == "q":
            ui.emit("Exiting trainer.", "muted")
            return 0
        if choice == "s":
            return _save_workflow(backend, selected_window, workflow_steps, use_color=use_color)

        try:
            control = controls[int(choice)]
            selected_control_index = int(choice)
        except Exception:
            print_error("Invalid control selection.", use_color=use_color)
            continue

        control_meta = control_to_dict(control)
        print_heading("Control details", use_color=use_color)
        for key, value in control_meta.items():
            print_row(f"- {key}: {value}", use_color=use_color)

        ui.emit_section("Actions")
        for idx, action in enumerate(SUPPORTED_ACTIONS, start=1):
            print_row(f"{idx}. {action}", use_color=use_color)

        raw_action = input(f"{icons['pointer']} Choose action number (or blank to cancel): ").strip()
        if not raw_action:
            continue
        try:
            action = SUPPORTED_ACTIONS[int(raw_action) - 1]
        except Exception:
            print_error("Invalid action.", use_color=use_color)
            continue

        value = None
        if action in {"set_text", "type_keys", "send_keys"}:
            value = input(
                f"{ui.status_pill('INPUT', 'muted')} action value "
                "(macros: {output_file}, {now}, {now:%Y%m%d_%H%M}): "
            )

        try:
            result = perform_action(control, action, value)
            print_success(f"Action completed: {result}", use_color=use_color)
        except Exception as exc:
            print_error(f"Action failed: {exc}", use_color=use_color)
            continue

        should_add = input(f"{ui.status_pill('INPUT', 'muted')} add action to workflow? [y/N]: ").strip().lower()
        if should_add != "y":
            continue

        step_name = input(f"{ui.status_pill('INPUT', 'muted')} step name: ").strip() or f"step_{len(workflow_steps) + 1}"
        delay_after = ask_float(
            f"{ui.status_pill('INPUT', 'muted')} delay after (seconds, default 0): ",
            default=0.0,
        )
        retries = ask_int(f"{ui.status_pill('INPUT', 'muted')} retries (default 0): ", default=0)

        workflow_steps.append(
            make_workflow_step(
                name=step_name,
                control={
                    "name": control_meta.get("name"),
                    "control_type": control_meta.get("control_type"),
                    "class_name": control_meta.get("class_name"),
                    "automation_id": control_meta.get("automation_id"),
                    "control_id": control_meta.get("control_id"),
                    "framework_id": control_meta.get("framework_id"),
                    "process_id": control_meta.get("process_id"),
                    "title_regex": _make_title_regex(control_meta.get("name")),
                    "found_index": selected_control_index,
                    "coordinates": control_meta.get("click_point"),
                },
                action=action,
                value=value,
                delay_after=delay_after,
                retries=retries,
                window_matcher={
                    "title": selected_window.get("title"),
                    "class_name": selected_window.get("class_name"),
                    "handle": selected_window.get("handle"),
                },
            )
        )
        print_success(f"Step saved in session. Total steps: {len(workflow_steps)}", use_color=use_color)


def _save_workflow(backend: str, selected_window: dict, workflow_steps: list, *, use_color: bool) -> int:
    if not workflow_steps:
        print_error("No workflow steps collected. Nothing to save.", use_color=use_color)
        return 0

    output_dir = input(f"{ui.status_pill('INPUT', 'muted')} export output directory [exports]: ").strip() or "exports"
    exe_path = input(f"{ui.status_pill('INPUT', 'muted')} vendor exe path (optional): ").strip() or None
    config_path = (
        input(f"{ui.status_pill('INPUT', 'muted')} config file path [configs/vendor_export.json]: ").strip()
        or "configs/vendor_export.json"
    )

    config = make_base_config(
        backend=backend,
        window_title_regex=f".*{selected_window['title']}.*",
        exe_path=exe_path,
        output_dir=output_dir,
    )
    config["workflow"] = workflow_steps

    save_json(config_path, config, base_dir=Path.cwd())
    print_success(f"Saved workflow to {config_path}", use_color=use_color)
    return 0


def _make_title_regex(name: str | None) -> str | None:
    if not name:
        return None
    escaped = "".join(f"\\{char}" if char in r".^$*+?{}[]|()" else char for char in name.strip())
    if not escaped:
        return None
    return f".*{escaped}.*"


def _menu_icons() -> dict[str, str]:
    fallback = {
        "ok": "[OK]",
        "warn": "[!]",
        "error": "[X]",
        "pointer": "->",
    }
    fancy = {
        "ok": "✅",
        "warn": "⚠️",
        "error": "❌",
        "pointer": "👉",
    }
    try:
        "".join(fancy.values()).encode("utf-8")
    except Exception:
        return fallback
    return fancy


def _advanced_menu_available() -> bool:
    encoding = (getattr(sys.stdout, "encoding", None) or "").lower()
    if "utf" not in encoding:
        return False
    return True


def _prompt_pick_index(items: list, prompt: str, invalid_message: str) -> int | None:
    try:
        index = ask_int(prompt)
        if index < 0 or index >= len(items):
            print(invalid_message)
            return None
        return index
    except Exception:
        print(invalid_message)
        return None


def _print_window_menu(windows: list[dict]) -> None:
    for i, window in enumerate(windows):
        print(
            f"[{i:>3}] "
            f"title='{window['title']}' class='{window['class_name']}' "
            f"handle='{window['handle']}' pid='{window['process_id']}' visible={window['visible']}"
        )


def _print_action_menu() -> None:
    icons = _menu_icons()
    print(f"\n{icons['pointer']} Action picker")
    for idx, action in enumerate(SUPPORTED_ACTIONS, start=1):
        print(f"[{idx:>2}] {action}")


def _filter_controls(controls: list, filter_text: str) -> list[tuple[int, dict]]:
    filtered = []
    lowered_filter = filter_text.strip().lower()
    for idx, control in enumerate(controls[:300]):
        info = control_to_dict(control)
        haystack = " ".join(
            [
                str(info.get("name", "")),
                str(info.get("control_type", "")),
                str(info.get("class_name", "")),
                str(info.get("automation_id", "")),
            ]
        ).lower()
        if lowered_filter and lowered_filter not in haystack:
            continue
        filtered.append((idx, info))
    return filtered


def _print_controls_menu(
    filtered_controls: list[tuple[int, dict]],
    page: int,
    page_size: int,
    filter_text: str,
    max_items: int,
) -> None:
    icons = _menu_icons()
    print(f"{icons['pointer']} Control picker")
    if filter_text:
        print(f"Filter: '{filter_text}'")
    total = len(filtered_controls)
    start = page * page_size
    end = min(start + page_size, total)
    print(f"Showing {start + 1 if total else 0}-{end} of {total} (max scanned: {max_items})")
    print(f"{'Idx':>5}  {'Name':<30} {'Type':<16} {'Class':<24} {'E/V':<5}")
    print("-" * 88)
    if not filtered_controls:
        print("(no controls match the current filter)")
        return

    for index, info in filtered_controls[start:end]:
        display_name = _trim(info.get("name") or "<no name>", 30)
        display_type = _trim(info.get("control_type") or "<unknown>", 16)
        display_class = _trim(info.get("class_name") or "<unknown>", 24)
        enabled = "Y" if info.get("enabled") else "N"
        visible = "Y" if info.get("visible") else "N"
        print(f"{index:>5}  {display_name:<30} {display_type:<16} {display_class:<24} {enabled}/{visible:<3}")


def _trim(text: str, width: int) -> str:
    if len(text) <= width:
        return text
    if width <= 1:
        return text[:width]
    return f"{text[: width - 1]}…"
