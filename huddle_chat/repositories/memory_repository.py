from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

from huddle_chat.constants import (
    LOCAL_MEMORY_ROOT,
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
