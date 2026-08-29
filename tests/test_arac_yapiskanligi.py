"""Araç listesinin sabit kalması — ölçülmüş bir hız kazancı.

Qwen'in şablonu araç şemalarını SİSTEM bloğunun içine koyuyor. Liste
değişince blok değişiyor ve Ollama'nın istem önbelleği ıskalanıyor.
Kullanıcının makinesinde ölçüldü (RTX 3080 Ti, qwen2.5:14b-instruct):

    aynı istem, 1. kez   →  okuma 2,19 sn
    aynı istem, 2. kez   →  okuma 0,02 sn        (110 kat)

250 token'lık gerçekçi bir cevapta üretim 3,80 sn. Okuma da eklenince
tur 6,0 saniyeye çıkıyor; önbellek tuttuğunda 3,8 saniyede bitiyor.
Yani listeyi sabit tutmak turun **%37'sini** geri veriyor.

Yapışkanlık yalnızca ARA cümlelerde devreye giriyor: "peki", "evet",
"tamam" gibi hiçbir kategori çağrıştırmayan turlarda konu hâlâ bir
öncekidir. Kullanıcı gerçekten konu değiştirdiğinde liste DEĞİŞMELİ —
önbellek uğruna yanlış araç göstermek, hızlı ama işe yaramaz bir
asistan demek olurdu.
"""
from __future__ import annotations

import pytest

from jarvis.bootstrap import build_agent
from jarvis.config import Config
from jarvis.core.arac_secici import araclari_sec, kategorileri_bul
from jarvis.memory.store import MemoryStore


@pytest.fixture(scope="module")
def semalar():
    ajan = build_agent(Config(llm_provider="mock", non_interactive=True),
                       memory=MemoryStore(":memory:"))
    return ajan.registry.schemas()


def _adlar(secilen):
    return tuple((s.get("function") or {}).get("name") for s in secilen)


def _konusma(semalar, cumleler, yapiskan: bool):
    """Bir konuşmayı yürütüp her turun araç listesini döndürür."""
    onceki: list[str] = []
    cikti = []
    for c in cumleler:
        s = araclari_sec(semalar, c, 8,
                         onceki_kategoriler=onceki if yapiskan else None)
        cikti.append(_adlar(s))
        if yapiskan:
            bulunan = kategorileri_bul(c)
            if bulunan:
                onceki = bulunan
    return cikti


#: Ara cumleler: hicbir kategori tutmuyor ama konu devam ediyor.
ARA_CUMLELER = ["peki", "evet", "tamam devam et", "anladım", "hı hı"]


# ---------------- yapışkanlık çalışıyor mu ----------------

@pytest.mark.parametrize("ara", ARA_CUMLELER)
def test_a_filler_turn_keeps_the_previous_tools(semalar, ara):
    """"peki" konuyu degistirmiyor; arac listesi de degismemeli."""
    ilk = araclari_sec(semalar, "CPU sıcaklığı kaç derece?", 8)
    kategoriler = kategorileri_bul("CPU sıcaklığı kaç derece?")
    sonra = araclari_sec(semalar, ara, 8, onceki_kategoriler=kategoriler)
    assert _adlar(sonra) == _adlar(ilk)


def test_without_stickiness_a_filler_turn_changes_everything(semalar):
    """Duzeltmeden onceki hâl — regresyon olursa bu test onu yakalar."""
    ilk = araclari_sec(semalar, "CPU sıcaklığı kaç derece?", 8)
    sonra = araclari_sec(semalar, "peki", 8)          # onceki_kategoriler yok
    assert _adlar(sonra) != _adlar(ilk)


def test_a_real_topic_change_still_switches_tools(semalar):
    """Onbellek ugruna yanlis arac gostermek hizli ama ise yaramaz olurdu."""
    kategoriler = kategorileri_bul("CPU sıcaklığı kaç derece?")
    sonra = araclari_sec(semalar, "Chrome'u aç", 8, onceki_kategoriler=kategoriler)
    assert "tarayici_ac" in _adlar(sonra)
    assert "get_cpu_temperature" not in _adlar(sonra)


def test_the_first_turn_needs_no_history(semalar):
    """Konusmanin basinda onceki kategori yok; cakilmamali."""
    assert araclari_sec(semalar, "merhaba", 8, onceki_kategoriler=None)
    assert araclari_sec(semalar, "merhaba", 8, onceki_kategoriler=[])


# ---------------- ölçülen kazanç ----------------

KONUSMA = ["CPU sıcaklığı kaç derece?", "peki", "evet", "tamam devam et",
           "RAM ne durumda?", "anladım", "Chrome'u aç"]


def _iskalama(listeler) -> int:
    """Ardisik iki tur farkliysa onbellek iskalandi demektir."""
    return sum(1 for a, b in zip(listeler, listeler[1:]) if a != b)


def test_stickiness_cuts_cache_misses(semalar):
    """Olculdu: 4/6 -> 1/6. Kalan tek iskalama dogru (konu gercekten degisti)."""
    eski = _iskalama(_konusma(semalar, KONUSMA, yapiskan=False))
    yeni = _iskalama(_konusma(semalar, KONUSMA, yapiskan=True))
    assert eski >= 4, "duzeltmeden onceki hâl degismis; sayilar yeniden olculmeli"
    assert yeni <= 1
    assert yeni < eski


def test_the_only_remaining_miss_is_a_real_topic_change(semalar):
    """Kalan iskalama "Chrome'u ac" turunda olmali — orada degisim DOGRU."""
    listeler = _konusma(semalar, KONUSMA, yapiskan=True)
    degisen = [KONUSMA[i + 1] for i, (a, b) in
               enumerate(zip(listeler, listeler[1:])) if a != b]
    assert degisen == ["Chrome'u aç"]


# ---------------- ajan hatırlıyor mu ----------------

def _ajan():
    return build_agent(Config(llm_provider="mock", non_interactive=True),
                       memory=MemoryStore(":memory:"))


def test_the_agent_remembers_the_last_categories():
    ajan = _ajan()
    ajan.ask("CPU sıcaklığı kaç derece?")
    assert ajan.son_kategoriler == ["sistem"]


def test_a_filler_turn_does_not_erase_the_remembered_categories():
    """Hatirlamanin tek anlami bu: ara cumle konuyu silmemeli."""
    ajan = _ajan()
    ajan.ask("CPU sıcaklığı kaç derece?")
    ajan.ask("peki")
    assert ajan.son_kategoriler == ["sistem"]


def test_a_new_topic_replaces_the_remembered_categories():
    ajan = _ajan()
    ajan.ask("CPU sıcaklığı kaç derece?")
    ajan.ask("Chrome'u aç")
    assert ajan.son_kategoriler == ["uygulama"]


def test_a_fresh_agent_starts_with_no_memory_of_categories():
    assert _ajan().son_kategoriler == []
