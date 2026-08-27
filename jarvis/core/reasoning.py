"""Adaptive, bounded inference profiles for each task difficulty."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReasoningProfile:
    level: int
    temperature: float
    top_p: float
    num_predict: int
    thinking: bool


_PROFILES = {
    0: ReasoningProfile(0, 0.0, 0.8, 0, False),
    1: ReasoningProfile(1, 0.35, 0.85, 192, False),
    2: ReasoningProfile(2, 0.35, 0.90, 384, False),
    3: ReasoningProfile(3, 0.45, 0.92, 640, False),
    4: ReasoningProfile(4, 0.60, 0.95, 896, True),
    5: ReasoningProfile(5, 0.70, 0.95, 1280, True),
}


def profile_for(level: int) -> ReasoningProfile:
    return _PROFILES[max(0, min(5, int(level)))]
