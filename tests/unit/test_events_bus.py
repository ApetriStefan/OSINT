"""Unit tests for the thread-safe EventBus and SSE streaming infrastructure."""

import asyncio
import logging
import pytest

from src.events import Event, EventBus, EventBusLogHandler


def test_event_creation_and_serialization():
    """Verify Event dataclass structure and SSE wire format."""
    ev = Event(
        type="token",
        agent="extractor",
        run_id="run_123",
        seq=1,
        text="Marcel",
        ts="2026-06-14T10:00:00Z",
        data={"step": 1}
    )
    sse_msg = ev.to_sse_message()
    assert "id: 1\n" in sse_msg
    assert "event: token\n" in sse_msg
    assert '"text": "Marcel"' in sse_msg
    assert '"agent": "extractor"' in sse_msg
    assert sse_msg.endswith("\n\n")


def test_event_bus_monotonic_sequence():
    """Verify sequence numbers strictly increase."""
    bus = EventBus(max_history=50)
    ev1 = bus.publish(event_type="stage", text="Stage 1")
    ev2 = bus.publish(event_type="token", text="Tok")
    ev3 = bus.publish(event_type="log", text="Log message")

    assert ev1.seq == 1
    assert ev2.seq == 2
    assert ev3.seq == 3


def test_event_bus_ring_buffer_eviction():
    """Verify ring buffer honors max_history."""
    bus = EventBus(max_history=5)
    for i in range(10):
        bus.publish(event_type="token", text=f"token_{i}")

    history = bus.get_history(limit=10)
    assert len(history) == 5
    assert history[0].text == "token_5"
    assert history[-1].text == "token_9"


def test_event_bus_subscribe_replay():
    """Verify Last-Event-ID replay functionality."""
    async def _test():
        bus = EventBus(max_history=50)
        bus.set_loop(asyncio.get_running_loop())

        # Emit 5 events before client subscribes
        for i in range(5):
            bus.publish(event_type="token", text=f"pre_{i}")

        # Client subscribes requesting replay of events after seq 3
        queue = bus.subscribe(last_event_id=3)
        assert queue.qsize() == 2

        ev4 = queue.get_nowait()
        assert ev4.seq == 4
        assert ev4.text == "pre_3"

        ev5 = queue.get_nowait()
        assert ev5.seq == 5
        assert ev5.text == "pre_4"

        # Emit event after subscription
        bus.publish(event_type="token", text="live_token")
        live_ev = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert live_ev.seq == 6
        assert live_ev.text == "live_token"

        bus.unsubscribe(queue)

    asyncio.run(_test())


def test_cooperative_cancellation_flag():
    """Verify cancellation flag signaling."""
    bus = EventBus()
    assert not bus.is_cancelled()

    bus.request_cancellation()
    assert bus.is_cancelled()

    bus.reset_cancellation(run_id="new_run")
    assert not bus.is_cancelled()
    assert bus.get_active_run_id() == "new_run"


def test_event_bus_log_handler():
    """Verify EventBusLogHandler publishes log records into event bus."""
    bus = EventBus()
    handler = EventBusLogHandler(bus)
    test_logger = logging.getLogger("test_logger_events")
    test_logger.addHandler(handler)
    test_logger.setLevel(logging.INFO)

    test_logger.info("Test log statement for event bus")

    history = bus.get_history()
    assert len(history) >= 1
    log_ev = history[-1]
    assert log_ev.type == "log"
    assert "Test log statement for event bus" in log_ev.text
    assert log_ev.agent == "test_logger_events"
