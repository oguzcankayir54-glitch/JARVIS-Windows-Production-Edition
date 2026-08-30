from pathlib import Path

from jarvis.tools import desktop_tools
from jarvis.tools.desktop_tools import CameraController, ScreenshotController


PNG = b"\x89PNG\r\n\x1a\n" + b"test-pixels"


class _Screenshot:
    available = True

    def capture(self):
        return PNG


def test_desktop_listing_uses_real_directory_contents(tmp_path, monkeypatch):
    (tmp_path / "Gercek-Proje").mkdir()
    (tmp_path / "gercek.txt").write_text("icerik", encoding="utf-8")
    monkeypatch.setattr(desktop_tools, "_desktop_path", lambda: tmp_path)

    result = desktop_tools.masaustu_listele()

    assert result["available"] is True
    assert result["count"] == 2
    assert {item["name"] for item in result["items"]} == {
        "Gercek-Proje", "gercek.txt",
    }
    assert "Temmuz_PPT.pptx" not in result["user_message"]


def test_screenshot_disabled_reports_the_exact_setting():
    result = ScreenshotController(enabled=False).capture_and_open()

    assert result["captured"] is False
    assert result["opened"] is False
    assert "JARVIS_SCREENSHOT_ENABLED=true" in result["user_message"]


def test_screenshot_is_saved_opened_and_remembered(tmp_path):
    opened = []
    controller = ScreenshotController(
        enabled=True,
        provider_factory=lambda **_kwargs: _Screenshot(),
        output_dir=tmp_path,
        opener=lambda path: opened.append(path) or True,
    )

    result = controller.capture_and_open()
    location = controller.last_location()

    path = Path(result["path"])
    assert result["captured"] is True and result["opened"] is True
    assert path.read_bytes() == PNG
    assert opened == [path]
    assert location["found"] is True
    assert location["path"] == str(path)
    assert str(path) in result["user_message"]


def test_screenshot_never_claims_it_opened_when_opener_failed(tmp_path):
    controller = ScreenshotController(
        enabled=True,
        provider_factory=lambda **_kwargs: _Screenshot(),
        output_dir=tmp_path,
        opener=lambda _path: False,
    )

    result = controller.capture_and_open()

    assert result["captured"] is True
    assert result["opened"] is False
    assert "kaydettim ancak açamadım" in result["user_message"]


def test_camera_status_never_claims_browser_camera_is_active():
    controller = CameraController("kamera kapalı")

    unavailable = controller.status()
    controller.bind(type("Vision", (), {"available": True, "reason": ""})())
    ready = controller.status()

    assert unavailable == {
        "available": False,
        "active": False,
        "user_message": "Kamerayı etkinleştiremedim: kamera kapalı",
    }
    assert ready["available"] is True
    assert ready["active"] is False
    assert "KAMERAYI AÇ" in ready["user_message"]
    assert "iznini" in ready["user_message"]
