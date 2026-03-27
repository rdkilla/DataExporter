from src.actions import SUPPORTED_ACTIONS, perform_action
from src.config_io import save_json
from src.config_schema import make_base_config, make_workflow_step
from src.control_discovery import control_to_dict, list_controls
from src.utils import ask_float, ask_int
from src.window_discovery import list_windows


def run_trainer(backend: str = "win32") -> int:
    windows = list_windows(backend=backend)
    if not windows:
        print("No windows found.")
        return 1

    print("\nOpen windows:\n")
    for i, window in enumerate(windows):
        print(
            f"[{i}] title='{window['title']}' "
            f"class='{window['class_name']}' handle='{window['handle']}'"
        )

    try:
        selected_window = windows[ask_int("\nSelect window number: ")]
    except Exception:
        print("Invalid selection.")
        return 1

    wrapper = selected_window["wrapper"]
    controls = list_controls(wrapper)
    if not controls:
        print("No controls found.")
        return 1

    workflow_steps = []
    while True:
        print("\nControls:\n")
        for i, control in enumerate(controls[:300]):
            info = control_to_dict(control)
            print(
                f"[{i}] Name='{info['name']}' | Type='{info['control_type']}' | "
                f"Class='{info['class_name']}' | AutomationId='{info['automation_id']}' | "
                f"Enabled={info['enabled']} Visible={info['visible']}"
            )

        choice = input("\nSelect control index, or [s]ave/[q]uit: ").strip().lower()
        if choice == "q":
            return 0
        if choice == "s":
            return _save_workflow(backend, selected_window, workflow_steps)

        try:
            control = controls[int(choice)]
        except Exception:
            print("Invalid control selection.")
            continue

        control_meta = control_to_dict(control)
        print("\nControl details:")
        for key, value in control_meta.items():
            print(f"- {key}: {value}")

        for idx, action in enumerate(SUPPORTED_ACTIONS, start=1):
            print(f"{idx}. {action}")

        raw_action = input("Choose action number (or blank to cancel): ").strip()
        if not raw_action:
            continue
        try:
            action = SUPPORTED_ACTIONS[int(raw_action) - 1]
        except Exception:
            print("Invalid action.")
            continue

        value = None
        if action in {"set_text", "type_keys", "send_keys"}:
            value = input("Enter action value: ")

        try:
            result = perform_action(control, action, value)
            print(f"Action completed: {result}")
        except Exception as exc:
            print(f"Action failed: {exc}")
            continue

        should_add = input("Add this action to workflow? [y/N]: ").strip().lower()
        if should_add != "y":
            continue

        step_name = input("Step name: ").strip() or f"step_{len(workflow_steps) + 1}"
        delay_after = ask_float("Delay after (seconds, default 0): ", default=0.0)
        retries = ask_int("Retries (default 0): ", default=0)

        workflow_steps.append(
            make_workflow_step(
                name=step_name,
                control={
                    "name": control_meta.get("name"),
                    "control_type": control_meta.get("control_type"),
                    "class_name": control_meta.get("class_name"),
                    "automation_id": control_meta.get("automation_id"),
                },
                action=action,
                value=value,
                delay_after=delay_after,
                retries=retries,
                window_matcher={"title": selected_window["title"]},
            )
        )
        print(f"Step saved in session. Total steps: {len(workflow_steps)}")


def _save_workflow(backend: str, selected_window: dict, workflow_steps: list) -> int:
    if not workflow_steps:
        print("No workflow steps collected. Nothing to save.")
        return 0

    output_dir = input("Export output directory [exports]: ").strip() or "exports"
    exe_path = input("Vendor exe path (optional): ").strip() or None
    config_path = input("Config file path [configs/vendor_export.json]: ").strip() or "configs/vendor_export.json"

    config = make_base_config(
        backend=backend,
        window_title_regex=f".*{selected_window['title']}.*",
        exe_path=exe_path,
        output_dir=output_dir,
    )
    config["workflow"] = workflow_steps

    save_json(config_path, config)
    print(f"Saved workflow to {config_path}")
    return 0
