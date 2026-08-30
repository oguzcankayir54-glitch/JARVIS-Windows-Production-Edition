"""Tarayıcı oynatması ile Neural Core durum göstergesi arasındaki kablo."""
from pathlib import Path


PANEL = (
    Path(__file__).resolve().parent.parent
    / "docs" / "mockups" / "jarvis-panel.html"
)


def _panel() -> str:
    return PANEL.read_text(encoding="utf-8")


def test_real_audio_playing_reports_started_and_end_reports_finished():
    panel = _panel()

    assert 'bu.onplaying = () =>' in panel
    assert 'sesDurumu(id, "started")' in panel
    assert 'bu.onended = kapat' in panel
    assert 'sesDurumu(id, "finished")' in panel


def test_interruption_and_voice_toggle_share_the_finish_path():
    panel = _panel()

    assert 'if (!voiceOn) sesiKes();' in panel
    assert 'window.addEventListener("pagehide", sesiKes)' in panel
    assert 'if (kapat) kapat();' in panel


def test_manual_autoplay_fallback_has_the_same_lifecycle():
    panel = _panel()

    assert "function addPlayButton(url, id)" in panel
    assert "a.onplaying = () =>" in panel
    assert "a.onended = kapat" in panel
