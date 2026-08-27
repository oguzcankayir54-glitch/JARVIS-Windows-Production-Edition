"""Central user-facing response layer for J.A.R.V.I.S. 2.0 (Phase 5).

LLM/tool/backend text is never assumed to be suitable for the user verbatim.
The engine removes internal plumbing in normal mode, converts common tool
payloads to readable Turkish, and maps exceptions to stable user-facing
messages.  Developer/debug mode can opt into raw details later.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field

from .intent_router import Intent
from .metin import katla


_TOOL_LABELS = {
    "get_system_info": "sistem bilgisi",
    "get_cpu_temperature": "CPU sıcaklığı",
    "get_gpu_temperature": "GPU bilgisi",
    "get_ram_usage": "RAM kullanımı",
    "get_disk_health": "disk sağlığı",
    "recall_facts": "hafıza",
    "remember_fact": "hafıza",
    "forget_fact": "hafıza",
    "bilgi_ara": "bilgi arşivi",
    "bilgi_durum": "bilgi arşivi",
    "web_ara": "web araması",
    "web_oku": "web içeriği",
    "run_terminal_command": "terminal işlemi",
}


@dataclass(frozen=True)
class ResponseValidation:
    text: str
    issues: tuple[str, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return not self.issues


class ResponseEngine:
    """Make backend/LLM output safe and natural for normal conversation."""

    _TRACEBACK = re.compile(r"Traceback \(most recent call last\):.*", re.S | re.I)
    _TOOL_PREFIX = re.compile(r"^\[([A-Za-z0-9_\-]+)\]\s*sonucu:\s*", re.I)
    _ERROR_CODE = re.compile(r"\b[A-Z][A-Z0-9]+(?:_[A-Z0-9]+){1,}\b")
    _SECRETS = (
        re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
        re.compile(r"(?i)(api[_ -]?key|token|password|parola)\s*[:=]\s*([^\s,;]+)"),
        re.compile(r"(?i)Bearer\s+[A-Za-z0-9._~+/-]{12,}"),
    )

    def __init__(self, tool_names: set[str] | None = None) -> None:
        self.tool_names = set(tool_names or ())

    @staticmethod
    def _explicit_internal_question(user_text: str) -> bool:
        t = katla(user_text or "")
        return any(k in t for k in (
            "rag", "embedding", "gomme", "vektor", "vector database",
            "tool", "arac adi", "backend", "arka uc", "stack trace",
            "debug", "veritabani", "database",
        ))

    @staticmethod
    def _format_number(value) -> str:
        if isinstance(value, float):
            return f"{value:g}"
        return str(value)

    def _natural_tool_payload(self, tool_name: str, raw: str) -> str | None:
        try:
            data = ast.literal_eval(raw.strip())
        except (ValueError, SyntaxError):
            return None
        if not isinstance(data, dict):
            return None

        n = self._format_number
        if tool_name == "get_system_info":
            pieces = []
            if "cpu_percent" in data:
                pieces.append(f"CPU kullanımı %{n(data['cpu_percent'])}")
            if "ram_used_gb" in data and "ram_total_gb" in data:
                pieces.append(
                    f"RAM {n(data['ram_used_gb'])}/{n(data['ram_total_gb'])} GB"
                    + (f" (%{n(data['ram_percent'])})" if "ram_percent" in data else "")
                )
            if "disk_used_percent" in data:
                pieces.append(f"disk kullanımı %{n(data['disk_used_percent'])}")
            return " · ".join(pieces) if pieces else None

        if tool_name == "get_ram_usage":
            pieces = []
            if "ram_used_gb" in data and "ram_total_gb" in data:
                pieces.append(
                    f"RAM {n(data['ram_used_gb'])}/{n(data['ram_total_gb'])} GB"
                    + (f" (%{n(data['ram_percent'])})" if "ram_percent" in data else "")
                )
            if "swap_used_gb" in data:
                pieces.append(f"swap {n(data['swap_used_gb'])} GB")
            return " · ".join(pieces) if pieces else None

        if tool_name == "get_cpu_temperature":
            if data.get("available") and "cpu_temp_c" in data:
                return f"CPU sıcaklığı {n(data['cpu_temp_c'])} °C."
            return str(data.get("note") or "CPU sıcaklık sensörüne erişemiyorum.")

        if tool_name == "get_gpu_temperature":
            if data.get("available"):
                pieces = [str(data.get("name") or "GPU")]
                if "gpu_temp_c" in data:
                    pieces.append(f"{n(data['gpu_temp_c'])} °C")
                if "gpu_util_percent" in data:
                    pieces.append(f"kullanım %{n(data['gpu_util_percent'])}")
                if "vram_used_mb" in data and "vram_total_mb" in data:
                    pieces.append(
                        f"VRAM {n(data['vram_used_mb'])}/{n(data['vram_total_mb'])} MB"
                    )
                return " · ".join(pieces)
            return str(data.get("note") or "GPU telemetrisine erişemiyorum.")

        return None

    @classmethod
    def redact_secrets(cls, text: str) -> str:
        out = text or ""
        out = cls._SECRETS[0].sub("[SECRET]", out)
        out = cls._SECRETS[1].sub(lambda m: f"{m.group(1)}=[SECRET]", out)
        out = cls._SECRETS[2].sub("Bearer [SECRET]", out)
        return out

    def sanitize(self, text: str, *, intent: Intent, user_text: str,
                 debug: bool = False) -> str:
        text = self.redact_secrets((text or "").strip())
        if not text:
            return "Bu tur için anlamlı bir yanıt üretemedim."
        if debug:
            return text

        # Mock/tool adapters sometimes expose the tool name directly.  Convert
        # known telemetry payloads first, then strip the plumbing prefix.
        match = self._TOOL_PREFIX.match(text)
        if match:
            tool_name = match.group(1)
            raw = text[match.end():].strip()
            natural = self._natural_tool_payload(tool_name, raw)
            text = natural if natural else raw

        if self._TRACEBACK.search(text):
            return "İşlem sırasında beklenmeyen bir hata oluştu. Teknik ayrıntıyı normal yanıta yansıtmıyorum."

        folded = katla(text)
        if "bilgi taban" in folded and "bos" in folded and (
            "jarvis-bilgi" in folded or "bilgi ekle" in folded
        ):
            return "Bu konuda henüz kayıtlı bir bilgim yok; isterseniz şimdi öğretebilirsiniz."

        if text.startswith("HATA:"):
            return "İşlem tamamlanamadı. İlgili bileşene şu anda erişemiyorum."

        internal_requested = self._explicit_internal_question(user_text)

        # Registered JARVIS tool identifiers are plumbing, not user-facing
        # vocabulary.  Keep them hidden even for a Git/GitHub request.  Coding
        # is the one exception: when inspecting source code, a function name
        # can be the subject of the question rather than a runtime leak.
        if intent is not Intent.CODING:
            for name, label in _TOOL_LABELS.items():
                text = re.sub(rf"\b{re.escape(name)}\b", label, text)
            for name in self.tool_names - set(_TOOL_LABELS):
                text = re.sub(rf"\b{re.escape(name)}\b", "iç işlem", text)

        if not internal_requested and intent not in {Intent.CODING, Intent.TERMINAL}:
            # Backend component names are implementation detail unless the
            # user explicitly asked about them.
            text = re.sub(r"\bRAG\b", "bilgi arşivi", text, flags=re.I)
            text = re.sub(r"\bembedding\b", "arama altyapısı", text, flags=re.I)
            text = re.sub(r"\bvector database\b", "bilgi tabanı", text, flags=re.I)
            text = self._ERROR_CODE.sub("teknik hata", text)

        return text.strip()

    def validate(self, text: str, *, intent: Intent, user_text: str,
                 debug: bool = False) -> ResponseValidation:
        sanitized = self.sanitize(text, intent=intent, user_text=user_text, debug=debug)
        issues: list[str] = []
        if not sanitized:
            issues.append("empty")
        if not debug and self._TRACEBACK.search(sanitized):
            issues.append("stack_trace")
        if not debug and not self._explicit_internal_question(user_text):
            if any(name in sanitized for name in self.tool_names):
                issues.append("internal_tool_name")
        return ResponseValidation(sanitized, tuple(issues))

    def render(self, text: str, *, intent: Intent, user_text: str,
               debug: bool = False) -> str:
        return self.validate(text, intent=intent, user_text=user_text, debug=debug).text

    def ground_tool_failures(self, text: str, *, errors: list[str],
                             debug: bool = False) -> str:
        """Make unresolved tool failures authoritative over model prose.

        The model sees tool output so that it can explain it naturally, but it
        is not the authority on whether an operation actually succeeded.  A
        later successful call removes that tool's error before this method is
        reached; any errors left here are therefore unresolved evidence.
        """
        if not errors:
            return text
        if debug:
            detail = "; ".join(self.redact_secrets(item) for item in errors if item)
            return ("İşlem tamamlanamadı." + (f" {detail}" if detail else ""))
        return "İşlem tamamlanamadı. İlgili araç başarılı bir sonuç döndürmedi."

    def error(self, exc: BaseException, *, debug: bool = False) -> str:
        if debug:
            detail = self.redact_secrets(str(exc).strip() or exc.__class__.__name__)
            return f"Yanıt motoru bu turu tamamlayamadı. {detail}"

        raw = katla(str(exc) or exc.__class__.__name__)
        if any(k in raw for k in ("credit", "quota", "rate limit", "kota")):
            return "Bağlı yapay zekâ hizmetinin kullanım kotası şu anda yetersiz."
        if any(k in raw for k in ("timeout", "timed out", "zaman asimi")):
            return "Yanıt motoru zaman aşımına uğradı. Bu tur tamamlanamadı."
        if any(k in raw for k in ("connection", "connect", "baglanti", "ollama")):
            return "Yanıt motoruna şu anda bağlanamıyorum. Bağlantı yeniden kurulduğunda devam edebilirim."
        return "Yanıt motoru bu turu tamamlayamadı. Teknik ayrıntıyı normal yanıta yansıtmıyorum."
