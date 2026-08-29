"""``ask_stream`` — akışlı tur, ``ask`` ile aynı davranış.

Akışın değeri ölçüldü: 250 token'lık bir cevap 3,80 saniye sürüyor ve
akışsız yolda kullanıcı bunun tamamını hiçbir şey görmeden bekliyor.

Ama akış eklemek, ikinci bir tur yolu açmak demek — ve iki yol
zamanla birbirinden ayrılır. Buradaki testlerin çoğu hızı değil
**ikisinin aynı kalmasını** koruyor: aynı hafıza kaydı, aynı bekleyen
soru takibi, aynı araç çalıştırma, aynı adım sınırı.

Sağlayıcı akışı desteklemiyorsa (``mock``) cevap tek parça geliyor.
Çağıran taraf tek bir yol biliyor; "akış var mı" sorusunu her yerde
sormak gerekmiyor.
"""
from __future__ import annotations

import pytest

from jarvis.bootstrap import build_agent
from jarvis.config import Config
from jarvis.core.agent import Agent
from jarvis.core.state import JarvisState, StateMachine
from jarvis.llm.base import LLMResponse, Message, ToolCall
from jarvis.memory.store import MemoryStore
from jarvis.tools.base import Param, Tool, ToolRegistry
from jarvis.tools.manager import ToolManager
from jarvis.security.audit import AuditLog
from jarvis.security.permissions import PermissionManager, RiskLevel


class _AkanLLM:
    """Parça parça veren sahte sağlayıcı."""

    name = "akan"
    num_ctx = 8192

    def __init__(self, parcalar, cagrilar=None, tur_cagrilari=None):
        self.parcalar = parcalar
        self.son_yanit = LLMResponse()
        #: Her tur icin ayri arac cagrisi listesi (arac dongusunu sinamak icin).
        self.tur_cagrilari = list(tur_cagrilari or [])
        self.tek_seferlik = cagrilar
        self.cagri_sayisi = 0

    def chat_stream(self, messages, tools=None):
        self.cagri_sayisi += 1
        if self.tur_cagrilari:
            cagrilar = self.tur_cagrilari.pop(0)
        else:
            cagrilar = self.tek_seferlik if self.cagri_sayisi == 1 else None
        if cagrilar:
            self.son_yanit = LLMResponse(content="", tool_calls=list(cagrilar))
            return iter(())
        self.son_yanit = LLMResponse(content="".join(self.parcalar))
        return iter(self.parcalar)


class _DuzLLM:
    """Akışı desteklemeyen sağlayıcı — mock gibi."""

    name = "duz"
    num_ctx = 8192

    def __init__(self, metin="tek parça cevap"):
        self.metin = metin

    def chat(self, messages, tools=None):
        return LLMResponse(content=self.metin)


def _ajan(llm, kayit=None):
    kayit = kayit or ToolRegistry()
    # non_interactive: testte stdin'den onay beklenmemeli, yoksa surec asilir.
    izin = PermissionManager(audit=AuditLog(), non_interactive=True)
    return Agent(llm=llm, tools=ToolManager(kayit, izin), registry=kayit,
                 state=StateMachine(), memory=MemoryStore(":memory:"))


# ---------------- akış gerçekten akıyor mu ----------------

def test_the_answer_arrives_in_pieces():
    """Akisin butun anlami: cevap bitmeden parca gelmeli."""
    ajan = _ajan(_AkanLLM(["Sistem", " hazır", " efendim."]))
    assert list(ajan.ask_stream("merhaba")) == ["Sistem", " hazır", " efendim."]


def test_the_whole_answer_lands_in_history():
    ajan = _ajan(_AkanLLM(["Sistem", " hazır."]))
    list(ajan.ask_stream("merhaba"))
    assert ajan.history[-1].content == "Sistem hazır."
    assert ajan.history[-1].role == "assistant"


def test_a_provider_without_streaming_still_answers():
    """mock saglayicida akis yok; cagiran taraf bunu bilmek zorunda kalmamali."""
    ajan = _ajan(_DuzLLM("tek parça cevap"))
    assert list(ajan.ask_stream("merhaba")) == ["tek parça cevap"]


def test_the_real_mock_provider_works_through_the_stream():
    ajan = build_agent(Config(llm_provider="mock", non_interactive=True),
                       memory=MemoryStore(":memory:"))
    parcalar = list(ajan.ask_stream("Merhaba"))
    assert parcalar and "".join(parcalar) == ajan.history[-1].content


# ---------------- ask ile aynı davranış ----------------

def test_both_paths_record_the_answer_in_memory():
    """Hafiza kaydi akisli yolda unutulursa "bugun ne yaptik" bozulur."""
    ajan = _ajan(_AkanLLM(["cevap"]))
    list(ajan.ask_stream("merhaba"))
    kayitli = ajan.memory.recent_messages(ajan.session_id)
    assert [m.role for m in kayitli] == ["user", "assistant"]
    assert kayitli[-1].content == "cevap"


def test_both_paths_track_the_pending_question():
    """Kullanicinin bir sonraki "evet"i buna bagli."""
    ajan = _ajan(_AkanLLM(["Devam edeyim mi?"]))
    list(ajan.ask_stream("merhaba"))
    assert ajan.durum.pending_question == "Devam edeyim mi?"


def test_both_paths_end_in_standby():
    ajan = _ajan(_AkanLLM(["cevap"]))
    list(ajan.ask_stream("merhaba"))
    assert ajan.state.state is JarvisState.STANDBY


def test_the_two_paths_produce_the_same_text():
    """Ayni girdi, ayni cevap. Ayrisirlarsa fark yalnizca akisli yolda
    gorunur ve testler yesil kalir — bu test tam onu engelliyor."""
    duz = build_agent(Config(llm_provider="mock", non_interactive=True),
                      memory=MemoryStore(":memory:"))
    akisli = build_agent(Config(llm_provider="mock", non_interactive=True),
                         memory=MemoryStore(":memory:"))
    assert duz.ask("Merhaba") == "".join(akisli.ask_stream("Merhaba"))


# ---------------- araç turları ----------------

def _sayac_kaydi():
    kayit = ToolRegistry()
    kayit.register(Tool(name="sayac", description="test aracı",
                        risk=RiskLevel.LOW, func=lambda: {"deger": 42},
                        params=[]))
    return kayit


def test_a_tool_round_runs_and_then_the_answer_streams():
    """Model arac isterken metin uretmiyor; akis yalnizca ASIL cevapta akiyor."""
    llm = _AkanLLM(["Bellek", " 42."],
                   tur_cagrilari=[[ToolCall(name="sayac", arguments={})], []])
    ajan = _ajan(llm, _sayac_kaydi())
    assert list(ajan.ask_stream("bellek?")) == ["Bellek", " 42."]


def test_the_tool_result_reaches_the_history():
    llm = _AkanLLM(["tamam"],
                   tur_cagrilari=[[ToolCall(name="sayac", arguments={})], []])
    ajan = _ajan(llm, _sayac_kaydi())
    list(ajan.ask_stream("bellek?"))
    arac = [m for m in ajan.history if m.role == "tool"]
    assert len(arac) == 1 and arac[0].name == "sayac"


def test_a_tool_only_provider_without_streaming_still_loops():
    """Akissiz saglayicida da arac dongusu calismali."""
    class _AracIsteyen:
        name = "arac"
        num_ctx = 8192

        def __init__(self):
            self.n = 0

        def chat(self, messages, tools=None):
            self.n += 1
            if self.n == 1:
                return LLMResponse(tool_calls=[ToolCall(name="sayac", arguments={})])
            return LLMResponse(content="sonuç 42")

    ajan = _ajan(_AracIsteyen(), _sayac_kaydi())
    assert list(ajan.ask_stream("bellek?")) == ["sonuç 42"]


# ---------------- emniyet vanası ----------------

def test_an_endless_tool_loop_still_stops():
    """Adim siniri akisli yolda da gecerli olmali; sonsuz dongu yok."""
    hep = [[ToolCall(name="sayac", arguments={})] for _ in range(20)]
    ajan = _ajan(_AkanLLM(["asla gelmeyecek"], tur_cagrilari=hep), _sayac_kaydi())
    cikti = list(ajan.ask_stream("bellek?"))
    assert len(cikti) == 1
    assert "tamamlayamadım" in cikti[0]


def test_the_step_limit_is_the_same_for_both_paths():
    hep = [[ToolCall(name="sayac", arguments={})] for _ in range(20)]
    ajan = _ajan(_AkanLLM(["x"], tur_cagrilari=list(hep)), _sayac_kaydi())
    list(ajan.ask_stream("bellek?"))
    # max_steps kadar tur donmus olmali, daha fazlasi degil.
    assert ajan.llm.cagri_sayisi == ajan.max_steps
