"""Hangi sistemin üstünde çalışıyoruz.

Üç ayrı ortam var ve üçü de farklı davranıyor:

* **Windows** — artık asıl hedef. Programlar doğrudan başlatılıyor, komutlar
  Windows komutları, yollar ``C:\\Users\\...``.
* **WSL** — Linux görünen ama Windows'un içinde duran ara katman. Programlar
  ``.exe`` ile, tarayıcı ``wslview`` ile açılıyor.
* **Linux** — düz Linux; Windows programı diye bir şey yok.

Bu ayrım üç dosyada üç kez elle yazılmıştı (``/proc/version`` okuyan üç ayrı
kopya). Bir yere toplanınca hem tutarlı oluyor hem de testte sahtelenebiliyor.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def windows_mi() -> bool:
    """Doğrudan Windows üzerinde miyiz (WSL değil)."""
    return os.name == "nt" or sys.platform.startswith("win")


def wsl_mi() -> bool:
    """WSL içindeki bir Linux'ta mıyız.

    Çekirdek sürümünde "microsoft" geçiyor; WSL1 ve WSL2'de de öyle.
    Dosya okunamıyorsa cevap hayır: WSL olduğunu varsayıp ``.exe``
    çağırmaya çalışmak, düz Linux'ta her açma denemesini bozardı.
    """
    if windows_mi():
        return False
    try:
        return "microsoft" in Path("/proc/version").read_text().lower()
    except OSError:
        return False


def windows_erisimi_var() -> bool:
    """Windows programları çalıştırılabiliyor mu — doğrudan ya da interop ile."""
    return windows_mi() or wsl_mi()


def ad() -> str:
    """İnsan için tek kelime: panelde ve tanılama çıktılarında görünüyor."""
    if windows_mi():
        return "windows"
    if wsl_mi():
        return "wsl"
    return "linux"
