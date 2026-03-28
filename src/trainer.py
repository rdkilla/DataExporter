from pathlib import Path

from src.actions import SUPPORTED_ACTIONS, perform_action
from src.cli_theme import CliTheme, build_theme
from src.config_io import save_json
from src.config_schema import make_base_config, make_workflow_step
from src.control_discovery import control_to_dict, list_controls
from src.utils import ask_float, ask_int
from src.window_discovery import list_windows


def run_trainer(backend: str = "win32", theme: CliTheme | None = None) -> int:
    ui = theme or build_theme()
    ui.emit_banner("Interactive Trainer", f"Backend: {backend}")

    windows = list_windows(backend=backend, include_hidden=False)
    if not windows:
        windows = list_windows(backend=backend, include_hidden=True)
    if not windows:
        ui.emit("No windows found.", "error")
        return 1

    ui.emit_section("Open windows")
    if backend == "win32":
        ui.emit(
            "Tip: If controls look empty on Windows 11, retry with '--backend uia'.",
            "muted",
        )
    for i, window in enumerate(windows):
        window_summary = (
            f"title='{window['title']}' class='{window['class_name']}' "
            f"handle='{window['handle']}' pid='{window['process_id']}' "
            f"visible={window['visible']}"
        )
        ui.emit(f"{ui.status_pill(str(i), 'accent')} {window_summary}", "primary")

    try:
        selected_window = windows[ask_int(f"\n{ui.status_pill('SELECT', 'accent')} window number: ")]
    except Exception:
        ui.emit("Invalid selection.", "error")
        return 1

    wrapper = selected_window["wrapper"]
    controls = list_controls(wrapper)
    if not controls:
        ui.emit("No controls found.", "error")
        return 1

    workflow_steps = []
    while True:
        ui.emit_section("Controls")
        for i, control in enumerate(controls[:300]):
            info = control_to_dict(control)
            display_name = info["name"] or "<no name>"
            display_type = info["control_type"] or "<unknown>"
            display_class = info["class_name"] or "<unknown>"
            ui.emit(
                f"{ui.status_pill(str(i), 'accent')} Name='{display_name}' | Type='{display_type}' | "
                f"Class='{display_class}' | AutomationId='{info['automation_id']}' | "
                f"Enabled={info['enabled']} Visible={info['visible']}",
                "primary",
            )

        choice = input(f"\n{ui.status_pill('INPUT', 'muted')} control index, or [s]ave/[q]uit: ").strip().lower()
        if choice == "q":
            ui.emit("Exiting trainer.", "muted")
            return 0
        if choice == "s":
            return _save_workflow(backend, selected_window, workflow_steps, ui)

        try:
            control = controls[int(choice)]
        except Exception:
            ui.emit("Invalid control selection.", "error")
            continue

        control_meta = control_to_dict(control)
        ui.emit_section("Control details")
        for key, value in control_meta.items():
            ui.emit(ui.key_value_row(key, value, key_style="muted", value_style="primary"), "primary")

        ui.emit_section("Actions")
        for idx, action in enumerate(SUPPORTED_ACTIONS, start=1):
            ui.emit(f"{ui.status_pill(str(idx), 'accent')} {action}", "primary")

        raw_action = input(f"{ui.status_pill('INPUT', 'muted')} action number (blank to cancel): ").strip()
        if not raw_action:
            continue
        try:
            action = SUPPORTED_ACTIONS[int(raw_action) - 1]
        except Exception:
            ui.emit("Invalid action.", "error")
            continue

        value = None
        if action in {"set_text", "type_keys", "send_keys"}:
            value = input(
                f"{ui.status_pill('INPUT', 'muted')} action value "
                "(macros: {output_file}, {now}, {now:%Y%m%d_%H%M}): "
            )

        try:
            result = perform_action(control, action, value)
            ui.emit(f"Action completed: {result}", "success")
        except Exception as exc:
            ui.emit(f"Action failed: {exc}", "error")
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
                    "found_index": int(choice),
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
        ui.emit(f"Step saved in session. Total steps: {len(workflow_steps)}", "success")


def _save_workflow(backend: str, selected_window: dict, workflow_steps: list, ui: CliTheme) -> int:
    if not workflow_steps:
        ui.emit("No workflow steps collected. Nothing to save.", "muted")
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
    ui.emit(f"Saved workflow to {config_path}", "success")
    return 0


def _make_title_regex(name: str | None) -> str | None:
    if not name:
        return None
    escaped = "".join(f"\\{char}" if char in r".^$*+?{}[]|()" else char for char in name.strip())
    if not escaped:
        return None
    return f".*{escaped}.*"
