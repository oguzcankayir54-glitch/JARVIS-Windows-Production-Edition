"""Uygulama açma: adın nasıl bulunduğu, ve neyin asla açılmadığı.

Hiçbir test gerçekten bir program başlatmıyor. Denenen şey eşleştirme ve
sınır: "YouTube aç" doğru yere gitmeli, ve elle verilmiş bir yol hiçbir
şekilde çalışmamalı.
"""
import json

import pytest

from jarvis.llm.base import Message
from jarvis.apps.katalog import (
    URI,
    VARSAYILAN,
    WEB,
    WINDOWS,
    Uygulama,
    benzerler,
    bul,
    katalog,
    kullanici_katalogu,
)


# ---------------- ad eşleştirme ----------------
# "komutları bu kadar zor öğrenmesin" istendi: konuşan biri harf harf
# doğru yazmak zorunda kalmamalı.

@pytest.mark.parametrize("istek,beklenen", [
    ("youtube", "YouTube"),
    ("YouTube", "YouTube"),
    ("YOUTUBE AÇ", "YouTube"),
    ("yutub", "YouTube"),                      # duyduğu gibi yazmış
    ("hesap makinesi", "Hesap Makinesi"),
    ("hesap makinası", "Hesap Makinesi"),      # yaygın söyleyiş
    ("HESAP MAKİNESİ", "Hesap Makinesi"),
    ("not defteri", "Not Defteri"),
    ("notepad", "Not Defteri"),
    ("gorev yoneticisi", "Görev Yöneticisi"),  # şapkasız
    ("ayarları", "Ayarlar"),                   # ek almış
    ("ceviri", "Google Çeviri"),
    ("wifi", "Ağ Ayarları"),
])
def test_a_spoken_name_finds_its_entry(istek, beklenen):
    uygulama = bul(istek)
    assert uygulama is not None, f"{istek!r} bulunamadı"
    assert uygulama.ad == beklenen


def test_turkish_folding_is_used_for_matching():
    """IŞIK/ışık sorunu burada da geçerli: I ve i tek başına eşleşmiyor."""
    assert bul("İNSTAGRAM") is not None
    assert bul("instagram") is not None


def test_an_empty_request_matches_nothing():
    assert bul("") is None
    assert bul("   ") is None


def test_an_unknown_name_is_not_guessed():
    assert bul("zzqqxx-boyle-bir-sey-yok") is None


# ---------------- güvenlik: katalog bir beyaz liste ----------------
# Terminal aracının kendi allowlist'i ve risk sınıflandırıcısı var. "aç"
# eline verilen her yolu çalıştırabilseydi o allowlist nazikçe rica ederek
# atlanabilirdi — ve rica bir WEB SAYFASINDAN gelebilir.

@pytest.mark.parametrize("kotu", [
    "C:\\Windows\\System32\\cmd.exe",
    "/bin/bash",
    "powershell -Command Remove-Item",
    "../../../etc/passwd",
    "rm -rf /",
    "notepad.exe & calc.exe",
])
def test_a_raw_path_or_command_never_resolves(kotu):
    uygulama = bul(kotu)
    # Bir sey donduyse bile KATALOGDAN gelmis olmali, verilen dize degil.
    assert uygulama is None or uygulama in katalog()


def test_every_default_entry_has_a_known_kind():
    for uygulama in VARSAYILAN:
        assert uygulama.tur in (WEB, WINDOWS, URI), uygulama.ad
        assert uygulama.hedef


def test_web_entries_are_https():
    for uygulama in VARSAYILAN:
        if uygulama.tur == WEB:
            assert uygulama.hedef.startswith("https://"), uygulama.ad


# ---------------- öneriler ----------------

def test_a_miss_comes_back_with_suggestions():
    """Boş liste "yardım edemem" demektir; birkaç örnek en azından yön verir."""
    assert benzerler("photoshop") != []


def test_suggestions_prefer_a_shared_word():
    oneriler = benzerler("google drive")
    assert any("Google" in ad for ad in oneriler)


# ---------------- kullanıcı kataloğu ----------------
# "Her uygulamayı açsın" isteği ile "eline verilen her şeyi çalıştırsın"
# arasındaki fark bu: eksik olanı klavye başındaki kişi ekliyor.

def test_the_owner_can_add_an_entry(tmp_path):
    kullanici_katalogu(tmp_path).parent.mkdir(parents=True, exist_ok=True)
    kullanici_katalogu(tmp_path).write_text(json.dumps([
        {"ad": "Photoshop", "tur": "windows", "hedef": "photoshop.exe",
         "takma": ["fotoşop", "ps"]}
    ]), encoding="utf-8")
    uygulama = bul("fotoşop", tmp_path)
    assert uygulama is not None and uygulama.ad == "Photoshop"


def test_an_owner_entry_wins_over_a_builtin_of_the_same_name(tmp_path):
    """Onun makinesi, o kelimenin onun için anlamı."""
    kullanici_katalogu(tmp_path).parent.mkdir(parents=True, exist_ok=True)
    kullanici_katalogu(tmp_path).write_text(json.dumps([
        {"ad": "YouTube", "tur": "windows", "hedef": "youtube-app.exe"}
    ]), encoding="utf-8")
    assert bul("youtube", tmp_path).hedef == "youtube-app.exe"


def test_a_broken_user_file_does_not_cost_the_builtins(tmp_path):
    kullanici_katalogu(tmp_path).parent.mkdir(parents=True, exist_ok=True)
    kullanici_katalogu(tmp_path).write_text("{bu geçerli json değil", encoding="utf-8")
    assert bul("youtube", tmp_path) is not None


@pytest.mark.parametrize("girdi", [
    {"ad": "Eksik"},                                  # hedef yok
    {"hedef": "x.exe"},                               # ad yok
    {"ad": "A", "hedef": "x", "tur": "bilinmeyen"},   # tür geçersiz
    "düz metin",                                      # sözlük bile değil
])
def test_a_malformed_entry_is_skipped(tmp_path, girdi):
    kullanici_katalogu(tmp_path).parent.mkdir(parents=True, exist_ok=True)
    kullanici_katalogu(tmp_path).write_text(json.dumps([girdi]), encoding="utf-8")
    assert len(katalog(tmp_path)) == len(VARSAYILAN)


# ---------------- araç katmanı ----------------

def _kayit(tmp_path):
    from jarvis.tools.app_tools import register_app_tools
    from jarvis.tools.base import ToolRegistry
    return register_app_tools(ToolRegistry(), data_dir=str(tmp_path))


def test_opening_a_program_is_medium_risk(tmp_path):
    """Görünür ve geri alınabilir, ama yine de bir program başlatıyor."""
    from jarvis.security.permissions import RiskLevel
    kayit = _kayit(tmp_path)
    assert kayit.get("uygulama_ac").risk is RiskLevel.MEDIUM
    assert kayit.get("uygulama_listesi").risk is RiskLevel.LOW


def test_an_unknown_app_returns_suggestions_not_a_guess(tmp_path):
    sonuc = _kayit(tmp_path).get("uygulama_ac").run(ad="zzqqxx")
    assert sonuc.ok
    assert "hata" in sonuc.data
    assert sonuc.data["oneriler"]
    assert "Uydurma" in sonuc.data["not"]


def test_an_empty_name_is_refused(tmp_path):
    sonuc = _kayit(tmp_path).get("uygulama_ac").run(ad="  ")
    assert "hata" in sonuc.data


def test_a_web_app_is_opened_through_the_browser(tmp_path, monkeypatch):
    import jarvis.apps.ac as modul
    acilanlar = []
    monkeypatch.setattr(modul, "tarayicida_ac", lambda u: acilanlar.append(u) or u)
    sonuc = _kayit(tmp_path).get("uygulama_ac").run(ad="youtube")
    assert sonuc.data["acildi"] is True
    assert acilanlar == ["https://www.youtube.com"]


def test_a_windows_app_on_plain_linux_says_why(tmp_path, monkeypatch):
    """Ne Windows ne WSL: sessizce başarısız olmaktansa sebebini söyle."""
    import jarvis.apps.ac as modul
    monkeypatch.setattr(modul, "windows_erisimi_var", lambda: False)
    sonuc = _kayit(tmp_path).get("uygulama_ac").run(ad="hesap makinesi")
    assert not sonuc.ok
    assert "Windows değil" in sonuc.error


def test_a_windows_app_opens_directly_on_windows(tmp_path, monkeypatch):
    """Yerel Windows'ta araya cmd.exe sokmak gerekmiyor."""
    import jarvis.apps.ac as modul
    acilanlar = []
    monkeypatch.setattr(modul, "windows_erisimi_var", lambda: True)
    monkeypatch.setattr(modul, "windows_mi", lambda: True)
    monkeypatch.setattr(modul, "_yerel_windows_programi",
                        lambda h: acilanlar.append(h) or True)
    sonuc = _kayit(tmp_path).get("uygulama_ac").run(ad="hesap makinesi")
    assert sonuc.data["acildi"] is True
    assert acilanlar == ["calc.exe"]


def test_a_settings_uri_also_opens_directly_on_windows(tmp_path, monkeypatch):
    import jarvis.apps.ac as modul
    acilanlar = []
    monkeypatch.setattr(modul, "windows_erisimi_var", lambda: True)
    monkeypatch.setattr(modul, "windows_mi", lambda: True)
    monkeypatch.setattr(modul, "_yerel_windows_programi",
                        lambda h: acilanlar.append(h) or True)
    sonuc = _kayit(tmp_path).get("uygulama_ac").run(ad="bluetooth")
    assert sonuc.data["acildi"] is True
    assert acilanlar == ["ms-settings:bluetooth"]


def test_a_missing_program_on_windows_says_so(tmp_path, monkeypatch):
    import jarvis.apps.ac as modul
    monkeypatch.setattr(modul, "windows_erisimi_var", lambda: True)
    monkeypatch.setattr(modul, "windows_mi", lambda: True)
    monkeypatch.setattr(modul, "_yerel_windows_programi", lambda h: False)
    sonuc = _kayit(tmp_path).get("uygulama_ac").run(ad="hesap makinesi")
    assert not sonuc.ok
    assert "bulunmuyor" in sonuc.error


@pytest.mark.parametrize("returncode", [1, 7])
def test_process_launcher_rejects_nonzero_exit_codes(monkeypatch, returncode):
    import jarvis.apps.ac as modul

    class Process:
        def wait(self, timeout=None):
            return returncode

    monkeypatch.setattr(modul.subprocess, "Popen", lambda *a, **k: Process())
    assert modul._calistir(["broken.exe"]) is False


def test_process_launcher_does_not_wait_for_a_running_gui(monkeypatch):
    import subprocess
    import jarvis.apps.ac as modul

    class Process:
        def wait(self, timeout=None):
            if timeout is not None:
                raise subprocess.TimeoutExpired("gui.exe", timeout)
            return 0

    started = []

    class Thread:
        def __init__(self, **kwargs):
            started.append(kwargs)
        def start(self):
            started.append("started")

    monkeypatch.setattr(modul.subprocess, "Popen", lambda *a, **k: Process())
    monkeypatch.setattr(modul.threading, "Thread", Thread)

    assert modul._calistir(["gui.exe"]) is True
    assert "started" in started


def test_native_startfile_needs_a_real_process(monkeypatch):
    import jarvis.apps.ac as modul

    opened = []
    monkeypatch.setattr(modul.os, "startfile", lambda target: opened.append(target),
                        raising=False)
    monkeypatch.setattr(modul, "_sureci_bekle", lambda _target: False)

    assert modul._yerel_windows_programi("devmgmt.msc") is False
    assert opened == ["devmgmt.msc"]


def test_native_startfile_succeeds_after_process_verification(monkeypatch):
    import jarvis.apps.ac as modul

    monkeypatch.setattr(modul.os, "startfile", lambda _target: None, raising=False)
    monkeypatch.setattr(modul, "_sureci_bekle", lambda _target: True)
    assert modul._yerel_windows_programi("devmgmt.msc") is True


def test_msc_targets_are_verified_as_mmc_processes():
    import jarvis.apps.ac as modul

    assert modul._beklenen_surec_adlari("devmgmt.msc") == {"mmc.exe"}
    assert modul._beklenen_surec_adlari("C:\\Windows\\diskmgmt.msc") == {"mmc.exe"}


def test_process_name_check_is_case_insensitive(monkeypatch):
    import jarvis.apps.ac as modul

    class Process:
        info = {"name": "MMC.EXE"}

    monkeypatch.setattr(modul.psutil, "process_iter", lambda _attrs: [Process()])
    assert modul._surec_var_mi({"mmc.exe"}) is True


def test_the_list_tool_reports_what_can_be_opened(tmp_path):
    sonuc = _kayit(tmp_path).get("uygulama_listesi").run()
    assert sonuc.data["adet"] == len(VARSAYILAN)
    assert "uygulamalar.json" in sonuc.data["ekleme_dosyasi"]


def test_the_tools_are_registered_by_bootstrap():
    from jarvis.bootstrap import build_agent
    from jarvis.config import Config
    from jarvis.memory.store import MemoryStore
    ajan = build_agent(Config(llm_provider="mock", non_interactive=True),
                       memory=MemoryStore(":memory:"))
    adlar = {t.name for t in ajan.registry.all()}
    assert {"uygulama_ac", "uygulama_listesi"} <= adlar


@pytest.mark.parametrize("izin", [
    "Önerilerde bulunabilirsin",
    "Önerilerde bulanabilirsin",
    "Uygulama tavsiyesi verebilirsin",
])
def test_app_suggestion_permission_keeps_the_previous_subject(izin, monkeypatch):
    from jarvis.bootstrap import build_agent
    from jarvis.config import Config
    from jarvis.memory.store import MemoryStore

    ajan = build_agent(Config(llm_provider="mock", non_interactive=True),
                       memory=MemoryStore(":memory:"))
    ajan.history.extend((
        Message(role="user", content="Hangi uygulamaları açabiliyorsun?"),
        Message(role="tool", name="uygulama_listesi",
                content='{"uygulamalar":[{"ad":"YouTube"}]}'),
        Message(role="assistant", content="Açabildiğim uygulama listesini gösterdim."),
    ))
    monkeypatch.setattr(
        ajan.llm, "chat",
        lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("bağlamsal onay LLM'e gitmemeli")),
    )

    cevap = ajan.ask(izin)
    assert "uygulama" in cevap.lower()
    assert "önereceğim" in cevap.lower()
    assert "ne arıyorsunuz" not in cevap.lower()


def test_generic_suggestion_permission_is_not_hijacked_by_old_app_context():
    from jarvis.bootstrap import build_agent
    from jarvis.config import Config
    from jarvis.memory.store import MemoryStore

    ajan = build_agent(Config(llm_provider="mock", non_interactive=True),
                       memory=MemoryStore(":memory:"))
    ajan.history.extend((
        Message(role="user", content="Hangi uygulamaları açabiliyorsun?"),
        Message(role="assistant", content="Açabildiğim uygulama listesini gösterdim."),
        Message(role="user", content="Bugünkü donanım planını konuşalım."),
        Message(role="assistant", content="Donanım planını değerlendirebiliriz."),
    ))
    assert ajan._app_suggestion_acknowledgement("Önerilerde bulunabilirsin") is None
