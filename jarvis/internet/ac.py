"""Opening a link in the owner's own browser.

Under WSL this is not what Python's ``webbrowser`` module does. There is no
browser inside the distro; the one the owner is looking at runs on Windows.
So the link is handed to Windows through interop, and only if that is
unavailable do we fall back to a Linux opener.

The address is validated for *shape* but not resolved. The owner's browser
does its own lookup, and the owner sees the address bar — unlike a fetch,
where J.A.R.V.I.S. reads the response and nobody else ever sees where it
went. What must not happen is a scheme that opens something other than a web
page: ``file://`` would hand a local file to the browser, and on Windows a
UNC path would reach a network share.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import urllib.parse
from pathlib import Path

from ..core.ortam import wsl_mi as _wsl_mi, windows_mi
from .guvenlik import AdresReddedildi, url_denetle

ZAMAN_ASIMI = 12.0


class AcError(RuntimeError):
    """Raised with a Turkish message the tool layer can hand straight back."""


#: Ortam tespiti tek yerde (jarvis/core/ortam.py). Bu ad geriye dönük
#: uyumluluk için duruyor: testler ve eski çağrı yerleri buradan alıyor.
wsl_mi = _wsl_mi


def _yerel_windows_ile_ac(url: str) -> bool:
    """Doğrudan Windows: kabuğun kendi açıcısı.

    ``os.startfile`` Explorer'ın "aç" fiilini çağırıyor — kullanıcının
    VARSAYILAN tarayıcısında açılıyor, bir ara program gerekmeden.
    """
    try:
        os.startfile(url)      # type: ignore[attr-defined]  # yalnızca Windows
        return True
    except (OSError, AttributeError, ValueError):
        return False


def _windows_ile_ac(url: str) -> bool:
    """Hand the URL to Windows. Returns False when interop is unavailable."""
    for arac, argumanlar in (
        # wslview WSL'in kendi acicisi; kuruluysa en temizi.
        ("wslview", [url]),
        # explorer.exe her WSL kurulumunda var. Basarili acilista bile
        # sifirdan farkli bir kod donduruyor, o yuzden ciktiya bakmiyoruz.
        ("explorer.exe", [url]),
    ):
        if shutil.which(arac) is None:
            continue
        try:
            subprocess.run([arac, *argumanlar], timeout=ZAMAN_ASIMI,
                           capture_output=True, check=False)
            return True
        except (OSError, subprocess.SubprocessError):
            continue
    return False


def _linux_ile_ac(url: str) -> bool:
    if shutil.which("xdg-open") is None:
        return False
    try:
        subprocess.run(["xdg-open", url], timeout=ZAMAN_ASIMI,
                       capture_output=True, check=False)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def tarayicida_ac(url: str) -> str:
    """Open a web address in the owner's browser. Returns the address opened."""
    try:
        # coz=False: adresi tarayici zaten kendisi cozumleyecek ve sahibi
        # nereye gittigini adres cubugunda gorecek. Burada onemli olan
        # semanin gercekten bir web adresi olmasi.
        guvenli = url_denetle(url, coz=False)
    except AdresReddedildi as exc:
        raise AcError(str(exc)) from exc

    # Once bulundugumuz ortamin dogru yolu, sonra digerleri. Sira onemli:
    # WSL'de xdg-open kurulu olabiliyor ama acacak bir masaustu yok, ve
    # sessizce basarili donuyor — hicbir sey acilmadan.
    if windows_mi():
        denemeler = (_yerel_windows_ile_ac, _linux_ile_ac)
    elif wsl_mi():
        denemeler = (_windows_ile_ac, _linux_ile_ac)
    else:
        denemeler = (_linux_ile_ac, _windows_ile_ac)

    if not any(dene(guvenli) for dene in denemeler):
        raise AcError(_neden_acilmadi())
    return guvenli


def _neden_acilmadi() -> str:
    """Say what to do about it, on the system we are actually on."""
    if windows_mi():
        return ("Tarayıcı açılamadı. Windows'ta varsayılan tarayıcı "
                "tanımlı olmayabilir: Ayarlar → Uygulamalar → "
                "Varsayılan uygulamalar.")
    if wsl_mi():
        return ("Tarayıcı açılamadı. WSL'de interop kapalı olabilir "
                "(/etc/wsl.conf içinde [interop] enabled=true) veya "
                "'wslu' kurulu değil: sudo apt install wslu")
    return ("Tarayıcı açılamadı. Masaüstü ortamı yoksa 'xdg-open' "
            "çalışmaz: sudo apt install xdg-utils")


def arama_adresi(sorgu: str, motor: str = "google") -> str:
    """Build a search URL for the given engine."""
    sorgu = (sorgu or "").strip()
    if not sorgu:
        raise AcError("Boş sorgu ile arama açılamaz.")
    q = urllib.parse.quote_plus(sorgu)
    motorlar = {
        "google": f"https://www.google.com/search?q={q}",
        "duckduckgo": f"https://duckduckgo.com/?q={q}",
        "youtube": f"https://www.youtube.com/results?search_query={q}",
        "wikipedia": f"https://tr.wikipedia.org/w/index.php?search={q}",
        "github": f"https://github.com/search?q={q}",
    }
    adres = motorlar.get(motor.strip().lower())
    if adres is None:
        raise AcError(f"Bilinmeyen arama motoru: {motor}. "
                      f"Seçenekler: {', '.join(sorted(motorlar))}")
    return adres
