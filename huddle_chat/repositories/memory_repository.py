from __future__ import annotations

import json
import logging
import os
import random
from pathlib import Path
from typing import TYPE_CHECKING, Any

from huddle_chat.constants import (
    LOCAL_MEMORY_ROOT,
    LOCK_BACKOFF_BASE_SECONDS,
    LOCK_BACKOFF_MAX_SECONDS,
    LOCK_MAX_ATTEMPTS,
    LOCK_TIMEOUT_SECONDS,
    MEMORY_DIR_NAME,
    MEMORY_GLOBAL_FILE,
    MEMORY_PRIVATE_FILE,
    MEMORY_REPO_FILE,
)

if TYPE_CHECKING:
    from chat import ChatApp

logger = logging.getLogger(__name__)


class MemoryRepository:
    def __init__(self, app: "ChatApp"):
        self.app = app

    def get_memory_dir(self) -> Path:
        return (Path(str(self.app.base_dir)) / MEMORY_DIR_NAME).resolve()

    def get_memory_file(self) -> Path:
        return self.get_memory_dir() / MEMORY_GLOBAL_FILE

    def get_private_memory_file(self) -> Path:
        return Path(LOCAL_MEMORY_ROOT).resolve() / MEMORY_PRIVATE_FILE

    def get_repo_memory_file(self) -> Path:
        return Path(LOCAL_MEMORY_ROOT).resolve() / MEMORY_REPO_FILE

    def get_memory_file_for_scope(self, scope: str) -> Path:
        if scope == "private":
            return self.get_private_memory_file()
        if scope == "repo":
            return self.get_repo_memory_file()
        return self.get_memory_file()

    def ensure_memory_paths(self) -> None:
        try:
            memory_dir = self.get_memory_dir()
            os.makedirs(memory_dir, exist_ok=True)
            self.get_memory_file().touch(exist_ok=True)
            os.makedirs(Path(LOCAL_MEMORY_ROOT).resolve(), exist_ok=True)
            self.get_private_memory_file().touch(exist_ok=True)
            self.get_repo_memory_file().touch(exist_ok=True)
        except OSError as exc:
            logger.warning("Failed ensuring memory paths: %s", exc)

    def load_entries_for_scopes(self, scopes: list[str]) -> list[dict[str, Any]]:
        self.ensure_memory_paths()
        entries: list[dict[str, Any]] = []
        for scope in scopes:
            path = self.get_memory_file_for_scope(scope)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if isinstance(data, dict):
                            data.setdefault("scope", scope)
                            entries.append(data)
            except OSError as exc:
                logger.warning("Failed reading memory entries from %s: %s", path, exc)
        return entries

    def append_entry(self, entry: dict[str, Any], scope: str) -> bool:
        self.app.ensure_locking_dependency()
        import chat

        assert chat.portalocker is not None
        self.ensure_memory_paths()
        memory_file = self.get_memory_file_for_scope(scope)
        row = json.dumps(entry, ensure_ascii=True)
        max_attempts = int(getattr(chat, "LOCK_MAX_ATTEMPTS", LOCK_MAX_ATTEMPTS))
        for attempt in range(max_attempts):
            try:
                with chat.portalocker.Lock(
                    str(memory_file),
                    mode="a",
                    timeout=LOCK_TIMEOUT_SECONDS,
                    fail_when_locked=True,
                    encoding="utf-8",
                ) as f:
                    f.write(row + "\n")
                    f.flush()
                    os.fsync(f.fileno())
                return True
            except chat.portalocker.exceptions.LockException:
                pass
            except OSError:
                pass
            if attempt == max_attempts - 1:
                break
            delay = min(
                LOCK_BACKOFF_MAX_SECONDS,
                LOCK_BACKOFF_BASE_SECONDS * (2 ** min(attempt, 5)),
            )
            chat.time.sleep(delay + random.uniform(0, 0.03))
        return False
