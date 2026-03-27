# Valve Export Tool

Local Windows utility for training and running GUI-based CSV exports from an old vendor application with no API.

## Modes
- `trainer`: inspect windows and controls, test actions, save workflow config
- `run`: execute a saved workflow config to perform exports

## Usage

### Trainer
```bash
python -m src.main trainer
```

### Runner
```bash
python -m src.main run --config configs/vendor_export.json
```
