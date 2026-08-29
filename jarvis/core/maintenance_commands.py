"""Platform-aware allowlist for the panel's maintenance command center."""
from __future__ import annotations

import platform
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class MaintenanceCommand:
    id: str
    label: str
    command: str
    argv: tuple[str, ...]
    run_allowed: bool = True
    timeout: float = 15.0

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "label": self.label, "command": self.command,
                "run_allowed": self.run_allowed}


def command_catalog(system: str | None = None) -> tuple[MaintenanceCommand, ...]:
    system = system or platform.system()
    py = sys.executable
    if system == "Windows":
        return (
            MaintenanceCommand("jarvis_start", "JARVİS BAŞLAT", "py -3.11 -m jarvis", (), False),
            MaintenanceCommand("ollama_list", "OLLAMA MODELLERİ", "ollama list", ("ollama", "list")),
            MaintenanceCommand("ollama_status", "OLLAMA DURUM", "Get-Process ollama", ("powershell", "-NoProfile", "-Command", "Get-Process ollama")),
            MaintenanceCommand("ollama_start", "OLLAMA BAŞLAT", "Start-Process ollama", (), False),
            MaintenanceCommand("gpu", "GPU KONTROL", "nvidia-smi", ("nvidia-smi",)),
            MaintenanceCommand("python_version", "PYTHON SÜRÜMÜ", "python --version", (py, "--version")),
            MaintenanceCommand("active_python", "AKTİF PYTHON", "Get-Command python", ("powershell", "-NoProfile", "-Command", "Get-Command python")),
            MaintenanceCommand("pip_version", "PIP", "python -m pip --version", (py, "-m", "pip", "--version")),
            MaintenanceCommand("pip_check", "BAĞIMLILIK KONTROLÜ", "python -m pip check", (py, "-m", "pip", "check"), timeout=30),
            MaintenanceCommand("jarvis_process", "JARVİS PROCESS KONTROL", "Get-Process python", ("powershell", "-NoProfile", "-Command", "Get-Process python")),
            MaintenanceCommand("logs", "LOG TAKİBİ", "Get-Content logs\\jarvis.log -Tail 100 -Wait", (), False),
        )
    return (
        MaintenanceCommand("jarvis_start", "JARVİS BAŞLAT", "python -m jarvis", (), False),
        MaintenanceCommand("ollama_list", "OLLAMA MODELLERİ", "ollama list", ("ollama", "list")),
        MaintenanceCommand("ollama_status", "OLLAMA DURUM", "systemctl status ollama", ("systemctl", "status", "ollama")),
        MaintenanceCommand("ollama_start", "OLLAMA BAŞLAT", "sudo systemctl start ollama", (), False),
        MaintenanceCommand("ollama_restart", "OLLAMA YENİDEN BAŞLAT", "sudo systemctl restart ollama", (), False),
        MaintenanceCommand("gpu", "GPU KONTROL", "nvidia-smi", ("nvidia-smi",)),
        MaintenanceCommand("python_version", "PYTHON SÜRÜMÜ", "python --version", (py, "--version")),
        MaintenanceCommand("active_python", "AKTİF PYTHON", "which python", ("which", "python")),
        MaintenanceCommand("pip_version", "PIP", "python -m pip --version", (py, "-m", "pip", "--version")),
        MaintenanceCommand("pip_check", "BAĞIMLILIK KONTROLÜ", "python -m pip check", (py, "-m", "pip", "check"), timeout=30),
        MaintenanceCommand("jarvis_process", "JARVİS PROCESS KONTROL", "pgrep -af jarvis", ("pgrep", "-af", "jarvis")),
        MaintenanceCommand("logs", "LOG TAKİBİ", "tail -f logs/jarvis.log", (), False),
    )


def run_maintenance(command_id: str, *, system: str | None = None,
                    cwd: Path | str | None = None) -> dict[str, Any]:
    catalog = {item.id: item for item in command_catalog(system)}
    item = catalog.get((command_id or "").strip())
    if item is None:
        raise ValueError("bilinmeyen bakım komutu")
    if not item.run_allowed or not item.argv:
        raise PermissionError("bu komut panelden otomatik çalıştırılamaz")
    started = time.perf_counter()
    try:
        result = subprocess.run(
            item.argv, cwd=str(cwd) if cwd else None, capture_output=True,
            text=True, timeout=item.timeout, shell=False,
        )
        return {
            "id": item.id, "command": item.command, "returncode": result.returncode,
            "stdout": result.stdout[-20_000:], "stderr": result.stderr[-20_000:],
            "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            "ok": result.returncode == 0, "finished_at": time.time(),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "id": item.id, "command": item.command, "returncode": None,
            "stdout": (exc.stdout or "")[-20_000:] if isinstance(exc.stdout, str) else "",
            "stderr": "komut zaman aşımına uğradı", "duration_ms": item.timeout * 1000,
            "ok": False, "finished_at": time.time(),
        }
    except OSError as exc:
        return {
            "id": item.id, "command": item.command, "returncode": None,
            "stdout": "", "stderr": f"{type(exc).__name__}: {exc}",
            "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            "ok": False, "finished_at": time.time(),
        }
