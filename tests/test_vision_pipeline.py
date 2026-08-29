from __future__ import annotations

import threading

import pytest

from jarvis.core.events import EventBus
from jarvis.core.state import JarvisState, StateMachine
from jarvis.vision.detect import MAX_FRAME_BYTES, VisionError
from jarvis.vision.pipeline import VisionPipeline


class _Value:
    def __init__(self, value):
        self.value = value

    def as_dict(self):
        return self.value


class _Detector:
    available = True

    def detect(self, _frame):
        return [_Value({"label": "item"})]


class _Reader:
    available = True

    def read(self, _frame):
        return _Value({"text": "JARVIS"})


class _Identity:
    available = True

    def identify(self, _frame):
        return _Value({"known": True, "name": "owner"})


class _Screenshot:
    available = True

    def capture(self):
        return b"png"


def _pipeline(events=None):
    return VisionPipeline(
        faces=_Detector(), objects=_Detector(), ocr=_Reader(),
        identity=_Identity(), screenshot=_Screenshot(),
        state=StateMachine(), events=events or EventBus(),
    )


def test_pipeline_uses_existing_providers_and_returns_no_raw_frame():
    pipeline = _pipeline()
    try:
        result = pipeline.analyze(b"image", ("faces", "objects", "ocr", "identity"))
        assert result.analyses["faces"] == [{"label": "item"}]
        assert result.analyses["ocr"] == {"text": "JARVIS"}
        assert result.raw_frame_stored is False
        assert pipeline.state.state is JarvisState.STANDBY
    finally:
        pipeline.close()


def test_pipeline_emits_lifecycle_without_raw_image_data():
    events = EventBus()
    seen = []
    events.subscribe("vision.*", seen.append)
    pipeline = _pipeline(events)
    try:
        pipeline.analyze(b"private-image", ("ocr",), source="upload")
        assert [event.name for event in seen] == [
            "vision.input", "vision.started", "vision.finished"
        ]
        assert all(b"private-image" not in repr(event.payload).encode() for event in seen)
    finally:
        pipeline.close()


def test_pipeline_rejects_unknown_empty_and_oversized_inputs():
    pipeline = _pipeline()
    try:
        with pytest.raises(ValueError):
            pipeline.analyze(b"x", ("depth",))
        with pytest.raises(VisionError):
            pipeline.analyze(b"", ("ocr",))
        with pytest.raises(VisionError):
            pipeline.analyze(b"x" * (MAX_FRAME_BYTES + 1), ("ocr",))
    finally:
        pipeline.close()


def test_submit_runs_analysis_off_the_calling_thread():
    pipeline = _pipeline()
    caller = threading.current_thread().name
    names = []
    original = pipeline.ocr.read
    pipeline.ocr.read = lambda frame: (names.append(threading.current_thread().name) or original(frame))
    try:
        pipeline.submit(b"x", ("ocr",)).result(timeout=2)
        assert names and names[0] != caller
        assert names[0].startswith("jarvis-vision")
    finally:
        pipeline.close()


def test_screenshot_source_flows_through_the_same_pipeline():
    pipeline = _pipeline()
    try:
        result = pipeline.capture_and_submit(("ocr",)).result(timeout=2)
        assert result.source == "desktop"
        assert result.analyses["ocr"]["text"] == "JARVIS"
    finally:
        pipeline.close()
