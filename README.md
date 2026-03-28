# Valve Export Tool

Automate CSV exports from a legacy Windows vendor application that has no API.

This project provides a **trainer** for building workflows interactively and a **runner** for executing saved workflows unattended.

---

## What this tool does

The tool is designed for operator stations that run older Windows software (for example, Windows 7-era systems) where data is only available through GUI interactions.

It helps you:
- Discover open windows and inspect controls.
- Try actions against controls (click, focus, type, read text, etc.).
- Save a repeatable workflow to JSON.
- Replay that workflow to export CSV files.
- Package the utility as a standalone executable with PyInstaller.

---

## Requirements

- **Python 3.10+** recommended.
- **Windows host** for actual GUI automation (pywinauto / pywin32).
- Same machine/session as the target vendor app (or equivalent desktop session).

Dependencies are listed in `requirements.txt`:
- `pywinauto`
- `pywin32`
- `pyinstaller`

Install:

```bash
python -m pip install -r requirements.txt
```

---

## Quick test scripts

Use the script that matches your platform:

- **Windows:** `run_test.bat`
- **Linux/macOS (config-only checks):** `run_test.sh`

`run_test.bat` will:
- create `configs/basic_test_config.json` if it does not exist,
- create a local virtual environment in `.venv`,
- install dependencies, and
- run `python -m src check --config configs/basic_test_config.json`.

`run_test.sh` is intended for config-only checks on non-Windows hosts. GUI automation (`trainer`/`run` against real windows) and `package` are Windows-focused targets.

---

## CLI Commands

The entry point is:

```bash
python -m src <command> [options]
```

### 1) Trainer mode

Interactive mode for selecting a target window, testing actions, and building workflow steps.

```bash
python -m src trainer
```

Optional backend:

```bash
python -m src trainer --backend win32
python -m src trainer --backend uia
```

Tips:
- On Windows 11, `--backend uia` usually provides better control names/types for modern apps.
- Trainer now hides common background/system windows by default to reduce noise in the window picker.

### 2) Run mode

Execute a saved workflow JSON.

```bash
python -m src run --config configs/vendor_export.json
```

### 3) Daemon mode

Run continuously using `export.schedule` and persist run metadata to a local state file.

```bash
python -m src daemon --config configs/vendor_export.json --state-file state/run_history.json
```

On startup, daemon mode inspects `state/run_history.json`, detects missed scheduling windows, and performs capped catch-up runs based on `export.max_missed_runs_to_catch_up`.

### 4) Package mode

Build a distributable executable with PyInstaller.

```bash
python -m src package --name valve-export-tool
```

Useful options:
- `--onedir` build folder-based output instead of a single executable.
- `--dist-dir <path>` output folder (default: `dist`).
- `--work-dir <path>` PyInstaller work folder (default: `build`).
- `--spec-dir <path>` spec output folder (default: current directory).
- `--no-clean` keep PyInstaller cache.
- `--pyinstaller-arg <arg>` pass through additional PyInstaller arguments (repeatable).

### 5) Check mode

Validate workflow configuration before running automation.

```bash
python -m src check --config configs/vendor_export.json
```

Optionally perform selector connectivity checks without executing actions:

```bash
python -m src check --config configs/vendor_export.json --resolve-selectors
```

#### What check mode validates

- Confirms the JSON configuration shape and supported action definitions are valid.
- With `--resolve-selectors`, also attempts optional selector resolution/connectivity checks without executing workflow actions.

> For best compatibility with older targets (such as Windows 7), build on a Windows machine that closely matches the target environment.

---

## Workflow configuration format

The runner expects JSON shaped like:

```json
{
  "app": {
    "backend": "win32",
    "window_title_regex": ".*Vendor App.*",
    "exe_path": "C:/Path/To/VendorApp.exe"
  },
  "export": {
    "output_dir": "exports",
    "schedule": "every 6 hours",
    "timezone": "America/Chicago",
    "max_missed_runs_to_catch_up": 3,
    "quiet_hours": { "start": "22:00", "end": "06:00" }
  },
  "alerts": {
    "enabled": true,
    "failure_threshold": 3,
    "sla_hours": 24,
    "output_path": "alerts"
  },
  "workflow": [
    {
      "name": "focus_export_button",
      "window": { "title": "Vendor App" },
      "control": {
        "name": "Export",
        "control_type": "Button",
        "class_name": "Button",
        "automation_id": "btnExport"
      },
      "action": "click_input",
      "delay_after": 1.0,
      "retries": 1
    },
    {
      "name": "enter_output_path",
      "window": { "title": "Vendor App" },
      "control": {
        "name": "File name",
        "control_type": "Edit",
        "class_name": "Edit",
        "automation_id": "txtPath"
      },
      "action": "set_text",
      "value": "{output_file}",
      "delay_after": 0.5,
      "retries": 2
    }
  ]
}
```


### Alerting configuration

When `alerts.enabled` is `true`, each scheduler/run invocation updates internal alert state and can emit machine-consumable alert files into `alerts.output_path`:

- `alerts.enabled`: turn alerting on/off.
- `alerts.failure_threshold`: emit a `failure_threshold` alert after this many consecutive failed runs.
- `alerts.sla_hours`: emit a `stale_data` alert if no successful run is observed within this many hours.
- `alerts.output_path`: watched folder where alert JSON files (and internal state file) are written.

Alert behaviors:
- A failure-threshold alert is emitted once per failure streak (resets after a successful run).
- A stale-data alert is emitted when the SLA window is breached and is cleared by the next successful run.
- On Windows hosts with `pywin32` Event Log support available, matching Windows Event Log entries are also written.

### Notes
- The runner generates CSV paths under `export.output_dir` using an optional naming template.
  - `prefix` sets the filename prefix (for site/unit/vendor ID).
  - `include_timestamp_utc` adds `YYYY-MM-DD_HHMMSS` in UTC.
  - `include_run_id` adds a short unique suffix to reduce collisions.
- Example output: `valves_2026-03-27_153045_a1b2c3d4.csv`.
- Step `value` macro support:
  - `"{output_file}"` inserts the generated export path.
  - `"{now}"` inserts current UTC time as `YYYY-MM-DD_HHMMSS`.
  - `"{now:%Y%m%d}"` (or any Python `strftime` pattern) inserts formatted current UTC time.
  - Macros can be mixed in longer strings, for example: `"Daily_{now:%Y%m%d}.csv"`.
  - `"{now...}"` macros are evaluated once per run and reused for all steps, so multi-step filenames stay consistent.
- Each step retries according to its `retries` field.
- `export.schedule` accepts either a 5-field cron expression (for example `0 */6 * * *`) or intervals such as `every 6 hours`, `30m`, or `1d`.
- `export.timezone` uses IANA names (for example `America/Chicago`).
- `export.max_missed_runs_to_catch_up` caps backlog execution on daemon startup.
- Optional `export.quiet_hours` (string `HH:MM-HH:MM` or object with `start`/`end`) defers executions during quiet windows.
- Daemon run history is stored at `state/run_history.json` by default with each run's planned time, execution timestamps, success/failure, catch-up marker, and output file path.

---

## Supported actions

Trainer/runner actions currently supported:

- `click_input`
- `double_click_input`
- `right_click_input`
- `set_focus`
- `read_text`
- `set_text`
- `type_keys`
- `send_keys`
- `print_children`
- `print_control_identifiers`

---

## Typical usage flow

1. Launch the vendor application manually.
2. Run trainer mode and select the correct window.
3. Test actions on relevant controls.
4. Add successful actions to the workflow (for filename entry steps, you can use macros like `"{output_file}"` or `"Report_{now:%Y%m%d}.csv"` as the action value).
5. Save config JSON (for example `configs/vendor_export.json`).
6. Run the workflow with `python -m src run --config ...`.
7. Verify the CSV file was created and is non-empty.

### First successful run checklist

1. Open the vendor application and navigate to the export screen.
2. Run `python -m src trainer` and capture/test the required controls.
3. Save a config JSON (for example `configs/vendor_export.json`).
4. Run `python -m src check --config configs/vendor_export.json` (optionally add `--resolve-selectors`).
5. Run `python -m src run --config configs/vendor_export.json` and verify CSV output.

---

## Operational FAQ

### Does this set the frequency of pulling data?

Yes. In daemon mode, the frequency is controlled by `export.schedule` in the config file.

- Interval examples: `every 6 hours`, `30m`, `1d`
- Cron example: `0 */6 * * *`

`export.timezone` controls how schedule times are interpreted. If you define `export.quiet_hours`, scheduled runs inside that window are deferred until quiet hours end.

### Is it user-friendly to run?

Partially:

- **Trainer mode** is interactive and helps you discover controls and build workflows.
- **Run/daemon mode** are CLI-first and intended for operators or scripts.

If your team prefers point-and-click setup/operations, adding a small GUI may improve onboarding.

### Can we register the executable as a service and run in the background?

The tool can be packaged as a Windows executable, and the daemon command is designed to run continuously. Service registration is not built in to this repository, but you can typically host the packaged executable with standard Windows service wrappers (for example NSSM/Task Scheduler/service host tooling) depending on your environment policies.

### Is it visible in the system tray?

No. There is no tray icon implementation in this project today.

### Does it have any form of GUI?

It has an interactive **text-based** trainer in the terminal, but no desktop GUI window/forms.

### Is it worth adding a GUI?

Usually yes if multiple non-technical operators must maintain workflows, monitor status, or acknowledge alerts. If a small technical team is comfortable with JSON + CLI, the current approach is simpler and lower maintenance.

Good incremental path:

1. Keep runner/daemon engine as-is.
2. Add a lightweight GUI only for config editing, validation (`check`), and start/stop status.
3. Optionally add tray notifications and last-run health view.

---


## Operator response playbook

Use the following runbook whenever an alert is written to the watched alert folder or appears in Windows Event Log.

1. **Acknowledge the alert**
   - Record alert type, timestamp, host, and current consecutive-failure count (if present).

2. **Collect evidence**
   - Save the runner console/log output for the failing schedule window.
   - Confirm whether the vendor application is open, responsive, and in the expected desktop session.
   - Verify output destination (`export.output_dir`) is writable and has free disk space.

3. **Failure-threshold alert response (`failure_threshold`)**
   - Re-run once manually: `python -m src run --config <config.json>`.
   - If manual run fails, re-open trainer and validate selectors for changed controls (`name`, `class_name`, `automation_id`).
   - If selectors are unchanged, escalate to application support/vendor team with the failed step and exception details.

4. **Stale-data alert response (`stale_data`)**
   - Confirm scheduler is still active and invoking the runner on expected cadence.
   - Validate most recent successful export timestamp against downstream SLA requirements.
   - Trigger an immediate manual run and verify a new non-empty export is produced.

5. **Recovery verification**
   - Ensure one successful run completes end-to-end; this clears failure streak and stale alert state.
   - Confirm downstream systems receive the new export file.

6. **Post-incident hardening**
   - Update selectors/workflow retries if UI timing changed.
   - Adjust `alerts.failure_threshold` / `alerts.sla_hours` only if operational requirements changed.
   - Document root cause and prevention action in your operations log.

---

## Troubleshooting

- **No windows found**: ensure the target app is open and visible in the same session.
- **Control lookup fails**: re-train using more stable selectors (`name`, `class_name`, `automation_id`).
- **Workflow succeeds but no file appears**: verify export dialog behavior and that a step writes `"{output_file}"` to the correct field.
- **Packaging works but EXE fails on target machine**: rebuild on a machine matching target OS and architecture.

## Run manifests

Each `run` attempt now writes a JSON manifest to `logs/manifests/` with a unique, append-only filename per run:

- `logs/manifests/YYYY-MM-DD_HHMMSS_microseconds_run.json`

Manifest records include:
- UTC run start/end timestamps.
- Config path and config SHA-256 checksum.
- App backend and window matcher details used.
- Per-step status (pass/fail), retry/attempt counts, and step duration.
- Export output path, file size, and file SHA-256 checksum when export succeeds.
- Overall result and any captured error details.

### Retention policy

Manifest files are intentionally append-only to preserve audit history. Keep at least **90 days** of manifest files for operational traceability. Older files can be archived or deleted according to your site policy/capacity constraints.

---

## Project scope

This is intentionally a local automation utility for offline environments. It does **not** include:
- Vendor protocol reverse engineering.
- Cloud services.
- External databases.
- AI-driven runtime decisions.
