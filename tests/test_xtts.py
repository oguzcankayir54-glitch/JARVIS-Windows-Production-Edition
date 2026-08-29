"""Local Craig XTTS provider: selection, warm loading and memory cache."""
from jarvis.voice.tts import build_tts
from jarvis.voice.xtts import XTTSTTS
from jarvis.voice.tts import TTSError
import pytest


class _FakeModel:
    def __init__(self):
        self.calls = []

    def tts(self, **kwargs):
        self.calls.append(kwargs)
        return [0.0, 0.1, -0.1, 0.0]


def test_xtts_can_be_selected(monkeypatch):
    monkeypatch.setattr("jarvis.voice.xtts.xtts_hazir", lambda: "")
    monkeypatch.setattr("jarvis.voice.xtts.XTTSTTS._warm_up", lambda self: None)
    provider = build_tts(None, None, "m", provider="xtts")
    assert provider.name == "xtts"
    assert provider.mime == "audio/wav"


def test_missing_xtts_dependency_is_actionable(monkeypatch):
    monkeypatch.setattr("jarvis.voice.xtts.xtts_hazir", lambda: "XTTS eksik")
    provider = build_tts(None, None, "m", provider="xtts")
    assert provider.available is False
    assert "XTTS" in provider.reason


def test_model_is_reused_and_audio_is_cached(monkeypatch):
    model = _FakeModel()
    factory_calls = []

    def factory(name, device):
        factory_calls.append((name, device))
        return model

    provider = XTTSTTS(
        speaker="Craig Gutsy", speed=1.04, device="cpu", preload=False,
        model_factory=factory,
    )
    monkeypatch.setattr(provider, "_studio_wav", lambda samples: b"RIFF-audio")

    first = b"".join(provider.synthesize("Efendim, hoş geldiniz."))
    second = b"".join(provider.synthesize("Efendim, hoş geldiniz."))

    assert first == second == b"RIFF-audio"
    assert factory_calls == [(provider.model_name, "cpu")]
    assert len(model.calls) == 1
    assert model.calls[0]["speaker"] == "Craig Gutsy"
    assert model.calls[0]["language"] == "tr"
    assert model.calls[0]["speed"] == 1.04


def test_preload_warms_the_model_once(monkeypatch):
    model = _FakeModel()
    provider = XTTSTTS(
        preload=True, device="cpu", model_factory=lambda _name, _device: model,
    )
    assert provider._warm_thread is not None
    provider.wait_ready(timeout=2)
    assert len(model.calls) == 1
    assert model.calls[0]["text"] == "Efendim, hazırım."


def test_close_releases_model_cache_and_rejects_new_synthesis(monkeypatch):
    model = _FakeModel()
    provider = XTTSTTS(
        preload=False, device="cpu", cache_size=2,
        model_factory=lambda _name, _device: model,
    )
    monkeypatch.setattr(provider, "_studio_wav", lambda samples: b"RIFF-audio")
    assert b"".join(provider.synthesize("Sistem hazır."))
    assert provider.ready
    assert provider._cache

    provider.close()

    assert provider.available is False
    assert provider.ready is False
    assert provider._model is None
    assert provider._cache == {}
    with pytest.raises(TTSError, match="kapatıldı"):
        next(provider.synthesize("Tekrar konuş."))


def test_warmup_failure_is_reflected_in_provider_health():
    def broken(_name, _device):
        raise RuntimeError("weights unavailable")

    provider = XTTSTTS(preload=True, device="cpu", model_factory=broken)
    with pytest.raises(TTSError):
        provider.wait_ready(timeout=2)
    assert provider.available is False
    assert "weights unavailable" in provider.reason
