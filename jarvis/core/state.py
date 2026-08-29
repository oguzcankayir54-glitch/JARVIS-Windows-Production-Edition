"""Central state machine — the single source of truth for J.A.R.V.I.S. status.

The states mirror the Neural Core panel (spec §3): the UI subscribes to this
machine so the visual state and the backend state never disagree (spec §30).
For V1 (terminal) there is no UI yet, but the agent already drives the machine
so wiring the panel later is only a transport concern.
"""
from __future__ import annotations

import enum
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable


class JarvisState(enum.Enum):
    STANDBY = "standby"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    SEEING = "seeing"
    ANALYZING = "analyzing"
    DIAGNOSING = "diagnosing"
    WARNING = "warning"
    CRITICAL = "critical"
    OFFLINE = "offline"

    @property
    def label_tr(self) -> str:
        return {
            "standby": "HAZIR",
            "listening": "DİNLİYOR",
            "thinking": "DÜŞÜNÜYOR",
            "speaking": "KONUŞUYOR",
            "seeing": "GÖRÜYOR",
            "analyzing": "ANALİZ EDİYOR",
            "diagnosing": "TEŞHİS EDİYOR",
            "warning": "UYARI",
            "critical": "KRİTİK",
            "offline": "OFFLINE",
        }[self.value]


Listener = Callable[[JarvisState, JarvisState], None]

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StateSnapshot:
    """Immutable, serialisable view of the current core state."""

    state: JarvisState
    previous: JarvisState
    revision: int
    changed_at: float
    reason: str = ""
    details: dict[str, Any] = field(default_factory=dict)


class StateMachine:
    def __init__(self, initial: JarvisState = JarvisState.STANDBY) -> None:
        self._state = initial
        self._previous = initial
        self._revision = 0
        self._changed_at = time.time()
        self._reason = "startup"
        self._details: dict[str, Any] = {}
        self._listeners: list[Listener] = []
        self._lock = threading.RLock()

    @property
    def state(self) -> JarvisState:
        with self._lock:
            return self._state

    def snapshot(self) -> StateSnapshot:
        """Return one consistent state view for CLI, GUI and future modules."""
        with self._lock:
            return StateSnapshot(
                state=self._state,
                previous=self._previous,
                revision=self._revision,
                changed_at=self._changed_at,
                reason=self._reason,
                details=dict(self._details),
            )

    def subscribe(self, listener: Listener) -> Callable[[], None]:
        """Register a listener and return an idempotent unsubscribe callback."""
        with self._lock:
            if listener not in self._listeners:
                self._listeners.append(listener)

        def unsubscribe() -> None:
            with self._lock:
                if listener in self._listeners:
                    self._listeners.remove(listener)

        return unsubscribe

    def transition(self, new: JarvisState, *, reason: str = "",
                   details: dict[str, Any] | None = None) -> JarvisState:
        """Atomically transition; observers cannot break the state owner."""
        if not isinstance(new, JarvisState):
            raise TypeError("new must be a JarvisState")
        with self._lock:
            old = self._state
            if old is new:
                return new
            self._previous = old
            self._state = new
            self._revision += 1
            self._changed_at = time.time()
            self._reason = reason
            self._details = dict(details or {})
            listeners = tuple(self._listeners)
        for listener in listeners:
            try:
                listener(old, new)
            except Exception:
                logger.exception("state listener failed: %s -> %s", old.value, new.value)
        return new
