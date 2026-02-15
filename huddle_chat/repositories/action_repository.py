from __future__ import annotations

import json
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

    def append_row(self, row: dict[str, Any]) -> bool:
        return self.app.append_jsonl_row(self.get_actions_audit_file(), row)

    def append_action_audit_row(self, row: dict[str, Any]) -> bool:
        return self.append_row(row)

    def load_audit_rows(self) -> list[dict[str, Any]]:
        path = self.get_actions_audit_file()
        if not path.exists():
            return []
        rows: list[dict[str, Any]] = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(row, dict):
                        rows.append(row)
        except OSError:
            return rows
        return rows
