import hashlib
import json
import logging
import math
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from src.actions import perform_action
from src.config_io import load_json
from src.config_validation import validate_config
from src.utils import make_output_file

_ALERT_STATE_FILE = ".data_exporter_alert_state.json"
_EVENT_LOG_SOURCE = "DataExporter"
_DEFAULT_NOW_FORMAT = "%Y-%m-%d_%H%M%S"
_STEP_RETRIES_MIN = 0
_STEP_RETRIES_MAX = 10
_STEP_DELAY_AFTER_MIN = 0.0
_STEP_DELAY_AFTER_MAX = 30.0


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


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


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_manifest(start_ts: str, manifest: dict) -> None:
    date_prefix = _utc_now().strftime("%Y-%m-%d")
    run_suffix = _utc_now().strftime("%H%M%S_%f")
    manifest_dir = Path("logs") / "manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / f"{date_prefix}_{run_suffix}_run.json"
    with manifest_path.open("w", encoding="utf-8") as fh:
        json.dump({"timestamp_start_utc": start_ts, **manifest}, fh, indent=2)
    logging.info("Wrote run manifest: %s", manifest_path)


def _connect_window(app_cfg: dict):
    from pywinauto import Application, Desktop

    backend = app_cfg.get("backend", "win32")
    title_re = app_cfg.get("window_title_regex", ".*")
    exe_path = app_cfg.get("exe_path")
    launch_if_needed = bool(app_cfg.get("launch_if_needed", True))

    if launch_if_needed and exe_path and Path(exe_path).exists():
        try:
            app = Application(backend=backend).start(exe_path)
            time.sleep(2)
            return app.window(title_re=title_re)
        except Exception:
            logging.exception("Failed launching app, trying attach instead")

    desktop = Desktop(backend=backend)
    return desktop.window(title_re=title_re)


_NOW_MACRO_PATTERN = re.compile(r"\{now(?::([^{}]+))?\}")


def _resolve_step_value(value: Any, *, output_file: str, now_utc: datetime) -> Any:
    """
    Resolve runtime macros for a workflow step value.

    Supported macros:
    - {output_file}: full generated output path for the current run.
    - {now}: UTC timestamp using _DEFAULT_NOW_FORMAT.
    - {now:<strftime>}: UTC timestamp using a custom strftime pattern.

    Any non-string value is returned unchanged.
    """
    if not isinstance(value, str):
        return value

    resolved = value.replace("{output_file}", output_file)

    def _replace_now(match: re.Match[str]) -> str:
        fmt = match.group(1)
        if not fmt:
            return now_utc.strftime(_DEFAULT_NOW_FORMAT)
        try:
            return now_utc.strftime(fmt)
        except Exception as exc:
            raise ValueError(f"Invalid {{now:...}} strftime format '{fmt}' in step value '{value}'") from exc

    return _NOW_MACRO_PATTERN.sub(_replace_now, resolved)


def _find_control(window, control_cfg: dict, backend: str = "win32"):
    from pywinauto import Desktop

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
        index_criteria: dict[str, Any] = {"found_index": int(found_index)}
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

    from pywinauto import Desktop

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


def _is_required_step(step: dict) -> bool:
    return bool(step.get("required", True))


def _build_manifest(app_cfg: dict, export_cfg: dict, output_file: str, dry_run: bool) -> dict[str, Any]:
    return {
        "timestamp_requested_utc": _utc_now_iso(),
        "mode": "dry_run" if dry_run else "run",
        "app": {
            "backend": app_cfg.get("backend", "win32"),
            "window_matcher": {
                "title_regex": app_cfg.get("window_title_regex", ".*"),
                "exe_path": app_cfg.get("exe_path"),
            },
        },
        "export": {
            "output_file": output_file,
            "output_dir": export_cfg.get("output_dir", "exports"),
        },
        "workflow_steps": [],
        "overall_result": "failed",
    }


def _should_redact_ui_text(cfg: dict) -> bool:
    logging_cfg = cfg.get("logging")
    if not isinstance(logging_cfg, dict):
        return True
    redact_value = logging_cfg.get("redact_ui_text", True)
    return bool(redact_value)


def _validated_step_retries(step: dict, step_name: str) -> int:
    retries = step.get("retries", 0)
    if isinstance(retries, bool) or not isinstance(retries, int):
        raise ValueError(
            f"Step '{step_name}' has invalid retries={retries!r}; expected integer in "
            f"[{_STEP_RETRIES_MIN}, {_STEP_RETRIES_MAX}]"
        )
    if not (_STEP_RETRIES_MIN <= retries <= _STEP_RETRIES_MAX):
        raise ValueError(
            f"Step '{step_name}' retries out of range ({retries}); expected "
            f"[{_STEP_RETRIES_MIN}, {_STEP_RETRIES_MAX}]"
        )
    return retries


def _validated_step_delay_after(step: dict, step_name: str) -> float:
    delay_after = step.get("delay_after", 0)
    if isinstance(delay_after, bool) or not isinstance(delay_after, (int, float)):
        raise ValueError(
            f"Step '{step_name}' has invalid delay_after={delay_after!r}; expected number in "
            f"[{_STEP_DELAY_AFTER_MIN:g}, {_STEP_DELAY_AFTER_MAX:g}] seconds"
        )
    delay_after_float = float(delay_after)
    if not math.isfinite(delay_after_float):
        raise ValueError(f"Step '{step_name}' has non-finite delay_after={delay_after!r}")
    if not (_STEP_DELAY_AFTER_MIN <= delay_after_float <= _STEP_DELAY_AFTER_MAX):
        raise ValueError(
            f"Step '{step_name}' delay_after out of range ({delay_after_float}); expected "
            f"[{_STEP_DELAY_AFTER_MIN:g}, {_STEP_DELAY_AFTER_MAX:g}] seconds"
        )
    return delay_after_float


def _run_workflow_cfg(cfg: dict, *, dry_run: bool = False) -> tuple[int, str | None]:
    app_cfg = cfg.get("app", {})
    export_cfg = cfg.get("export", {})
    workflow = cfg.get("workflow", [])

    output_file = make_output_file(
        output_dir=export_cfg.get("output_dir", "exports"),
        prefix=export_cfg.get("prefix", "valves"),
        include_timestamp_utc=bool(export_cfg.get("include_timestamp_utc", True)),
        include_run_id=bool(export_cfg.get("include_run_id", True)),
    )

    started_at_utc = _utc_now_iso()
    manifest = _build_manifest(app_cfg, export_cfg, output_file, dry_run)

    if not workflow:
        logging.error("No workflow steps found in config.")
        manifest["error"] = "No workflow steps found in config."
        manifest["timestamp_end_utc"] = _utc_now_iso()
        _write_manifest(started_at_utc, manifest)
        return 1, None

    logging.info("Resolved output path: %s", output_file)
    output_path = Path(output_file)
    if output_path.exists():
        logging.error("Output file collision detected, refusing to overwrite: %s", output_file)
        manifest["error"] = f"Output file collision detected: {output_file}"
        manifest["timestamp_end_utc"] = _utc_now_iso()
        _write_manifest(started_at_utc, manifest)
        return 1, None

    try:
        window = _connect_window(app_cfg)
        window.wait("visible", timeout=30)
    except Exception as exc:
        logging.exception("Failed to connect to target window: %s", exc)
        manifest["error"] = f"Failed to connect to target window: {exc}"
        manifest["timestamp_end_utc"] = _utc_now_iso()
        _write_manifest(started_at_utc, manifest)
        return 1, None

    unresolvable_required_steps: list[str] = []
    resolved_steps: list[str] = []
    macro_now_utc = _utc_now()
    redact_ui_text = _should_redact_ui_text(cfg)

    for step in workflow:
        step_name = step.get("name", "<unnamed>")
        retries = _validated_step_retries(step, step_name)
        delay_after = _validated_step_delay_after(step, step_name)
        action = step["action"]
        control_cfg = step["control"]
        step_window_cfg = step.get("window")
        required = _is_required_step(step)
        value = _resolve_step_value(step.get("value"), output_file=output_file, now_utc=macro_now_utc)

        attempt = 0
        step_started = time.perf_counter()
        last_error = None
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
                            if redact_ui_text:
                                logging.info(
                                    "Dry-run read_text captured for step=%s (redacted; chars=%s)",
                                    step_name,
                                    len(text),
                                )
                                print(
                                    f"[DRY-RUN] read_text current value for '{step_name}': "
                                    "[REDACTED]"
                                )
                            else:
                                logging.debug("Dry-run read_text value: %s | value=%r", step_name, text)
                                print(f"[DRY-RUN] read_text current value for '{step_name}': {text!r}")
                        except Exception as exc:
                            logging.warning("Dry-run read_text capture failed: %s | error=%s", step_name, exc)
                            print(f"[DRY-RUN] read_text capture failed for '{step_name}': {exc}")
                else:
                    result = perform_action(control, action, value)
                    if delay_after > 0:
                        time.sleep(delay_after)
                    if action == "read_text" and redact_ui_text:
                        logging.info(
                            "Step succeeded: %s | read_text=[REDACTED] | chars=%s",
                            step_name,
                            len(str(result)),
                        )
                    else:
                        logging.info("Step succeeded: %s | %s", step_name, result)
                manifest["workflow_steps"].append(
                    {
                        "name": step_name,
                        "action": action,
                        "passed": True,
                        "attempts": attempt + 1,
                        "retries_configured": retries,
                        "duration_seconds": round(time.perf_counter() - step_started, 3),
                    }
                )
                break
            except Exception as exc:
                attempt += 1
                last_error = str(exc)
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
                    manifest["workflow_steps"].append(
                        {
                            "name": step_name,
                            "action": action,
                            "passed": False,
                            "attempts": attempt,
                            "retries_configured": retries,
                            "duration_seconds": round(time.perf_counter() - step_started, 3),
                            "error": last_error,
                        }
                    )
                    manifest["error"] = f"Workflow failed on step '{step_name}': {last_error}"
                    manifest["timestamp_end_utc"] = _utc_now_iso()
                    _write_manifest(started_at_utc, manifest)
                    return 1, None
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
            return 1, None
        print(f"[DRY-RUN] SUCCESS: all required steps are resolvable ({len(resolved_steps)} step(s))")
        manifest["overall_result"] = "success"
        manifest["timestamp_end_utc"] = _utc_now_iso()
        _write_manifest(started_at_utc, manifest)
        return 0, None

    path = Path(output_file)
    if not path.exists():
        logging.error("Expected export file does not exist: %s", output_file)
        manifest["error"] = f"Expected export file does not exist: {output_file}"
        manifest["timestamp_end_utc"] = _utc_now_iso()
        _write_manifest(started_at_utc, manifest)
        return 1, None

    if output_path.stat().st_size <= 0:
        logging.error("Export file is empty: %s", output_file)
        manifest["error"] = f"Export file is empty: {output_file}"
        manifest["timestamp_end_utc"] = _utc_now_iso()
        _write_manifest(started_at_utc, manifest)
        return 1, None

    manifest["export"]["size_bytes"] = path.stat().st_size
    manifest["export"]["checksum_sha256"] = _file_sha256(path)
    manifest["overall_result"] = "success"
    manifest["timestamp_end_utc"] = _utc_now_iso()
    _write_manifest(started_at_utc, manifest)

    logging.info("Workflow completed successfully: %s", output_file)
    print(f"SUCCESS: {output_file}")
    return 0, output_file


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
                    message="No successful run observed within SLA window " f"({sla_hours:g} hours).",
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


def check_workflow(config_path: str, *, resolve_selectors: bool = False) -> int:
    cfg = load_json(config_path)
    errors = validate_config(cfg)
    if errors:
        for err in errors:
            logging.error("Config validation error: %s", err)
            print(f"ERROR: {err}")
        return 1

    print("Config schema validation: OK")
    if not resolve_selectors:
        return 0

    return _run_workflow_cfg(cfg, dry_run=True)[0]


def run_workflow(config_path: str, dry_run: bool = False) -> int:
    cfg = load_json(config_path)
    errors = validate_config(cfg)
    if errors:
        for err in errors:
            logging.error("Config validation error: %s", err)
            print(f"ERROR: {err}")
        return 1

    status, _ = _run_workflow_cfg(cfg, dry_run=dry_run)
    _handle_alerts_for_run(cfg, status)
    return status


def run_workflow_with_metadata(config_path: str) -> dict[str, Any]:
    cfg = load_json(config_path)
    errors = validate_config(cfg)
    if errors:
        for err in errors:
            logging.error("Config validation error: %s", err)
        return {
            "success": False,
            "exit_code": 1,
            "output_file": None,
            "errors": errors,
        }

    status, output_file = _run_workflow_cfg(cfg, dry_run=False)
    _handle_alerts_for_run(cfg, status)
    return {
        "success": status == 0,
        "exit_code": status,
        "output_file": output_file,
    }
