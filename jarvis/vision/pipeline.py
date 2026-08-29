"""Provider-independent local vision orchestration."""
from __future__ import annotations

import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Iterable

from ..core.events import EventBus
from ..core.state import JarvisState, StateMachine
from .detect import MAX_FRAME_BYTES, VisionError

VISION_TASKS = frozenset({"faces", "objects", "ocr", "identity"})


@dataclass(frozen=True)
class VisionResult:
    source: str
    tasks: tuple[str, ...]
    analyses: dict[str, Any]
    duration_ms: float
    raw_frame_stored: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {"source": self.source, "tasks": list(self.tasks),
                "analyses": self.analyses, "duration_ms": self.duration_ms,
                "raw_frame_stored": self.raw_frame_stored}


class VisionPipeline:
    """Coordinates existing providers without coupling them to the LLM."""

    available = True
    reason = ""

    def __init__(self, *, faces, objects, ocr, identity, screenshot,
                 state: StateMachine, events: EventBus, workers: int = 2) -> None:
        self.faces = faces
        self.objects = objects
        self.ocr = ocr
        self.identity = identity
        self.screenshot = screenshot
        self.state = state
        self.events = events
        self._executor = ThreadPoolExecutor(
            max_workers=max(1, min(4, int(workers))),
            thread_name_prefix="jarvis-vision",
        )

    @staticmethod
    def normalize_tasks(tasks: Iterable[str]) -> tuple[str, ...]:
        normalized = tuple(dict.fromkeys(str(x).strip().lower() for x in tasks if str(x).strip()))
        unknown = set(normalized) - VISION_TASKS
        if unknown:
            raise ValueError(f"bilinmeyen vision görevi: {', '.join(sorted(unknown))}")
        if not normalized:
            raise ValueError("en az bir vision görevi gerekli")
        return normalized

    def submit(self, frame: bytes, tasks: Iterable[str], *,
               source: str = "upload") -> Future[VisionResult]:
        # Copy into immutable bytes before another request/thread can mutate it.
        return self._executor.submit(self.analyze, bytes(frame), tuple(tasks), source=source)

    def capture_and_submit(self, tasks: Iterable[str]) -> Future[VisionResult]:
        return self._executor.submit(self._capture_and_analyze, tuple(tasks))

    def _capture_and_analyze(self, tasks: tuple[str, ...]) -> VisionResult:
        if not self.screenshot.available:
            raise VisionError(getattr(self.screenshot, "reason", "Screenshot kullanılamıyor."))
        frame = self.screenshot.capture()
        return self.analyze(frame, tasks, source="desktop")

    def analyze(self, frame: bytes, tasks: Iterable[str], *,
                source: str = "upload") -> VisionResult:
        tasks = self.normalize_tasks(tasks)
        if not frame:
            raise VisionError("Görüntü boş.")
        if len(frame) > MAX_FRAME_BYTES:
            raise VisionError("Görüntü güvenli boyut sınırını aşıyor.")
        started = time.perf_counter()
        self.events.publish("vision.input", {"source": source, "bytes": len(frame),
                                             "tasks": list(tasks)}, source="vision")
        self.state.transition(JarvisState.SEEING, reason="vision.input")
        self.events.publish("vision.started", {"source": source, "tasks": list(tasks)},
                            source="vision")
        try:
            self.state.transition(JarvisState.ANALYZING, reason="vision.analysis")
            analyses: dict[str, Any] = {}
            for task in tasks:
                provider = getattr(self, task)
                if not getattr(provider, "available", False):
                    raise VisionError(getattr(provider, "reason", f"{task} kullanılamıyor"))
                if task == "faces":
                    analyses[task] = [x.as_dict() for x in provider.detect(frame)]
                elif task == "objects":
                    analyses[task] = [x.as_dict() for x in provider.detect(frame)]
                elif task == "ocr":
                    analyses[task] = provider.read(frame).as_dict()
                elif task == "identity":
                    analyses[task] = provider.identify(frame).as_dict()
            result = VisionResult(
                source=source, tasks=tasks, analyses=analyses,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )
            self.events.publish(
                "vision.finished", {"source": source, "tasks": list(tasks),
                                    "duration_ms": result.duration_ms}, source="vision")
            return result
        except Exception as exc:
            self.events.publish(
                "vision.error", {"source": source, "tasks": list(tasks),
                                 "error_type": type(exc).__name__}, source="vision")
            raise
        finally:
            self.state.transition(JarvisState.STANDBY, reason="vision.finished")

    def close(self) -> None:
        self._executor.shutdown(wait=True, cancel_futures=True)
