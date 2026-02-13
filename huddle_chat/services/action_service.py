import json
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

if TYPE_CHECKING:
    from chat import ChatApp


class ActionService:
    def __init__(self, app: "ChatApp"):
        self.app = app

    def ensure_pending_actions_initialized(self) -> None:
        if not hasattr(self.app, "pending_actions"):
            self.app.pending_actions = {}

    def create_pending_action(
        self,
        *,
        tool: str,
        summary: str,
        command_preview: str,
        risk_level: str = "med",
    ) -> str:
        self.ensure_pending_actions_initialized()
        action_id = uuid4().hex[:8]
        row = {
            "action_id": action_id,
            "ts": datetime.now().isoformat(timespec="seconds"),
            "user": self.app.name,
            "agent_profile": self.app.get_active_agent_profile().get("id", "default"),
            "tool": tool,
            "summary": summary,
            "command_preview": command_preview,
            "risk_level": risk_level,
            "status": "pending",
        }
        self.app.pending_actions[action_id] = row
        self.app.append_jsonl_row(self.app.get_actions_audit_file(), row)
        return action_id

    def decide_action(self, action_id: str, decision: str) -> tuple[bool, str]:
        self.ensure_pending_actions_initialized()
        action = self.app.pending_actions.get(action_id)
        if action is None:
            return False, f"Unknown action '{action_id}'."
        if action.get("status") != "pending":
            return False, f"Action '{action_id}' is already {action.get('status')}."
        if decision not in {"approved", "denied"}:
            return False, "Decision must be approved or denied."
        action["status"] = decision
        row = {
            "action_id": action_id,
            "ts": datetime.now().isoformat(timespec="seconds"),
            "user": self.app.name,
            "decision": decision,
        }
        self.app.append_jsonl_row(self.app.get_actions_audit_file(), row)
        return True, f"Action {action_id} {decision}."

    def format_pending_actions(self) -> str:
        self.ensure_pending_actions_initialized()
        pending = [
            action
            for action in self.app.pending_actions.values()
            if str(action.get("status", "")) == "pending"
        ]
        if not pending:
            return "No pending actions."
        lines = ["Pending actions:"]
        for action in pending[-10:]:
            lines.append(
                f"{action.get('action_id')} [{action.get('risk_level')}] {action.get('summary')}"
            )
            lines.append(f"  {action.get('command_preview')}")
        return "\n".join(lines)

    def load_actions_from_audit(self) -> None:
        self.ensure_pending_actions_initialized()
        path = self.app.get_actions_audit_file()
        if not path.exists():
            return
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
                    if not isinstance(row, dict):
                        continue
                    action_id = str(row.get("action_id", "")).strip()
                    if not action_id:
                        continue
                    status = str(row.get("status", "")).strip()
                    if status == "pending":
                        self.app.pending_actions[action_id] = row
                        continue
                    decision = str(row.get("decision", "")).strip()
                    if (
                        decision in {"approved", "denied"}
                        and action_id in self.app.pending_actions
                    ):
                        self.app.pending_actions[action_id]["status"] = decision
        except OSError:
            return
