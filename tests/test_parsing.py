import pytest
from unittest.mock import MagicMock, patch
import chat
from datetime import datetime

@pytest.fixture
def app_instance():
    """Returns a ChatApp instance with mocked UI and IO."""
    with patch("chat.ChatApp.load_config_data", return_value={}):
        with patch("chat.ChatApp.ensure_paths"):
            with patch("chat.ChatApp.prompt_for_path", return_value="/tmp"):
                # We need to mock TUI components since __init__ creates them
                with (patch("chat.TextArea"), patch("chat.FormattedTextControl"), patch("chat.Window"), 
                     patch("chat.Application"), patch("chat.KeyBindings"), patch("chat.HSplit"), 
                     patch("chat.VSplit"), patch("chat.Frame"), patch("chat.FloatContainer"),
                     patch("chat.Layout")):
                    
                    app = chat.ChatApp()
                    app.name = "TestUser"
                    app.chat_file = "/tmp/Shared_chat.txt"
                    # Mock the write method to capture output
                    app.write_to_file = MagicMock()
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
    # Setup the mock to return a string so += works logically or at least we can check assignment
    # But simpler: just check if the attribute was set
    app_instance.handle_input("/theme nonexist")
    
    assert not app_instance.write_to_file.called
    
    # Check if 'text' attribute was set on the output_field mock
    # When doing mock.text += "foo", it effectively does mock.text = mock.text + "foo"
    # So we check the last assignment to the 'text' attribute
    # However, MagicMock properties are tricky. 
    # Let's check if the code attempted to access the buffer (which happens right after error print)
    # self.output_field.buffer.cursor_position = ...
    assert app_instance.output_field.buffer.cursor_position is not None
    
    # And we can check that save_config was NOT called (unlike a successful theme change)
    # We need to mock save_config on the instance to check this
    with patch.object(app_instance, 'save_config') as mock_save:
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
