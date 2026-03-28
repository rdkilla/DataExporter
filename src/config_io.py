import json
from pathlib import Path

from src.path_safety import resolve_write_path


def load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def save_json(path: str, data: dict, *, base_dir: str | Path | None = None) -> None:
    output = resolve_write_path(path, base_dir=base_dir, reject_symlink_traversal=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)
