from __future__ import annotations

import importlib.util
import os
import platform
import shutil
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from ..agenda.notifier import WindowsNotifier
from ..llm.ollama_provider import ollama_hazir


@dataclass(frozen=True)
class AcceptanceCheck:
    id: str
    name: str
    status: str                 # hazir | eksik | arizali
    detail: str
    fix: str = ""
    required: bool = False

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class AcceptanceReport:
    checks: tuple[AcceptanceCheck, ...]

    @property
    def status(self) -> str:
        if any(x.required and x.status == "arizali" for x in self.checks):
            return "arizali"
        if any(x.required and x.status != "hazir" for x in self.checks):
            return "eksik"
        if any(x.status != "hazir" for x in self.checks):
            return "eksik"
        return "hazir"

    def as_dict(self) -> dict:
        counts = {s: sum(x.status == s for x in self.checks)
                  for s in ("hazir", "eksik", "arizali")}
        return {"status": self.status, "counts": counts,
                "checks": [x.as_dict() for x in self.checks]}


def _provider(check_id: str, name: str, provider, *, enabled: bool,
              fix: str) -> AcceptanceCheck:
    if not enabled:
        return AcceptanceCheck(check_id, name, "eksik", "Ayar kapalı.", fix)
    if provider is None or not getattr(provider, "available", False):
        reason = getattr(provider, "reason", "Sağlayıcı kullanılamıyor.")
        return AcceptanceCheck(check_id, name, "arizali", str(reason).splitlines()[0], fix)
    return AcceptanceCheck(check_id, name, "hazir", getattr(provider, "name", "hazır"))


def run_acceptance(cfg, *, tts=None, stt=None, vision=None,
                   notifier=None, ollama_probe=ollama_hazir) -> AcceptanceReport:
    """Salt-okunur üretim yoklaması; cihaz açmaz ve ayar değiştirmez."""
    checks: list[AcceptanceCheck] = []
    windows = platform.system().lower() == "windows"
    checks.append(AcceptanceCheck(
        "windows", "Windows", "hazir" if windows else "eksik",
        platform.platform(), "Bu kurucu Windows 10/11 içindir.", required=True))

    py_ok = sys.version_info >= (3, 10)
    checks.append(AcceptanceCheck(
        "python", "Python", "hazir" if py_ok else "arizali",
        platform.python_version(), "winget install Python.Python.3.12", required=True))

    data_dir = Path(cfg.data_dir).expanduser()
    parent = data_dir if data_dir.exists() else data_dir.parent
    writable = parent.exists() and os.access(parent, os.W_OK)
    checks.append(AcceptanceCheck(
        "data", "Veri klasörü", "hazir" if writable else "arizali", str(data_dir),
        "JARVIS_DATA_DIR değerini yazılabilir bir kullanıcı klasörü yapın.", required=True))

    free = shutil.disk_usage(parent).free if parent.exists() else 0
    disk_ok = free >= 5 * 1024**3
    checks.append(AcceptanceCheck(
        "disk", "Boş disk", "hazir" if disk_ok else "arizali",
        f"{free / 1024**3:.1f} GB boş", "En az 5 GB alan boşaltın.", required=True))

    if cfg.llm_provider == "ollama":
        problem = ollama_probe(cfg.ollama_host, cfg.ollama_model)
        checks.append(AcceptanceCheck(
            "ollama", "Ollama ve model", "arizali" if problem else "hazir",
            problem.splitlines()[0] if problem else cfg.ollama_model,
            f"ollama serve; ollama pull {cfg.ollama_model}", required=True))
    else:
        checks.append(AcceptanceCheck(
            "ollama", "Gerçek dil modeli", "eksik", f"Sağlayıcı: {cfg.llm_provider}",
            "JARVIS_LLM_PROVIDER=ollama", required=True))

    checks.append(_provider("tts", "Seslendirme", tts, enabled=cfg.voice_enabled,
                            fix="JARVIS_VOICE_ENABLED=true ve pip install -e .[ses]"))
    checks.append(_provider("microphone", "Mikrofon/STT", stt, enabled=cfg.stt_enabled,
                            fix="JARVIS_STT_ENABLED=true ve pip install -e .[mikrofon]"))
    checks.append(_provider("camera", "Kamera analizi", vision, enabled=cfg.vision_enabled,
                            fix="JARVIS_VISION_ENABLED=true ve pip install -e .[kamera]"))

    toast = notifier or WindowsNotifier()
    checks.append(AcceptanceCheck(
        "notification", "Windows bildirimi",
        "hazir" if getattr(toast, "available", False) else "eksik",
        "Yerel Toast API hazır." if getattr(toast, "available", False) else "Windows oturumu algılanmadı.",
        "Kabul testini Windows kullanıcı oturumunda çalıştırın."))

    for module, label, fix in (
        ("psutil", "Sistem telemetrisi", "pip install psutil"),
        ("pytest", "Regresyon test altyapısı", "pip install -e .[dev]"),
    ):
        available = importlib.util.find_spec(module) is not None
        checks.append(AcceptanceCheck(module, label, "hazir" if available else "eksik",
                                      "Kurulu." if available else "Paket bulunamadı.", fix,
                                      required=module == "psutil"))
    return AcceptanceReport(tuple(checks))
