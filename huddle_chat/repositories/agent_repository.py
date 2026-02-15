from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from huddle_chat.constants import (
    AGENT_AUDIT_FILE,
    AGENT_PROFILES_DIR_NAME,
    AGENTS_DIR_NAME,
)

if TYPE_CHECKING:
    from chat import ChatApp

logger = logging.getLogger(__name__)


class AgentRepository:
    def __init__(self, app: "ChatApp"):
        self.app = app

    def get_agents_dir(self) -> Path:
        return (Path(str(self.app.base_dir)) / AGENTS_DIR_NAME).resolve()

    def get_agent_profiles_dir(self) -> Path:
        return (self.get_agents_dir() / AGENT_PROFILES_DIR_NAME).resolve()

    def get_agent_profile_path(self, profile_id: str) -> Path:
        safe_id = self.app.sanitize_agent_id(profile_id)
        base = self.get_agent_profiles_dir().resolve()
        target = (base / f"{safe_id}.json").resolve()
        if target.parent != base:
            raise ValueError("Invalid agent profile path.")
        return target

    def get_agent_audit_file(self) -> Path:
        return self.get_agents_dir() / AGENT_AUDIT_FILE

    def ensure_agent_paths(self) -> None:
        try:
            os.makedirs(self.get_agent_profiles_dir(), exist_ok=True)
            self.get_agent_audit_file().touch(exist_ok=True)
            self.app.get_actions_audit_file().touch(exist_ok=True)
        except OSError as exc:
            logger.warning("Failed ensuring agent paths: %s", exc)

    def append_agent_audit_row(self, row: dict[str, Any]) -> bool:
        return self.app.append_jsonl_row(self.get_agent_audit_file(), row)
