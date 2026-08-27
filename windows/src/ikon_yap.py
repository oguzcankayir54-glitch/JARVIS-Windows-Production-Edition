"""Build ``jarvis.ico`` from ``logo.svg``.

Each size is rendered from the SVG separately rather than downsampled from one
large bitmap: at 16 and 20 pixels a downsampled glow turns into grey mush, and
those are exactly the sizes Windows uses in the taskbar and Explorer lists.
"""
from __future__ import annotations


import sys
from pathlib import Path

from PIL import Image

BURASI = Path(__file__).resolve().parent
SVG = BURASI / "logo.svg"
ICO = BURASI.parent / "jarvis.ico"
PNG = BURASI.parent / "jarvis-logo.png"

CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"

#: Windows'un gerçekten istediği boyutlar. 256 Explorer'ın büyük görünümü,
#: 16 görev çubuğu ve menüler.
BOYUTLAR = (16, 20, 24, 32, 40, 48, 64, 128, 256)


#: Hedef boyutun kaç katında çizilip küçültüleceği. Süperörnekleme: 16 pikseli
#: doğrudan çizdirmek yerine 64'te çizip indirmek, cam kenarları ve parlamayı
#: çok daha temiz bırakıyor.
KAT = 4


def render_hepsi(boyutlar: tuple[int, ...], klasor: Path) -> dict[int, Path]:
    """Render the SVG once per size, at KAT× and with an exact viewport.

    Playwright is used rather than ``--screenshot`` because the old headless
    mode clamps the window height to whatever chrome it thinks it needs, which
    silently produced a 256×169 icon.
    """
    from playwright.sync_api import sync_playwright

    govde = SVG.read_text(encoding="utf-8")
    sayfa = klasor / "sayfa.html"
    cikti: dict[int, Path] = {}

    with sync_playwright() as pw:
        tarayici = pw.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        for boyut in boyutlar:
            cizim = max(boyut * KAT, 128)
            sayfa.write_text(
                "<!doctype html><meta charset='utf-8'>"
                "<style>html,body{margin:0;padding:0;background:transparent;"
                "overflow:hidden}"
                f"svg{{display:block;width:{cizim}px;height:{cizim}px}}</style>" + govde,
                encoding="utf-8",
            )
            s = tarayici.new_page(viewport={"width": cizim, "height": cizim},
                                  device_scale_factor=1)
            s.goto(f"file://{sayfa}")
            s.wait_for_timeout(120)
            hedef = klasor / f"{boyut}.png"
            s.screenshot(path=str(hedef), omit_background=True)
            s.close()
            cikti[boyut] = hedef
        tarayici.close()

    sayfa.unlink(missing_ok=True)
    return cikti


def main() -> int:
    if not Path(CHROME).exists():
        print(f"! Chromium bulunamadı: {CHROME}")
        return 1

    katmanlar: list[Image.Image] = []
    gecici = BURASI / "_gecici"
    gecici.mkdir(exist_ok=True)
    try:
        cizimler = render_hepsi(BOYUTLAR, gecici)
        for boyut in BOYUTLAR:
            resim = Image.open(cizimler[boyut]).convert("RGBA")
            if resim.size != (boyut, boyut):
                resim = resim.resize((boyut, boyut), Image.LANCZOS)
            katmanlar.append(resim)
            print(f"  {boyut:>3}×{boyut:<3} çizildi")

        en_buyuk = katmanlar[-1]
        en_buyuk.save(PNG)
        # append_images ile her boyut kendi çiziminden gider; sizes= tek
        # görüntüden küçültür ve küçük boyutlar bulanıklaşır.
        en_buyuk.save(ICO, format="ICO", append_images=katmanlar[:-1],
                      sizes=[(b, b) for b in BOYUTLAR])
    finally:
        for artik in gecici.glob("*"):
            artik.unlink()
        gecici.rmdir()

    print(f"\n✓ {ICO}  ({ICO.stat().st_size} bayt)")
    print(f"✓ {PNG}  ({PNG.stat().st_size} bayt)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
