import logging
import time
from pathlib import Path

from src.actions import perform_action
from src.config_io import load_json
from src.config_validation import validate_config
from src.utils import make_output_file


def _connect_window(app_cfg: dict, launch_if_needed: bool = True):
    from pywinauto import Application, Desktop

    backend = app_cfg.get("backend", "win32")
    title_re = app_cfg.get("window_title_regex", ".*")
    exe_path = app_cfg.get("exe_path")

    if launch_if_needed and exe_path and Path(exe_path).exists():
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


def run_workflow(config_path: str) -> int:
    cfg = load_json(config_path)
    validation_errors = validate_config(cfg)
    if validation_errors:
        logging.error("Configuration validation failed.")
        for error in validation_errors:
            logging.error(" - %s", error)
        return 1

    app_cfg = cfg.get("app", {})
    export_cfg = cfg.get("export", {})
    workflow = cfg.get("workflow", [])

    output_file = make_output_file(export_cfg.get("output_dir", "exports"))

    try:
        window = _connect_window(app_cfg)
        window.wait("visible", timeout=30)
    except Exception as exc:
        logging.exception("Failed to connect to target window: %s", exc)
        return 1

    for step in workflow:
        step_name = step.get("name", "<unnamed>")
        retries = int(step.get("retries", 0))
        delay_after = float(step.get("delay_after", 0))
        action = step["action"]
        control_cfg = step["control"]
        value = step.get("value")

        if value == "{output_file}":
            value = output_file

        attempt = 0
        while True:
            try:
                control = _find_control(window, control_cfg)
                control.wait("exists enabled visible ready", timeout=10)
                result = perform_action(control, action, value)
                if delay_after > 0:
                    time.sleep(delay_after)
                logging.info("Step succeeded: %s | %s", step_name, result)
                break
            except Exception as exc:
                attempt += 1
                logging.warning("Step failed: %s | attempt=%s | error=%s", step_name, attempt, exc)
                if attempt > retries:
                    logging.exception("Workflow failed on step: %s", step_name)
                    return 1
                time.sleep(1)

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


def check_workflow(config_path: str, resolve_selectors: bool = False) -> int:
    errors: list[str] = []

    try:
        cfg = load_json(config_path)
    except Exception as exc:
        print("CHECK FAILED")
        print(f"- Unable to load config '{config_path}': {exc}")
        return 1

    schema_errors = validate_config(cfg)
    errors.extend(schema_errors)

    if resolve_selectors and not errors:
        app_cfg = cfg.get("app", {})
        workflow = cfg.get("workflow", [])

        try:
            window = _connect_window(app_cfg, launch_if_needed=False)
            window.wait("visible", timeout=10)
        except Exception as exc:
            errors.append(
                "Unable to connect to the target window using app selectors "
                f"(backend/window_title_regex). Error: {exc}"
            )
        else:
            for index, step in enumerate(workflow):
                step_name = step.get("name", f"workflow[{index}]")
                control_cfg = step.get("control", {})
                try:
                    control = _find_control(window, control_cfg)
                    control.wait("exists enabled visible ready", timeout=10)
                except Exception as exc:
                    errors.append(
                        f"Step '{step_name}' control selector did not resolve. "
                        "Check control name/class_name/control_type/automation_id. "
                        f"Error: {exc}"
                    )

    if errors:
        print("CHECK FAILED")
        for error in errors:
            print(f"- {error}")
        print(f"Summary: {len(errors)} issue(s) found.")
        return 1

    check_type = "schema + selector connectivity" if resolve_selectors else "schema only"
    print("CHECK PASSED")
    print(f"Summary: 0 issues found ({check_type}).")
    return 0
