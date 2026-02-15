from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from huddle_chat.constants import ACTION_TTL_SECONDS
from huddle_chat.models import ToolCallRequest, ToolCallResult, ToolDefinition
from huddle_chat.services.tool_contract import validate_tool_call_args
from huddle_chat.services.tool_executor import ToolExecutorService
from huddle_chat.services.tool_registry import ToolRegistryService

if TYPE_CHECKING:
    from chat import ChatApp


class ToolService:
    def __init__(self, app: "ChatApp"):
        self.app = app
        self.registry = ToolRegistryService(app)
        self.executor = ToolExecutorService(app)

    def list_tools(self) -> list[ToolDefinition]:
        return self.registry.list_tools_for_policy()

    def build_tools_prompt_block(self) -> str:
        tools = self.list_tools()
        if not tools:
            return "No tools available."
        # Serialize list of Pydantic models
        return json.dumps(
            [t.model_dump(exclude_none=True) for t in tools], ensure_ascii=True
        )

    def parse_ai_action_response(
        self, text: str
    ) -> tuple[str, list[dict[str, Any]], str | None]:
        data = self.app.extract_json_object(text)
        if not isinstance(data, dict):
            return text.strip(), [], "AI action response was not valid JSON."
        answer = str(data.get("answer", "")).strip()
        actions = data.get("proposed_actions", [])
        if not isinstance(actions, list):
            actions = []
        normalized: list[dict[str, Any]] = []
        for row in actions:
            if not isinstance(row, dict):
                continue
            tool_name = str(row.get("tool", "")).strip()
            if not tool_name:
                continue
            arguments = row.get("arguments", {})
            if not isinstance(arguments, dict):
                arguments = {}
            summary = (
                str(row.get("summary", f"Run {tool_name}")).strip()
                or f"Run {tool_name}"
            )
            normalized.append(
                {"tool": tool_name, "arguments": arguments, "summary": summary}
            )
        if not answer:
            answer = text.strip()
        return answer, normalized, None

    def is_tool_allowed(self, tool_name: str) -> bool:
        profile = self.app.get_active_agent_profile()
        policy = profile.tool_policy
        allowed = policy.allowed_tools
        return tool_name in {str(v).strip() for v in allowed}

    def validate_tool_action(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> tuple[bool, str | None]:
        definition = self.registry.get_definition(tool_name)
        if definition is None:
            return False, f"Unknown tool '{tool_name}'."
        if not self.is_tool_allowed(tool_name):
            return False, f"Tool '{tool_name}' is not allowed by active agent policy."
        return validate_tool_call_args(definition, arguments)

    def create_action_from_proposal(
        self,
        *,
        request_id: str,
        room: str,
        tool: str,
        arguments: dict[str, Any],
        summary: str,
    ) -> tuple[bool, str]:
        ok, err = self.validate_tool_action(tool, arguments)
        if not ok:
            return False, err or "Invalid tool action."
        command_preview = f"{tool} {json.dumps(arguments, ensure_ascii=True)}"
        expires = datetime.now() + timedelta(seconds=ACTION_TTL_SECONDS)
        action_id = self.app.create_pending_action(
            tool=tool,
            summary=summary,
            command_preview=command_preview,
            risk_level="med",
            request_id=request_id,
            room=room,
            inputs=arguments,
            ttl_seconds=ACTION_TTL_SECONDS,
            expires_at=expires.isoformat(timespec="seconds"),
        )
        return True, action_id

    def execute_action(self, action: dict[str, Any]) -> ToolCallResult:
        request = ToolCallRequest(
            toolName=str(action.get("tool", "")),
            arguments=(
                action.get("inputs", {})
                if isinstance(action.get("inputs"), dict)
                else {}
            ),
            requestId=str(action.get("request_id", "")),
            actionId=str(action.get("action_id", "")),
            room=str(action.get("room", self.app.current_room)),
            user=self.app.name,
        )
        return self.executor.execute_tool(request)
