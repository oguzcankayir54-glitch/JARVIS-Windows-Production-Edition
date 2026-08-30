"""Bounded Windows capability adapters.

These tools keep platform-specific behavior behind the ToolManager boundary.
Linux/WSL reports an honest unsupported result; no fake Windows state is
returned and no unrestricted shell is introduced.
"""
from __future__ import annotations

import json
import platform
import subprocess
from typing import Any

import psutil

from ..security.permissions import RiskLevel
from .base import Param, Tool, ToolRegistry


def _unsupported(capability: str) -> dict[str, Any]:
    return {"available": False, "platform": platform.system(),
            "capability": capability,
            "note": "Bu Windows yeteneği yalnızca gerçek Windows ortamında kullanılabilir."}


def windows_system() -> dict[str, Any]:
    return {"available": True, "platform": platform.system(),
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "ram_percent": psutil.virtual_memory().percent}


def windows_process(limit: int = 50) -> dict[str, Any]:
    limit = max(1, min(200, int(limit or 50)))
    rows = []
    for proc in psutil.process_iter(["pid", "name", "status"]):
        try:
            rows.append({"pid": proc.info["pid"], "name": proc.info["name"] or "",
                         "status": proc.info["status"] or ""})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        if len(rows) >= limit:
            break
    return {"available": True, "platform": platform.system(), "processes": rows}


def windows_network() -> dict[str, Any]:
    return {"available": True, "platform": platform.system(),
            "interfaces": {name: bool(stats.isup)
                           for name, stats in psutil.net_if_stats().items()}}


def windows_service(name: str) -> dict[str, Any]:
    if platform.system().lower() != "windows":
        return _unsupported("windows_service")
    service = (name or "").strip()
    if not service or len(service) > 128 or any(ch in service for ch in "&|<>\"'"):
        return {"available": False, "hata": "Geçerli bir servis adı gerekli."}
    try:
        completed = subprocess.run(
            ["sc.exe", "query", service], capture_output=True, text=True,
            errors="replace",
            timeout=5, check=False, shell=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"available": False, "hata": f"Servis sorgulanamadı: {type(exc).__name__}"}
    return {"available": completed.returncode == 0, "service": service,
            "output": (completed.stdout or completed.stderr).strip()[:2000]}


_WINDOWS_UPDATE_SCRIPT = r"""
$session = New-Object -ComObject Microsoft.Update.Session
$searcher = $session.CreateUpdateSearcher()
$result = $searcher.Search("IsInstalled=0 and IsHidden=0")
$items = @()
for ($i = 0; $i -lt $result.Updates.Count -and $i -lt 50; $i++) {
  $u = $result.Updates.Item($i)
  $items += [PSCustomObject]@{
    title = $u.Title
    downloaded = [bool]$u.IsDownloaded
    mandatory = [bool]$u.IsMandatory
  }
}
$systemInfo = New-Object -ComObject Microsoft.Update.SystemInfo
[PSCustomObject]@{
  count = [int]$result.Updates.Count
  updates = $items
  reboot_required = [bool]$systemInfo.RebootRequired
} | ConvertTo-Json -Compress -Depth 4
""".strip()


def windows_update_status() -> dict[str, Any]:
    """Query pending updates through the Windows Update Agent COM API."""
    if platform.system().lower() != "windows":
        return _unsupported("windows_update_status") | {
            "user_message": (
                "Eksik Windows güncellemelerini yalnızca gerçek Windows "
                "ortamında sorgulayabilirim."
            ),
        }
    try:
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
             _WINDOWS_UPDATE_SCRIPT],
            capture_output=True, text=True, errors="replace",
            timeout=120, check=False, shell=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(
            f"Windows Update sorgusu çalıştırılamadı: {type(exc).__name__}"
        ) from exc
    if completed.returncode != 0:
        detail = (completed.stderr or "PowerShell hata verdi").strip().splitlines()[-1]
        raise RuntimeError(f"Windows Update sorgusu başarısız: {detail[:240]}")
    try:
        data = json.loads((completed.stdout or "").lstrip("\ufeff").strip())
    except (TypeError, ValueError) as exc:
        raise RuntimeError("Windows Update geçerli bir sonuç döndürmedi") from exc
    count = int(data.get("count", 0))
    updates = list(data.get("updates") or [])
    titles = [str(item.get("title") or "").strip() for item in updates]
    titles = [title for title in titles if title]
    if count:
        shown = "; ".join(titles[:10]) or "başlıklar alınamadı"
        suffix = f" İlk güncellemeler: {shown}."
        if count > 10:
            suffix += f" Ayrıca {count - 10} güncelleme daha var."
        message = f"Windows Update {count} bekleyen güncelleme buldu.{suffix}"
    else:
        message = "Windows Update bekleyen güncelleme bulmadı."
    if data.get("reboot_required"):
        message += " Bekleyen bir yeniden başlatma var."
    return {
        "available": True,
        "count": count,
        "updates": updates,
        "reboot_required": bool(data.get("reboot_required")),
        "user_message": message,
    }


def register_windows_tools(registry: ToolRegistry) -> ToolRegistry:
    registry.register(Tool("windows_system", "Windows sistem durumunu oku.",
                           RiskLevel.LOW, windows_system, params=[]))
    registry.register(Tool("windows_process", "Windows işlemlerini listele.",
                           RiskLevel.LOW, windows_process,
                           params=[Param("limit", "integer", "En fazla işlem sayısı")]))
    registry.register(Tool("windows_network", "Windows ağ arayüzü durumunu oku.",
                           RiskLevel.LOW, windows_network, params=[]))
    registry.register(Tool("windows_service", "Bir Windows servisinin durumunu oku.",
                           RiskLevel.LOW, windows_service,
                           params=[Param("name", "string", "Servis adı", required=True)]))
    registry.register(Tool(
        "windows_update_status",
        "Windows Update Agent ile gerçekten bekleyen güncellemeleri sorgula.",
        RiskLevel.LOW,
        windows_update_status,
        params=[],
    ))
    # These contracts intentionally report unsupported until native adapters
    # and Windows acceptance tests exist; exposing fake state is worse.
    for name, description in (("windows_window", "Windows pencere durumunu oku."),
                              ("windows_audio", "Windows ses durumunu oku."),
                              ("windows_power", "Windows güç durumunu oku."),
                              ("windows_input", "Windows giriş aygıtı durumunu oku.")):
        registry.register(Tool(name, description, RiskLevel.LOW,
                               lambda n=name: _unsupported(n), params=[]))
    return registry
