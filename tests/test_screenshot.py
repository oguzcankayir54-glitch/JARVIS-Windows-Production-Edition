from __future__ import annotations

import base64
from subprocess import CompletedProcess

import pytest

from jarvis.vision.detect import VisionError
from jarvis.vision.screenshot import WslWindowsScreenshot, build_screenshot


PNG = b"\x89PNG\r\n\x1a\ncontent"


def test_wsl_provider_decodes_in_memory_png(monkeypatch):
    seen = {}

    def run(command, **kwargs):
        seen["command"] = command
        seen["kwargs"] = kwargs
        return CompletedProcess(command, 0, base64.b64encode(PNG).decode(), "")

    monkeypatch.setattr("jarvis.vision.screenshot.subprocess.run", run)
    provider = WslWindowsScreenshot("powershell.exe")
    assert provider.capture() == PNG
    assert seen["command"][0] == "powershell.exe"
    assert seen["kwargs"]["timeout"] == 20


def test_wsl_provider_rejects_failed_or_invalid_output(monkeypatch):
    provider = WslWindowsScreenshot()
    monkeypatch.setattr(
        "jarvis.vision.screenshot.subprocess.run",
        lambda *a, **k: CompletedProcess(a, 1, "", "capture failed"),
    )
    with pytest.raises(VisionError, match="capture failed"):
        provider.capture()
    monkeypatch.setattr(
        "jarvis.vision.screenshot.subprocess.run",
        lambda *a, **k: CompletedProcess(a, 0, "not-base64", ""),
    )
    with pytest.raises(VisionError, match="geçerli PNG"):
        provider.capture()


def test_builder_selects_windows_provider_under_wsl(monkeypatch):
    monkeypatch.setattr("jarvis.vision.screenshot._running_under_wsl", lambda: True)
    monkeypatch.setattr("jarvis.vision.screenshot.shutil.which", lambda _: "powershell.exe")
    assert isinstance(build_screenshot(True), WslWindowsScreenshot)


def test_builder_stays_disabled_without_explicit_consent():
    provider = build_screenshot(False)
    assert provider.available is False
