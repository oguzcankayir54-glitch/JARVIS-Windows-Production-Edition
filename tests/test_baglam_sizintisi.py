"""Arka uç dilinin kullanıcıya sızmaması.

Bu dosya tek bir gerçek şikâyetten doğdu. Sahibi şunu yazdı:

    "Ben senin geliştiricinim."

ve şu cevabı aldı:

    "Bilgi tabanınız şu an için kurulmuş ancak boş. Bilgi eklemek için
     'jarvis-bilgi ekle <klasör>' komutunu kullanabilirsiniz..."

Cevabı model uydurmadı. ``Agent._knowledge_context()`` bilgi tabanı boşken
HER TURDA, sistem isteminin hemen ardına — yani kullanıcının cümlesine
persona'dan çok daha yakın bir yere — içinde "neleri kaydettiğini sorarsa"
geçen ve ``jarvis-bilgi ekle <klasör>`` komutunu birebir taşıyan bir talimat
koyuyordu. "Ben senin geliştiricinim" bir KAYIT cümlesi; model yakın ve somut
talimatı, uzak ve genel kişiliğe tercih etti.

Buradaki testler o bloğun geri gelmesini engelliyor. Hepsi ucuz ve modelsiz:
gerçek bir LLM'e ihtiyaç duymadan, modele NE GÖNDERİLDİĞİNİ denetliyorlar —
zaten hata da orada, gönderilenin içindeydi.
"""
from __future__ import annotations

import json

import pytest

from jarvis.bootstrap import build_agent
from jarvis.config import Config
from jarvis.core.arac_secici import araclari_sec
from jarvis.memory.store import MemoryStore

#: Kullanicinin ekraninda gormemesi gereken kabuk komutlari. Bunlar modele
#: gonderilen metinde geciyorsa, er ya da gec cevapta da gecer.
KOMUTLAR = ("jarvis-bilgi ekle", "ollama pull", "jarvis-panel", "pip install")

#: Hicbir kategoriye dusmeyen, yani duz sohbet olan cumleler. Dordu de
#: gercek sikayetlerden alindi.
SOHBET = [
    "Ben senin geliştiricinim.",
    "Nasılsın Jarvis?",
    "Eğitim süreci 1.",
    "Canım sıkılıyor.",
    "Bugün biraz yoruldum.",
]


class SahteTaban:
    """Gerçek indeks kurmadan bilgi tabanı durumu taklit eder."""

    def __init__(self, parca: int = 0, patla: bool = False) -> None:
        self._parca = parca
        self._patla = patla

    def stats(self) -> dict:
        if self._patla:
            raise RuntimeError("indeks okunamadı")
        return {"belge": 3 if self._parca else 0, "parca": self._parca,
                "anlam_aramasi": True, "model": "bge-m3"}


def _ajan(taban=None):
    ajan = build_agent(Config(llm_provider="mock", non_interactive=True),
                       memory=MemoryStore(":memory:"))
    if taban is not None:
        ajan.knowledge = taban
    return ajan


def _adlar(semalar) -> list[str]:
    return [(s.get("function") or {}).get("name") for s in semalar]


def _tur_araclari(ajan, metin: str) -> list[str]:
    """``ask`` içindeki seçimin aynısı — kopya değil, aynı sıra."""
    adaylar = ajan.registry.schemas()
    if ajan._bilgi_tabani_bos():
        adaylar = [s for s in adaylar
                   if (s.get("function") or {}).get("name") != "bilgi_ara"]
    return _adlar(araclari_sec(adaylar, metin, ajan.arac_siniri))


# ---------------- kök sebep ----------------

@pytest.mark.parametrize("cumle", SOHBET)
def test_no_shell_command_is_ever_pushed_into_the_context(cumle):
    """Modele komut gönderilmezse kullanıcıya komut okunamaz."""
    ajan = _ajan(SahteTaban(parca=0))
    ajan.ask(cumle)
    butun = "\n".join(m.content for m in ajan.history)
    for komut in KOMUTLAR:
        assert komut not in butun, f"{cumle!r} turunda '{komut}' bağlama girdi"


def test_an_empty_knowledge_base_announces_nothing():
    """Boş bir özelliği her turda duyurmak, sohbetin tamamını kirletiyordu."""
    ajan = _ajan(SahteTaban(parca=0))
    assert ajan._knowledge_context() is None


def test_the_developer_sentence_gets_a_clean_context():
    """Şikâyetin tam cümlesi. Bağlamda bilgi tabanı bloğu olmamalı."""
    ajan = _ajan(SahteTaban(parca=0))
    ajan.ask("Ben senin geliştiricinim.")
    bloklar = [m.content for m in ajan.history
               if m.content.startswith(ajan.BILGI_ONEKI)]
    assert bloklar == []


# ---------------- özellik bozulmadı mı ----------------
# Sizintiyi kesmenin kolay yolu ozelligi kapatmakti; o cozum degil.

def test_a_populated_knowledge_base_is_still_announced():
    ajan = _ajan(SahteTaban(parca=120))
    mesaj = ajan._knowledge_context()
    assert mesaj is not None
    assert "120" in mesaj.content
    assert "bilgi_ara" in mesaj.content


def test_the_populated_announcement_carries_no_command():
    ajan = _ajan(SahteTaban(parca=120))
    icerik = ajan._knowledge_context().content
    for komut in KOMUTLAR:
        assert komut not in icerik


def test_search_is_offered_when_there_is_something_to_search():
    ajan = _ajan(SahteTaban(parca=120))
    assert "bilgi_ara" in _tur_araclari(ajan, "Projede authentication nasıl çalışıyor?")


def test_a_broken_index_never_drops_the_turn():
    """İndeks okunamıyorsa tur yine tamamlanmalı; boş sayılıp geçilir."""
    ajan = _ajan(SahteTaban(patla=True))
    assert ajan._bilgi_tabani_bos() is True
    assert ajan.ask("Merhaba")


# ---------------- araç masaya konmuyor ----------------

@pytest.mark.parametrize("cumle", SOHBET)
def test_chat_turns_are_not_handed_a_search_tool(cumle):
    """Eline arama aracı verilen model onu kullanmak için bahane arıyor."""
    ajan = _ajan(SahteTaban(parca=0))
    assert "bilgi_ara" not in _tur_araclari(ajan, cumle)


def test_an_empty_base_offers_no_search_even_for_a_document_question():
    """Aranacak bir şey yokken arama aracı yalnızca 'sonuç yok' döndürebilir."""
    ajan = _ajan(SahteTaban(parca=0))
    assert "bilgi_ara" not in _tur_araclari(ajan, "Projede authentication nerede?")


def test_the_default_tools_do_not_include_search():
    from jarvis.core.arac_secici import VARSAYILAN
    assert "bilgi_ara" not in VARSAYILAN
    # Araci tamamen kaldirmak da yanlis olurdu: aracsiz model CPU
    # sicakligini uyduruyor. Sigorta duruyor, arama sigorta degil.
    assert "get_system_info" in VARSAYILAN


# ---------------- hafıza ile belge arşivi karışmasın ----------------
# "Benim hakkimda ne biliyorsun?" HAFIZA sorusu. bilgi_durum aracinin
# aciklamasi bu cumleleri kendine cekiyordu.

def test_a_question_about_the_user_goes_to_memory_not_to_documents():
    ajan = _ajan(SahteTaban(parca=120))
    araclar = _tur_araclari(ajan, "Benim hakkımda ne biliyorsun?")
    assert "recall_facts" in araclar
    assert "bilgi_ara" not in araclar


def test_the_status_tool_does_not_claim_memory_questions():
    """Arac aciklamasi modelin tek yonlendirmesi; yanlis ornek yanlis arac."""
    ajan = _ajan(SahteTaban(parca=120))
    sema = next(s for s in ajan.registry.schemas()
                if (s.get("function") or {}).get("name") == "bilgi_durum")
    aciklama = json.dumps(sema, ensure_ascii=False)
    assert "recall_facts" in aciklama, "hafızaya yönlendirmeli"


def test_the_status_tool_reports_an_empty_base_as_a_fact():
    """Arac sonucu modelin okudugu metin: icine komut koyarsak kullanici duyar."""
    from jarvis.rag.index import KnowledgeBase
    from jarvis.tools.base import ToolRegistry
    from jarvis.tools.rag_tools import register_rag_tools

    class BosTaban:
        def stats(self):
            return {"belge": 0, "parca": 0, "anlam_aramasi": False, "model": ""}

    kayit = register_rag_tools(ToolRegistry(), BosTaban())
    sonuc = kayit.get("bilgi_durum").func()
    assert sonuc["kurulu"] is True
    assert sonuc["parca"] == 0
    for komut in KOMUTLAR:
        assert komut not in sonuc["not"]


# ---------------- kişilik ----------------

def test_the_persona_forbids_speaking_in_backend_language():
    """Nasil anlatilacagi kisiligin isi; arac ve baglam yalnizca olguyu tasir."""
    from jarvis.core.persona import build_system_prompt
    metin = build_system_prompt()
    assert "ARKA UÇ DİLİYLE KONUŞMA" in metin
    assert "öğretebilirsiniz" in metin, "bilmediğini insan gibi söylemeli"
