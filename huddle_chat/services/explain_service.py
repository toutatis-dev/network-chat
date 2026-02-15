from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chat import ChatApp


class ExplainService:
    def __init__(self, app: "ChatApp") -> None:
        self.app = app

    def _truncate(self, text: str, limit: int = 140) -> str:
        cleaned = str(text).strip()
        if len(cleaned) <= limit:
            return cleaned
        return cleaned[:limit] + "..."

    def explain_action(self, action_id: str) -> str:
        action = self.app.pending_actions.get(action_id)
        if action is None:
            return f"Unknown action '{action_id}'. Run /actions to list known IDs."

        status = str(action.get("status", "pending")).strip().lower() or "pending"
        tool = str(action.get("tool", ""))
        risk = str(action.get("risk_level", "med"))
        summary = self._truncate(str(action.get("summary", "")), 200)
        command_preview = self._truncate(str(action.get("command_preview", "")), 180)

        inputs = action.get("inputs", {})
        input_keys = []
        if isinstance(inputs, dict):
            input_keys = sorted(str(k) for k in inputs.keys())

        if status == "pending":
            next_step = f"Review details: /action {action_id} then decide with /approve {action_id} or /deny {action_id}."
        elif status == "running":
            next_step = (
                f"Execution in progress. Re-check details with /action {action_id}."
            )
        elif status in {"completed", "failed", "denied", "expired"}:
            next_step = "Check summary via /actions. Use /actions prune to clear terminal records."
        else:
            next_step = f"Check /action {action_id} for latest status."

        lines = [
            f"Action {action_id}",
            f"status={status} risk={risk} tool={tool}",
            f"summary={summary or '(none)'}",
            f"command={command_preview or '(none)'}",
            f"inputs={', '.join(input_keys) if input_keys else '(none)'}",
            f"room={action.get('room', '')} request_id={action.get('request_id', '')}",
            f"Next: {next_step}",
        ]
        return "\n".join(lines)

    def explain_agent(self) -> str:
        profile = self.app.get_active_agent_profile()
        profile_id = str(profile.id or "default")
        name = str(profile.name or "")
        version = profile.version or 1

        memory_scopes = "team"
        memory_policy = profile.memory_policy
        # Pydantic model MemoryPolicy
        scopes = memory_policy.scopes
        if isinstance(scopes, list) and scopes:
            memory_scopes = ",".join(str(item) for item in scopes)

        route_count = 0
        route_preview: list[str] = []
        routing_policy = profile.routing_policy
        routes = routing_policy.routes
        if routes:
            route_count = len(routes)
            for key in ("chat_general", "code_analysis", "memory_rerank"):
                value = routes.get(key)
                if value:
                    route_preview.append(
                        f"{key}->{value.get('provider', '?')}:{value.get('model', '?')}"
                    )

        tool_policy = profile.tool_policy
        mode = str(tool_policy.mode or "unknown")
        require_approval = str(tool_policy.require_approval)
        allowed_count = 0
        allowed_tools = tool_policy.allowed_tools
        if isinstance(allowed_tools, list):
            allowed_count = len(allowed_tools)

        lines = [
            f"Agent profile={profile_id} name={name} version={version}",
            f"memory_scopes={memory_scopes}",
            f"routes={route_count} ({'; '.join(route_preview) if route_preview else 'no key routes set'})",
            f"tool_policy mode={mode} require_approval={require_approval} allowed_tools={allowed_count}",
            "Next: Use /agent route or /agent memory to adjust behavior.",
        ]
        return "\n".join(lines)

    def explain_tool(self, tool_name: str) -> str:
        definition = self.app.tool_service.registry.get_definition(tool_name)
        if definition is None:
            return f"Unknown tool '{tool_name}'. Use /help tools for tool workflow guidance."

        title = str(definition.title or tool_name)
        description = str(definition.description or "")
        schema = definition.inputSchema or {}
        required: list[str] = []
        properties: list[str] = []
        if isinstance(schema, dict):
            req = schema.get("required", [])
            if isinstance(req, list):
                required = [str(v) for v in req]
            props = schema.get("properties", {})
            if isinstance(props, dict):
                properties = sorted(str(k) for k in props.keys())

        annotations = definition.annotations or {}
        risk = "med"
        read_only = "?"
        requires_approval = "?"
        if isinstance(annotations, dict):
            risk = str(annotations.get("riskLevel", "med"))
            read_only = str(annotations.get("readOnlyHint", "?"))
            requires_approval = str(annotations.get("requiresApproval", "?"))

        allowed = self.app.tool_service.is_tool_allowed(tool_name)
        tool_paths = self.app.get_tool_paths()
        lines = [
            f"Tool {tool_name} ({title})",
            description,
            f"required_args={', '.join(required) if required else '(none)'}",
            f"args={', '.join(properties) if properties else '(none)'}",
            f"risk={risk} read_only={read_only} requires_approval={requires_approval}",
            f"allowed_by_agent_policy={allowed}",
            f"tool_paths={', '.join(tool_paths) if tool_paths else '(none configured; base_dir still allowed)'}",
            (
                "Example: /ai --act propose a "
                + tool_name
                + " action with required arguments"
            ),
        ]
        return "\n".join(lines)

    def handle_explain_command(self, args: str) -> None:
        trimmed = args.strip()
        if not trimmed or trimmed.lower() == "help":
            self.app.append_system_message(
                "Explain commands: /explain action <id>, /explain agent, /explain tool <name>"
            )
            return

        tokens = trimmed.split()
        subject = tokens[0].lower()

        if subject == "action":
            if len(tokens) < 2:
                self.app.append_system_message("Usage: /explain action <action-id>")
                return
            self.app.append_system_message(self.explain_action(tokens[1]))
            return

        if subject == "agent":
            self.app.append_system_message(self.explain_agent())
            return

        if subject == "tool":
            if len(tokens) < 2:
                self.app.append_system_message("Usage: /explain tool <tool-name>")
                return
            self.app.append_system_message(self.explain_tool(tokens[1]))
            return

        self.app.append_system_message(
            f"Unknown /explain subject '{subject}'. Run /explain help."
        )
