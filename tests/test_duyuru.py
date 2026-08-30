"""Sesli duyuru — asıl iş konuşmak değil, susmak.

Monitor zaten ölçüyor ve yayınlıyor; panel gösteriyor. Eksik olan tek
şey JARVIS'in söylemesi. Ama sesli bir kanalda sessizliğin bedeli
ekrandakinden çok daha yüksek: dört eşik birden aşılırsa ekranda dört
satır olur (göz tek bakışta geçer), kulakta dört kesinti olur.

Bu yüzden testlerin çoğu duyurunun YAPILDIĞINI değil, YAPILMADIĞINI
kanıtlıyor.
"""
from __future__ import annotations

import time

import pytest

from jarvis.core.events import EventBus
from jarvis.core.sayac import SAYACLAR
from jarvis.diagnostics.duyuru import DuyuruAyari, Duyurucu


class _Saat:
    """İlerletilebilir sahte monotonic saat."""

    def __init__(self, t: float = 1000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t

    def ilerlet(self, sn: float) -> None:
        self.t += sn


def _takvim(saat: int):
    """Belirli bir saatte duran sahte yerel takvim."""
    return lambda: time.struct_time((2026, 8, 29, saat, 0, 0, 5, 241, 0))


def _kur(ayar=None, saat=None, takvim=None):
    bus = EventBus()
    soylenenler: list[str] = []
    duyurucu = Duyurucu(
        bus, soylenenler.append,
        ayar or DuyuruAyari(enabled=True),
        clock=saat or _Saat(),
        takvim=takvim or _takvim(14),
    )
    return bus, soylenenler, duyurucu


def _kritik(bus, anahtar="disk.high", **ek):
    bus.publish("system.alert", {"key": anahtar, "severity": "critical",
                                 "message": "Disk kullanımı kritik seviyede",
                                 **ek}, source="test")


# ---------------- konuşuyor mu ----------------

def test_a_critical_alert_is_spoken():
    bus, soylenen, _ = _kur()
    _kritik(bus)
    assert soylenen == ["Disk kullanımı kritik seviyede."]


def test_the_number_is_read_out_with_the_sentence():
    """"Disk kritik" bir durum bildirimi; "yüzde 97" eyleme geçirten şey."""
    bus, soylenen, _ = _kur()
    _kritik(bus, value=97.0, unit="%")
    assert soylenen == ["Disk kullanımı kritik seviyede. Yüzde 97."]


def test_the_percent_sign_is_spelled_out():
    """Sentezleyici '%' karakterini güvenilir okumuyor."""
    bus, soylenen, _ = _kur()
    _kritik(bus, value=85.4, unit="%")
    assert "%" not in soylenen[0] and "Yüzde 85" in soylenen[0]


def test_a_non_percent_unit_keeps_its_unit():
    bus, soylenen, _ = _kur()
    bus.publish("system.alert", {"key": "gpu.temperature", "severity": "critical",
                                 "message": "GPU sıcaklığı kritik seviyede",
                                 "value": 91.0, "unit": "°C"})
    assert soylenen == ["GPU sıcaklığı kritik seviyede. 91 °C."]


# ---------------- susuyor mu ----------------

def test_disabled_is_the_default_and_says_nothing():
    """Sessizce açılan bir özellik, ilk kez gece yarısı konuştuğunda
    arıza gibi görünür."""
    bus, soylenen, duyurucu = _kur(DuyuruAyari())
    _kritik(bus)
    assert soylenen == []
    assert duyurucu.durum()["acik"] is False


def test_a_warning_stays_on_screen():
    """"RAM yüksek" bilgilendirmedir; sesli kanal yalnızca eylem için."""
    bus, soylenen, duyurucu = _kur()
    bus.publish("system.warning", {"key": "ram.high", "severity": "warning",
                                   "message": "RAM kullanımı yüksek"})
    assert soylenen == []
    assert duyurucu.durum()["atlanan"]["seviye"] == 1


def test_four_thresholds_crossing_at_once_produce_one_sentence():
    """Monitor'ün susturması ANAHTAR başına; ses toplamda susturuyor.
    Dört eşik birden aşılırsa dört cümle değil, bir cümle."""
    bus, soylenen, _ = _kur()
    for anahtar in ("ram.high", "disk.high", "vram.high", "gpu.temperature"):
        _kritik(bus, anahtar)
    assert len(soylenen) == 1


def test_the_next_alert_is_spoken_once_the_gap_has_passed():
    saat = _Saat()
    bus, soylenen, _ = _kur(DuyuruAyari(enabled=True, en_az_ara=120.0), saat=saat)
    _kritik(bus, "ram.high")
    saat.ilerlet(121)
    _kritik(bus, "disk.high")
    assert len(soylenen) == 2


def test_the_same_key_is_not_repeated():
    """Monitor cooldown süresince aynı eşiği yeniden yayınlıyor; ikinci
    cümle yeni bilgi taşımıyor."""
    saat = _Saat()
    bus, soylenen, _ = _kur(saat=saat)
    _kritik(bus, "disk.high")
    saat.ilerlet(10_000)
    _kritik(bus, "disk.high")
    assert len(soylenen) == 1


# ---------------- sessiz saatler ----------------

@pytest.mark.parametrize("saat", [23, 2, 7])
def test_nothing_is_spoken_during_quiet_hours(saat):
    bus, soylenen, _ = _kur(takvim=_takvim(saat))
    _kritik(bus)
    assert soylenen == []


@pytest.mark.parametrize("saat", [8, 14, 22])
def test_outside_quiet_hours_it_speaks(saat):
    bus, soylenen, _ = _kur(takvim=_takvim(saat))
    _kritik(bus)
    assert len(soylenen) == 1


def test_a_quiet_hours_alert_is_not_saved_for_the_morning():
    """Bayat uyarı yanlış bilgidir: 03:00'te dolan disk 08:00'de dolu
    olmayabilir. Sabah hâlâ doluysa monitor yeni bir olay üretecek."""
    saat = _Saat()
    bus, soylenen, duyurucu = _kur(saat=saat, takvim=_takvim(3))
    _kritik(bus)
    assert duyurucu.durum()["atlanan"]["sessiz_saat"] == 1
    assert soylenen == []


def test_quiet_hours_can_be_switched_off():
    bus, soylenen, _ = _kur(
        DuyuruAyari(enabled=True, sessiz_baslangic=0, sessiz_bitis=0),
        takvim=_takvim(3))
    _kritik(bus)
    assert len(soylenen) == 1


def test_a_daytime_quiet_window_does_not_wrap():
    """Başlangıç < bitiş ise aralık gece yarısını aşmıyor: 09–17 sessizse
    20:00 konuşmalı."""
    ayar = DuyuruAyari(enabled=True, sessiz_baslangic=9, sessiz_bitis=17)
    bus, soylenen, _ = _kur(ayar, takvim=_takvim(20))
    _kritik(bus)
    assert len(soylenen) == 1

    bus2, soylenen2, _ = _kur(ayar, takvim=_takvim(12))
    _kritik(bus2)
    assert soylenen2 == []


# ---------------- düzelme ----------------

def test_a_recovery_is_spoken_only_if_the_failure_was_heard():
    """Bozulduğunu duymadığınız şeyin düzeldiğini duymak gürültü."""
    bus, soylenen, duyurucu = _kur()
    bus.publish("system.recovered", {"key": "disk.high",
                                     "message": "disk.high normale döndü"})
    assert soylenen == []
    assert duyurucu.durum()["atlanan"]["duyulmayan_duzelme"] == 1


def test_a_heard_failure_gets_its_closing_sentence():
    saat = _Saat()
    bus, soylenen, _ = _kur(saat=saat)
    _kritik(bus, "disk.high")
    bus.publish("system.recovered", {"key": "disk.high",
                                     "message": "disk.high normale döndü"})
    assert soylenen == ["Disk kullanımı kritik seviyede.",
                        "disk.high normale döndü."]


def test_the_closing_sentence_ignores_the_rate_limit():
    """Uyarıyı duyup kapanışını duymamak, açık kalmış bir soru bırakır."""
    saat = _Saat()
    bus, soylenen, _ = _kur(DuyuruAyari(enabled=True, en_az_ara=600.0), saat=saat)
    _kritik(bus, "disk.high")
    saat.ilerlet(1)
    bus.publish("system.recovered", {"key": "disk.high", "message": "düzeldi"})
    assert len(soylenen) == 2


def test_the_same_failure_can_be_announced_again_after_recovering():
    saat = _Saat()
    bus, soylenen, _ = _kur(saat=saat)
    _kritik(bus, "disk.high")
    bus.publish("system.recovered", {"key": "disk.high", "message": "düzeldi"})
    saat.ilerlet(1000)
    _kritik(bus, "disk.high")
    assert len(soylenen) == 3


def test_turning_the_closing_sentence_off_does_not_mute_the_alerts():
    """``duzelmeyi_soyle=False`` yalnızca kapanış cümlesini kapatmalı.
    Anahtar düşmezse aynı arıza "zaten duyuruldu" sayılır ve bir daha
    HİÇ duyulmaz — yani ayar, uyarıları da kalıcı olarak susturur."""
    saat = _Saat()
    bus, soylenen, _ = _kur(
        DuyuruAyari(enabled=True, duzelmeyi_soyle=False), saat=saat)
    _kritik(bus, "disk.high")
    bus.publish("system.recovered", {"key": "disk.high", "message": "düzeldi"})
    saat.ilerlet(1000)
    _kritik(bus, "disk.high")
    assert len(soylenen) == 2  # iki uyarı, sıfır kapanış


# ---------------- dayanıklılık ----------------

def test_a_speech_failure_does_not_swallow_the_alert_silently():
    """Ses üretilemiyorsa uyarı HİÇ duyulmamış oluyor — bu sayılması
    gereken bir arıza, olay otobüsünün günlüğüne gömülecek bir şey değil."""
    SAYACLAR.sifirla()
    try:
        bus = EventBus()

        def patla(_metin):
            raise RuntimeError("oynatıcı yok")

        Duyurucu(bus, patla, DuyuruAyari(enabled=True),
                 clock=_Saat(), takvim=_takvim(14))
        _kritik(bus)
        assert SAYACLAR.adet("duyuru.ses") == 1
    finally:
        SAYACLAR.sifirla()


def test_closing_stops_the_announcements():
    bus, soylenen, duyurucu = _kur()
    duyurucu.close()
    _kritik(bus)
    assert soylenen == []


def test_an_event_without_a_message_still_says_something():
    bus, soylenen, _ = _kur()
    bus.publish("system.alert", {"key": "ram.high", "severity": "critical"})
    assert soylenen == ["ram.high."]
