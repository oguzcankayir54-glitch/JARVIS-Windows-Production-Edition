"""Persistent, auditable natural-language aliases for ordinary JARVIS commands."""
from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass
from pathlib import Path

from .metin import katla


@dataclass(frozen=True)
class CustomCommand:
    phrase: str
    expansion: str


class CustomCommandStore:
    """Exact phrase aliases; expansions still pass through every safety layer."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self._lock = threading.RLock()
        self._items: dict[str, CustomCommand] = {}
        self._load()

    def _load(self) -> None:
        if self.path is None or not self.path.is_file():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            for row in data if isinstance(data, list) else []:
                phrase, expansion = str(row["phrase"]).strip(), str(row["expansion"]).strip()
                if phrase and expansion:
                    self._items[katla(phrase)] = CustomCommand(phrase, expansion)
        except (OSError, ValueError, KeyError, TypeError):
            return

    def _save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps([asdict(x) for x in self.all()], ensure_ascii=False,
                                        indent=2), encoding="utf-8")
        temporary.replace(self.path)

    def teach(self, phrase: str, expansion: str) -> CustomCommand:
        phrase, expansion = phrase.strip(), expansion.strip()
        if not 2 <= len(phrase) <= 100 or not 2 <= len(expansion) <= 300:
            raise ValueError("Komut 2-100, karşılığı 2-300 karakter olmalı.")
        if katla(phrase) == katla(expansion):
            raise ValueError("Komut ve karşılığı aynı olamaz.")
        with self._lock:
            item = CustomCommand(phrase, expansion)
            self._items[katla(phrase)] = item
            self._save()
            return item

    def resolve(self, text: str) -> str | None:
        with self._lock:
            item = self._items.get(katla(text.strip()))
            return item.expansion if item else None

    def all(self) -> list[CustomCommand]:
        with self._lock:
            return sorted(self._items.values(), key=lambda x: katla(x.phrase))

    def delete(self, phrase: str) -> bool:
        with self._lock:
            removed = self._items.pop(katla(phrase.strip()), None) is not None
            if removed:
                self._save()
            return removed
