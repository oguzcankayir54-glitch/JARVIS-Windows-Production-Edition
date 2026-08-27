"""Kimlik tohumu: J.A.R.V.I.S. neden sahibini tanımıyordu.

Kimlik hep veritabanındaydı ve oraya girmenin tek yolu ``jarvis-tanit --kur``
komutunu çalıştırmaktı. O komut kurulum adımlarının arasında kayboldu ve
"beni hâlâ tanımıyor" üç kez geri geldi. Bir adımın hatırlanmasını beklemek
tasarım değil.

Buradaki testler iki şeyi birden koruyor: boş bir kimlik dosyadan dolmalı, ve
dolu bir kimliğin ÜSTÜNE YAZILMAMALI — ikincisi daha önemli, çünkü sessizce
veri kaybettiren taraf o.
"""
import json
from pathlib import Path

import pytest

from jarvis.core.kimlik_tohumu import (
    dosyadan_oku,
    kimligi_tohumla,
    tohum_yollari,
    tohumu_bul,
)
from jarvis.core.owner import Owner
from jarvis.memory.store import MemoryStore


@pytest.fixture
def yalniz_kullanici(monkeypatch, tmp_path):
    """Aramayı YALNIZCA kullanıcı klasörüne indir.

    Normalde depodaki dosya bir yedek: kullanıcının kendi kopyası yoksa ya da
    bozuksa oradan doldurulur — istenen davranış bu. Ama "dosya yok" ve
    "dosya bozuk" hâllerini sınamak için o yedeğin kaldırılması gerekiyor,
    yoksa her test depodaki kimliği bulup geçiyor.
    """
    monkeypatch.setattr("jarvis.core.kimlik_tohumu.tohum_yollari",
                        lambda data_dir=tmp_path: [Path(data_dir) / "kimlik.json"])


def _tohum_yaz(klasor, **alanlar):
    klasor.mkdir(parents=True, exist_ok=True)
    veri = {"name": "Deniz Yılmaz", "address_forms": ["Deniz", "Efendim"],
            "role": "tasarımcısı", "profession": "teknisyen"}
    veri.update(alanlar)
    (klasor / "kimlik.json").write_text(json.dumps(veri, ensure_ascii=False),
                                        encoding="utf-8")
    return klasor / "kimlik.json"


# ---------------- doldurma ----------------

def test_an_empty_identity_is_filled_from_the_file(tmp_path):
    _tohum_yaz(tmp_path)
    store = MemoryStore(":memory:")
    yazilan = kimligi_tohumla(store, tmp_path)
    assert yazilan is not None
    assert store.get_owner().name == "Deniz Yılmaz"


def test_the_seeded_identity_reaches_the_prompt(tmp_path):
    _tohum_yaz(tmp_path)
    store = MemoryStore(":memory:")
    kimligi_tohumla(store, tmp_path)
    metin = store.get_owner().to_prompt()
    assert "Deniz Yılmaz" in metin
    assert "SENİ KİM YAPTI" in metin, "tasarımcı sorusu cevaplanabilmeli"


# ---------------- üstüne yazmama ----------------

def test_an_existing_identity_is_never_overwritten(tmp_path):
    """Elle girilen bilgiyi her açılışta dosyadaki değere döndürmek,
    kullanıcının yaptığı işi sessizce silmek olurdu."""
    _tohum_yaz(tmp_path)
    store = MemoryStore(":memory:")
    store.set_owner(Owner(name="Başka Biri", role="sahibi"))
    assert kimligi_tohumla(store, tmp_path) is None
    assert store.get_owner().name == "Başka Biri"


# ---------------- bozuk girdiler ----------------

def test_a_missing_file_is_not_an_error(tmp_path, yalniz_kullanici):
    store = MemoryStore(":memory:")
    assert kimligi_tohumla(store, tmp_path / "yok") is None


@pytest.mark.parametrize("icerik", [
    "{bu geçerli json değil",
    "[]",
    '"düz metin"',
    "{}",
    '{"name": "   "}',
])
def test_a_broken_file_does_not_stop_start_up(tmp_path, icerik, yalniz_kullanici):
    """Kimlik yüzünden J.A.R.V.I.S.'in hiç açılmaması kabul edilemez."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "kimlik.json").write_text(icerik, encoding="utf-8")
    store = MemoryStore(":memory:")
    assert kimligi_tohumla(store, tmp_path) is None
    assert store.get_owner().configured is False


def test_a_single_address_form_given_as_text_is_accepted(tmp_path):
    _tohum_yaz(tmp_path, address_forms="Efendim")
    sahip = dosyadan_oku(tmp_path / "kimlik.json")
    assert sahip.address_forms == ["Efendim"]


def test_a_notepad_bom_does_not_hide_the_name(tmp_path):
    """Bu tuzağa .env ile bir kez düşüldü: BOM ilk satırı sessizce yutuyordu."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "kimlik.json").write_text(
        json.dumps({"name": "Deniz Yılmaz"}), encoding="utf-8-sig")
    sahip = tohumu_bul(tmp_path)
    assert sahip is not None and sahip.name == "Deniz Yılmaz"


# ---------------- arama sırası ----------------

def test_the_users_own_copy_wins_over_the_repository_one(tmp_path):
    """Kendi makinesindeki bilgi, depoya yazılmış olandan daha doğrudur."""
    yollar = tohum_yollari(tmp_path)
    assert yollar[0] == tmp_path / "kimlik.json"
    assert yollar[1].name == "kimlik.json"


def test_the_repository_ships_a_usable_seed():
    """Depodaki dosya gerçekten okunabilir olmalı — asıl amacı bu."""
    from pathlib import Path
    yol = Path(__file__).resolve().parents[1] / "kimlik.json"
    sahip = dosyadan_oku(yol)
    assert sahip is not None and sahip.configured
    assert sahip.role, "tasarımcı sorusu için rol gerekiyor"


# ---------------- açılışa bağlanması ----------------

def test_starting_up_seeds_the_identity(tmp_path):
    """Asıl kural bu: kimse hiçbir komut çalıştırmadan tanınmalı."""
    from jarvis.bootstrap import build_agent
    from jarvis.config import Config
    _tohum_yaz(tmp_path)
    store = MemoryStore(":memory:")
    ajan = build_agent(Config(llm_provider="mock", non_interactive=True,
                              data_dir=tmp_path), memory=store)
    assert ajan.owner.name == "Deniz Yılmaz"
    assert "Deniz Yılmaz" in ajan.history[0].content


def test_a_broken_user_file_falls_back_to_the_one_in_the_repository(tmp_path):
    """Kullanıcının dosyası bozuksa kimliksiz kalmak yerine yedeği kullan."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "kimlik.json").write_text("{bozuk", encoding="utf-8")
    sahip = tohumu_bul(tmp_path)
    assert sahip is not None and sahip.configured
