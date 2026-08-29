"""Low-latency local XTTS-v2 speech with the selected Craig voice.

The expensive model is loaded once in a background thread when JARVIS starts,
then kept on the GPU for the lifetime of the process.  Synthesis results are
cached in memory only: repeated status lines play immediately without writing
the user's answers to disk.
"""
from __future__ import annotations

from collections import OrderedDict
import importlib.util
import io
import threading
import wave
from typing import Callable, Iterator

from .tts import TTSError, normalize_for_speech


MODEL_NAME = "tts_models/multilingual/multi-dataset/xtts_v2"
DEFAULT_SPEAKER = "Craig Gutsy"
SAMPLE_RATE = 24000
CHUNK_SIZE = 64 * 1024


def xtts_hazir() -> str:
    """Return an actionable dependency error, or an empty string."""
    missing = [name for name in ("TTS", "torch", "numpy", "scipy")
               if importlib.util.find_spec(name) is None]
    if not missing:
        return ""
    return (
        "Yerel Craig sesi için XTTS bağımlılıkları eksik: "
        + ", ".join(missing)
        + "\n    pip install -e \".[ses-xtts]\""
    )


class XTTSTTS:
    """Persistent local XTTS provider optimized for conversational latency."""

    name = "xtts"
    mime = "audio/wav"

    def __init__(
        self,
        speaker: str = DEFAULT_SPEAKER,
        speed: float = 1.04,
        device: str = "auto",
        cache_size: int = 32,
        preload: bool = True,
        model_name: str = MODEL_NAME,
        *,
        model_factory: Callable[[str, str], object] | None = None,
    ) -> None:
        self.speaker = (speaker or DEFAULT_SPEAKER).strip()
        self.speed = min(1.25, max(0.75, float(speed)))
        self.device = (device or "auto").strip().lower()
        self.cache_size = max(0, min(256, int(cache_size)))
        self.model_name = model_name or MODEL_NAME
        self._model_factory = model_factory
        self._model = None
        self._load_error: Exception | None = None
        self._load_lock = threading.Lock()
        self._inference_lock = threading.Lock()
        self._cache_lock = threading.Lock()
        self._cache: OrderedDict[str, bytes] = OrderedDict()
        self._warm_thread: threading.Thread | None = None
        self._closed = False
        if preload:
            self._warm_thread = threading.Thread(
                target=self._warm_up,
                name="jarvis-xtts-warmup",
                daemon=True,
            )
            self._warm_thread.start()

    @property
    def available(self) -> bool:
        return not self._closed and self._load_error is None

    @property
    def ready(self) -> bool:
        return self._model is not None and self.available

    @property
    def reason(self) -> str:
        if self._closed:
            return "XTTS motoru kapatıldı."
        if self._load_error is not None:
            return f"XTTS modeli yüklenemedi: {self._load_error}"
        return ""

    def _resolved_device(self) -> str:
        if self.device != "auto":
            return self.device
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"

    def _default_factory(self, model_name: str, device: str):
        from TTS.api import TTS
        return TTS(model_name).to(device)

    def _get_model(self):
        if self._closed:
            raise TTSError("XTTS motoru kapatıldı.")
        if self._model is not None:
            return self._model
        with self._load_lock:
            if self._model is not None:
                return self._model
            if self._load_error is not None:
                raise TTSError(f"XTTS modeli yüklenemedi: {self._load_error}")
            try:
                factory = self._model_factory or self._default_factory
                self._model = factory(self.model_name, self._resolved_device())
            except Exception as exc:
                self._load_error = exc
                raise TTSError(f"XTTS modeli yüklenemedi: {exc}") from exc
        return self._model

    def _warm_up(self) -> None:
        """Load weights before the first conversation; never crash the app."""
        try:
            model = self._get_model()
            with self._inference_lock:
                model.tts(
                    text="Efendim, hazırım.", speaker=self.speaker,
                    language="tr", speed=self.speed, split_sentences=False,
                )
        except Exception as exc:
            self._load_error = exc

    def wait_ready(self, timeout: float = 180.0) -> None:
        """Block application startup, never the first spoken conversation."""
        if self._warm_thread is not None:
            self._warm_thread.join(timeout=max(1.0, float(timeout)))
            if self._warm_thread.is_alive():
                raise TTSError("XTTS modeli açılışta zamanında hazırlanamadı.")
        self._get_model()
        if self._load_error is not None:
            raise TTSError(f"XTTS modeli yüklenemedi: {self._load_error}")

    @staticmethod
    def _studio_wav(samples) -> bytes:
        """Fast in-process mastering; no ffmpeg startup on each response."""
        import numpy as np
        from scipy.signal import butter, sosfilt

        audio = np.asarray(samples, dtype=np.float32).reshape(-1)
        if audio.size == 0:
            raise TTSError("XTTS boş ses üretti.")
        audio = np.nan_to_num(audio, copy=False)
        audio -= float(np.mean(audio))

        # Remove rumble and ultrasonic model noise without changing Craig's
        # pitch or formants.  The upper edge stays below the 12 kHz Nyquist.
        sos = butter(2, (68.0, 11_300.0), btype="bandpass",
                     fs=SAMPLE_RATE, output="sos")
        audio = sosfilt(sos, audio).astype(np.float32, copy=False)

        # Gentle studio compression followed by a true-peak safety margin.
        threshold = 10 ** (-14.0 / 20.0)
        magnitude = np.abs(audio)
        over = magnitude > threshold
        audio[over] = np.sign(audio[over]) * (
            threshold + (magnitude[over] - threshold) / 1.8
        )
        peak = float(np.max(np.abs(audio)))
        if peak > 0:
            audio *= 0.87 / peak

        pcm = np.clip(audio * 32767.0, -32768, 32767).astype("<i2")
        target = io.BytesIO()
        with wave.open(target, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(SAMPLE_RATE)
            wav.writeframes(pcm.tobytes())
        return target.getvalue()

    def _cache_get(self, key: str) -> bytes | None:
        with self._cache_lock:
            audio = self._cache.pop(key, None)
            if audio is not None:
                self._cache[key] = audio
            return audio

    def _cache_put(self, key: str, audio: bytes) -> None:
        if not self.cache_size:
            return
        with self._cache_lock:
            self._cache[key] = audio
            self._cache.move_to_end(key)
            while len(self._cache) > self.cache_size:
                self._cache.popitem(last=False)

    def synthesize(self, text: str) -> Iterator[bytes]:
        if self._closed:
            raise TTSError("XTTS motoru kapatıldı.")
        text = normalize_for_speech(text)
        if not text:
            raise TTSError("Seslendirilecek metin boş.")
        key = f"{self.speaker}\0{self.speed:.3f}\0{text}"
        audio = self._cache_get(key)
        if audio is None:
            model = self._get_model()
            try:
                with self._inference_lock:
                    samples = model.tts(
                        text=text,
                        speaker=self.speaker,
                        language="tr",
                        speed=self.speed,
                        split_sentences=True,
                    )
                audio = self._studio_wav(samples)
            except TTSError:
                raise
            except Exception as exc:
                raise TTSError(f"XTTS ses üretemedi: {exc}") from exc
            self._cache_put(key, audio)

        for start in range(0, len(audio), CHUNK_SIZE):
            yield audio[start:start + CHUNK_SIZE]

    def close(self, timeout: float = 10.0) -> None:
        """Release cached audio/model references and best-effort GPU memory."""
        if self._closed:
            return
        self._closed = True
        warm = self._warm_thread
        if warm is not None and warm.is_alive():
            warm.join(timeout=max(0.0, float(timeout)))
        # Never race model disposal with an active synthesis.
        with self._inference_lock:
            self._model = None
        with self._cache_lock:
            self._cache.clear()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass
