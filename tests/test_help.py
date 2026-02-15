from pathlib import Path
from types import SimpleNamespace

import chat


def build_help_app(tmp_path: Path) -> chat.ChatApp:
    app = chat.ChatApp.__new__(chat.ChatApp)
    app.name = "HelpUser"
    app.client_id = "help12345678"
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
        "streaming": {"enabled": True, "providers": {"gemini": True, "openai": True}},
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


def test_help_overview_lists_topics(tmp_path):
    app = build_help_app(tmp_path)
    app.controller.handle_input("/help")
    assert "Help: Overview" in app.output_field.text
    assert "Help topics:" in app.output_field.text


def test_help_ai_topic_contains_examples(tmp_path):
    app = build_help_app(tmp_path)
    app.controller.handle_input("/help ai")
    assert "Help: AI Requests" in app.output_field.text
    assert "--act" in app.output_field.text


def test_help_unknown_topic_returns_guided_error(tmp_path):
    app = build_help_app(tmp_path)
    app.controller.handle_input("/help unknown_topic")
    assert "Problem:" in app.output_field.text
    assert "Next:" in app.output_field.text


def test_onboard_status_start_reset_flow(tmp_path):
    app = build_help_app(tmp_path)
    app.controller.handle_input("/onboard status")
    assert "Onboarding status:" in app.output_field.text
    assert "Not started." in app.output_field.text

    app.controller.handle_input("/onboard start")
    assert "Onboarding started." in app.output_field.text
    assert "Next step:" in app.output_field.text

    app.controller.handle_input("/onboard reset")
    assert "Onboarding state reset." in app.output_field.text


def test_unknown_command_guides_to_help(tmp_path):
    app = build_help_app(tmp_path)
    app.controller.handle_input("/notreal")
    assert "Problem:" in app.output_field.text
    assert "/help overview" in app.output_field.text
