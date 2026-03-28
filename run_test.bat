@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "ROOT_DIR=%~dp0"
if "%ROOT_DIR:~-1%"=="\" set "ROOT_DIR=%ROOT_DIR:~0,-1%"
set "CONFIG_DIR=%ROOT_DIR%\configs"
set "CONFIG_PATH=%CONFIG_DIR%\basic_test_config.json"

if not exist "!CONFIG_DIR!" mkdir "!CONFIG_DIR!"
if not exist "!ROOT_DIR!\test_exports" mkdir "!ROOT_DIR!\test_exports"
if not exist "!ROOT_DIR!\test_alerts" mkdir "!ROOT_DIR!\test_alerts"

if not exist "!CONFIG_PATH!" (
  (
    echo {
    echo   "app": {
    echo     "backend": "win32",
    echo     "window_title_regex": ".*Vendor App.*",
    echo     "exe_path": "C:\\Program Files\\Vendor\\App.exe"
    echo   },
    echo   "export": {
    echo     "output_dir": "test_exports",
    echo     "schedule": "every 6 hours",
    echo     "timezone": "America/Chicago",
    echo     "max_missed_runs_to_catch_up": 1,
    echo     "quiet_hours": {
    echo       "start": "22:00",
    echo       "end": "06:00"
    echo     }
    echo   },
    echo   "alerts": {
    echo     "enabled": false,
    echo     "failure_threshold": 3,
    echo     "sla_hours": 24,
    echo     "output_path": "test_alerts"
    echo   },
    echo   "workflow": [
    echo     {
    echo       "name": "focus_export_button",
    echo       "window": {
    echo         "title": "Vendor App"
    echo       },
    echo       "control": {
    echo         "name": "Export",
    echo         "control_type": "Button",
    echo         "class_name": "Button",
    echo         "automation_id": "btnExport"
    echo       },
    echo       "action": "click_input",
    echo       "delay_after": 1.0,
    echo       "retries": 1
    echo     },
    echo     {
    echo       "name": "enter_output_path",
    echo       "window": {
    echo         "title": "Vendor App"
    echo       },
    echo       "control": {
    echo         "name": "File name",
    echo         "control_type": "Edit",
    echo         "class_name": "Edit",
    echo         "automation_id": "txtPath"
    echo       },
    echo       "action": "set_text",
    echo       "value": "{output_file}",
    echo       "delay_after": 0.5,
    echo       "retries": 2
    echo     }
    echo   ]
    echo }
  ) > "!CONFIG_PATH!"
  echo Created basic test config: !CONFIG_PATH!
) else (
  echo Using existing config: !CONFIG_PATH!
)

if not exist "!ROOT_DIR!\.venv\Scripts\python.exe" (
  where py >nul 2>&1
  if !errorlevel! == 0 (
    py -3 -m venv "!ROOT_DIR!\.venv"
  ) else (
    python -m venv "!ROOT_DIR!\.venv"
  )
  if errorlevel 1 goto :error
)

call "!ROOT_DIR!\.venv\Scripts\activate.bat"
python -m pip install --upgrade pip >nul
python -m pip install -r "!ROOT_DIR!\requirements.txt"
python -m src check --config "!CONFIG_PATH!"
if errorlevel 1 goto :error

echo.
echo Config check passed. Next steps (Windows host with vendor app open):
echo   python -m src trainer --backend win32
echo   python -m src run --config "!CONFIG_PATH!"

goto :eof

:error
echo Config check failed.
exit /b 1
