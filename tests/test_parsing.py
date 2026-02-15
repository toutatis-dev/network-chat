from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document

import chat
from huddle_chat.models import ChatEvent


@pytest.fixture
def app_instance(tmp_path):
    app = chat.ChatApp.__new__(chat.ChatApp)
    app.name = "TestUser"
    app.client_id = "testuser1234"
    app.color = "green"
    app.status = ""
    app.current_room = "general"
    app.base_dir = str(tmp_path)
    app.rooms_root = str(tmp_path / "rooms")
    Path(app.rooms_root).mkdir(parents=True, exist_ok=True)
    app.presence_file_id = app.client_id
    app.messages = []
    app.message_events = []
    app.online_users = {}
    app.last_pos_by_room = {}
    app.search_query = ""
    app.search_hits = []
    app.active_search_hit_idx = -1
    app.input_field = SimpleNamespace(text="")
    app.output_field = SimpleNamespace(
        text="", buffer=SimpleNamespace(cursor_position=0)
    )
    app.application = MagicMock()
    app.sidebar_control = SimpleNamespace(text=[])
    app.ensure_paths()
    app.update_room_paths()
    return app


def test_handle_normal_message(app_instance):
    app_instance.write_to_file = MagicMock(return_value=True)
    app_instance.handle_input("Hello World")

    assert app_instance.write_to_file.called
    payload = app_instance.write_to_file.call_args.args[0]
    assert payload.type == "chat"
    assert payload.author == "TestUser"
    assert payload.text == "Hello World"


def test_handle_empty_input(app_instance):
    app_instance.write_to_file = MagicMock(return_value=True)
    app_instance.handle_input("   ")
    assert not app_instance.write_to_file.called


def test_command_me(app_instance):
    app_instance.write_to_file = MagicMock(return_value=True)
    app_instance.handle_input("/me dances")
    payload = app_instance.write_to_file.call_args.args[0]
    assert payload.type == "me"
    assert payload.text == "dances"


def test_command_theme_unknown(app_instance):
    app_instance.write_to_file = MagicMock(return_value=True)
    app_instance.handle_input("/theme nonexist")
    assert "Unknown theme" in app_instance.output_field.text


def test_status_command_updates_without_spawning_thread(app_instance):
    with (
        patch("chat.Thread") as mock_thread,
        patch.object(app_instance, "force_heartbeat") as mock_force,
    ):
        app_instance.handle_input("/status Busy")

    assert app_instance.status == "Busy"
    assert mock_force.called
    assert not mock_thread.called


def test_join_command_calls_switch_room(app_instance):
    with patch.object(app_instance, "switch_room") as mock_switch:
        app_instance.handle_input("/join dev")
    mock_switch.assert_called_once_with("dev")


def test_rooms_command_prints_rooms(app_instance):
    with patch.object(app_instance, "list_rooms", return_value=["general", "dev"]):
        app_instance.handle_input("/rooms")
    assert "Rooms: general, dev" in app_instance.output_field.text


def test_search_commands_set_and_clear(app_instance):
    app_instance.messages = ["alpha", "beta alpha"]
    app_instance.message_events = [
        ChatEvent(ts="1", type="chat", author="a", text="alpha"),
        ChatEvent(ts="2", type="chat", author="a", text="beta alpha"),
    ]
    app_instance.handle_input("/search alpha")
    assert app_instance.search_query == "alpha"
    assert len(app_instance.search_hits) >= 2
    assert app_instance.search_hits[0:2] == [0, 1]

    app_instance.handle_input("/clearsearch")
    assert app_instance.search_query == ""
    assert app_instance.search_hits == []


def test_command_clear_resets_local_history_and_search(app_instance):
    app_instance.messages = ["msg1"]
    app_instance.message_events = [
        ChatEvent(ts="1", type="chat", author="a", text="msg1")
    ]
    app_instance.search_query = "msg"
    app_instance.search_hits = [0]

    app_instance.handle_input("/clear")

    assert app_instance.messages == []
    assert app_instance.message_events == []
    assert app_instance.search_query == ""
    assert app_instance.search_hits == []


def test_sidebar_color_sanitization_falls_back_to_white(app_instance):
    app_instance.online_users = {
        "alice12345678": {
            "name": "alice",
            "client_id": "alice12345678",
            "color": "bad-color",
            "status": "",
        }
    }
    app_instance.update_sidebar()
    user_fragments = [
        frag for frag in app_instance.sidebar_control.text if "* alice" in frag[1]
    ]
    assert user_fragments
    assert user_fragments[0][0] == "fg:white"


def test_lex_line_highlights_mentions_and_search(app_instance):
    app_instance.online_users = {
        "testuser1234": {
            "name": "TestUser",
            "client_id": "testuser1234",
            "color": "green",
            "status": "",
        }
    }
    app_instance.search_query = "hello"
    tokens = app_instance.lex_line("[12:00:00] TestUser: hello @TestUser")
    styles = [style for style, _ in tokens]
    assert "class:search-match" in styles
    assert "class:mention" in styles


def test_mention_completion_opens_on_at_and_hides_self(app_instance):
    app_instance.online_users = {
        "alice11111111": {
            "name": "Alice",
            "client_id": "alice11111111",
            "color": "green",
            "status": "online",
        },
        "self999999999": {
            "name": "TestUser",
            "client_id": "self999999999",
            "color": "cyan",
            "status": "",
        },
    }
    completer = chat.SlashCompleter(app_instance)
    completions = list(
        completer.get_completions(Document("@", cursor_position=1), CompleteEvent())
    )
    inserted = [c.text for c in completions]
    assert "Alice " in inserted
    assert "TestUser " not in inserted


def test_mention_completion_filters_case_insensitive(app_instance):
    app_instance.online_users = {
        "alice11111111": {"name": "Alice", "client_id": "alice11111111", "status": ""},
        "bob1111111111": {"name": "Bob", "client_id": "bob1111111111", "status": ""},
    }
    completer = chat.SlashCompleter(app_instance)
    completions = list(
        completer.get_completions(Document("@AL", cursor_position=3), CompleteEvent())
    )
    assert [c.text for c in completions] == ["Alice "]


def test_mention_completion_supports_spaced_names(app_instance):
    app_instance.online_users = {
        "jane11111111": {
            "name": "Jane Doe",
            "client_id": "jane11111111",
            "status": "busy",
        }
    }
    completer = chat.SlashCompleter(app_instance)
    completions = list(
        completer.get_completions(Document("@ja", cursor_position=3), CompleteEvent())
    )
    assert completions
    assert completions[0].text == "Jane Doe "


def test_mention_not_triggered_in_email_like_text(app_instance):
    app_instance.online_users = {
        "alice11111111": {"name": "Alice", "client_id": "alice11111111", "status": ""}
    }
    completer = chat.SlashCompleter(app_instance)
    completions = list(
        completer.get_completions(
            Document("email@al", cursor_position=8), CompleteEvent()
        )
    )
    assert completions == []


def test_render_event_does_not_clip_long_text_for_system_help(app_instance):
    long_text = "x" * 800
    event = ChatEvent(
        ts="2026-01-01T10:00:00",
        type="system",
        author="system",
        text=long_text,
    )
    rendered = app_instance.render_event(event)
    assert long_text in rendered


def test_render_event_does_not_clip_long_text_for_ai_response(app_instance):
    long_text = "a" * 900
    event = ChatEvent(
        ts="2026-01-01T10:00:00",
        type="ai_response",
        author="system",
        text=long_text,
        provider="openai",
        model="gpt-4o-mini",
    )
    rendered = app_instance.render_event(event)
    assert long_text in rendered


def test_slash_completion_unchanged_with_theme_prefix(app_instance):
    completer = chat.SlashCompleter(app_instance)
    completions = list(
        completer.get_completions(
            Document("/theme n", cursor_position=8), CompleteEvent()
        )
    )
    assert any(c.text == "nord" for c in completions)


def test_ai_subcommand_completion_shows_status_and_cancel(app_instance):
    completer = chat.SlashCompleter(app_instance)
    completions = list(
        completer.get_completions(Document("/ai ", cursor_position=4), CompleteEvent())
    )
    texts = [c.text for c in completions]
    assert "status" in texts
    assert "cancel" in texts
    assert "--no-memory" in texts


def test_aiconfig_set_model_suggests_provider_models(app_instance):
    app_instance.ai_config = {
        "default_provider": "openai",
        "providers": {"openai": {"api_key": "x", "model": "gpt-4o-mini"}},
    }
    completer = chat.SlashCompleter(app_instance)
    completions = list(
        completer.get_completions(
            Document("/aiconfig set-model openai g", cursor_position=27),
            CompleteEvent(),
        )
    )
    assert any(c.text.startswith("gpt-") for c in completions)


def test_aiconfig_provider_first_completion_suggests_set_actions(app_instance):
    completer = chat.SlashCompleter(app_instance)
    completions = list(
        completer.get_completions(
            Document("/aiconfig gemini ", cursor_position=17), CompleteEvent()
        )
    )
    texts = [c.text for c in completions]
    assert "set-key" in texts
    assert "set-model" in texts


def test_aiconfig_streaming_completion_suggests_stream_controls(app_instance):
    completer = chat.SlashCompleter(app_instance)
    completions = list(
        completer.get_completions(
            Document("/aiconfig streaming ", cursor_position=20),
            CompleteEvent(),
        )
    )
    texts = [c.text for c in completions]
    assert "status" in texts
    assert "on" in texts
    assert "provider" in texts


def test_aiconfig_streaming_provider_completion_suggests_on_off(app_instance):
    completer = chat.SlashCompleter(app_instance)
    text = "/aiconfig streaming provider openai "
    completions = list(
        completer.get_completions(
            Document(text, cursor_position=len(text)),
            CompleteEvent(),
        )
    )
    texts = [c.text for c in completions]
    assert "on" in texts
    assert "off" in texts


def test_help_completion_suggests_topics(app_instance):
    completer = chat.SlashCompleter(app_instance)
    completions = list(
        completer.get_completions(
            Document("/help a", cursor_position=7),
            CompleteEvent(),
        )
    )
    assert any(c.text == "ai" for c in completions)


def test_onboard_completion_suggests_actions(app_instance):
    completer = chat.SlashCompleter(app_instance)
    completions = list(
        completer.get_completions(
            Document("/onboard ", cursor_position=9),
            CompleteEvent(),
        )
    )
    texts = [c.text for c in completions]
    assert "status" in texts
    assert "start" in texts
    assert "reset" in texts


def test_playbook_completion_suggests_subcommands(app_instance):
    completer = chat.SlashCompleter(app_instance)
    completions = list(
        completer.get_completions(
            Document("/playbook ", cursor_position=10),
            CompleteEvent(),
        )
    )
    texts = [c.text for c in completions]
    assert "list" in texts
    assert "show" in texts
    assert "run" in texts


def test_explain_completion_suggests_subjects(app_instance):
    completer = chat.SlashCompleter(app_instance)
    completions = list(
        completer.get_completions(
            Document("/explain ", cursor_position=9),
            CompleteEvent(),
        )
    )
    texts = [c.text for c in completions]
    assert "action" in texts
    assert "agent" in texts
    assert "tool" in texts


def test_parse_event_line_rejects_unknown_event_type(app_instance):
    app_instance.ensure_services_initialized()
    event = app_instance.parse_event_line(
        '{"v":1,"ts":"2026-01-01T00:00:00","type":"mystery","author":"a","text":"b"}'
    )
    assert event is None


def test_parse_event_line_rejects_non_string_fields(app_instance):
    app_instance.ensure_services_initialized()
    event = app_instance.parse_event_line(
        '{"v":1,"ts":"2026-01-01T00:00:00","type":"chat","author":123,"text":false}'
    )
    assert event is None


def test_toolpaths_add_list_remove(app_instance, tmp_path):
    app_instance.ensure_services_initialized()
    app_instance.save_config = MagicMock()
    target = str(tmp_path.resolve())
    app_instance.handle_input(f'/toolpaths add "{target}"')
    assert "Added tool path" in app_instance.output_field.text

    app_instance.handle_input("/toolpaths list")
    assert target in app_instance.output_field.text

    app_instance.handle_input(f'/toolpaths remove "{target}"')
    assert "Removed tool path" in app_instance.output_field.text
