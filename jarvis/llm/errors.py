"""Typed provider failures used by retry, fallback and observability policy."""
from __future__ import annotations

from enum import Enum


class ErrorType(str, Enum):
    TIMEOUT = "TIMEOUT"
    SERVER_UNAVAILABLE = "SERVER_UNAVAILABLE"
    MODEL_MISSING = "MODEL_MISSING"
    MODEL_OOM = "MODEL_OOM"
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    PROVIDER_FAILURE = "PROVIDER_FAILURE"


class LLMProviderError(RuntimeError):
    def __init__(self, message: str, *, kind: ErrorType,
                 retryable: bool = False, fallback_allowed: bool = False,
                 server_available: bool | None = None) -> None:
        super().__init__(message)
        self.kind = kind
        self.retryable = bool(retryable)
        self.fallback_allowed = bool(fallback_allowed)
        self.server_available = server_available
