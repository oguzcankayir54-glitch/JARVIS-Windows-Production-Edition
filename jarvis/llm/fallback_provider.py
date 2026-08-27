"""Controlled primary/fallback routing with a small circuit breaker."""
from __future__ import annotations

import time
from typing import Any

from .base import LLMProvider, LLMResponse, Message
from .errors import ErrorType, LLMProviderError


class FallbackProvider:
    name = "ollama-fallback"

    def __init__(self, primary: LLMProvider, fallback: LLMProvider, *,
                 max_retries: int = 1, circuit_cooldown: float = 30.0,
                 same_server: bool = True) -> None:
        self.primary = primary
        self.fallback = fallback
        self.max_retries = max(0, int(max_retries))
        self.circuit_cooldown = max(1.0, float(circuit_cooldown))
        self.same_server = bool(same_server)
        self._circuit_opened_at: float | None = None
        self.active_model = str(getattr(primary, "model", primary.name))
        self.fallback_used = False
        self.retry_count = 0
        self.son_kullanim: dict[str, Any] = {}

    @property
    def model(self) -> str:
        return self.active_model

    @property
    def think(self) -> bool:
        provider = self.fallback if self.fallback_used else self.primary
        return bool(getattr(provider, "think", False))

    @property
    def circuit_open(self) -> bool:
        if self._circuit_opened_at is None:
            return False
        if time.monotonic() - self._circuit_opened_at >= self.circuit_cooldown:
            self._circuit_opened_at = None
            return False
        return True

    def _usage_from(self, provider: LLMProvider) -> None:
        usage = getattr(provider, "son_kullanim", None)
        self.son_kullanim = dict(usage) if isinstance(usage, dict) else {}

    def apply_reasoning(self, level: int) -> None:
        for provider in (self.primary, self.fallback):
            apply = getattr(provider, "apply_reasoning", None)
            if apply is not None:
                apply(level)

    def chat(self, messages: list[Message],
             tools: list[dict[str, Any]] | None = None) -> LLMResponse:
        self.fallback_used = False
        self.retry_count = 0
        self.active_model = str(getattr(self.primary, "model", self.primary.name))
        if self.circuit_open:
            raise LLMProviderError(
                "Ollama bağlantısı geçici olarak devre dışı; yeniden deneme süresi bekleniyor.",
                kind=ErrorType.SERVER_UNAVAILABLE, retryable=False,
                fallback_allowed=False, server_available=False,
            )

        last_error: LLMProviderError | None = None
        for attempt in range(self.max_retries + 1):
            try:
                result = self.primary.chat(messages, tools=tools)
                self.retry_count = attempt
                self._usage_from(self.primary)
                return result
            except LLMProviderError as exc:
                last_error = exc
                if exc.server_available is False:
                    self._circuit_opened_at = time.monotonic()
                    raise
                if not exc.retryable or attempt >= self.max_retries:
                    break

        assert last_error is not None
        self.retry_count = self.max_retries if last_error.retryable else 0
        if not last_error.fallback_allowed:
            raise last_error
        if self.same_server and last_error.server_available is False:
            raise last_error

        self.fallback_used = True
        self.active_model = str(getattr(self.fallback, "model", self.fallback.name))
        result = self.fallback.chat(messages, tools=tools)
        self._usage_from(self.fallback)
        return result
