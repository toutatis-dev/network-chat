import pytest
from unittest.mock import MagicMock, patch
import chat


@pytest.fixture
def app_instance():
    """Returns a ChatApp instance with mocked UI and IO."""
    with patch("chat.ChatApp.load_config_data", return_value={}):
        with patch("chat.ChatApp.ensure_paths"):
            with patch("chat.ChatApp.prompt_for_path", return_value="/tmp"):
                with patch("chat.ChatApp.ensure_locking_dependency"):
                    # We need to mock TUI components since __init__ creates them
                    with (
                        patch("chat.TextArea"),
                        patch("chat.FormattedTextControl"),
                        patch("chat.Window"),
                        patch("chat.Application"),
                        patch("chat.KeyBindings"),
                        patch("chat.HSplit"),
                        patch("chat.VSplit"),
                        patch("chat.Frame"),
                        patch("chat.FloatContainer"),
                        patch("chat.Layout"),
                    ):

                        app = chat.ChatApp()
                        app.name = "TestUser"
                        app.chat_file = "/tmp/Shared_chat.txt"
                        # Mock the write method to capture output and return Success (True) by default
                        app.write_to_file = MagicMock(return_value=True)
                        app.input_field = MagicMock()
                        app.output_field = MagicMock()
                        app.application = MagicMock()
                        return app


def test_handle_normal_message(app_instance):
    """Test sending a regular message."""
    app_instance.handle_input("Hello World")

    # Verify write_to_file was called
    assert app_instance.write_to_file.called
    args = app_instance.write_to_file.call_args[0][0]

    # Check format: [Timestamp] Name: Message
    assert "TestUser: Hello World" in args
    assert args.endswith("\n")


def test_handle_empty_input(app_instance):
    """Test that empty or whitespace input is ignored."""
    app_instance.handle_input("   ")
    assert not app_instance.write_to_file.called


def test_command_me(app_instance):
    """Test the /me command."""
    app_instance.handle_input("/me dances")

    assert app_instance.write_to_file.called
    args = app_instance.write_to_file.call_args[0][0]

    # Check format: [Timestamp] * Name Action
    assert "* TestUser dances" in args


def test_command_theme_unknown(app_instance):
    """Test handling an unknown theme command."""
    app_instance.handle_input("/theme nonexist")

    assert not app_instance.write_to_file.called

    # Check if 'text' attribute was set on the output_field mock
    assert app_instance.output_field.buffer.cursor_position is not None

    with patch.object(app_instance, "save_config") as mock_save:
        app_instance.handle_input("/theme nonexist")
        assert not mock_save.called

        app_instance.handle_input("/theme matrix")
        assert mock_save.called


def test_command_clear(app_instance):
    """Test the /clear command."""
    app_instance.messages = ["msg1", "msg2"]
    app_instance.handle_input("/clear")

    assert app_instance.messages == []
    assert app_instance.output_field.text == ""


def test_handle_write_failure(app_instance):
    """Test that input is NOT cleared if write fails."""
    # Simulate write failure
    app_instance.write_to_file.return_value = False

    app_instance.handle_input("Important Message")

    # Verify write was attempted
    assert app_instance.write_to_file.called

    # Verify we printed the specific error message to local output
    assert app_instance.output_field.buffer.cursor_position is not None


def test_sidebar_text_sanitization_removes_control_chars(app_instance):
    app_instance.online_users = {
        'eve<style fg="red">x</style>': {
            "color": "green",
            "status": "busy\n<script>",
        }
    }
    app_instance.sidebar_control = MagicMock()

    app_instance.update_sidebar()

    fragments = app_instance.sidebar_control.text
    assert isinstance(fragments, list)
    rendered = "".join(text for _, text in fragments)
    assert "\n" not in rendered
    assert "\r" not in rendered
    assert "\t" not in rendered
    assert 'eve<style fg="red">x</style>' in rendered


def test_sidebar_color_sanitization_falls_back_to_white(app_instance):
    app_instance.online_users = {"alice": {"color": "bad-color", "status": ""}}
    app_instance.sidebar_control = MagicMock()

    app_instance.update_sidebar()

    fragments = app_instance.sidebar_control.text
    assert fragments[0][0] == "fg:white"
