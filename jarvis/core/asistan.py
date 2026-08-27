"""J.A.R.V.I.S.'in kimliği — davranışı değil, kim olduğu.

Bir dönem burada iki asistan vardı: ``ASISTAN=friday`` ikinci bir kimliği
açıyordu. Kaldırıldı, çünkü ikisi bir arada kullanımda karışıklık yarattı:
iki masaüstü simgesi, iki panel, iki port, iki hafıza klasörü ve her
ayarın iki öneki. Kazandırdığı şey (aynı koddan ikinci bir isim) ödediği
bedeli karşılamıyordu.

Kimliğin yine de burada, tek yerde toplanmasının sebebi ayrı: ad, okunuş,
ses ve renk kodun içine dağıldığında bir tanesini değiştirmek diğerlerini
tutarsız bırakıyor. Panelde bir ad, seslendirmede başka bir ad okunması
tam olarak böyle oldu (bkz. :attr:`Asistan.okunus`).
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Asistan:
    """Asistanın kimliği: adı, sesi, nerede yaşadığı."""

    #: Ayarlarda ve dosya adlarında geçen kısa ad.
    kod: str
    #: Yazılışı: panelde ve sistem isteminde görünen hâli.
    ad: str
    #: Ekranda ve metinde görünen sade ad. Noktalı yazılış başlıkta güzel
    #: duruyor ama her satırda okumayı zorlaştırıyor.
    sade_ad: str
    #: SESLENDİRİCİYE giden okunuş. Görünen addan AYRI bir alan olmak
    #: zorunda: ikisi tek alanda tutulunca okunuş ekrana sızdı ve panelde
    #: adın yanlış yazılışı göründü. J.A.R.V.I.S.'te ikisi aynı, ki bu da
    #: alanı gereksiz göstermenin tuzağı — hatanın görünmediği durum tam
    #: olarak buydu.
    okunus: str
    #: Kullanıcı çağırdığında yazabileceği biçimler (küçük harfle).
    seslenisler: tuple[str, ...]
    #: Varsayılan Edge sesi.
    ses: str
    #: Hafızanın, vakaların ve bilgi tabanının durduğu klasör.
    veri_klasoru: str
    #: Panelin vurgu rengi.
    vurgu: str
    #: Sistem isteminin ilk cümlesindeki tanım.
    tanim: str


JARVIS = Asistan(
    kod="jarvis",
    ad="J.A.R.V.I.S.",
    sade_ad="Jarvis",
    okunus="Jarvis",
    seslenisler=("jarvis", "carvis"),
    ses="tr-TR-AhmetNeural",
    veri_klasoru="~/.jarvis",
    vurgu="#7fe3ff",
    tanim="kişisel, teknik bir yapay zekâ asistanısın",
)

#: Ayarların öneki. Sabit: seçilecek başka bir asistan yok.
ONEK = "JARVIS_"


def asistan_bul() -> Asistan:
    """Bu programın kimliği. Tek asistan var; seçim yok."""
    return JARVIS


#: Noktalı yazılışı yakalar: J.A.R.V.I.S.
#: Seslendiriciye giden metinde okunuşuyla değiştiriliyor, yoksa harfleri
#: tek tek okuyor.
def noktali_desen(asistan: Asistan = JARVIS) -> re.Pattern[str]:
    harfler = [h for h in asistan.ad if h.isalpha()]
    return re.compile(r"\.?".join(harfler) + r"\.?", re.IGNORECASE)
