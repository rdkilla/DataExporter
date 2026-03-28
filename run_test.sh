#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_PATH="${ROOT_DIR}/configs/basic_test_config.json"

mkdir -p "${ROOT_DIR}/configs" "${ROOT_DIR}/test_exports" "${ROOT_DIR}/test_alerts"

if [[ ! -f "${CONFIG_PATH}" ]]; then
  cat > "${CONFIG_PATH}" <<'JSON'
{
  "app": {
    "backend": "win32",
    "window_title_regex": ".*Vendor App.*",
    "exe_path": "C:\\Program Files\\Vendor\\App.exe"
  },
  "export": {
    "output_dir": "test_exports",
    "schedule": "every 6 hours",
    "timezone": "America/Chicago",
    "max_missed_runs_to_catch_up": 1,
    "quiet_hours": {
      "start": "22:00",
      "end": "06:00"
    }
  },
  "alerts": {
    "enabled": false,
    "failure_threshold": 3,
    "sla_hours": 24,
    "output_path": "test_alerts"
  },
  "workflow": [
    {
      "name": "focus_export_button",
      "window": {
        "title": "Vendor App"
      },
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
      "window": {
        "title": "Vendor App"
      },
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
JSON
  echo "Created basic test config: ${CONFIG_PATH}"
else
  echo "Using existing config: ${CONFIG_PATH}"
fi

if [[ ! -d "${ROOT_DIR}/.venv" ]]; then
  python3 -m venv "${ROOT_DIR}/.venv"
fi

source "${ROOT_DIR}/.venv/bin/activate"
python -m pip install --upgrade pip >/dev/null
python -m pip install -r "${ROOT_DIR}/requirements.txt"

python -m src check --config "${CONFIG_PATH}"

echo
echo "Config check passed. Next steps (Windows host with vendor app open):"
echo "  python -m src trainer --backend win32"
echo "  python -m src run --config ${CONFIG_PATH}"
