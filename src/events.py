"""Thread-safe Event Bus and SSE streaming broker with ring buffer and replay support."""

import asyncio
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import logging
import threading
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Event:
    """Canonical event structure streamed via SSE."""
    type: str  # 'token' | 'thinking' | 'stage' | 'agent_start' | 'agent_end' | 'log'
    agent: str
    run_id: str
    seq: int
    text: str
    ts: str
    data: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if d["data"] is None:
            del d["data"]
        return d

    def to_sse_message(self) -> str:
        payload = json.dumps(self.to_dict(), ensure_ascii=False)
        return f"id: {self.seq}\nevent: {self.type}\ndata: {payload}\n\n"


class EventBus:
    """Thread-safe event bus with ring buffer, replay (Last-Event-ID), and asyncio SSE subscribers."""

    def __init__(self, max_history: int = 2000) -> None:
        self.max_history = max_history
        self._history: deque[Event] = deque(maxlen=max_history)
        self._subscribers: List[asyncio.Queue] = []
        self._lock = threading.Lock()
        self._seq = 0
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self._cancel_flag = threading.Event()
        self._active_run_id: Optional[str] = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Register the running asyncio event loop for thread-safe cross-thread dispatch."""
        self.loop = loop

    def request_cancellation(self) -> None:
        """Cooperatively request cancellation of the active run."""
        self._cancel_flag.set()

    def reset_cancellation(self, run_id: Optional[str] = None) -> None:
        """Reset the cancellation flag for a new run."""
        self._cancel_flag.clear()
        self._active_run_id = run_id

    def is_cancelled(self) -> bool:
        """Check if cancellation has been requested."""
        return self._cancel_flag.is_set()

    def get_active_run_id(self) -> Optional[str]:
        return self._active_run_id

    def publish(
        self,
        event_type: str,
        text: str = "",
        agent: str = "",
        run_id: str = "",
        data: Optional[Dict[str, Any]] = None
    ) -> Event:
        """Publish a new event to ring buffer and broadcast immediately to all SSE subscribers."""
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        with self._lock:
            self._seq += 1
            event = Event(
                type=event_type,
                agent=agent or "",
                run_id=run_id or self._active_run_id or "",
                seq=self._seq,
                text=text or "",
                ts=ts,
                data=data
            )
            self._history.append(event)
            subs = list(self._subscribers)

        if self.loop and self.loop.is_running():
            for q in subs:
                try:
                    self.loop.call_soon_threadsafe(q.put_nowait, event)
                except Exception:
                    pass

        return event

    def subscribe(self, last_event_id: Optional[int] = None) -> asyncio.Queue:
        """Create an asyncio subscriber queue, replaying missed events if last_event_id is provided."""
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)

        with self._lock:
            if last_event_id is not None and last_event_id > 0:
                # Replay all events strictly newer than last_event_id
                for ev in self._history:
                    if ev.seq > last_event_id:
                        try:
                            q.put_nowait(ev)
                        except Exception:
                            pass
            self._subscribers.append(q)

        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        """Unsubscribe and clean up an SSE client queue."""
        with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def get_history(self, limit: int = 100) -> List[Event]:
        """Return the latest N events from the ring buffer."""
        with self._lock:
            return list(self._history)[-limit:]


# Global EventBus singleton
event_bus = EventBus(max_history=2000)


class EventBusLogHandler(logging.Handler):
    """Logging handler that pipes log records into the event bus as type='log'."""

    def __init__(self, bus: EventBus) -> None:
        super().__init__()
        self.bus = bus

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self.bus.publish(
                event_type="log",
                text=msg,
                agent=record.name,
                data={
                    "level": record.levelname,
                    "logger": record.name,
                }
            )
        except Exception:
            self.handleError(record)
