"""Sesli duyurunun panele kadar giden yolu.

:mod:`tests.test_duyuru` politikayı sınıyor — ne söylenir, ne susulur.
Buradaki testler bağlantıyı sınıyor: monitor bir kritik olay yayınladığında
panelin çalacağı ses gerçekten üretiliyor mu, ve ses kapalıyken hiçbir şey
sızıyor mu.

Bağlantı ayrı sınanmak zorunda: politikanın kusursuz çalıştığı ama
``konus`` çağrısının hiçbir yere bağlı olmadığı bir sürüm, bütün politika
testlerini geçer ve tek bir kelime söylemez.
"""
from __future__ import annotations

import json
import queue
from typing import Iterator

import pytest

from jarvis.bootstrap import build_agent
from jarvis.config import Config
from jarvis.diagnostics.duyuru import DuyuruAyari
from jarvis.memory.store import MemoryStore
from jarvis.web.server import PanelServer


class _StubTTS:
    name = "stub"
    available = True
    mime = "audio/mpeg"

    def synthesize(self, text: str) -> Iterator[bytes]:
        yield b"MP3DATA"


def _sunucu(*, sesli: bool = True, **ayar):
    """HTTP dinlemeden yalnızca nesneyi kur — bağlantı testi için yeter."""
    agent = build_agent(Config(llm_provider="mock", non_interactive=True),
                        memory=MemoryStore(":memory:"))
    # Bu dosya duyuru politikasını değil panel bağlantısını sınıyor. Gerçek
    # yerel saat 23:00-08:00 arasındaysa varsayılan sessiz aralık kabloyu
    # kasten susturur ve test günün saatine göre kırmızı/yeşil olur.
    ayar = {"sessiz_baslangic": 0, "sessiz_bitis": 0, **ayar}
    return PanelServer(
        agent, host="127.0.0.1", port=0,
        tts=_StubTTS() if sesli else None,
        duyuru_ayari=DuyuruAyari(enabled=True, **ayar),
    )


def _olaylar(kuyruk: queue.Queue, tur: str) -> list[dict]:
    bulunan = []
    while True:
        try:
            ham = kuyruk.get_nowait()
        except queue.Empty:
            break
        satirlar = ham.strip().split("\n")
        if satirlar[0] == f"event: {tur}":
            bulunan.append(json.loads(satirlar[1][len("data: "):]))
    return bulunan


def _kritik(srv, anahtar="disk.high"):
    srv.agent.events.publish(
        "system.alert",
        {"key": anahtar, "severity": "critical",
         "message": "Disk kullanımı kritik seviyede", "value": 97.0, "unit": "%"},
        source="test")


def test_a_critical_alert_reaches_the_panel_as_playable_speech():
    srv = _sunucu()
    try:
        kuyruk = srv.hub.subscribe()
        _kritik(srv)
        duyurular = _olaylar(kuyruk, "duyuru")
        assert len(duyurular) == 1
        assert duyurular[0]["speech_id"]
        # Panelin çekeceği metin gerçekten hazır olmalı.
        assert srv.speech_text(duyurular[0]["speech_id"]) == \
            "Disk kullanımı kritik seviyede. Yüzde 97."
    finally:
        srv.duyurucu.close()


def test_nothing_is_published_when_voice_is_off():
    """Ses kapalıyken duyuru olayı üretmek, panelde çalınamayacak bir
    kimlik göndermek olurdu."""
    srv = _sunucu(sesli=False)
    try:
        kuyruk = srv.hub.subscribe()
        _kritik(srv)
        assert _olaylar(kuyruk, "duyuru") == []
    finally:
        srv.duyurucu.close()


def test_the_announcement_is_not_retained_for_late_panels():
    """Bayat bir uyarıyı sonradan bağlanan panele çalmak yanlış bilgi:
    olay ``retain=False`` yayınlanıyor, yani yalnızca o an bağlı olanlar
    duyuyor."""
    srv = _sunucu()
    try:
        _kritik(srv)
        gec_gelen = srv.hub.subscribe()
        assert _olaylar(gec_gelen, "duyuru") == []
    finally:
        srv.duyurucu.close()


def test_a_warning_does_not_reach_the_voice_channel():
    srv = _sunucu()
    try:
        kuyruk = srv.hub.subscribe()
        srv.agent.events.publish("system.warning",
                                 {"key": "ram.high", "severity": "warning",
                                  "message": "RAM kullanımı yüksek"})
        assert _olaylar(kuyruk, "duyuru") == []
    finally:
        srv.duyurucu.close()


def test_the_announcer_is_off_unless_it_is_configured_on():
    """Varsayılan yapılandırmayla kurulan bir panel konuşmamalı."""
    agent = build_agent(Config(llm_provider="mock", non_interactive=True),
                        memory=MemoryStore(":memory:"))
    srv = PanelServer(agent, host="127.0.0.1", port=0, tts=_StubTTS())
    try:
        kuyruk = srv.hub.subscribe()
        _kritik(srv)
        assert _olaylar(kuyruk, "duyuru") == []
        assert srv.duyurucu.durum()["acik"] is False
    finally:
        srv.duyurucu.close()


def test_answer_speech_and_announcement_share_one_cache():
    """İkisi de ``_speech_kaydet``ten geçiyor; ayrı yazılsalardı önbellek
    sınırı birinde düzeltilip diğerinde unutulurdu."""
    srv = _sunucu()
    try:
        kimlikler = {srv._speech_kaydet(f"cümle {i}") for i in range(30)}
        assert None not in kimlikler
        # Sınır 20; eskiler düşmüş olmalı.
        assert len(srv._speech) == 20
    finally:
        srv.duyurucu.close()
