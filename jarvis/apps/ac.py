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
from pathlib import Path

from ..core.ortam import windows_erisimi_var, windows_mi, wsl_mi as _wsl_mi
from ..internet.ac import AcError, tarayicida_ac
from .katalog import URI, WEB, WINDOWS, Uygulama

ZAMAN_ASIMI = 15.0


#: Ortam tespiti tek yerde. Ad geriye dönük uyumluluk için duruyor.
wsl_mi = _wsl_mi


def _yerel_windows_programi(hedef: str) -> bool:
    """Doğrudan Windows: programı kabuğun kendisi başlatsın.

    ``os.startfile`` Explorer'ın "aç" fiili — ``.exe`` de, ``.msc`` konsolu
    da, bir kısayol da aynı çağrıyla açılıyor, ve WSL'deki gibi araya bir
    ``cmd.exe`` sokmak gerekmiyor.
    """
    try:
        os.startfile(hedef)    # type: ignore[attr-defined]  # yalnızca Windows
        return True
    except (OSError, AttributeError, ValueError):
        return False


def _calistir(argumanlar: list[str]) -> bool:
    try:
        subprocess.run(argumanlar, timeout=ZAMAN_ASIMI,
                       capture_output=True, check=False)
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
