from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ChatEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: str = "chat"
    author: str = "Unknown"
    text: str = ""
    v: int = 1
    ts: str = Field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds")
    )
    provider: str | None = None
    model: str | None = None
    request_id: str | None = None
    memory_ids_used: list[str] = Field(default_factory=list)
    memory_topics_used: list[str] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChatEvent":
        return cls(**data)


class MemoryEntry(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    author: str = "Unknown"
    summary: str = ""
    topic: str = "general"
    confidence: str = "med"
    source: str = ""
    room: str = ""
    ts: str = Field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds")
    )
    origin_event_ref: str | None = None
    tags: list[str] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MemoryEntry":
        return cls(**data)


class AIProviderConfig(BaseModel):
    provider: str
    api_key: str
    model: str


class ParsedAIArgs(BaseModel):
    prompt: str
    provider_override: str | None = None
    model_override: str | None = None
    is_private: bool = False
    disable_memory: bool = False
    memory_scope_override: list[str] = Field(default_factory=list)
    action_mode: bool = False


class ToolPolicy(BaseModel):
    mode: str = "default"
    require_approval: bool = True
    allowed_tools: list[str] = Field(default_factory=list)


class MemoryPolicy(BaseModel):
    scopes: list[str] = Field(default_factory=list)


class RoutingPolicy(BaseModel):
    routes: dict[str, dict[str, str]] = Field(default_factory=dict)


class AgentProfile(BaseModel):
    id: str
    name: str
    description: str
    system_prompt: str
    tool_policy: ToolPolicy = Field(default_factory=ToolPolicy)
    memory_policy: MemoryPolicy = Field(default_factory=MemoryPolicy)
    routing_policy: RoutingPolicy = Field(default_factory=RoutingPolicy)
    created_by: str = "system"
    updated_by: str = "system"
    updated_at: str = Field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds")
    )
    version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class ResolvedRoute(BaseModel):
    provider: str
    model: str
    api_key: str
    reason: str


class ToolActionRequest(BaseModel):
    action_id: str
    ts: str
    user: str
    agent_profile: str
    tool: str
    summary: str
    command_preview: str
    risk_level: str
    status: str
    request_id: str
    room: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    ttl_seconds: int = 0
    expires_at: str = ""


class ToolActionDecision(BaseModel):
    action_id: str
    ts: str
    user: str
    decision: str


class ToolActionResult(BaseModel):
    action_id: str
    ts: str
    result: str
    output_preview: str
    exit_code: int | None = None
    duration_ms: int = 0


class ToolDefinition(BaseModel):
    name: str
    title: str
    description: str
    inputSchema: dict[str, Any] = Field(default_factory=dict)
    annotations: dict[str, Any] = Field(default_factory=dict)


class ToolCallRequest(BaseModel):
    toolName: str
    arguments: dict[str, Any]
    requestId: str
    actionId: str
    room: str
    user: str


class ToolCallResult(BaseModel):
    content: list[dict[str, Any]]
    isError: bool
    meta: dict[str, Any] = Field(default_factory=dict)


class PlaybookStep(BaseModel):
    id: str
    title: str
    kind: str
    command_template: str
    requires_input: bool = False
    placeholders: list[str] = Field(default_factory=list)
    expected_result: str = ""


class PlaybookDefinition(BaseModel):
    name: str
    summary: str
    steps: list[PlaybookStep] = Field(default_factory=list)


JsonDict = dict[str, Any]
