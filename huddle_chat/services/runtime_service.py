import asyncio
import logging
import os
import time
from typing import TYPE_CHECKING

from huddle_chat.constants import (
    MONITOR_POLL_INTERVAL_ACTIVE_SECONDS,
    MONITOR_POLL_INTERVAL_MAX_SECONDS,
    MONITOR_POLL_INTERVAL_MIN_SECONDS,
    PRESENCE_REFRESH_INTERVAL_SECONDS,
    MAX_MESSAGES,
)

if TYPE_CHECKING:
    from chat import ChatApp

logger = logging.getLogger(__name__)


class RuntimeService:
    def __init__(self, app: "ChatApp"):
        self.app = app

    async def monitor_messages(self) -> None:
        self.app.ensure_monitor_state_initialized()
        next_presence_refresh = 0.0
        while self.app.running:
            now = time.monotonic()
            if now >= next_presence_refresh:
                self.app.refresh_presence_sidebar()
                next_presence_refresh = now + PRESENCE_REFRESH_INTERVAL_SECONDS

            room = self.app.current_room
            repo = getattr(self.app, "message_repository", None)
            message_file = (
                repo.get_message_file(room)
                if repo is not None
                else self.app.get_message_file(room)
            )
            self.app.last_pos_by_room.setdefault(room, 0)
            had_new_messages = False

            if message_file.exists():
                try:
                    with open(message_file, "r", encoding="utf-8") as f:
                        current_size = os.path.getsize(message_file)
                        last_pos = self.app.last_pos_by_room[room]
                        if current_size < last_pos:
                            logger.warning(
                                "Chat file shrank in room %s from offset %s to %s; resetting.",
                                room,
                                last_pos,
                                current_size,
                            )
                            last_pos = 0
                        f.seek(last_pos)
                        new_lines = f.readlines()
                        if new_lines and room == self.app.current_room:
                            had_new_messages = True
                            for line in new_lines:
                                event = self.app.parse_event_line(line)
                                if event is None:
                                    continue
                                self.app.message_events.append(event)
                                if len(self.app.message_events) > MAX_MESSAGES:
                                    self.app.message_events.pop(0)
                            self.app.refresh_output_from_events()
                            self.app.rebuild_search_hits()
                        self.app.last_pos_by_room[room] = f.tell()
                except OSError as exc:
                    logger.warning(
                        "Failed while monitoring room %s chat file %s: %s",
                        room,
                        message_file,
                        exc,
                    )
            if had_new_messages:
                self.app.monitor_idle_cycles = 0
                self.app.monitor_poll_interval_seconds = (
                    MONITOR_POLL_INTERVAL_MIN_SECONDS
                )
            else:
                self.app.monitor_idle_cycles = min(self.app.monitor_idle_cycles + 1, 20)
                if self.app.monitor_idle_cycles >= 4:
                    self.app.monitor_poll_interval_seconds = min(
                        MONITOR_POLL_INTERVAL_MAX_SECONDS,
                        self.app.monitor_poll_interval_seconds + 0.1,
                    )
                else:
                    self.app.monitor_poll_interval_seconds = (
                        MONITOR_POLL_INTERVAL_ACTIVE_SECONDS
                    )

            if self.app.monitor_refresh_event.is_set():
                self.app.monitor_refresh_event.clear()
                self.app.monitor_poll_interval_seconds = (
                    MONITOR_POLL_INTERVAL_MIN_SECONDS
                )

            await asyncio.sleep(self.app.monitor_poll_interval_seconds)
