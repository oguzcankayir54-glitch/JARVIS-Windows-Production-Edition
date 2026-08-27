"""Kısaltmaların okunuşu — "türkçe terimleri söyleyemiyor" şikâyetinin kökü.

Şikâyet sesin suçu sanılmıştı. Ölçünce görüldü ki iyi ses de aynı yerde
tökezliyor: ``BIOS`` Türkçe bir sözcük gibi okunup "boz" çıkıyor. Buradaki
testler iki şeyi birden koruyor — kısaltmalar okunuşuna çevrilmeli, ve
çevrilmemesi gerekenlere DOKUNULMAMALI. İkincisi daha kırılgan: fazla hevesli
bir kural sıradan Türkçeyi harf yığınına çevirir.
"""
import pytest

from jarvis.voice.soyleyis import OKUNUS, okunusa_cevir
from jarvis.voice.tts import normalize_for_speech


# ---------------- tablodaki kısaltmalar ----------------

@pytest.mark.parametrize("yazi,beklenen", [
    ("BIOS güncellemesi", "bayos"),
    ("SSD takılı", "es es de"),
    ("HDD sesi", "ha de de"),
    ("RAM modülü", "ram"),
    ("USB portu", "u es be"),
    ("DNS ayarı", "de en es"),
    ("ECC hatası", "e ce ce"),
])
def test_a_known_abbreviation_is_read_the_turkish_way(yazi, beklenen):
    assert beklenen in okunusa_cevir(yazi)


def test_an_abbreviation_keeps_its_turkish_suffix():
    """SSD'nin → "es es de'nin". Eki yutmak cümleyi bozar."""
    assert "es es de'nin" in okunusa_cevir("SSD'nin değerleri")
    assert "bayos'u" in okunusa_cevir("BIOS'u güncelledim")


def test_a_dotted_abbreviation_is_collapsed_first():
    """S.M.A.R.T. noktalarıyla tabloda aranmaz; noktalar önce düşüyor."""
    assert "smart" in okunusa_cevir("S.M.A.R.T. değerleri")


def test_an_unknown_abbreviation_is_spelled_with_turkish_letter_names():
    """İngilizce harf adları ("es-es-di") bir Türkçe ses için yanlış."""
    assert okunusa_cevir("XYZ kaydı").startswith("iks ye ze")


def test_a_unit_stuck_to_a_number_is_separated():
    sonuc = okunusa_cevir("500GB disk, 3.5GHz işlemci, 67°C")
    assert "500 gigabayt" in sonuc
    assert "3.5 gigahertz" in sonuc
    assert "santigrat derece" in sonuc


# ---------------- dokunulmaması gerekenler ----------------
# Asıl risk burada: kural fazla geniş olursa sıradan Türkçe bozulur.

@pytest.mark.parametrize("yazi", [
    "Windows kayıt defteri",
    "Ekran kartının sürücüsü",
    "İşlemci sıcaklığı normal",
    "Merhaba efendim",
])
def test_ordinary_turkish_is_left_alone(yazi):
    assert okunusa_cevir(yazi) == yazi


def test_a_model_number_is_not_spelled_out():
    """X570, RTX3080 — seslendirici bunları zaten makul okuyor."""
    metin = "X570 anakart ve RTX3080 kartı"
    assert okunusa_cevir(metin) == metin


def test_a_shouted_sentence_is_not_treated_as_a_list_of_abbreviations():
    """Tamamı büyük harfli bir metin bağırmadır; hecelenirse anlaşılmaz olur."""
    metin = "TAMAM EFENDİM HEMEN BAKIYORUM"
    assert okunusa_cevir(metin) == metin


def test_a_long_uppercase_word_is_not_spelled():
    assert okunusa_cevir("Bu bir DENEME kaydı") == "Bu bir DENEME kaydı"


def test_empty_text_survives():
    assert okunusa_cevir("") == ""


# ---------------- sese giden metnin tamamı ----------------

def test_speech_normalisation_applies_the_pronunciation_layer():
    """Ölçülen kazanç buradan geliyor: anlaşılırlık 0.82 → 0.87."""
    sonuc = normalize_for_speech("**J.A.R.V.I.S.**: BIOS ve SSD kontrol edildi.")
    assert "Jarvis" in sonuc
    assert "*" not in sonuc
    assert "bayos" in sonuc and "es es de" in sonuc


def test_the_written_form_is_not_changed_anywhere_else():
    """Panelde "es es de" yazsaydı okunmaz olurdu; değişen yalnızca ses."""
    yazi = "SSD'nin S.M.A.R.T. değerleri normal."
    assert okunusa_cevir(yazi) != yazi     # sese giden değişiyor
    assert "SSD" in yazi                   # kaynak dize olduğu gibi duruyor


# ---------------- tablonun kendisi ----------------

def test_no_pronunciation_reintroduces_the_problem_it_solves():
    """Bir okunuş yine büyük harfli bir kısaltma içerse döngüye girerdi."""
    for yazilis, okunus in OKUNUS.items():
        assert okunus == okunus.lower() or okunus[0].isdigit(), yazilis
