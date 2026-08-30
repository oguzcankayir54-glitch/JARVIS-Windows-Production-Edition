from types import SimpleNamespace

import pytest

from jarvis.tools import system_tools, windows_tools


def test_windows_update_reports_only_parsed_real_result(monkeypatch):
    monkeypatch.setattr(windows_tools.platform, "system", lambda: "Windows")
    monkeypatch.setattr(
        windows_tools.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0,
            stdout=(
                '{"count":2,"updates":['
                '{"title":"KB Gerçek 1","downloaded":true,"mandatory":false},'
                '{"title":"KB Gerçek 2","downloaded":false,"mandatory":true}'
                '],"reboot_required":true}'
            ),
            stderr="",
        ),
    )

    result = windows_tools.windows_update_status()

    assert result["available"] is True
    assert result["count"] == 2
    assert result["reboot_required"] is True
    assert "KB Gerçek 1" in result["user_message"]
    assert "yeniden başlatma" in result["user_message"]


def test_windows_update_failure_is_not_converted_to_success(monkeypatch):
    monkeypatch.setattr(windows_tools.platform, "system", lambda: "Windows")
    monkeypatch.setattr(
        windows_tools.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=1, stdout="", stderr="COM erişimi reddedildi",
        ),
    )

    with pytest.raises(RuntimeError, match="başarısız"):
        windows_tools.windows_update_status()


def test_windows_update_is_honest_off_windows(monkeypatch):
    monkeypatch.setattr(windows_tools.platform, "system", lambda: "Linux")

    result = windows_tools.windows_update_status()

    assert result["available"] is False
    assert "yalnızca gerçek Windows" in result["user_message"]


def test_system_summary_uses_measured_telemetry(monkeypatch):
    monkeypatch.setattr(system_tools.platform, "node", lambda: "GERCEK-PC")
    monkeypatch.setattr(system_tools, "get_system_info", lambda: {
        "cpu_cores": 6,
        "cpu_threads": 12,
        "ram_total_gb": 31.9,
    })
    monkeypatch.setattr(system_tools, "get_gpu_temperature", lambda: {
        "available": True,
        "name": "Gerçek GPU",
        "vram_total_mb": 8192,
    })

    result = system_tools.get_system_summary()

    assert result["hostname"] == "GERCEK-PC"
    assert result["user_message"] == (
        "Doğrulanan sistem bilgileri: CPU 6 çekirdek / 12 iş parçacığı; "
        "31.9 GB RAM; GPU Gerçek GPU (8 GB VRAM)."
    )
