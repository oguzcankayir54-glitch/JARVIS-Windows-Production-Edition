"""Bir bilginin ne kadar önemli olduğu — ve neden bunun ölçülmesi gerektiği.

Hafızadaki her kayıt her turda bağlama itiliyor. Bağlam sınırlı: ölçüldü,
basit bir selam turu bile 2338 token ve bunun dörtte üçü sistem istemi.
Kırk kayıt biriktiğinde hepsini göndermek, asıl soruyu bastırmak demek.

O yüzden "hangisi önce" sorusunun bir cevabı olmak zorunda. İki kötü cevap
var ve ikisi de denenmişin aynısı:

- **Hepsini gönder.** Bağlam şişer, model odağını kaybeder.
- **En yenisini gönder.** Kullanıcının adı, üç gün önce söylenmiş diye
  bugünkü "yazıcı kağıt sıkıştırıyor" notunun arkasında kalır.

Doğru sıralama tazelik değil, ÖNEM. Kim olduğu kalıcıdır; bir arıza notu
geçicidir. Bu modül o ayrımı yapıyor.

Puanlama modele sorulmuyor, kuralla veriliyor. Sebebi maliyet değil
güvenilirlik: modelden her kayıt için ikinci bir çağrı istemek hem yavaş
hem de kendi içinde tutarsız — aynı cümle iki turda iki farklı puan
alabilir. Kural tekrarlanabilir, sınanabilir ve okunabilir.
"""
from __future__ import annotations

import enum

from ..core.metin import katla


class Onem(enum.IntEnum):
    """Bağlama girme sırası. Sayı olarak saklanıyor: sıralama doğrudan.

    Metin olarak ('yuksek'/'orta') saklamak okunaklı olurdu ama her
    sıralamada bir eşleme tablosu gerektirirdi; bu alanın var olma sebebi
    tam olarak sıralamak.
    """

    DUSUK = 0
    ORTA = 1
    YUKSEK = 2

    @property
    def etiket(self) -> str:
        return {0: "düşük", 1: "orta", 2: "yüksek"}[int(self)]


class Kaynak(str, enum.Enum):
    """Bilginin nereden geldiği — çelişki çözümünde belirleyici.

    Kullanıcının açıkça söylediği ile modelin konuşmadan çıkardığı aynı
    ağırlıkta olamaz. Çıkarım, kullanıcının söylediğinin üstüne yazamaz;
    bu kuralın kodu :meth:`MemoryStore.remember` içinde.
    """

    KULLANICI = "kullanici"   # açıkça söylendi
    CIKARIM = "cikarim"       # konuşmadan çıkarıldı
    TOHUM = "tohum"           # kimlik.json gibi bir dosyadan geldi
    ARAC = "arac"             # bir aracın ölçtüğü/okuduğu veri


#: Kullanıcı "bunu unutma" dediğinde tartışma biter: yüksek.
#:
#: Kökler kısa bırakıldı — Türkçe eklemeli bir dil ve "hatırla", "hatırlar
#: mısın", "hatırlamanı" hepsi aynı köke bakıyor. Aynı gerekçe
#: arac_secici.py içinde ayrıntılı yazılı.
ISRAR_KOKLERI = (
    "bunu hatirla", "unutma", "aklinda tut", "not al", "kaydet",
    "hatirlamani", "her zaman", "bundan sonra", "asla",
)

#: Kimlik ve kalıcı olan: kim olduğu, ne yaptığı, neyi tercih ettiği.
YUKSEK_KATEGORILER = frozenset({
    "kimlik", "kullanici", "gelistirici", "tercih", "karar", "kural",
})

#: Proje ve çalışma düzeni: lazım olur ama kimlik kadar değil.
ORTA_KATEGORILER = frozenset({
    "proje", "donanim", "arac", "alistirma", "calisma", "yapilandirma",
})

#: Tek seferlik olan: bugünkü vaka notu, geçici durum.
DUSUK_KATEGORILER = frozenset({
    "gecici", "notlar", "oturum", "gunluk",
})

#: Kimliğe işaret eden kökler. Kategori yanlış verilmiş olsa bile bunlar
#: yakalanmalı: "Ben senin geliştiricinim" cümlesi 'genel' kategorisiyle
#: kaydedilirse düşük öneme düşerdi.
KIMLIK_KOKLERI = (
    "gelistirici", "gelistiren", "tasarimci", "sahibi", "adim ", "adi ",
    "ismim", "mesleg", "meslek", "calistigim", "unvan",
)

#: Kalıcılık bildiren kökler: "artık", "her zaman", "varsayılan".
KALICI_KOKLERI = ("artik", "varsayilan", "surekli", "genelde", "hep ")

#: Geçicilik bildiren kökler. Bunlar bir kaydın ömrünün kısa olduğunu
#: söylüyor; kimlik kökleriyle çakışırsa kimlik kazanıyor.
GECICI_KOKLERI = (
    "bugun", "simdilik", "gecici", "su an", "birazdan", "yarin",
    "bu hafta", "deneme", "test icin",
)


def _geciyor(kokler: tuple[str, ...], metin: str) -> bool:
    return any(k in metin for k in kokler)


def onem_belirle(key: str, value: str, category: str = "genel",
                 israr: bool = False) -> Onem:
    """Bu kayıt bağlamda ne kadar öncelik hak ediyor.

    ``israr`` kullanıcının açıkça "bunu hatırla" demesi. En güçlü sinyal
    bu: sistemin tahmini, kullanıcının açık isteğini geçemez.

    Kategori ile metin çelişirse METİN kazanıyor. Kategoriyi çoğu zaman
    model yazıyor ve 'genel' yazması işten değil; cümlenin kendisi ise
    kullanıcının kelimeleri.
    """
    if israr:
        return Onem.YUKSEK

    kat = (category or "").strip().lower()
    metin = katla(f"{key} {value}")

    # Kimlik her seyin onunde: kategori yanlis verilse bile.
    if _geciyor(KIMLIK_KOKLERI, metin) or kat in YUKSEK_KATEGORILER:
        return Onem.YUKSEK

    # "Bundan sonra hep boyle" demek kalici demek.
    if _geciyor(KALICI_KOKLERI, metin):
        return Onem.YUKSEK

    if _geciyor(GECICI_KOKLERI, metin) or kat in DUSUK_KATEGORILER:
        return Onem.DUSUK

    if kat in ORTA_KATEGORILER:
        return Onem.ORTA

    # Bilinmeyen kategori ORTA'ya düşüyor, DÜŞÜK'e değil: yanlışlıkla
    # unutmak, yanlışlıkla hatırlamaktan pahalı.
    return Onem.ORTA


def israr_var_mi(kullanici_metni: str) -> bool:
    """Kullanıcı bu turda açıkça "bunu hatırla" dedi mi."""
    return _geciyor(ISRAR_KOKLERI, katla(kullanici_metni or ""))


#: Kaynağa göre başlangıç güveni.
#:
#: Çıkarımın kullanıcının söylediğinden düşük olması şart: çelişki
#: çözümünde hangisinin geçerli olduğu buna bakıyor.
KAYNAK_GUVENI: dict[str, float] = {
    Kaynak.KULLANICI.value: 1.0,
    Kaynak.TOHUM.value: 1.0,
    Kaynak.ARAC.value: 0.9,
    Kaynak.CIKARIM.value: 0.6,
}


def guven_belirle(source: str) -> float:
    return KAYNAK_GUVENI.get((source or "").strip().lower(), 0.6)
