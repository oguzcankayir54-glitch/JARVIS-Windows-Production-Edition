"""Optional local OCR adapter with bounded, non-persistent frame handling."""
from __future__ import annotations

from dataclasses import dataclass

MAX_OCR_FRAME_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True)
class OcrResult:
    text: str
    confidence: float | None = None
    language: str = "tur"

    def as_dict(self) -> dict[str, object]:
        return {"text": self.text, "confidence": self.confidence,
                "language": self.language}


class TesseractOCR:
    name = "tesseract"
    available = True

    def __init__(self, language: str = "tur") -> None:
        self.language = language

    def read(self, frame: bytes) -> OcrResult:
        if not frame:
            raise ValueError("Kare boş.")
        if len(frame) > MAX_OCR_FRAME_BYTES:
            raise ValueError("Kare çok büyük.")
        try:
            import pytesseract
            from PIL import Image
            from io import BytesIO
            image = Image.open(BytesIO(frame))
            text = pytesseract.image_to_string(image, lang=self.language).strip()
        except ImportError as exc:
            raise RuntimeError("OCR için pytesseract ve Pillow gerekli.") from exc
        return OcrResult(text=text, language=self.language)


class NullOCR:
    name = "yok"
    available = False

    def __init__(self, reason: str) -> None:
        self.reason = reason

    def read(self, frame: bytes) -> OcrResult:
        return OcrResult(text="", language="tur")


def build_ocr(enabled: bool = False, language: str = "tur"):
    if not enabled:
        return NullOCR("OCR kapalı.")
    try:
        import pytesseract  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError:
        return NullOCR("OCR hazır değil: pip install -e '.[gorsel]'")
    return TesseractOCR(language)
