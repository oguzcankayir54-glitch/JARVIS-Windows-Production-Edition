"""Optional local object detection; frames are decoded and discarded."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

MAX_OBJECT_FRAME_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True)
class ObjectDetection:
    label: str
    confidence: float
    x: float
    y: float
    w: float
    h: float

    def as_dict(self) -> dict[str, float | str]:
        return {"label": self.label, "confidence": round(self.confidence, 4),
                "x": round(self.x, 4), "y": round(self.y, 4),
                "w": round(self.w, 4), "h": round(self.h, 4)}


class ObjectVision:
    name = "yolo"

    def __init__(self, model: str = "yolo11n.pt") -> None:
        self.model = model
        self.available = True
        self._model = None

    def _load(self):
        if self._model is not None:
            return self._model
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise RuntimeError(
                "Nesne tanıma için ultralytics gerekli: pip install -e '.[gorsel]'"
            ) from exc
        self._model = YOLO(self.model)
        return self._model

    def detect(self, frame: bytes) -> list[ObjectDetection]:
        if not frame:
            raise ValueError("Kare boş.")
        if len(frame) > MAX_OBJECT_FRAME_BYTES:
            raise ValueError("Kare çok büyük.")
        try:
            import cv2
            import numpy as np
        except ImportError as exc:
            raise RuntimeError("Nesne tanıma için OpenCV gerekli.") from exc
        image = cv2.imdecode(np.frombuffer(frame, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("Kare çözümlenemedi.")
        height, width = image.shape[:2]
        results = self._load()(image, verbose=False)
        names = getattr(self._load(), "names", {})
        detections: list[ObjectDetection] = []
        for result in results:
            boxes = getattr(result, "boxes", None)
            if boxes is None:
                continue
            for box, confidence, cls in zip(boxes.xyxy.tolist(),
                                            boxes.conf.tolist(), boxes.cls.tolist()):
                x1, y1, x2, y2 = box
                detections.append(ObjectDetection(
                    str(names.get(int(cls), int(cls))), float(confidence),
                    x1 / width, y1 / height, (x2 - x1) / width, (y2 - y1) / height,
                ))
        return detections


class NullObjectVision:
    name = "yok"
    available = False

    def __init__(self, reason: str) -> None:
        self.reason = reason

    def detect(self, frame: bytes) -> list[ObjectDetection]:
        return []


def build_object_vision(enabled: bool = False, model: str = "yolo11n.pt"):
    if not enabled:
        return NullObjectVision("Nesne tanıma kapalı.")
    try:
        import ultralytics  # noqa: F401
    except ImportError:
        return NullObjectVision(
            "Nesne tanıma hazır değil: pip install -e '.[gorsel]'"
        )
    return ObjectVision(model)
