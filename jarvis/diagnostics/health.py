"""Measured system-health report used by the local panel."""
from __future__ import annotations

import importlib.util
import json
import platform
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any, Callable

from ..core.sayac import SAYACLAR
from ..tools.system_tools import (
    get_disk_health,
    get_gpu_temperature,
    get_ram_usage,
    get_system_info,
)

#: Bu kadar yutulan hatadan sonra "Core" uyarıya düşüyor. Beş, tek bir
#: geçici arıza ile süregelen bir arızayı ayıran en küçük sayı: açılışta
#: bir kez patlayan bir yoklama paneli kalıcı olarak sarıya boyamamalı.
YUTULAN_ESIGI = 5


@dataclass(frozen=True)
class HealthCheck:
    key: str
    label: str
    category: str
    status: str
    value: str
    required: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


_POINTS = {"ready": 100, "warning": 50, "critical": 0, "unavailable": 0}


def _ollama(agent, timeout: float = 2.0) -> tuple[HealthCheck, HealthCheck]:
    llm = agent.llm
    model = str(getattr(llm, "model", "") or getattr(llm, "name", "unknown"))
    provider_name = str(getattr(llm, "name", ""))
    if not provider_name.startswith("ollama"):
        return (
            HealthCheck("ollama", "OLLAMA", "LLM", "unknown",
                        f"kullanılmıyor · {provider_name}"),
            HealthCheck("model", model.upper(), "LLM", "ready", "READY", required=True),
        )
    provider = getattr(llm, "primary", llm)
    host = str(getattr(provider, "host", "http://127.0.0.1:11434")).rstrip("/")
    try:
        with urllib.request.urlopen(f"{host}/api/tags", timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
        names = {str(x.get("name", "")) for x in body.get("models", [])}
        found = model in names or any(x.split(":", 1)[0] == model.split(":", 1)[0] for x in names)
        return (
            HealthCheck("ollama", "OLLAMA", "LLM", "ready", "ONLINE", required=True),
            HealthCheck("model", model.upper(), "LLM",
                        "ready" if found else "critical",
                        "READY" if found else "MODEL NOT FOUND", required=True),
        )
    except (OSError, ValueError, urllib.error.URLError) as exc:
        return (
            HealthCheck("ollama", "OLLAMA", "LLM", "critical",
                        f"OFFLINE · {type(exc).__name__}", required=True),
            HealthCheck("model", model.upper(), "LLM", "critical",
                        "UNAVAILABLE", required=True),
        )


def _dependency_check(timeout: float = 20.0) -> HealthCheck:
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "check"], capture_output=True,
            text=True, timeout=timeout, shell=False,
        )
        detail = (result.stdout or result.stderr or "No broken requirements found.").strip()
        return HealthCheck(
            "dependencies", "DEPENDENCIES", "Dependencies",
            "ready" if result.returncode == 0 else "critical",
            "OK" if result.returncode == 0 else detail[:300], required=True,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return HealthCheck("dependencies", "DEPENDENCIES", "Dependencies",
                           "critical", type(exc).__name__, required=True)


def collect_health(agent, *, tts=None, stt=None,
                   gpu_probe: Callable[[], dict[str, Any]] = get_gpu_temperature,
                   check_dependencies: bool = True) -> dict[str, Any]:
    """Collect actual component status and calculate a transparent score."""
    checks: list[HealthCheck] = []
    state = agent.state.snapshot()
    core_ok = state.state.value not in {"critical", "offline"}
    checks.append(HealthCheck(
        "core", "JARVİS CORE", "Core", "ready" if core_ok else "critical",
        "RUNNING" if core_ok else state.state.value.upper(), required=True,
    ))
    try:
        system_info = get_system_info()
        ram = get_ram_usage()
        disk = get_disk_health()
        disk_percent = float(system_info.get("disk_used_percent") or 0)
        ram_percent = float(ram.get("ram_percent") or 0)
        checks.extend([
            HealthCheck("cpu", "CPU", "Core", "ready",
                        f"{system_info.get('cpu_percent', 0):.0f}% · "
                        f"{system_info.get('cpu_threads', 0)} threads"),
            HealthCheck("ram", "RAM", "Core",
                        "critical" if ram_percent >= 97 else
                        "warning" if ram_percent >= 90 else "ready",
                        f"{ram_percent:.0f}% · {ram.get('ram_used_gb', 0):.1f} / "
                        f"{ram.get('ram_total_gb', 0):.1f} GB"),
            HealthCheck("disk", "DISK", "Core",
                        "critical" if disk_percent >= 97 else
                        "warning" if disk_percent >= 90 else "ready",
                        f"{disk_percent:.0f}% · SMART {disk.get('smart_overall') or 'UNKNOWN'}"),
        ])
    except Exception as exc:
        checks.append(HealthCheck("system_resources", "SYSTEM RESOURCES", "Core",
                                  "warning", type(exc).__name__))
    checks.extend(_ollama(agent))

    try:
        gpu = gpu_probe()
    except Exception as exc:
        gpu = {"available": False, "note": type(exc).__name__}
    gpu_available = bool(gpu.get("available"))
    checks.append(HealthCheck(
        "gpu", "GPU", "GPU", "ready" if gpu_available else "unknown",
        str(gpu.get("name") or gpu.get("note") or "NOT DETECTED"),
    ))
    checks.append(HealthCheck(
        "vram", "VRAM", "GPU", "ready" if gpu_available else "unknown",
        (f"{float(gpu.get('vram_used_mb') or 0) / 1024:.1f} / "
         f"{float(gpu.get('vram_total_mb') or 0) / 1024:.1f} GB")
        if gpu_available else "UNKNOWN",
    ))
    cuda_status, cuda_value = "unknown", "NOT CHECKED"
    if importlib.util.find_spec("torch") is not None:
        try:
            import torch
            cuda = bool(torch.cuda.is_available())
            cuda_status, cuda_value = ("ready" if cuda else "unknown",
                                       "AVAILABLE" if cuda else "UNAVAILABLE")
        except Exception as exc:
            cuda_value = f"ERROR · {type(exc).__name__}"
    checks.append(HealthCheck("cuda", "CUDA", "GPU", cuda_status, cuda_value))

    checks.extend([
        HealthCheck("python", "PYTHON", "Dependencies", "ready",
                    platform.python_version(), required=True),
        HealthCheck(
            "venv", "VIRTUAL ENVIRONMENT", "Dependencies",
            "ready" if sys.prefix != sys.base_prefix else "warning",
            "ACTIVE" if sys.prefix != sys.base_prefix else "SYSTEM PYTHON",
        ),
        _dependency_check() if check_dependencies else
        HealthCheck("dependencies", "DEPENDENCIES", "Dependencies", "unknown", "NOT CHECKED"),
    ])

    tts_available = bool(tts is not None and getattr(tts, "available", False))
    stt_available = bool(stt is not None and getattr(stt, "available", False))
    checks.extend([
        HealthCheck("stt", "STT", "Voice", "ready" if stt_available else "warning",
                    getattr(stt, "name", "DISABLED") if stt_available else "DISABLED"),
        HealthCheck("tts", "TTS", "Voice", "ready" if tts_available else "warning",
                    getattr(tts, "name", "DISABLED") if tts_available else "DISABLED"),
        # Browser microphones live on the client; claiming a server-side device
        # is available would be invented health data.
        HealthCheck("microphone", "MICROPHONE", "Voice", "unknown",
                    "CLIENT PERMISSION REQUIRED" if stt_available else "STT DISABLED"),
    ])

    wm = agent.working_memory.stats()
    checks.append(HealthCheck(
        "working_memory", "WORKING MEMORY", "Memory", "ready",
        f"READY · {wm.conversation_messages} messages",
    ))
    store = getattr(agent, "memory", None)
    if store is None:
        checks.append(HealthCheck("long_memory", "LONG-TERM MEMORY", "Memory",
                                  "critical", "NOT CONNECTED", required=True))
    else:
        try:
            count = store.fact_count()
            checks.append(HealthCheck("long_memory", "LONG-TERM MEMORY", "Memory",
                                      "ready", f"READY · {count} facts", required=True))
        except Exception as exc:
            checks.append(HealthCheck("long_memory", "LONG-TERM MEMORY", "Memory",
                                      "critical", type(exc).__name__, required=True))
    kb = getattr(agent, "knowledge", None)
    try:
        stats = kb.stats() if kb is not None else None
        checks.append(HealthCheck(
            "vector_backend", "VECTOR / MEMORY BACKEND", "Memory",
            "ready" if stats is not None else "unknown",
            (f"READY · {stats.get('belge', 0)} docs / {stats.get('parca', 0)} chunks"
             if stats is not None else "NOT CONNECTED"),
        ))
    except Exception as exc:
        checks.append(HealthCheck("vector_backend", "VECTOR / MEMORY BACKEND", "Memory",
                                  "warning", type(exc).__name__))

    tool_count = len(agent.registry.all())
    checks.append(HealthCheck("tools", "TOOLS", "Tools",
                              "ready" if tool_count else "critical",
                              f"READY · {tool_count}" if tool_count else "EMPTY",
                              required=True))

    # Yutulan hatalar. Bunların hiçbiri bir turu düşürmedi — düşürmemeleri
    # doğru. Ama düşürmedikleri için hiçbir yerde de görünmüyorlardı:
    # bilgi indeksi kırk kez okunamadıysa JARVIS kırk turda bilgi tabanı
    # yokmuş gibi cevap verir ve tek belirti "bilmiyor" olur.
    yutulan = SAYACLAR.dokum()
    toplam_yutulan = sum(d.adet for d in yutulan)
    checks.append(HealthCheck(
        "yutulan_hata", "SWALLOWED ERRORS", "Core",
        # Tek bir geçici arıza gürültü; YUTULAN_ESIGI tanesi bir örüntü.
        # Sıfırdan büyük her sayıyı uyarıya çevirmek, açılışta bir kez
        # patlayan bir yoklamayı yeniden başlatmaya kadar kalıcı kılardı.
        "ready" if toplam_yutulan < YUTULAN_ESIGI else "warning",
        "NONE" if not toplam_yutulan else
        f"{toplam_yutulan} · " + ", ".join(f"{d.ad}={d.adet}" for d in yutulan[:3]),
    ))

    categories: dict[str, dict[str, Any]] = {}
    for category in ("Core", "LLM", "GPU", "Voice", "Memory", "Tools", "Dependencies"):
        group = [c for c in checks if c.category == category]
        known = [c for c in group if c.status in _POINTS]
        score = round(sum(_POINTS[c.status] for c in known) / len(known)) if known else None
        categories[category] = {
            "score": score,
            "status": ("UNKNOWN" if score is None else
                       "OPERATIONAL" if score >= 85 else
                       "DEGRADED" if score >= 50 else "CRITICAL"),
        }
    scored = [c["score"] for c in categories.values() if c["score"] is not None]
    score = round(sum(scored) / len(scored)) if scored else 0
    required_failure = any(c.required and c.status in {"critical", "unavailable"}
                           for c in checks)
    status = ("CRITICAL" if required_failure or score < 50 else
              "OPERATIONAL" if score >= 85 else "DEGRADED")
    return {
        "score": score, "status": status, "checked_at": time.time(),
        "platform": platform.system(), "categories": categories,
        "checks": [c.as_dict() for c in checks],
        # Tek satırlık özet yukarıdaki denetimde; dökümü ayrı, çünkü
        # panelin göstereceği şey "hangi sayaç" — bir denetim satırına
        # sığmıyor ve her sayaç için ayrı denetim uydurmak puanı bozardı.
        "yutulan": [asdict(d) for d in yutulan],
    }
