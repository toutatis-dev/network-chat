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


JsonDict = dict[str, Any]
