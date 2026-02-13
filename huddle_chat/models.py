from typing import Any, TypedDict


class ChatEvent(TypedDict, total=False):
    v: int
    ts: str
    type: str
    author: str
    text: str
    provider: str
    model: str
    request_id: str
    memory_ids_used: list[str]
    memory_topics_used: list[str]


class MemoryEntry(TypedDict, total=False):
    id: str
    ts: str
    author: str
    summary: str
    topic: str
    confidence: str
    source: str
    room: str
    origin_event_ref: str
    tags: list[str]


class AIProviderConfig(TypedDict):
    provider: str
    api_key: str
    model: str


class ParsedAIArgs(TypedDict, total=False):
    provider_override: str | None
    model_override: str | None
    is_private: bool
    disable_memory: bool
    prompt: str
    memory_scope_override: list[str]


class ToolPolicy(TypedDict, total=False):
    mode: str
    require_approval: bool
    allowed_tools: list[str]


class MemoryPolicy(TypedDict, total=False):
    scopes: list[str]


class RoutingPolicy(TypedDict, total=False):
    routes: dict[str, dict[str, str]]


class AgentProfile(TypedDict, total=False):
    id: str
    name: str
    description: str
    system_prompt: str
    tool_policy: ToolPolicy
    memory_policy: MemoryPolicy
    routing_policy: RoutingPolicy
    created_by: str
    updated_by: str
    updated_at: str
    version: int


class ResolvedRoute(TypedDict):
    provider: str
    model: str
    api_key: str
    reason: str


class ToolActionRequest(TypedDict):
    action_id: str
    ts: str
    user: str
    agent_profile: str
    tool: str
    summary: str
    command_preview: str
    risk_level: str
    status: str


class ToolActionDecision(TypedDict):
    action_id: str
    ts: str
    user: str
    decision: str


class ToolActionResult(TypedDict):
    action_id: str
    ts: str
    result: str
    output_preview: str


JsonDict = dict[str, Any]
