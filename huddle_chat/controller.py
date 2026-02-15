from __future__ import annotations

import time
from threading import Event
from typing import cast
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from huddle_chat.constants import MAX_MESSAGES, PRESENCE_SIDEBAR_MIN_REFRESH_SECONDS
from huddle_chat.event_bus import EventBus
from huddle_chat.events import (
    RebuildSearchEvent,
    RefreshOutputEvent,
    RunCommandEvent,
    SystemMessageEvent,
)
from huddle_chat.models import ChatEvent
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
        self.command_handlers = CommandRegistry(self).build()
        return self.command_handlers

    def register_event_handlers(self, bus: EventBus) -> None:
        bus.subscribe(SystemMessageEvent, self.on_system_message_event)
        bus.subscribe(RefreshOutputEvent, self.on_refresh_output_event)
        bus.subscribe(RebuildSearchEvent, self.on_rebuild_search_event)
        bus.subscribe(RunCommandEvent, self.on_run_command_event)

    def on_system_message_event(self, event: SystemMessageEvent) -> None:
        self.app.append_system_message(event.text)

    def on_refresh_output_event(self, _event: RefreshOutputEvent) -> None:
        self.refresh_output_from_events()

    def on_rebuild_search_event(self, _event: RebuildSearchEvent) -> None:
        self.rebuild_search_hits()

    def on_run_command_event(self, event: RunCommandEvent) -> None:
        self.handle_input(event.command_text)

    def handle_input(self, text: str) -> None:
        self.app.ensure_services_initialized()
        text = text.strip()
        if not text:
            return

        if self.app.memory_service.handle_memory_confirmation_input(text):
            self.app.input_field.text = ""
            return

        if self.app.playbook_service.handle_confirmation_input(text):
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

    def handle_theme_command(self, args: str) -> None:
        from huddle_chat.constants import THEMES

        if not args:
            avail = ", ".join(THEMES.keys())
            self.app.append_system_message(f"Available themes: {avail}")
            return
        target = args.strip().lower()
        if target in THEMES:
            self.app.current_theme = target
            self.app.save_config()
            self.app.application.style = self.app.get_style()
            self.app.application.invalidate()
            return
        self.app.append_system_message(f"Unknown theme '{target}'.")

    def handle_setpath_command(self, args: str) -> None:
        self.app.base_dir = args.strip()
        self.app.save_config()
        self.app.application.exit(result="restart")

    def handle_status_command(self, args: str) -> None:
        self.app.status = args[:20]
        self.app.force_heartbeat()

    def handle_rooms_command(self) -> None:
        rooms = ", ".join(self.app.list_rooms())
        self.app.append_system_message(f"Rooms: {rooms}")

    def handle_room_command(self) -> None:
        self.app.append_system_message(f"Current room: #{self.app.current_room}")

    def handle_aiproviders_command(self) -> None:
        self.app.ensure_services_initialized()
        self.app.append_system_message(
            self.app.command_ops_service.get_ai_provider_summary()
        )

    def handle_aiconfig_command(self, args: str) -> None:
        self.app.ensure_services_initialized()
        self.app.command_ops_service.handle_aiconfig_command(args)

    def handle_ai_command(self, args: str) -> None:
        self.app.ensure_services_initialized()
        self.app.ai_service.handle_ai_command(args)

    def handle_share_command(self, args: str) -> None:
        self.app.ensure_services_initialized()
        self.app.command_ops_service.handle_share_command(args)

    def handle_agent_command(self, args: str) -> None:
        self.app.ensure_services_initialized()
        self.app.command_ops_service.handle_agent_command(args)

    def handle_memory_command(self, args: str) -> None:
        self.app.ensure_services_initialized()
        self.app.memory_service.handle_memory_command(args)

    def get_pending_actions_text(self) -> str:
        self.app.ensure_services_initialized()
        return self.app.action_service.format_pending_actions()

    def prune_terminal_actions(self) -> int:
        self.app.ensure_services_initialized()
        return self.app.action_service.prune_terminal_actions()

    def get_action_details(self, action_id: str) -> str:
        self.app.ensure_services_initialized()
        return self.app.action_service.get_action_details(action_id)

    def decide_action(self, action_id: str, decision: str) -> tuple[bool, str]:
        self.app.ensure_services_initialized()
        return self.app.action_service.decide_action(action_id, decision)

    def handle_toolpaths_command(self, args: str) -> None:
        self.app.ensure_services_initialized()
        self.app.command_ops_service.handle_toolpaths_command(args)

    def handle_help_command(self, args: str) -> None:
        self.app.ensure_services_initialized()
        self.app.help_service.handle_help_command(args)

    def handle_onboard_command(self, args: str) -> None:
        self.app.ensure_services_initialized()
        self.app.help_service.handle_onboard_command(args)

    def handle_playbook_command(self, args: str) -> None:
        self.app.ensure_services_initialized()
        self.app.playbook_service.handle_playbook_command(args)

    def handle_explain_command(self, args: str) -> None:
        self.app.ensure_services_initialized()
        self.app.explain_service.handle_explain_command(args)

    def handle_clear_command(self) -> None:
        self.app.messages = []
        self.app.message_events = []
        self.app.output_field.text = ""
        self.app.search_query = ""
        self.app.search_hits = []
        self.app.active_search_hit_idx = -1

    def handle_me_command(self, args: str) -> None:
        event = self.app.build_event("me", args)
        if not self.app.write_to_file(event):
            self.app.append_system_message(
                "Error: Could not send message. Network busy or locked."
            )

    def rebuild_search_hits(self) -> None:
        self.app.search_hits = []
        self.app.active_search_hit_idx = -1
        if not self.app.search_query:
            return

        pattern = self.app.search_query.lower()
        for idx, line in enumerate(self.app.messages):
            if pattern in line.lower():
                self.app.search_hits.append(idx)

        if self.app.search_hits:
            self.app.active_search_hit_idx = 0
            self.jump_to_search_hit(0)

    def jump_to_search_hit(self, direction: int) -> bool:
        if not self.app.search_hits:
            return False

        if direction != 0:
            self.app.active_search_hit_idx = (
                self.app.active_search_hit_idx + direction
            ) % len(self.app.search_hits)

        target_line = self.app.search_hits[self.app.active_search_hit_idx]
        cursor = 0
        for idx, line in enumerate(self.app.messages):
            if idx == target_line:
                break
            cursor += len(line) + 1
        self.app.output_field.buffer.cursor_position = cursor
        self.app.application.invalidate()
        return True

    def render_event_for_display(self, event: ChatEvent, index: int) -> str:
        rendered = self.app.render_event(event)
        if self.app.is_local_room():
            return f"({index}) {rendered}"
        return rendered

    def get_ai_preview_line(self) -> str:
        self.app.ensure_ai_state_initialized()
        with self.app.ai_state_lock:
            if not self.app.ai_active_request_id:
                return ""
            if self.app.ai_active_room != self.app.current_room:
                return ""
            elapsed = int(max(0, time.monotonic() - self.app.ai_active_started_at))
            provider = self.app.ai_active_provider or "ai"
            model = self.app.ai_active_model
            model_suffix = f":{model}" if model else ""
            base = f"[AI pending {provider}{model_suffix} {elapsed}s]"
            if self.app.ai_preview_text:
                return f"{base} {self.app.ai_preview_text}"
            return base

    def refresh_output_from_events(self) -> None:
        self.app.messages = [
            self.render_event_for_display(event, idx + 1)
            for idx, event in enumerate(self.app.message_events)
        ]
        preview_line = self.get_ai_preview_line()
        if preview_line:
            self.app.messages.append(preview_line)
        if len(self.app.messages) > MAX_MESSAGES:
            overflow = len(self.app.messages) - MAX_MESSAGES
            self.app.messages = self.app.messages[overflow:]
            self.app.message_events = self.app.message_events[overflow:]
        self.app.output_field.text = "\n".join(self.app.messages)
        self.app.output_field.buffer.cursor_position = len(self.app.output_field.text)
        self.app.application.invalidate()

    def update_sidebar(self) -> None:
        room_label = f"Room: #{self.app.current_room}"
        if self.app.is_local_room():
            room_label += " (local)"
        fragments: list[tuple[str, str]] = [
            ("fg:#aaaaaa", room_label),
            ("", "\n"),
            ("", "\n"),
        ]
        users = sorted(
            self.app.online_users.values(),
            key=lambda data: (
                str(data.get("name", "Anonymous")).lower(),
                str(data.get("client_id", "")),
            ),
        )
        name_counts: dict[str, int] = {}
        for data in users:
            name = self.app.sanitize_sidebar_text(data.get("name", "Anonymous"), 64)
            name_counts[name] = name_counts.get(name, 0) + 1

        for idx, data in enumerate(users):
            color = self.app.sanitize_sidebar_color(data.get("color", "white"))
            display_name = self.app.sanitize_sidebar_text(
                data.get("name", "Anonymous"), 64
            )
            client_id = self.app.sanitize_sidebar_text(data.get("client_id", ""), 12)
            if name_counts.get(display_name, 0) > 1 and client_id:
                display_name = f"{display_name} ({client_id[:4]})"
            status = self.app.sanitize_sidebar_text(data.get("status", ""), 80)
            user_room = self.app.sanitize_sidebar_text(data.get("room", ""), 32)
            fragments.append((f"fg:{color}", f"* {display_name}"))
            if status:
                fragments.append(("fg:#888888", f" [{status}]"))
            if user_room:
                fragments.append(("fg:#888888", f" #{user_room}"))
            if idx < len(users) - 1:
                fragments.append(("", "\n"))
        self.app.sidebar_control.text = cast(Any, fragments)
        self.app.application.invalidate()

    def refresh_presence_sidebar(self, force: bool = False) -> None:
        self.app.ensure_presence_health_initialized()
        now = time.monotonic()
        if not force:
            since_last = now - self.app._last_presence_sidebar_refresh_at
            if since_last < PRESENCE_SIDEBAR_MIN_REFRESH_SECONDS:
                return
        self.app._last_presence_sidebar_refresh_at = now
        self.app.online_users = self.app.get_online_users_all_rooms()
        self.update_sidebar()

    def switch_room(self, target_room: str) -> None:
        room = self.app.sanitize_room_name(target_room)
        if room == self.app.current_room:
            self.app.append_system_message(f"Already in #{room}.")
            return

        self.app.current_room = room
        self.app.update_room_paths()
        self.app.ensure_paths()
        self.app.search_query = ""
        self.app.search_hits = []
        self.app.active_search_hit_idx = -1
        self.app.messages = []
        self.app.message_events = []
        self.app.storage_service.load_recent_messages()
        self.refresh_presence_sidebar()
        self.app.save_config()
        self.app.signal_monitor_refresh()
        self.app.append_system_message(f"Joined room #{room}.")

    def start_ai_request_state(
        self, provider: str, model: str, target_room: str, scope: str
    ) -> str | None:
        self.app.ensure_ai_state_initialized()
        with self.app.ai_state_lock:
            if self.app.ai_active_request_id is not None:
                return None
            request_id = uuid4().hex[:10]
            self.app.ai_active_request_id = request_id
            self.app.ai_active_started_at = time.monotonic()
            self.app.ai_active_provider = provider
            self.app.ai_active_model = model
            self.app.ai_active_scope = scope
            self.app.ai_active_room = target_room
            self.app.ai_retry_count = 0
            self.app.ai_preview_text = "connecting..."
            self.app.ai_cancel_event = Event()
            return request_id

    def clear_ai_request_state(self, request_id: str) -> None:
        self.app.ensure_ai_state_initialized()
        with self.app.ai_state_lock:
            if self.app.ai_active_request_id != request_id:
                return
            self.app.ai_active_request_id = None
            self.app.ai_active_started_at = 0.0
            self.app.ai_active_provider = ""
            self.app.ai_active_model = ""
            self.app.ai_active_scope = ""
            self.app.ai_active_room = ""
            self.app.ai_retry_count = 0
            self.app.ai_preview_text = ""
            self.app.ai_cancel_event = Event()

    def is_ai_request_active(self) -> bool:
        self.app.ensure_ai_state_initialized()
        with self.app.ai_state_lock:
            return self.app.ai_active_request_id is not None

    def set_ai_preview_text(self, request_id: str, text: str) -> None:
        self.app.ensure_ai_state_initialized()
        with self.app.ai_state_lock:
            if self.app.ai_active_request_id != request_id:
                return
            self.app.ai_preview_text = text[:180]
        self.refresh_output_from_events()

    def is_ai_request_cancelled(self, request_id: str) -> bool:
        self.app.ensure_ai_state_initialized()
        with self.app.ai_state_lock:
            if self.app.ai_active_request_id != request_id:
                return True
            return self.app.ai_cancel_event.is_set()

    def request_ai_cancel(self) -> bool:
        self.app.ensure_ai_state_initialized()
        with self.app.ai_state_lock:
            if self.app.ai_active_request_id is None:
                return False
            self.app.ai_cancel_event.set()
            self.app.ai_preview_text = "cancellation requested..."
            return True

    def build_ai_status_text(self) -> str:
        self.app.ensure_ai_state_initialized()
        with self.app.ai_state_lock:
            if self.app.ai_active_request_id is None:
                return "No active AI request."
            elapsed = int(max(0, time.monotonic() - self.app.ai_active_started_at))
            return (
                f"AI status: request={self.app.ai_active_request_id}, "
                f"provider={self.app.ai_active_provider}, model={self.app.ai_active_model}, "
                f"scope={self.app.ai_active_scope}, room=#{self.app.ai_active_room}, "
                f"elapsed={elapsed}s, retry={self.app.ai_retry_count}, "
                f"cancelled={self.app.ai_cancel_event.is_set()}"
            )

    def run_ai_preview_pulse(self, request_id: str) -> None:
        self.app.ensure_ai_state_initialized()
        while True:
            with self.app.ai_state_lock:
                if self.app.ai_active_request_id != request_id:
                    return
            self.refresh_output_from_events()
            time.sleep(0.5)
