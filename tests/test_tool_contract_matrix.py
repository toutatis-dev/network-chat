from types import SimpleNamespace

from huddle_chat.services.tool_contract import validate_tool_call_args
from huddle_chat.services.tool_registry import ToolRegistryService


def _registry():
    app = SimpleNamespace()
    return ToolRegistryService(app)


def test_tool_contract_accepts_minimal_valid_arguments():
    samples = {
        "search_repo": {"query": "needle"},
        "list_files": {"path": "."},
        "read_file": {"path": "chat.py"},
        "run_tests": {},
        "run_lint": {},
        "run_typecheck": {},
        "git_status": {},
        "git_diff": {},
    }
    registry = _registry()
    for definition in registry.get_tool_definitions():
        name = definition.name
        ok, err = validate_tool_call_args(definition, samples[name])
        assert ok is True, f"{name} should accept minimal args: {err}"


def test_tool_contract_rejects_unknown_argument_for_every_tool():
    registry = _registry()
    seed = {
        "search_repo": {"query": "needle"},
        "read_file": {"path": "chat.py"},
    }
    for definition in registry.get_tool_definitions():
        name = definition.name
        args = dict(seed.get(name, {}))
        args["unknownField"] = "x"
        ok, err = validate_tool_call_args(definition, args)
        assert ok is False
        assert err == "Unsupported argument 'unknownField'."


def test_tool_contract_rejects_missing_required_arguments():
    registry = _registry()
    required_tools = {"search_repo": "query", "read_file": "path"}
    for definition in registry.get_tool_definitions():
        name = definition.name
        if name not in required_tools:
            continue
        ok, err = validate_tool_call_args(definition, {})
        assert ok is False
        assert err == f"Missing required argument '{required_tools[name]}'."


def test_tool_registry_schema_matches_executor_argument_surface():
    # Keep schema and executor argument expectations synchronized.
    expected = {
        "search_repo": {"query", "path", "maxResults", "maxDurationSec"},
        "list_files": {"path", "maxResults", "maxDurationSec"},
        "read_file": {"path", "startLine", "lineCount", "maxDurationSec"},
        "run_tests": {"maxDurationSec"},
        "run_lint": {"maxDurationSec"},
        "run_typecheck": {"maxDurationSec"},
        "git_status": {"maxDurationSec"},
        "git_diff": {"path", "maxLines", "maxDurationSec"},
    }
    registry = _registry()
    for definition in registry.get_tool_definitions():
        name = definition.name
        # inputSchema is a dict
        props = (definition.inputSchema or {}).get("properties", {})
        assert isinstance(props, dict)
        assert set(props.keys()) == expected[name]
