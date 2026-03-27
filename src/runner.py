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


def run_workflow(config_path: str) -> int:
    cfg = load_json(config_path)
    app_cfg = cfg.get("app", {})
    export_cfg = cfg.get("export", {})
    workflow = cfg.get("workflow", [])

    if not workflow:
        logging.error("No workflow steps found in config.")
        return 1

    output_file = make_output_file(
        output_dir=export_cfg.get("output_dir", "exports"),
        prefix=export_cfg.get("prefix", "valves"),
        include_timestamp_utc=bool(export_cfg.get("include_timestamp_utc", True)),
        include_run_id=bool(export_cfg.get("include_run_id", True)),
    )

    logging.info("Resolved output path: %s", output_file)
    output_path = Path(output_file)
    if output_path.exists():
        logging.error("Output file collision detected, refusing to overwrite: %s", output_file)
        return 1

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

    if not output_path.exists():
        logging.error("Expected export file does not exist: %s", output_file)
        return 1

    if output_path.stat().st_size <= 0:
        logging.error("Export file is empty: %s", output_file)
        return 1

    logging.info("Workflow completed successfully: %s", output_file)
    print(f"SUCCESS: {output_file}")
    return 0
