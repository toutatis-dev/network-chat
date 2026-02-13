import os
import json
import pytest
from unittest.mock import patch, mock_open
import chat

# We mock ChatApp's dependency on TUI and file system to test logic in isolation


@pytest.fixture
def clean_env():
    # Helper to clean up or set up environment variables/paths if needed
    # For these tests, we mostly mock, but good to have a fixture place
    pass


def test_load_config_defaults(clean_env):
    """Test that loading config returns empty dict if file is missing."""
    with patch("os.path.exists", return_value=False):
        app = chat.ChatApp.__new__(
            chat.ChatApp
        )  # Create instance without calling __init__
        config = app.load_config_data()
        assert config == {}


def test_load_config_existing(clean_env):
    """Test loading a valid config file."""
    mock_data = json.dumps({"theme": "nord", "username": "Tester", "path": "/tmp"})
    with patch("os.path.exists", return_value=True):
        with patch("builtins.open", mock_open(read_data=mock_data)):
            app = chat.ChatApp.__new__(chat.ChatApp)
            config = app.load_config_data()
            assert config["theme"] == "nord"
            assert config["username"] == "Tester"


def test_save_config(clean_env):
    """Test that save_config writes the correct JSON."""
    app = chat.ChatApp.__new__(chat.ChatApp)
    app.base_dir = "/tmp/chat"
    app.current_theme = "matrix"
    app.name = "Neo"

    with patch("builtins.open", mock_open()) as mocked_file:
        app.save_config()

        # Verify file was opened for writing
        mocked_file.assert_called_with("chat_config.json", "w")

        # Verify JSON content written
        # We combine all write calls to check the full JSON string
        handle = mocked_file()
        # Collect all write calls
        written_chunks = [call.args[0] for call in handle.write.call_args_list]
        full_json = "".join(written_chunks)

        written_data = json.loads(full_json)

        assert written_data["path"] == "/tmp/chat"
        assert written_data["theme"] == "matrix"
        assert written_data["username"] == "Neo"
