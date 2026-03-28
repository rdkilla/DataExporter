from pathlib import Path
import shlex
import sys

from src.config_io import save_json
from src.config_schema import make_base_config


def _supports_color() -> bool:
    return sys.stdout.isatty()


def _color(text: str, code: str) -> str:
    if not _supports_color():
        return text
    return f"\033[{code}m{text}\033[0m"


def _format_cmd(args: list[str]) -> str:
    return " ".join(shlex.quote(arg) for arg in args)


def init_config(
    config_path: str,
    backend: str = "win32",
    output_dir: str = "exports",
    schedule: str = "every 6 hours",
    timezone: str = "UTC",
) -> int:
    config = make_base_config(
        backend=backend,
        window_title_regex=".*Vendor App.*",
        exe_path=None,
        output_dir=output_dir,
    )
    config["export"]["schedule"] = schedule
    config["export"]["timezone"] = timezone

    save_json(config_path, config, base_dir=Path.cwd())

    print(f"Starter config written to: {config_path}")
    check_cmd = _format_cmd(["python", "-m", "src", "check", "--config", config_path])
    trainer_cmd = _format_cmd(["python", "-m", "src", "trainer", "--backend", backend])
    run_cmd = _format_cmd(["python", "-m", "src", "run", "--config", config_path])

    print("Next steps (copy/paste):")
    print(_color("check", "1;32"))
    print(f"  {check_cmd}")
    print(_color("trainer", "1;33"))
    print(f"  {trainer_cmd}")
    print(_color("run", "1;36"))
    print(f"  {run_cmd}")
    return 0
