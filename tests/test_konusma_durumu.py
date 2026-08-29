"""Konuşma durumu ve bağlam penceresi.

İki iş bir arada sınanıyor çünkü ikisi aynı sorunun iki yüzü.

**Pencere.** Geçmiş hiç kırpılmıyordu: listeye ekleme vardı, çıkarma yoktu.
Pencere taştığında Ollama en eski mesajı düşürüyor ve o mesaj sistem istemi —
kişilik, Türkçe kuralı, kullanıcının kimliği. Yani kırpmayı biz yapmazsak
model yapıyor ve en kötü yerden yapıyor.

**Durum.** Körlemesine kırpmak bilgiyi kaybetmek demek:

    "Qwen 14B'yi kurdum."  →  "Ollama üzerinden mi?"  →  "Evet."

Son mesaj tek başına anlamsız. Kırpma soruyu düşürürse model neyin
onaylandığını bilmiyor ve konuşma sessizce kopuyor.
"""
from __future__ import annotations

import pytest

from jarvis.bootstrap import build_agent
from jarvis.config import Config
from jarvis.core.konusma import (
    EN_AZ_TUR,
    KonusmaDurumu,
    bagli_cevap_mi,
    bekleyen_soruyu_yakala,
    butce_karakteri,
    durumu_guncelle,
    ozetle,
    pencerele,
)
from jarvis.llm.base import Message
from jarvis.memory.store import MemoryStore


def _ajan():
    return build_agent(Config(llm_provider="mock", non_interactive=True),
                       memory=MemoryStore(":memory:"))


def _uzunluk(mesajlar) -> int:
    return sum(len(m.content) for m in mesajlar)


# ---------------- pencere gerçekten tutuyor mu ----------------

class _OlcenLLM:
    """Modele GERÇEKTEN ne gönderildiğini kaydeder.

    Bütçe, gönderilen istem için geçerli — ``ask()`` döndükten sonraki
    geçmiş için değil, çünkü o an modelin cevabı da eklenmiş oluyor.
    Yanlış anda ölçmek, doğru kodu hatalı gösteriyordu.
    """

    num_ctx = 8192

    def __init__(self) -> None:
        self.en_buyuk = 0

    def chat(self, messages, tools=None):
        from jarvis.llm.base import LLMResponse
        self.en_buyuk = max(self.en_buyuk, sum(len(m.content) for m in messages))
        return LLMResponse(content="Tamam efendim.", tool_calls=[])


def _olcen_ajan():
    from jarvis.core.agent import Agent
    from jarvis.core.state import StateMachine
    from jarvis.tools.base import ToolRegistry
    from jarvis.tools.manager import ToolManager

    llm = _OlcenLLM()
    kayit = ToolRegistry()
    ajan = Agent(llm=llm, tools=ToolManager(kayit, None), registry=kayit,
                 state=StateMachine())
    return ajan, llm


@pytest.mark.parametrize("tur", [50, 200, 500])
def test_the_prompt_stays_within_budget_however_long_the_session_runs(tur):
    """Kirpma olmadan 300 tur pencerenin %195'ini yiyordu."""
    ajan, llm = _olcen_ajan()
    for i in range(tur):
        ajan.ask(f"Bu {i}. mesajım ve epeyce uzun bir cümle kuruyorum.")
    assert llm.en_buyuk <= butce_karakteri(ajan.num_ctx)


@pytest.mark.parametrize("tur", [50, 500])
def test_the_stored_history_does_not_grow_with_the_turn_count(tur):
    """Kirpma calisiyorsa 50 tur ile 500 tur ayni yerde durmali."""
    a = _ajan()
    for i in range(tur):
        a.ask(f"Bu {i}. mesajım ve epeyce uzun bir cümle kuruyorum.")
    # Butce + son cevap + durum blogu kadar pay birakiliyor: butce
    # GONDERILEN istem icin gecerli, saklanan gecmis icin degil.
    assert _uzunluk(a.history) <= butce_karakteri(a.num_ctx) * 1.1


def test_the_system_prompt_is_never_the_thing_that_gets_dropped():
    """Kirpmayi biz yapmazsak model yapiyor ve tam bunu dusuruyor."""
    a = _ajan()
    for i in range(300):
        a.ask(f"mesaj {i} " + "x" * 200)
    assert a.history[0].role == "system"
    assert a.history[0].content.startswith("Sen J.A.R.V.I.S.")


def test_identical_messages_do_not_defeat_the_trimming():
    """Olcumle yakalanan hata: Message bir dataclass, yani iki ayni metin
    ESIT sayiliyor. Deger uyelugu ile calisan kirpma, tekrarlanan bir
    cumle ("evet", "tamam") yuzunden hicbir sey atmiyordu."""
    ajan, llm = _olcen_ajan()
    for _ in range(300):
        ajan.ask("evet")         # hepsi birebir ayni
    assert llm.en_buyuk <= butce_karakteri(ajan.num_ctx)


def test_the_most_recent_turns_always_survive():
    """Butce ne derse desin: "az once ne dedim"in bir cevabi olmali."""
    gecmis = [Message(role="system", content="S" * 5000)]
    for i in range(60):
        gecmis.append(Message(role="user", content=f"soru {i} " + "u" * 900))
    kalan, _ = pencerele(gecmis, 1024)          # bilerek kucuk pencere
    konusma = [m for m in kalan if m.role != "system"]
    assert len(konusma) >= EN_AZ_TUR
    assert "soru 59" in konusma[-1].content


def test_dropped_messages_are_handed_back_not_thrown_away():
    """Ozet onlardan cikiyor; atilirlarsa kirpma korlesir."""
    gecmis = [Message(role="system", content="S")]
    for i in range(50):
        gecmis.append(Message(role="user", content=f"m{i} " + "x" * 500))
    kalan, dusen = pencerele(gecmis, 2048)
    assert dusen
    assert len(kalan) + len(dusen) == len(gecmis)


def test_nothing_is_dropped_when_it_all_fits():
    gecmis = [Message(role="system", content="S"),
              Message(role="user", content="kısa")]
    kalan, dusen = pencerele(gecmis, 8192)
    assert dusen == []
    assert len(kalan) == 2


# ---------------- "evet" neye evet ----------------

def test_the_assistants_question_is_remembered():
    d = bekleyen_soruyu_yakala(
        KonusmaDurumu(), "Harika. Ollama üzerinden mi çalıştırıyorsun?")
    assert d.pending_question == "Ollama üzerinden mi çalıştırıyorsun?"


def test_only_the_last_sentence_is_kept_as_the_question():
    """Uzun bir cevabin tamamini tasimak, korumasi gereken seyi baglam
    yukune cevirir."""
    uzun = ("Sistemi kontrol ettim ve her şey yolunda görünüyor. "
            "Devam etmemi ister misiniz?")
    d = bekleyen_soruyu_yakala(KonusmaDurumu(), uzun)
    assert d.pending_question == "Devam etmemi ister misiniz?"


def test_a_statement_leaves_no_pending_question():
    d = bekleyen_soruyu_yakala(KonusmaDurumu(), "İşlem tamamlandı.")
    assert d.pending_question == ""


@pytest.mark.parametrize("cevap", ["evet", "Evet.", "hayır", "Tamam", "olur", "aynen"])
def test_a_bare_answer_is_recognised_as_bound_to_a_question(cevap):
    assert bagli_cevap_mi(cevap) is True


@pytest.mark.parametrize("cumle", [
    "evet ama önce şunu kontrol edelim",
    "Bilgisayar açılmıyor",
])
def test_a_sentence_with_content_is_not_a_bare_answer(cumle):
    assert bagli_cevap_mi(cumle) is False


def test_the_question_survives_until_it_is_answered():
    d = bekleyen_soruyu_yakala(KonusmaDurumu(), "Ollama üzerinden mi?")
    d = durumu_guncelle(d, [], "Evet.")
    assert d.pending_question == "Ollama üzerinden mi?"


def test_a_new_subject_clears_the_pending_question():
    """Yoksa her turda tasinip birikirdi ve model eski bir soruya
    cevap bekliyormus gibi davranirdi."""
    d = bekleyen_soruyu_yakala(KonusmaDurumu(), "Ollama üzerinden mi?")
    d = durumu_guncelle(d, [], "Boş ver, disk sağlığına bakalım.")
    assert d.pending_question == ""


def test_the_pending_question_is_protected_from_trimming():
    """Sizin orneginiz: soru 300 mesaj geride kalsa bile pencerede kalmali."""
    d = bekleyen_soruyu_yakala(KonusmaDurumu(), "Ollama üzerinden mi çalıştırıyorsun?")
    gecmis = [Message(role="system", content="S"),
              Message(role="assistant",
                      content="Harika. Ollama üzerinden mi çalıştırıyorsun?")]
    for i in range(200):
        gecmis.append(Message(role="user", content=f"dolgu {i} " + "x" * 200))
        gecmis.append(Message(role="assistant", content=f"tamam {i} " + "y" * 200))
    kalan, _ = pencerele(gecmis, 8192, d)
    assert any(d.pending_question in m.content for m in kalan)


def test_the_state_block_tells_the_model_what_is_pending():
    d = bekleyen_soruyu_yakala(KonusmaDurumu(), "Ollama üzerinden mi?")
    assert "Ollama üzerinden mi?" in d.ozet_satiri()


def test_an_empty_state_adds_nothing_to_the_context():
    """Bos bir blok da baglamda yer kapliyor."""
    assert KonusmaDurumu().ozet_satiri() == ""


# ---------------- konu ve varlıklar ----------------

def test_entities_are_picked_up_from_the_conversation():
    d = durumu_guncelle(KonusmaDurumu(), [], "Qwen 14B'yi Ollama ile kurdum.")
    assert "Qwen" in d.referenced_entities
    assert any("14B" in v for v in d.referenced_entities)


def test_the_entity_list_cannot_grow_without_limit():
    """Sinirsiz birakmak, listenin kendisinin baglami yemesi demek."""
    from jarvis.core.konusma import EN_FAZLA_VARLIK
    d = KonusmaDurumu()
    for i in range(100):
        d = durumu_guncelle(d, [], f"Model{i} kurdum.")
    assert len(d.referenced_entities) <= EN_FAZLA_VARLIK


def test_the_topic_comes_from_the_existing_classifier():
    """Ikinci bir siniflandirici, iki ayri dogruluk tanimi demek olurdu."""
    d = durumu_guncelle(KonusmaDurumu(), [], "CPU sıcaklığı kaç derece?")
    assert d.current_topic == "sistem"


def test_the_topic_holds_when_a_turn_matches_nothing():
    """"Peki" demek konuyu degistirmiyor."""
    d = durumu_guncelle(KonusmaDurumu(), [], "CPU sıcaklığı kaç derece?")
    d = durumu_guncelle(d, [], "peki")
    assert d.current_topic == "sistem"


def test_the_last_tool_is_tracked():
    gecmis = [Message(role="tool", name="get_ram_usage", content="{}")]
    d = durumu_guncelle(KonusmaDurumu(), gecmis, "ram?")
    assert d.active_tool == "get_ram_usage"


# ---------------- özet ----------------

def test_the_summary_keeps_a_trace_of_what_fell_out():
    dusen = [Message(role="user", content="Qwen 14B'yi kurdum."),
             Message(role="assistant", content="Harika, Ollama ile mi?")]
    ozet = ozetle(dusen)
    assert "Qwen" in ozet
    assert "Kullanıcı:" in ozet and "Sen:" in ozet


def test_tool_output_stays_out_of_the_summary():
    """Ciktilari uzun, tekrarli, ve sonuclari zaten konusmanin icinde."""
    dusen = [Message(role="tool", name="get_ram_usage",
                     content="{'toplam': '32 GB'}" * 50)]
    assert ozetle(dusen) == ""


def test_the_summary_cannot_grow_without_limit():
    """Ozetin kendisi baglami yerse kirpmanin anlami kalmaz."""
    from jarvis.core.konusma import OZET_SATIR
    ozet = ""
    for i in range(200):
        ozet = ozetle([Message(role="user", content=f"mesaj {i} " + "x" * 400)], ozet)
    assert len(ozet.split("\n")) <= OZET_SATIR


def test_a_long_session_ends_up_with_a_summary():
    a = _ajan()
    for i in range(200):
        a.ask(f"mesaj {i} " + "x" * 200)
    assert a.durum.conversation_summary


# ---------------- ajana bağlandı mı ----------------

def test_the_agent_takes_its_window_from_the_provider():
    """Saglayici 32768 ile kurulduysa ajan 8192'ye gore kirpmamali."""
    class SahteLLM:
        num_ctx = 32768
        def chat(self, messages, tools=None):
            from jarvis.llm.base import LLMResponse
            return LLMResponse(content="tamam", tool_calls=[])

    from jarvis.core.agent import Agent
    from jarvis.core.state import StateMachine
    from jarvis.tools.base import ToolRegistry
    from jarvis.tools.manager import ToolManager

    kayit = ToolRegistry()
    a = Agent(llm=SahteLLM(), tools=ToolManager(kayit, None), registry=kayit,
              state=StateMachine())
    assert a.num_ctx == 32768


def test_the_state_block_does_not_accumulate():
    """Diger bloklarla ayni kural: her turda silinip yeniden yaziliyor."""
    a = _ajan()
    for _ in range(10):
        a.ask("Devam edelim mi?")
    bloklar = [m for m in a.history if m.content.startswith(a.DURUM_ONEKI)]
    assert len(bloklar) <= 1
