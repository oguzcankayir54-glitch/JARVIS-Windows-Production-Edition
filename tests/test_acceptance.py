from types import SimpleNamespace

from jarvis.acceptance.engine import AcceptanceCheck, AcceptanceReport, run_acceptance


class Provider:
    available = True
    name = "test-provider"


def cfg(tmp_path, **changes):
    values = dict(data_dir=tmp_path, llm_provider="ollama",
                  ollama_host="http://127.0.0.1:11434", ollama_model="qwen",
                  voice_enabled=True, stt_enabled=True, vision_enabled=True,
                  object_vision_enabled=True, ocr_enabled=True,
                  face_recognition_enabled=True)
    values.update(changes)
    return SimpleNamespace(**values)


def test_ready_report_when_required_and_optional_checks_are_ready(tmp_path, monkeypatch):
    monkeypatch.setattr("jarvis.acceptance.engine.platform.system", lambda: "Windows")
    monkeypatch.setattr("jarvis.acceptance.engine.importlib.util.find_spec", lambda _: object())
    report = run_acceptance(
        cfg(tmp_path), tts=Provider(), stt=Provider(), vision=Provider(),
        object_vision=Provider(), ocr=Provider(), face_recognizer=Provider(),
        notifier=Provider(), ollama_probe=lambda *_: "",
    )
    assert report.status == "hazir"
    assert all(x.status == "hazir" for x in report.checks)


def test_mock_model_is_a_required_missing_check(tmp_path, monkeypatch):
    monkeypatch.setattr("jarvis.acceptance.engine.platform.system", lambda: "Windows")
    report = run_acceptance(cfg(tmp_path, llm_provider="mock"), tts=Provider(),
                            stt=Provider(), vision=Provider(), notifier=Provider())
    item = next(x for x in report.checks if x.id == "ollama")
    assert item.required and item.status == "eksik"
    assert report.status == "eksik"


def test_disabled_devices_are_reported_missing_not_ready(tmp_path, monkeypatch):
    monkeypatch.setattr("jarvis.acceptance.engine.platform.system", lambda: "Windows")
    report = run_acceptance(cfg(tmp_path, voice_enabled=False, stt_enabled=False,
                                vision_enabled=False, object_vision_enabled=False,
                                ocr_enabled=False, face_recognition_enabled=False), notifier=Provider(),
                            ollama_probe=lambda *_: "")
    assert {x.id for x in report.checks if x.status == "eksik"} >= {
        "tts", "microphone", "camera"}
    assert {x.id for x in report.checks}.isdisjoint({"objects", "ocr", "face_identity"})


def test_enabled_extended_vision_failure_is_reported(tmp_path, monkeypatch):
    monkeypatch.setattr("jarvis.acceptance.engine.platform.system", lambda: "Windows")
    broken = SimpleNamespace(available=False, reason="YOLO modeli bulunamadı.")
    report = run_acceptance(
        cfg(tmp_path), tts=Provider(), stt=Provider(), vision=Provider(),
        object_vision=broken, ocr=Provider(), face_recognizer=Provider(),
        notifier=Provider(), ollama_probe=lambda *_: "",
    )
    check = next(x for x in report.checks if x.id == "objects")
    assert check.status == "arizali"
    assert "YOLO" in check.detail


def test_provider_failure_preserves_safe_one_line_reason(tmp_path, monkeypatch):
    monkeypatch.setattr("jarvis.acceptance.engine.platform.system", lambda: "Windows")
    broken = SimpleNamespace(available=False, reason="Paket yok.\npip secret")
    report = run_acceptance(cfg(tmp_path), tts=broken, stt=Provider(), vision=Provider(),
                            notifier=Provider(), ollama_probe=lambda *_: "")
    check = next(x for x in report.checks if x.id == "tts")
    assert check.status == "arizali" and check.detail == "Paket yok."


def test_report_counts_and_required_failure_priority():
    report = AcceptanceReport((
        AcceptanceCheck("a", "A", "eksik", "", required=False),
        AcceptanceCheck("b", "B", "arizali", "", required=True),
    ))
    assert report.status == "arizali"
    assert report.as_dict()["counts"] == {"hazir": 0, "eksik": 1, "arizali": 1}
