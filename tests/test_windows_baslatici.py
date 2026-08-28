"""Windows başlatıcısının biçimi — Linux'ta yazılıp Windows'ta çalışan dosyalar.

Bu testler kodun ne yaptığını değil, dosyaların **nasıl kodlandığını**
denetliyor. Sıradışı görünüyor, ama buradaki hatalar bu projede gerçekten
yaşandı ve en kötü türden: Linux'ta dosya kusursuz görünüyor, PowerShell 7'de
sorunsuz ayrışıyor, ve yalnızca kullanıcının Windows 10 makinesinde patlıyor.
Yani geliştirirken görünmezler.

İki tuzak, ikisi de Windows PowerShell 5.1'e özgü:

* **BOM yoksa** ``.ps1`` dosyası UTF-8 değil ANSI okunuyor —
  ``yapılamadı`` → ``yapÄ±lamadÄ±``.
* **LF satır sonuyla** here-string sonlandırıcısı tanınmıyor; blok açık
  kalıyor ve içindeki metin kod diye ayrıştırılıyor.
"""
from pathlib import Path

import re

import pytest

KOK = Path(__file__).resolve().parent.parent
WINDOWS = KOK / "windows"
BOM = b"\xef\xbb\xbf"


def _oku(ad: str) -> bytes:
    yol = WINDOWS / ad
    if not yol.is_file():
        pytest.skip(f"{ad} yok")
    return yol.read_bytes()


def _yalniz_lf(govde: bytes) -> int:
    """CRLF'e ait olmayan LF sayısı."""
    return govde.count(b"\n") - govde.count(b"\r\n")


# ---------------- PowerShell ----------------

#: Windows'ta çalışan bütün PowerShell betikleri. Yeni bir tane eklenince
#: aynı tuzaklara aynı şekilde düşmesin diye liste burada.
BETIKLER = ("src/kur.ps1", "src/kur-windows.ps1", "src/watchdog.ps1")


@pytest.mark.parametrize("betik", BETIKLER)
def test_powershell_script_has_a_bom(betik):
    """BOM olmadan PS 5.1 dosyayı ANSI sanar ve Türkçe harfleri bozar."""
    assert _oku(betik).startswith(BOM)


@pytest.mark.parametrize("betik", BETIKLER)
def test_powershell_script_uses_crlf(betik):
    """LF ile PS 5.1 here-string sonlandırıcısını tanımıyor."""
    assert _yalniz_lf(_oku(betik)) == 0


@pytest.mark.parametrize("betik", BETIKLER)
def test_powershell_script_avoids_here_strings(betik):
    """CRLF bunu zaten çözüyor; here-string'siz olmak ikinci savunma.

    Bir gün biri dosyayı LF'e çeviren bir editörle kaydederse, here-string
    olmayan bir betik yine de ayrışır.
    """
    metin = _oku(betik).decode("utf-8-sig")
    assert '@"' not in metin, "here-string LF'e duyarlı; satır dizisi kullanın"


@pytest.mark.parametrize("betik", BETIKLER)
def test_powershell_script_is_valid_utf8(betik):
    _oku(betik).decode("utf-8-sig")


@pytest.mark.parametrize("betik", BETIKLER)
def test_powershell_script_has_balanced_braces(betik):
    """Kaba ama ucuz bir ayrıştırma denetimi.

    Bu depoda PowerShell çalıştırılamıyor (Linux, pwsh yok), yani sözdizimi
    ancak kullanıcının makinesinde sınanıyor. Dengesiz süslü parantez o
    hataların en sık ve en sessiz olanı: betik yarıya kadar çalışıp orada
    kesiliyor.
    """
    metin = _oku(betik).decode("utf-8-sig")
    # Dize ve yorum içindekiler sayılmasın diye kaba bir temizlik.
    temiz = re.sub(r"<#.*?#>", "", metin, flags=re.S)
    temiz = re.sub(r'"[^"\n]*"', '""', temiz)
    temiz = re.sub(r"'[^'\n]*'", "''", temiz)
    temiz = re.sub(r"(?m)#.*$", "", temiz)
    assert temiz.count("{") == temiz.count("}"), "süslü parantezler dengesiz"
    assert temiz.count("(") == temiz.count(")"), "parantezler dengesiz"


# ---------------- toplu iş dosyası ----------------

def test_cmd_uses_crlf():
    assert _yalniz_lf(_oku("Kur.cmd")) == 0


def test_cmd_has_no_bom():
    """cmd.exe BOM'u komut sanıp ekrana döküyor."""
    assert not _oku("Kur.cmd").startswith(BOM)


def test_cmd_is_pure_ascii():
    """Konsol kod sayfası öngörülemez; ASCII dışı karakter bozuk çıkar."""
    ham = _oku("Kur.cmd")
    assert all(b < 128 for b in ham)


# ---------------- WSL kabuk betiği ----------------

def test_shell_script_stays_lf():
    """CRLF ile shebang '/usr/bin/env bash\\r' olur ve çekirdek çalıştıramaz."""
    ham = _oku("kur.sh")
    assert b"\r\n" not in ham
    assert not ham.startswith(BOM)
    assert ham.startswith(b"#!/usr/bin/env bash")


# ---------------- gitattributes ----------------

def test_gitattributes_pins_the_line_endings():
    """Kural dosyada yoksa git checkout sırasında LF'e çevirir ve hata geri gelir."""
    kurallar = (KOK / ".gitattributes").read_text(encoding="utf-8")
    assert "*.ps1" in kurallar and "eol=crlf" in kurallar
    assert "*.sh" in kurallar and "eol=lf" in kurallar


# ---------------- çalıştırılabilir ----------------

def test_launcher_is_a_windows_executable():
    import struct
    ham = _oku("JARVIS.exe")
    pe = struct.unpack_from("<I", ham, 0x3C)[0]
    assert ham[pe:pe + 4] == b"PE\x00\x00"
    assert struct.unpack_from("<H", ham, pe + 4)[0] == 0x8664, "x64 olmalı"
    assert struct.unpack_from("<H", ham, pe + 0x5C)[0] == 3, "konsol uygulaması olmalı"


def test_icon_is_embedded_in_the_executable():
    """Simge exe'nin içinde olmalı: kısayol onu oradan alıyor."""
    assert _oku("JARVIS.exe").count(b"\x89PNG") >= 9


def test_icon_file_carries_every_size_windows_asks_for():
    from PIL import Image
    yol = WINDOWS / "jarvis.ico"
    if not yol.is_file():
        pytest.skip("jarvis.ico yok")
    boyutlar = set(Image.open(yol).ico.sizes())
    # 16 görev çubuğu ve menüler, 256 Explorer'ın büyük görünümü.
    assert (16, 16) in boyutlar and (256, 256) in boyutlar


# ---------------- biçim aracının kendisi ----------------

def test_the_formatter_reports_the_tree_as_correct():
    """windows_bicimi.py --denetle bu dosyaların bekçisi; kendisi de doğrulanmalı."""
    import subprocess
    import sys
    betik = WINDOWS / "src" / "windows_bicimi.py"
    if not betik.is_file():
        pytest.skip("windows_bicimi.py yok")
    sonuc = subprocess.run([sys.executable, str(betik), "--denetle"],
                           capture_output=True, text=True, timeout=60)
    assert sonuc.returncode == 0, sonuc.stdout + sonuc.stderr


# ---------------- uygulama penceresi ve giriş ----------------

def _kaynak() -> str:
    return (WINDOWS / "src" / "jarvis-launcher.c").read_text(encoding="utf-8")


def test_the_launcher_opens_an_app_window_not_a_tab():
    """İstenen şey "gerçek bir program"dı; --app kipi sekmeyi ve adres
    çubuğunu kaldırıp görev çubuğunda kendi girişini veriyor."""
    kaynak = _kaynak()
    assert "--app=" in kaynak
    assert "--user-data-dir=" in kaynak, "kendi profili olmalı"


def test_more_than_one_browser_is_tried():
    """Edge Windows 10/11'de hep var, ama Chrome/Brave da kabul edilmeli."""
    kaynak = _kaynak()
    for tarayici in ("msedge.exe", "chrome.exe", "brave.exe"):
        assert tarayici in kaynak


def test_a_missing_browser_falls_back_instead_of_giving_up():
    """Pencere süslemesi için paneli hiç açmamak saçma olurdu."""
    kaynak = _kaynak()
    assert "ShellExecuteW" in kaynak


def test_the_app_window_and_intro_are_configurable():
    kaynak = _kaynak()
    assert 'L"uygulama"' in kaynak and 'L"intro"' in kaynak
    ini = (WINDOWS / "jarvis.ini").read_text(encoding="utf-8-sig")
    assert "uygulama = 1" in ini and "intro = 1" in ini


def test_disabling_the_intro_reaches_the_panel_as_a_url_parameter():
    assert "intro=0" in _kaynak()


def test_the_app_window_allows_the_intro_sound():
    """Sayfa içi hareket olmadan ses engelleniyor; masaüstü tıklaması sayılmıyor.

    Kendi penceremiz ve kendi profilimiz olduğu için izni orada veriyoruz.
    """
    assert "--autoplay-policy=no-user-gesture-required" in _kaynak()


# ---------------- tam ekran ----------------

def test_the_window_opens_at_the_size_the_panel_was_designed_for():
    """Panel 1920x1080 için tasarlandı; daha küçüğünde sütunlar sıkışıyor."""
    kaynak = _kaynak()
    assert "g_genislik      = 1920" in kaynak
    assert "g_yukseklik     = 1080" in kaynak
    assert "--window-size=%d,%d" in kaynak


def test_fullscreen_is_the_default_and_can_be_turned_off():
    kaynak = _kaynak()
    assert "--start-fullscreen" in kaynak
    assert 'L"tamekran"' in kaynak
    ini = (WINDOWS / "jarvis.ini").read_text(encoding="utf-8-sig")
    assert "tamekran = 1" in ini
    assert "genislik = 1920" in ini and "yukseklik = 1080" in ini


# ---------------- Windows kipi ----------------
# "Artık WSL ortamından çıkıp J.A.R.V.I.S.'i tamamen Windows'a kuruyoruz."
# Başlatıcı iki kipi de tanıyor: eski kurulumlar WSL'de çalışmaya devam
# ediyor, yeni kurulum Windows'un kendi Python'unu çağırıyor.

def test_the_launcher_can_run_the_panel_on_windows_itself():
    kaynak = _kaynak()
    assert 'L"mod"' in kaynak, "kip ini'den okunmalı"
    assert "MOD_WINDOWS" in kaynak
    assert "jarvis.web.cli" in kaynak, "panel modül olarak başlatılmalı"


def test_windows_mode_does_not_require_wsl():
    """WSL'den çıkmanın anlamı bu: wsl.exe yoksa da açılmalı."""
    kaynak = _kaynak()
    kip = kaynak[kaynak.index("if (g_mod == MOD_WINDOWS) {"):]
    kesim = kip[:kip.index("} else {")]
    assert "wsl_bulundu" not in kesim
    assert "python" in kesim.lower(), "aranan şey Python olmalı"


def test_windows_mode_starts_the_panel_in_the_project_folder():
    """`.env` çalışma klasöründen okunuyor; başka bir klasörden başlatılan
    panel bütün ayarları görmeden açılır."""
    kaynak = _kaynak()
    assert "(g_mod == MOD_WINDOWS) ? g_klasor : NULL" in kaynak


def test_the_python_path_can_be_overridden():
    """Kurulum .venv kuramadıysa sistem Python'u gösterilebilmeli."""
    assert 'L"python"' in _kaynak()


def test_windows_installer_registers_a_user_watchdog():
    installer = _oku("src/kur-windows.ps1").decode("utf-8-sig")
    watchdog = _oku("src/watchdog.ps1").decode("utf-8-sig")
    assert "J.A.R.V.I.S. Watchdog.lnk" in installer
    assert "Programs\\Startup" in installer
    assert "Invoke-WebRequest" in watchdog and "/health" in watchdog
    assert "Start-Process" in watchdog and "JARVIS.exe" in watchdog
    assert "Local\\JARVIS-Watchdog" in watchdog, "yalnizca tek izleyici calismali"


def test_watchdog_can_be_disabled_in_ini():
    ini = (WINDOWS / "jarvis.ini").read_text(encoding="utf-8-sig")
    watchdog = _oku("src/watchdog.ps1").decode("utf-8-sig")
    assert "watchdog = 1" in ini
    assert 'Ini-Oku $ini "watchdog" "1"' in watchdog


# ---------------- tek asistan ----------------
# Bir donem ayni exe ikinci bir asistani da baslatiyordu ("JARVIS.exe
# friday"): asistan komut satirindan seciliyor, ini adi ve port ondan
# turuyordu. Ikinci asistan kaldirildi ve bu makine de kaldirildi —
# calismayan bir secenegi tasimak, olmayan bir seyi varmis gibi gostermek.

def test_the_launcher_takes_no_assistant_argument():
    kaynak = _kaynak()
    assert "g_asistan" not in kaynak
    assert 'L"friday"' not in kaynak
    assert "asistani_sec" not in kaynak


def test_the_launcher_reads_a_single_settings_file():
    # Ileri bildirimi degil TANIMI bul: ilki yalnizca bir prototip.
    kaynak = _kaynak()
    ini = kaynak[kaynak.index("static void ini_yolu(wchar_t *hedef, size_t adet)\n{"):]
    ini = ini[:ini.index("}")]
    assert 'L"jarvis.ini"' in ini


def test_the_launcher_does_not_set_a_stale_identity_variable():
    """Eski bir .env'de ``ASISTAN=friday`` kalmis olabilir; baslatici onu
    tazelememeli, yoksa kaldirilmis kimlik geri gelmis gibi gorunur."""
    assert 'SetEnvironmentVariableW(L"ASISTAN"' not in _kaynak()


def test_the_wsl_path_starts_the_panel():
    assert "L\"exec jarvis-panel --port %d%ls\"" in _kaynak()


def test_the_console_title_names_the_assistant():
    kaynak = _kaynak()
    assert 'L"J.A.R.V.I.S."' in kaynak
    assert 'L"F.R.I.D.A.Y."' not in kaynak


# ---------------- kurulum ----------------

def _kurulum_kaynagi() -> str:
    return (KOK / "windows" / "src" / "kur-windows.ps1").read_text(encoding="utf-8-sig")


def test_the_installer_offers_no_second_assistant():
    kaynak = _kurulum_kaynagi()
    assert "[switch]$Friday" not in kaynak
    assert "if ($Friday)" not in kaynak
    assert 'Ini-Yaz "friday"' not in kaynak


def test_the_installer_writes_the_settings_file():
    assert 'Ini-Yaz "jarvis" "J.A.R.V.I.S." 8765' in _kurulum_kaynagi()


def test_the_shortcut_needs_no_argument():
    kaynak = _kurulum_kaynagi()
    govde = kaynak[kaynak.index("function Kisayol-Yap"):]
    govde = govde[:govde.index("if (Kisayol-Yap")]
    assert '$lnk.Arguments' not in govde
    assert 'Kisayol-Yap $Masaustu "J.A.R.V.I.S."' in kaynak


def test_the_existing_token_survives_reinstall():
    """'Tokenleri asla degistirme' kurali."""
    kaynak = _kurulum_kaynagi()
    govde = kaynak[kaynak.index("function Ini-Yaz"):]
    govde = govde[:govde.index('Ini-Yaz "jarvis"')]
    assert "jeton" in govde
    assert "$eski = @($eski)" in govde, "tek satirda dize donme tuzagi"


def test_install_and_uninstall_both_clear_the_removed_assistant():
    """Onceden F.R.I.D.A.Y. kuranlarda masaustunde calismayan bir simge
    kaliyor. Kurulum kendi biraktigini kendi topluyor."""
    kaynak = _kurulum_kaynagi()
    kaldir = kaynak[:kaynak.index("function Ini-Yaz")]
    assert "F.R.I.D.A.Y..lnk" in kaldir, "kaldirmada simge silinmeli"
    kurulum = kaynak[kaynak.index('Ini-Yaz "jarvis"'):]
    assert "F.R.I.D.A.Y..lnk" in kurulum, "kurulumda kalinti temizlenmeli"
    assert "friday.ini" in kurulum
