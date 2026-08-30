"""Bounded desktop capabilities with user-verifiable results.

These tools never accept an arbitrary path.  The desktop and screenshot
folders are Windows known folders, screenshot capture happens only after an
explicit tool call, and the image is opened with a fixed allowlisted program.
"""
from __future__ import annotations

import ctypes
import platform
import shutil
from datetime import datetime
from pathlib import Path
from typing import Callable

from ..apps.ac import _calistir
from ..security.permissions import RiskLevel
from ..vision.screenshot import build_screenshot
from .base import Tool, ToolRegistry

_CSIDL_DESKTOPDIRECTORY = 0x10
_CSIDL_MYPICTURES = 0x27


def _known_folder(csidl: int, fallback: str) -> Path | None:
    if platform.system().lower() != "windows":
        return None
    try:
        buffer = ctypes.create_unicode_buffer(32768)
        result = ctypes.windll.shell32.SHGetFolderPathW(  # type: ignore[attr-defined]
            None, csidl, None, 0, buffer,
        )
        if result == 0 and buffer.value:
            return Path(buffer.value)
    except (AttributeError, OSError, ValueError):
        pass
    return Path.home() / fallback


def _desktop_path() -> Path | None:
    return _known_folder(_CSIDL_DESKTOPDIRECTORY, "Desktop")


def _pictures_path() -> Path | None:
    return _known_folder(_CSIDL_MYPICTURES, "Pictures")


def masaustu_listele() -> dict:
    desktop = _desktop_path()
    if desktop is None:
        return {
            "available": False,
            "user_message": "Masaüstü içeriğini yalnızca gerçek Windows ortamında okuyabilirim.",
        }
    if not desktop.is_dir():
        return {
            "available": False,
            "path": str(desktop),
            "user_message": f"Windows masaüstü klasörünü bulamadım: {desktop}",
        }

    items = []
    for child in sorted(desktop.iterdir(), key=lambda p: p.name.casefold())[:200]:
        try:
            items.append({
                "name": child.name,
                "type": "klasör" if child.is_dir() else "dosya",
                "size": child.stat().st_size if child.is_file() else None,
            })
        except OSError:
            continue
    names = ", ".join(item["name"] for item in items)
    message = (
        f"Masaüstünde {len(items)} öğe var: {names}."
        if items else f"Masaüstü klasörü boş: {desktop}"
    )
    return {
        "available": True,
        "path": str(desktop),
        "count": len(items),
        "items": items,
        "user_message": message,
    }


def _open_image(path: Path) -> bool:
    executable = shutil.which("mspaint.exe")
    return bool(executable and _calistir([executable, str(path)]))


class ScreenshotController:
    """Capture one explicit screenshot, save it locally and open it."""

    def __init__(self, *, enabled: bool,
                 provider_factory: Callable[..., object] = build_screenshot,
                 output_dir: Path | None = None,
                 opener: Callable[[Path], bool] = _open_image) -> None:
        self.enabled = bool(enabled)
        self.provider_factory = provider_factory
        self.output_dir = output_dir
        self.opener = opener
        self.last_path: Path | None = None

    def capture_and_open(self) -> dict:
        if not self.enabled:
            return {
                "captured": False,
                "opened": False,
                "user_message": (
                    "Ekran görüntüsü özelliği kapalı. Açmak için .env dosyasına "
                    "JARVIS_SCREENSHOT_ENABLED=true yazıp JARVIS'i yeniden başlatın."
                ),
            }
        provider = self.provider_factory(enabled=True)
        if not getattr(provider, "available", False):
            reason = str(getattr(provider, "reason", "ekran görüntüsü sağlayıcısı hazır değil"))
            return {
                "captured": False,
                "opened": False,
                "user_message": f"Ekran görüntüsü alamadım: {reason}",
            }
        pictures = _pictures_path()
        directory = self.output_dir or (
            pictures / "JARVIS Screenshots" if pictures is not None else None
        )
        if directory is None:
            return {
                "captured": False,
                "opened": False,
                "user_message": "Ekran görüntüsünü yalnızca gerçek Windows ortamında kaydedebilirim.",
            }
        data = bytes(provider.capture())
        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
            return {
                "captured": False,
                "opened": False,
                "user_message": "Ekran görüntüsü sağlayıcısı geçerli bir PNG üretmedi.",
            }
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / datetime.now().strftime("JARVIS-%Y%m%d-%H%M%S-%f.png")
        target.write_bytes(data)
        self.last_path = target
        opened = bool(self.opener(target))
        return {
            "captured": True,
            "opened": opened,
            "path": str(target),
            "user_message": (
                f"Ekran görüntüsünü aldım ve açtım: {target}"
                if opened else
                f"Ekran görüntüsünü kaydettim ancak açamadım: {target}"
            ),
        }

    def last_location(self) -> dict:
        if self.last_path is None:
            return {
                "found": False,
                "user_message": "Bu oturumda kaydedilmiş bir ekran görüntüsü yok.",
            }
        exists = self.last_path.is_file()
        return {
            "found": exists,
            "path": str(self.last_path),
            "user_message": (
                f"Son ekran görüntüsü burada: {self.last_path}"
                if exists else
                f"Son ekran görüntüsü artık bu konumda bulunmuyor: {self.last_path}"
            ),
        }


class CameraController:
    """Report the real backend state; browser permission remains a user act."""

    def __init__(self, reason: str = "Kamera panel sunucusuna bağlı değil.") -> None:
        self.provider = None
        self.reason = reason

    def bind(self, provider) -> None:
        self.provider = provider
        self.reason = str(getattr(provider, "reason", self.reason))

    def status(self) -> dict:
        available = bool(self.provider is not None
                         and getattr(self.provider, "available", False))
        if available:
            message = (
                "Kamera analizi hazır. Kamerayı gerçekten açmak için panelde "
                "KAMERAYI AÇ düğmesine basın ve tarayıcı kamera iznini onaylayın."
            )
        else:
            message = f"Kamerayı etkinleştiremedim: {self.reason}"
        return {"available": available, "active": False, "user_message": message}


def register_desktop_tools(registry: ToolRegistry, *, screenshot: ScreenshotController,
                           camera: CameraController) -> ToolRegistry:
    registry.register(Tool(
        name="masaustu_listele",
        description="Windows masaüstündeki gerçek dosya ve klasör adlarını listele.",
        risk=RiskLevel.LOW,
        func=masaustu_listele,
        params=[],
    ))
    registry.register(Tool(
        name="ekran_goruntusu_al_ac",
        description="Masaüstünün ekran görüntüsünü yerel diske kaydet ve Paint ile aç.",
        risk=RiskLevel.MEDIUM,
        func=screenshot.capture_and_open,
        params=[],
    ))
    registry.register(Tool(
        name="son_ekran_goruntusu",
        description="Bu oturumda en son kaydedilen ekran görüntüsünün gerçek yolunu getir.",
        risk=RiskLevel.LOW,
        func=screenshot.last_location,
        params=[],
    ))
    registry.register(Tool(
        name="kamera_kontrol",
        description="Kamera analizinin gerçek durumunu ve gereken kullanıcı adımını bildir.",
        risk=RiskLevel.LOW,
        func=camera.status,
        params=[],
    ))
    return registry
