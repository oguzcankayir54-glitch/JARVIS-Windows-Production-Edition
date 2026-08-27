"""Consent-based local face identity templates; raw frames are never stored."""
from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class FaceMatch:
    identity: str | None
    confidence: float
    known: bool

    def as_dict(self) -> dict[str, Any]:
        return {"identity": self.identity, "confidence": round(self.confidence, 4),
                "known": self.known}


class FaceTemplateStore:
    """Small JSON template store. It contains embeddings, never photographs."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser()
        self.templates: dict[str, list[float]] = {}
        self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if isinstance(data, dict):
            self.templates = {
                str(name): [float(x) for x in values]
                for name, values in data.items()
                if isinstance(values, list) and values
            }

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.templates, ensure_ascii=False), encoding="utf-8")
        try:
            os.chmod(self.path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass

    def put(self, name: str, embedding: list[float]) -> None:
        clean = (name or "").strip()
        if not clean or len(clean) > 120:
            raise ValueError("Geçerli bir kimlik adı gerekli.")
        if not embedding:
            raise ValueError("Boş yüz embedding'i kaydedilemez.")
        self.templates[clean] = [float(x) for x in embedding]
        self.save()

    def remove(self, name: str) -> bool:
        existed = (name or "") in self.templates
        self.templates.pop(name or "", None)
        if existed:
            self.save()
        return existed


class LocalFaceRecognizer:
    name = "local-face-embedding"
    available = True

    def __init__(self, store: FaceTemplateStore, tolerance: float = 0.48) -> None:
        self.store = store
        self.tolerance = max(0.1, min(1.0, float(tolerance)))

    @staticmethod
    def _module():
        try:
            import face_recognition
        except ImportError as exc:
            raise RuntimeError(
                "Yüz tanıma için face-recognition gerekli: pip install -e '.[yuz]'"
            ) from exc
        return face_recognition

    def _embedding(self, frame: bytes) -> list[float]:
        if not frame:
            raise ValueError("Kare boş.")
        module = self._module()
        image = module.load_image_file(__import__("io").BytesIO(frame))
        encodings = module.face_encodings(image)
        if len(encodings) != 1:
            raise ValueError("Kimlik kaydı için karede tam olarak bir yüz olmalı.")
        return [float(value) for value in encodings[0]]

    def enroll(self, name: str, frame: bytes) -> dict[str, Any]:
        self.store.put(name, self._embedding(frame))
        return {"kaydedildi": True, "identity": name.strip(), "raw_frame_stored": False}

    def identify(self, frame: bytes) -> FaceMatch:
        embedding = self._embedding(frame)
        if not self.store.templates:
            return FaceMatch(None, 0.0, False)
        module = self._module()
        names = list(self.store.templates)
        known = [self.store.templates[name] for name in names]
        distances = module.face_distance(known, embedding)
        index = min(range(len(distances)), key=lambda i: distances[i])
        distance = float(distances[index])
        confidence = max(0.0, min(1.0, 1.0 - distance))
        return FaceMatch(names[index], confidence, distance <= self.tolerance)


class NullFaceRecognizer:
    name = "yok"
    available = False

    def __init__(self, reason: str) -> None:
        self.reason = reason

    def identify(self, frame: bytes) -> FaceMatch:
        return FaceMatch(None, 0.0, False)

    def enroll(self, name: str, frame: bytes) -> dict[str, Any]:
        raise RuntimeError(self.reason)


def build_face_recognizer(enabled: bool = False, path: str | Path = "~/.jarvis/face_templates.json"):
    if not enabled:
        return NullFaceRecognizer("Yüz tanıma kapalı.")
    try:
        import face_recognition  # noqa: F401
    except ImportError:
        return NullFaceRecognizer(
            "Yüz tanıma hazır değil: pip install -e '.[yuz]'"
        )
    return LocalFaceRecognizer(FaceTemplateStore(path))
