from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

if TYPE_CHECKING:
    from chat import ChatApp

logger = logging.getLogger(__name__)


class PresenceRepository:
    def __init__(self, app: "ChatApp"):
        self.app = app

    def get_presence_dir(self, room: str | None = None) -> Path:
        if self.app.is_local_room(room):
            return self.app.get_local_room_dir(room) / "presence"
        return self.app.get_room_dir(room) / "presence"

    def get_presence_path(self, room: str | None = None) -> Path:
        base = self.get_presence_dir(room).resolve()
        target = (base / self.app.presence_file_id).resolve()
        if target.parent != base:
            raise ValueError("Invalid username for presence path.")
        return target

    def load_presence_entry(
        self, path: Path, fallback_room: str | None, st_mtime: float
    ) -> dict[str, Any] | None:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        client_id = self.app.normalize_client_id(path.name)
        if isinstance(data, dict):
            display_name = str(data.get("name", "Anonymous")).strip() or "Anonymous"
            room_name = self.app.sanitize_room_name(
                str(data.get("room", fallback_room or self.app.current_room))
            )
            normalized = dict(data)
            normalized["name"] = display_name
            normalized["client_id"] = client_id
            normalized["room"] = room_name
            if "last_seen" not in normalized:
                normalized["last_seen"] = st_mtime
            return normalized
        return {
            "name": "Anonymous",
            "color": "white",
            "status": "",
            "client_id": client_id,
            "room": self.app.sanitize_room_name(fallback_room or self.app.current_room),
            "last_seen": st_mtime,
        }

    def get_online_users(self, room: str | None = None) -> dict[str, dict[str, Any]]:
        online: dict[str, dict[str, Any]] = {}
        if self.app.is_local_room(room):
            return online
        now = time.time()
        presence_dir = self.get_presence_dir(room)
        if not presence_dir.exists():
            return online

        for path in presence_dir.iterdir():
            if not path.is_file():
                continue
            try:
                st_mtime = path.stat().st_mtime
                if now - st_mtime >= 30:
                    path.unlink(missing_ok=True)
                    continue
                entry = self.load_presence_entry(
                    path, fallback_room=room, st_mtime=st_mtime
                )
                if entry is not None:
                    client_id = str(entry.get("client_id", ""))
                    online[client_id] = entry
            except OSError as exc:
                logger.warning("Failed to process presence file %s: %s", path, exc)
            except (json.JSONDecodeError, ValueError):
                self.app._drop_malformed_presence(path)
        return online

    def get_online_users_all_rooms(self) -> dict[str, dict[str, Any]]:
        online: dict[str, dict[str, Any]] = {}
        now = time.time()
        root = Path(self.app.rooms_root)
        if not root.exists():
            return online
        for room_dir in root.iterdir():
            if not room_dir.is_dir():
                continue
            room = self.app.sanitize_room_name(room_dir.name)
            presence_dir = room_dir / "presence"
            if not presence_dir.exists() or not presence_dir.is_dir():
                continue
            for path in presence_dir.iterdir():
                if not path.is_file():
                    continue
                try:
                    st_mtime = path.stat().st_mtime
                    if now - st_mtime >= 30:
                        path.unlink(missing_ok=True)
                        continue
                    entry = self.load_presence_entry(
                        path, fallback_room=room, st_mtime=st_mtime
                    )
                    if entry is None:
                        continue
                    client_id = str(entry.get("client_id", ""))
                    seen = online.get(client_id)
                    current_seen = float(entry.get("last_seen", st_mtime))
                    prior_seen = float(seen.get("last_seen", 0.0)) if seen else 0.0
                    if seen is None or current_seen >= prior_seen:
                        online[client_id] = entry
                except OSError as exc:
                    logger.warning("Failed to process presence file %s: %s", path, exc)
                except (json.JSONDecodeError, ValueError):
                    self.app._drop_malformed_presence(path)
        return online

    def write_presence_atomic(self, presence_path: Path, data: dict[str, Any]) -> bool:
        tmp_name = f".{presence_path.name}.tmp-{os.getpid()}-{uuid4().hex[:8]}"
        tmp_path = presence_path.with_name(tmp_name)
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, presence_path)
            return True
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
