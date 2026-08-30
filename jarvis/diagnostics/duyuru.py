"""Uyarıları sesle söylemek — ve uyarıların çoğunu söylememek.

Malzeme zaten hazırdı: :class:`~jarvis.diagnostics.monitor.ProactiveMonitor`
ölçüyor, ``system.alert`` / ``system.warning`` yayınlıyor, panel bunları bir
bildirim satırı olarak gösteriyor. Eksik olan tek şey JARVIS'in bunları
**söylemesi**. ``jarvis/diagnostics/`` içinde tek bir seslendirme çağrısı
yoktu; TTS orada yalnızca sağlığı kontrol edilen bir bileşendi, konuşulan
bir kanal değil. Ekrana bakmıyorsanız diskin %97 olduğunu öğrenmiyorsunuz.

Sorulmadan konuşmak, bir asistanı asistan yapan şeydir. Aynı zamanda onu
dayanılmaz yapan şeydir — ve buradaki kodun çoğu ikincisiyle ilgili.

**Neden politika ayrı bir katman:** monitor'ün susturma mantığı ekran için
doğru ayarlanmış. Cooldown her *anahtar* için ayrı işliyor (varsayılan 300
sn), yani RAM, disk, VRAM ve GPU sıcaklığı birlikte eşiği aşarsa beş
dakikalık pencerede dört olay çıkıyor. Ekranda bu dört satır: göz onları
tek bakışta geçer. Kulakta dört ayrı kesinti. Sesli bir kanalda sessizliğin
bedeli ekrandakinden çok daha yüksek, o yüzden ses kendi eşiğini kendisi
koyuyor:

* **yalnızca kritik.** ``system.warning`` ekranda kalıyor. "RAM yüksek"
  bilgilendirmedir; "RAM kritik" eylemdir. Sesli kanal yalnızca ikincisi
  için.
* **duyurular arası en az bir süre.** Anahtar başına değil, toplamda:
  arka arkaya dört farklı kritik, dört cümle değil bir cümledir.
* **sessiz saatler.** Gece söylemiyor — ve sabaha **saklamıyor.** Bayat
  bir uyarı yanlış bilgidir: saat 03:00'te dolan disk 08:00'de dolu
  olmayabilir ve "disk doldu" diye uyanan kişi olmayan bir sorunu arar.
  Sabah hâlâ doluysa monitor zaten yeni bir olay üretecek.
* **düzelme yalnızca bozulma duyulduysa.** ``system.recovered`` tek başına
  gürültüdür: bozulduğunu duymadığınız şeyin düzeldiğini duymak, bilgi
  değil kesintidir.

Seslendirmenin kendisi buraya ait değil. :class:`Duyurucu` bir ``konus``
çağrılabiliri alıyor; paneldeki hâli tarayıcıya ses gönderir, terminal
hâli hoparlörden çalar. Politika iki yüzeyde de aynı kalıyor, taşıma
katmanı değişiyor.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

from ..core.events import Event, EventBus
from ..core.sayac import yut


@dataclass(frozen=True)
class DuyuruAyari:
    """Sesli duyuru politikası.

    Varsayılan **kapalı**. Konuşan bir asistanı isteyip istemediğine
    kullanıcı karar verir; sessizce açılan bir özellik, ilk kez gece
    yarısı konuştuğunda arıza gibi görünür.
    """

    enabled: bool = False
    #: Yalnızca ``system.alert``. False yapılırsa ``system.warning`` da
    #: sesleniyor — ölçülmeden açılmaması önerilir.
    yalnizca_kritik: bool = True
    #: İki duyuru arasındaki en az süre (sn), anahtardan bağımsız toplam.
    en_az_ara: float = 120.0
    #: Sessiz aralık, yerel saat. Başlangıç == bitiş ise sessiz saat yok.
    sessiz_baslangic: int = 23
    sessiz_bitis: int = 8
    #: Düzelme cümlesi söylensin mi (yalnızca bozulması duyulmuş anahtarlar).
    duzelmeyi_soyle: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "en_az_ara", max(0.0, float(self.en_az_ara)))
        object.__setattr__(self, "sessiz_baslangic",
                           int(self.sessiz_baslangic) % 24)
        object.__setattr__(self, "sessiz_bitis", int(self.sessiz_bitis) % 24)


class Duyurucu:
    """``system.*`` olaylarını sesli cümleye çeviren politika katmanı.

    ``konus`` senkron çağrılıyor ama hızlı dönmesi bekleniyor: olay
    otobüsü teslimatı senkron ve yavaş bir abone bütün yayını bekletir
    (bkz. :mod:`jarvis.core.events`). Panelde bu bir kuyruğa yazmak,
    terminalde bir iş parçacığı başlatmak demek.
    """

    def __init__(self, events: EventBus, konus: Callable[[str], None],
                 ayar: DuyuruAyari | None = None, *,
                 clock: Callable[[], float] = time.monotonic,
                 takvim: Callable[[], time.struct_time] = time.localtime) -> None:
        self.events = events
        self.konus = konus
        self.ayar = ayar or DuyuruAyari()
        # İki ayrı saat, iki ayrı iş. Aralık ölçümü monotonic olmak
        # zorunda: sistem saati geri alınırsa (NTP düzeltmesi, yaz saati)
        # duvar saatiyle ölçülen bir aralık negatife düşer ve susturma
        # sessizce devre dışı kalır. Sessiz saatler ise duvar saatidir —
        # "gece" monotonic'te bir karşılığı olmayan bir kavram.
        self._clock = clock
        self._takvim = takvim
        self._lock = threading.RLock()
        self._son_duyuru = 0.0
        self._hic_duyuruldu = False
        #: Sesle duyurulmuş anahtarlar; düzelme yalnızca bunlar için söyleniyor.
        self._duyurulan: set[str] = set()
        #: Ölçüm: neyin neden söylenmediği. Panelde tek satır, testte kanıt.
        self.atlanan = {"seviye": 0, "sessiz_saat": 0, "sik": 0, "tekrar": 0,
                        "duyulmayan_duzelme": 0}
        self.soylenen = 0
        self._unsubscribers = [
            events.subscribe("system.alert", self._on_uyari),
            events.subscribe("system.warning", self._on_uyari),
            events.subscribe("system.recovered", self._on_duzelme),
        ] if self.ayar.enabled else []

    def close(self) -> None:
        for unsubscribe in self._unsubscribers:
            unsubscribe()
        self._unsubscribers.clear()

    # ---------------- politika ----------------

    def _sessiz_saat_mi(self) -> bool:
        if self.ayar.sessiz_baslangic == self.ayar.sessiz_bitis:
            return False
        saat = self._takvim().tm_hour
        bas, bit = self.ayar.sessiz_baslangic, self.ayar.sessiz_bitis
        if bas < bit:
            return bas <= saat < bit
        # Gece yarısını aşan aralık (23 → 8).
        return saat >= bas or saat < bit

    def _izin_ve_kaydet(self, anahtar: str, kritik: bool) -> bool:
        """Politikayı uygula ve izin verilirse kaydı **aynı kilit altında** al.

        Denetim ile kayıt ayrı kilitlerde yapılamaz: monitor'ün ölçüm iş
        parçacığı ile olay otobüsünün teslimatı aynı anda buraya girebilir,
        ikisi de "arayı geçtim" der ve iki cümle üst üste söylenir. Susturma
        mantığının kendisi yarışa açıksa susturma yok demektir.
        """
        with self._lock:
            if self.ayar.yalnizca_kritik and not kritik:
                self.atlanan["seviye"] += 1
                return False
            # Aynı anahtar üst üste: monitor cooldown'ı zaten seyreltiyor,
            # ama seviye değişiminde (warning → critical) yeni olay üretiyor.
            # Sesli kanalda bu ikinci cümle yeni bilgi taşımıyor.
            if anahtar and anahtar in self._duyurulan:
                self.atlanan["tekrar"] += 1
                return False
            if self._sessiz_saat_mi():
                self.atlanan["sessiz_saat"] += 1
                return False
            simdi = self._clock()
            if self._hic_duyuruldu and simdi - self._son_duyuru < self.ayar.en_az_ara:
                self.atlanan["sik"] += 1
                return False
            self._son_duyuru = simdi
            self._hic_duyuruldu = True
            if anahtar:
                self._duyurulan.add(anahtar)
            self.soylenen += 1
            return True

    # ---------------- cümle ----------------

    @staticmethod
    def cumle(payload: dict[str, Any]) -> str:
        """Olay yükünü söylenebilir bir cümleye çevir.

        Sayı varsa ekleniyor: "Disk kullanımı kritik seviyede" bir durum
        bildirimi, "yüzde 97" ise eyleme geçirten şey. Yüzde işareti
        yazıyla — sentezleyici "%" karakterini güvenilir okumuyor.
        """
        mesaj = str(payload.get("message") or payload.get("key") or "Sistem uyarısı")
        deger = payload.get("value")
        birim = str(payload.get("unit") or "")
        if isinstance(deger, (int, float)):
            sayi = f"{float(deger):.0f}"
            if birim == "%":
                return f"{mesaj}. Yüzde {sayi}."
            if birim:
                return f"{mesaj}. {sayi} {birim}."
            return f"{mesaj}. {sayi}."
        return f"{mesaj}."

    # ---------------- olaylar ----------------

    def _on_uyari(self, event: Event) -> None:
        anahtar = str(event.payload.get("key") or "")
        kritik = (event.name == "system.alert"
                  or event.payload.get("severity") == "critical")
        # Seslendirme kilidin DIŞINDA: konuşma yavaş olabilir ve kilidi
        # tutarken beklemek, monitor'ün bir sonraki ölçümünü de bekletir.
        if self._izin_ve_kaydet(anahtar, kritik):
            self._seslendir(self.cumle(event.payload))

    def _on_duzelme(self, event: Event) -> None:
        anahtar = str(event.payload.get("key") or "")
        with self._lock:
            duyulmustu = bool(anahtar) and anahtar in self._duyurulan
            # Anahtar HER durumda düşüyor — ``duzelmeyi_soyle`` kapalıyken
            # de. Düşmezse aynı arıza tekrar ettiğinde "zaten duyuruldu"
            # sayılır ve bir daha hiç duyulmaz; yani düzelme cümlesini
            # kapatmak, uyarıları da kalıcı olarak susturmuş olurdu.
            self._duyurulan.discard(anahtar)
            if not self.ayar.duzelmeyi_soyle:
                return
            if not duyulmustu:
                # Bozulduğunu duymadıysanız düzeldiğini duymanız gürültü.
                self.atlanan["duyulmayan_duzelme"] += 1
                return
            if self._sessiz_saat_mi():
                self.atlanan["sessiz_saat"] += 1
                return
            # Düzelme cümlesi ``en_az_ara``ya takılmıyor: bu, bir uyarının
            # kapanışı. Uyarıyı duyup kapanışını duymamak, açık kalmış bir
            # soru bırakıyor.
            self._son_duyuru = self._clock()
            self._hic_duyuruldu = True
            self.soylenen += 1
        self._seslendir(str(event.payload.get("message") or "Sistem normale döndü") + ".")

    def _seslendir(self, metin: str) -> None:
        """Konuşma hatası bir sistem uyarısını yutmamalı.

        Olay otobüsü zaten istisnaları yakalıyor, ama orada yakalanan şey
        günlüğe gidip kayboluyor. Ses üretilemiyorsa bu sayılması gereken
        bir arıza: uyarı hiç duyulmamış oluyor.
        """
        try:
            self.konus(metin)
        except Exception as exc:
            yut("duyuru.ses", exc)

    def durum(self) -> dict[str, Any]:
        """Panelin/testin okuduğu özet."""
        with self._lock:
            return {
                "acik": bool(self._unsubscribers),
                "soylenen": self.soylenen,
                "atlanan": dict(self.atlanan),
                "bekleyen_anahtarlar": tuple(sorted(self._duyurulan)),
            }
