from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable
from queue import Empty, Full, Queue
from threading import Event, Lock, Thread
from typing import Any

from huddle_chat.events import AppEvent

logger = logging.getLogger(__name__)


class EventBus:
    def __init__(self, maxsize: int = 512, publish_timeout_seconds: float = 0.1):
        self._queue: Queue[AppEvent] = Queue(maxsize=maxsize)
        self._publish_timeout_seconds = publish_timeout_seconds
        self._handlers: dict[type[AppEvent], list[Callable[[Any], None]]] = defaultdict(
            list
        )
        self._running = Event()
        self._worker: Thread | None = None
        self._lock = Lock()

        self.published_count = 0
        self.dropped_count = 0
        self.handler_error_count = 0

    def subscribe(
        self, event_type: type[AppEvent], handler: Callable[[Any], None]
    ) -> None:
        with self._lock:
            self._handlers[event_type].append(handler)

    def publish(self, event: AppEvent) -> bool:
        try:
            self._queue.put(event, timeout=self._publish_timeout_seconds)
            self.published_count += 1
            return True
        except Full:
            self.dropped_count += 1
            logger.warning(
                "Event queue full; dropped topic=%s source=%s",
                event.topic,
                event.source,
            )
            return False

    def start(self) -> None:
        if self._running.is_set():
            return
        self._running.set()
        self._worker = Thread(target=self._run, daemon=True)
        self._worker.start()

    def stop(self, timeout_seconds: float = 2.0) -> None:
        self._running.clear()
        worker = self._worker
        if worker is None:
            return
        worker.join(timeout=timeout_seconds)
        self._worker = None

    def _run(self) -> None:
        while self._running.is_set() or not self._queue.empty():
            try:
                event = self._queue.get(timeout=0.1)
            except Empty:
                continue
            self._dispatch(event)

    def _dispatch(self, event: AppEvent) -> None:
        with self._lock:
            snapshot = list(self._handlers.items())
        for event_type, handlers in snapshot:
            if not isinstance(event, event_type):
                continue
            for handler in handlers:
                try:
                    handler(event)
                except Exception:
                    self.handler_error_count += 1
                    logger.exception(
                        "Event handler failed topic=%s source=%s",
                        event.topic,
                        event.source,
                    )
