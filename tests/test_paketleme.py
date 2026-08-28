"""Temiz bir makinede kurulum gerçekten çalışıyor mu.

Bu dosyanın var olma sebebi somut: ``windows/`` klasörü eklendikten sonra
``pip install -e .`` temiz bir ortamda şu hatayla düşmeye başladı —

    error: Multiple top-level packages discovered in a flat-layout:
    ['jarvis', 'windows']

— ve bu hata **geliştirme makinesinde hiçbir belirti vermedi**. Zaten kurulu
bir ortam çalışmaya devam ediyordu; kırılan tek şey, kimsenin her gün
yapmadığı iş olan sıfırdan kurulumdu. Yani hata ancak yeni bilgisayarda,
tam da kurulum yaparken görünecekti.

Buradaki testler ağa çıkmıyor ve paket kurmuyor: yapılandırmanın kurulumu
belirsizliğe bırakmadığını denetliyorlar.
"""
import tomllib
import re
from pathlib import Path

import pytest

from scripts.windows_acceptance import configure_utf8_console

KOK = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def proje():
    return tomllib.loads((KOK / "pyproject.toml").read_text(encoding="utf-8"))


def test_the_build_backend_is_stated_explicitly(proje):
    """Yazılmadığında pip'in seçtiği arka uç sürümüne göre değişiyor."""
    assert proje["build-system"]["build-backend"] == "setuptools.build_meta"
    assert proje["build-system"]["requires"]


def test_package_discovery_is_not_left_to_guesswork(proje):
    """Otomatik keşif depo kökünü tarıyor ve jarvis dışındakileri de topluyor."""
    bulma = proje["tool"]["setuptools"]["packages"]["find"]
    assert bulma["include"] == ["jarvis*"]


def test_every_top_level_folder_that_is_not_jarvis_stays_out():
    """Keşfe bırakılsa bu klasörlerin her biri bir paket sanılırdı.

    ``__init__.py`` gerekmiyor: setuptools ad alanı paketlerini de buluyor,
    ki ``windows/`` tam olarak öyle yakalandı.
    """
    disarida = []
    for yol in KOK.iterdir():
        if not yol.is_dir() or yol.name.startswith((".", "_")):
            continue
        if yol.name == "jarvis":
            continue
        if any(yol.glob("**/*.py")):
            disarida.append(yol.name)
    # Bunlarin pakete girmemesi gerekiyor; testin amaci listeyi gormek degil,
    # boyle klasorlerin VAR oldugunu ve yapilandirmanin onlari dislamasi
    # gerektigini kayit altina almak.
    assert disarida, "python dosyasi olan baska klasor kalmamis: kural gevsetilebilir"
    assert "tests" in disarida


def test_the_entry_points_the_installer_promises_exist(proje):
    """Kurulum bittiğinde bu komutlar çalışabilmeli."""
    komutlar = proje["project"]["scripts"]
    for ad in ("jarvis", "jarvis-panel", "jarvis-ses", "jarvis-tanit"):
        assert ad in komutlar, f"{ad} tanımlı değil"
        modul = komutlar[ad].split(":")[0]
        assert modul.startswith("jarvis."), f"{ad} jarvis paketinin dışını gösteriyor"


def test_the_optional_extras_do_not_hide_a_required_dependency(proje):
    """İsteğe bağlı olan gerçekten isteğe bağlı olmalı: onlarsız da açılmalı."""
    zorunlu = proje["project"]["dependencies"]
    assert zorunlu == ["psutil>=5.9"], (
        "Zorunlu bağımlılık listesi büyüdü. Her ekleme kurulumu ağırlaştırıyor "
        "ve ağsız bir makinede kurulumu tamamen engelleyebiliyor."
    )


def test_the_identity_seed_ships_with_the_package():
    """Kimlik dosyası depoda: yeni bir makinede J.A.R.V.I.S. sahibini tanımalı."""
    assert (KOK / "kimlik.json").is_file()


def test_the_windows_installer_ships_with_the_repository():
    """ZIP indirip kuracak birinin ihtiyacı olan her şey depoda olmalı."""
    for gereken in ("windows/Kur.cmd", "windows/JARVIS.exe", "windows/jarvis.ico",
                    "windows/jarvis.ini", "windows/src/kur-windows.ps1",
                    "windows/src/watchdog.ps1"):
        assert (KOK / gereken).is_file(), f"{gereken} depoda yok"


# ---------------- indirme yonergesi ----------------
# İndirme rehberi artık public Production Edition Release paketini göstermeli;
# eski özel depo ve geliştirme dalı kullanıcıya sunulmamalı.

#: Elle yazildiginda calismayan bicimler. Hicbir belgede onerilmemeli.
CALISMAYAN = (
    "github.com/oguzcankayir54-glitch/jarvis/archive/refs/heads/claude",
    "codeload.github.com/oguzcankayir54-glitch/jarvis/zip",
)


def _belgeler():
    for belge in KOK.rglob("*.md"):
        if ".venv" in belge.parts or "cikti" in str(belge):
            continue
        yield belge


def test_the_download_guide_exists():
    assert (KOK / "INDIRME.md").is_file()


def test_the_guide_gives_the_button_path_not_a_dead_link():
    """Hazır EXE birincil, kaynak ZIP ikincil yol olmalı."""
    metin = (KOK / "INDIRME.md").read_text(encoding="utf-8")
    assert "Download ZIP" in metin
    assert "JARVIS-Setup-2.0.1.exe" in metin
    assert "feat/complete-project-sync" in metin
    assert "oguzcankayir54-glitch/jarvis" not in metin


def test_release_download_links_use_one_current_tag():
    """Aynı ürün için iki farklı kurucu önermek eski hatayı geri getirir."""
    belgeler = (KOK / "README.md", KOK / "INDIRME.md",
                KOK / "docs" / "KURULUM-WINDOWS.md")
    tags = set()
    for belge in belgeler:
        tags.update(re.findall(r"releases/download/(v[^/]+)/JARVIS-Setup-",
                               belge.read_text(encoding="utf-8")))
    assert tags == {"v2.0.1-production.7"}


def test_release_workflow_runs_acceptance_before_building_installer():
    workflow = (KOK / ".github" / "workflows" /
                "windows-installer-release.yml").read_text(encoding="utf-8")
    assert "python scripts/windows_acceptance.py" in workflow
    assert "needs: test" in workflow


def test_windows_acceptance_forces_utf8_console(monkeypatch):
    class Console:
        configured = None

        def reconfigure(self, **kwargs):
            self.configured = kwargs

    console = Console()
    monkeypatch.setattr("scripts.windows_acceptance.sys.stdout", console)
    configure_utf8_console()
    assert console.configured == {"encoding": "utf-8", "errors": "backslashreplace"}


def test_no_document_offers_a_link_that_does_not_work():
    """Ikisi de denendi ve ikisi de tarayicida 404 verdi."""
    for belge in _belgeler():
        metin = belge.read_text(encoding="utf-8")
        for kirik in CALISMAYAN:
            if kirik not in metin:
                continue
            # Yalnizca "bu calismiyor" diye ANLATMAK serbest; onermek degil.
            assert "404" in metin, f"{belge}: calismayan adres uyarisiz duruyor"


@pytest.mark.parametrize("belge", ["KURULUM.md", "windows/BENIOKU.md"])
def test_the_install_docs_point_at_the_download_guide(belge):
    metin = (KOK / belge).read_text(encoding="utf-8")
    assert "INDIRME.md" in metin


def test_the_double_clickable_installer_is_named_in_the_guide():
    metin = (KOK / "INDIRME.md").read_text(encoding="utf-8")
    assert "JARVIS-Setup-2.0.1.exe" in metin and "Kur.cmd" in metin
    # Ikinci asistan kaldirildi: olmayan bir dosyaya cift tiklatmak,
    # kurulumun ilk adiminda takilmak demek olurdu.
    assert "Kur-Friday.cmd" not in metin


def test_the_guide_says_what_survives_an_update():
    """"Guncellersem ayarlarim gider mi" sorusu sorulmadan cevaplanmali."""
    metin = (KOK / "INDIRME.md").read_text(encoding="utf-8")
    for korunan in (".env", "jeton", ".venv", "jarvis-yedek"):
        assert korunan in metin
