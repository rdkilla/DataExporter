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

### 2) Run mode

Execute a saved workflow JSON.

```bash
python -m src run --config configs/vendor_export.json
```

### 3) Package mode

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

### 4) Check mode

Validate workflow configuration before running automation.

```bash
python -m src check --config configs/vendor_export.json
```

Optionally perform selector connectivity checks without executing actions:

```bash
python -m src check --config configs/vendor_export.json --resolve-selectors
```

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
    "output_dir": "exports"
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

### Notes
- The runner generates timestamped CSV paths under `export.output_dir`.
- If a step `value` is `"{output_file}"`, it is replaced with the generated path.
- Each step retries according to its `retries` field.

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
4. Add successful actions to the workflow.
5. Save config JSON (for example `configs/vendor_export.json`).
6. Run the workflow with `python -m src run --config ...`.
7. Verify the CSV file was created and is non-empty.

---

## Troubleshooting

- **No windows found**: ensure the target app is open and visible in the same session.
- **Control lookup fails**: re-train using more stable selectors (`name`, `class_name`, `automation_id`).
- **Workflow succeeds but no file appears**: verify export dialog behavior and that a step writes `"{output_file}"` to the correct field.
- **Packaging works but EXE fails on target machine**: rebuild on a machine matching target OS and architecture.

---

## Project scope

This is intentionally a local automation utility for offline environments. It does **not** include:
- Vendor protocol reverse engineering.
- Cloud services.
- External databases.
- AI-driven runtime decisions.
