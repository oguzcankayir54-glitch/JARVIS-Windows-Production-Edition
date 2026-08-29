"""Ollama-backed LLM provider (local inference).

Talks to an Ollama server's ``/api/chat`` endpoint using only the standard
library. Tool-calling is supported by models that emit ``tool_calls``; if the
model returns plain text, that text is used as the answer.

Not exercised in the container (no Ollama/GPU here) — the mock provider covers
the tested path. On a real workstation set ``JARVIS_LLM_PROVIDER=ollama``.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Iterator

from .base import LLMResponse, Message, ToolCall
from .errors import ErrorType, LLMProviderError
from ..core.reasoning import profile_for


class OllamaProvider:
    name = "ollama"

    #: Bağlam penceresi, açıkça yazılıyor.
    #:
    #: Bir dönem hiç yazılmıyordu ve Ollama'nın varsayılanı geçerliydi.
    #: Kullanıcının makinesinde ``ollama show qwen2.5:14b-instruct
    #: --modelfile`` çalıştırıldı: Modelfile'da TEK BİR ``PARAMETER``
    #: satırı yok, yani num_ctx tanımsız ve varsayılan (çoğu sürümde 2048)
    #: geçerli. Ölçülen ilk tur ise 2338 token — yani pencere daha ilk
    #: mesajda taşıyordu ve taşınca kırpılan en baştaki mesaj oluyordu:
    #: sistem istemi. Kişiliğin, Türkçe kuralının ve kullanıcının kimliğinin
    #: durduğu yer tam orası.
    #:
    #: 8192 seçildi, 32768 değil. Sebep bellek: Qwen2.5-14B'de KV önbelleği
    #: token başına ~0,19 MB, yani 8192 ≈ 1,6 GB, 32768 ≈ 6,3 GB. Ağırlıklar
    #: (q4) zaten ~9 GB; 32768 çoğu ekran kartında karta sığmayıp RAM'e
    #: taşar ve cevap dakikalara çıkar. 8192 hem bugünkü turun üç katı hem
    #: de kartta kalıyor. Daha fazlası gereken JARVIS_OLLAMA_NUM_CTX ile
    #: yükseltir — ama bunu ÖLÇEREK yapmalı, çünkü taşma sessiz.
    VARSAYILAN_NUM_CTX = 8192

    def __init__(self, host: str, model: str, timeout: float = 120.0,
                 temperature: float = 0.35, top_p: float = 0.9,
                 repeat_penalty: float = 1.1,
                 num_ctx: int = VARSAYILAN_NUM_CTX, think: bool = False,
                 num_predict: int = 512, keep_alive: str = "30m") -> None:
        self.host = host.rstrip("/")
        self.model = model
        # Ollama defaults to temperature 0.8, which suits creative writing and
        # not a technical assistant. High temperature is what produces mangled
        # inflection — at every token the model is nudged toward a less likely
        # word, and in an agglutinative language a wrong suffix wrecks the
        # sentence rather than just colouring it. Lower is steadier prose.
        self.temperature = temperature
        self.top_p = top_p
        self.repeat_penalty = repeat_penalty
        # Configurable because a model too large for the card offloads to RAM
        # and can take minutes per answer — which is exactly the situation the
        # comparison tool puts it in on purpose.
        self.timeout = timeout
        self.num_ctx = max(512, int(num_ctx or self.VARSAYILAN_NUM_CTX))
        self.think = bool(think)
        self.num_predict = max(32, int(num_predict or 512))
        self.keep_alive = str(keep_alive or "30m")
        #: Son turun ÖLÇÜLEN bağlam kullanımı. Tahmin değil: Ollama
        #: prompt_eval_count alanında kaç token okuduğunu söylüyor.
        #: Panelin "context usage" göstergesi buradan besleniyor, ve
        #: taşmayı fark etmenin tek dürüst yolu bu.
        self.son_kullanim: dict[str, Any] = {}
        self.son_yanit = LLMResponse()
        self._base_temperature = self.temperature
        self._base_top_p = self.top_p
        self._base_num_predict = self.num_predict
        self._base_think = self.think

    def apply_reasoning(self, level: int) -> None:
        """Apply a bounded task profile; level 0 is handled by Agent."""
        profile = profile_for(level)
        self.temperature = profile.temperature if level else self._base_temperature
        self.top_p = profile.top_p if level else self._base_top_p
        self.num_predict = profile.num_predict if level else self._base_num_predict
        self.think = profile.thinking if level >= 4 else self._base_think

    def warmup(self) -> None:
        """Load the model once before the first user turn."""
        self.chat([Message(role="user", content="Kısa yanıt ver: hazır.")])

    def _govde(self, messages: list[Message], tools, *, akis: bool) -> dict[str, Any]:
        """Build streaming and plain requests from one set of options."""
        payload: dict[str, Any] = {
            "model": self.model,
            "stream": akis,
            "think": self.think,
            "keep_alive": self.keep_alive,
            "messages": [self._encode(m) for m in messages],
            "options": {
                "temperature": self.temperature,
                "top_p": self.top_p,
                "repeat_penalty": self.repeat_penalty,
                # Yazılmazsa Ollama'nın varsayılanı geçerli oluyor ve o
                # varsayılan bizim ilk turumuzdan küçük. Gerekçe
                # VARSAYILAN_NUM_CTX içinde.
                "num_ctx": self.num_ctx,
                "num_predict": self.num_predict,
            },
        }
        if tools:
            payload["tools"] = tools
        return payload

    def _istek(self, payload: dict[str, Any]) -> urllib.request.Request:
        return urllib.request.Request(
            f"{self.host}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )

    def chat(self, messages: list[Message], tools: list[dict[str, Any]] | None = None) -> LLMResponse:
        req = self._istek(self._govde(messages, tools, akis=False))
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise self._http_exception(exc) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise self._connection_exception(exc) from exc

        self.son_kullanim = self._kullanim(body)
        msg = body.get("message", {}) or {}
        calls = self._parse_tool_calls(msg.get("tool_calls"))
        return LLMResponse(content=msg.get("content", "") or "", tool_calls=calls)

    def chat_stream(self, messages: list[Message],
                    tools: list[dict[str, Any]] | None = None) -> Iterator[str]:
        """Yield Ollama NDJSON content and retain its final structured result."""
        self.son_yanit = LLMResponse()
        self.son_kullanim = {}
        req = self._istek(self._govde(messages, tools, akis=True))
        parcalar: list[str] = []
        cagrilar: list[ToolCall] = []
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                for ham in resp:
                    satir = ham.decode("utf-8").strip()
                    if not satir:
                        continue
                    try:
                        veri = json.loads(satir)
                    except json.JSONDecodeError:
                        # A partial line must not discard already received text.
                        continue
                    msg = veri.get("message") or {}
                    yeni = msg.get("content") or ""
                    if yeni:
                        parcalar.append(yeni)
                        yield yeni
                    cagrilar.extend(self._parse_tool_calls(msg.get("tool_calls")))
                    if veri.get("done"):
                        self.son_kullanim = self._kullanim(veri)
        except urllib.error.HTTPError as exc:
            raise self._http_exception(exc) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise self._connection_exception(exc) from exc

        self.son_yanit = LLMResponse(
            content="".join(parcalar), tool_calls=cagrilar
        )

    #: Pencerenin bu oranı aşıldığında taşma yakın sayılıyor.
    #:
    #: %90'da uyarmak geç: bir sonraki tur araç çıktısıyla birlikte gelirse
    #: aradaki payı tek adımda yiyor. %80 fark etmek ile yer kalması
    #: arasındaki denge.
    DOLULUK_ESIGI = 0.80
    _NS = 1_000_000_000
    # Reading the prompt for more than half the generation duration is a
    # measurable prefill bottleneck, commonly caused by changing tool schemas
    # invalidating Qwen's prompt cache.
    OKUMA_BASKIN_ORANI = 0.5

    def _kullanim(self, body: dict[str, Any]) -> dict[str, Any]:
        """Bu turda gerçekten kaç token okundu ve üretildi.

        Ollama bunu sayıyor; biz tahmin etmiyoruz. Ayrım önemli çünkü
        "3 karakter ≈ 1 token" Türkçede kabaca doğru ama taşmanın kenarında
        yanılmak, sessizce kırpılan bir sistem istemi demek.
        """
        okunan = int(body.get("prompt_eval_count") or 0)
        uretilen = int(body.get("eval_count") or 0)
        sure_ns = int(body.get("eval_duration") or 0)
        okuma_ns = int(body.get("prompt_eval_duration") or 0)
        yukleme_ns = int(body.get("load_duration") or 0)
        toplam_ns = int(body.get("total_duration") or 0)
        kullanim: dict[str, Any] = {
            "okunan_token": okunan,
            "uretilen_token": uretilen,
            "pencere": self.num_ctx,
            "doluluk": round(okunan / self.num_ctx, 3) if self.num_ctx else 0.0,
        }
        if okuma_ns > 0:
            kullanim["okuma_sn"] = round(okuma_ns / self._NS, 2)
            if okunan > 0:
                kullanim["okuma_token_sn"] = round(
                    okunan / (okuma_ns / self._NS), 1
                )
        if sure_ns > 0:
            kullanim["uretim_sn"] = round(sure_ns / self._NS, 2)
        if toplam_ns > 0:
            kullanim["toplam_sn"] = round(toplam_ns / self._NS, 2)
        if yukleme_ns > self._NS // 10:
            kullanim["model_yukleme_sn"] = round(yukleme_ns / self._NS, 2)
        if (okuma_ns > 0 and sure_ns > 0
                and okuma_ns > sure_ns * self.OKUMA_BASKIN_ORANI):
            kullanim["darbogaz"] = (
                "Süre ağırlıkla İSTEMİ OKUMAKTA geçiyor "
                f"({kullanim['okuma_sn']} sn okuma / "
                f"{kullanim['uretim_sn']} sn üretim). "
                "Bu genellikle istem önbelleğinin tutmadığı anlamına gelir: "
                "araç listesi her turda değişirse Qwen'in sistem bloğu da "
                "değişiyor ve tüm istem yeniden işleniyor."
            )
        if sure_ns > 0 and uretilen > 0:
            kullanim["token_sn"] = round(uretilen / (sure_ns / self._NS), 1)
        if okunan >= self.num_ctx * self.DOLULUK_ESIGI:
            kullanim["uyari"] = (
                f"Bağlam penceresi dolmak üzere: {okunan}/{self.num_ctx} token. "
                "Pencere taştığında en eski mesaj — sistem istemi — kırpılır ve "
                "kişilik, dil kuralı ve kimlik sessizce kaybolur. "
                "JARVIS_OLLAMA_NUM_CTX ile büyütün ya da konuşmayı yenileyin."
            )
        return kullanim

    def _baglanti_acikla(self, exc: Exception) -> str:
        """Bağlantı hatasını kullanıcının bir şey yapabileceği cümleye çevir.

        Ham hâli şuydu:

            RuntimeError: Ollama'ya ulaşılamadı (http://localhost:11434):
            <urlopen error [WinError 10061] Hedef makine etkin olarak
            reddettiğinden bağlantı kurulamadı>

        Doğru ama işe yaramaz: hatayı okuyan kişi Ollama'nın ayrı bir program
        olduğunu ve kurulup çalıştırılması gerektiğini buradan çıkaramıyor.
        Bağlantının REDDEDİLMESİ ile ZAMAN AŞIMI farklı şeyler ve farklı
        şeyler yapılmasını gerektiriyor, o yüzden ayrı ayrı söyleniyor.
        """
        ham = str(exc)
        dusuk = ham.lower()

        # Reddedildi: adreste dinleyen yok. Windows 10061, Linux/mac 111.
        reddedildi = ("10061" in ham or "refused" in dusuk
                      or "reddedild" in dusuk or "errno 111" in dusuk)
        if reddedildi:
            return (
                f"Ollama çalışmıyor ({self.host}).\n"
                "    Ollama ayrı bir programdır ve arka planda açık olmalı.\n"
                "\n"
                "    Kurulu değilse:\n"
                "      Windows : winget install Ollama.Ollama\n"
                "      Linux   : curl -fsSL https://ollama.com/install.sh | sh\n"
                "\n"
                "    Kuruluysa başlatın:  ollama serve\n"
                f"    Sonra modeli indirin:  ollama pull {self.model}\n"
                "\n"
                "    Model olmadan da çalışsın isterseniz .env içine:\n"
                "      JARVIS_LLM_PROVIDER=mock   (yalnızca birkaç kalıp cevap)"
            )

        if isinstance(exc, TimeoutError) or "timed out" in dusuk:
            return (
                f"Ollama {self.timeout:.0f} saniyede cevap vermedi ({self.host}).\n"
                f"    '{self.model}' bu makine için büyük olabilir; ilk cevap\n"
                "    modeli belleğe yüklerken uzun sürer.\n"
                "    Daha küçük bir model:  JARVIS_OLLAMA_MODEL=qwen2.5:7b-instruct"
            )

        if "name or service not known" in dusuk or "getaddrinfo" in dusuk:
            return (
                f"Ollama adresi çözümlenemedi ({self.host}).\n"
                "    JARVIS_OLLAMA_HOST ayarındaki makine adını kontrol edin."
            )

        return f"Ollama'ya ulaşılamadı ({self.host}): {ham}"

    def _connection_exception(self, exc: Exception) -> LLMProviderError:
        raw = str(exc).lower()
        if isinstance(exc, TimeoutError) or "timed out" in raw:
            return LLMProviderError(
                self._baglanti_acikla(exc), kind=ErrorType.TIMEOUT,
                retryable=True, fallback_allowed=True, server_available=None,
            )
        return LLMProviderError(
            self._baglanti_acikla(exc), kind=ErrorType.SERVER_UNAVAILABLE,
            retryable=False, fallback_allowed=False, server_available=False,
        )

    @staticmethod
    def _http_body(exc: urllib.error.HTTPError) -> str:
        try:
            return exc.read().decode("utf-8", errors="replace")[:300]
        except Exception:  # noqa: BLE001 - error body is optional evidence
            return ""

    def _http_exception(self, exc: urllib.error.HTTPError) -> LLMProviderError:
        body = self._http_body(exc)
        lowered = body.lower()
        message = self._http_message(exc, body)
        if exc.code == 404 or "not found" in lowered:
            return LLMProviderError(
                message, kind=ErrorType.MODEL_MISSING,
                fallback_allowed=True, server_available=True,
            )
        if any(term in lowered for term in (
            "out of memory", "more system memory", "cuda out of memory", "oom",
        )):
            return LLMProviderError(
                message, kind=ErrorType.MODEL_OOM,
                fallback_allowed=True, server_available=True,
            )
        kind = ErrorType.INVALID_ARGUMENT if exc.code in {400, 422} else ErrorType.PROVIDER_FAILURE
        return LLMProviderError(
            message, kind=kind, retryable=exc.code >= 500,
            fallback_allowed=False, server_available=True,
        )

    def _http_acikla(self, exc: urllib.error.HTTPError) -> str:
        """Sunucu cevap verdi ama isteği reddetti.

        En sık görüleni 404: sunucu ayakta, model indirilmemiş. Bunu
        "ulaşılamadı" diye bildirmek yanlış yöne baktırıyordu.
        """
        govde = self._http_body(exc)
        return self._http_message(exc, govde)

    def _http_message(self, exc: urllib.error.HTTPError, govde: str) -> str:
        if exc.code == 404 or "not found" in govde.lower():
            return (
                f"Ollama '{self.model}' modelini bulamadı.\n"
                f"    İndirmek için:  ollama pull {self.model}\n"
                "    Kurulu modelleri görmek için:  ollama list"
            )
        return f"Ollama isteği reddetti (HTTP {exc.code}): {govde or exc.reason}"

    @staticmethod
    def _parse_tool_calls(raw: Any) -> list[ToolCall]:
        """Read tool calls defensively.

        Models and Ollama versions disagree on the exact shape, and a small
        model can emit something malformed. A bad entry is skipped rather than
        allowed to kill the turn — the agent then works with whatever text or
        remaining calls came back.
        """
        calls: list[ToolCall] = []
        for entry in raw or []:
            if not isinstance(entry, dict):
                continue
            fn = entry.get("function") or entry
            if not isinstance(fn, dict):
                continue
            name = fn.get("name")
            if not isinstance(name, str) or not name:
                continue

            args = fn.get("arguments", {})
            if isinstance(args, str):
                # Some builds serialise arguments as a JSON string.
                try:
                    args = json.loads(args or "{}")
                except json.JSONDecodeError:
                    args = {}
            if not isinstance(args, dict):
                args = {}

            calls.append(ToolCall(name=name, arguments=args))
        return calls

    @staticmethod
    def _encode(m: Message) -> dict[str, Any]:
        out: dict[str, Any] = {"role": m.role, "content": m.content}
        if m.role == "tool" and m.name:
            out["name"] = m.name
        if m.role == "assistant" and m.tool_calls:
            out["tool_calls"] = m.tool_calls
        return out

def ollama_hazir(host: str, model: str, timeout: float = 3.0) -> str:
    """Boş dize: Ollama konuşmaya hazır. Değilse neden değil.

    Açılışta çağrılıyor, ilk soruda değil. Bu projede aynı ders üç kez
    alındı — kamera, Piper ve Edge katmanlarında: kurulu olmayan bir şeyin
    "hazır" görünmesi, hatanın konuşmanın ORTASINDA çıkması demek. Oysa
    açılışta çıksa kullanıcı daha panele bakmadan ne yapacağını biliyor.

    Kısa zaman aşımı bilinçli: bu bir sağlık yoklaması, cevap üretimi değil.
    Ollama ayakta ama meşgulse birkaç saniye gecikebilir, ve o durumda
    açılışı bekletmektense "erişilemedi" dememek daha doğru — bu yüzden
    zaman aşımı sessizce boş dize döndürüyor.
    """
    import json as _json
    import urllib.error as _err
    import urllib.request as _req

    adres = host.rstrip("/") + "/api/tags"
    try:
        with _req.urlopen(adres, timeout=timeout) as cevap:
            govde = _json.loads(cevap.read().decode("utf-8"))
    except (_err.URLError, TimeoutError, OSError, ValueError) as exc:
        ham = str(exc).lower()
        if "timed out" in ham:
            # Ayakta ama yavas olabilir; acilisi engellemek yanlis olur.
            return ""
        return (f"Ollama çalışmıyor ({host}). Panel açılır ama soru "
                f"cevaplanamaz.\n"
                f"    Başlatmak için:  ollama serve\n"
                f"    Kurulu değilse:  winget install Ollama.Ollama")

    adlar = {(m or {}).get("name", "") for m in govde.get("models") or []}
    if not adlar:
        return (f"Ollama çalışıyor ama hiç model yok.\n"
                f"    İndirmek için:  ollama pull {model}")

    # "qwen2.5:14b-instruct" ile "qwen2.5:14b-instruct" birebir eslesmeli,
    # ama Ollama bazen ":latest" ekliyor.
    if model not in adlar and f"{model}:latest" not in adlar:
        return (f"'{model}' modeli indirilmemiş.\n"
                f"    İndirmek için:  ollama pull {model}\n"
                f"    Kurulu olanlar:  {', '.join(sorted(adlar)) or '(yok)'}")
    return ""
