from src.config_io import save_json
from src.config_schema import make_base_config


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

    save_json(config_path, config)

    print(f"Starter config written to: {config_path}")
    print("Next steps:")
    print(f"  1) python -m src check --config {config_path}")
    print(f"  2) python -m src trainer --backend {backend}")
    print(f"  3) python -m src run --config {config_path}")
    return 0
