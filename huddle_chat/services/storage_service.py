import json
import logging
import os
import random
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from huddle_chat.constants import (
    EVENT_ALLOWED_TYPES,
    EVENT_SCHEMA_VERSION,
    LOCK_BACKOFF_BASE_SECONDS,
    LOCK_BACKOFF_MAX_SECONDS,
    LOCK_MAX_ATTEMPTS,
    LOCK_TIMEOUT_SECONDS,
    MAX_MESSAGES,
)

if TYPE_CHECKING:
    from chat import ChatApp

logger = logging.getLogger(__name__)


class StorageService:
    def __init__(self, app: "ChatApp"):
        self.app = app

    def parse_event_line(self, line: str) -> dict[str, Any] | None:
        line = line.strip()
        if not line:
            return None
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            logger.warning("Invalid message JSONL row ignored.")
            return None
        if not isinstance(data, dict):
            return None

        event_type = str(data.get("type", "")).strip().lower()
        if event_type not in EVENT_ALLOWED_TYPES:
            logger.warning("Invalid event type '%s' ignored.", event_type)
            return None
        author = data.get("author")
        text = data.get("text")
        if not isinstance(author, str) or not isinstance(text, str):
            logger.warning(
                "Invalid event payload ignored (author/text must be string)."
            )
            return None
        if "v" in data:
            version = data.get("v")
            if not isinstance(version, int):
                logger.warning("Invalid event schema version ignored.")
                return None
            if version > EVENT_SCHEMA_VERSION:
                logger.warning("Future event schema version %s ignored.", version)
                return None
        else:
            data["v"] = EVENT_SCHEMA_VERSION
        if "ts" not in data:
            data["ts"] = datetime.now().isoformat(timespec="seconds")
        if not isinstance(data.get("ts"), str):
            data["ts"] = str(data.get("ts"))
        data["type"] = event_type
        data["author"] = author
        data["text"] = text
        return data

    def read_recent_lines(self, path: Path, max_lines: int) -> list[str]:
        if max_lines <= 0:
            return []
        if not path.exists():
            return []

        raw_lines: list[bytes] = []
        chunk_size = 8192
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            position = f.tell()
            buffer = b""

            while position > 0 and len(raw_lines) <= max_lines:
                read_size = min(chunk_size, position)
                position -= read_size
                f.seek(position)
                buffer = f.read(read_size) + buffer
                raw_lines = buffer.splitlines()

            decoded = [row.decode("utf-8", errors="replace") for row in raw_lines]
            return decoded[-max_lines:]

    def load_recent_messages(self) -> None:
        message_file = self.app.get_message_file()
        if not message_file.exists():
            self.app.output_field.text = ""
            self.app.last_pos_by_room[self.app.current_room] = 0
            return

        loaded_events: list[dict[str, Any]] = []
        try:
            for line in self.read_recent_lines(message_file, MAX_MESSAGES * 2):
                event = self.parse_event_line(line)
                if event is not None:
                    loaded_events.append(event)
            self.app.last_pos_by_room[self.app.current_room] = (
                message_file.stat().st_size
            )
        except OSError as exc:
            logger.warning(
                "Failed loading history for room %s: %s", self.app.current_room, exc
            )
            loaded_events = []
            self.app.last_pos_by_room[self.app.current_room] = 0

        self.app.message_events = loaded_events[-MAX_MESSAGES:]
        self.app.refresh_output_from_events()
        self.app.rebuild_search_hits()

    def write_to_file(
        self, payload: dict[str, Any] | str, room: str | None = None
    ) -> bool:
        self.app.ensure_locking_dependency()
        import chat

        assert chat.portalocker is not None

        message_file = self.app.get_message_file(room)
        for attempt in range(LOCK_MAX_ATTEMPTS):
            try:
                with chat.portalocker.Lock(
                    str(message_file),
                    mode="a",
                    timeout=LOCK_TIMEOUT_SECONDS,
                    fail_when_locked=True,
                    encoding="utf-8",
                ) as f:
                    if isinstance(payload, dict):
                        row = json.dumps(payload, ensure_ascii=True)
                    else:
                        row = payload.rstrip("\n")
                    f.write(row + "\n")
                    f.flush()
                    os.fsync(f.fileno())
                self.app.signal_monitor_refresh()
                return True
            except chat.portalocker.exceptions.LockException:
                pass
            except OSError:
                pass
            except Exception as exc:
                logger.warning("Unexpected write_to_file failure: %s", exc)
                return False

            if attempt == LOCK_MAX_ATTEMPTS - 1:
                break
            delay = min(
                LOCK_BACKOFF_MAX_SECONDS,
                LOCK_BACKOFF_BASE_SECONDS * (2 ** min(attempt, 5)),
            )
            time.sleep(delay + random.uniform(0, 0.03))

        return False
