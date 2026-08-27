"""Provider-agnostic LLM interface.

The agent talks to this abstraction, not to any specific backend, so the
local Ollama model, a cloud model, or a deterministic mock are
interchangeable (spec §27 hybrid + §32 abstraction). A model router can later
choose the provider per request without touching the agent.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class Message:
    role: str            # system | user | assistant | tool
    content: str = ""
    name: str = ""       # tool name, when role == "tool"
    # Ollama tool-calling protocol requires the assistant request that led to
    # a tool result to be sent back on the next turn. Keeping the raw API shape
    # here avoids coupling Message to one provider-specific ToolCall class.
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponse:
    """Either free-text content, or one or more tool calls to execute."""
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)

    @property
    def wants_tool(self) -> bool:
        return bool(self.tool_calls)


class LLMProvider(Protocol):
    name: str

    def chat(self, messages: list[Message], tools: list[dict[str, Any]] | None = None) -> LLMResponse:
        ...
