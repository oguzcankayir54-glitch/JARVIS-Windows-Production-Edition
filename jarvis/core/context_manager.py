"""Central context budgeting for J.A.R.V.I.S. 2.0 (Phase 3).

This component owns *how much* context reaches the LLM and how dynamic system
blocks are replaced.  Retrieval policy (which memories/RAG chunks are
relevant) is intentionally left to later phases.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..llm.base import Message


@dataclass
class ContextManager:
    history_max_messages: int = 24
    max_chars: int = 18000
    tool_result_max_chars: int = 12000

    def replace_system_block(self, history: list[Message], prefix: str,
                             message: Message | None,
                             *, after_base: bool = True) -> list[Message]:
        """Keep at most one dynamic block with ``prefix``.

        The first system message is the immutable persona.  Dynamic blocks are
        inserted after it so they can be refreshed without ever replacing the
        base identity.
        """
        cleaned = [m for m in history if not (
            m.role == "system" and m.content.startswith(prefix)
        )]
        if message is None:
            return cleaned
        if after_base and cleaned:
            cleaned.insert(1, message)
        else:
            cleaned.append(message)
        return cleaned

    def prune(self, history: list[Message]) -> list[Message]:
        """Preserve system instructions and the newest complete conversation.

        Two independent limits are applied:
        * message count prevents unbounded session growth;
        * character budget prevents a few very large turns from overflowing
          the model context even when the message count is small.
        """
        systems = [m for m in history if m.role == "system"]
        conversation = [m for m in history if m.role != "system"]

        count_limit = max(0, int(self.history_max_messages or 0))
        if count_limit and len(conversation) > count_limit:
            conversation = conversation[-count_limit:]
            # Do not begin with an orphan tool/assistant message when a user
            # message still exists in the retained window.
            if any(m.role == "user" for m in conversation):
                while conversation and conversation[0].role != "user":
                    conversation.pop(0)

        char_limit = max(0, int(self.max_chars or 0))
        if char_limit:
            system_chars = sum(len(m.content or "") for m in systems)
            budget = max(0, char_limit - system_chars)
            while conversation and sum(len(m.content or "") for m in conversation) > budget:
                conversation.pop(0)
                if any(m.role == "user" for m in conversation):
                    while conversation and conversation[0].role != "user":
                        conversation.pop(0)

        return systems + conversation

    def truncate_tool_result(self, text: str) -> str:
        limit = max(0, int(self.tool_result_max_chars or 0))
        if limit <= 0 or len(text) <= limit:
            return text
        head = max(1, int(limit * 0.72))
        tail = max(1, limit - head)
        skipped = len(text) - head - tail
        return (
            text[:head]
            + f"\n\n[... {skipped} karakterlik orta bölüm bağlamı korumak için kısaltıldı ...]\n\n"
            + text[-tail:]
        )
