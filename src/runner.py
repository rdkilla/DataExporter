import logging
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from pywinauto import Application, Desktop

from src.actions import perform_action
from src.config_io import load_json
from src.utils import make_output_file


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_manifest(start_ts: str, manifest: dict) -> None:
    date_prefix = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    run_suffix = datetime.now(timezone.utc).strftime("%H%M%S_%f")
    manifest_dir = Path("logs") / "manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / f"{date_prefix}_{run_suffix}_run.json"
    with manifest_path.open("w", encoding="utf-8") as fh:
        json.dump(
            {
                "timestamp_start_utc": start_ts,
                **manifest,
            },
            fh,
            indent=2,
        )
    logging.info("Wrote run manifest: %s", manifest_path)


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
    started_at_utc = _utc_now_iso()
    manifest = {
        "timestamp_end_utc": None,
        "config": {
            "path": str(Path(config_path).resolve()),
            "checksum_sha256": None,
        },
        "app": {
            "backend": None,
            "window_matcher": None,
        },
        "workflow_steps": [],
        "export": {
            "path": None,
            "size_bytes": None,
            "checksum_sha256": None,
        },
        "overall_result": "failed",
        "error": None,
    }

    config_file = Path(config_path)
    try:
        manifest["config"]["checksum_sha256"] = _file_sha256(config_file)
    except Exception as exc:
        manifest["error"] = f"Failed reading config file checksum: {exc}"
        manifest["timestamp_end_utc"] = _utc_now_iso()
        _write_manifest(started_at_utc, manifest)
        logging.exception("Unable to checksum config file: %s", config_path)
        return 1

    cfg = load_json(config_path)
    app_cfg = cfg.get("app", {})
    export_cfg = cfg.get("export", {})
    workflow = cfg.get("workflow", [])
    manifest["app"]["backend"] = app_cfg.get("backend", "win32")
    manifest["app"]["window_matcher"] = {
        "title_regex": app_cfg.get("window_title_regex", ".*"),
        "exe_path": app_cfg.get("exe_path"),
    }

    if not workflow:
        logging.error("No workflow steps found in config.")
        manifest["error"] = "No workflow steps found in config."
        manifest["timestamp_end_utc"] = _utc_now_iso()
        _write_manifest(started_at_utc, manifest)
        return 1

    output_file = make_output_file(export_cfg.get("output_dir", "exports"))
    manifest["export"]["path"] = output_file

    try:
        window = _connect_window(app_cfg)
        window.wait("visible", timeout=30)
    except Exception as exc:
        logging.exception("Failed to connect to target window: %s", exc)
        manifest["error"] = f"Failed to connect to target window: {exc}"
        manifest["timestamp_end_utc"] = _utc_now_iso()
        _write_manifest(started_at_utc, manifest)
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
        step_started = time.perf_counter()
        last_error = None
        while True:
            try:
                control = _find_control(window, control_cfg)
                control.wait("exists enabled visible ready", timeout=10)
                result = perform_action(control, action, value)
                if delay_after > 0:
                    time.sleep(delay_after)
                logging.info("Step succeeded: %s | %s", step_name, result)
                manifest["workflow_steps"].append(
                    {
                        "name": step_name,
                        "action": action,
                        "passed": True,
                        "attempts": attempt + 1,
                        "retries_configured": retries,
                        "duration_seconds": round(time.perf_counter() - step_started, 3),
                        "error": None,
                    }
                )
                break
            except Exception as exc:
                attempt += 1
                last_error = str(exc)
                logging.warning("Step failed: %s | attempt=%s | error=%s", step_name, attempt, exc)
                if attempt > retries:
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
                    return 1
                time.sleep(1)

    path = Path(output_file)
    if not path.exists():
        logging.error("Expected export file does not exist: %s", output_file)
        manifest["error"] = f"Expected export file does not exist: {output_file}"
        manifest["timestamp_end_utc"] = _utc_now_iso()
        _write_manifest(started_at_utc, manifest)
        return 1

    if path.stat().st_size <= 0:
        logging.error("Export file is empty: %s", output_file)
        manifest["error"] = f"Export file is empty: {output_file}"
        manifest["timestamp_end_utc"] = _utc_now_iso()
        _write_manifest(started_at_utc, manifest)
        return 1

    manifest["export"]["size_bytes"] = path.stat().st_size
    manifest["export"]["checksum_sha256"] = _file_sha256(path)
    manifest["overall_result"] = "success"
    manifest["timestamp_end_utc"] = _utc_now_iso()
    _write_manifest(started_at_utc, manifest)

    logging.info("Workflow completed successfully: %s", output_file)
    print(f"SUCCESS: {output_file}")
    return 0
