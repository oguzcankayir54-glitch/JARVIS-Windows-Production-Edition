"""Actually starting the thing the catalogue resolved to.

Three kinds of target, three ways to reach them — and under WSL none of them
is what Python's ``webbrowser`` or a bare ``subprocess`` would do, because the
programs the owner means are on the Windows side of the boundary.

Nothing here accepts a free path. The target always comes from
:mod:`jarvis.apps.katalog`, which is an allowlist. That is what keeps "open
anything I use" from becoming "run anything you are told to".
"""
from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
from pathlib import PureWindowsPath

import psutil

from ..core.ortam import windows_erisimi_var, windows_mi, wsl_mi as _wsl_mi
from ..internet.ac import AcError, tarayicida_ac
from .katalog import URI, WEB, WINDOWS, Uygulama

BASLATMA_YOKLAMA_SURESI = 0.5
SUREC_DOGRULAMA_SURESI = 4.0
SUREC_DOGRULAMA_ARALIGI = 0.1

_SUREC_ESLEME = {
    # Modern Windows calc.exe'yi paketlenmiş hesap makinesine devredebilir.
    "calc.exe": {"calc.exe", "calculator.exe", "calculatorapp.exe"},
    # ms-settings URI'lerinin görünür sahibi bu süreçtir.
    "ms-settings:": {"systemsettings.exe"},
}


#: Ortam tespiti tek yerde. Ad geriye dönük uyumluluk için duruyor.
wsl_mi = _wsl_mi


def _beklenen_surec_adlari(hedef: str) -> set[str]:
    """Translate a catalogue target to the process Windows should expose."""
    folded = (hedef or "").strip().casefold()
    if not folded:
        return set()
    if folded.startswith("ms-settings:"):
        return set(_SUREC_ESLEME["ms-settings:"])
    name = PureWindowsPath(hedef).name.casefold()
    if name.endswith(".msc"):
        return {"mmc.exe"}
    if name in _SUREC_ESLEME:
        return set(_SUREC_ESLEME[name])
    if name.endswith(".exe"):
        return {name}
    return set()


def _surec_var_mi(adlar: set[str]) -> bool:
    if not adlar:
        return False
    try:
        for process in psutil.process_iter(["name"]):
            try:
                name = str(process.info.get("name") or "").casefold()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
            if name in adlar:
                return True
    except (psutil.Error, OSError):
        return False
    return False


def _sureci_bekle(hedef: str) -> bool:
    """Wait briefly until the process implied by ``hedef`` really exists."""
    adlar = _beklenen_surec_adlari(hedef)
    if not adlar:
        return False
    deadline = time.monotonic() + SUREC_DOGRULAMA_SURESI
    while True:
        if _surec_var_mi(adlar):
            return True
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        time.sleep(min(SUREC_DOGRULAMA_ARALIGI, remaining))


def _yerel_windows_programi(hedef: str) -> bool:
    """Doğrudan Windows: programı kabuğun kendisi başlatsın.

    ``os.startfile`` Explorer'ın "aç" fiili — ``.exe`` de, ``.msc`` konsolu
    da, bir kısayol da aynı çağrıyla açılıyor, ve WSL'deki gibi araya bir
    ``cmd.exe`` sokmak gerekmiyor.
    """
    try:
        os.startfile(hedef)    # type: ignore[attr-defined]  # yalnızca Windows
        return _sureci_bekle(hedef)
    except (OSError, AttributeError, ValueError):
        return False


def _arkada_bekle(process: subprocess.Popen) -> None:
    """Reap a long-running child without blocking the request thread."""
    try:
        process.wait()
    except (OSError, subprocess.SubprocessError):
        pass


def _calistir(argumanlar: list[str]) -> bool:
    try:
        process = subprocess.Popen(
            argumanlar,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            return process.wait(timeout=BASLATMA_YOKLAMA_SURESI) == 0
        except subprocess.TimeoutExpired:
            # GUI hâlâ ayaktaysa açılışı başarılı kabul et; kapanmasını istek
            # iş parçacığında beklemek 15 saniyelik gecikmeye ve yanlış
            # fallback üzerinden ikinci kopyaya yol açıyordu.
            threading.Thread(
                target=_arkada_bekle,
                args=(process,),
                name="jarvis-app-reaper",
                daemon=True,
            ).start()
            return True
    except (OSError, subprocess.SubprocessError):
        return False


def _windows_programi(hedef: str) -> bool:
    """Start a Windows program from inside WSL.

    Interop puts the Windows PATH on ours, so ``notepad.exe`` usually runs
    directly. ``.msc`` consoles are not executables and need the shell, and a
    program that interop cannot see needs it too — hence the fallback.

    ``cmd.exe`` is called with ``cd /d %SystemRoot%`` first: started from a
    ``\\\\wsl$`` path it prints a UNC warning and silently works from
    ``C:\\Windows`` anyway, which looks like a failure in the output.
    """
    if hedef.endswith(".exe") and shutil.which(hedef) and _calistir([hedef]):
        return True
    if shutil.which("cmd.exe"):
        return _calistir(["cmd.exe", "/c",
                          f'cd /d %SystemRoot% && start "" "{hedef}"'])
    return False


def _protokol(hedef: str) -> bool:
    """Open a shell URI (``ms-settings:``…). Explorer resolves these."""
    if shutil.which("explorer.exe") and _calistir(["explorer.exe", hedef]):
        return True
    if shutil.which("cmd.exe"):
        return _calistir(["cmd.exe", "/c",
                          f'cd /d %SystemRoot% && start "" "{hedef}"'])
    return False


def uygulamayi_ac(uygulama: Uygulama) -> str:
    """Open one catalogue entry. Returns what was opened, or raises."""
    if uygulama.tur == WEB:
        return tarayicida_ac(uygulama.hedef)

    if not windows_erisimi_var():
        # Duz Linux'ta bir Windows programi yok; sessizce basarisiz olmaktansa
        # neden olmadigini soylemek iyi.
        raise AcError(
            f"'{uygulama.ad}' bir Windows programı; bu makine Windows değil."
        )

    if uygulama.tur not in (WINDOWS, URI):
        raise AcError(f"Bilinmeyen hedef türü: {uygulama.tur}")

    if windows_mi():
        # Yerel Windows: program da protokol de ayni cagriyla aciliyor.
        if _yerel_windows_programi(uygulama.hedef):
            return uygulama.hedef
        raise AcError(
            f"'{uygulama.ad}' açılamadı. Program bu Windows kurulumunda "
            "bulunmuyor olabilir."
        )

    if uygulama.tur == WINDOWS:
        if _windows_programi(uygulama.hedef):
            return uygulama.hedef
    elif _protokol(uygulama.hedef):
        return uygulama.hedef

    raise AcError(
        f"'{uygulama.ad}' açılamadı. WSL'de Windows programlarını "
        "çalıştırmak için interop açık olmalı "
        "(/etc/wsl.conf içinde [interop] enabled=true)."
    )
