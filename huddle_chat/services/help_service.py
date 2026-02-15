import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from huddle_chat.help_catalog import HELP_TOPICS
from huddle_chat.models import ChatEvent

if TYPE_CHECKING:
    from chat import ChatApp


class HelpService:
    def __init__(self, app: "ChatApp") -> None:
        self.app = app

    def format_guided_error(self, *, problem: str, why: str, next_step: str) -> str:
        return f"Problem: {problem}\nWhy: {why}\nNext: {next_step}"

    def get_help_topics(self) -> list[str]:
        topics = sorted(HELP_TOPICS.keys())
        if "overview" in topics:
            topics = ["overview", *[topic for topic in topics if topic != "overview"]]
        return topics

    def render_help(self, topic: str | None = None) -> str:
        normalized = (topic or "overview").strip().lower()
        if not normalized:
            normalized = "overview"

        if normalized not in HELP_TOPICS:
            available = ", ".join(self.get_help_topics())
            return self.format_guided_error(
                problem=f"Unknown help topic '{normalized}'.",
                why="Help topics are fixed so command guidance stays deterministic.",
                next_step=f"Run /help to list topics. Available: {available}",
            )

        entry = HELP_TOPICS[normalized]
        lines = [
            f"Help: {entry['title']}",
            entry["summary"],
            "",
            "Commands:",
        ]
        for command in entry["commands"]:
            lines.append(f"- {command}")

        if entry["examples"]:
            lines.extend(["", "Examples:"])
            for example in entry["examples"]:
                lines.append(f"- {example}")

        if entry["common_errors"]:
            lines.extend(["", "Common mistakes:"])
            for row in entry["common_errors"]:
                lines.append(f"- {row}")

        if entry["related_topics"]:
            lines.extend(["", f"Related: {', '.join(entry['related_topics'])}"])

        lines.extend(["", "More: /onboard start for guided setup and first workflow."])
        return "\n".join(lines)

    def handle_help_command(self, args: str) -> None:
        topic = args.strip()
        if not topic:
            self.app.append_system_message(self.render_help("overview"))
            topics = ", ".join(self.get_help_topics())
            self.app.append_system_message(f"Help topics: {topics}")
            return
        self.app.append_system_message(self.render_help(topic))

    def _onboarding_default_state(self) -> dict[str, Any]:
        return {
            "started_at": "",
            "completed_at": "",
            "steps": {
                "provider_configured": False,
                "sent_ai_prompt": False,
                "reviewed_or_decided_action": False,
                "saved_memory": False,
            },
        }

    def _normalize_onboarding_state(self, payload: Any) -> dict[str, Any]:
        state = self._onboarding_default_state()
        if not isinstance(payload, dict):
            return state

        started_at = payload.get("started_at")
        completed_at = payload.get("completed_at")
        if isinstance(started_at, str):
            state["started_at"] = started_at
        if isinstance(completed_at, str):
            state["completed_at"] = completed_at

        steps = payload.get("steps")
        if isinstance(steps, dict):
            for key in state["steps"]:
                value = steps.get(key)
                if isinstance(value, bool):
                    state["steps"][key] = value
        return state

    def load_onboarding_state(self) -> dict[str, Any]:
        path = self.app.get_onboarding_state_path()
        try:
            with open(path, "r", encoding="utf-8") as f:
                return self._normalize_onboarding_state(json.load(f))
        except (OSError, json.JSONDecodeError):
            return self._onboarding_default_state()

    def save_onboarding_state(self, state: dict[str, Any]) -> None:
        path = self.app.get_onboarding_state_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
        except OSError:
            return

    def _has_provider_configuration(self) -> bool:
        ai_config = getattr(self.app, "ai_config", {})
        if not isinstance(ai_config, dict):
            return False
        default_provider = (
            str(ai_config.get("default_provider", "gemini")).strip().lower()
        )
        providers = ai_config.get("providers", {})
        if not isinstance(providers, dict):
            return False
        cfg = providers.get(default_provider, {})
        if not isinstance(cfg, dict):
            return False
        key = str(cfg.get("api_key", "")).strip()
        model = str(cfg.get("model", "")).strip()
        return bool(key and model)

    def _scan_recent_event_types(self, path: Path, limit: int = 300) -> list[str]:
        if not path.exists():
            return []
        event_types: list[str] = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()[-limit:]
        except OSError:
            return []
        for line in lines:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                event_types.append(str(row.get("type", "")).strip().lower())
        return event_types

    def _has_ai_prompt(self) -> bool:
        # self.app.message_events is a list[ChatEvent]
        for event in getattr(self.app, "message_events", []):
            if isinstance(event, ChatEvent):
                if str(event.type or "").strip().lower() == "ai_prompt":
                    return True
            elif isinstance(event, dict):
                # Fallback if somehow dicts sneak in (e.g. tests not fully updated)
                if str(event.get("type", "")).strip().lower() == "ai_prompt":
                    return True
        ai_dm_file = self.app.get_local_message_file("ai-dm")
        return "ai_prompt" in self._scan_recent_event_types(ai_dm_file)

    def _has_action_review_or_decision(self) -> bool:
        if getattr(self.app, "pending_actions", {}):
            return True
        action_repo = getattr(self.app, "action_repository", None)
        path = (
            action_repo.get_actions_audit_file()
            if action_repo is not None
            else self.app.get_actions_audit_file()
        )
        if not path.exists():
            return False
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
                    if "action_id" not in row:
                        continue
                    status = str(row.get("status", "")).strip().lower()
                    decision = str(row.get("decision", "")).strip().lower()
                    if status in {
                        "pending",
                        "approved",
                        "running",
                        "completed",
                        "failed",
                        "expired",
                        "denied",
                    }:
                        return True
                    if decision in {"approved", "denied"}:
                        return True
        except OSError:
            return False
        return False

    def _has_saved_memory(self) -> bool:
        memory_repo = getattr(self.app, "memory_repository", None)
        if memory_repo is not None:
            paths = (
                memory_repo.get_memory_file(),
                memory_repo.get_private_memory_file(),
                memory_repo.get_repo_memory_file(),
            )
        else:
            paths = (
                self.app.get_memory_file(),
                self.app.get_private_memory_file(),
                self.app.get_repo_memory_file(),
            )

        for path in paths:
            if not path.exists():
                continue
            try:
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            return True
            except OSError:
                continue
        return False

    def evaluate_onboarding_steps(self) -> dict[str, bool]:
        return {
            "provider_configured": self._has_provider_configuration(),
            "sent_ai_prompt": self._has_ai_prompt(),
            "reviewed_or_decided_action": self._has_action_review_or_decision(),
            "saved_memory": self._has_saved_memory(),
        }

    def _sync_onboarding_state(self, state: dict[str, Any]) -> dict[str, Any]:
        steps = self.evaluate_onboarding_steps()
        for key, value in steps.items():
            state["steps"][key] = bool(value)

        if all(steps.values()) and not state.get("completed_at"):
            state["completed_at"] = datetime.now().isoformat(timespec="seconds")
        return state

    def render_onboarding_status(self, state: dict[str, Any]) -> str:
        step_labels = {
            "provider_configured": "Configure default provider key+model",
            "sent_ai_prompt": "Send at least one AI prompt",
            "reviewed_or_decided_action": "Inspect or decide at least one action",
            "saved_memory": "Save at least one memory entry",
        }

        lines = ["Onboarding status:"]
        for key in (
            "provider_configured",
            "sent_ai_prompt",
            "reviewed_or_decided_action",
            "saved_memory",
        ):
            done = bool(state["steps"].get(key))
            marker = "[x]" if done else "[ ]"
            lines.append(f"{marker} {step_labels[key]}")

        lines.append("")
        if not state.get("started_at"):
            lines.append("Not started. Run: /onboard start")
        elif state.get("completed_at"):
            lines.append(f"Completed at: {state['completed_at']}")
        else:
            lines.append("In progress.")

        next_hint = self.next_onboarding_hint(state)
        if next_hint:
            lines.append(f"Next step: {next_hint}")

        lines.append("Use /help overview for workflow map.")
        return "\n".join(lines)

    def next_onboarding_hint(self, state: dict[str, Any]) -> str:
        steps = state["steps"]
        if not steps.get("provider_configured", False):
            return "Configure provider: /aiconfig set-key <provider> <key> then /aiconfig set-model <provider> <model>."
        if not steps.get("sent_ai_prompt", False):
            return "Run your first AI request: /ai hello"
        if not steps.get("reviewed_or_decided_action", False):
            return "Try action workflow: /ai --act <prompt>, then /actions and /action <id>."
        if not steps.get("saved_memory", False):
            return "Capture memory: /memory add then /memory confirm"
        return "All onboarding steps done."

    def handle_onboard_command(self, args: str) -> None:
        action = args.strip().lower() or "status"
        state = self.load_onboarding_state()

        if action == "start":
            if not state.get("started_at"):
                state["started_at"] = datetime.now().isoformat(timespec="seconds")
            state["completed_at"] = ""
            state = self._sync_onboarding_state(state)
            self.save_onboarding_state(state)
            self.app.append_system_message("Onboarding started.")
            self.app.append_system_message(self.render_onboarding_status(state))
            return

        if action == "reset":
            state = self._onboarding_default_state()
            self.save_onboarding_state(state)
            self.app.append_system_message("Onboarding state reset.")
            self.app.append_system_message("Run /onboard start to begin again.")
            return

        if action == "status":
            state = self._sync_onboarding_state(state)
            self.save_onboarding_state(state)
            self.app.append_system_message(self.render_onboarding_status(state))
            return

        self.app.append_system_message(
            self.format_guided_error(
                problem=f"Unknown /onboard command '{action}'.",
                why="Supported onboarding actions are fixed for consistent guidance.",
                next_step="Run /onboard status, /onboard start, or /onboard reset.",
            )
        )
