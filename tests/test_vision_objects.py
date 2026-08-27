from jarvis.vision.objects import ObjectVision, ObjectDetection, build_object_vision
from jarvis.vision.ocr import OcrResult, TesseractOCR, build_ocr
from jarvis.vision.identity import FaceMatch, FaceTemplateStore, build_face_recognizer


def test_disabled_object_vision_is_honest():
    provider = build_object_vision(enabled=False)
    assert provider.available is False
    assert provider.detect(b"") == []


def test_detection_uses_normalized_coordinates():
    item = ObjectDetection("bottle", 0.91, 0.1, 0.2, 0.3, 0.4)
    assert item.as_dict() == {
        "label": "bottle", "confidence": 0.91,
        "x": 0.1, "y": 0.2, "w": 0.3, "h": 0.4,
    }


def test_object_vision_refuses_oversized_or_empty_frames():
    provider = ObjectVision(model="missing-model.pt")
    import pytest
    with pytest.raises(ValueError, match="boş"):
        provider.detect(b"")
    with pytest.raises(ValueError, match="büyük"):
        provider.detect(b"x" * (8 * 1024 * 1024 + 1))


def test_ocr_is_disabled_honestly_and_result_is_structured():
    assert build_ocr(enabled=False).available is False
    result = OcrResult("Jarvis", 0.88)
    assert result.as_dict()["text"] == "Jarvis"


def test_ocr_bounds_input_before_optional_dependency():
    provider = TesseractOCR()
    import pytest
    with pytest.raises(ValueError, match="boş"):
        provider.read(b"")


def test_face_identity_is_disabled_by_default_and_match_is_structured():
    provider = build_face_recognizer(enabled=False)
    assert provider.available is False
    assert FaceMatch(None, 0.0, False).as_dict()["known"] is False


def test_face_templates_store_embeddings_only_and_use_private_permissions(tmp_path):
    store = FaceTemplateStore(tmp_path / "faces.json")
    store.put("Oğuz", [0.1, 0.2, 0.3])
    loaded = FaceTemplateStore(tmp_path / "faces.json")
    assert loaded.templates == {"Oğuz": [0.1, 0.2, 0.3]}
    assert "photo" not in (tmp_path / "faces.json").read_text(encoding="utf-8")
