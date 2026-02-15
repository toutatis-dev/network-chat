from __future__ import annotations

from typing import TYPE_CHECKING

from huddle_chat.models import PlaybookDefinition, PlaybookStep
from huddle_chat.playbook_catalog import PLAYBOOKS

if TYPE_CHECKING:
    from chat import ChatApp


class PlaybookService:
    def __init__(self, app: "ChatApp") -> None:
        self.app = app

    def ensure_playbook_state_initialized(self) -> None:
        if not hasattr(self.app, "playbook_run_state"):
            self.app.playbook_run_state = None

    def list_playbooks(self) -> list[tuple[str, str]]:
        rows: list[tuple[str, str]] = []
        for key in sorted(PLAYBOOKS.keys()):
            row = PLAYBOOKS[key]
            rows.append((row.name, row.summary))
        return rows

    def get_playbook(self, name: str) -> PlaybookDefinition | None:
        return PLAYBOOKS.get(name.strip().lower())

    def render_playbook(self, playbook: PlaybookDefinition) -> str:
        lines = [f"Playbook: {playbook.name}", playbook.summary, "", "Steps:"]
        for idx, step in enumerate(playbook.steps, start=1):
            placeholder_text = ""
            if step.placeholders:
                placeholder_text = f" placeholders={','.join(step.placeholders)}"
            lines.append(
                f"{idx}. [{step.kind}] {step.title}{placeholder_text}\n"
                f"   cmd: {step.command_template}\n"
                f"   expect: {step.expected_result}"
            )
        return "\n".join(lines)

    def _is_confirm_required(self, step: PlaybookStep) -> bool:
        return str(step.kind or "").strip().lower() in {"mutating", "approval"}

    def _start_run_state(self, playbook: PlaybookDefinition) -> None:
        self.ensure_playbook_state_initialized()
        self.app.playbook_run_state = {
            "name": playbook.name,
            "step_index": 0,
            "steps": playbook.steps,
            "awaiting_confirmation": False,
        }

    def _clear_run_state(self) -> None:
        self.ensure_playbook_state_initialized()
        self.app.playbook_run_state = None

    def _step_status_header(self, step: PlaybookStep, idx: int, total: int) -> str:
        return f"Playbook step {idx}/{total}: {step.title or 'step'}"

    def _advance_run(self) -> None:
        self.ensure_playbook_state_initialized()
        state = self.app.playbook_run_state
        if not isinstance(state, dict):
            return
        steps = state.get("steps", [])
        if not isinstance(steps, list):
            self._clear_run_state()
            return

        while True:
            idx = int(state.get("step_index", 0))
            total = len(steps)
            if idx >= total:
                name = str(state.get("name", "playbook"))
                self.app.append_system_message(f"Playbook '{name}' completed.")
                self._clear_run_state()
                return

            step = steps[idx]
            if not isinstance(step, PlaybookStep):
                # Should not happen if initialized correctly, but handle gracefully
                state["step_index"] = idx + 1
                continue

            self.app.append_system_message(
                self._step_status_header(step, idx + 1, total)
            )

            if step.requires_input:
                command_template = str(step.command_template or "").strip()
                self.app.append_system_message(
                    f"Manual input required: {command_template}"
                )
                self.app.append_system_message(
                    f"Expected result: {step.expected_result or ''}"
                )
                self._clear_run_state()
                return

            command = str(step.command_template or "").strip()
            if not command:
                state["step_index"] = idx + 1
                continue

            if self._is_confirm_required(step):
                state["awaiting_confirmation"] = True
                state["pending_command"] = command
                state["pending_title"] = str(step.title or "step")
                self.app.append_system_message(
                    "Confirmation required for mutating step. Continue? (y/n)"
                )
                return

            self.app.append_system_message(f"Auto-running: {command}")
            self.app.controller.handle_input(command)
            state["step_index"] = idx + 1

    def handle_confirmation_input(self, text: str) -> bool:
        self.ensure_playbook_state_initialized()
        state = self.app.playbook_run_state
        if not isinstance(state, dict):
            return False
        if not bool(state.get("awaiting_confirmation", False)):
            return False

        lowered = text.strip().lower()
        if lowered not in {"y", "n"}:
            return False

        if lowered == "n":
            title = str(state.get("pending_title", "step"))
            self.app.append_system_message(f"Playbook cancelled at step: {title}")
            self._clear_run_state()
            return True

        command = str(state.get("pending_command", "")).strip()
        if command:
            self.app.append_system_message(f"Confirmed. Running: {command}")
            self.app.controller.handle_input(command)

        state["awaiting_confirmation"] = False
        state["pending_command"] = ""
        state["pending_title"] = ""
        state["step_index"] = int(state.get("step_index", 0)) + 1
        self._advance_run()
        return True

    def handle_playbook_command(self, args: str) -> None:
        trimmed = args.strip()
        if not trimmed or trimmed.lower() == "help":
            self.app.append_system_message(
                "Playbook commands: /playbook list, /playbook show <name>, /playbook run <name>"
            )
            return

        tokens = trimmed.split()
        action = tokens[0].lower()

        if action == "list":
            rows = self.list_playbooks()
            lines = ["Available playbooks:"]
            for name, summary in rows:
                lines.append(f"- {name}: {summary}")
            self.app.append_system_message("\n".join(lines))
            return

        if action == "show":
            if len(tokens) < 2:
                self.app.append_system_message("Usage: /playbook show <name>")
                return
            playbook = self.get_playbook(tokens[1])
            if playbook is None:
                self.app.append_system_message(
                    f"Unknown playbook '{tokens[1]}'. Run /playbook list."
                )
                return
            self.app.append_system_message(self.render_playbook(playbook))
            return

        if action == "run":
            if len(tokens) < 2:
                self.app.append_system_message("Usage: /playbook run <name>")
                return
            playbook = self.get_playbook(tokens[1])
            if playbook is None:
                self.app.append_system_message(
                    f"Unknown playbook '{tokens[1]}'. Run /playbook list."
                )
                return
            if self.app.controller.is_ai_request_active():
                self.app.append_system_message(
                    "Cannot start playbook run while AI request is active. Use /ai status or /ai cancel first."
                )
                return
            self._start_run_state(playbook)
            self.app.append_system_message(
                f"Playbook '{playbook.name}' started (semi-automated mode)."
            )
            self._advance_run()
            return

        self.app.append_system_message(
            f"Unknown /playbook command '{action}'. Run /playbook help."
        )
