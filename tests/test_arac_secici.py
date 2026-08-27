"""Araç daraltma: neden var ve neyi bozmamalı.

Ölçülmüş bir sorun. qwen2.5:3b'ye 26 araç şeması gönderildiğinde 5000
karakterlik sistem istemi bastırılıyor:

* "Jarvis" → İngilizce, kişiliksiz bir cevap
* "sen kimsin" → "I am a language model"
* "cpu sıcaklığı nedir" → ``run_terminal_command`` (yanlış araç), bir
  denemede ise ham JSON'un metin olarak kusulması

Aynı sorular 6–8 araçla doğru cevaplanıyor. Kullanıcının üç ayrı şikâyeti
("İngilizce cevap veriyor", "beni tanımıyor", "söylediğimi anlamıyor") tek
bir sebebe çıkıyordu.

Buradaki testlerin çoğu daraltmanın işe yaradığını değil, **yanlış şeyi
elemediğini** koruyor: bir aracı gizlemek, o aracı silmekle aynı sonucu
verir.
"""
import pytest

from jarvis.core.arac_secici import (
    KATEGORILER,
    VARSAYILAN,
    VARSAYILAN_SINIR,
    araclari_sec,
    kategorileri_bul,
)


@pytest.fixture(scope="module")
def semalar():
    from jarvis.tools.base import ToolRegistry
    from jarvis.bootstrap import build_agent
    from jarvis.config import Config
    from jarvis.memory.store import MemoryStore
    ajan = build_agent(Config(llm_provider="mock", non_interactive=True),
                       memory=MemoryStore(":memory:"))
    return ajan.registry.schemas()


def _adlar(secilen):
    return [s["function"]["name"] for s in secilen]


# ---------------- doğru aracı getirmek ----------------

@pytest.mark.parametrize("soru,beklenen", [
    ("cpu sıcaklığı nedir", "get_cpu_temperature"),
    ("ram kullanımı ne durumda", "get_ram_usage"),
    ("diskin smart değerleri", "get_disk_health"),
    ("youtube aç", "uygulama_ac"),
    ("not defterini aç", "uygulama_ac"),
    ("bunu hatırla: parolam kasada", "remember_fact"),
    ("ekran kartı fiyatlarını internetten araştır", "web_ara"),
    ("bu vakayı kaydet", "vaka_ac"),
])
def test_the_right_tool_survives_the_narrowing(semalar, soru, beklenen):
    assert beklenen in _adlar(araclari_sec(semalar, soru))


def test_the_limit_is_respected(semalar):
    for soru in ("cpu sıcaklığı", "youtube aç", "hiçbir şey"):
        assert len(araclari_sec(semalar, soru, 8)) <= 8


def test_narrowing_can_be_switched_off(semalar):
    """Büyük bir model 26 aracı taşıyor; orada daraltmak yetenek kaybı olur."""
    assert araclari_sec(semalar, "cpu sıcaklığı", 0) == semalar
    assert araclari_sec(semalar, "cpu sıcaklığı", -1) == semalar


def test_a_short_list_is_left_alone(semalar):
    az = semalar[:3]
    assert araclari_sec(az, "herhangi bir şey", 8) == az


# ---------------- eşleşme olmadığında ----------------

def test_an_unmatched_question_still_gets_tools(semalar):
    """Araçsız bırakmak çözüm değil: araçsız model CPU sıcaklığını UYDURDU."""
    secilen = _adlar(araclari_sec(semalar, "bugün hava nasıl acaba"))
    assert secilen
    assert set(secilen) <= set(_adlar(semalar))


def test_the_fallback_tools_actually_exist(semalar):
    """Var olmayan bir ada geri düşmek sessizce boş liste üretirdi."""
    mevcut = set(_adlar(semalar))
    for ad in VARSAYILAN:
        assert ad in mevcut, f"{ad} kayıtta yok"


def test_empty_input_does_not_crash(semalar):
    assert araclari_sec(semalar, "")
    assert araclari_sec(semalar, "   ")
    assert kategorileri_bul("") == []


# ---------------- Türkçe ----------------

def test_turkish_folding_is_used(semalar):
    """IŞIK/ışık sorunu burada da geçerli; ekler de öyle."""
    for yazim in ("SICAKLIK", "sıcaklık", "sicaklik", "sıcaklığı", "SICAKLIĞI"):
        assert "sistem" in kategorileri_bul(yazim), yazim


def test_suffixes_do_not_hide_a_match():
    """Türkçe eklemeli: 'sıcaklıktan' da 'sıcaklık' demektir."""
    for yazim in ("sıcaklıktan", "sıcaklığını", "bellekteki", "diskimde"):
        assert kategorileri_bul(yazim), yazim


def test_the_strongest_category_comes_first():
    siralı = kategorileri_bul("disk sıcaklığı ve ram kullanımı")
    assert siralı[0] == "sistem"


# ---------------- kayıt bütünlüğü ----------------

def test_every_registered_tool_has_a_category(semalar):
    """Kategorisi olmayan bir araç hiçbir zaman seçilmez — sessizce kaybolur."""
    eksik = [ad for ad in _adlar(semalar) if ad not in KATEGORILER]
    assert not eksik, f"kategorisiz araçlar: {eksik}"


def test_no_category_maps_to_a_tool_that_does_not_exist(semalar):
    mevcut = set(_adlar(semalar))
    hayalet = [ad for ad in KATEGORILER if ad not in mevcut]
    assert not hayalet, f"kayıtta olmayan araçlar: {hayalet}"


# ---------------- ajana bağlanması ----------------

def test_the_agent_narrows_before_asking_the_model(monkeypatch):
    from jarvis.bootstrap import build_agent
    from jarvis.config import Config
    from jarvis.memory.store import MemoryStore

    ajan = build_agent(Config(llm_provider="mock", non_interactive=True),
                       memory=MemoryStore(":memory:"))
    gorulen = {}
    asil = ajan.llm.chat

    def izle(mesajlar, tools=None):
        gorulen["adet"] = len(tools or [])
        gorulen["adlar"] = [t["function"]["name"] for t in (tools or [])]
        return asil(mesajlar, tools=tools)

    monkeypatch.setattr(ajan.llm, "chat", izle)
    ajan.ask("cpu sıcaklığı nedir")
    assert gorulen["adet"] <= VARSAYILAN_SINIR
    assert "get_cpu_temperature" in gorulen["adlar"]


def test_the_limit_comes_from_configuration():
    from jarvis.bootstrap import build_agent
    from jarvis.config import Config
    from jarvis.memory.store import MemoryStore
    ajan = build_agent(Config(llm_provider="mock", non_interactive=True,
                              arac_siniri=3), memory=MemoryStore(":memory:"))
    assert ajan.arac_siniri == 3
