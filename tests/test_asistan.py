"""Asistanın kimliği: adı, sesi, rengi, hafızası.

Bir dönem burada iki kimlik vardı — ``ASISTAN=friday`` ikinci bir asistanı
açıyordu — ve bu dosyanın çoğu "ikisi birbirine karışmıyor mu" sorusunu
koruyordu. İkinci asistan kaldırıldı: kullanımda karışıklık yarattığı
söylendi (iki simge, iki panel, iki port, iki hafıza, her ayarın iki öneki)
ve kazandırdığı tek şey aynı koddan ikinci bir isimdi.

Geriye kalan testler kimliğin **tek yerde** durduğunu koruyor. Bunun sebebi
somut: ad, okunuş, renk ve ses koda dağıldığında birini değiştirmek
diğerlerini tutarsız bırakıyor, ve tutarsızlık hata vermeden görünüyor —
panelde bir ad, seslendirmede başka bir ad.

Sondaki bölüm ise ikinci asistanın gerçekten gittiğini denetliyor: yarısı
silinmiş bir özellik, hiç silinmemiş olmasından kötü.
"""
import pytest

from jarvis.config import Config
from jarvis.core.asistan import JARVIS, ONEK, asistan_bul

KOK = __import__("pathlib").Path(__file__).resolve().parents[1]


# ---------------- kimlik ----------------

def test_the_assistant_is_completely_described():
    """Eksik bir alan, sessizce boş bir panel başlığı demek."""
    for alan in ("kod", "ad", "sade_ad", "okunus", "ses", "veri_klasoru",
                 "vurgu", "tanim"):
        assert getattr(JARVIS, alan), f"{alan} boş"
    assert JARVIS.seslenisler


def test_there_is_exactly_one_assistant_and_no_choice_to_make():
    assert asistan_bul() is JARVIS
    assert ONEK == "JARVIS_"


def test_the_environment_cannot_switch_the_identity(monkeypatch):
    """Eski ``ASISTAN=friday`` ayarı .env'de kalmış olabilir; artık etkisiz.

    Sessizce yok saymak doğru olan: hata vermek, eski bir satır yüzünden
    programın hiç açılmaması demek olurdu.
    """
    monkeypatch.setenv("ASISTAN", "friday")
    assert asistan_bul() is JARVIS


# ---------------- ayarlar ----------------

def test_the_data_directory_defaults_to_the_identity(monkeypatch):
    monkeypatch.delenv("JARVIS_DATA_DIR", raising=False)
    assert Config().data_dir.name == ".jarvis"


def test_an_explicit_data_directory_still_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_DATA_DIR", str(tmp_path))
    assert Config().data_dir == tmp_path


def test_the_voice_defaults_to_the_identity(monkeypatch):
    monkeypatch.delenv("JARVIS_EDGE_VOICE", raising=False)
    assert Config().edge_voice == JARVIS.ses


def test_the_voice_can_be_overridden(monkeypatch):
    monkeypatch.setenv("JARVIS_EDGE_VOICE", "tr-TR-EmelNeural")
    assert Config().edge_voice == "tr-TR-EmelNeural"


def test_a_leftover_friday_prefix_changes_nothing(monkeypatch):
    """Eski kurulumdaki FRIDAY_ satırları artık okunmuyor."""
    monkeypatch.setenv("FRIDAY_TTS_PROVIDER", "piper")
    monkeypatch.delenv("JARVIS_TTS_PROVIDER", raising=False)
    assert Config().tts_provider == "elevenlabs"


# ---------------- görünen ad ile okunuş ----------------
# Ikisi tek alanda tutuluyordu ve okunus ekrana sizdi: panelde adin yanlis
# yazilisi gorundu. J.A.R.V.I.S.'te ikisi ayni oldugu icin hata gorunmuyor —
# alanlarin ayri kalmasinin sebebi tam olarak bu.

def test_the_display_name_and_the_pronunciation_are_separate_fields():
    alanlar = {a.name for a in __import__("dataclasses").fields(JARVIS)}
    assert {"sade_ad", "okunus"} <= alanlar


def test_the_spelled_name_is_spoken_not_letter_by_letter():
    from jarvis.voice.tts import normalize_for_speech
    assert normalize_for_speech("J.A.R.V.I.S. hazır.") == "Jarvis hazır."


def test_an_ordinary_word_is_not_mistaken_for_the_name():
    from jarvis.voice.tts import normalize_for_speech
    for cumle in ("Cuma günü geliyorum.", "Bugün cumartesi."):
        assert normalize_for_speech(cumle) == cumle


# ---------------- kişilik ----------------

def _istem() -> str:
    from jarvis.core.owner import Owner
    from jarvis.core.persona import build_system_prompt
    sahip = Owner(name="Deniz Yılmaz", address_forms=["Deniz", "Efendim"],
                  role="tasarımcısı ve geliştiricisi")
    return build_system_prompt(sahip, "")


def test_the_prompt_names_the_assistant():
    assert _istem().startswith(f"Sen {JARVIS.ad}'sin")


def test_who_made_you_still_answers_with_the_owner():
    metin = _istem()
    assert "Deniz Yılmaz" in metin
    assert JARVIS.ad in metin


def test_the_summons_uses_the_written_name():
    assert '"Jarvis"' in _istem()


def test_the_prompt_does_not_mention_the_removed_assistant():
    assert "F.R.I.D.A.Y." not in _istem()


# ---------------- ajan ve panel ----------------

def _ajan():
    from jarvis.bootstrap import build_agent
    from jarvis.memory.store import MemoryStore
    return build_agent(Config(llm_provider="mock", non_interactive=True),
                       memory=MemoryStore(":memory:"))


def test_the_agent_carries_its_assistant():
    assert _ajan().asistan is JARVIS


def test_the_panel_reports_the_assistant():
    from jarvis.web.server import PanelServer
    meta = PanelServer(_ajan(), port=0)._meta()
    assert meta["asistan"] == JARVIS.kod
    assert meta["asistan_ad"] == JARVIS.ad
    assert meta["asistan_sade"] == JARVIS.sade_ad
    assert meta["asistan_vurgu"] == JARVIS.vurgu


def test_the_served_page_carries_the_name_before_any_script_runs():
    """Açılış girişi harfleri sayfa yüklenir yüklenmez çiziliyor; adı SSE
    ile beklemek girişte bir an boş başlık demekti."""
    from jarvis.web.server import PanelServer
    betik = PanelServer(_ajan(), port=0)._kimlik_betigi()
    assert JARVIS.ad in betik
    assert JARVIS.vurgu in betik


# ---------------- ikinci asistan gercekten gitti mi ----------------
# Yarim kalmis bir kaldirma, hic kaldirmamaktan kotu: calismayan bir
# masaustu simgesi, ice aktarilamayan bir giris noktasi, ya da hicbir sey
# yapmayan bir kurulum secenegi geride kalirdi.

#: Depoda hicbir yerde durmamasi gereken dosyalar.
GITMESI_GEREKENLER = (
    "jarvis/core/friday_cli.py",
    "windows/Kur-Friday.cmd",
    "tanitim/anlatim_friday.py",
    "tanitim/video_cek_friday.py",
    "tanitim/ikili.html",
)


@pytest.mark.parametrize("yol", GITMESI_GEREKENLER)
def test_the_second_assistants_files_are_gone(yol):
    assert not (KOK / yol).exists(), f"{yol} hâlâ duruyor"


def test_no_entry_point_points_at_the_removed_module():
    """``pip install`` calismayan bir komut kurmamali."""
    import tomllib
    proje = tomllib.loads((KOK / "pyproject.toml").read_text(encoding="utf-8"))
    for ad, hedef in proje["project"]["scripts"].items():
        assert not ad.startswith("friday"), f"{ad} hâlâ tanımlı"
        assert "friday" not in hedef


def test_the_installer_no_longer_offers_a_second_assistant():
    ps1 = (KOK / "windows/src/kur-windows.ps1").read_text(encoding="utf-8")
    assert "$Friday" not in ps1, "kurulumda -Friday secenegi kalmis"
    cmd = (KOK / "windows/Kur.cmd").read_text(encoding="utf-8")
    assert "/friday" not in cmd.lower()


def test_the_installer_cleans_up_what_it_left_on_earlier_machines():
    """ONCEDEN kuranlarda masaustunde calismayan bir simge kaliyor.

    Kullanicidan elle silmesini beklemek, kaldirmanin yarim kalmasi olurdu.
    """
    ps1 = (KOK / "windows/src/kur-windows.ps1").read_text(encoding="utf-8")
    assert "friday.ini" in ps1
    assert "F.R.I.D.A.Y..lnk" in ps1
    assert "Remove-Item" in ps1


def test_the_launcher_no_longer_takes_an_assistant_argument():
    kaynak = (KOK / "windows/src/jarvis-launcher.c").read_text(encoding="utf-8")
    assert "g_asistan" not in kaynak
    assert 'L"friday"' not in kaynak
    # Ortam degiskenini KOYMAMALI: eski bir .env'de ASISTAN=friday kalmis
    # olabilir ve baslatici onu tazelemis gibi gorunurdu.
    assert 'SetEnvironmentVariableW(L"ASISTAN"' not in kaynak
