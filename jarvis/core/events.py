"""Small in-process event bus for decoupled J.A.R.V.I.S. modules.

Delivery is synchronous and best-effort. Subscribers must return quickly;
slow/background work owns its own queue. This keeps the core dependency-free
and avoids pretending one local process needs distributed messaging.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Event:
    name: str
    payload: dict[str, Any] = field(default_factory=dict)
    source: str = "core"
    timestamp: float = field(default_factory=time.time)
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.event_id,
            "name": self.name,
            "source": self.source,
            "timestamp": self.timestamp,
            "payload": dict(self.payload),
        }


EventListener = Callable[[Event], None]


class EventBus:
    """Thread-safe exact/prefix/wildcard publish-subscribe bus."""

    def __init__(self, history_size: int = 100) -> None:
        self._subscriptions: dict[str, list[EventListener]] = {}
        self._history: deque[Event] = deque(maxlen=max(0, int(history_size)))
        self._lock = threading.RLock()

    @staticmethod
    def _valid_name(name: str) -> str:
        cleaned = (name or "").strip()
        if not cleaned or "." not in cleaned or any(ch.isspace() for ch in cleaned):
            raise ValueError("event name must use a dotted form such as 'jarvis.ready'")
        return cleaned

    def subscribe(self, pattern: str, listener: EventListener) -> Callable[[], None]:
        """Subscribe to `name`, `prefix.*`, or all dotted events with `*`."""
        pattern = (pattern or "").strip()
        if pattern != "*" and not pattern.endswith(".*"):
            self._valid_name(pattern)
        elif pattern != "*" and len(pattern) <= 2:
            raise ValueError("event prefix cannot be empty")
        with self._lock:
            listeners = self._subscriptions.setdefault(pattern, [])
            if listener not in listeners:
                listeners.append(listener)

        def unsubscribe() -> None:
            with self._lock:
                listeners = self._subscriptions.get(pattern)
                if listeners and listener in listeners:
                    listeners.remove(listener)
                if listeners == []:
                    self._subscriptions.pop(pattern, None)

        return unsubscribe

    def publish(self, name: str, payload: dict[str, Any] | None = None, *,
                source: str = "core") -> Event:
        event = Event(self._valid_name(name), dict(payload or {}), source=source)
        with self._lock:
            if self._history.maxlen:
                self._history.append(event)
            listeners: list[EventListener] = []
            for pattern, callbacks in self._subscriptions.items():
                if (pattern == "*" or pattern == event.name
                        or (pattern.endswith(".*")
                            and event.name.startswith(pattern[:-1]))):
                    listeners.extend(callbacks)
        # A callback registered through overlapping patterns is invoked once.
        for listener in dict.fromkeys(listeners):
            try:
                listener(event)
            except Exception:
                logger.exception("event listener failed: %s", event.name)
        return event

    def recent(self, pattern: str = "*", limit: int = 20) -> tuple[Event, ...]:
        """Return bounded diagnostic history; it is not a durable event log."""
        with self._lock:
            events = tuple(self._history)
        if pattern != "*":
            events = tuple(e for e in events if (
                e.name == pattern
                or (pattern.endswith(".*") and e.name.startswith(pattern[:-1]))
            ))
        return events[-max(0, int(limit)):]
