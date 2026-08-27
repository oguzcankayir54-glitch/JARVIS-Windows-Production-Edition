"""Local speech-to-text: absence handling, limits, and device resolution.

No test loads a Whisper model or touches a GPU — the suite has to pass on a
machine that has neither. What is checked is the wiring around the model:
that a missing dependency degrades instead of crashing, that an oversized
recording is refused before it is read, and that the recording does not
survive on disk.
"""
import pytest

from jarvis.voice import stt as stt_mod
from jarvis.voice.stt import (
    MAX_AUDIO_BYTES,
    NullSTT,
    STTError,
    WhisperSTT,
    build_stt,
    suffix_for,
)
from jarvis.voice.normalization import SpeechNormalizer
from jarvis.security.permissions import RiskLevel


# ---------------- graceful absence ----------------

def test_build_returns_null_when_disabled():
    provider = build_stt(enabled=False)
    assert isinstance(provider, NullSTT)
    assert provider.available is False


def test_null_provider_explains_itself():
    """The panel shows this text; it must say what to do, not just fail."""
    with pytest.raises(STTError) as exc:
        NullSTT().transcribe(b"veri")
    assert "faster-whisper" in str(exc.value)


def test_missing_dependency_does_not_raise_at_build(monkeypatch):
    """A machine without faster-whisper must still start J.A.R.V.I.S."""
    import builtins
    real_import = builtins.__import__

    def sahte(name, *args, **kwargs):
        if name == "faster_whisper":
            raise ImportError("yok")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", sahte)
    provider = build_stt(enabled=True)
    assert provider.available is False


# ---------------- container detection ----------------

def test_safari_and_chrome_containers_are_distinguished():
    """Safari records mp4/aac, Chrome webm/opus; the decoder needs to know."""
    assert suffix_for("audio/mp4") == ".mp4"
    assert suffix_for("audio/webm;codecs=opus") == ".webm"
    assert suffix_for("audio/ogg") == ".ogg"


def test_unknown_container_falls_back_to_webm():
    assert suffix_for("") == ".webm"
    assert suffix_for("application/octet-stream") == ".webm"


# ---------------- limits ----------------

def _stt() -> WhisperSTT:
    return WhisperSTT(model_size="tiny", device="cpu", compute_type="int8")


def test_empty_audio_is_refused():
    with pytest.raises(STTError, match="boş"):
        _stt().transcribe(b"")


def test_oversized_audio_is_refused_without_loading_a_model():
    """The cap exists to bound memory, so it must apply before any decoding."""
    provider = _stt()
    provider._load = lambda: (_ for _ in ()).throw(AssertionError("model yüklenmemeliydi"))
    with pytest.raises(STTError, match="çok büyük"):
        provider.transcribe(b"x" * (MAX_AUDIO_BYTES + 1))


# ---------------- device resolution ----------------

def test_auto_picks_gpu_when_available(monkeypatch):
    monkeypatch.setattr(stt_mod, "_cuda_var_mi", lambda: True)
    provider = WhisperSTT(device="auto", compute_type="auto")
    assert provider.device == "cuda"
    # int8_float16 halves what float16 would take — the 14B model needs the room.
    assert provider.compute_type == "int8_float16"


def test_auto_falls_back_to_cpu_without_gpu(monkeypatch):
    monkeypatch.setattr(stt_mod, "_cuda_var_mi", lambda: False)
    provider = WhisperSTT(device="auto", compute_type="auto")
    assert (provider.device, provider.compute_type) == ("cpu", "int8")


def test_explicit_device_is_respected(monkeypatch):
    monkeypatch.setattr(stt_mod, "_cuda_var_mi", lambda: True)
    assert WhisperSTT(device="cpu").device == "cpu"


def test_cuda_probe_survives_missing_ctranslate2(monkeypatch):
    import builtins
    real_import = builtins.__import__

    def sahte(name, *args, **kwargs):
        if name == "ctranslate2":
            raise ImportError("yok")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", sahte)
    assert stt_mod._cuda_var_mi() is False


# ---------------- transcription plumbing ----------------

class _SahteSegment:
    def __init__(self, text: str) -> None:
        self.text = text


class _SahteModel:
    """Stands in for WhisperModel: records the path, returns fixed segments."""

    def __init__(self) -> None:
        self.gorulen_yol = None
        self.dil = None

    def transcribe(self, path, language=None, **kwargs):
        self.gorulen_yol = path
        self.dil = language
        return [_SahteSegment(" merhaba "), _SahteSegment("jarvis ")], {}


def test_segments_are_joined_and_trimmed():
    provider = _stt()
    provider._model = _SahteModel()
    assert provider.transcribe(b"sesverisi", "audio/webm") == "merhaba jarvis"


def test_language_is_passed_through():
    provider = WhisperSTT(model_size="tiny", device="cpu", language="tr")
    model = _SahteModel()
    provider._model = model
    provider.transcribe(b"sesverisi")
    assert model.dil == "tr"


def test_recording_is_deleted_after_transcription():
    """A voice sample is personal data; it must not linger in /tmp."""
    from pathlib import Path
    provider = _stt()
    model = _SahteModel()
    provider._model = model
    provider.transcribe(b"sesverisi", "audio/mp4")
    assert model.gorulen_yol is not None
    assert model.gorulen_yol.endswith(".mp4")
    assert not Path(model.gorulen_yol).exists()


# ---------------- CUDA fallback ----------------
#
# Regression guard: CTranslate2 opens libcublas/libcudnn at the first compute,
# not when the model is built. Falling back only at load time therefore never
# fired — the GPU model built cleanly and decoding failed with
# "Library libcublas.so.12 is not found", which reached the user verbatim.

class _CudaPatlayanModel:
    """Builds happily, then fails the way a missing CUDA library does."""

    def transcribe(self, path, **kwargs):
        raise RuntimeError("Library libcublas.so.12 is not found or cannot be loaded")


def test_missing_cuda_library_at_decode_falls_back_to_cpu(monkeypatch):
    monkeypatch.setattr(stt_mod, "_cuda_var_mi", lambda: True)
    provider = WhisperSTT(model_size="tiny", device="auto", compute_type="auto")
    assert provider.device == "cuda"

    kurulanlar = []

    def sahte_load(self):
        kurulanlar.append(self.device)
        if self._model is None:
            self._model = _CudaPatlayanModel() if self.device == "cuda" else _SahteModel()
        return self._model

    monkeypatch.setattr(WhisperSTT, "_load", sahte_load)
    assert provider.transcribe(b"sesverisi") == "merhaba jarvis"
    assert kurulanlar == ["cuda", "cpu"], "GPU denenmeli, sonra CPU'ya düşülmeli"
    assert provider.device == "cpu"


def test_cuda_fallback_is_not_attempted_twice(monkeypatch):
    """A CPU decode that also fails must report, not loop."""
    monkeypatch.setattr(stt_mod, "_cuda_var_mi", lambda: True)
    provider = WhisperSTT(model_size="tiny", device="auto")

    def sahte_load(self):
        return _CudaPatlayanModel()

    monkeypatch.setattr(WhisperSTT, "_load", sahte_load)
    with pytest.raises(STTError, match="çözümlenemedi"):
        provider.transcribe(b"sesverisi")


def test_ordinary_decode_failure_is_not_treated_as_a_cuda_problem(monkeypatch):
    """A corrupt recording must not silently move the model to the CPU."""
    monkeypatch.setattr(stt_mod, "_cuda_var_mi", lambda: True)
    provider = WhisperSTT(model_size="tiny", device="auto")

    class _BozukKap:
        def transcribe(self, path, **kwargs):
            raise RuntimeError("Invalid data found when processing input")

    monkeypatch.setattr(WhisperSTT, "_load", lambda self: _BozukKap())
    with pytest.raises(STTError, match="çözümlenemedi"):
        provider.transcribe(b"sesverisi")
    assert provider.device == "cuda", "alakasız hata cihazı değiştirmemeli"


@pytest.mark.parametrize("mesaj", [
    "Library libcublas.so.12 is not found or cannot be loaded",
    "Unable to load libcudnn_ops.so.9",
    "CUDA driver version is insufficient",
])
def test_cuda_library_failures_are_recognised(mesaj):
    assert stt_mod._cuda_kutuphane_hatasi(RuntimeError(mesaj))


@pytest.mark.parametrize("mesaj", [
    "Invalid data found when processing input",
    "moov atom not found",
    "ses kaydı bozuk",
])
def test_audio_failures_are_not_mistaken_for_cuda(mesaj):
    assert not stt_mod._cuda_kutuphane_hatasi(RuntimeError(mesaj))


def test_library_preload_survives_missing_packages():
    """Without the nvidia-* wheels this must do nothing, not raise."""
    stt_mod._cuda_kutuphanelerini_yukle()


def test_falling_back_to_cpu_discards_the_gpu_model(monkeypatch):
    """Keeping the GPU model would send the retry straight back to the GPU."""
    monkeypatch.setattr(stt_mod, "_cuda_var_mi", lambda: True)
    provider = WhisperSTT(model_size="tiny", device="auto")
    provider._model = _CudaPatlayanModel()
    provider._cpuya_dus()
    assert provider._model is None
    assert (provider.device, provider.compute_type) == ("cpu", "int8")


def test_recording_is_deleted_even_when_decoding_fails():
    from pathlib import Path

    gorulen = {}

    class _PatlayanModel:
        def transcribe(self, path, **kwargs):
            gorulen["yol"] = path
            raise RuntimeError("bozuk kap")

    provider = _stt()
    provider._model = _PatlayanModel()
    with pytest.raises(STTError, match="çözümlenemedi"):
        provider.transcribe(b"sesverisi")
    assert not Path(gorulen["yol"]).exists()


def test_decode_uses_accuracy_and_vad_tuning():
    provider = WhisperSTT(model_size="tiny", device="cpu", compute_type="int8",
                          beam_size=4, vad_min_silence_ms=420,
                          vad_speech_pad_ms=180, condition_on_previous_text=False)
    seen = {}
    class Model:
        def transcribe(self, path, **kwargs):
            seen.update(kwargs)
            return [_SahteSegment(" tamam ")], {}
    provider._model = Model()
    assert provider.transcribe(b"ses") == "tamam"
    assert seen["beam_size"] == 4
    assert seen["temperature"] == 0.0
    assert seen["condition_on_previous_text"] is False
    assert seen["vad_parameters"]["min_silence_duration_ms"] == 420
    assert seen["vad_parameters"]["speech_pad_ms"] == 180


def test_special_names_bias_decoder_without_rewriting_real_words():
    provider = WhisperSTT(
        model_size="tiny", device="cpu", hotwords=" Jarvis, Oğuz, BIOS ",
        initial_prompt="Asistanın adı Jarvis.",
    )
    seen = {}

    class Model:
        def transcribe(self, path, **kwargs):
            seen.update(kwargs)
            return [_SahteSegment(" servis kaydı aç ")], {}

    provider._model = Model()
    assert provider.transcribe(b"ses") == "servis kaydı aç"
    assert seen["hotwords"] == "Jarvis, Oğuz, BIOS"
    assert seen["initial_prompt"] == "Asistanın adı Jarvis."


# ---------------- structured speech normalization ----------------

def test_known_stt_distortion_is_normalized_without_losing_original():
    result = SpeechNormalizer().normalize("Görev yerini sınaç")
    assert result.original_text == "Görev yerini sınaç"
    assert result.normalized_text == "Görev yöneticisini aç"
    assert result.confidence >= 0.9
    assert result.corrections
    assert result.ambiguity is False


def test_real_service_request_is_never_rewritten_as_jarvis():
    result = SpeechNormalizer().normalize("servis kaydı aç")
    assert result.normalized_text == "servis kaydı aç"
    assert result.corrections == ()


def test_low_confidence_high_risk_speech_requires_confirmation():
    result = SpeechNormalizer().normalize(
        "bilgisayarı kapat", transcription_confidence=0.54,
        risk=RiskLevel.HIGH,
    )
    assert result.needs_confirmation is True
    assert result.ambiguity is True


def test_low_confidence_read_only_speech_does_not_raise_action_permission():
    result = SpeechNormalizer().normalize(
        "sistem nasıl", transcription_confidence=0.54,
        risk=RiskLevel.LOW,
    )
    assert result.needs_confirmation is False
