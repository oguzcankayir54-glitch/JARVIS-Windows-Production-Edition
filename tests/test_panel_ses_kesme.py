"""Panelde sözünü kesme — telin varlığı.

Terminal tarafı ``jarvis/voice/tts.py`` içinde çözüldü ve orada gerçek
davranış sınanıyor (``tests/test_ses_kesme.py``). Tarayıcı tarafı bir
mockup HTML dosyasının içindeki JavaScript; burada sınanabilecek olan
davranış değil, **bağlantının kurulu olduğu.**

Zayıf bir test olduğunun farkındayız. Ama bu depoda tam olarak bu tür
bir bağlantı bir kez sessizce koptu: ``duyuru`` olayının SSE dinleyicisi
bir birleştirmede düştü, sunucu yayınlamaya devam etti, panel duymadı ve
hiçbir test kırmızı olmadı. Kesme tetikleyicileri de aynı biçimde
kaybolabilir — ve kaybolduğunda tek belirti, kimsenin şikâyet etmediği
bir eksiklik olur.

Asıl düzeltilen hata burada görünmüyor ama sebebi yazıya geçsin:
``audio.pause()`` ne ``ended`` ne ``error`` olayını tetikliyor. Eller
serbest sohbet ``await speak(...)`` ile konuşmanın bitmesini bekliyordu;
oynatma yalnızca duraklatılırsa o bekleyiş **hiç bitmiyordu** —
``mesgul`` true'da kalıyor, ``kayitBasla()`` bir daha çalışmıyor, yani
sohbet sayfa yenilenene kadar ölüyordu. Bu, proaktif sesli duyuru bir
cevabın üstüne bindiğinde gerçekten tetiklenebilir bir yoldu.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

PANEL = Path(__file__).resolve().parent.parent / "docs" / "mockups" / "jarvis-panel.html"


@pytest.fixture(scope="module")
def panel() -> str:
    assert PANEL.is_file(), f"{PANEL} yok; bu testler hiçbir şey ölçmüyor."
    return PANEL.read_text(encoding="utf-8")


def test_the_cut_function_exists(panel):
    assert re.search(r"function\s+sesiKes\s*\(", panel), (
        "sesiKes() tanımı yok — panelde sözünü kesmenin tek yolu buydu."
    )


def test_typing_cuts_the_speech(panel):
    """Asıl tetikleyici: yazmaya başlamak susturuyor."""
    assert re.search(r'input\.addEventListener\(\s*"input"\s*,\s*sesiKes', panel), (
        "Girdi kutusu sesiKes'e bağlı değil; konuşurken yazmak artık susturmuyor."
    )


def test_escape_cuts_the_speech(panel):
    """Yazmak istemeyene de bir yol kalmalı."""
    kesit = re.search(r'"Escape"[^\n]*\n?[^\n]*sesiKes', panel)
    assert kesit, "Escape sesiKes'e bağlı değil."


def test_sending_a_message_cuts_the_speech(panel):
    """Gönderilen yeni bir mesaj, önceki cevabı geçersiz kılar."""
    govde = panel.split('form.addEventListener("submit"', 1)
    assert len(govde) == 2, "submit işleyicisi bulunamadı."
    assert "sesiKes()" in govde[1][:400], (
        "submit işleyicisinin başında sesiKes() çağrılmıyor."
    )


def test_a_new_playback_closes_the_previous_one_properly(panel):
    """En kritik satır.

    Yeni bir oynatma başlarken eskisi yalnızca ``pause()`` edilirse, o
    eskiyi bekleyen tur sonsuza kadar asılı kalıyor. ``sesiKes()``
    çağrılması, bekleyen sözün de kapatılmasını sağlıyor.
    """
    assert not re.search(r"if\s*\(\s*audio\s*\)\s*\{\s*audio\.pause\(\)\s*;\s*audio\s*=\s*null", panel), (
        "speak() içinde ham 'audio.pause(); audio = null' kalıbı geri gelmiş. "
        "Bu, oynatmayı bekleyen turu askıda bırakıyor — sesiKes() kullanılmalı."
    )


def test_the_finish_promise_can_be_resolved_by_a_cut(panel):
    """Kesme, bitiş sözünü de çözebilmeli."""
    assert "sesiBitir" in panel, (
        "sesiBitir yok; kesilen oynatmanın bitiş sözünü çözecek bir şey kalmamış."
    )
