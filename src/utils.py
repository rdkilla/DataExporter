from datetime import datetime
from pathlib import Path


def make_output_file(output_dir: str) -> str:
    folder = Path(output_dir)
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    return str(folder / f"valves_{stamp}.csv")


def ask_int(prompt: str, default: int = 0) -> int:
    raw = input(prompt).strip()
    if raw == "":
        return default
    return int(raw)


def ask_float(prompt: str, default: float = 0.0) -> float:
    raw = input(prompt).strip()
    if raw == "":
        return default
    return float(raw)
