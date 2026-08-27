"""Request-level observability for J.A.R.V.I.S. turns.

The tool audit answers *what operation was attempted*.  This module answers
*what happened during one assistant turn*: intent, context sources, tools,
model latency and token usage.  It deliberately does **not** persist raw user
text by default.  The refactor specification asks for request tracing while
also forbidding secrets and sensitive personal data in logs; privacy-by-
default is the only safe way to satisfy both requirements.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..maintenance.logs import rotate_if_needed


_SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"(?i)(api[_ -]?key|token|password|parola|secret)\s*[:=]\s*([^\s,;]+)"),
    re.compile(r"(?i)Bearer\s+[A-Za-z0-9._~+/-]{8,}"),
    # credentials embedded in URLs: https://user:pass@example.com
    re.compile(r"(?i)(https?://[^\s/:]+:)[^@\s/]+(@)"),
)


def redact_log_value(value: Any) -> Any:
    """Recursively remove obvious credentials before anything reaches disk."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, val in value.items():
            folded = str(key).lower().replace("-", "_")
            if any(s in folded for s in ("password", "parola", "api_key", "apikey", "token", "secret")):
                out[str(key)] = "[SECRET]"
            else:
                out[str(key)] = redact_log_value(val)
        return out
    if isinstance(value, (list, tuple)):
        return [redact_log_value(v) for v in value]
    if not isinstance(value, str):
        return value

    text = value
    text = _SECRET_PATTERNS[0].sub("[SECRET]", text)
    text = _SECRET_PATTERNS[1].sub(lambda m: f"{m.group(1)}=[SECRET]", text)
    text = _SECRET_PATTERNS[2].sub("Bearer [SECRET]", text)
    text = _SECRET_PATTERNS[3].sub(r"\1[SECRET]\2", text)
    return text


@dataclass
class RequestTrace:
    request_id: str
    timestamp: float
    user_message: str
    user_message_sha256: str
    detected_intent: str
    confidence: float
    memory_used: bool = False
    rag_used: bool = False
    tools_used: list[str] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    model: str = ""
    active_model: str = ""
    fallback_used: bool = False
    retry_count: int = 0
    reasoning_level: int = 1
    thinking_enabled: bool = False
    latency_ms: float = 0.0
    token_usage: dict[str, Any] = field(default_factory=dict)
    response_status: str = "started"
    error_type: str = ""
    error: str = ""

    def safe_dict(self) -> dict[str, Any]:
        return redact_log_value(asdict(self))

    def to_json(self) -> str:
        return json.dumps(self.safe_dict(), ensure_ascii=False, sort_keys=True)


class RequestTraceLog:
    """Append-only JSONL trace log; logging failures never break a turn."""

    def __init__(self, path: Path | None = None, *, include_user_text: bool = False,
                 max_bytes: int = 10 * 1024 * 1024, backup_count: int = 5) -> None:
        self.path = path
        self.include_user_text = bool(include_user_text)
        self.max_bytes = max(0, int(max_bytes))
        self.backup_count = max(0, int(backup_count))
        self.entries: list[RequestTrace] = []
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def message_fingerprint(text: str) -> str:
        return hashlib.sha256((text or "").encode("utf-8", errors="replace")).hexdigest()

    def start(self, *, request_id: str, user_text: str, intent: str,
              confidence: float, model: str, reasoning_level: int = 1,
              thinking_enabled: bool = False) -> tuple[RequestTrace, float]:
        sanitized = redact_log_value(user_text or "")
        visible = sanitized if self.include_user_text else "[privacy-redacted]"
        trace = RequestTrace(
            request_id=request_id,
            timestamp=time.time(),
            user_message=visible,
            user_message_sha256=self.message_fingerprint(user_text),
            detected_intent=intent,
            confidence=round(float(confidence), 4),
            model=model,
            active_model=model,
            reasoning_level=max(0, min(5, int(reasoning_level))),
            thinking_enabled=bool(thinking_enabled),
        )
        return trace, time.perf_counter()

    def finish(self, trace: RequestTrace, started_at: float, *, status: str,
               error: str = "", error_type: str = "",
               token_usage: dict[str, Any] | None = None) -> RequestTrace:
        trace.latency_ms = round((time.perf_counter() - started_at) * 1000, 2)
        trace.response_status = status
        trace.error_type = str(error_type or "")
        trace.error = str(redact_log_value(error or ""))
        trace.token_usage = redact_log_value(token_usage or {})
        # Preserve insertion order but remove duplicates.
        trace.tools_used = list(dict.fromkeys(trace.tools_used))
        trace.rag_used = trace.rag_used or any(
            name in {"bilgi_ara", "bilgi_durum"} for name in trace.tools_used
        )
        trace.memory_used = trace.memory_used or any(
            name in {"remember_fact", "recall_facts", "forget_fact"} for name in trace.tools_used
        )
        self.record(trace)
        return trace

    def record(self, trace: RequestTrace) -> RequestTrace:
        self.entries.append(trace)
        if self.path is not None:
            try:
                line = trace.to_json() + "\n"
                rotate_if_needed(self.path, len(line.encode("utf-8")),
                                 max_bytes=self.max_bytes,
                                 backup_count=self.backup_count)
                with self.path.open("a", encoding="utf-8") as fh:
                    fh.write(line)
            except OSError:
                pass
        return trace
