from pathlib import Path
from types import SimpleNamespace

import chat


def build_playbook_app(tmp_path: Path) -> chat.ChatApp:
    app = chat.ChatApp.__new__(chat.ChatApp)
    app.name = "PlaybookUser"
    app.client_id = "playbook1234"
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
    app.ai_active_request_id = None
    app.pending_actions = {}
    app.ensure_paths()
    app.ensure_local_paths()
    app.ensure_memory_paths()
    app.ensure_agent_paths()
    app.update_room_paths()
    app.get_onboarding_state_path = (
        lambda: tmp_path / ".local_chat" / "onboarding_state.json"
    )
    return app


def test_playbook_list_and_show(tmp_path):
    app = build_playbook_app(tmp_path)
    app.handle_input("/playbook list")
    assert "Available playbooks:" in app.output_field.text
    assert "code-task" in app.output_field.text

    app.handle_input("/playbook show code-task")
    assert "Playbook: code-task" in app.output_field.text
    assert "Steps:" in app.output_field.text


def test_playbook_run_requires_confirmation_for_mutating_step(tmp_path):
    app = build_playbook_app(tmp_path)
    app.handle_input("/playbook run code-task")
    assert "Playbook 'code-task' started" in app.output_field.text
    assert "Confirmation required for mutating step" in app.output_field.text


def test_playbook_run_cancel_with_n(tmp_path):
    app = build_playbook_app(tmp_path)
    app.handle_input("/playbook run code-task")
    app.handle_input("n")
    assert "Playbook cancelled at step" in app.output_field.text


def test_playbook_run_confirm_with_y_advances(tmp_path):
    app = build_playbook_app(tmp_path)
    app.handle_input("/playbook run code-task")
    app.handle_input("y")
    assert "Confirmed. Running:" in app.output_field.text
    assert "Manual input required" in app.output_field.text
