from src.actions import SUPPORTED_ACTIONS


REQUIRED_TOP_LEVEL_KEYS = ("app", "export", "workflow")
REQUIRED_STEP_KEYS = ("name", "control", "action")
ACTIONS_REQUIRING_VALUE = {"set_text", "type_keys", "send_keys"}


def validate_config(config: dict) -> list[str]:
    errors: list[str] = []

    if not isinstance(config, dict):
        return ["Configuration root must be a JSON object."]

    for key in REQUIRED_TOP_LEVEL_KEYS:
        if key not in config:
            errors.append(f"Missing required top-level key: '{key}'.")

    workflow = config.get("workflow")
    if not isinstance(workflow, list):
        errors.append("'workflow' must be a list of step objects.")
        return errors

    if not workflow:
        errors.append("'workflow' must contain at least one step.")
        return errors

    for index, step in enumerate(workflow):
        step_label = f"workflow[{index}]"
        if not isinstance(step, dict):
            errors.append(f"{step_label} must be an object.")
            continue

        for key in REQUIRED_STEP_KEYS:
            if key not in step:
                errors.append(f"{step_label} missing required key: '{key}'.")

        if "name" in step:
            name = step.get("name")
            if not isinstance(name, str) or not name.strip():
                errors.append(f"{step_label}.name must be a non-empty string.")

        control = step.get("control")
        if "control" in step and not isinstance(control, dict):
            errors.append(f"{step_label}.control must be an object.")

        action = step.get("action")
        if "action" in step:
            if not isinstance(action, str) or not action.strip():
                errors.append(f"{step_label}.action must be a non-empty string.")
            elif action not in SUPPORTED_ACTIONS:
                allowed = ", ".join(SUPPORTED_ACTIONS)
                errors.append(
                    f"{step_label}.action '{action}' is not supported. Allowed actions: {allowed}."
                )

        if action in ACTIONS_REQUIRING_VALUE:
            value = step.get("value")
            if not isinstance(value, str) or not value.strip():
                errors.append(
                    f"{step_label}.value is required and must be a non-empty string for action '{action}'."
                )

    return errors
