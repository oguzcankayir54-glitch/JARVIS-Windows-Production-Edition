"""Text-to-speech via ElevenLabs, streamed for low latency.

The API key lives only in the environment (or a local ``.env``) and is sent
nowhere except api.elevenlabs.io. It is never logged, never written to disk by
J.A.R.V.I.S., and never embedded in a client — a phone app will talk to the
J.A.R.V.I.S. server, which holds the key on its behalf (spec §6).

Audio is streamed rather than downloaded whole: playback can start on the
first chunk instead of waiting for the last one, which is most of the
difference between a reply that feels immediate and one that feels laggy.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Iterator, Protocol

from ..core.asistan import JARVIS
from .soyleyis import okunusa_cevir

_API_ROOT = "https://api.elevenlabs.io/v1"
#: Ses listesi yalnızca v2'de sayfalanıyor; v1 her şeyi tek gövdede döndürür.
_API_ROOT_V2 = "https://api.elevenlabs.io/v2"

#: Players that can read an MP3 stream from stdin, in order of preference.
_PLAYERS = (
    ("ffplay", ["-nodisp", "-autoexit", "-loglevel", "quiet", "-"]),
    ("mpv", ["--no-video", "--really-quiet", "-"]),
    ("mpg123", ["-q", "-"]),
    ("cvlc", ["--play-and-exit", "--intf", "dummy", "-"]),
)


#: Noktalı yazılış TTS'e harf harf okutur; söylenişi düzeltir, yazılışı değil.
_ASISTAN_ADLARI = (
    (re.compile(r"\b" + r"\.?".join(JARVIS.ad.replace(".", "")) + r"\.?", re.IGNORECASE),
     JARVIS.okunus),
)

#: Geriye dönük ad — eski çağrı yerleri ve testler bunu kullanıyor.
_SPELLED_NAME = _ASISTAN_ADLARI[0][0]
#: Modelin ürettiği markdown işaretleri sesli okunduğunda gürültüye dönüşür.
_MARKDOWN_NOISE = re.compile(r"(\*{1,3}|_{2,}|`{1,3}|^#{1,6}\s*)", re.MULTILINE)
_OUTPUT_FORMAT = re.compile(r"^(?:mp3|pcm|ulaw|alaw|opus)_[A-Za-z0-9_]+$")
_RETRYABLE_HTTP = {429, 500, 502, 503, 504}


def normalize_for_speech(text: str) -> str:
    """Prepare written text for the ear rather than the eye.

    The panel keeps the stylised spelling; only what is sent to the synthesiser
    changes. Three things trip a Turkish synthesiser up: a dotted acronym gets
    spelled out letter by letter, markdown markers get read aloud as
    punctuation, and a technical abbreviation gets read as if it were a Turkish
    word — ``BIOS`` comes out "boz". The last one is
    :mod:`jarvis.voice.soyleyis`, and it is worth more than changing voices.
    """
    for desen, okunus in _ASISTAN_ADLARI:
        text = desen.sub(okunus, text)
    text = _MARKDOWN_NOISE.sub("", text)
    text = okunusa_cevir(text)
    return re.sub(r"[ \t]{2,}", " ", text).strip()


#: 401 hem geçersiz anahtar hem tükenmiş kota için dönüyor; gövde ayırt eder.
_KOTA_IZI = re.compile(r"quota|credits remaining|exceeds your", re.IGNORECASE)


class TTSError(RuntimeError):
    """Raised with a human-readable Turkish message the CLI can print as-is."""


class TTSProvider(Protocol):
    name: str
    available: bool
    #: Uretilen sesin turu. Saglayicilar farkli bicimler veriyor
    #: (ElevenLabs MP3, Piper WAV) ve sunucu bunu tarayiciya dogru
    #: bildirmek zorunda; sabit bir tur yazmak ikinci saglayicida bozulurdu.
    mime: str

    def synthesize(self, text: str) -> Iterator[bytes]:
        ...


class NullTTS:
    """Used when speech is unconfigured: J.A.R.V.I.S. stays text-only."""

    name = "yok"
    available = False
    mime = "audio/mpeg"

    def __init__(self, reason: str = "") -> None:
        self.reason = reason

    def synthesize(self, text: str) -> Iterator[bytes]:
        raise TTSError(self.reason or (
            "Ses yapılandırılmamış. Yerel Craig sesi için:\n"
            "    pip install -e \".[ses-xtts]\"\n"
            "    JARVIS_TTS_PROVIDER=xtts\n"
            "ElevenLabs yedeği için JARVIS_TTS_PROVIDER=elevenlabs, "
            "ELEVENLABS_API_KEY ve ELEVENLABS_VOICE_ID ayarlanabilir."
        ))


class ElevenLabsTTS:
    """Production ElevenLabs provider used by every J.A.R.V.I.S. surface.

    The provider deliberately has no dependency on the ElevenLabs SDK: the
    official HTTP streaming endpoint is small, stable, and keeping the key in
    this server-side module avoids accidentally shipping it inside a GUI.
    """

    name = "elevenlabs"
    mime = "audio/mpeg"

    def __init__(
        self,
        api_key: str,
        voice_id: str,
        model_id: str = "eleven_flash_v2_5",
        timeout: float = 30.0,
        speed: float = 1.0,
        *,
        output_format: str = "mp3_44100_128",
        language_code: str = "tr",
        stability: float = 0.50,
        similarity_boost: float = 0.75,
        style: float = 0.0,
        speaker_boost: bool = True,
        max_retries: int = 2,
        chunk_size: int = 8192,
    ) -> None:
        if not api_key:
            raise TTSError("ELEVENLABS_API_KEY boş.")
        if not voice_id:
            raise TTSError("ELEVENLABS_VOICE_ID boş.")
        output_format = (output_format or "mp3_44100_128").strip()
        if not _OUTPUT_FORMAT.fullmatch(output_format):
            raise TTSError(f"Geçersiz ElevenLabs output formatı: {output_format}")

        self._api_key = api_key
        self.voice_id = voice_id.strip()
        self.model_id = (model_id or "eleven_flash_v2_5").strip()
        self.output_format = output_format
        self.language_code = (language_code or "").strip().lower()
        self.timeout = max(1.0, float(timeout))
        # ElevenLabs resmi API aralıkları. Kötü .env değeri konuşma anında 422
        # üretmesin; burada güvenli sınırda tutuluyor.
        self.speed = min(1.2, max(0.7, float(speed)))
        self.stability = min(1.0, max(0.0, float(stability)))
        self.similarity_boost = min(1.0, max(0.0, float(similarity_boost)))
        self.style = min(1.0, max(0.0, float(style)))
        self.speaker_boost = bool(speaker_boost)
        self.max_retries = max(0, int(max_retries))
        self.chunk_size = max(1024, min(1 << 16, int(chunk_size)))
        self.available = True

    def _voice_settings(self) -> dict[str, object]:
        settings: dict[str, object] = {
            "stability": self.stability,
            "style": self.style,
            "speed": self.speed,
        }
        # Eleven v3 does not expose Similarity Boost or Speaker Boost. Sending
        # them anyway makes a future API validation change a runtime failure.
        if not self.model_id.startswith("eleven_v3"):
            settings["similarity_boost"] = self.similarity_boost
            settings["use_speaker_boost"] = self.speaker_boost
        return settings

    def _payload(self, text: str) -> bytes:
        body: dict[str, object] = {
            "text": text,
            "model_id": self.model_id,
            "voice_settings": self._voice_settings(),
        }
        # multilingual_v2 detects language from text and does not support the
        # language_code parameter; newer conversational/Flash models do.
        if self.language_code and self.model_id != "eleven_multilingual_v2":
            body["language_code"] = self.language_code
        return json.dumps(body, ensure_ascii=False).encode("utf-8")

    def _speech_request(self, text: str) -> urllib.request.Request:
        voice = urllib.parse.quote(self.voice_id, safe="")
        query = urllib.parse.urlencode({"output_format": self.output_format})
        return urllib.request.Request(
            f"{_API_ROOT}/text-to-speech/{voice}/stream?{query}",
            data=self._payload(text),
            headers={
                "xi-api-key": self._api_key,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
                "User-Agent": "JARVIS/2.0.1",
            },
        )

    def synthesize(self, text: str) -> Iterator[bytes]:
        """Yield ElevenLabs audio chunks as soon as the API produces them.

        429 and transient 5xx failures are retried with a short exponential
        backoff. Authentication, bad voice IDs and invalid requests fail
        immediately so configuration mistakes never look like a slow network.
        """
        text = normalize_for_speech(text)
        if not text:
            return

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            req = self._speech_request(text)
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    while chunk := resp.read(self.chunk_size):
                        yield chunk
                return
            except urllib.error.HTTPError as exc:
                last_error = exc
                if exc.code not in _RETRYABLE_HTTP or attempt >= self.max_retries:
                    raise TTSError(self._explain(exc)) from exc
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    raise TTSError(f"ElevenLabs'e ulaşılamadı: {exc}") from exc
            time.sleep(min(1.5, 0.25 * (2 ** attempt)))

        # Defensive only: every loop path either returns or raises.
        raise TTSError(f"ElevenLabs ses üretimi tamamlanamadı: {last_error}")

    def _get_json(self, url: str) -> dict:
        req = urllib.request.Request(url, headers={"xi-api-key": self._api_key})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise TTSError(self._explain(exc)) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise TTSError(f"ElevenLabs'e ulaşılamadı: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise TTSError(f"ElevenLabs beklenmeyen bir yanıt verdi: {exc}") from exc

    def voice_info(self, voice_id: str) -> dict[str, str]:
        """Look one voice up by id — the cheap way to verify a setup.

        Asking for the single voice that is actually configured settles both
        questions at once: a bad key answers 401, a wrong id answers 404. The
        alternative, listing the account's voices and searching, downloads a
        response that has grown large enough to look like a hang.
        """
        # safe="" so a stray slash cannot walk the id out into another path.
        body = self._get_json(f"{_API_ROOT}/voices/{urllib.parse.quote(voice_id, safe='')}")
        return {"voice_id": body.get("voice_id", voice_id), "name": body.get("name", "")}

    def quota(self) -> dict[str, int | str] | None:
        """Characters left this period, or None when the key may not ask.

        Worth checking before a conversation rather than during one: a valid
        key with an exhausted quota fails at synthesis time with the same 401
        a bad key returns, which is a confusing place to discover it. Newer
        scoped keys can be denied this endpoint, and that is not a fault —
        hence None rather than an error.
        """
        try:
            body = self._get_json(f"{_API_ROOT}/user/subscription")
        except TTSError:
            return None
        try:
            used = int(body["character_count"])
            limit = int(body["character_limit"])
        except (KeyError, TypeError, ValueError):
            return None
        return {"used": used, "limit": limit, "left": max(0, limit - used),
                "tier": str(body.get("tier", ""))}

    def voices(self, limit: int = 100) -> list[dict[str, str]]:
        """List the account's voices — used to find a voice id.

        Paged deliberately: the unpaged v1 endpoint can return the whole
        shared library, which is minutes of transfer for a list nobody reads
        past the first screen of.
        """
        found: list[dict[str, str]] = []
        token = ""
        while len(found) < limit:
            query = {"page_size": str(min(100, limit - len(found)))}
            if token:
                query["next_page_token"] = token
            body = self._get_json(f"{_API_ROOT_V2}/voices?{urllib.parse.urlencode(query)}")
            found += [
                {"voice_id": v.get("voice_id", ""), "name": v.get("name", "")}
                for v in body.get("voices", [])
            ]
            token = body.get("next_page_token") or ""
            if not body.get("has_more") or not token:
                break
        return found

    @staticmethod
    def _explain(exc: urllib.error.HTTPError) -> str:
        """Turn an HTTP status into something the user can act on.

        The API explains most failures in its response body; discarding that
        turns a fixable problem into a bare status code, so it is read and
        appended whenever it says something.
        """
        detail = ElevenLabsTTS._read_detail(exc)
        suffix = f" Sunucu mesajı: {detail}" if detail else ""

        if exc.code == 401:
            # ElevenLabs returns 401 for an exhausted quota as well as a bad
            # key; pointing at the key would send the user to fix the wrong
            # thing, so the body decides which message applies.
            if _KOTA_IZI.search(detail):
                return ("ElevenLabs krediniz bitti. Anahtarınız geçerli — aylık kota "
                        f"tükenmiş. Kota yenilenene kadar ses çalışmaz.{suffix}")
            return ("ElevenLabs API anahtarı geçersiz (401). .env içindeki "
                    f"ELEVENLABS_API_KEY'i kontrol edin.{suffix}")
        if exc.code == 404:
            return ("Voice ID bulunamadı (404). 'jarvis-ses --sesler' ile kendi ses "
                    f"kimliklerinizi listeleyin.{suffix}")
        if exc.code == 400:
            return ("ElevenLabs isteği reddetti (400). Genellikle anahtarda görünmez bir "
                    "karakter (kopyalarken bulaşan boşluk/satır sonu) veya hatalı bir "
                    f"parametre olur.{suffix}")
        if exc.code == 422:
            return f"ElevenLabs isteği reddetti (422). Model kimliği veya metin geçersiz olabilir.{suffix}"
        if exc.code == 429:
            return f"ElevenLabs kota/hız sınırı aşıldı (429). Bir süre sonra tekrar deneyin.{suffix}"
        return f"ElevenLabs hatası (HTTP {exc.code}).{suffix}"

    @staticmethod
    def _read_detail(exc: urllib.error.HTTPError) -> str:
        """Best-effort read of the API's own explanation."""
        try:
            body = exc.read().decode("utf-8", errors="replace").strip()
        except Exception:
            return ""
        if not body:
            return ""
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return body[:300]
        # ElevenLabs nests the message under detail, sometimes as a dict.
        detail = data.get("detail", data) if isinstance(data, dict) else data
        if isinstance(detail, dict):
            detail = detail.get("message") or detail.get("status") or detail
        return str(detail)[:300]


def find_player() -> tuple[str, list[str]] | None:
    """First available stdin-capable audio player, or None."""
    for binary, args in _PLAYERS:
        if shutil.which(binary):
            return binary, args
    return None


def play_stream(chunks: Iterator[bytes]) -> bool:
    """Pipe audio chunks straight into a player as they arrive.

    Returns False when no player is installed, so the caller can fall back to
    saving a file instead of losing the audio.
    """
    player = find_player()
    if player is None:
        return False
    binary, args = player
    proc = subprocess.Popen([binary, *args], stdin=subprocess.PIPE,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        assert proc.stdin is not None
        for chunk in chunks:
            proc.stdin.write(chunk)
        proc.stdin.close()
        proc.wait(timeout=120)
    except (BrokenPipeError, subprocess.TimeoutExpired):
        proc.kill()
    finally:
        if proc.poll() is None:
            proc.kill()
    return True


def save_stream(chunks: Iterator[bytes], path: Path | str) -> Path:
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as fh:
        for chunk in chunks:
            fh.write(chunk)
    return target


def build_tts(api_key: str | None, voice_id: str | None, model_id: str,
              speed: float = 1.0, provider: str = "", piper_voice: str = "",
              piper_binary: str = "piper", piper_cuda: bool = False,
              data_dir: str = "~/.jarvis", edge_voice: str = "",
              edge_ca: str = "", output_format: str = "mp3_44100_128",
              language_code: str = "tr", stability: float = 0.50,
              similarity_boost: float = 0.75, style: float = 0.0,
              speaker_boost: bool = True, timeout: float = 30.0,
              max_retries: int = 2, xtts_speaker: str = "Craig Gutsy",
              xtts_speed: float = 1.04, xtts_device: str = "auto",
              xtts_preload: bool = True, xtts_cache_size: int = 32,
              xtts_model: str = "tts_models/multilingual/multi-dataset/xtts_v2",
              ) -> TTSProvider:
    """Pick a speech provider.

    ``provider`` decides explicitly. Left empty the order is: a configured
    ElevenLabs key, then Edge, then Piper — best-sounding first among the ones
    that are actually usable. Edge outranks Piper because the difference is
    measured, not felt: 0.82 against 0.65 on the round-trip intelligibility
    test in :mod:`jarvis.voice.soyleyis`.

    Anyone who needs speech to stay on the machine says so once
    (``JARVIS_TTS_PROVIDER=piper``) and nothing else changes.
    """
    secim = (provider or "").strip().lower()

    if secim in ("yok", "kapali", "none", "off"):
        return NullTTS("Ses kapalı (JARVIS_TTS_PROVIDER=yok).")

    if secim in ("xtts", "craig", "yerel-xtts"):
        from .xtts import XTTSTTS, xtts_hazir
        eksik = xtts_hazir()
        if eksik:
            return NullTTS(eksik)
        return XTTSTTS(
            speaker=xtts_speaker, speed=xtts_speed, device=xtts_device,
            preload=xtts_preload, cache_size=xtts_cache_size,
            model_name=xtts_model,
        )

    if secim in ("edge", "microsoft", "edge-tts"):
        from .edge import EdgeTTS, edge_hazir
        eksik = edge_hazir()
        if eksik:
            return NullTTS(eksik)
        return EdgeTTS(edge_voice, speed=speed, ca_bundle=edge_ca)

    anahtarsiz = not secim and not (api_key and voice_id)

    if anahtarsiz:
        # Anahtar yok: once Edge, sonra Piper. Edge kurulu degilse asagi
        # dusuyor ve Piper'in kendi mesaji donuyor — kurulmasi gereken sey o.
        from .edge import EdgeTTS, edge_hazir
        if not edge_hazir():
            return EdgeTTS(edge_voice, speed=speed, ca_bundle=edge_ca)

    if secim == "piper" or anahtarsiz:
        # Yerel import: piper.py bu modulu iceri aliyor, ustte import etmek
        # dairesel olurdu.
        from .piper import PiperTTS, piper_hazir, piper_modeli
        model = piper_modeli(piper_voice, data_dir)
        # Yetenek burada denetleniyor, ilk cumlede degil. Kurulu olmayan bir
        # Piper "ses hazir" derse panel calismayan bir dugme gosteriyor ve
        # hata konusmanin ortasinda cikiyor — kamera katmani ayni hatayi
        # yapmisti, ayni sekilde cozuluyor.
        eksik = piper_hazir(model, piper_binary)
        if eksik:
            return NullTTS(eksik)
        return PiperTTS(model, binary=piper_binary, speed=speed, cuda=piper_cuda)

    if secim in ("elevenlabs", "11labs", ""):
        if not api_key or not voice_id:
            return NullTTS(
                "ElevenLabs seçildi ama ELEVENLABS_API_KEY / "
                "ELEVENLABS_VOICE_ID eksik."
            )
        return ElevenLabsTTS(
            api_key, voice_id, model_id, speed=speed, timeout=timeout,
            output_format=output_format, language_code=language_code,
            stability=stability, similarity_boost=similarity_boost,
            style=style, speaker_boost=speaker_boost, max_retries=max_retries,
        )

    return NullTTS(f"Bilinmeyen ses sağlayıcısı: {provider}. "
                   "Seçenekler: xtts | edge | piper | elevenlabs | yok")


def tts_from_config(cfg) -> TTSProvider:
    """Build the provider a :class:`~jarvis.config.Config` describes.

    Four callers were passing the same eight arguments by hand and had begun
    to drift apart; a new setting had to be added in four places to take
    effect anywhere. One reading of the config, one place to change.
    """
    return build_tts(
        cfg.elevenlabs_api_key, cfg.elevenlabs_voice_id, cfg.elevenlabs_model_id,
        cfg.elevenlabs_speed, provider=cfg.tts_provider,
        piper_voice=cfg.piper_voice, piper_binary=cfg.piper_binary,
        piper_cuda=cfg.piper_cuda, data_dir=str(cfg.data_dir),
        edge_voice=getattr(cfg, "edge_voice", ""),
        edge_ca=getattr(cfg, "edge_ca", ""),
        output_format=getattr(cfg, "elevenlabs_output_format", "mp3_44100_128"),
        language_code=getattr(cfg, "elevenlabs_language_code", "tr"),
        stability=getattr(cfg, "elevenlabs_stability", 0.50),
        similarity_boost=getattr(cfg, "elevenlabs_similarity_boost", 0.75),
        style=getattr(cfg, "elevenlabs_style", 0.0),
        speaker_boost=getattr(cfg, "elevenlabs_speaker_boost", True),
        timeout=getattr(cfg, "elevenlabs_timeout", 30.0),
        max_retries=getattr(cfg, "elevenlabs_max_retries", 2),
        xtts_speaker=getattr(cfg, "xtts_speaker", "Craig Gutsy"),
        xtts_speed=getattr(cfg, "xtts_speed", 1.04),
        xtts_device=getattr(cfg, "xtts_device", "auto"),
        xtts_preload=getattr(cfg, "xtts_preload", True),
        xtts_cache_size=getattr(cfg, "xtts_cache_size", 32),
        xtts_model=getattr(
            cfg, "xtts_model", "tts_models/multilingual/multi-dataset/xtts_v2"),
    )
