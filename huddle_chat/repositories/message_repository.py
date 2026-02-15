from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

from huddle_chat.constants import AI_DM_ROOM

if TYPE_CHECKING:
    from chat import ChatApp

logger = logging.getLogger(__name__)


class MessageRepository:
    def __init__(self, app: "ChatApp"):
        self.app = app

    def get_room_dir(self, room: str | None = None) -> Path:
        active_room = self.app.sanitize_room_name(room or self.app.current_room)
        base = Path(self.app.rooms_root).resolve()
        target = (base / active_room).resolve()
        if target.parent != base:
            raise ValueError("Invalid room path.")
        return target

    def get_message_file(self, room: str | None = None) -> Path:
        if self.app.is_local_room(room):
            return self.app.get_local_message_file(room)
        return self.get_room_dir(room) / "messages.jsonl"

    def ensure_paths(self) -> None:
        try:
            os.makedirs(self.app.rooms_root, exist_ok=True)
            if not self.app.is_local_room():
                room_dir = self.get_room_dir()
                os.makedirs(room_dir, exist_ok=True)
                os.makedirs(self.app.get_presence_dir(), exist_ok=True)
                self.get_message_file().touch(exist_ok=True)
        except OSError as exc:
            logger.warning("Failed ensuring room paths: %s", exc)

    def list_rooms(self) -> list[str]:
        rooms: list[str] = []
        root = Path(self.app.rooms_root)
        if not root.exists():
            return sorted({self.app.current_room, AI_DM_ROOM})
        for entry in root.iterdir():
            if entry.is_dir():
                rooms.append(self.app.sanitize_room_name(entry.name))
        rooms.append(AI_DM_ROOM)
        if self.app.current_room not in rooms:
            rooms.append(self.app.current_room)
        return sorted(set(rooms))

    def read_lines(self, path: Path) -> list[str]:
        if not path.exists():
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.readlines()
        except OSError:
            return []

    def tail_lines(self, path: Path, limit: int = 300) -> list[str]:
        if limit <= 0:
            return []
        lines = self.read_lines(path)
        if not lines:
            return []
        return lines[-limit:]
