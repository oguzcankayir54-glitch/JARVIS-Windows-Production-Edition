"""Deterministic mock LLM — lets the agent loop run and be tested without a
live model (no Ollama, no network).

It uses tiny keyword heuristics to decide whether to call a telemetry tool,
then produces a plain-language Turkish answer from the tool result. This is a
stand-in for a real model's tool-calling, not an attempt at intelligence.
"""
from __future__ import annotations

from typing import Any

from .base import LLMResponse, Message, ToolCall


class MockProvider:
    name = "mock"

    #: keyword → tool name
    _INTENTS = {
        "cpu": "get_cpu_temperature",
        "işlemci": "get_cpu_temperature",
        "sıcaklık": "get_cpu_temperature",
        "gpu": "get_gpu_temperature",
        "ekran kart": "get_gpu_temperature",
        "ram": "get_ram_usage",
        "bellek": "get_ram_usage",
        "disk": "get_disk_health",
        "smart": "get_disk_health",
        "sistem": "get_system_info",
        "durum": "get_system_info",
    }

    def chat(self, messages: list[Message], tools: list[dict[str, Any]] | None = None) -> LLMResponse:
        # Only consider messages from the CURRENT turn (after the last user msg).
        last_user_idx = max(
            (i for i, m in enumerate(messages) if m.role == "user"), default=-1
        )
        turn = messages[last_user_idx:] if last_user_idx >= 0 else messages
        turn_tool_msgs = [m for m in turn if m.role == "tool"]

        # If a tool has already produced output this turn, summarise it.
        if turn_tool_msgs:
            latest = turn_tool_msgs[-1]
            return LLMResponse(content=f"[{latest.name}] sonucu: {latest.content}")

        last_user = messages[last_user_idx] if last_user_idx >= 0 else None
        raw = last_user.content if last_user else ""
        text = raw.lower()

        # Argument-taking intents, checked before the simple keyword map.
        call = self._parse_arg_intent(raw, text)
        if call is not None:
            return LLMResponse(tool_calls=[call])

        for keyword, tool_name in self._INTENTS.items():
            if keyword in text:
                return LLMResponse(tool_calls=[ToolCall(name=tool_name, arguments={})])

        return LLMResponse(content=(
            "Merhaba, ben J.A.R.V.I.S. Şu an mock modeldeyim. "
            "CPU/GPU sıcaklığı, RAM, disk veya sistem durumu sorabilirsiniz."
        ))

    @staticmethod
    def _parse_arg_intent(raw: str, text: str) -> ToolCall | None:
        """Recognise the few phrasings that carry an argument.

        Deliberately literal: this stands in for a model's tool-calling, so it
        only needs to be predictable enough to drive the loop in tests and the
        terminal demo.
        """
        if text.startswith("çalıştır:") or text.startswith("calistir:"):
            command = raw.split(":", 1)[1].strip()
            return ToolCall(name="run_terminal_command", arguments={"command": command})

        if text.startswith("oku:"):
            return ToolCall(name="read_file", arguments={"path": raw.split(":", 1)[1].strip()})

        if text.startswith("listele:"):
            return ToolCall(name="list_directory", arguments={"path": raw.split(":", 1)[1].strip()})

        # "hatırla: anahtar = değer"
        if text.startswith("hatırla:") or text.startswith("hatirla:"):
            body = raw.split(":", 1)[1]
            key, sep, value = body.partition("=")
            if sep:
                return ToolCall(
                    name="remember_fact",
                    arguments={"key": key.strip(), "value": value.strip(), "category": "kullanici"},
                )

        if "ne biliyorsun" in text or text.startswith("hatırlıyor musun") or "hafızanda" in text:
            return ToolCall(name="recall_facts", arguments={})

        return None
