from pathlib import Path
from types import SimpleNamespace

import chat


def build_explain_app(tmp_path: Path) -> chat.ChatApp:
    app = chat.ChatApp.__new__(chat.ChatApp)
    app.name = "ExplainUser"
    app.client_id = "explain1234"
    app.color = "green"
    app.status = ""
    app.running = True
    app.current_room = "general"
    app.current_theme = "default"
    app.base_dir = str(tmp_path)
    app.rooms_root = str(tmp_path / "rooms")
    app.presence_file_id = app.client_id
    app.messages = []
    app.message_events = []
    app.last_pos_by_room = {}
    app.online_users = {}
    app.search_query = ""
    app.search_hits = []
    app.active_search_hit_idx = -1
    app.sidebar_control = SimpleNamespace(text=[])
    app.output_field = SimpleNamespace(
        text="", buffer=SimpleNamespace(cursor_position=0)
    )
    app.application = SimpleNamespace(invalidate=lambda: None)
    app.input_field = SimpleNamespace(text="")
    app.ensure_locking_dependency = lambda: None
    app.ai_config = {
        "default_provider": "gemini",
        "providers": {
            "gemini": {"api_key": "", "model": "gemini-2.5-flash"},
            "openai": {"api_key": "", "model": "gpt-4o-mini"},
        },
        "streaming": {
            "enabled": True,
            "providers": {"gemini": True, "openai": True},
        },
    }
    app.pending_actions = {
        "ab12cd34": {
            "action_id": "ab12cd34",
            "status": "pending",
            "tool": "run_tests",
            "risk_level": "med",
            "summary": "Run full test suite",
            "command_preview": "run_tests {}",
            "inputs": {},
            "room": "general",
            "request_id": "req123",
        }
    }
    app.ensure_paths()
    app.ensure_local_paths()
    app.ensure_memory_paths()
    app.ensure_agent_paths()
    app.update_room_paths()
    app.controller = chat.ChatController(app)
    app.get_onboarding_state_path = (
        lambda: tmp_path / ".local_chat" / "onboarding_state.json"
    )
    return app


def test_explain_action_outputs_concise_summary(tmp_path):
    app = build_explain_app(tmp_path)
    app.controller.handle_input("/explain action ab12cd34")
    assert "Action ab12cd34" in app.output_field.text
    assert "status=pending" in app.output_field.text
    assert "Next:" in app.output_field.text


def test_explain_agent_outputs_profile_context(tmp_path):
    app = build_explain_app(tmp_path)
    app.controller.handle_input("/explain agent")
    assert "Agent profile=" in app.output_field.text
    assert "memory_scopes=" in app.output_field.text
    assert "tool_policy" in app.output_field.text


def test_explain_tool_outputs_constraints(tmp_path):
    app = build_explain_app(tmp_path)
    app.controller.handle_input("/explain tool run_tests")
    assert "Tool run_tests" in app.output_field.text
    assert "requires_approval" in app.output_field.text
    assert "allowed_by_agent_policy=" in app.output_field.text
