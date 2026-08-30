"""Gecikme bütçesi — bir ölçüm değil, bir **eşik**.

Bu depoda ölçüm altyapısı zaten var: ``okuma_sn``, ``üretim_sn``,
``darbogaz``. Eksik olan şey eşikti. Bir sayıyı günlüğe yazmak onu
savunmak değil; sistem prompt'una üç bin karakter ekleyen commit'in tek
belirtisi "Jarvis yavaşladı" olur, o da üç hafta sonra, ve o noktada
hangi commit'in yaptığını kimse bilmez.

Buradaki testler modeli çağırmıyor ve ağ istemiyor. Ölçtükleri şey
**modele gönderilen istem** — çünkü gecikmenin kontrol edebildiğimiz
kısmı orada. Üç ayrı şeyi koruyorlar:

1. **Bağlam penceresinin ne kadarı daha kullanıcı konuşmadan dolu.**
2. **Önbelleğe alınabilir önekin turlar arası sabitliği.** Qwen şablonu
   araç şemalarını SYSTEM bloğunun içine koyuyor; blok değişirse
   Ollama'nın istem önbelleği ıskalıyor. Ölçülmüştü: aynı önek yeniden
   kullanıldığında okuma 2,19 sn yerine 0,02 sn — 110 kat.
3. **Araç şemalarının büyüklüğü.**

Sayılar 2026-08-29'da ``fix/app-suggestion-context`` dalında ölçüldü ve
kaynakları aşağıda tek tek yazılı. Tavanlar bugünün biraz üstünde:
amaçları bugünü kırmak değil, yarını kırmadan geçirtmemek.
"""
from __future__ import annotations

import pytest

from jarvis.bootstrap import build_agent
from jarvis.config import Config
from jarvis.llm.base import LLMResponse
from jarvis.memory.store import MemoryStore

#: Kaba token tahmini. Türkçe metinde bir token ortalama bu kadar karakter;
#: kesin değil ve olması da gerekmiyor — bütçe bir mertebe sorusu.
KARAKTER_BASINA_TOKEN = 3.0

#: Sistem prompt'u tavanı. ÖLÇÜM: 13.189 karakter (yalnızca persona bloğu).
#: 8192'lik pencerede bu ≈4.400 token, yani kullanıcı daha tek kelime
#: etmeden pencerenin **%54'ü** dolu. Tavan bilerek dar: 14.000'i aşan bir
#: değişiklik, konuşmanın kendisine kalan yeri daraltıyor demektir.
SISTEM_TAVANI = 14_000

#: Persona'nın pencereden alabileceği en büyük pay. Karakter tavanından
#: ayrı duruyor çünkü asıl kısıt bu: num_ctx düşürülürse tavan sabit
#: kalır ama pay fırlar, ve bozulan şey paydır.
PENCERE_PAYI_TAVANI = 0.60

#: İlk turun tamamı (persona + yönlendirme blokları + kullanıcı cümlesi).
#: ÖLÇÜM: 13.525 karakter.
TUR_TAVANI = 14_500

#: Araç şemalarının toplam boyu, araç sunulan bir turda.
#: ÖLÇÜM: 8 araç sunuluyor.
ARAC_SAYISI_TAVANI = 12

#: Altı turluk gerçekçi bir konuşmada araç listesinin KAÇ KEZ değiştiği.
#: ÖLÇÜM: 5 geçişin 3'ü. Her değişim, Qwen şablonunda SYSTEM bloğunu
#: değiştirdiği için bir önbellek ıskası demek.
#:
#: Araç listesi yapışkanlığı (``ara_cumle_mi`` + ``son_arac_adlari``) bu
#: dalda VAR, ama bilerek dar: yalnızca açık bağlaç sözcüklerinde
#: ("peki", "evet", "devam et") önceki şema yeniden kullanılıyor. Bu
#: konuşmadaki "Peki disk?" ve "Yeterli mi sence?" o listeye girmiyor, o
#: yüzden sayı 3 kalıyor. Daraltma kasıtlı — gerekçesi ``ara_cumle_mi``
#: içinde yazılı: her kategorisiz turu yapışkan yapmak, eski araç
#: bağlamını alakasız sohbete sızdırırdı.
#:
#: Yani bu tavan bir kusuru değil, bir ödünleşmeyi kayda geçiriyor.
#: İşlevi tek: DAHA KÖTÜYE gidişi yakalamak.
ARAC_DEGISIMI_TAVANI = 3


class _Kaydeden:
    """Modeli çağırmayan, ne gönderildiğini kaydeden sağlayıcı.

    Ölçümün doğru anda yapılması bunun tek sebebi. Bütçe, saklanan
    geçmişe değil **gönderilen isteme** uygulanıyor; ajanın kendi
    ``history`` listesine bakan bir test, pencereleme uygulandıktan
    sonraki gerçeği kaçırır.
    """

    name = "kaydeden"
    num_ctx = 8192

    def __init__(self) -> None:
        self.turlar: list[tuple[list, list]] = []

    def chat(self, messages, tools=None):
        self.turlar.append((list(messages), list(tools or [])))
        return LLMResponse(content="tamam")


def _ajan() -> object:
    ajan = build_agent(Config(llm_provider="mock", non_interactive=True),
                       memory=MemoryStore(":memory:"))
    ajan.llm = _Kaydeden()
    return ajan


def _sistem_metni(mesajlar) -> str:
    return "".join(m.content or "" for m in mesajlar if m.role == "system")


def _arac_imzasi(araclar) -> tuple[str, ...]:
    return tuple(sorted(a.get("function", {}).get("name", "") for a in araclar))


# ---------------- pencere doluluğu ----------------

def test_the_persona_block_stays_within_its_budget():
    ajan = _ajan()
    ajan.ask("Merhaba.")
    persona = ajan.llm.turlar[0][0][0].content
    assert len(persona) <= SISTEM_TAVANI, (
        f"Persona {len(persona)} karakter; tavan {SISTEM_TAVANI}. "
        "Sistem prompt'u büyüdüğünde hiçbir test kırmızı olmuyordu — bu o test."
    )


def test_the_prompt_does_not_eat_most_of_the_context_window():
    """Asıl kısıt karakter değil, PAY.

    num_ctx bir gün 4096'ya indirilirse karakter tavanı hâlâ geçilir ama
    konuşmaya yer kalmaz. Bu test o durumu yakalıyor.
    """
    ajan = _ajan()
    ajan.ask("Merhaba.")
    mesajlar, _ = ajan.llm.turlar[0]
    pencere_karakter = ajan.llm.num_ctx * KARAKTER_BASINA_TOKEN
    pay = len(_sistem_metni(mesajlar)) / pencere_karakter
    assert pay <= PENCERE_PAYI_TAVANI, (
        f"Sistem blokları pencerenin %{pay * 100:.0f}'ini kaplıyor; "
        f"tavan %{PENCERE_PAYI_TAVANI * 100:.0f}."
    )


def test_the_whole_first_turn_stays_within_its_budget():
    ajan = _ajan()
    ajan.ask("Merhaba, nasılsın?")
    mesajlar, _ = ajan.llm.turlar[0]
    toplam = sum(len(m.content or "") for m in mesajlar)
    assert toplam <= TUR_TAVANI, f"İlk tur {toplam} karakter; tavan {TUR_TAVANI}."


# ---------------- önbelleğe alınabilirlik ----------------

def test_the_persona_is_byte_identical_across_turns():
    """Önbelleğin tamamı buna bağlı.

    Persona'ya değişken bir şey sızarsa (saat, canlı RAM yüzdesi, oturum
    kimliği) önek her turda başkalaşır ve okuma süresi 0,02 sn'den
    2,19 sn'ye döner. Bu, kullanıcının "yavaşladı" dediği şeyin ta
    kendisi ve hiçbir hata mesajı üretmiyor.
    """
    ajan = _ajan()
    for cumle in ("Merhaba.", "RAM ne durumda?", "Teşekkürler."):
        ajan.ask(cumle)
    personalar = {msgs[0].content for msgs, _ in ajan.llm.turlar}
    assert len(personalar) == 1, "Persona bloğu turlar arasında değişiyor."


def test_the_tool_list_does_not_churn_more_than_it_does_today():
    """Araç listesi değişimi = önbellek ıskası.

    Qwen şablonu araç şemalarını SYSTEM bloğunun İÇİNE koyuyor; liste
    değiştiğinde önek de değişiyor ve önceki turun önbelleği işe
    yaramıyor. Bugünkü hâl 5 geçişte 3 ıska.
    """
    konusma = ["RAM kullanımı ne durumda?", "Peki disk?", "Yeterli mi sence?",
               "GPU sıcaklığı kaç?", "Teşekkürler.", "Bir de sistem bilgisi ver."]
    ajan = _ajan()
    for cumle in konusma:
        ajan.ask(cumle)

    imzalar = [_arac_imzasi(araclar) for _, araclar in ajan.llm.turlar]
    degisim = sum(1 for onceki, simdiki in zip(imzalar, imzalar[1:])
                  if onceki != simdiki)
    assert degisim <= ARAC_DEGISIMI_TAVANI, (
        f"Araç listesi {degisim} kez değişti (tavan {ARAC_DEGISIMI_TAVANI}); "
        "her değişim bir önbellek ıskası."
    )


def test_a_short_continuation_reuses_the_previous_tool_schema():
    """Yapışkanlığın ASIL kazancı burada ve ölçülebilir.

    "RAM ne durumda?" → "Peki" → "Evet" → "Devam et" zincirinde şema hiç
    değişmiyor (0/3). Yapışkanlık olmasaydı bağlaç sözcüklerinin hiçbiri
    bir kategoriye düşmez, liste boşalır, ve dört turun üçü önbelleği
    ıskalardı.

    Bu test o kazancı sabitliyor: ``_ARA_CUMLELER`` listesi budanırsa ya
    da yapışkanlık bir yeniden düzenlemede düşerse burası kırmızı olur.
    """
    ajan = _ajan()
    for cumle in ("RAM kullanımı ne durumda?", "Peki", "Evet", "Devam et"):
        ajan.ask(cumle)
    imzalar = [_arac_imzasi(araclar) for _, araclar in ajan.llm.turlar]
    assert len(set(imzalar)) == 1, (
        "Ara cümlelerde araç şeması değişti; yapışkanlık çalışmıyor."
    )
    assert imzalar[0], "İlk turda hiç araç sunulmadı; ölçüm anlamsız."


# ---------------- araç şemaları ----------------

def test_the_model_is_not_handed_every_tool_at_once():
    """Araç şemaları da isteme giriyor; hepsini sunmak istemi şişiriyor
    ve modelin seçimini zorlaştırıyor."""
    ajan = _ajan()
    ajan.ask("RAM kullanımı ne durumda?")
    _, araclar = ajan.llm.turlar[0]
    assert araclar, "Sistem sorusunda hiç araç sunulmadı — daraltma fazla agresif."
    assert len(araclar) <= ARAC_SAYISI_TAVANI


def test_a_chat_turn_offers_no_tools_at_all():
    """"Merhaba" araç istemiyor. Eline arama aracı verilen model onu
    kullanmak için bahane arıyor — bu ölçülmüştü."""
    ajan = _ajan()
    ajan.ask("Merhaba, nasılsın?")
    _, araclar = ajan.llm.turlar[0]
    assert araclar == []


# ---------------- bütçe sabitlerinin kendisi ----------------

@pytest.mark.parametrize("tavan", [SISTEM_TAVANI, TUR_TAVANI])
def test_the_budgets_are_not_accidentally_disabled(tavan):
    """Bir tavanı devre dışı bırakmanın en sessiz yolu onu çok büyütmek.

    Bu test o hareketi görünür kılıyor: sınırı gerçekten yükseltmek
    gerekiyorsa burası da değişecek ve inceleme sırasında sorulacak.
    """
    assert tavan <= 20_000
