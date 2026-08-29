"""Konuşma durumu ve bağlam penceresi.

İki iş bir arada, çünkü ikisi aynı sorunun iki yüzü.

**Pencere.** Geçmiş hiç kırpılmıyordu: ``Agent.history`` listesine ekleme
vardı, çıkarma yoktu. Ölçüldü — kırk kısa tur 4719 token, yani 8192'lik
pencerenin %57'si; araç çıktısı olan gerçek turlarda çok daha hızlı.
Pencere taştığında Ollama en eski mesajı düşürüyor ve o mesaj sistem
istemi: kişilik, Türkçe kuralı ve kullanıcının kimliği. Yani kırpmayı biz
yapmazsak model yapıyor, ve en kötü yerden yapıyor.

**Durum.** Kırpmak tek başına bilgiyi kaybetmek demek. "Qwen 14B'yi
kurdum." → "Ollama üzerinden mi?" → "Evet." Bu üçlüde son mesaj tek
başına anlamsız; neyin evetlendiği bir önceki cümlede. Kırpma bunu
düşürürse konuşma sessizce kopuyor.

O yüzden kırpma kör değil: neyin taşındığı biliniyor. Bekleyen soru
korunuyor, düşen turlardan bir özet kalıyor, ve konu ile varlıklar
takip ediliyor.

Özet için modele ikinci bir çağrı YAPILMIYOR. Her kırpmada bir LLM
çağrısı, her uzun konuşmayı iki kat yavaşlatır ve kendi içinde tutarsız
olur — aynı konuşma iki kez özetlenince iki farklı özet çıkar. Buradaki
özet çıkarımsal: kimin ne söylediğinin kısaltılmış hâli. Kaba ama
tekrarlanabilir ve bedava.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..llm.base import Message
from .arac_secici import kategorileri_bul
from .metin import katla

#: Türkçede kabaca karakter/token oranı.
#:
#: Ölçüm: 7016 karakterlik bir tur Ollama'da 2338 token okundu, yani 3,00.
#: Tam sayı değil ve olmasına gerek yok — bütçe zaten ihtiyatlı tutuluyor
#: ve gerçek sayaç (prompt_eval_count) her turdan sonra düzeltme veriyor.
KARAKTER_BASINA_TOKEN = 3.0

#: Pencerenin ne kadarı geçmişe ayrılıyor.
#:
#: Kalanı cevabın kendisine ve paya gidiyor. %85 vermek cazip ama yanlış:
#: model uzun bir cevap üretirken pencere yine taşar, ve o taşma cevabın
#: ortasında olur. %60 iki tarafa da yer bırakıyor.
GECMIS_PAYI = 0.60

#: Bütçe ne olursa olsun korunacak en son tur sayısı.
#:
#: Sıfıra kadar kırpmak teknik olarak mümkün ama konuşmayı yok eder;
#: kullanıcı "az önce ne dedim" diye sorduğunda cevabı olmalı.
EN_AZ_TUR = 4

#: Soru işaretiyle biten bir asistan cümlesi bekleyen soru sayılıyor.
SORU_ISARETLERI = ("?",)

#: Tek başına anlamsız olan, bir önceki soruya bağlanan cevaplar.
#:
#: Bunlar kırpmanın en tehlikeli olduğu yer: "evet" korunup sorusu
#: düşerse, model neyin onaylandığını bilmeden devam ediyor.
BAGLI_CEVAPLAR = frozenset({
    "evet", "hayir", "olur", "tamam", "peki", "yok", "var", "dogru",
    "yanlis", "aynen", "kesinlikle", "belki", "hayır", "doğru", "yanlış",
})


def bagli_cevap_mi(metin: str) -> bool:
    """Bu mesaj tek başına anlamsız mı — bir önceki soruya mı bağlı."""
    sade = katla(metin or "").strip().strip(".!,")
    return sade in BAGLI_CEVAPLAR


@dataclass
class KonusmaDurumu:
    """Konuşmanın o anki hâli — geçmişin kendisi değil, hakkındaki bilgi."""

    #: Son turların çağrıştırdığı kategori. ``arac_secici`` zaten bunu
    #: hesaplıyor; ikinci bir sınıflandırıcı yazmak iki ayrı doğruluk
    #: tanımı demek olurdu.
    current_topic: str = ""
    #: Asistanın sorduğu ve henüz cevaplanmamış soru. Kırpmadan KORUNUYOR.
    pending_question: str = ""
    #: Konuşmada geçen özel adlar ve teknik terimler.
    referenced_entities: list[str] = field(default_factory=list)
    #: Bir önceki turun kategorileri.
    previous_intent: str = ""
    #: En son çağrılan araç.
    active_tool: str = ""
    #: Pencereden düşen turların kısa özeti.
    conversation_summary: str = ""

    def ozet_satiri(self) -> str:
        """Modele verilecek tek satırlık durum. Boşsa hiç eklenmiyor."""
        parcalar = []
        if self.conversation_summary:
            parcalar.append(f"Konuşmanın daha öncesi: {self.conversation_summary}")
        if self.pending_question:
            parcalar.append(
                f"Az önce şunu sordun ve cevabı bekliyorsun: "
                f"\"{self.pending_question}\"")
        return "\n".join(parcalar)


#: Büyük harfle başlayan ya da rakam içeren belirteçler: ürün ve sürüm
#: adları buradan çıkıyor ("Qwen", "14B", "Ollama", "BIOS").
def _varliklar(metin: str) -> list[str]:
    bulunan: list[str] = []
    for ham in (metin or "").split():
        sozcuk = ham.strip(".,!?;:()[]\"'")
        if len(sozcuk) < 2:
            continue
        if sozcuk[0].isupper() or any(k.isdigit() for k in sozcuk):
            if sozcuk not in bulunan:
                bulunan.append(sozcuk)
    return bulunan


#: Bağlamda tutulacak en fazla varlık. Sınırsız bırakmak, uzun bir
#: konuşmada bu listenin kendisinin bağlamı yemesi demek.
EN_FAZLA_VARLIK = 12


def durumu_guncelle(durum: KonusmaDurumu, gecmis: list[Message],
                    kullanici_metni: str) -> KonusmaDurumu:
    """Bu turdan sonra konuşma nerede duruyor."""
    kategoriler = kategorileri_bul(kullanici_metni)
    durum.previous_intent = durum.current_topic
    durum.current_topic = kategoriler[0] if kategoriler else durum.current_topic

    for varlik in _varliklar(kullanici_metni):
        if varlik not in durum.referenced_entities:
            durum.referenced_entities.append(varlik)
    del durum.referenced_entities[:-EN_FAZLA_VARLIK]

    son_arac = [m for m in gecmis if m.role == "tool"]
    if son_arac:
        durum.active_tool = son_arac[-1].name or ""

    # Kullanici bagli bir cevap verdiyse ("evet") soru CEVAPLANMIS
    # sayiliyor ve birakiliyor; yoksa her turda tasinip birikirdi.
    if durum.pending_question and not bagli_cevap_mi(kullanici_metni):
        durum.pending_question = ""
    return durum


def bekleyen_soruyu_yakala(durum: KonusmaDurumu, cevap: str) -> KonusmaDurumu:
    """Asistan soru sorduysa kaydet — kırpmada korunacak olan bu."""
    metin = (cevap or "").strip()
    if not metin.endswith(SORU_ISARETLERI):
        durum.pending_question = ""
        return durum
    # Yalnizca SON cumle: uzun bir cevabin tamamini tasimak, korumasi
    # gereken seyin kendisini baglam yukune cevirir.
    for ayrac in ("\n", ". ", "! "):
        if ayrac in metin:
            metin = metin.rsplit(ayrac, 1)[-1]
    durum.pending_question = metin.strip()[:300]
    return durum


def _uzunluk(mesajlar: list[Message]) -> int:
    return sum(len(m.content) for m in mesajlar)


def butce_karakteri(num_ctx: int) -> int:
    """Geçmişe ayrılan karakter bütçesi."""
    return int(num_ctx * GECMIS_PAYI * KARAKTER_BASINA_TOKEN)


def pencerele(gecmis: list[Message], num_ctx: int,
              durum: KonusmaDurumu | None = None, *,
              max_messages: int = 0,
              max_chars: int = 0) -> tuple[list[Message], list[Message]]:
    """Geçmişi bütçeye sığdır. (kalan, düşen) döndürür.

    Korunanlar, sırayla:

    1. **Sistem mesajları.** Hepsi. Kişilik, hafıza bloğu, bilgi tabanı
       bloğu — bunlar her turda zaten yeniden yazılıyor ve düşürülmeleri
       tam olarak kaçındığımız hasar.
    2. **Son :data:`EN_AZ_TUR` tur.** Bütçe ne derse desin.
    3. **Bekleyen soru ve ona bağlı cevap.** "Evet" korunup sorusu
       düşerse model neyin onaylandığını bilemez.

    Düşenler çağırana veriliyor, atılmıyor: özet onlardan çıkıyor.
    """
    butce = butce_karakteri(num_ctx)
    if max_chars > 0:
        # Production ContextManager already exposes a configurable hard
        # character ceiling.  The token-derived budget and that ceiling are
        # two descriptions of the same resource, so the stricter one wins;
        # running two independent pruners would silently discard the pending
        # question before this state-aware layer could protect it.
        butce = min(butce, int(max_chars))
    sistem = [m for m in gecmis if m.role == "system"]
    konusma = [m for m in gecmis if m.role != "system"]

    # Sistem mesajlari butcenin disinda degil, ONUNDE: onlar kirpilamaz,
    # o yuzden konusmaya kalan yer onlardan arta kalan.
    kalan_butce = max(0, butce - _uzunluk(sistem))

    # KIMLIK degil KONUM ile calisiliyor. Deger esitligi ile calismak bir
    # hataydi ve olcumle yakalandi: Message bir dataclass, yani iki ayni
    # metin esit sayiliyor. Konusmada ayni cumle tekrarlaninca ("evet",
    # "tamam", ayni hata mesaji) "bu mesaj korunanlarda mi" sorusu
    # HEPSI icin dogru donuyordu ve kirpma hicbir sey atmiyordu.
    # Olcum: 300 tur sonra pencerenin %195'i.
    korunan: set[int] = set(range(max(0, len(konusma) - EN_AZ_TUR), len(konusma)))

    if durum is not None and durum.pending_question:
        for i in range(len(konusma) - 1, -1, -1):
            m = konusma[i]
            if m.role == "assistant" and durum.pending_question in m.content:
                korunan.add(i)
                break

    toplam = sum(len(konusma[i].content) for i in korunan)
    # Yeniden eskiye dogru doldur: en yakin baglam en degerli olan.
    for i in range(len(konusma) - 1, -1, -1):
        if i in korunan:
            continue
        if max_messages > 0 and len(korunan) >= int(max_messages):
            break
        if toplam + len(konusma[i].content) > kalan_butce:
            break
        korunan.add(i)
        toplam += len(konusma[i].content)

    kalan_sirali = [konusma[i] for i in sorted(korunan)]
    dusen = [konusma[i] for i in range(len(konusma)) if i not in korunan]
    return sistem + kalan_sirali, dusen


#: Özette bir mesajdan alınacak en fazla karakter.
OZET_KIRPMA = 90
#: Özette tutulacak en fazla satır.
OZET_SATIR = 6


def ozetle(dusen: list[Message], onceki: str = "") -> str:
    """Pencereden düşen turlardan kalan iz.

    Modele çağrı yok: gerekçe modül başlığında. Araç mesajları özete
    girmiyor — çıktıları uzun, tekrarlı ve zaten sonuçları konuşmanın
    içinde geçiyor.
    """
    satirlar = [s for s in onceki.split("\n") if s.strip()]
    for m in dusen:
        if m.role not in ("user", "assistant"):
            continue
        kim = "Kullanıcı" if m.role == "user" else "Sen"
        metin = " ".join(m.content.split())[:OZET_KIRPMA]
        if metin:
            satirlar.append(f"{kim}: {metin}")
    return "\n".join(satirlar[-OZET_SATIR:])
