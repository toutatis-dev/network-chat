import json
import logging
from unittest.mock import mock_open, patch

import chat


def test_load_config_defaults_when_missing():
    with patch("os.path.exists", return_value=False):
        app = chat.ChatApp.__new__(chat.ChatApp)
        assert app.load_config_data() == {}


def test_load_config_existing_with_room():
    mock_data = json.dumps(
        {
            "theme": "nord",
            "username": "Tester",
            "path": "/tmp",
            "room": "dev",
            "client_id": "abc123def456",
        }
    )
    with patch("os.path.exists", return_value=True):
        with patch("builtins.open", mock_open(read_data=mock_data)):
            app = chat.ChatApp.__new__(chat.ChatApp)
            config = app.load_config_data()
    assert config["theme"] == "nord"
    assert config["username"] == "Tester"
    assert config["room"] == "dev"
    assert config["client_id"] == "abc123def456"


def test_save_config_writes_room():
    app = chat.ChatApp.__new__(chat.ChatApp)
    app.base_dir = "/tmp/chat"
    app.current_theme = "matrix"
    app.name = "Neo"
    app.current_room = "ops"
    app.client_id = "abc123def456"

    with patch("builtins.open", mock_open()) as mocked_file:
        app.save_config()

    mocked_file.assert_called_with("chat_config.json", "w", encoding="utf-8")
    handle = mocked_file()
    written_chunks = [call.args[0] for call in handle.write.call_args_list]
    full_json = "".join(written_chunks)
    payload = json.loads(full_json)
    assert payload["path"] == "/tmp/chat"
    assert payload["theme"] == "matrix"
    assert payload["username"] == "Neo"
    assert payload["room"] == "ops"
    assert payload["client_id"] == "abc123def456"


def test_load_config_invalid_json_logs_warning(caplog):
    with patch("os.path.exists", return_value=True):
        with patch("builtins.open", mock_open(read_data="{bad-json")):
            app = chat.ChatApp.__new__(chat.ChatApp)
            with caplog.at_level(logging.WARNING):
                config = app.load_config_data()
    assert config == {}
    assert "Failed to load config from chat_config.json" in caplog.text
