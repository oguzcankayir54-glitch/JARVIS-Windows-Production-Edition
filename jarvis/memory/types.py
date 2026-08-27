"""Canonical long-term memory categories for J.A.R.V.I.S. 2.0.

Existing databases are not rewritten.  ``category_family`` maps old Turkish
labels and newer canonical labels into one semantic family at read time, so
this refactor is backward compatible with months of accumulated user data.
"""
from __future__ import annotations

from enum import Enum

from ..core.metin import katla


class MemoryCategory(str, Enum):
    IDENTITY = "IDENTITY"
    PREFERENCE = "PREFERENCE"
    PROJECT = "PROJECT"
    FACT = "FACT"
    DECISION = "DECISION"
    INSTRUCTION = "INSTRUCTION"
    HISTORY = "HISTORY"
    TASK = "TASK"
    RELATIONSHIP = "RELATIONSHIP"
    TECHNICAL = "TECHNICAL"


_ALIASES: dict[str, MemoryCategory] = {
    "identity": MemoryCategory.IDENTITY,
    "kimlik": MemoryCategory.IDENTITY,
    "gelistirici": MemoryCategory.IDENTITY,
    "kullanici": MemoryCategory.IDENTITY,
    "preference": MemoryCategory.PREFERENCE,
    "tercih": MemoryCategory.PREFERENCE,
    "project": MemoryCategory.PROJECT,
    "proje": MemoryCategory.PROJECT,
    "fact": MemoryCategory.FACT,
    "genel": MemoryCategory.FACT,
    "decision": MemoryCategory.DECISION,
    "karar": MemoryCategory.DECISION,
    "instruction": MemoryCategory.INSTRUCTION,
    "talimat": MemoryCategory.INSTRUCTION,
    "kural": MemoryCategory.INSTRUCTION,
    "history": MemoryCategory.HISTORY,
    "gecmis": MemoryCategory.HISTORY,
    "oturum": MemoryCategory.HISTORY,
    "task": MemoryCategory.TASK,
    "gorev": MemoryCategory.TASK,
    "relationship": MemoryCategory.RELATIONSHIP,
    "iliski": MemoryCategory.RELATIONSHIP,
    "technical": MemoryCategory.TECHNICAL,
    "teknik": MemoryCategory.TECHNICAL,
    "donanim": MemoryCategory.TECHNICAL,
    "yapilandirma": MemoryCategory.TECHNICAL,
    "arac": MemoryCategory.TECHNICAL,
}


def category_family(value: str) -> MemoryCategory:
    key = katla((value or "").strip()).replace(" ", "_")
    return _ALIASES.get(key, MemoryCategory.FACT)
