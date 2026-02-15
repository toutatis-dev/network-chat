from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from huddle_chat.constants import AGENT_ACTIONS_FILE

if TYPE_CHECKING:
    from chat import ChatApp


class ActionRepository:
    def __init__(self, app: "ChatApp"):
        self.app = app

    def get_actions_audit_file(self) -> Path:
        return self.app.get_agents_dir() / AGENT_ACTIONS_FILE

    def append_action_audit_row(self, row: dict[str, Any]) -> bool:
        return self.app.append_jsonl_row(self.get_actions_audit_file(), row)
