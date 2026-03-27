def make_base_config(backend: str, window_title_regex: str, exe_path: str | None, output_dir: str) -> dict:
    return {
        "app": {
            "backend": backend,
            "window_title_regex": window_title_regex,
            "exe_path": exe_path,
        },
        "export": {
            "output_dir": output_dir,
        },
        "workflow": [],
        "alerts": {
            "enabled": False,
            "failure_threshold": 3,
            "sla_hours": 24,
            "output_path": "alerts",
        },
    }


def make_workflow_step(
    name: str,
    control: dict,
    action: str,
    value: str | None,
    delay_after: float,
    retries: int,
    window_matcher: dict,
) -> dict:
    step = {
        "name": name,
        "window": window_matcher,
        "control": control,
        "action": action,
        "delay_after": delay_after,
        "retries": retries,
    }
    if value is not None:
        step["value"] = value
    return step
