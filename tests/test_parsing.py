from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import chat


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
    assert payload["type"] == "chat"
    assert payload["author"] == "TestUser"
    assert payload["text"] == "Hello World"


def test_handle_empty_input(app_instance):
    app_instance.write_to_file = MagicMock(return_value=True)
    app_instance.handle_input("   ")
    assert not app_instance.write_to_file.called


def test_command_me(app_instance):
    app_instance.write_to_file = MagicMock(return_value=True)
    app_instance.handle_input("/me dances")
    payload = app_instance.write_to_file.call_args.args[0]
    assert payload["type"] == "me"
    assert payload["text"] == "dances"


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
        {"ts": "1", "type": "chat", "author": "a", "text": "alpha"},
        {"ts": "2", "type": "chat", "author": "a", "text": "beta alpha"},
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
        {"ts": "1", "type": "chat", "author": "a", "text": "msg1"}
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
