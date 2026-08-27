"""Conservative, auditable normalization for Turkish speech transcripts."""
from __future__ import annotations

from dataclasses import dataclass

from ..core.metin import katla
from ..security.permissions import RiskLevel


@dataclass(frozen=True)
class SpeechNormalization:
    original_text: str
    normalized_text: str
    confidence: float
    corrections: tuple[str, ...] = ()
    ambiguity: bool = False
    needs_confirmation: bool = False


class SpeechNormalizer:
    """Apply only narrow corrections backed by known STT failure examples.

    This is intentionally not a general autocorrect engine. Broad fuzzy
    replacement can turn an innocent sentence into a computer action.
    """

    _KNOWN: dict[str, tuple[str, float, str]] = {
        "gorev yerini sinac": (
            "Görev yöneticisini aç", 0.94,
            "bilinen STT bozulması: görev yöneticisini aç",
        ),
        "sasirt benim": (
            "Şaşırt beni", 0.96,
            "bilinen dilbilgisel STT bozulması: şaşırt beni",
        ),
    }

    def normalize(self, text: str, *, transcription_confidence: float = 1.0,
                  risk: RiskLevel = RiskLevel.LOW) -> SpeechNormalization:
        original = (text or "").strip()
        source_confidence = max(0.0, min(1.0, float(transcription_confidence)))
        known = self._KNOWN.get(katla(original))
        if known is None:
            normalized = original
            confidence = source_confidence
            corrections: tuple[str, ...] = ()
        else:
            normalized, rule_confidence, explanation = known
            confidence = min(source_confidence, rule_confidence)
            corrections = (explanation,)

        ambiguity = confidence < 0.65
        needs_confirmation = ambiguity and risk >= RiskLevel.HIGH
        return SpeechNormalization(
            original_text=original,
            normalized_text=normalized,
            confidence=round(confidence, 3),
            corrections=corrections,
            ambiguity=ambiguity,
            needs_confirmation=needs_confirmation,
        )
