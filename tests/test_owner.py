"""Owner identity: storage, prompt rendering, and its separation from facts.

Fixtures use an invented name: the real owner's details belong in their local
database, not in a public repository.
"""
from jarvis.core.owner import Owner
from jarvis.core.persona import BASE_PROMPT, build_system_prompt
from jarvis.memory.store import MemoryStore


def _owner(**kw):
    base = dict(
        name="Deniz Yılmaz",
        address_forms=["Deniz", "Efendim"],
        role="tasarımcısı ve geliştiricisi",
        profession="bilgisayar teknik servisi",
        response_style="Teknik ve ayrıntılı; basit sorularda kısa.",
    )
    base.update(kw)
    return Owner(**base)


# ---------------- storage ----------------

def test_owner_roundtrip():
    s = MemoryStore(":memory:")
    s.set_owner(_owner())
    got = s.get_owner()
    assert got.name == "Deniz Yılmaz"
    assert got.address_forms == ["Deniz", "Efendim"]
    assert got.share_with_cloud is True


def test_no_owner_returns_unconfigured():
    owner = MemoryStore(":memory:").get_owner()
    assert not owner.configured and owner.to_prompt() == ""


def test_owner_update_replaces_single_row():
    s = MemoryStore(":memory:")
    s.set_owner(_owner())
    s.set_owner(_owner(name="Deniz Y."))
    assert s.get_owner().name == "Deniz Y."


def test_owner_survives_forget_fact():
    """Identity must not be deletable through the ordinary memory tools."""
    s = MemoryStore(":memory:")
    s.set_owner(_owner())
    s.remember("adım", "başka bir şey")
    s.forget("adım")
    assert s.get_owner().name == "Deniz Yılmaz"


def test_clear_owner():
    s = MemoryStore(":memory:")
    s.set_owner(_owner())
    assert s.clear_owner() is True
    assert not s.get_owner().configured


def test_cloud_flag_is_persisted():
    s = MemoryStore(":memory:")
    s.set_owner(_owner(share_with_cloud=False))
    assert s.get_owner().share_with_cloud is False


def test_corrupt_address_forms_do_not_crash():
    s = MemoryStore(":memory:")
    s.set_owner(_owner())
    s._conn.execute("UPDATE owner SET address_forms = 'bozuk json' WHERE id = 1")
    s._conn.commit()
    assert s.get_owner().address_forms == []


# ---------------- prompt ----------------

def test_prompt_contains_identity():
    text = _owner().to_prompt()
    assert "Deniz Yılmaz" in text
    assert "'Deniz'" in text and "'Efendim'" in text
    assert "tasarımcısı ve geliştiricisi" in text


def test_prompt_answers_who_made_you_directly():
    """The model answered this evasively; the instruction must be explicit."""
    text = _owner().to_prompt()
    assert "Seni kim tasarladı" in text
    assert "kaçamak cevap" in text
    assert "dil modeli başka bir kuruluşun" in text, "model kaynağı da dürüstçe ayrılmalı"


def test_prompt_defines_greeting():
    text = _owner().to_prompt()
    assert "hoş geldiniz" in text
    # Sadece adını söylemek bir çağrıdır, soru değil: kısa karşılık bekler.
    assert "SESLENİŞ" in text
    assert "Efendim?" in text


# ---------------- karşılama, iki kez düzeltildi ----------------
# 1) Once "ardindan tek bir kisa cumleyle yardim oner" yaziyordu ve teklifin
#    gercek yeteneklerle sinirli olmasi isteniyordu — olmayan bir takvimi
#    teklif etmesin diye.
# 2) O teklifin kendisi hataymis. Kisiligin ust kismi "Size nasil yardimci
#    olabilirim?" cumlesini ACIKCA yasakliyor; kimlik blogu ise ayni seyi
#    EMREDIYORDU. Model kurali cignemedi, iki kuraldan yakin ve somut olanina
#    uydu — ve "Ben senin gelistiricinim." cumlesine "Efendim, hos geldiniz.
#    Size nasil yardimci olabilirim?" cevabini verdi.
#
# Hicbir sey teklif etmemek, "yalnizca gercek olani teklif et"ten daha guclu
# bir garanti: teklif yoksa asiri vaat de yok.

def test_the_greeting_offers_nothing_at_all():
    text = _owner().to_prompt()
    assert "yardım teklif etme" in text
    assert "Ne yapabileceğini sıralama" in text
    assert "yardım öner" not in text, "yasaklanan cümleyi üreten emir geri gelmiş"


def test_the_greeting_only_applies_to_an_actual_greeting():
    """Ilk mesajin ICERIGI ne olursa olsun selamlama uretiyordu."""
    text = _owner().to_prompt()
    assert "YALNIZCA bir selamsa" in text
    assert "İLK MESAJDA BİR ŞEY SÖYLENDİYSE" in text
    assert "Ben senin geliştiricinim" in text, "somut örnek olmadan kural tutmadı"


def test_no_banned_filler_is_also_issued_as_an_instruction():
    """Bir cumle hem yasaklanip hem emredilirse, emir kazaniyor.

    Bu testin sinadigi sey tek bir ifade degil, bir HATA SINIFI: sistem
    isteminin kendi icinde celismesi. Yasak listesindeki bir cumle istemde
    ikinci kez geciyorsa, orada bir emir olma ihtimali var.
    """
    from jarvis.core.persona import build_system_prompt
    from jarvis.core.owner import Owner

    metin = build_system_prompt(
        Owner(name="Deniz Yılmaz", address_forms=["Deniz", "Efendim"],
              role="tasarımcısı ve geliştiricisi"), "")
    for yasak in ("Size nasıl yardımcı olabilirim",
                  "Başka bir şey ister misiniz"):
        assert metin.count(yasak) == 1, (
            f"{yasak!r} istemde {metin.count(yasak)} kez geçiyor; "
            "yasak listesinde bir kez geçmeli, emir olarak hiç geçmemeli")


def test_the_user_stating_a_known_fact_is_acknowledged_not_greeted():
    """Kayitta zaten yazan bir seyi kullanici soylerse, bu yeni bilgi degil."""
    text = _owner().to_prompt()
    assert "ben senin geliştiricinim" in text.lower()
    assert "kayıtlarında zaten" in text
    assert "boş bir selamla geçiştirme" in text


def test_prompt_frames_service_work_correctly():
    """A technician's 'this computer' is often a customer's machine, not theirs."""
    text = _owner().to_prompt()
    assert "teknik servis" in text
    assert "sor" in text, "belirsizlikte sorması gerektiği söylenmeli"


def test_build_system_prompt_composes_sections():
    prompt = build_system_prompt(_owner(), machine="CPU: 8 çekirdek · RAM: 32 GB")
    assert BASE_PROMPT in prompt
    assert "Deniz Yılmaz" in prompt
    assert "32 GB" in prompt


def test_build_system_prompt_without_owner_states_that_it_is_unknown():
    """Eskiden kimlik yokken hiçbir şey eklenmiyordu, ve bu bir kusurdu.

    Sessiz kalınca model boşluğu kendisi dolduruyor: "seni kim tasarladı"
    sorusuna kaçamak cevap veriyor, "Jarvis" seslenişine hitapsız karşılık
    veriyor, ve kullanıcı sistemin kendisini tanıdığını sanmaya devam
    ediyor. Şikâyet tam olarak buydu.
    """
    prompt = build_system_prompt(None, "")
    assert prompt.startswith(BASE_PROMPT)
    assert "TANIMLANMAMIŞ" in prompt
    assert "jarvis-tanit" in prompt
    # Boş bir Owner da "tanımlanmamış" sayılır: adı yoksa kimliği yoktur.
    bos = build_system_prompt(Owner(), "")
    assert "TANIMLANMAMIŞ" in bos


def test_persona_still_forbids_claiming_feelings():
    assert "duyguların olduğunu iddia etmezsin" in BASE_PROMPT


# ---------------- agent integration ----------------

def test_agent_loads_owner_into_prompt():
    from jarvis.bootstrap import build_agent
    from jarvis.config import Config

    store = MemoryStore(":memory:")
    store.set_owner(_owner())
    agent = build_agent(Config(llm_provider="mock", non_interactive=True), memory=store)
    assert "Deniz Yılmaz" in agent.history[0].content


def test_reload_owner_updates_live_session():
    from jarvis.bootstrap import build_agent
    from jarvis.config import Config

    store = MemoryStore(":memory:")
    agent = build_agent(Config(llm_provider="mock", non_interactive=True), memory=store)
    assert "Deniz" not in agent.history[0].content

    store.set_owner(_owner())
    agent.reload_owner()
    assert "Deniz Yılmaz" in agent.history[0].content


def test_persona_forbids_filler_closings():
    """The model habitually appended 'anything else?' to every answer."""
    assert "DOLDURMA CÜMLESİ EKLEME" in BASE_PROMPT
    assert "Başka bir şey ister misiniz?" in BASE_PROMPT
    assert "Başka bir şey istiyorsan?" in BASE_PROMPT, "gördüğümüz varyant da yasaklanmalı"
    assert "nokta koy" in BASE_PROMPT


def test_persona_requires_consistent_formality():
    """The model slipped into informal address mid-sentence."""
    assert "HİTAPTA TUTARLI OL" in BASE_PROMPT
    assert '"sen"e' in BASE_PROMPT


def test_persona_accepts_playful_address():
    assert "şakacı" in BASE_PROMPT
