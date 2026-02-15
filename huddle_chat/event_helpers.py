from __future__ import annotations

import logging
from typing import Any

from huddle_chat.events import (
    RebuildSearchEvent,
    RefreshOutputEvent,
    RunCommandEvent,
    SystemMessageEvent,
)

logger = logging.getLogger(__name__)


def _mark_fallback(bus: Any) -> None:
    marker = getattr(bus, "increment_fallback_executed", None)
    if callable(marker):
        marker()


def _publish(app: Any, event: Any, *, critical: bool = False) -> bool:
    bus = getattr(app, "event_bus", None)
    if bus is None:
        return False
    try:
        return bool(bus.publish(event, critical=critical))
    except Exception:
        logger.exception(
            "Failed publishing event topic=%s", getattr(event, "topic", "unknown")
        )
        return False


def emit_system_message(app: Any, text: str, source: str = "service") -> None:
    if _publish(
        app,
        SystemMessageEvent(source=source, text=text, critical=True),
        critical=True,
    ):
        return
    bus = getattr(app, "event_bus", None)
    if bus is not None:
        _mark_fallback(bus)
    app.append_system_message(text)


def emit_refresh_output(app: Any, source: str = "service") -> None:
    if _publish(app, RefreshOutputEvent(source=source)):
        return
    bus = getattr(app, "event_bus", None)
    if bus is not None:
        _mark_fallback(bus)
    app.refresh_output_from_events()


def emit_rebuild_search(app: Any, source: str = "service") -> None:
    if _publish(app, RebuildSearchEvent(source=source)):
        return
    bus = getattr(app, "event_bus", None)
    if bus is not None:
        _mark_fallback(bus)
    app.rebuild_search_hits()


def emit_run_command(app: Any, command_text: str, source: str = "service") -> None:
    if _publish(
        app,
        RunCommandEvent(source=source, command_text=command_text, critical=True),
        critical=True,
    ):
        return
    bus = getattr(app, "event_bus", None)
    if bus is not None:
        _mark_fallback(bus)
    app.controller.handle_input(command_text)
