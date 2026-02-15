import json
from datetime import datetime
from threading import Thread
from typing import TYPE_CHECKING, Any
from uuid import uuid4

if TYPE_CHECKING:
    from chat import ChatApp


class ActionService:
    TERMINAL_STATUSES = {"denied", "expired", "completed", "failed"}

    def __init__(self, app: "ChatApp"):
        self.app = app

    def ensure_pending_actions_initialized(self) -> None:
        if not hasattr(self.app, "pending_actions"):
            self.app.pending_actions = {}

    def _append_audit_row(self, row: dict[str, Any]) -> bool:
        repo = getattr(self.app, "action_repository", None)
        if repo is not None:
            return repo.append_action_audit_row(row)
        return self.app.append_jsonl_row(self.app.get_actions_audit_file(), row)

    def create_pending_action(
        self,
        *,
        tool: str,
        summary: str,
        command_preview: str,
        risk_level: str = "med",
        request_id: str = "",
        room: str = "",
        inputs: dict[str, Any] | None = None,
        ttl_seconds: int = 0,
        expires_at: str = "",
    ) -> str:
        self.ensure_pending_actions_initialized()
        action_id = uuid4().hex[:8]
        agent_profile = self.app.get_active_agent_profile()
        row = {
            "action_id": action_id,
            "ts": datetime.now().isoformat(timespec="seconds"),
            "user": self.app.name,
            "agent_profile": str(agent_profile.id or "default"),
            "tool": tool,
            "summary": summary,
            "command_preview": command_preview,
            "risk_level": risk_level,
            "status": "pending",
            "request_id": request_id,
            "room": room or self.app.current_room,
            "inputs": inputs or {},
            "ttl_seconds": ttl_seconds,
            "expires_at": expires_at,
        }
        self.app.pending_actions[action_id] = row
        self._append_audit_row(row)
        return action_id

    def decide_action(self, action_id: str, decision: str) -> tuple[bool, str]:
        self.ensure_pending_actions_initialized()
        action = self.app.pending_actions.get(action_id)
        if action is None:
            return False, f"Unknown action '{action_id}'."
        if self._is_action_expired(action):
            self._mark_action_expired(action_id, action)
            return False, f"Action '{action_id}' is expired."
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
        self._append_audit_row(row)
        if decision == "approved":
            Thread(target=self.execute_action, args=(action_id,), daemon=True).start()
        return True, f"Action {action_id} {decision}."

    def execute_action(self, action_id: str) -> None:
        self.ensure_pending_actions_initialized()
        action = self.app.pending_actions.get(action_id)
        if action is None:
            return
        if self._is_action_expired(action):
            self._mark_action_expired(action_id, action)
            self.app.append_system_message(
                f"Action {action_id} expired before execution."
            )
            return
        if str(action.get("status")) != "approved":
            return
        action["status"] = "running"
        self._append_audit_row(
            {
                "action_id": action_id,
                "ts": datetime.now().isoformat(timespec="seconds"),
                "status": "running",
                "user": self.app.name,
            }
        )
        self.app.append_system_message(
            f"Running action {action_id}: {action.get('summary', '')}"
        )
        result = self.app.tool_service.execute_action(action)
        meta = result.meta
        is_error = result.isError
        status = "failed" if is_error else "completed"
        action["status"] = status
        output_text = ""
        content = result.content
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    output_text = str(block.get("text", ""))
                    break
        action["output_preview"] = output_text
        action["exit_code"] = meta.get("exitCode")
        action["duration_ms"] = meta.get("durationMs")
        self._append_audit_row(
            {
                "action_id": action_id,
                "ts": datetime.now().isoformat(timespec="seconds"),
                "status": status,
                "result": result.model_dump(exclude_none=True),
                "user": self.app.name,
            }
        )
        summary = (
            f"Action {action_id} {status}. "
            f"exit={meta.get('exitCode')} duration={meta.get('durationMs')}ms"
        )
        self.app.append_system_message(summary)

    def format_pending_actions(self) -> str:
        self.ensure_pending_actions_initialized()
        pending = [
            action
            for action in self.app.pending_actions.values()
            if str(action.get("status", "")) == "pending"
        ]
        counts: dict[str, int] = {}
        for action in self.app.pending_actions.values():
            status = str(action.get("status", "")).strip().lower()
            if status and status != "pending":
                counts[status] = counts.get(status, 0) + 1
        if not pending and not counts:
            return "No actions."
        if not pending:
            summary = ", ".join(
                f"{status}={counts[status]}" for status in sorted(counts.keys())
            )
            return (
                "No pending actions.\n"
                f"Other actions: {summary}\n"
                "Use /actions prune to clear terminal actions."
            )
        lines = ["Pending actions:"]
        for action in pending[-10:]:
            lines.append(
                f"{action.get('action_id')} [{action.get('risk_level')}] "
                f"{action.get('tool')} - {action.get('summary')}"
            )
            lines.append(f"  {action.get('command_preview')}")
        if counts:
            summary = ", ".join(
                f"{status}={counts[status]}" for status in sorted(counts.keys())
            )
            lines.append(f"Other actions: {summary}")
            lines.append("Use /actions prune to clear terminal actions.")
        return "\n".join(lines)

    def get_action_details(self, action_id: str) -> str:
        self.ensure_pending_actions_initialized()
        action = self.app.pending_actions.get(action_id)
        if action is None:
            return f"Unknown action '{action_id}'."
        return (
            f"Action {action_id}\n"
            f"Status: {action.get('status')}\n"
            f"Tool: {action.get('tool')}\n"
            f"Summary: {action.get('summary')}\n"
            f"Inputs: {json.dumps(action.get('inputs', {}), ensure_ascii=True)}\n"
            f"Preview: {action.get('command_preview')}\n"
            f"Output: {action.get('output_preview', '')}"
        )

    def load_actions_from_audit(self) -> None:
        self.ensure_pending_actions_initialized()
        repo = getattr(self.app, "action_repository", None)
        path = (
            repo.get_actions_audit_file()
            if repo is not None
            else self.app.get_actions_audit_file()
        )
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
                        if self._is_action_expired(row):
                            self._mark_action_expired(action_id, row)
                        continue
                    if status in {"approved", "running", "completed", "failed"}:
                        if action_id in self.app.pending_actions:
                            self.app.pending_actions[action_id]["status"] = status
                            if "result" in row:
                                self.app.pending_actions[action_id]["result"] = row[
                                    "result"
                                ]
                        continue
                    decision = str(row.get("decision", "")).strip()
                    if (
                        decision in {"approved", "denied"}
                        and action_id in self.app.pending_actions
                    ):
                        self.app.pending_actions[action_id]["status"] = decision
        except OSError:
            return

    def _is_action_expired(self, action: dict[str, Any]) -> bool:
        expires_at = str(action.get("expires_at", "")).strip()
        if not expires_at:
            return False
        try:
            expiry = datetime.fromisoformat(expires_at)
        except ValueError:
            return True
        return datetime.now() >= expiry

    def _mark_action_expired(self, action_id: str, action: dict[str, Any]) -> None:
        if str(action.get("status", "")).strip() == "expired":
            return
        action["status"] = "expired"
        self._append_audit_row(
            {
                "action_id": action_id,
                "ts": datetime.now().isoformat(timespec="seconds"),
                "status": "expired",
                "user": self.app.name,
            }
        )

    def prune_terminal_actions(self) -> int:
        self.ensure_pending_actions_initialized()
        to_remove = [
            action_id
            for action_id, action in self.app.pending_actions.items()
            if str(action.get("status", "")).strip().lower() in self.TERMINAL_STATUSES
        ]
        for action_id in to_remove:
            self.app.pending_actions.pop(action_id, None)
        return len(to_remove)
