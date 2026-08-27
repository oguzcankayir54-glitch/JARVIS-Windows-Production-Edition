"""Central state machine — the single source of truth for J.A.R.V.I.S. status.

The states mirror the Neural Core panel (spec §3): the UI subscribes to this
machine so the visual state and the backend state never disagree (spec §30).
For V1 (terminal) there is no UI yet, but the agent already drives the machine
so wiring the panel later is only a transport concern.
"""
from __future__ import annotations

import enum
from typing import Callable


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


class StateMachine:
    def __init__(self, initial: JarvisState = JarvisState.STANDBY) -> None:
        self._state = initial
        self._listeners: list[Listener] = []

    @property
    def state(self) -> JarvisState:
        return self._state

    def subscribe(self, listener: Listener) -> None:
        """Register a callback fired on every transition (e.g. the UI)."""
        self._listeners.append(listener)

    def transition(self, new: JarvisState) -> JarvisState:
        old, self._state = self._state, new
        if old is not new:
            for listener in list(self._listeners):
                listener(old, new)
        return new
