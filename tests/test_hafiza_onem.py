"""Uyarlanabilir hafıza: neyin önce hatırlanacağı ve çelişkinin nasıl çözüldüğü.

İki soru var ve ikisi de bağlam sınırından doğuyor. Ölçüldü: basit bir selam
turu 2338 token, ve bunun dörtte üçü sistem istemi. Kırk kayıt biriktiğinde
hepsini göndermek asıl soruyu bastırıyor.

1. **Hangisi önce gider?** Tazelik yanlış cevap: kullanıcının adı, bugünkü
   "yazıcı kağıt sıkıştırıyor" notunun arkasında kalır. Doğru sıra önem.

2. **Çelişince ne olur?** Körü körüne üstüne yazmak, hafızayı zamanla
   tahmine çevirir — model konuşmadan bir şey çıkarır ve kullanıcının
   bizzat söylediğini ezer. Ama kullanıcı fikrini değiştirdiğinde de
   güncelleme olmak zorunda.

Bir de sessiz olan üçüncü mesele: kullanıcının makinesinde aylardır dolu bir
veritabanı var. Şema değişikliği onu YENİDEN KURMAK değil, üstüne eklemek
zorunda. Buradaki göç testleri bunun için.
"""
from __future__ import annotations

import sqlite3
import time

import pytest

from jarvis.memory.onem import Kaynak, Onem, israr_var_mi, onem_belirle
from jarvis.memory.store import MemoryStore


@pytest.fixture
def d():
    return MemoryStore(":memory:")


# ---------------- önem puanlaması ----------------

@pytest.mark.parametrize("key,value,kategori,beklenen", [
    # Kimlik her seyin onunde — kategori 'genel' verilse bile.
    ("gelistirici", "Oğuz benim geliştiricim", "genel", Onem.YUKSEK),
    ("adim", "Oğuz Kayır", "kimlik", Onem.YUKSEK),
    ("meslek", "bilgisayar teknisyeni", "genel", Onem.YUKSEK),
    # "Artik" kalicilik bildiriyor.
    ("editor", "Artık Cursor kullanıyorum", "genel", Onem.YUKSEK),
    # Proje bilgisi lazim olur ama kimlik kadar degil.
    ("proje_yol", "~/jarvis", "proje", Onem.ORTA),
    # Tek seferlik.
    ("vaka", "Bugün gelen yazıcı kağıt sıkıştırıyor", "notlar", Onem.DUSUK),
    ("gecici", "test için geçici kayıt", "genel", Onem.DUSUK),
])
def test_importance_is_scored_from_the_sentence_not_just_the_category(
        key, value, kategori, beklenen):
    assert onem_belirle(key, value, kategori) is beklenen


def test_an_unknown_category_lands_in_the_middle_not_at_the_bottom():
    """Yanlislikla unutmak, yanlislikla hatirlamaktan pahali."""
    assert onem_belirle("x", "tanımsız bir şey", "bilinmeyen") is Onem.ORTA


def test_the_user_insisting_beats_every_guess():
    """Sistemin tahmini, kullanicinin acik istegini gecemez."""
    assert onem_belirle("x", "sıradan not", "notlar") is Onem.DUSUK
    assert onem_belirle("x", "sıradan not", "notlar", israr=True) is Onem.YUKSEK


@pytest.mark.parametrize("cumle", [
    "Bunu hatırla: parolayı değiştirdim",
    "Şunu unutma, sabah toplantı var",
    "Bundan sonra hep Türkçe yaz",
    "Aklında tut",
])
def test_insistence_is_recognised_in_turkish(cumle):
    assert israr_var_mi(cumle) is True


def test_an_ordinary_sentence_is_not_read_as_insistence():
    assert israr_var_mi("Bugün hava güzel") is False


# ---------------- çelişki ----------------

def test_an_inference_cannot_overwrite_what_the_user_said():
    """Hafizanin zamanla tahmine donusmesini engelleyen kural."""
    d = MemoryStore(":memory:")
    d.remember("editor", "VS Code", "tercih", source=Kaynak.KULLANICI.value)
    d.remember("editor", "Vim", "tercih", source=Kaynak.CIKARIM.value)
    assert d.recall("editor", kullanim_say=False)[0].value == "VS Code"


def test_the_user_changing_their_mind_does_update():
    """"Artik Cursor kullaniyorum" guncelleme olmali; kural donmus olmamali."""
    d = MemoryStore(":memory:")
    d.remember("editor", "VS Code", "tercih", source=Kaynak.KULLANICI.value)
    d.remember("editor", "Cursor", "tercih", source=Kaynak.KULLANICI.value)
    assert d.recall("editor", kullanim_say=False)[0].value == "Cursor"


def test_the_replaced_value_is_kept_not_deleted():
    """Eski deger gecerliligini kaybetti ama yanlis degildi.

    "Ben sana bunu soylemistim" dendiginde bakilacak bir yer olmali.
    """
    d = MemoryStore(":memory:")
    d.remember("editor", "VS Code", "tercih")
    d.remember("editor", "Cursor", "tercih")
    gecmis = d.gecmis("editor")
    assert len(gecmis) == 1
    assert gecmis[0]["old_value"] == "VS Code"
    assert gecmis[0]["new_value"] == "Cursor"


def test_a_rejected_write_is_recorded_too():
    """"Neden guncellenmedi" sorusunun cevabi bir yerde olmali."""
    d = MemoryStore(":memory:")
    d.remember("editor", "VS Code", "tercih", source=Kaynak.KULLANICI.value)
    d.remember("editor", "Vim", "tercih", source=Kaynak.CIKARIM.value)
    gecmis = d.gecmis("editor")
    assert len(gecmis) == 1
    assert "reddedildi" in gecmis[0]["source"]


def test_writing_the_same_value_again_is_not_a_conflict():
    d = MemoryStore(":memory:")
    d.remember("adim", "Oğuz", "kimlik")
    d.remember("adim", "Oğuz", "kimlik")
    assert d.gecmis("adim") == []


def test_importance_only_rises_never_falls():
    """Kimlik diye isaretlenen bir kayit, gevsek bir yazmayla dibe dusmemeli.

    Ayni ders izin katmaninda da alinmisti: yukselen taban, dusen taban
    degil.
    """
    d = MemoryStore(":memory:")
    d.remember("adim", "Oğuz Kayır", "kimlik")
    assert d.recall("adim", kullanim_say=False)[0].onem is Onem.YUKSEK
    d.remember("adim", "Oğuz K.", "notlar")
    assert d.recall("adim", kullanim_say=False)[0].onem is Onem.YUKSEK


# ---------------- sıralama ----------------

def test_context_is_ordered_by_importance_not_by_recency():
    """Tazeliğe göre sıralamak kullanıcının adını arıza notunun arkasına atıyordu."""
    d = MemoryStore(":memory:")
    d.remember("adim", "Oğuz Kayır", "kimlik")
    d.remember("proje", "jarvis ~/jarvis", "proje")
    d.remember("vaka", "bugün gelen yazıcı arızalı", "notlar")  # en taze
    sirali = [f.key for f in d.all_facts()]
    assert sirali == ["adim", "proje", "vaka"]


def test_pushing_to_context_is_not_counted_as_use():
    """"Baglama kondu" ile "ise yaradi" ayni sey degil.

    all_facts her turda kosulsuz cagriliyor; sayaci burada artirmak hic
    kullanilmayan bir kaydi cok kullanilmis gosterirdi ve budama olcumu
    anlamsizlasirdi.
    """
    d = MemoryStore(":memory:")
    d.remember("x", "bir şey", "genel")
    d.all_facts()
    d.all_facts()
    assert d.recall("x", kullanim_say=False)[0].usage_count == 0


def test_an_actual_lookup_is_counted():
    d = MemoryStore(":memory:")
    d.remember("x", "bir şey", "genel")
    d.recall("x")
    kayit = d.recall("x", kullanim_say=False)[0]
    assert kayit.usage_count == 1
    assert kayit.last_used > 0


# ---------------- budama ----------------

def test_pruning_only_ever_proposes_never_deletes():
    """Hafizadan bir sey dusurmek geri alinamaz; karar sahibinin."""
    d = MemoryStore(":memory:")
    d.remember("gecici", "test için geçici kayıt", "genel")
    d._conn.execute("UPDATE facts SET updated_ts = ?", (time.time() - 200 * 86400,))
    d._conn.commit()
    adaylar = d.budama_adaylari()
    assert [f.key for f in adaylar] == ["gecici"]
    # Onerildi ama SILINMEDI.
    assert len(d.all_facts()) == 1


def test_a_used_record_is_never_a_pruning_candidate():
    d = MemoryStore(":memory:")
    d.remember("gecici", "test için geçici kayıt", "genel")
    d.recall("gecici")                      # kullanildi
    d._conn.execute("UPDATE facts SET updated_ts = ?", (time.time() - 200 * 86400,))
    d._conn.commit()
    assert d.budama_adaylari() == []


def test_an_important_record_is_never_a_pruning_candidate():
    d = MemoryStore(":memory:")
    d.remember("adim", "Oğuz Kayır", "kimlik")
    d._conn.execute("UPDATE facts SET updated_ts = ?", (time.time() - 900 * 86400,))
    d._conn.commit()
    assert d.budama_adaylari() == []


# ---------------- göç: mevcut veritabanı bozulmamalı ----------------
# Kullanicinin makinesinde aylardir dolu bir veritabani var. CREATE TABLE
# IF NOT EXISTS var olan bir tabloya sutun EKLEMEZ — sessizce hicbir sey
# yapar. Tabloyu silip yeniden yaratmak en kolay ve en yikici secenekti.

ESKI_SEMA = """
CREATE TABLE facts (
    key TEXT PRIMARY KEY, value TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'genel',
    created_ts REAL NOT NULL, updated_ts REAL NOT NULL);
"""


def _eski_veritabani(yol) -> None:
    c = sqlite3.connect(str(yol))
    c.executescript(ESKI_SEMA)
    now = time.time()
    c.execute("INSERT INTO facts VALUES (?,?,?,?,?)",
              ("adim", "Oğuz Kayır", "kullanici", now, now))
    c.execute("INSERT INTO facts VALUES (?,?,?,?,?)",
              ("yazici", "HP LaserJet", "notlar", now, now))
    c.commit()
    c.close()


def test_an_existing_database_keeps_every_record(tmp_path):
    yol = tmp_path / "eski.sqlite3"
    _eski_veritabani(yol)
    d = MemoryStore(yol)
    assert {f.key for f in d.all_facts()} == {"adim", "yazici"}
    assert d.recall("adim", kullanim_say=False)[0].value == "Oğuz Kayır"


def test_migrated_records_land_in_the_middle_of_the_ordering(tmp_path):
    """Hepsini DUSUK saymak bugune kadarki her seyi dibe atardi; YUKSEK
    saymak yeni puanlamayi anlamsiz kilardi."""
    yol = tmp_path / "eski.sqlite3"
    _eski_veritabani(yol)
    d = MemoryStore(yol)
    for f in d.all_facts():
        assert f.onem is Onem.ORTA
        assert f.confidence == 1.0
        assert f.usage_count == 0


def test_running_the_migration_twice_is_safe(tmp_path):
    yol = tmp_path / "eski.sqlite3"
    _eski_veritabani(yol)
    MemoryStore(yol)
    d = MemoryStore(yol)          # ikinci acilis
    assert len(d.all_facts()) == 2


def test_a_migrated_database_accepts_the_new_fields(tmp_path):
    """Goc yalnizca acmakla bitmiyor; yazma da calismali."""
    yol = tmp_path / "eski.sqlite3"
    _eski_veritabani(yol)
    d = MemoryStore(yol)
    f = d.remember("gelistirici", "Oğuz benim geliştiricim", "kimlik")
    assert f.onem is Onem.YUKSEK
    assert f.source == Kaynak.KULLANICI.value


# ---------------- araç katmanı ----------------

def test_the_tool_does_not_claim_it_saved_when_it_did_not():
    """Modele "kaydedildi" demek, kullaniciya "kaydettim" dedirtir."""
    from jarvis.tools.base import ToolRegistry
    from jarvis.tools.memory_tools import register_memory_tools

    d = MemoryStore(":memory:")
    d.remember("editor", "VS Code", "tercih", source=Kaynak.KULLANICI.value)
    kayit = register_memory_tools(ToolRegistry(), d)

    sonuc = kayit.get("remember_fact").func(
        key="editor", value="Vim", category="tercih", cikarim=True)
    assert sonuc["kaydedildi"] is False
    assert "VS Code" in sonuc["not"]


def test_the_tool_reports_what_the_value_used_to_be():
    from jarvis.tools.base import ToolRegistry
    from jarvis.tools.memory_tools import register_memory_tools

    d = MemoryStore(":memory:")
    d.remember("editor", "VS Code", "tercih")
    kayit = register_memory_tools(ToolRegistry(), d)
    sonuc = kayit.get("remember_fact").func(
        key="editor", value="Cursor", category="tercih")
    assert sonuc["kaydedildi"] is True
    assert sonuc["onceki_deger"] == "VS Code"


def test_the_tool_tells_the_model_not_to_fake_insistence():
    from jarvis.tools.base import ToolRegistry
    from jarvis.tools.memory_tools import register_memory_tools

    kayit = register_memory_tools(ToolRegistry(), MemoryStore(":memory:"))
    sema = kayit.get("remember_fact").to_schema()
    metin = str(sema)
    assert "Kendi kararınla true yapma" in metin
    assert "üstüne" in metin, "çıkarım kuralı modele anlatılmalı"
