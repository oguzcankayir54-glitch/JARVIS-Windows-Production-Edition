"""Sessizce yutulan hataları saymak.

``except Exception: return None`` doğru bir karardır ve kaldırılmamalı:
bilgi indeksinin çökmesi bir konuşma turunu düşürmemeli. Ama doğru olan
şey görünmez olduğunda ölçülemez hâle geliyor. ``_knowledge_context``
indeksi bugün kırk kez okuyamadıysa kimse bunu bilmiyor — JARVIS
kırk turda bilgi tabanı yokmuş gibi cevap veriyor, hiçbir yerde bir
hata görünmüyor, yalnızca cevaplar sessizce kötüleşiyor.

Burada tutulan şey bir günlük değil, bir **sayaç**. Aradaki fark şu:
günlük satırı hata anında yazılır ve birinin şüphelenip dosyayı açmasını
bekler; sayaç panelde tek satır olarak durur ve şüpheyi kendisi başlatır.
"bilgi.indeks — 40" satırını gören kişi o dosyayı zaten açacaktır.

İçeriye hiçbir serbest metin girmiyor: yalnızca sayı ve istisna sınıfının
adı. Yutulan bir hatanın mesajında kullanıcı verisi olabilir (dosya yolu,
sorgu metni, bir yol içindeki kullanıcı adı) ve buranın işi onu görünür
kılmak değil — hata mesajı gereken yerde ``logger.exception`` zaten var.

Ad alanı bilerek sınırlı: :data:`EN_FAZLA_AD` tane farklı ad tutuluyor.
Sayaç adı yanlışlıkla değişken bir şeyden üretilirse (dosya yolu, oturum
kimliği) sözlük sınırsız büyür; sessiz hatayı görünür kılmak için eklenen
şeyin kendisi sessiz bir bellek sızıntısı olamaz.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable

#: Bundan fazla farklı ad tutulmuyor. Gerçek çağrı yerleri sabit ve iki
#: elin parmağını geçmiyor; bu sınıra dayanmak "adı dinamik üretiyoruz"
#: demektir ve o bir hatadır, sessizce büyütülecek bir şey değil.
EN_FAZLA_AD = 64


@dataclass(frozen=True)
class Dokum:
    """Tek bir sayacın okunabilir hâli."""

    ad: str
    adet: int
    son_tur: str
    son_zaman: float


class Sayaclar:
    """İş parçacığına dayanıklı, adla anahtarlanmış sayaç kümesi.

    Örnek ayrıca alınabiliyor (testler kendi örneğini kurar); süreç
    genelinde paylaşılan olan :data:`SAYACLAR`.
    """

    def __init__(self, *, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._sayilar: dict[str, int] = {}
        self._son_tur: dict[str, str] = {}
        self._son_zaman: dict[str, float] = {}
        #: Sınır aşıldığı için düşürülen artırma sayısı. Sıfırdan büyükse
        #: sayaç adlarından biri sabit değil demektir.
        self.tasan = 0

    def say(self, ad: str, hata: BaseException | str | None = None) -> int:
        """Bir yutulan hatayı kaydet, yeni toplamı döndür.

        ``hata`` verilirse yalnızca **sınıf adı** saklanıyor (``OSError``),
        mesajı değil. Aynı sayacın altında iki farklı arıza varsa —
        indeks dosyası bozuk mu, disk mi dolu — bunu ayırmaya yeten en
        küçük bilgi bu.
        """
        ad = (ad or "").strip() or "bilinmeyen"
        if isinstance(hata, BaseException):
            tur = type(hata).__name__
        else:
            tur = str(hata or "").strip()[:40]
        with self._lock:
            if ad not in self._sayilar and len(self._sayilar) >= EN_FAZLA_AD:
                self.tasan += 1
                return 0
            toplam = self._sayilar.get(ad, 0) + 1
            self._sayilar[ad] = toplam
            self._son_zaman[ad] = self._clock()
            if tur:
                self._son_tur[ad] = tur
            return toplam

    def adet(self, ad: str) -> int:
        with self._lock:
            return self._sayilar.get(ad, 0)

    def toplam(self) -> int:
        with self._lock:
            return sum(self._sayilar.values())

    def dokum(self) -> tuple[Dokum, ...]:
        """Tüm sayaçlar, çoktan aza sıralı — panelin okuduğu biçim."""
        with self._lock:
            satirlar = [
                Dokum(ad=ad, adet=adet, son_tur=self._son_tur.get(ad, ""),
                      son_zaman=self._son_zaman.get(ad, 0.0))
                for ad, adet in self._sayilar.items()
            ]
        return tuple(sorted(satirlar, key=lambda d: (-d.adet, d.ad)))

    def sifirla(self) -> None:
        with self._lock:
            self._sayilar.clear()
            self._son_tur.clear()
            self._son_zaman.clear()
            self.tasan = 0


#: Süreç genelinde paylaşılan sayaçlar. Global olması bilinçli: alternatif,
#: bir sayaç nesnesini yirmi çağrı yerine parametre olarak geçirmekti ve o
#: yirmi imza değişikliği bu özelliğin hiç eklenmemesi anlamına gelirdi.
SAYACLAR = Sayaclar()


def yut(ad: str, hata: BaseException | str | None = None) -> None:
    """``except`` bloğunun içine tek satır: ``yut("bilgi.indeks", exc)``.

    Dönüş değeri yok — çağıran taraf bunun sonucuyla bir şey yapmamalı.
    Sayaç tutmak, hatayı ele almanın yerine geçmez; yanına eklenir.
    """
    SAYACLAR.say(ad, hata)
