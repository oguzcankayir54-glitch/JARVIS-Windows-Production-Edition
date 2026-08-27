"""Speech-to-text via faster-whisper, run locally on this machine.

Nothing leaves the host: the audio is decoded and transcribed by a local
model, so what is said into the microphone never reaches a cloud service —
unlike the answer, which may be routed to a cloud model if the router decides
to. That asymmetry is deliberate (spec §6): raw voice is the most personal
signal in the system and stays put.

``faster-whisper`` is an optional dependency. When it is missing J.A.R.V.I.S.
still starts and still answers typed questions; only the microphone is
switched off, and it says so instead of failing obscurely.

VRAM note: on a 12 GB card a 14B model in Q4 already takes ~9 GB. ``small``
(~0.5 GB) leaves room; ``medium`` (~1.5 GB) is noticeably better at Turkish
but is the point where the two start competing. ``JARVIS_STT_DEVICE=cpu``
sidesteps the question entirely at the cost of speed.
"""
from __future__ import annotations

import re
import tempfile
import threading
from pathlib import Path
from typing import Protocol

#: Kayıt boyutu üst sınırı. Panel ağa açılabildiği için, karşı tarafın
#: gönderdiği veriyi sınırsız belleğe almak kabul edilebilir değil.
#: ~25 MB, opus/aac için birkaç dakikalık konuşmaya karşılık gelir.
MAX_AUDIO_BYTES = 25 * 1024 * 1024

#: Tarayıcıların ürettiği kaplar. Safari mp4/aac, Chrome webm/opus verir;
#: faster-whisper ikisini de (PyAV üzerinden) çözer.
_SUFFIX_BY_TYPE = {
    "audio/webm": ".webm",
    "audio/ogg": ".ogg",
    "audio/mp4": ".mp4",
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/aac": ".aac",
}

_KURULUM_NOTU = (
    "Mikrofon için faster-whisper gerekli:\n"
    "    pip install faster-whisper"
)


class STTError(RuntimeError):
    """Raised with a human-readable Turkish message the caller can show as-is."""


class STTProvider(Protocol):
    name: str
    available: bool

    def transcribe(self, audio: bytes, content_type: str = "") -> str:
        ...


def suffix_for(content_type: str) -> str:
    """File extension matching a browser's recording, ``.webm`` by default.

    The container matters to the decoder, and the browser is the only one who
    knows which it produced — Safari and Chrome disagree.
    """
    base = (content_type or "").split(";")[0].strip().lower()
    return _SUFFIX_BY_TYPE.get(base, ".webm")


class NullSTT:
    """Used when faster-whisper is absent: J.A.R.V.I.S. stays typing-only."""

    name = "yok"
    available = False

    def __init__(self, reason: str = "") -> None:
        self.reason = reason or _KURULUM_NOTU

    def transcribe(self, audio: bytes, content_type: str = "") -> str:
        raise STTError(self.reason)


_CUDA_KURULUM_NOTU = "pip install nvidia-cublas-cu12 nvidia-cudnn-cu12"

#: CTranslate2 CUDA kütüphanesini bulamadığında dönen hatalar.
_CUDA_LIB_IZI = re.compile(
    r"libcublas|libcudnn|libcuda\b|cublas|cudnn|cannot be loaded|"
    r"no kernel image|CUDA (?:driver|runtime|error)",
    re.IGNORECASE,
)


def _cuda_kutuphane_hatasi(exc: BaseException) -> bool:
    """True when a failure is CUDA's libraries missing, not the audio."""
    return bool(_CUDA_LIB_IZI.search(str(exc)))


class _CudaKutuphanesiYok(Exception):
    """Internal marker: retry on CPU rather than reporting failure."""


def _cuda_kutuphanelerini_yukle() -> None:
    """Make pip-installed NVIDIA libraries visible to CTranslate2.

    CTranslate2 opens ``libcublas``/``libcudnn`` by bare name, which only
    works when they sit on the loader's search path. The ``nvidia-*-cu12``
    pip packages install them inside site-packages instead, where the loader
    never looks — and ``LD_LIBRARY_PATH`` cannot be changed from inside a
    running process. Loading them here by absolute path puts them in the
    process, so the later open-by-name finds them already resident.

    Entirely best-effort: without the packages this does nothing and the
    caller falls back to CPU.
    """
    import ctypes
    import glob
    import importlib.util
    import os

    # cuBLAS first: cuDNN links against it.
    for paket in ("nvidia.cublas.lib", "nvidia.cudnn.lib"):
        try:
            spec = importlib.util.find_spec(paket)
        except (ImportError, ValueError, ModuleNotFoundError):
            continue
        if spec is None or not spec.submodule_search_locations:
            continue
        klasor = list(spec.submodule_search_locations)[0]
        for yol in sorted(glob.glob(os.path.join(klasor, "lib*.so*"))):
            try:
                ctypes.CDLL(yol, mode=ctypes.RTLD_GLOBAL)
            except OSError:
                pass  # bir kütüphane açılmazsa diğerleri denensin


def _cuda_var_mi() -> bool:
    """True when CTranslate2 can actually see a GPU.

    Asked of CTranslate2 rather than torch: it is what runs the model, and
    faster-whisper does not pull torch in at all.
    """
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


class WhisperSTT:
    """Local transcription. The model is loaded on first use, not at startup.

    A cold model costs a download (hundreds of MB) plus several seconds of
    load time. Doing that while the panel is starting would look like a hang,
    and would happen even for a session where nobody touches the microphone.
    """

    name = "faster-whisper"

    def __init__(self, model_size: str = "small", device: str = "auto",
                 compute_type: str = "auto", language: str = "tr",
                 beam_size: int = 5, vad_min_silence_ms: int = 350,
                 vad_speech_pad_ms: int = 250,
                 condition_on_previous_text: bool = False,
                 hotwords: str = "", initial_prompt: str = "") -> None:
        self.model_size = model_size
        self.language = language or None
        self.device, self.compute_type = self._resolve(device, compute_type)
        self.available = True
        self.beam_size = max(1, int(beam_size or 1))
        self.vad_min_silence_ms = max(100, int(vad_min_silence_ms or 350))
        self.vad_speech_pad_ms = max(0, int(vad_speech_pad_ms or 250))
        self.condition_on_previous_text = bool(condition_on_previous_text)
        self.hotwords = ", ".join(
            word.strip() for word in (hotwords or "").split(",") if word.strip()
        ) or None
        self.initial_prompt = (initial_prompt or "").strip() or None
        self._model = None
        self._lock = threading.Lock()

    @staticmethod
    def _resolve(device: str, compute_type: str) -> tuple[str, str]:
        device = (device or "auto").strip().lower()
        if device == "auto":
            device = "cuda" if _cuda_var_mi() else "cpu"
        compute_type = (compute_type or "auto").strip().lower()
        if compute_type == "auto":
            # int8_float16 halves the VRAM a float16 model would take, which
            # matters when a 14B model already holds most of the card.
            compute_type = "int8_float16" if device == "cuda" else "int8"
        return device, compute_type

    def _load(self):
        """Load the model once, falling back to CPU rather than dying.

        A CUDA build of CTranslate2 needs cuBLAS and cuDNN present; under WSL
        they are a common thing to be missing. Refusing to transcribe at all
        because the fast path is unavailable would be the wrong trade — slow
        speech recognition still works.
        """
        if self._model is not None:
            return self._model
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise STTError(_KURULUM_NOTU) from exc

        if self.device == "cuda":
            _cuda_kutuphanelerini_yukle()

        try:
            self._model = WhisperModel(self.model_size, device=self.device,
                                       compute_type=self.compute_type)
        except Exception as exc:
            if self.device != "cuda":
                raise STTError(
                    f"Whisper modeli yüklenemedi ({self.model_size}): {exc}"
                ) from exc
            print(f"! Whisper GPU'da başlatılamadı ({exc}); CPU'ya düşülüyor.", flush=True)
            self._cpuya_dus()
            try:
                self._model = WhisperModel(self.model_size, device="cpu",
                                           compute_type="int8")
            except Exception as exc2:
                raise STTError(
                    f"Whisper modeli yüklenemedi ({self.model_size}): {exc2}"
                ) from exc2
        return self._model

    def _cpuya_dus(self) -> None:
        self.device, self.compute_type = "cpu", "int8"
        self._model = None

    def _coz(self, path: str) -> str:
        """One decode attempt on the currently selected device."""
        model = self._load()
        try:
            segments, _ = model.transcribe(
                path,
                language=self.language,
                # Cuts most of the "Altyazı M.K." style hallucinations
                # Whisper produces from silence between words.
                vad_filter=True,
                vad_parameters={
                    "min_silence_duration_ms": self.vad_min_silence_ms,
                    "speech_pad_ms": self.vad_speech_pad_ms,
                },
                beam_size=self.beam_size,
                temperature=0.0,
                condition_on_previous_text=self.condition_on_previous_text,
                hotwords=self.hotwords,
                initial_prompt=self.initial_prompt,
            )
            # The generator is where the work happens, so the join is inside
            # the try — a CUDA failure surfaces here, not at the call above.
            return " ".join(seg.text.strip() for seg in segments).strip()
        except Exception as exc:
            if self.device == "cuda" and _cuda_kutuphane_hatasi(exc):
                raise _CudaKutuphanesiYok(str(exc)) from exc
            raise STTError(f"Ses çözümlenemedi: {exc}") from exc

    def transcribe(self, audio: bytes, content_type: str = "") -> str:
        if not audio:
            raise STTError("Ses kaydı boş.")
        if len(audio) > MAX_AUDIO_BYTES:
            raise STTError(
                f"Kayıt çok büyük ({len(audio) // (1024 * 1024)} MB); "
                f"sınır {MAX_AUDIO_BYTES // (1024 * 1024)} MB."
            )

        # Serialised: one model instance, and two concurrent decodes on the
        # same GPU would only contend for the memory it is trying to save.
        with self._lock:
            path = None
            try:
                with tempfile.NamedTemporaryFile(
                    suffix=suffix_for(content_type), delete=False
                ) as fh:
                    fh.write(audio)
                    path = Path(fh.name)
                try:
                    return self._coz(str(path))
                except _CudaKutuphanesiYok as exc:
                    # CTranslate2 opens libcublas/libcudnn at the first compute,
                    # not when the model is built — so building on the GPU can
                    # succeed and only decoding fails. Falling back at load time
                    # alone never fires; the retry has to live here.
                    print(f"! Whisper GPU'da çözümleyemedi ({exc}); CPU'ya düşülüyor.",
                          flush=True)
                    print(f"  GPU hızı için: {_CUDA_KURULUM_NOTU}", flush=True)
                    self._cpuya_dus()
                    return self._coz(str(path))
            finally:
                # The recording is a voice sample; it does not linger on disk.
                if path is not None:
                    path.unlink(missing_ok=True)


def build_stt(enabled: bool = True, model_size: str = "small", device: str = "auto",
              compute_type: str = "auto", language: str = "tr",
              beam_size: int = 5, vad_min_silence_ms: int = 350,
              vad_speech_pad_ms: int = 250,
              condition_on_previous_text: bool = False,
              hotwords: str = "", initial_prompt: str = "") -> STTProvider:
    """Return a working provider, or :class:`NullSTT` explaining why not."""
    if not enabled:
        return NullSTT("Mikrofon kapalı (JARVIS_STT_ENABLED=false).")
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        return NullSTT()
    return WhisperSTT(model_size, device, compute_type, language,
                      beam_size=beam_size,
                      vad_min_silence_ms=vad_min_silence_ms,
                      vad_speech_pad_ms=vad_speech_pad_ms,
                      condition_on_previous_text=condition_on_previous_text,
                      hotwords=hotwords, initial_prompt=initial_prompt)
