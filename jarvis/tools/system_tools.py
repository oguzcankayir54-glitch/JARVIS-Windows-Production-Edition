"""Host-machine telemetry tools (all LOW risk, read-only).

V1 target is the machine J.A.R.V.I.S. runs on (decision D1). Everything here
degrades gracefully: if a sensor, GPU, or CLI tool is unavailable, the tool
returns a clear "not available" note instead of raising — so the same code
runs on a workstation with an RTX 3080 and inside a bare container.
"""
from __future__ import annotations

import shutil
import subprocess
from typing import Any

import psutil

from ..security.permissions import RiskLevel
from .base import Param, Tool, ToolRegistry


def _run(cmd: list[str], timeout: float = 4.0) -> str | None:
    exe = shutil.which(cmd[0])
    if exe is None:
        return None
    try:
        out = subprocess.run(
            [exe, *cmd[1:]], capture_output=True, text=True, timeout=timeout, check=False
        )
        return out.stdout.strip() if out.returncode == 0 else None
    except (subprocess.SubprocessError, OSError):
        return None


def get_system_info() -> dict[str, Any]:
    """High-level snapshot of the host: CPU, RAM and disk headline numbers."""
    vm = psutil.virtual_memory()
    du = psutil.disk_usage("/")
    return {
        "cpu_percent": psutil.cpu_percent(interval=0.3),
        "cpu_cores": psutil.cpu_count(logical=False),
        "cpu_threads": psutil.cpu_count(logical=True),
        "ram_used_gb": round(vm.used / 1e9, 1),
        "ram_total_gb": round(vm.total / 1e9, 1),
        "ram_percent": vm.percent,
        "disk_used_percent": du.percent,
    }


def get_cpu_temperature() -> dict[str, Any]:
    """CPU temperature in °C, via psutil sensors (falls back cleanly)."""
    fn = getattr(psutil, "sensors_temperatures", None)
    if fn:
        temps = fn() or {}
        for key in ("k10temp", "coretemp", "cpu_thermal", "acpitz"):
            if key in temps and temps[key]:
                cur = temps[key][0].current
                return {"available": True, "cpu_temp_c": round(cur, 1), "source": key}
    return {"available": False, "note": "CPU sıcaklık sensörü bulunamadı (donanıma/izne bağlı)."}


def get_gpu_temperature() -> dict[str, Any]:
    """NVIDIA GPU temperature/usage/VRAM via nvidia-smi (falls back cleanly)."""
    out = _run([
        "nvidia-smi",
        "--query-gpu=name,temperature.gpu,utilization.gpu,memory.used,memory.total",
        "--format=csv,noheader,nounits",
    ])
    if not out:
        return {"available": False, "note": "nvidia-smi bulunamadı veya NVIDIA GPU yok."}
    name, temp, util, mem_used, mem_total = (x.strip() for x in out.splitlines()[0].split(","))
    return {
        "available": True,
        "name": name,
        "gpu_temp_c": float(temp),
        "gpu_util_percent": float(util),
        "vram_used_mb": float(mem_used),
        "vram_total_mb": float(mem_total),
    }


def get_ram_usage() -> dict[str, Any]:
    vm = psutil.virtual_memory()
    sw = psutil.swap_memory()
    return {
        "ram_used_gb": round(vm.used / 1e9, 2),
        "ram_total_gb": round(vm.total / 1e9, 2),
        "ram_percent": vm.percent,
        "swap_used_gb": round(sw.used / 1e9, 2),
    }


def get_disk_health() -> dict[str, Any]:
    """Per-partition usage plus SMART overall-health when smartctl is present."""
    parts = []
    for p in psutil.disk_partitions(all=False):
        try:
            du = psutil.disk_usage(p.mountpoint)
        except (PermissionError, OSError):
            continue
        parts.append({
            "device": p.device,
            "mount": p.mountpoint,
            "fstype": p.fstype,
            "used_percent": du.percent,
            "total_gb": round(du.total / 1e9, 1),
        })
    smart = _run(["smartctl", "-H", "/dev/sda"])
    smart_status = "unavailable"
    if smart:
        smart_status = "PASSED" if "PASSED" in smart.upper() else "CHECK"
    return {"partitions": parts, "smart_overall": smart_status}


def register_system_tools(registry: ToolRegistry) -> ToolRegistry:
    """Register all host telemetry tools (LOW risk) into ``registry``."""
    registry.register(Tool(
        name="get_system_info", description="Host CPU/RAM/disk özet bilgisini oku.",
        risk=RiskLevel.LOW, func=get_system_info, params=[]))
    registry.register(Tool(
        name="get_cpu_temperature", description="CPU sıcaklığını (°C) oku.",
        risk=RiskLevel.LOW, func=get_cpu_temperature, params=[]))
    registry.register(Tool(
        name="get_gpu_temperature", description="NVIDIA GPU sıcaklık/kullanım/VRAM oku.",
        risk=RiskLevel.LOW, func=get_gpu_temperature, params=[]))
    registry.register(Tool(
        name="get_ram_usage", description="RAM ve swap kullanımını oku.",
        risk=RiskLevel.LOW, func=get_ram_usage, params=[]))
    registry.register(Tool(
        name="get_disk_health", description="Disk kullanımı ve SMART genel sağlık durumunu oku.",
        risk=RiskLevel.LOW, func=get_disk_health, params=[]))
    return registry
