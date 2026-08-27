"""Central configuration for J.A.R.V.I.S.

Settings come from environment variables (optionally loaded from a local
``.env`` file). Secrets such as API keys are never hard-coded and never
written to the repository — see ``.env.example`` for the template.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .core.asistan import Asistan, asistan_bul


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (no external dependency).

    Only sets keys that are not already present in the environment, so real
    environment variables always win over the file.

    Read as ``utf-8-sig`` rather than ``utf-8`` because this file is often
    edited from Windows. Notepad can save a UTF-8 BOM, which lands invisibly
    on the *first* line — turning ``ELEVENLABS_API_KEY`` into
    ``﻿ELEVENLABS_API_KEY`` so it never matches. The failure is silent
    and looks exactly like "the key was never set", which is the worst way to
    lose an afternoon. ``utf-8-sig`` strips a BOM when present and behaves
    identically when it is not.
    """
    if not path.is_file():
        return
    # errors="replace": a key mangled by a bad paste should surface as a
    # rejected credential, not as a crash before J.A.R.V.I.S. even starts.
    metin = path.read_text(encoding="utf-8-sig", errors="replace")
    for raw in metin.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _float(name: str, default: float) -> float:
    """Read a float setting without letting a typo take the app down.

    A Turkish keyboard produces a comma for the decimal separator, so "0,96"
    is an easy thing to write; bare float() would raise and stop J.A.R.V.I.S.
    from starting at all. The comma is accepted, and anything still unparsable
    falls back to the default with a warning rather than crashing.
    """
    raw = _oku(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw.strip().replace(",", "."))
    except ValueError:
        print(f"! {name} değeri okunamadı ({raw!r}); varsayılan {default} kullanılıyor.")
        return default


def _bool(name: str, default: bool) -> bool:
    val = _oku(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on", "evet"}


def _oku(name: str) -> str | None:
    """Bir ayarı ortamdan oku.

    Bir dönem burada iki önek vardı (``JARVIS_`` ve ``FRIDAY_``) ve hangi
    ayarın paylaşıldığı, hangisinin kimliğe bağlı olduğu ayrı ayrı
    yazılmak zorundaydı. İkinci asistan kaldırıldı; tek önek kaldı.
    """
    return os.getenv(name)


def _env(name: str, default: str = "") -> Callable[[], str]:
    """Lazy env reader for a dataclass default.

    Every env-backed field must use ``default_factory``: a plain
    ``os.getenv(...)`` default is evaluated once at class-definition time, so
    it would freeze before ``load_config()`` has read ``.env`` — and the file
    would silently do nothing.
    """
    def _al() -> str:
        deger = _oku(name)
        return default if deger is None else deger

    return _al


def _env_opt(name: str) -> Callable[[], str | None]:
    return lambda: _oku(name)


@dataclass
class Config:
    """Runtime configuration snapshot."""

    profile: str = field(default_factory=_env("JARVIS_PROFILE", "custom"))

    # --- paths ---
    data_dir: Path = field(default_factory=lambda: Path(
        _oku("JARVIS_DATA_DIR") or asistan_bul().veri_klasoru).expanduser())

    # --- LLM ---
    llm_provider: str = field(default_factory=_env("JARVIS_LLM_PROVIDER", "mock"))  # mock | ollama
    ollama_host: str = field(default_factory=_env("JARVIS_OLLAMA_HOST", "http://localhost:11434"))
    ollama_model: str = field(default_factory=_env("JARVIS_OLLAMA_MODEL", "qwen2.5:14b-instruct"))
    # Empty disables model fallback. Production profile enables an explicit
    # smaller model; keeping the generic default empty avoids surprise pulls.
    ollama_fallback_model: str = field(default_factory=_env("JARVIS_OLLAMA_FALLBACK_MODEL", ""))
    ollama_max_retries: int = field(
        default_factory=lambda: max(0, int(_float("JARVIS_OLLAMA_MAX_RETRIES", 1))))
    ollama_circuit_cooldown: float = field(
        default_factory=lambda: max(1.0, _float("JARVIS_OLLAMA_CIRCUIT_COOLDOWN", 30.0)))
    #: Bağlam penceresi. Yazılmazsa Ollama'nın varsayılanı geçerli olur ve
    #: o varsayılan ölçülen ilk turumuzdan küçük — gerekçe ve bellek hesabı
    #: OllamaProvider.VARSAYILAN_NUM_CTX içinde.
    ollama_num_ctx: int = field(
        default_factory=lambda: int(_float("JARVIS_OLLAMA_NUM_CTX", 8192)))
    # Qwen3/3.5 düşünme kipinde kısa bir soruda bile yüzlerce görünmez token
    # üretebilir. Teknik asistanın günlük kipi doğrudan cevap verir; isteyen
    # üretim profilinde açıkça etkinleştirebilir.
    ollama_think: bool = field(default_factory=lambda: _bool("JARVIS_OLLAMA_THINK", False))
    ollama_num_predict: int = field(
        default_factory=lambda: max(32, int(_float("JARVIS_OLLAMA_NUM_PREDICT", 512))))
    ollama_keep_alive: str = field(default_factory=_env("JARVIS_OLLAMA_KEEP_ALIVE", "30m"))

    # --- voice ---
    elevenlabs_api_key: str | None = field(default_factory=_env_opt("ELEVENLABS_API_KEY"))
    elevenlabs_voice_id: str | None = field(default_factory=_env_opt("ELEVENLABS_VOICE_ID"))
    # J.A.R.V.I.S. gerçek zamanlı bir asistan olduğu için Flash v2.5 varsayılan:
    # ElevenLabs da konuşma/agent senaryoları için v3 yerine düşük gecikmeli
    # Flash v2.5'i öneriyor. Sinematik/en yüksek ifade için ELEVENLABS_MODEL_ID=eleven_v3.
    elevenlabs_model_id: str = field(default_factory=_env("ELEVENLABS_MODEL_ID", "eleven_flash_v2_5"))
    elevenlabs_output_format: str = field(
        default_factory=_env("ELEVENLABS_OUTPUT_FORMAT", "mp3_44100_128"))
    elevenlabs_language_code: str = field(default_factory=_env("ELEVENLABS_LANGUAGE_CODE", "tr"))
    elevenlabs_stability: float = field(default_factory=lambda: _float("ELEVENLABS_STABILITY", 0.50))
    elevenlabs_similarity_boost: float = field(
        default_factory=lambda: _float("ELEVENLABS_SIMILARITY_BOOST", 0.75))
    elevenlabs_style: float = field(default_factory=lambda: _float("ELEVENLABS_STYLE", 0.0))
    elevenlabs_speaker_boost: bool = field(
        default_factory=lambda: _bool("ELEVENLABS_SPEAKER_BOOST", True))
    elevenlabs_timeout: float = field(default_factory=lambda: _float("ELEVENLABS_TIMEOUT", 30.0))
    elevenlabs_max_retries: int = field(
        default_factory=lambda: max(0, int(_float("ELEVENLABS_MAX_RETRIES", 2))))
    # Konuşma hızı, her sağlayıcı için ortak: 1.0 normal, düşük = daha yavaş.
    # Eskiden 0.96 idi ve "çok yavaş" şikâyetinin bir parçasıydı. Yukarı
    # çekmek de çözüm değil: ölçümde +12% hız anlaşılırlığı 0.82'den 0.76'ya
    # düşürüyor. Doğal hız, doğru okunuşla birlikte (bkz. soyleyis.py).
    elevenlabs_speed: float = field(default_factory=lambda: _float("ELEVENLABS_SPEED", 1.0))
    voice_enabled: bool = field(default_factory=lambda: _bool("JARVIS_VOICE_ENABLED", False))
    # edge | piper | elevenlabs | yok. Boş bırakılırsa sıra: ElevenLabs
    # anahtarı varsa o, yoksa Edge, o da yoksa Piper.
    #   edge       — ücretsiz, anahtarsız, en anlaşılır Türkçe; ama çevrimiçi
    #   piper      — ücretsiz ve tamamen yerel; belirgin biçimde daha bozuk
    #   elevenlabs — en iyi, ama karakter başına ücretli
    tts_provider: str = field(default_factory=_env("JARVIS_TTS_PROVIDER", "elevenlabs"))
    #: Edge sesi. Boş bırakılırsa kimlikteki varsayılan (bkz. asistan.py).
    edge_voice: str = field(
        default_factory=lambda: _oku("JARVIS_EDGE_VOICE") or asistan_bul().ses)
    # Eller serbest sohbette onaysız çalışabilen en yüksek risk.
    #
    # Varsayılan "medium", yani yazarken olduğu gibi: MEDIUM zaten "görünür
    # ve geri alınabilir" demek — "YouTube aç" bu seviyede, ve mikrofondan
    # söylenince çalışmaması istenen şeyin tam tersi olurdu. Yıkıcı olan her
    # şey HIGH/CRITICAL, o da panelde reddediliyor.
    #
    # Odada başkaları konuşuyorsa "low" yapın: o zaman yalnızca OKUYAN
    # araçlar sesle çalışır, geri kalanı reddedilir.
    sesli_taban: str = field(default_factory=_env("JARVIS_SESLI_TABAN", "medium"))
    # TLS'i kendi sertifikasıyla açan bir vekilin arkasındaysanız CA paketi.
    edge_ca: str = field(default_factory=_env("JARVIS_EDGE_CA", ""))
    piper_voice: str = field(default_factory=_env("JARVIS_PIPER_VOICE", "tr_TR-dfki-medium"))
    piper_binary: str = field(default_factory=_env("JARVIS_PIPER_BIN", "piper"))
    piper_cuda: bool = field(default_factory=lambda: _bool("JARVIS_PIPER_CUDA", False))

    # Sampling. Ollama's own default is 0.8 — good for prose, too loose for a
    # technical assistant, and the usual cause of mangled Turkish inflection.
    temperature: float = field(default_factory=lambda: _float("JARVIS_TEMPERATURE", 0.35))
    top_p: float = field(default_factory=lambda: _float("JARVIS_TOP_P", 0.9))
    repeat_penalty: float = field(default_factory=lambda: _float("JARVIS_REPEAT_PENALTY", 1.1))

    # --- internet ---
    # On by default: a technician's questions are often about parts, prices
    # and error messages that no local model can know. Fetched text is
    # labelled as data, and local/private addresses are refused outright —
    # see jarvis/internet/guvenlik.py for why that matters.
    web_enabled: bool = field(default_factory=lambda: _bool("JARVIS_WEB_ENABLED", True))
    # Optional. The key-free path scrapes DuckDuckGo and gets challenged from
    # some networks; a key removes that failure mode entirely.
    brave_api_key: str = field(default_factory=_env("JARVIS_BRAVE_API_KEY", ""))

    # --- knowledge base (RAG) ---
    # Embeddings run through the same local Ollama server as the model, so no
    # text leaves the machine. bge-m3 is the default because it is genuinely
    # multilingual: an English-trained embedder scores Turkish questions
    # against Turkish notes badly enough to make retrieval feel broken.
    rag_embed_model: str = field(default_factory=_env("JARVIS_RAG_EMBED_MODEL", "bge-m3"))
    rag_embed_enabled: bool = field(default_factory=lambda: _bool("JARVIS_RAG_EMBED_ENABLED", True))
    #: Bağlama kaç parça girsin. Fazlası asıl soruyu bastırır.
    rag_limit: int = field(default_factory=lambda: int(_float("JARVIS_RAG_LIMIT", 5)))

    # --- camera (local vision) ---
    # Off by default: a camera in a workshop sees customers and couriers, and
    # that should be a deliberate act rather than something that starts itself.
    vision_enabled: bool = field(default_factory=lambda: _bool("JARVIS_VISION_ENABLED", False))
    object_vision_enabled: bool = field(default_factory=lambda: _bool("JARVIS_OBJECT_VISION_ENABLED", False))
    ocr_enabled: bool = field(default_factory=lambda: _bool("JARVIS_OCR_ENABLED", False))
    face_recognition_enabled: bool = field(default_factory=lambda: _bool("JARVIS_FACE_RECOGNITION_ENABLED", False))

    # --- microphone (local speech-to-text) ---
    stt_enabled: bool = field(default_factory=lambda: _bool("JARVIS_STT_ENABLED", True))
    # tiny · base · small · medium · large-v3 — bigger is more accurate and
    # heavier. On a 12 GB card shared with a 14B model, "small" leaves room.
    stt_model: str = field(default_factory=_env("JARVIS_STT_MODEL", "small"))
    stt_device: str = field(default_factory=_env("JARVIS_STT_DEVICE", "auto"))       # auto|cuda|cpu
    stt_compute_type: str = field(default_factory=_env("JARVIS_STT_COMPUTE", "auto"))
    stt_language: str = field(default_factory=_env("JARVIS_STT_LANGUAGE", "tr"))
    # Whisper decode tuning. Conservative defaults: better Turkish accuracy
    # without materially increasing VRAM usage.
    stt_beam_size: int = field(default_factory=lambda: int(_float("JARVIS_STT_BEAM_SIZE", 5)))
    stt_vad_min_silence_ms: int = field(default_factory=lambda: int(_float("JARVIS_STT_VAD_MIN_SILENCE_MS", 350)))
    stt_vad_speech_pad_ms: int = field(default_factory=lambda: int(_float("JARVIS_STT_VAD_SPEECH_PAD_MS", 250)))
    stt_condition_previous: bool = field(default_factory=lambda: _bool("JARVIS_STT_CONDITION_PREVIOUS", False))
    stt_hotwords: str = field(default_factory=_env(
        "JARVIS_STT_HOTWORDS",
        "Jarvis,J.A.R.V.I.S.,Oğuz,NVIDIA,Zotac,Ollama,Qwen,BIOS,UEFI,VRAM,SSD,NVMe",
    ))
    stt_initial_prompt: str = field(default_factory=_env(
        "JARVIS_STT_INITIAL_PROMPT",
        "Türkçe teknik servis konuşması. Asistanın adı Jarvis. Söylenen özel adları, "
        "model numaralarını, harfleri ve sayıları değiştirmeden yaz.",
    ))

    # --- conversation/context safety ---
    # Keep recent conversational state bounded so Ollama never has to silently
    # discard the oldest system/persona messages. Dynamic system blocks are
    # rebuilt every turn and are always preserved.
    history_max_messages: int = field(default_factory=lambda: int(_float("JARVIS_HISTORY_MAX_MESSAGES", 24)))
    # Approximate character budget for messages. This sits below an 8192-token
    # model window so tool schemas and the generated answer still have room.
    context_max_chars: int = field(default_factory=lambda: int(_float("JARVIS_CONTEXT_MAX_CHARS", 18000)))
    tool_result_max_chars: int = field(default_factory=lambda: int(_float("JARVIS_TOOL_RESULT_MAX_CHARS", 12000)))

    @property
    def voice_configured(self) -> bool:
        return bool(self.elevenlabs_api_key and self.elevenlabs_voice_id)

    def masked_key(self) -> str:
        """Key fingerprint safe to print: enough to identify, not to use."""
        key = self.elevenlabs_api_key or ""
        if not key:
            return "(yok)"
        return f"{key[:4]}…{key[-4:]} ({len(key)} karakter)" if len(key) > 12 else "(çok kısa?)"

    # --- security ---
    # When True, HIGH/CRITICAL tools auto-deny instead of prompting (useful
    # for headless/automated runs). Default False = interactive approval.
    non_interactive: bool = field(default_factory=lambda: _bool("JARVIS_NON_INTERACTIVE", False))
    # Max agent tool-call iterations before forcing a final answer.
# Bir turda modele gosterilen en fazla arac. 0 = sinirsiz.
    #
    # Olculdu: qwen2.5:3b'ye 26 arac semasi gonderildiginde 5000 karakterlik
    # sistem istemi bastiriliyor — model Ingilizce cevap veriyor, kimligi
    # unutuyor ve "cpu sicakligi" icin run_terminal_command seciyor. Ayni
    # soru 6 aracla dogru cevaplaniyor. Buyuk modellerde gerekmiyor: 0 yapin.
    arac_siniri: int = field(default_factory=lambda: int(_float("JARVIS_ARAC_SINIRI", 8)))
    max_agent_steps: int = field(default_factory=lambda: int(_float("JARVIS_MAX_AGENT_STEPS", 6)))

    # Request tracing keeps raw user text off disk by default.  Enable only on
    # a development machine where that privacy trade-off is intentional.
    trace_user_text: bool = field(default_factory=lambda: _bool("JARVIS_TRACE_USER_TEXT", False))

    @property
    def audit_log_path(self) -> Path:
        return self.data_dir / "audit.log.jsonl"

    @property
    def request_trace_log_path(self) -> Path:
        return self.data_dir / "requests.log.jsonl"

    @property
    def memory_db_path(self) -> Path:
        return self.data_dir / "memory.sqlite3"

    @property
    def knowledge_db_path(self) -> Path:
        """The knowledge base lives in its own file, apart from memory.

        Memory is small, precious and irreplaceable — what the owner told
        J.A.R.V.I.S. about themselves. The index is large and rebuildable from
        the sources at any time. Keeping them apart means the index can be
        deleted and rebuilt without ever putting memory at risk.
        """
        return self.data_dir / "bilgi.sqlite3"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)


def load_config() -> Config:
    """Load ``.env`` (if present) then build a :class:`Config`."""
    _load_dotenv(Path.cwd() / ".env")
    cfg = Config()
    cfg.ensure_dirs()
    return cfg
