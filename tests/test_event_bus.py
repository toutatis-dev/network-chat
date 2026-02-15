import time
from threading import Event

from huddle_chat.event_bus import EventBus
from huddle_chat.events import SystemMessageEvent


def test_critical_event_retries_handler_and_delivers() -> None:
    bus = EventBus(critical_handler_retries=1)
    done = Event()
    calls = {"count": 0}

    def flaky_handler(event: SystemMessageEvent) -> None:
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("transient failure")
        assert event.text == "hello"
        done.set()

    bus.subscribe(SystemMessageEvent, flaky_handler)
    bus.start()
    try:
        ok = bus.publish(
            SystemMessageEvent(source="test", text="hello", critical=True),
            critical=True,
        )
        assert ok is True
        assert done.wait(timeout=1.0)
    finally:
        bus.stop()

    metrics = bus.snapshot_metrics()
    assert calls["count"] == 2
    assert metrics.retried >= 1
    assert metrics.delivered >= 1
    assert metrics.handler_failures >= 1


def test_non_critical_handler_failure_does_not_retry() -> None:
    bus = EventBus(critical_handler_retries=1)
    done = Event()
    calls = {"count": 0}

    def always_fails(_event: SystemMessageEvent) -> None:
        calls["count"] += 1
        done.set()
        raise RuntimeError("fail")

    bus.subscribe(SystemMessageEvent, always_fails)
    bus.start()
    try:
        ok = bus.publish(SystemMessageEvent(source="test", text="hello"))
        assert ok is True
        assert done.wait(timeout=1.0)
        time.sleep(0.05)
    finally:
        bus.stop()

    metrics = bus.snapshot_metrics()
    assert calls["count"] == 1
    assert metrics.handler_failures >= 1


def test_critical_publish_retries_when_queue_is_full() -> None:
    bus = EventBus(maxsize=1, publish_timeout_seconds=0.01, critical_publish_retries=2)
    first = SystemMessageEvent(source="test", text="first")
    second = SystemMessageEvent(source="test", text="second", critical=True)

    assert bus.publish(first) is True
    assert bus.publish(second, critical=True) is False

    metrics = bus.snapshot_metrics()
    assert metrics.queue_full >= 1
    assert metrics.dropped == 1
