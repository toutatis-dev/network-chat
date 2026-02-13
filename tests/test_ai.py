from pathlib import Path
from threading import Event, Lock
from types import SimpleNamespace
from unittest.mock import patch

import chat


def build_ai_app(tmp_path: Path) -> chat.ChatApp:
    app = chat.ChatApp.__new__(chat.ChatApp)
    app.name = "Tester"
    app.client_id = "tester123456"
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
    app.ai_state_lock = Lock()
    app.ai_active_request_id = None
    app.ai_active_started_at = 0.0
    app.ai_active_provider = ""
    app.ai_active_model = ""
    app.ai_active_scope = ""
    app.ai_active_room = ""
    app.ai_retry_count = 0
    app.ai_preview_text = ""
    app.ai_cancel_event = Event()
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
            "gemini": {"api_key": "g-key", "model": "gemini-2.5-flash"},
            "openai": {"api_key": "o-key", "model": "gpt-4o-mini"},
        },
    }
    app.ensure_paths()
    app.ensure_local_paths()
    app.update_room_paths()
    return app


def test_parse_ai_args_accepts_flags():
    app = chat.ChatApp.__new__(chat.ChatApp)
    parsed, error = app.parse_ai_args(
        "--provider openai --model gpt-5-mini --private summarize this"
    )
    assert error is None
    assert parsed["provider_override"] == "openai"
    assert parsed["model_override"] == "gpt-5-mini"
    assert parsed["is_private"] is True
    assert parsed["prompt"] == "summarize this"


def test_aiconfig_set_key_updates_local_config(tmp_path):
    app = build_ai_app(tmp_path)
    called = {"saved": 0}
    app.save_ai_config_data = lambda: called.__setitem__("saved", called["saved"] + 1)
    app.handle_aiconfig_command("set-key gemini NEWKEY")
    assert app.ai_config["providers"]["gemini"]["api_key"] == "NEWKEY"
    assert called["saved"] == 1


def test_aiconfig_set_key_accepts_provider_first_syntax(tmp_path):
    app = build_ai_app(tmp_path)
    called = {"saved": 0}
    app.save_ai_config_data = lambda: called.__setitem__("saved", called["saved"] + 1)
    app.handle_aiconfig_command("gemini set-key NEWKEY")
    assert app.ai_config["providers"]["gemini"]["api_key"] == "NEWKEY"
    assert called["saved"] == 1


def test_ai_private_targets_local_dm_room(tmp_path):
    app = build_ai_app(tmp_path)
    written: list[tuple[str | None, dict]] = []

    def fake_write(payload, room=None):
        if isinstance(payload, dict):
            written.append((room, payload))
        return True

    app.write_to_file = fake_write
    app.call_ai_provider = lambda **kwargs: "local-answer"
    with patch.object(
        chat,
        "Thread",
        side_effect=lambda target, args, daemon: SimpleNamespace(
            start=lambda: target(*args)
        ),
    ):
        app.handle_ai_command("--private hello from private")
    assert len(written) == 2
    assert written[0][0] == "ai-dm"
    assert written[1][0] == "ai-dm"
    assert written[0][1]["type"] == "ai_prompt"
    assert written[1][1]["type"] == "ai_response"


def test_get_message_file_routes_ai_dm_to_local_storage(tmp_path):
    app = build_ai_app(tmp_path)
    path = app.get_message_file("ai-dm")
    assert ".local_chat" in str(path)
    assert str(path).endswith("ai-dm\\messages.jsonl") or str(path).endswith(
        "ai-dm/messages.jsonl"
    )


def test_ai_dm_renders_share_indexes(tmp_path):
    app = build_ai_app(tmp_path)
    app.current_room = "ai-dm"
    app.message_events = [
        {
            "ts": "2026-01-01T10:00:00",
            "type": "ai_prompt",
            "author": "Tester",
            "text": "Q",
        },
        {
            "ts": "2026-01-01T10:00:01",
            "type": "ai_response",
            "author": "Tester",
            "text": "A",
            "provider": "gemini",
            "model": "gemini-2.5-flash",
        },
    ]
    app.refresh_output_from_events()
    lines = app.output_field.text.splitlines()
    assert lines[0].startswith("(1) ")
    assert lines[1].startswith("(2) ")


def test_ai_status_and_cancel_messages(tmp_path):
    app = build_ai_app(tmp_path)
    app.handle_ai_command("status")
    assert "No active AI request" in app.output_field.text

    app.ai_active_request_id = "abc123"
    app.ai_cancel_event = Event()
    app.handle_ai_command("cancel")
    assert "AI cancellation requested" in app.output_field.text
    assert app.ai_cancel_event.is_set()


def test_ai_busy_rejects_new_request(tmp_path):
    app = build_ai_app(tmp_path)
    app.ai_active_request_id = "busy123"
    app.ai_cancel_event = Event()
    app.handle_ai_command("hello while busy")
    assert "AI busy. Use /ai status or /ai cancel." in app.output_field.text
