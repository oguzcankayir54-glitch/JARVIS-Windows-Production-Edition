"""Bounded, process-local working memory for one J.A.R.V.I.S. session.

This is deliberately separate from :mod:`jarvis.memory.store`: working memory
owns the active prompt/history, while SQLite owns durable conversation and
facts. Nothing in this module writes to disk or performs retrieval.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Iterable

from ..llm.base import Message


@dataclass(frozen=True)
class WorkingMemoryStats:
    messages: int
    system_messages: int
    conversation_messages: int
    characters: int


class WorkingMemory:
    """Thread-safe owner of the current session's transient messages."""

    def __init__(self, messages: Iterable[Message] = ()) -> None:
        self._messages = list(messages)
        self._lock = threading.RLock()

    @property
    def messages(self) -> list[Message]:
        """Compatibility view for the existing agent/context pipeline.

        Mutations remain owned by the Agent. External consumers should use
        :meth:`snapshot` so GUI and diagnostic readers cannot alter a turn.
        """
        return self._messages

    def replace(self, messages: Iterable[Message]) -> None:
        with self._lock:
            self._messages = list(messages)

    def append(self, message: Message) -> None:
        with self._lock:
            self._messages.append(message)

    def snapshot(self) -> tuple[Message, ...]:
        with self._lock:
            return tuple(self._messages)

    def stats(self) -> WorkingMemoryStats:
        with self._lock:
            systems = sum(m.role == "system" for m in self._messages)
            characters = sum(len(m.content or "") for m in self._messages)
            return WorkingMemoryStats(
                messages=len(self._messages),
                system_messages=systems,
                conversation_messages=len(self._messages) - systems,
                characters=characters,
            )

    def clear_conversation(self) -> None:
        """Forget only transient turns; preserve persona/dynamic system data."""
        with self._lock:
            self._messages = [m for m in self._messages if m.role == "system"]
