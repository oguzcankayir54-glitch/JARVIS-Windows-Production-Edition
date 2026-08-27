"""Windows'un okuyabileceği biçime çevir: CRLF satır sonları, UTF-8 BOM.

Bu depo Linux'ta yazılıyor, betikler Windows'ta çalışıyor ve **Windows
PowerShell 5.1** (Windows 10/11'de kurulu olan sürüm) ikisine de duyarlı:

* **BOM olmadan** bir ``.ps1`` dosyasını UTF-8 değil ANSI sayıyor. Türkçe
  harfler bozuluyor: ``yapılamadı`` → ``yapÄ±lamadÄ±``.
* **LF satır sonlarıyla** here-string sonlandırıcısını (``"@``) tanımıyor.
  Blok açık kalıyor, içindeki metin kod diye ayrıştırılıyor ve betik
  tamamen bozuluyor.

Bunlar sessiz tuzaklar: Linux'ta dosya kusursuz görünüyor, PowerShell 7'de
sorunsuz ayrışıyor, ve yalnızca kullanıcının makinesinde patlıyor. Bu yüzden
biçim elle değil buradan uygulanıyor ve ``.gitattributes`` ile korunuyor.

``.cmd`` dosyaları CRLF alır ama **BOM almaz** — cmd.exe BOM'u komut sanıp
ekrana döküyor.
"""
from __future__ import annotations

import sys
from pathlib import Path

BURASI = Path(__file__).resolve().parent
WINDOWS = BURASI.parent

#: (dosya, BOM ister mi)
DOSYALAR = (
    (WINDOWS / "src" / "kur.ps1", True),
    (WINDOWS / "src" / "kur-windows.ps1", True),
    (WINDOWS / "Kur.cmd", False),
    (WINDOWS / "jarvis.ini", True),
)

BOM = b"\xef\xbb\xbf"


def duzelt(yol: Path, bom_ister: bool) -> str:
    ham = yol.read_bytes()
    vardi_bom = ham.startswith(BOM)
    if vardi_bom:
        ham = ham[len(BOM):]

    # Once tum satir sonlarini LF'e indir, sonra CRLF'e cikar: dosya zaten
    # karisik biçimdeyse cift \r üretmeyelim.
    metin = ham.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    yeni = metin.replace(b"\n", b"\r\n")
    if bom_ister:
        yeni = BOM + yeni

    if yeni == (BOM + ham if vardi_bom else ham):
        return "değişmedi"
    yol.write_bytes(yeni)
    return f"CRLF{' + BOM' if bom_ister else ''}"


def denetle() -> int:
    """Her dosya gerçekten doğru biçimde mi? Sıfır dışı çıkış = değil."""
    kotu = 0
    for yol, bom_ister in DOSYALAR:
        ham = yol.read_bytes()
        bom_var = ham.startswith(BOM)
        govde = ham[len(BOM):] if bom_var else ham
        yalniz_lf = govde.count(b"\n") - govde.count(b"\r\n")
        sorunlar = []
        if bom_ister and not bom_var:
            sorunlar.append("BOM yok")
        if not bom_ister and bom_var:
            sorunlar.append("BOM olmamalı")
        if yalniz_lf:
            sorunlar.append(f"{yalniz_lf} satır LF")
        if sorunlar:
            kotu += 1
            print(f"  ✗ {yol.name}: {', '.join(sorunlar)}")
        else:
            print(f"  ✓ {yol.name}")
    return kotu


def main() -> int:
    if "--denetle" in sys.argv:
        return 1 if denetle() else 0
    for yol, bom_ister in DOSYALAR:
        if not yol.is_file():
            print(f"  ! yok: {yol}")
            continue
        print(f"  {yol.name}: {duzelt(yol, bom_ister)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
