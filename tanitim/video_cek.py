"""Tanıtım videosunu GERÇEK panelden yakala.

Hiçbir sahne canlandırma değil: kayıt, çalışan panelin kendisi. Telemetri
gerçek makineden, cevap gerçek modelden (Ollama), ses gerçek seslendirme
katmanından, mikrofon turu gerçek Whisper'dan geçiyor.

Sahne süreleri anlatım seslerinin gerçek uzunluğundan geliyor (zamanlama.json),
böylece ses ile görüntü kaymıyor.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BURASI = Path(__file__).resolve().parent
HEDEF = Path(sys.argv[2]) if len(sys.argv) > 2 else BURASI / "cikti"
KROM = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
ADRES = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8801/"
#: Mikrofon sahnesi icin sahte ses aygiti. Yoksa o sahne sessiz
#: gecmiyor, yalnizca gercek bir mikrofon yokken bos kaliyor.
SAHTE_MIKROFON = str(BURASI / "sahte-mikrofon.wav")

SURELER = {s["ad"]: s["sahne_sure"]
           for s in json.loads((HEDEF / "zamanlama.json").read_text())}


KAPANIS = """
(() => {
  const k = document.createElement('div');
  k.id = 'kapanisKarti';
  k.style.cssText = `position:fixed;inset:0;z-index:99999;display:flex;
    flex-direction:column;align-items:center;justify-content:center;
    background:radial-gradient(circle at 50% 45%, #0a1a26 0%, #05090e 70%);
    font-family:'Chakra Petch',system-ui,sans-serif;color:#cfeaf7;
    opacity:0;transition:opacity .8s ease`;
  k.innerHTML = `
    <div style="font-size:88px;font-weight:700;letter-spacing:.22em;
                color:#7fe3ff;text-shadow:0 0 42px rgba(127,227,255,.5)">J.A.R.V.I.S.</div>
    <div style="margin-top:18px;font-size:23px;letter-spacing:.1em;opacity:.75">
      Kişisel teknik asistan</div>
    <div style="margin-top:64px;font-size:19px;letter-spacing:.06em;opacity:.55">
      Tasarlayan ve geliştiren</div>
    <div style="margin-top:10px;font-size:31px;font-weight:600;color:#9fe9ff">
      Oğuz Kayır</div>`;
  document.body.appendChild(k);
  requestAnimationFrame(() => { k.style.opacity = '1'; });
})();
"""


def sahne(sayfa, ad: str, is_yap=None) -> None:
    """Bir sahneyi oyna: işi yap, sonra sahnenin süresi dolana kadar bekle."""
    sure_ms = int(SURELER[ad] * 1000)
    bas = sayfa.evaluate("() => performance.now()")
    if is_yap is not None:
        is_yap()
    gecen = sayfa.evaluate("() => performance.now()") - bas
    kalan = sure_ms - gecen
    if kalan > 0:
        sayfa.wait_for_timeout(kalan)
    print(f"  {ad:10} {sure_ms/1000:5.1f}s")


def main() -> int:
    HEDEF.mkdir(exist_ok=True)
    with sync_playwright() as p:
        tarayici = p.chromium.launch(executable_path=KROM, args=[
            "--use-fake-device-for-media-stream",
            "--use-fake-ui-for-media-stream",
            f"--use-file-for-fake-audio-capture={SAHTE_MIKROFON}",
            "--autoplay-policy=no-user-gesture-required",
            "--hide-scrollbars",
        ])
        ctx = tarayici.new_context(
            viewport={"width": 1920, "height": 1080},
            record_video_dir=str(HEDEF / "ham"),
            record_video_size={"width": 1920, "height": 1080},
        )
        # Google Fonts bu konteynerden tarayiciyla erisilemiyor ve goto,
        # istek zaman asimina ugrayana kadar (13 saniye) bekliyordu — girisin
        # tamami beyaz ekran olarak kaydedilmisti. Fontlar curl ile indirildi
        # ve istekler yerel dosyalardan karsilaniyor: hem hizli, hem de video
        # urunun GERCEK tipografisiyle cikiyor.
        # Fontlar yerel olarak servis edilebiliyorsa oyle yapiliyor:
        # engellenen bir Google Fonts istegi goto'yu 13 saniye
        # bekletiyor ve girisin tamami beyaz ekran olarak kaydediliyor.
        F = BURASI / "fontlar"
        esleme = json.loads((F / "esleme.json").read_text()) \
            if (F / "esleme.json").is_file() else {}

        def font_yonlendir(route):
            if not esleme:
                return route.continue_()
            adres = route.request.url
            if "fonts.googleapis.com" in adres:
                return route.fulfill(status=200, content_type="text/css",
                                     body=(F / "fontlar.css").read_text())
            dosya = esleme.get(adres)
            if dosya:
                return route.fulfill(status=200, content_type="font/woff2",
                                     body=(F / dosya).read_bytes())
            return route.abort()

        ctx.route("https://fonts.googleapis.com/**", font_yonlendir)
        ctx.route("https://fonts.gstatic.com/**", font_yonlendir)

        sayfa = ctx.new_page()
        # Panelin kendi sesi kapali: anlatim sesi ustune binmesin.
        sayfa.add_init_script("window.__tanitim = true;")
        sayfa.goto(ADRES)

        print("sahneler:")
        # 1 — acilis girisi. Panel zaten ~10 saniyelik girisi kendisi oynatiyor.
        sahne(sayfa, "giris")

        # Panelin seslendirmesini kapat: anlatim ile carpismasin.
        try:
            sayfa.click("text=SES · AÇIK", timeout=1500)
        except Exception:
            pass

        sahne(sayfa, "panel")
        sahne(sayfa, "telemetri", lambda: sayfa.click('[data-modul="donanim"]'))

        def modul_turu():
            for ad in ("sistem", "ses", "hafiza", "bilgi"):
                sayfa.click(f'[data-modul="{ad}"]')
                sayfa.wait_for_timeout(2200)
        sahne(sayfa, "moduller", modul_turu)

        def soru_sor():
            sayfa.click('[data-modul="donanim"]')
            sayfa.fill("#askInput", "")
            sayfa.type("#askInput", "Merhaba Jarvis, sistem durumu nasıl?", delay=45)
            sayfa.press("#askInput", "Enter")
            sayfa.wait_for_timeout(6000)
        sahne(sayfa, "soru", soru_sor)

        def mikrofon():
            sayfa.click("#micBtn")
            sayfa.wait_for_timeout(10000)
            try:
                sayfa.click("#micBtn")
            except Exception:
                pass
        sahne(sayfa, "mikrofon", mikrofon)

        sahne(sayfa, "guvenlik", lambda: sayfa.click('[data-modul="araclar"]'))
        sahne(sayfa, "kapanis", lambda: sayfa.evaluate(KAPANIS))

        video = sayfa.video
        ctx.close()
        tarayici.close()
        if video:
            son = HEDEF / "panel.webm"
            Path(video.path()).replace(son)
            print("video:", son, son.stat().st_size, "bayt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
