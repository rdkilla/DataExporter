from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def make_output_file(
    output_dir: str,
    prefix: str = "valves",
    include_timestamp_utc: bool = True,
    include_run_id: bool = True,
) -> str:
    folder = Path(output_dir)
    folder.mkdir(parents=True, exist_ok=True)

    safe_prefix = (prefix or "valves").strip() or "valves"
    name_parts = [safe_prefix]

    if include_timestamp_utc:
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
        name_parts.append(stamp)

    if include_run_id:
        name_parts.append(uuid4().hex[:8])

    filename = "_".join(name_parts) + ".csv"
    return str(folder / filename)


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
