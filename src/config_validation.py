from pathlib import Path
from zoneinfo import ZoneInfo

from src.actions import SUPPORTED_ACTIONS
from src.path_safety import PathSafetyError, resolve_base_dir, resolve_write_path
from src.scheduler import SchedulePolicy


REQUIRED_TOP_LEVEL_KEYS = ("app", "export", "workflow")
REQUIRED_STEP_KEYS = ("name", "control", "action")
ACTIONS_REQUIRING_VALUE = {"set_text", "type_keys", "send_keys"}
SUPPORTED_BACKENDS = {"win32", "uia"}


def validate_config(config: dict, *, base_dir: str | Path | None = None) -> list[str]:
    errors: list[str] = []
    approved_base = resolve_base_dir(base_dir)

    if not isinstance(config, dict):
        return ["Configuration root must be a JSON object."]

    for key in REQUIRED_TOP_LEVEL_KEYS:
        if key not in config:
            errors.append(f"Missing required top-level key: '{key}'.")

    app = config.get("app")
    if not isinstance(app, dict):
        errors.append("'app' must be an object.")
    else:
        backend = app.get("backend")
        if not isinstance(backend, str) or backend.strip() not in SUPPORTED_BACKENDS:
            allowed = ", ".join(sorted(SUPPORTED_BACKENDS))
            errors.append(f"'app.backend' must be one of: {allowed}.")

        for optional_field in ("window_title_regex", "exe_path"):
            optional_value = app.get(optional_field)
            if optional_value is not None and not isinstance(optional_value, str):
                errors.append(f"'app.{optional_field}' must be a string when provided.")

    export = config.get("export")
    if not isinstance(export, dict):
        errors.append("'export' must be an object.")
    else:
        output_dir = export.get("output_dir")
        if not isinstance(output_dir, str) or not output_dir.strip():
            errors.append("'export.output_dir' must be a non-empty string.")
        else:
            try:
                resolve_write_path(output_dir, base_dir=approved_base, reject_symlink_traversal=True)
            except PathSafetyError as exc:
                errors.append(f"'export.output_dir' is not writable within approved base '{approved_base}': {exc}")

        has_schedule = "schedule" in export
        if not has_schedule:
            errors.append("'export.schedule' is required.")

        timezone_name = export.get("timezone")
        if timezone_name is None or not isinstance(timezone_name, str) or not timezone_name.strip():
            errors.append("'export.timezone' must be a non-empty IANA timezone string.")
        else:
            try:
                ZoneInfo(timezone_name)
            except Exception:
                errors.append(f"'export.timezone' is not a valid IANA timezone: '{timezone_name}'.")

        max_missed = export.get("max_missed_runs_to_catch_up")
        if max_missed is not None and (not isinstance(max_missed, int) or max_missed < 0):
            errors.append("'export.max_missed_runs_to_catch_up' must be a non-negative integer.")

        if has_schedule:
            try:
                SchedulePolicy.from_export_config(export)
            except Exception as exc:
                errors.append(f"'export.schedule' configuration is invalid: {exc}")

    alerts = config.get("alerts")
    if alerts is not None:
        if not isinstance(alerts, dict):
            errors.append("'alerts' must be an object when provided.")
        else:
            enabled = alerts.get("enabled")
            if enabled is not None and not isinstance(enabled, bool):
                errors.append("'alerts.enabled' must be a boolean when provided.")

            failure_threshold = alerts.get("failure_threshold")
            if failure_threshold is not None and (not isinstance(failure_threshold, int) or failure_threshold < 1):
                errors.append("'alerts.failure_threshold' must be an integer >= 1 when provided.")

            sla_hours = alerts.get("sla_hours")
            if sla_hours is not None and not isinstance(sla_hours, (int, float)):
                errors.append("'alerts.sla_hours' must be a number when provided.")
            elif isinstance(sla_hours, (int, float)) and sla_hours <= 0:
                errors.append("'alerts.sla_hours' must be > 0 when provided.")

            output_path = alerts.get("output_path")
            if output_path is not None and (not isinstance(output_path, str) or not output_path.strip()):
                errors.append("'alerts.output_path' must be a non-empty string when provided.")
            elif isinstance(output_path, str):
                try:
                    resolve_write_path(output_path, base_dir=approved_base, reject_symlink_traversal=True)
                except PathSafetyError as exc:
                    errors.append(
                        f"'alerts.output_path' is not writable within approved base '{approved_base}': {exc}"
                    )

    workflow = config.get("workflow")
    if not isinstance(workflow, list):
        errors.append("'workflow' must be a list of step objects.")
        return errors

    if not workflow:
        errors.append("'workflow' must contain at least one step.")
        return errors

    for index, step in enumerate(workflow):
        step_label = f"workflow[{index}]"
        if not isinstance(step, dict):
            errors.append(f"{step_label} must be an object.")
            continue

        for key in REQUIRED_STEP_KEYS:
            if key not in step:
                errors.append(f"{step_label} missing required key: '{key}'.")

        if "name" in step:
            name = step.get("name")
            if not isinstance(name, str) or not name.strip():
                errors.append(f"{step_label}.name must be a non-empty string.")

        control = step.get("control")
        if "control" in step and not isinstance(control, dict):
            errors.append(f"{step_label}.control must be an object.")

        action = step.get("action")
        if "action" in step:
            if not isinstance(action, str) or not action.strip():
                errors.append(f"{step_label}.action must be a non-empty string.")
            elif action not in SUPPORTED_ACTIONS:
                allowed = ", ".join(SUPPORTED_ACTIONS)
                errors.append(
                    f"{step_label}.action '{action}' is not supported. Allowed actions: {allowed}."
                )

        if action in ACTIONS_REQUIRING_VALUE:
            value = step.get("value")
            if not isinstance(value, str) or not value.strip():
                errors.append(
                    f"{step_label}.value is required and must be a non-empty string for action '{action}'."
                )

    return errors
