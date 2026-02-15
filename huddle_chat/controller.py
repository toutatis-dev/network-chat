from __future__ import annotations

from typing import TYPE_CHECKING, Any

from huddle_chat.commands.registry import CommandRegistry

if TYPE_CHECKING:
    from chat import ChatApp


class ChatController:
    def __init__(self, app: "ChatApp"):
        self.app = app
        self.command_handlers: dict[str, Any] = {}

    def __getattr__(self, item: str) -> Any:
        return getattr(self.app, item)

    def build_command_handlers(self) -> dict[str, Any]:
        self.command_handlers = CommandRegistry(self.app).build()
        return self.command_handlers

    def handle_input(self, text: str) -> None:
        text = text.strip()
        if not text:
            return

        if self.app.handle_memory_confirmation_input(text):
            self.app.input_field.text = ""
            return

        if self.app.handle_playbook_confirmation_input(text):
            self.app.input_field.text = ""
            return

        if text.startswith("/"):
            if not self.command_handlers:
                self.build_command_handlers()
            parts = text.split(" ", 1)
            command = parts[0].lower()
            args = parts[1] if len(parts) > 1 else ""
            handler = self.command_handlers.get(command)
            if handler is None:
                self.app.ensure_services_initialized()
                self.app.append_system_message(
                    self.app.help_service.format_guided_error(
                        problem=f"Unknown command '{command}'.",
                        why="The command is not in the registered slash command list.",
                        next_step="Run /help overview to see available workflows and commands.",
                    )
                )
                self.app.input_field.text = ""
                return
            handler(args)
            self.app.input_field.text = ""
            return

        event = self.app.build_event("chat", text)
        if self.app.write_to_file(event):
            self.app.input_field.text = ""
        else:
            self.app.append_system_message(
                "Error: Could not send message. Network busy or locked."
            )
