from __future__ import annotations

from dataclasses import dataclass, field
from threading import Event, Lock
from typing import Any

from huddle_chat.constants import DEFAULT_ROOM, MONITOR_POLL_INTERVAL_ACTIVE_SECONDS
from huddle_chat.models import ChatEvent


@dataclass
class AppState:
    name: str = "Anonymous"
    color: str = "white"
    status: str = ""
    running: bool = True
    current_theme: str = "default"
    current_room: str = DEFAULT_ROOM
    client_id: str = ""
    presence_file_id: str = ""

    messages: list[str] = field(default_factory=list)
    message_events: list[ChatEvent] = field(default_factory=list)
    online_users: dict[str, dict[str, Any]] = field(default_factory=dict)
    last_pos_by_room: dict[str, int] = field(default_factory=dict)
    search_query: str = ""
    search_hits: list[int] = field(default_factory=list)
    active_search_hit_idx: int = -1

    monitor_refresh_event: Event = field(default_factory=Event)
    monitor_poll_interval_seconds: float = MONITOR_POLL_INTERVAL_ACTIVE_SECONDS
    monitor_idle_cycles: int = 0
    file_observer: Any = None

    ai_state_lock: Lock = field(default_factory=Lock)
    ai_active_request_id: str | None = None
    ai_active_started_at: float = 0.0
    ai_active_provider: str = ""
    ai_active_model: str = ""
    ai_active_scope: str = ""
    ai_active_room: str = ""
    ai_retry_count: int = 0
    ai_preview_text: str = ""
    ai_cancel_event: Event = field(default_factory=Event)

    memory_draft_active: bool = False
    memory_draft_mode: str = "none"
    memory_draft: dict[str, Any] | None = None
    agent_draft_active: bool = False
    agent_draft: dict[str, Any] | None = None
    playbook_run_state: dict[str, Any] | None = None
    pending_actions: dict[str, dict[str, Any]] = field(default_factory=dict)

    presence_malformed_dropped: int = 0
    presence_quarantined: int = 0
    presence_write_failures: int = 0
    presence_malformed_counts: dict[str, int] = field(default_factory=dict)
    last_presence_sidebar_refresh_at: float = 0.0

    tool_paths: list[str] = field(default_factory=list)
    active_agent_profile_id: str = "default"

    def apply_to(self, app: Any) -> None:
        app.name = self.name
        app.color = self.color
        app.status = self.status
        app.running = self.running
        app.current_theme = self.current_theme
        app.current_room = self.current_room
        app.client_id = self.client_id
        app.presence_file_id = self.presence_file_id

        app.messages = self.messages
        app.message_events = self.message_events
        app.online_users = self.online_users
        app.last_pos_by_room = self.last_pos_by_room
        app.search_query = self.search_query
        app.search_hits = self.search_hits
        app.active_search_hit_idx = self.active_search_hit_idx

        app.monitor_refresh_event = self.monitor_refresh_event
        app.monitor_poll_interval_seconds = self.monitor_poll_interval_seconds
        app.monitor_idle_cycles = self.monitor_idle_cycles
        app.file_observer = self.file_observer

        app.ai_state_lock = self.ai_state_lock
        app.ai_active_request_id = self.ai_active_request_id
        app.ai_active_started_at = self.ai_active_started_at
        app.ai_active_provider = self.ai_active_provider
        app.ai_active_model = self.ai_active_model
        app.ai_active_scope = self.ai_active_scope
        app.ai_active_room = self.ai_active_room
        app.ai_retry_count = self.ai_retry_count
        app.ai_preview_text = self.ai_preview_text
        app.ai_cancel_event = self.ai_cancel_event

        app.memory_draft_active = self.memory_draft_active
        app.memory_draft_mode = self.memory_draft_mode
        app.memory_draft = self.memory_draft
        app.agent_draft_active = self.agent_draft_active
        app.agent_draft = self.agent_draft
        app.playbook_run_state = self.playbook_run_state
        app.pending_actions = self.pending_actions

        app.presence_malformed_dropped = self.presence_malformed_dropped
        app.presence_quarantined = self.presence_quarantined
        app.presence_write_failures = self.presence_write_failures
        app._presence_malformed_counts = self.presence_malformed_counts
        app._last_presence_sidebar_refresh_at = self.last_presence_sidebar_refresh_at

        app.tool_paths = self.tool_paths
        app.active_agent_profile_id = self.active_agent_profile_id
