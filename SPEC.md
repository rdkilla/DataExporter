# Valve Export Trainer

## Goal
Build a Windows utility that helps automate CSV exports from an old vendor application used on a Windows 7 operator station.

The app has no API and only exposes data through its GUI. It stores only about 3 days of data history. The utility should let a user inspect the vendor app’s window and controls, test possible actions on controls, save a training configuration, and later run the saved export workflow automatically.

Phase 1 only. No direct controller integration, no protocol reverse engineering, no cloud services, no AI decision-making in the runtime loop.

## Core use case
A user opens the vendor app on the same Windows machine. Our utility runs locally, discovers available windows, lets the user select the vendor window, enumerates visible controls, allows trying actions like click/focus/type/read text, and saves successful mappings into a config file. Later, the runner uses that config to perform exports into a chosen local folder.

## Constraints
- Target machine is offline.
- Likely Windows 7.
- Vendor app is about 18 years old.
- Prefer pywinauto with win32 backend first.
- Fallback support should allow keyboard-driven actions.
- No internet dependency at runtime.
- No database required.
- No installer required for first version, but app should be packagable into an EXE later.
