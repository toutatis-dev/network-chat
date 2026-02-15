from __future__ import annotations

from typing import TYPE_CHECKING

from huddle_chat.models import ToolDefinition

if TYPE_CHECKING:
    from chat import ChatApp


class ToolRegistryService:
    def __init__(self, app: "ChatApp"):
        self.app = app

    def get_tool_definitions(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="search_repo",
                title="Search Repository",
                description="Search text in files using a regex or plain query.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "path": {"type": "string"},
                        "maxResults": {"type": "integer"},
                        "maxDurationSec": {"type": "integer"},
                    },
                    "required": ["query"],
                },
                annotations={
                    "readOnlyHint": True,
                    "riskLevel": "low",
                    "requiresApproval": True,
                },
            ),
            ToolDefinition(
                name="list_files",
                title="List Files",
                description="List files recursively under a path.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "maxResults": {"type": "integer"},
                        "maxDurationSec": {"type": "integer"},
                    },
                    "required": [],
                },
                annotations={
                    "readOnlyHint": True,
                    "riskLevel": "low",
                    "requiresApproval": True,
                },
            ),
            ToolDefinition(
                name="read_file",
                title="Read File",
                description="Read a bounded line range from a file.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "startLine": {"type": "integer"},
                        "lineCount": {"type": "integer"},
                        "maxDurationSec": {"type": "integer"},
                    },
                    "required": ["path"],
                },
                annotations={
                    "readOnlyHint": True,
                    "riskLevel": "med",
                    "requiresApproval": True,
                },
            ),
            ToolDefinition(
                name="run_tests",
                title="Run Tests",
                description="Run project tests.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "maxDurationSec": {"type": "integer"},
                    },
                    "required": [],
                },
                annotations={
                    "readOnlyHint": True,
                    "riskLevel": "med",
                    "requiresApproval": True,
                },
            ),
            ToolDefinition(
                name="run_lint",
                title="Run Lint",
                description="Run lint checks.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "maxDurationSec": {"type": "integer"},
                    },
                    "required": [],
                },
                annotations={
                    "readOnlyHint": True,
                    "riskLevel": "low",
                    "requiresApproval": True,
                },
            ),
            ToolDefinition(
                name="run_typecheck",
                title="Run Type Check",
                description="Run static type checks.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "maxDurationSec": {"type": "integer"},
                    },
                    "required": [],
                },
                annotations={
                    "readOnlyHint": True,
                    "riskLevel": "low",
                    "requiresApproval": True,
                },
            ),
            ToolDefinition(
                name="git_status",
                title="Git Status",
                description="Show git working tree state.",
                inputSchema={
                    "type": "object",
                    "properties": {"maxDurationSec": {"type": "integer"}},
                    "required": [],
                },
                annotations={
                    "readOnlyHint": True,
                    "riskLevel": "low",
                    "requiresApproval": True,
                },
            ),
            ToolDefinition(
                name="git_diff",
                title="Git Diff",
                description="Show git diff for working tree or staged changes.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "maxLines": {"type": "integer"},
                        "maxDurationSec": {"type": "integer"},
                    },
                    "required": [],
                },
                annotations={
                    "readOnlyHint": True,
                    "riskLevel": "low",
                    "requiresApproval": True,
                },
            ),
        ]

    def list_tools_for_policy(self) -> list[ToolDefinition]:
        profile = self.app.get_active_agent_profile()
        tool_policy = profile.tool_policy
        allowed: set[str] = set()
        raw = tool_policy.allowed_tools
        if isinstance(raw, list):
            allowed = {str(v).strip() for v in raw if str(v).strip()}
        if not allowed:
            return []
        return [
            definition
            for definition in self.get_tool_definitions()
            if definition.name in allowed
        ]

    def get_definition(self, tool_name: str) -> ToolDefinition | None:
        for definition in self.get_tool_definitions():
            if definition.name == tool_name:
                return definition
        return None
