"""Structured intent routing for J.A.R.V.I.S. 2.0 (Phase 2).

The router decides *what the user is trying to do* before RAG, memory or tool
selection happens.  It is deliberately deterministic and dependency-free: a
local classifier may be added later, but basic routing must keep working when
the LLM is unavailable.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
import re

from .metin import katla
from ..security.permissions import RiskLevel


class Intent(str, Enum):
    CHAT = "CHAT"
    MEMORY_SAVE = "MEMORY_SAVE"
    MEMORY_RECALL = "MEMORY_RECALL"
    MEMORY_UPDATE = "MEMORY_UPDATE"
    MEMORY_DELETE = "MEMORY_DELETE"
    TRAINING = "TRAINING"
    RAG_QUERY = "RAG_QUERY"
    WEB_RESEARCH = "WEB_RESEARCH"
    CODING = "CODING"
    GITHUB = "GITHUB"
    TERMINAL = "TERMINAL"
    COMPUTER_CONTROL = "COMPUTER_CONTROL"
    SYSTEM_MONITOR = "SYSTEM_MONITOR"
    TASK = "TASK"
    AUTONOMOUS = "AUTONOMOUS"
    VOICE = "VOICE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class IntentDecision:
    intent: Intent
    confidence: float
    requires_tool: bool = False
    requires_memory: bool = False
    requires_rag: bool = False
    requires_confirmation: bool = False
    tool: str | None = None
    subtype: str | None = None
    reason: str = ""
    entities: dict[str, str] = field(default_factory=dict)
    risk: RiskLevel = RiskLevel.LOW
    ambiguity: bool = False
    needs_confirmation: bool = False
    reasoning_level: int = 1
    original_text: str = ""
    normalized_text: str = ""

    @property
    def required_tool(self) -> str | None:
        """Preferred contract name while keeping the legacy ``tool`` field."""
        return self.tool

    def as_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "intent": self.intent.value,
            "confidence": round(float(self.confidence), 3),
            "requires_tool": self.requires_tool,
            "requires_memory": self.requires_memory,
            "requires_rag": self.requires_rag,
            "requires_confirmation": self.requires_confirmation,
            "required_tool": self.required_tool,
            "entities": dict(self.entities),
            "risk": self.risk.label,
            "ambiguity": self.ambiguity,
            "needs_confirmation": self.needs_confirmation,
            "reasoning_level": self.reasoning_level,
            "original_text": self.original_text,
            "normalized_text": self.normalized_text,
        }
        if self.tool:
            data["tool"] = self.tool
        if self.subtype:
            data["subtype"] = self.subtype
        return data


class IntentRouter:
    """Conservative Turkish-first intent classifier.

    Ordering is important.  Explicit GitHub/coding/RAG requests are detected
    before generic words such as ``proje`` or ``dosya``.  Conceptual questions
    such as "RAG ne?" are explicitly kept in CHAT so merely naming a backend
    concept never activates that backend.
    """

    _CONCEPT_QUESTION = re.compile(
        r"^(rag|embedding|gomme|vektor veri tabani|vector database|llm|ollama)\s+"
        r"(ne|nedir|ne demek|nasil calisir)(\?|$)"
    )

    _MEMORY_RECALL = (
        "benim hakkimda ne bili", "hakkimda neler bili", "ne hatirliyor",
        "hatirliyor musun", "hafizanda", "sana ne ogretmistim",
        "sana ne soylemistim", "gecen gun sana ne",
    )
    _MEMORY_DELETE = ("unut ", "hafizandan sil", "kaydi sil", "bunu unut")
    _MEMORY_UPDATE = ("artik ", "bundan sonra ", "degisti", "guncelle")
    _MEMORY_SAVE_EXPLICIT = ("hatirla", "unutma", "aklinda tut", "not al", "kaydet")
    _IDENTITY_SAVE = (
        "ben senin gelistiricinim", "ben senin gelistiricin", "bu sistemi ben yaptim",
        "benim adim ", "ben oguz", "ben senin sahibinim", "ben senin sahibin",
    )

    _TRAINING = ("egitim sureci", "egitim modu", "sana ogretecegim", "seni egitecegim", "egitimi bitir", "egitimi kapat")
    _TRAINING_STOP = ("egitimi bitir", "egitimi kapat", "egitim modundan cik", "egitim surecini bitir")
    _GITHUB = ("github", "pull request", "merge request", "commit", "branch", "repo", "repository")
    _TERMINAL = ("terminal", "powershell", "cmd", "kabuk", "shell", "komut satiri", "calistir:")
    _CODING = (
        "kodunu incele", "kodu incele", "kodlari incele", "source code", "kaynak kod",
        "fonksiyonu incele", "sinifi incele", "bug bul", "hatayi duzelt", "refactor",
        "authentication kod", "python dosya", "py dosya", "kod yaz", "kodu duzelt",
    )
    _RAG_EXPLICIT = (
        "bilgi tabaninda", "bilgi tabanindan", "dokumaninda", "dokumanda", "pdf'de",
        "pdf de", "pdfde", "bu pdf", "belgede", "belgeden", "arsivinde", "rag'de",
        "rag de", "ragde",
    )
    _WEB = ("internette", "internetten", "webde", "web'de", "guncel bilgi", "guncel olarak",
            "son surum", "haberleri", "fiyatini arastir", "arastir", "internete bak")
    _COMPUTER_CONTROL = (
        "chrome'u ac", "chrome ac", "uygulamayi ac", "programi ac", "program ac",
        "not defterini ac", "hesap makinesini ac", "ayarlar'i ac", "ayarlari ac",
        "youtube'u ac", "tarayiciyi ac", "uygulama ac", "gorev yoneticisini ac",
        "task manager ac", "gorev yoneticisi gelsin", "gorev yoneticisine bakalim",
    )
    _SYSTEM = (
        "cpu", "islemci", "gpu", "ekran kart", "ram", "bellek", "disk", "ssd", "hdd",
        "smart", "sicaklik", "sicakligi", "fan", "sistem durumu", "donanim durumu",
        "kullanimim", "kullanimi", "performans neden", "neden bu kadar yuksek",
    )
    _VOICE = ("mikrofon", "sesli mod", "sesli dinle", "beni duyuyor", "konusmami algila", "stt")
    _AUTONOMOUS = ("kendi basina", "otonom", "autonomous", "ben sormadan devam et")
    _TASK = ("gorev olustur", "gorev ekle", "yapilacaklara ekle", "todo", "hatirlatici")
    _CASE_TASK = ("vaka", "musteri kaydi", "servis kaydi", "ariza kaydi", "onarim kaydi")
    _FILE_OPERATION = ("oku:", "listele:", "dosyayi oku", "klasoru listele", "dizini listele")

    @staticmethod
    def _has(text: str, needles: tuple[str, ...]) -> bool:
        return any(n in text for n in needles)

    @staticmethod
    def _d(intent: Intent, confidence: float, **kw) -> IntentDecision:
        return IntentDecision(intent=intent, confidence=confidence, **kw)

    @staticmethod
    def _risk_for(intent: Intent) -> RiskLevel:
        if intent in {Intent.TERMINAL, Intent.MEMORY_DELETE}:
            return RiskLevel.HIGH
        if intent in {Intent.COMPUTER_CONTROL, Intent.MEMORY_SAVE,
                      Intent.MEMORY_UPDATE, Intent.TASK}:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    @staticmethod
    def _reasoning_for(intent: Intent) -> int:
        if intent is Intent.CODING:
            return 4
        if intent is Intent.AUTONOMOUS:
            return 3
        if intent in {Intent.COMPUTER_CONTROL, Intent.SYSTEM_MONITOR,
                      Intent.TERMINAL, Intent.RAG_QUERY, Intent.WEB_RESEARCH,
                      Intent.GITHUB, Intent.TASK}:
            return 2
        return 1

    def route(self, message: str, *, original_text: str | None = None,
              speech_confidence: float = 1.0,
              ambiguity: bool = False) -> IntentDecision:
        normalized = (message or "").strip()
        decision = self._route_normalized(normalized)
        confidence = min(decision.confidence,
                         max(0.0, min(1.0, float(speech_confidence))))
        risk = self._risk_for(decision.intent)
        ambiguous = bool(ambiguity or confidence < 0.65)
        needs_confirmation = bool(
            decision.requires_confirmation
            or (ambiguous and risk >= RiskLevel.HIGH)
        )
        wake_key = re.sub(r"[^a-z0-9]", "", katla(normalized))
        reasoning_level = (
            0 if wake_key == "jarvis"
            else self._reasoning_for(decision.intent)
        )
        return replace(
            decision,
            confidence=confidence,
            risk=risk,
            ambiguity=ambiguous,
            needs_confirmation=needs_confirmation,
            reasoning_level=reasoning_level,
            original_text=(original_text if original_text is not None else normalized),
            normalized_text=normalized,
        )

    def _route_normalized(self, message: str) -> IntentDecision:
        text = katla((message or "").strip())
        if not text:
            return self._d(Intent.UNKNOWN, 0.2, reason="boş mesaj")

        # Explaining a concept is ordinary conversation, not an invocation of
        # the component bearing that name.
        if self._CONCEPT_QUESTION.search(text):
            return self._d(Intent.CHAT, 0.99, reason="kavramsal açıklama sorusu")

        if self._has(text, self._TRAINING_STOP):
            return self._d(Intent.TRAINING, 0.99, requires_memory=True,
                           subtype="STOP", reason="eğitim modunu kapatma")
        if self._has(text, self._TRAINING):
            return self._d(Intent.TRAINING, 0.99, requires_memory=True,
                           subtype="START", reason="açık eğitim modu ifadesi")

        # Identity statements are durable user information, but they are not
        # RAG queries and do not mutate CoreIdentity.
        if self._has(text, self._IDENTITY_SAVE):
            return self._d(Intent.MEMORY_SAVE, 0.99, requires_memory=True,
                           subtype="IDENTITY", reason="kullanıcı kimlik beyanı")

        if self._has(text, self._MEMORY_RECALL):
            return self._d(Intent.MEMORY_RECALL, 0.98, requires_memory=True,
                           requires_tool=True, tool="recall_facts",
                           reason="açık hafıza geri çağırma")

        if self._has(text, self._MEMORY_DELETE):
            return self._d(Intent.MEMORY_DELETE, 0.96, requires_memory=True,
                           requires_tool=True, tool="forget_fact",
                           reason="açık hafıza silme")

        # "Artık ..." is an update only when it describes a preference/fact,
        # not every sentence starting with that word.  The explicit memory
        # verbs below provide the high-confidence path.
        if self._has(text, self._MEMORY_SAVE_EXPLICIT):
            return self._d(Intent.MEMORY_SAVE, 0.96, requires_memory=True,
                           requires_tool=True, tool="remember_fact",
                           reason="açık hatırlama/kaydetme talebi")
        if self._has(text, self._MEMORY_UPDATE) and any(
            k in text for k in ("favori", "tercih", "kullaniyorum", "adim", "benim")
        ):
            return self._d(Intent.MEMORY_UPDATE, 0.9, requires_memory=True,
                           requires_tool=True, tool="remember_fact",
                           reason="kalıcı bilginin değiştiğini belirtiyor")

        if self._has(text, self._GITHUB):
            return self._d(Intent.GITHUB, 0.98, requires_tool=True,
                           reason="Git/GitHub kaynağı açıkça belirtilmiş")

        if self._has(text, self._FILE_OPERATION):
            return self._d(Intent.CODING, 0.94, requires_tool=True,
                           reason="açık dosya/kaynak okuma işlemi")

        # Coding precedes generic document/file routing.  "Jarvis klasöründeki
        # authentication kodunu incele" must not become RAG_QUERY merely
        # because it contains "klasör/proje".
        if self._has(text, self._CODING) or (
            "jarvis" in text and any(k in text for k in ("kod", ".py", "fonksiyon", "sinif"))
        ):
            return self._d(Intent.CODING, 0.96, requires_tool=True,
                           reason="kaynak kod üzerinde çalışma")

        if self._has(text, self._RAG_EXPLICIT):
            return self._d(Intent.RAG_QUERY, 0.97, requires_tool=True,
                           requires_rag=True, tool="bilgi_ara",
                           reason="belge/PDF/bilgi tabanı içeriği soruluyor")

        if self._has(text, self._WEB):
            return self._d(Intent.WEB_RESEARCH, 0.96, requires_tool=True,
                           tool="web_ara", reason="güncel/internet araştırması")

        if self._has(text, self._COMPUTER_CONTROL) or (
            text.endswith(" ac") and any(k in text for k in ("chrome", "uygulama", "program", "tarayici"))
        ):
            return self._d(Intent.COMPUTER_CONTROL, 0.97, requires_tool=True,
                           tool="uygulama_ac", reason="uygulama/bilgisayar kontrolü")

        if self._has(text, self._TERMINAL):
            return self._d(Intent.TERMINAL, 0.95, requires_tool=True,
                           tool="run_terminal_command", reason="terminal/komut isteği")

        if self._has(text, self._SYSTEM):
            return self._d(Intent.SYSTEM_MONITOR, 0.95, requires_tool=True,
                           reason="sistem telemetrisi/sağlığı sorusu")

        if self._has(text, self._VOICE):
            return self._d(Intent.VOICE, 0.92, reason="ses/mikrofon davranışı")

        if self._has(text, self._AUTONOMOUS):
            return self._d(Intent.AUTONOMOUS, 0.9, reason="otonom çalışma isteği")

        if self._has(text, self._CASE_TASK):
            return self._d(Intent.TASK, 0.94, requires_tool=True, subtype="SERVICE_CASE",
                           reason="teknik servis vaka işlemi")

        if self._has(text, self._TASK):
            return self._d(Intent.TASK, 0.9, reason="görev/todo isteği")

        # Ordinary human conversation is intentionally the default.  UNKNOWN
        # is reserved for empty/unparseable input; making UNKNOWN the default
        # would push harmless chat into fallback tool logic again.
        return self._d(Intent.CHAT, 0.82, reason="özel sistem niyeti yok")
