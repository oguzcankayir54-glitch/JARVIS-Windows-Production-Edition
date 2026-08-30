"""Sözünü kesebilmek.

Ölçüldü: 250 token'lık gerçekçi bir cevap 3,80 saniye konuşuyor. Akış
eklendiğinden beri ilk kelime hızlı geliyor, ama JARVIS soruyu yanlış
anladıysa o 3,80 saniyenin tamamını dinlemekten başka yol yoktu —
``play_stream`` bitene kadar bloke ediyordu.

Buradaki testler gerçek bir oynatıcı çalıştırmıyor; ölçtükleri şey
davranış: parçaların tamamı gidiyor mu, kesince oynatıcı GERÇEKTEN
ölüyor mu, ve kesildikten sonra sentezleyiciden parça çekilmeye devam
ediliyor mu. Sonuncusu görünmez ama pahalı: kesilen bir cümlenin geri
kalanını üretmek GPU'yu bir sonraki cevabın önünde meşgul tutar.
"""
from __future__ import annotations

import subprocess
import threading
import time

import pytest

from jarvis.voice import tts as mod
from jarvis.voice.tts import TTSError, play_stream, play_stream_kesilebilir


class _SahteBoru:
    """``proc.stdin`` yerine geçen, yazılanı biriktiren boru."""

    def __init__(self) -> None:
        self.veri = bytearray()
        self.closed = False

    def write(self, parca: bytes) -> int:
        if self.closed:
            raise ValueError("kapalı boruya yazıldı")
        self.veri += parca
        return len(parca)

    def close(self) -> None:
        self.closed = True


class _SahteSurec:
    """Öldürülene kadar yaşayan sahte oynatıcı süreci."""

    def __init__(self) -> None:
        self.stdin = _SahteBoru()
        self.olduruldu = False
        self._bitti = threading.Event()

    def poll(self):
        return 0 if self._bitti.is_set() else None

    def kill(self) -> None:
        self.olduruldu = True
        self._bitti.set()

    def bitir(self) -> None:
        """Oynatıcı kendiliğinden bitti (ses sonuna geldi)."""
        self._bitti.set()

    def wait(self, timeout=None):
        if not self._bitti.wait(timeout=timeout):
            raise subprocess.TimeoutExpired("ffplay", timeout)
        return 0


@pytest.fixture
def surec(monkeypatch):
    """Oynatıcıyı sahteyle değiştir; hiçbir test ses çıkarmasın."""
    sahte = _SahteSurec()
    monkeypatch.setattr(mod, "find_player", lambda: ("ffplay", []))
    monkeypatch.setattr(mod.subprocess, "Popen", lambda *a, **k: sahte)
    return sahte


# ---------------- temel ----------------

def test_no_player_means_no_playback(monkeypatch):
    """Oynatıcı kurulu değilse çağıran taraf sesi dosyaya yazabilmeli."""
    monkeypatch.setattr(mod, "find_player", lambda: None)
    assert play_stream_kesilebilir(iter([b"ses"])) is None
    assert play_stream(iter([b"ses"])) is False


def test_every_chunk_reaches_the_player(surec):
    oynatim = play_stream_kesilebilir(iter([b"bir", b"iki", b"uc"]))
    surec.bitir()
    oynatim.bekle(timeout=2)
    assert bytes(surec.stdin.veri) == b"birikiuc"


def test_playing_does_not_block_the_caller(surec):
    """Kesmenin ön koşulu: çağıran taraf konuşma biterken geri dönüyor."""
    yavas_akiyor = threading.Event()

    def yavas():
        yield b"ilk"
        yavas_akiyor.set()
        time.sleep(5)  # kesilmezse test zaman aşımına uğrar
        yield b"asla"

    basladi = time.monotonic()
    oynatim = play_stream_kesilebilir(yavas())
    gecen = time.monotonic() - basladi
    assert gecen < 1.0, f"oynatma çağrısı {gecen:.2f} sn bloke etti"
    assert yavas_akiyor.wait(timeout=2)
    oynatim.kes()


# ---------------- kesme ----------------

def test_cutting_kills_the_player_now(surec):
    """Yarım saniye daha konuşan bir asistan kesilmemiş sayılır."""
    oynatim = play_stream_kesilebilir(iter([b"uzun bir cevap"]))
    oynatim.kes()
    assert surec.olduruldu
    assert oynatim.kesildi


def test_cutting_stops_pulling_from_the_synthesizer(surec):
    """Kesilen cümlenin geri kalanı üretilmemeli — GPU bir sonraki
    cevabın önünde meşgul kalmasın."""
    uretilen = []
    devam = threading.Event()

    def sayan():
        for i in range(50):
            uretilen.append(i)
            yield b"x" * 1000
            if i == 0:
                devam.set()
                time.sleep(0.05)

    oynatim = play_stream_kesilebilir(sayan())
    assert devam.wait(timeout=2)
    oynatim.kes()
    time.sleep(0.1)
    assert len(uretilen) < 50, "kesildikten sonra da parça çekilmeye devam etti"


def test_a_playback_that_finished_on_its_own_is_not_cut(surec):
    oynatim = play_stream_kesilebilir(iter([b"kisa"]))
    surec.bitir()
    assert oynatim.bekle(timeout=2) is True
    oynatim.kes()
    assert oynatim.kesildi is False


def test_cutting_twice_is_harmless(surec):
    oynatim = play_stream_kesilebilir(iter([b"ses"]))
    oynatim.kes()
    oynatim.kes()
    assert surec.olduruldu


# ---------------- hata kaybolmamalı ----------------

def test_a_synthesis_error_is_captured_not_lost(surec):
    """Besleme ayrı bir iş parçacığında; sentezleyici hatası çağıran
    tarafın ``try`` bloğuna DÜŞMÜYOR. Yakalanmasaydı ses sessizce
    çalışmaz hâle gelir ve sebebi hiçbir yerde görünmezdi."""
    def patlayan():
        yield b"ilk"
        raise TTSError("ElevenLabs krediniz bitti.")

    oynatim = play_stream_kesilebilir(patlayan())
    surec.bitir()
    oynatim.bekle(timeout=2)
    assert isinstance(oynatim.hata, TTSError)
    assert "krediniz bitti" in str(oynatim.hata)


def test_play_stream_still_raises_the_synthesis_error(surec):
    """Eski sözleşme korunuyor: ``play_stream`` çağıranları TTSError
    yakalıyor ve konuşmayı bitirmiyor."""
    def patlayan():
        yield b"ilk"
        raise TTSError("anahtar geçersiz")

    surec.bitir()
    with pytest.raises(TTSError):
        play_stream(patlayan())


def test_play_stream_still_blocks_and_reports_success(surec):
    """Bloklayan yol, kesilebilir yolun beklenmiş hâli — ayrı bir
    uygulama değil. Ayrı olsalardı biri düzeltilip diğeri unutulurdu."""
    surec.bitir()
    assert play_stream(iter([b"a", b"b"])) is True
    assert bytes(surec.stdin.veri) == b"ab"
