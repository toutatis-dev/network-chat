from __future__ import annotations

from typing import Any

from huddle_chat.models import ToolDefinition


class ToolContractError(ValueError):
    pass


def validate_required_args(
    schema: dict[str, Any], args: dict[str, Any]
) -> tuple[bool, str | None]:
    required = schema.get("required", [])
    if not isinstance(required, list):
        return False, "Invalid tool schema: required must be a list."
    for name in required:
        if not isinstance(name, str):
            continue
        if name not in args:
            return False, f"Missing required argument '{name}'."
    return True, None


def validate_arg_types(
    schema: dict[str, Any], args: dict[str, Any]
) -> tuple[bool, str | None]:
    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        return False, "Invalid tool schema: properties must be an object."
    for key, value in args.items():
        prop = properties.get(key)
        if not isinstance(prop, dict):
            continue
        expected = prop.get("type")
        if expected == "string" and not isinstance(value, str):
            return False, f"Argument '{key}' must be a string."
        if expected == "integer" and not isinstance(value, int):
            return False, f"Argument '{key}' must be an integer."
        if expected == "boolean" and not isinstance(value, bool):
            return False, f"Argument '{key}' must be a boolean."
        if expected == "object" and not isinstance(value, dict):
            return False, f"Argument '{key}' must be an object."
    return True, None


def validate_tool_call_args(
    definition: ToolDefinition, arguments: dict[str, Any]
) -> tuple[bool, str | None]:
    if not isinstance(arguments, dict):
        return False, "Tool arguments must be a JSON object."
    schema = definition.get("inputSchema", {})
    if not isinstance(schema, dict):
        return False, "Invalid tool schema."
    ok, err = validate_required_args(schema, arguments)
    if not ok:
        return False, err
    ok, err = validate_arg_types(schema, arguments)
    if not ok:
        return False, err
    return True, None
