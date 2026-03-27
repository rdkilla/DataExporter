import logging
import time
from pathlib import Path

from pywinauto import Application, Desktop

from src.actions import perform_action
from src.config_io import load_json
from src.utils import make_output_file


def _connect_window(app_cfg: dict):
    backend = app_cfg.get("backend", "win32")
    title_re = app_cfg.get("window_title_regex", ".*")
    exe_path = app_cfg.get("exe_path")

    if exe_path and Path(exe_path).exists():
        try:
            app = Application(backend=backend).start(exe_path)
            time.sleep(2)
            return app.window(title_re=title_re)
        except Exception:
            logging.exception("Failed launching app, trying attach instead")

    desktop = Desktop(backend=backend)
    return desktop.window(title_re=title_re)


def _find_control(window, control_cfg: dict):
    return window.child_window(
        title=control_cfg.get("name") or None,
        control_type=control_cfg.get("control_type") or None,
        class_name=control_cfg.get("class_name") or None,
        auto_id=control_cfg.get("automation_id") or None,
    )


def _is_required_step(step: dict) -> bool:
    return bool(step.get("required", True))


def run_workflow(config_path: str, dry_run: bool = False) -> int:
    cfg = load_json(config_path)
    app_cfg = cfg.get("app", {})
    export_cfg = cfg.get("export", {})
    workflow = cfg.get("workflow", [])

    if not workflow:
        logging.error("No workflow steps found in config.")
        return 1

    output_file = make_output_file(export_cfg.get("output_dir", "exports"))

    try:
        window = _connect_window(app_cfg)
        window.wait("visible", timeout=30)
    except Exception as exc:
        logging.exception("Failed to connect to target window: %s", exc)
        return 1

    unresolvable_required_steps: list[str] = []
    resolved_steps: list[str] = []

    for step in workflow:
        step_name = step.get("name", "<unnamed>")
        retries = int(step.get("retries", 0))
        delay_after = float(step.get("delay_after", 0))
        action = step["action"]
        control_cfg = step["control"]
        required = _is_required_step(step)
        value = step.get("value")

        if value == "{output_file}":
            value = output_file

        attempt = 0
        while True:
            try:
                control = _find_control(window, control_cfg)
                control.wait("exists enabled visible ready", timeout=10)
                if dry_run:
                    resolved_steps.append(step_name)
                    logging.info("Dry-run step resolvable: %s | action=%s", step_name, action)
                    print(f"[DRY-RUN] RESOLVABLE: {step_name} (action={action})")
                    if action == "read_text":
                        try:
                            text = str(control.window_text())
                            logging.info("Dry-run read_text value: %s | value=%r", step_name, text)
                            print(f"[DRY-RUN] read_text current value for '{step_name}': {text!r}")
                        except Exception as exc:
                            logging.warning("Dry-run read_text capture failed: %s | error=%s", step_name, exc)
                            print(f"[DRY-RUN] read_text capture failed for '{step_name}': {exc}")
                else:
                    result = perform_action(control, action, value)
                    if delay_after > 0:
                        time.sleep(delay_after)
                    logging.info("Step succeeded: %s | %s", step_name, result)
                break
            except Exception as exc:
                attempt += 1
                logging.warning("Step failed: %s | attempt=%s | error=%s", step_name, attempt, exc)
                if attempt > retries:
                    if dry_run:
                        required_label = "required" if required else "optional"
                        logging.error(
                            "Dry-run step unresolvable: %s | action=%s | required=%s",
                            step_name,
                            action,
                            required,
                        )
                        print(f"[DRY-RUN] UNRESOLVABLE ({required_label}): {step_name} (action={action})")
                        if required:
                            unresolvable_required_steps.append(step_name)
                        break
                    logging.exception("Workflow failed on step: %s", step_name)
                    return 1
                time.sleep(1)

    if dry_run:
        logging.info(
            "Dry-run summary: resolvable=%s | required_unresolvable=%s",
            len(resolved_steps),
            len(unresolvable_required_steps),
        )
        if unresolvable_required_steps:
            print("[DRY-RUN] Required steps that are not resolvable:")
            for step_name in unresolvable_required_steps:
                print(f"  - {step_name}")
            return 1
        print(f"[DRY-RUN] SUCCESS: all required steps are resolvable ({len(resolved_steps)} step(s))")
        return 0

    path = Path(output_file)
    if not path.exists():
        logging.error("Expected export file does not exist: %s", output_file)
        return 1

    if path.stat().st_size <= 0:
        logging.error("Export file is empty: %s", output_file)
        return 1

    logging.info("Workflow completed successfully: %s", output_file)
    print(f"SUCCESS: {output_file}")
    return 0
