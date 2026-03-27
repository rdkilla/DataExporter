import json
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pywinauto import Application, Desktop

from src.actions import perform_action
from src.config_io import load_json
from src.utils import make_output_file

_ALERT_STATE_FILE = ".data_exporter_alert_state.json"
_EVENT_LOG_SOURCE = "DataExporter"


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


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _to_iso8601(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _from_iso8601(value: str | None) -> datetime | None:
    if not value:
        return None

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        logging.warning("Could not parse timestamp in alert state: %s", value)
        return None


def _write_windows_event_log(message: str, *, event_type: str = "error") -> None:
    try:
        import win32evtlog  # type: ignore
        import win32evtlogutil  # type: ignore
    except Exception:
        logging.info("Windows Event Log libraries unavailable; skipping Event Log write")
        return

    event_map = {
        "error": win32evtlog.EVENTLOG_ERROR_TYPE,
        "warning": win32evtlog.EVENTLOG_WARNING_TYPE,
        "info": win32evtlog.EVENTLOG_INFORMATION_TYPE,
    }
    safe_event_type = event_map.get(event_type, win32evtlog.EVENTLOG_ERROR_TYPE)

    try:
        win32evtlogutil.ReportEvent(
            appName=_EVENT_LOG_SOURCE,
            eventID=1000,
            eventCategory=0,
            eventType=safe_event_type,
            strings=[message],
            data=b"",
        )
    except Exception:
        logging.exception("Failed writing Windows Event Log entry")


def _write_alert_file(output_path: Path, *, alert_kind: str, message: str, metadata: dict | None = None) -> Path:
    output_path.mkdir(parents=True, exist_ok=True)
    ts = _utc_now().strftime("%Y%m%dT%H%M%SZ")
    alert_file = output_path / f"alert_{alert_kind}_{ts}.json"
    payload = {
        "alert_type": alert_kind,
        "message": message,
        "created_utc": _to_iso8601(_utc_now()),
        "metadata": metadata or {},
    }
    alert_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return alert_file


def _load_alert_state(output_path: Path) -> dict:
    state_path = output_path / _ALERT_STATE_FILE
    if not state_path.exists():
        return {
            "first_run_utc": None,
            "last_run_utc": None,
            "last_success_utc": None,
            "consecutive_failures": 0,
            "failure_alert_sent_for": 0,
            "stale_alert_active": False,
        }

    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        logging.exception("Failed to read alert state file; resetting state")
        return {
            "first_run_utc": None,
            "last_run_utc": None,
            "last_success_utc": None,
            "consecutive_failures": 0,
            "failure_alert_sent_for": 0,
            "stale_alert_active": False,
        }


def _save_alert_state(output_path: Path, state: dict) -> None:
    output_path.mkdir(parents=True, exist_ok=True)
    state_path = output_path / _ALERT_STATE_FILE
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _emit_alert(alerts_cfg: dict, *, alert_kind: str, message: str, metadata: dict | None = None, event_type: str = "error") -> None:
    output_path = Path(alerts_cfg.get("output_path") or "alerts")
    try:
        alert_file = _write_alert_file(output_path, alert_kind=alert_kind, message=message, metadata=metadata)
        logging.error("ALERT emitted (%s): %s | file=%s", alert_kind, message, alert_file)
    except Exception:
        logging.exception("Failed to write alert file for %s", alert_kind)

    _write_windows_event_log(f"[{alert_kind}] {message}", event_type=event_type)


def _run_workflow_cfg(cfg: dict) -> int:
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
                step_window = _resolve_step_window(window, app_cfg, step_window_cfg)
                step_window.wait("visible", timeout=10)
                control = _find_control(step_window, control_cfg, backend=app_cfg.get("backend", "win32"))
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


def _handle_alerts_for_run(cfg: dict, run_status: int) -> None:
    alerts_cfg = cfg.get("alerts", {})
    if not alerts_cfg.get("enabled", False):
        return

    output_path = Path(alerts_cfg.get("output_path") or "alerts")
    failure_threshold = max(int(alerts_cfg.get("failure_threshold", 3)), 1)
    sla_hours = float(alerts_cfg.get("sla_hours", 24))

    now = _utc_now()
    now_iso = _to_iso8601(now)

    state = _load_alert_state(output_path)
    state.setdefault("consecutive_failures", 0)
    state.setdefault("failure_alert_sent_for", 0)
    state.setdefault("stale_alert_active", False)

    if not state.get("first_run_utc"):
        state["first_run_utc"] = now_iso
    state["last_run_utc"] = now_iso

    if run_status == 0:
        state["last_success_utc"] = now_iso
        state["consecutive_failures"] = 0
        state["failure_alert_sent_for"] = 0
        state["stale_alert_active"] = False
    else:
        state["consecutive_failures"] = int(state.get("consecutive_failures", 0)) + 1
        consecutive_failures = int(state["consecutive_failures"])
        already_sent_for = int(state.get("failure_alert_sent_for", 0))
        if consecutive_failures >= failure_threshold and already_sent_for < failure_threshold:
            _emit_alert(
                alerts_cfg,
                alert_kind="failure_threshold",
                message=(
                    f"Workflow has failed {consecutive_failures} consecutive run(s), "
                    f"meeting configured threshold ({failure_threshold})."
                ),
                metadata={
                    "consecutive_failures": consecutive_failures,
                    "failure_threshold": failure_threshold,
                },
            )
            state["failure_alert_sent_for"] = failure_threshold

    if sla_hours > 0:
        reference_dt = _from_iso8601(state.get("last_success_utc")) or _from_iso8601(state.get("first_run_utc"))
        stale_active = bool(state.get("stale_alert_active", False))
        if reference_dt:
            deadline = reference_dt + timedelta(hours=sla_hours)
            if now >= deadline and not stale_active:
                _emit_alert(
                    alerts_cfg,
                    alert_kind="stale_data",
                    message=(
                        "No successful run observed within SLA window "
                        f"({sla_hours:g} hours)."
                    ),
                    metadata={
                        "sla_hours": sla_hours,
                        "reference_time_utc": _to_iso8601(reference_dt),
                        "deadline_utc": _to_iso8601(deadline),
                        "last_success_utc": state.get("last_success_utc"),
                    },
                    event_type="warning",
                )
                state["stale_alert_active"] = True

    _save_alert_state(output_path, state)


def run_workflow(config_path: str) -> int:
    cfg = load_json(config_path)
    status = _run_workflow_cfg(cfg)
    _handle_alerts_for_run(cfg, status)
    return status
