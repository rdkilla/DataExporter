# Valve Export Tool

Local Windows utility for training and running GUI-based CSV exports from an old vendor application with no API.

## Modes
- `trainer`: inspect windows and controls, test actions, save workflow config
- `run`: execute a saved workflow config to perform exports
- `package`: build a standalone executable of this tool for transfer to another Windows machine

## Usage

### Trainer
```bash
python -m src trainer
```

### Runner
```bash
python -m src run --config configs/vendor_export.json
```

### Build executable package
```bash
python -m src package --name valve-export-tool
```

This command uses PyInstaller to create a distributable executable in `dist/`.

For best Windows 7 compatibility, run the packaging command on a Windows host that closely matches the target machine (architecture + runtime libraries).
