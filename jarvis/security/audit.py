"""Append-only audit log for every tool invocation and permission decision.

Each entry is one JSON object per line (JSONL). The log is append-only by
convention: J.A.R.V.I.S. never rewrites or deletes prior entries, so the
trail of what was run — and what was approved or denied — stays intact.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..maintenance.logs import rotate_if_needed


_SECRET_KEYS = ("password", "parola", "api_key", "apikey", "token", "secret")
_SECRET_TEXT = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"(?i)(api[_ -]?key|token|password|parola|secret)\s*[:=]\s*([^\s,;]+)"),
    re.compile(r"(?i)Bearer\s+[A-Za-z0-9._~+/-]{8,}"),
    re.compile(r"(?i)(https?://[^\s/:]+:)[^@\s/]+(@)"),
)

def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(k): ("[SECRET]" if any(s in str(k).lower().replace("-", "_") for s in _SECRET_KEYS) else _redact(v))
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact(v) for v in value]
    if not isinstance(value, str):
        return value
    out = _SECRET_TEXT[0].sub("[SECRET]", value)
    out = _SECRET_TEXT[1].sub(lambda m: f"{m.group(1)}=[SECRET]", out)
    out = _SECRET_TEXT[2].sub("Bearer [SECRET]", out)
    out = _SECRET_TEXT[3].sub(r"\1[SECRET]\2", out)
    return out


@dataclass
class AuditEntry:
    tool: str
    risk: str
    decision: str           # allowed | denied | approved | error
    args: dict[str, Any] = field(default_factory=dict)
    detail: str = ""
    ts: float = field(default_factory=time.time)

    def to_json(self) -> str:
        # Disk logs must never contain credentials even if a tool argument did.
        return json.dumps(_redact(asdict(self)), ensure_ascii=False, sort_keys=True)


class AuditLog:
    """Writes :class:`AuditEntry` records to a JSONL file (and stays usable
    in-memory even if the path is unwritable)."""

    def __init__(self, path: Path | None = None, *, max_bytes: int = 10 * 1024 * 1024,
                 backup_count: int = 5) -> None:
        self.path = path
        self.max_bytes = max(0, int(max_bytes))
        self.backup_count = max(0, int(backup_count))
        self.entries: list[AuditEntry] = []
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, entry: AuditEntry) -> AuditEntry:
        self.entries.append(entry)
        if self.path is not None:
            try:
                line = entry.to_json() + "\n"
                rotate_if_needed(self.path, len(line.encode("utf-8")),
                                 max_bytes=self.max_bytes,
                                 backup_count=self.backup_count)
                with self.path.open("a", encoding="utf-8") as fh:
                    fh.write(line)
            except OSError:
                # Never let a logging failure crash a tool call; keep the
                # in-memory copy so the session still has the trail.
                pass
        return entry
