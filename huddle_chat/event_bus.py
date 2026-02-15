from __future__ import annotations

import logging
from dataclasses import dataclass
from collections import defaultdict
from collections.abc import Callable
from queue import Empty, Full, Queue
from threading import Event, Lock, Thread
from typing import Any

from huddle_chat.events import AppEvent

logger = logging.getLogger(__name__)


@dataclass
class EventBusMetrics:
    published: int = 0
    delivered: int = 0
    retried: int = 0
    dropped: int = 0
    handler_failures: int = 0
    queue_full: int = 0
    fallback_executed: int = 0


class EventBus:
    def __init__(
        self,
        maxsize: int = 512,
        publish_timeout_seconds: float = 0.1,
        critical_publish_retries: int = 2,
        critical_handler_retries: int = 1,
    ):
        self._queue: Queue[AppEvent] = Queue(maxsize=maxsize)
        self._publish_timeout_seconds = publish_timeout_seconds
        self._critical_publish_retries = max(0, critical_publish_retries)
        self._critical_handler_retries = max(0, critical_handler_retries)
        self._handlers: dict[type[AppEvent], list[Callable[[Any], None]]] = defaultdict(
            list
        )
        self._running = Event()
        self._worker: Thread | None = None
        self._lock = Lock()

        self.metrics = EventBusMetrics()

    def subscribe(
        self, event_type: type[AppEvent], handler: Callable[[Any], None]
    ) -> None:
        with self._lock:
            self._handlers[event_type].append(handler)

    def publish(self, event: AppEvent, *, critical: bool = False) -> bool:
        event.critical = event.critical or critical
        max_attempts = 1 + (self._critical_publish_retries if event.critical else 0)
        for attempt in range(max_attempts):
            try:
                self._queue.put(event, timeout=self._publish_timeout_seconds)
                self.metrics.published += 1
                return True
            except Full:
                self.metrics.queue_full += 1
                if attempt + 1 < max_attempts:
                    self.metrics.retried += 1
                    continue
                self.metrics.dropped += 1
                logger.warning(
                    "Event queue full; dropped topic=%s source=%s critical=%s",
                    event.topic,
                    event.source,
                    event.critical,
                )
                return False
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
                self._dispatch_to_handler(event, handler)

    def _dispatch_to_handler(
        self, event: AppEvent, handler: Callable[[Any], None]
    ) -> None:
        max_attempts = 1 + (self._critical_handler_retries if event.critical else 0)
        for attempt in range(max_attempts):
            try:
                handler(event)
                self.metrics.delivered += 1
                return
            except Exception:
                self.metrics.handler_failures += 1
                if attempt + 1 < max_attempts:
                    event.retry_count += 1
                    self.metrics.retried += 1
                    continue
                logger.exception(
                    "Event handler failed topic=%s source=%s critical=%s retries=%s",
                    event.topic,
                    event.source,
                    event.critical,
                    event.retry_count,
                )

    def increment_fallback_executed(self) -> None:
        self.metrics.fallback_executed += 1

    def snapshot_metrics(self) -> EventBusMetrics:
        return EventBusMetrics(
            published=self.metrics.published,
            delivered=self.metrics.delivered,
            retried=self.metrics.retried,
            dropped=self.metrics.dropped,
            handler_failures=self.metrics.handler_failures,
            queue_full=self.metrics.queue_full,
            fallback_executed=self.metrics.fallback_executed,
        )
