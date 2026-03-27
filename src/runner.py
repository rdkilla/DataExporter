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


def _find_control(window, control_cfg: dict, backend: str = "win32"):
    def _try_child_window(strategy: str, criteria: dict):
        control = window.child_window(**criteria)
        if control.exists(timeout=1):
            logging.info("Control selector matched using strategy=%s | criteria=%s", strategy, criteria)
            return control
        return None

    criteria = {
        "title": control_cfg.get("name") or control_cfg.get("title") or None,
        "control_type": control_cfg.get("control_type") or None,
        "class_name": control_cfg.get("class_name") or None,
        "auto_id": control_cfg.get("automation_id") or None,
    }

    exact_criteria = {k: v for k, v in criteria.items() if v is not None}
    if exact_criteria:
        control = _try_child_window("exact_attributes", exact_criteria)
        if control is not None:
            return control

    title_regex = control_cfg.get("title_regex") or control_cfg.get("title_re")
    if title_regex:
        regex_criteria = {
            "title_re": title_regex,
            "control_type": criteria.get("control_type"),
            "class_name": criteria.get("class_name"),
            "auto_id": criteria.get("auto_id"),
        }
        regex_criteria = {k: v for k, v in regex_criteria.items() if v is not None}
        control = _try_child_window("regex_title", regex_criteria)
        if control is not None:
            return control

    found_index = control_cfg.get("found_index")
    if found_index is not None:
        index_criteria = {"found_index": int(found_index)}
        for key in ("control_type", "class_name", "auto_id"):
            value = criteria.get(key)
            if value is not None:
                index_criteria[key] = value
        control = _try_child_window("found_index", index_criteria)
        if control is not None:
            return control

    coordinate_fallback = control_cfg.get("coordinates") or control_cfg.get("click_point")
    if coordinate_fallback and "x" in coordinate_fallback and "y" in coordinate_fallback:
        x = int(coordinate_fallback["x"])
        y = int(coordinate_fallback["y"])
        control = Desktop(backend=backend).from_point(x, y)
        logging.info("Control selector matched using strategy=coordinates | x=%s | y=%s", x, y)
        return control

    raise ValueError(f"No supported selector strategy found for control config: {control_cfg}")


def _resolve_step_window(default_window, app_cfg: dict, step_window_cfg: dict | None):
    if not step_window_cfg:
        return default_window

    backend = app_cfg.get("backend", "win32")
    matcher = {
        "title": step_window_cfg.get("title") or None,
        "title_re": step_window_cfg.get("title_regex") or step_window_cfg.get("title_re") or None,
        "class_name": step_window_cfg.get("class_name") or None,
        "handle": step_window_cfg.get("handle") or None,
    }
    matcher = {k: v for k, v in matcher.items() if v is not None}
    if not matcher:
        return default_window

    step_window = Desktop(backend=backend).window(**matcher)
    logging.info("Using step-specific window matcher: %s", matcher)
    return step_window


def run_workflow(config_path: str) -> int:
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

    for step in workflow:
        step_name = step.get("name", "<unnamed>")
        retries = int(step.get("retries", 0))
        delay_after = float(step.get("delay_after", 0))
        action = step["action"]
        control_cfg = step["control"]
        step_window_cfg = step.get("window")
        value = step.get("value")

        if value == "{output_file}":
            value = output_file

        attempt = 0
        while True:
            try:
                step_window = _resolve_step_window(window, app_cfg, step_window_cfg)
                step_window.wait("visible", timeout=10)
                control = _find_control(step_window, control_cfg, backend=app_cfg.get("backend", "win32"))
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
