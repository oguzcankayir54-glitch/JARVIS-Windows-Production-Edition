"""Explicit, local desktop screenshot source; pixels are never persisted."""
from __future__ import annotations

import base64
import io
import platform
import shutil
import subprocess
import threading
from typing import Protocol

from .detect import MAX_FRAME_BYTES, VisionError


class ScreenshotProvider(Protocol):
    name: str
    available: bool

    def capture(self) -> bytes: ...


class NullScreenshot:
    name = "yok"
    available = False

    def __init__(self, reason: str = "Masaüstü görüntüsü kapalı.") -> None:
        self.reason = reason

    def capture(self) -> bytes:
        raise VisionError(self.reason)


class PillowScreenshot:
    name = "pillow-imagegrab"
    available = True

    def __init__(self) -> None:
        self._lock = threading.Lock()

    def capture(self) -> bytes:
        try:
            from PIL import ImageGrab
        except ImportError as exc:
            raise VisionError("Screenshot için Pillow gerekli.") from exc
        try:
            with self._lock:
                image = ImageGrab.grab(all_screens=True)
                target = io.BytesIO()
                image.save(target, format="PNG", optimize=True)
                data = target.getvalue()
                image.close()
        except Exception as exc:
            raise VisionError(
                f"Masaüstü görüntüsü alınamadı: {type(exc).__name__}"
            ) from exc
        if not data or len(data) > MAX_FRAME_BYTES:
            raise VisionError("Screenshot boş veya güvenli boyut sınırını aşıyor.")
        return data


_WINDOWS_CAPTURE_SCRIPT = r"""
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
$bounds = [System.Windows.Forms.SystemInformation]::VirtualScreen
$bitmap = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$stream = New-Object System.IO.MemoryStream
try {
  $graphics.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
  $bitmap.Save($stream, [System.Drawing.Imaging.ImageFormat]::Png)
  [Convert]::ToBase64String($stream.ToArray())
} finally {
  $stream.Dispose()
  $graphics.Dispose()
  $bitmap.Dispose()
}
""".strip()


class WslWindowsScreenshot:
    """Capture the Windows virtual desktop from WSL without a temporary file."""

    name = "windows-powershell"
    available = True

    def __init__(self, executable: str = "powershell.exe") -> None:
        self.executable = executable
        self._lock = threading.Lock()

    def capture(self) -> bytes:
        try:
            with self._lock:
                result = subprocess.run(
                    [self.executable, "-NoProfile", "-NonInteractive", "-Command",
                     _WINDOWS_CAPTURE_SCRIPT],
                    capture_output=True, text=True, timeout=20, check=False,
                )
        except (OSError, subprocess.SubprocessError) as exc:
            raise VisionError(
                f"Windows masaüstü görüntüsü alınamadı: {type(exc).__name__}"
            ) from exc
        if result.returncode != 0:
            detail = (result.stderr or "PowerShell hata verdi.").strip().splitlines()[-1]
            raise VisionError(f"Windows masaüstü görüntüsü alınamadı: {detail[:240]}")
        try:
            data = base64.b64decode(result.stdout.strip(), validate=True)
        except (ValueError, base64.binascii.Error) as exc:
            raise VisionError("Windows screenshot çıktısı geçerli PNG verisi değil.") from exc
        if (not data or len(data) > MAX_FRAME_BYTES
                or not data.startswith(b"\x89PNG\r\n\x1a\n")):
            raise VisionError("Screenshot boş, geçersiz veya güvenli boyut sınırını aşıyor.")
        return data


def _running_under_wsl() -> bool:
    return platform.system() == "Linux" and "microsoft" in platform.release().lower()


def build_screenshot(enabled: bool = False):
    if not enabled:
        return NullScreenshot("Screenshot kapalı (JARVIS_SCREENSHOT_ENABLED=false).")
    if _running_under_wsl():
        executable = shutil.which("powershell.exe")
        if executable:
            return WslWindowsScreenshot(executable)
        return NullScreenshot("WSL screenshot hazır değil: powershell.exe bulunamadı.")
    try:
        from PIL import ImageGrab  # noqa: F401
    except ImportError:
        return NullScreenshot("Screenshot hazır değil: Pillow gerekli.")
    return PillowScreenshot()
