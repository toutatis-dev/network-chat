from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class AppEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: uuid4().hex)
    ts: str = Field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds")
    )
    topic: str
    source: str
    correlation_id: str | None = None
    critical: bool = False
    retry_count: int = 0


class SystemMessageEvent(AppEvent):
    topic: Literal["system_message"] = "system_message"
    text: str


class RefreshOutputEvent(AppEvent):
    topic: Literal["refresh_output"] = "refresh_output"


class RebuildSearchEvent(AppEvent):
    topic: Literal["rebuild_search"] = "rebuild_search"


class RunCommandEvent(AppEvent):
    topic: Literal["run_command"] = "run_command"
    command_text: str
