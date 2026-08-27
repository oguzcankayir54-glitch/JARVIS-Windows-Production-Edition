"""What "aç" can mean, and how a spoken name finds it.

"YouTube aç" has to work. So does "hesap makinesi aç", "not defteri aç",
"ayarları aç". The person saying it should not have to learn a command, and
J.A.R.V.I.S. should not have to guess an executable path.

**A catalogue, not arbitrary execution.** This looks like a limitation and is
the point. J.A.R.V.I.S. already has a terminal tool with its own allowlist and
risk classifier; if "aç" could launch any path it was handed, that allowlist
would be bypassable by asking nicely — and the asking can come from a web page
rather than from the owner. So a name resolves to a known entry or to nothing.

**The owner extends it, not the model.** Anything missing goes into
``~/.jarvis/uygulamalar.json``, which only the person at the keyboard edits.
That keeps "open anything I use" true without making "open anything at all"
true.

Matching is deliberately forgiving: Turkish folding (so "hesap makinesı" and
"HESAP MAKİNESİ" agree), aliases, and partial matches. Someone speaking to an
assistant should not have to spell.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from ..core.metin import katla

#: Hedef turleri:
#:   web     — tarayicida acilir
#:   windows — Windows programi (WSL'den interop ile)
#:   uri     — protokol adresi (ms-settings: gibi), kabuk cozer
WEB, WINDOWS, URI = "web", "windows", "uri"

#: Parca eslesmesi icin en kisa ad. Bunun altindakiler yalnizca birebir
#: eslesir; sebebi asagida bul() icinde.
_EN_KISA_PARCA = 3


@dataclass(frozen=True)
class Uygulama:
    ad: str
    tur: str
    hedef: str
    takma: tuple[str, ...] = field(default_factory=tuple)
    aciklama: str = ""

    def adlar(self) -> tuple[str, ...]:
        return (self.ad,) + self.takma


#: Varsayilan katalog. Turkce adlar once: kullanici "hesap makinesi" der,
#: "calc.exe" demez.
VARSAYILAN: tuple[Uygulama, ...] = (
    # ---- web ----
    Uygulama("YouTube", WEB, "https://www.youtube.com", ("youtube", "yutub", "video")),
    Uygulama("Gmail", WEB, "https://mail.google.com", ("gmail", "mail", "eposta", "e-posta")),
    Uygulama("WhatsApp", WEB, "https://web.whatsapp.com", ("whatsapp", "wp", "vatsap")),
    Uygulama("Google", WEB, "https://www.google.com", ("google", "gugıl")),
    Uygulama("Google Çeviri", WEB, "https://translate.google.com",
             ("çeviri", "translate", "tercüme")),
    Uygulama("Google Haritalar", WEB, "https://www.google.com/maps",
             ("harita", "haritalar", "maps")),
    Uygulama("Google Drive", WEB, "https://drive.google.com", ("drive", "sürücü")),
    Uygulama("GitHub", WEB, "https://github.com", ("github", "git")),
    Uygulama("ChatGPT", WEB, "https://chat.openai.com", ("chatgpt", "gpt")),
    Uygulama("X (Twitter)", WEB, "https://x.com", ("twitter", "x")),
    Uygulama("Instagram", WEB, "https://www.instagram.com", ("instagram", "insta")),
    Uygulama("LinkedIn", WEB, "https://www.linkedin.com", ("linkedin",)),
    Uygulama("Spotify", WEB, "https://open.spotify.com", ("spotify", "müzik")),
    Uygulama("Netflix", WEB, "https://www.netflix.com", ("netflix",)),
    Uygulama("Trendyol", WEB, "https://www.trendyol.com", ("trendyol",)),
    Uygulama("Hepsiburada", WEB, "https://www.hepsiburada.com", ("hepsiburada",)),
    Uygulama("N11", WEB, "https://www.n11.com", ("n11",)),
    Uygulama("Sahibinden", WEB, "https://www.sahibinden.com", ("sahibinden",)),
    Uygulama("DonanımHaber", WEB, "https://www.donanimhaber.com",
             ("donanımhaber", "donanim haber")),
    Uygulama("Ekşi Sözlük", WEB, "https://eksisozluk.com", ("ekşi", "eksi sözlük")),
    Uygulama("Wikipedia", WEB, "https://tr.wikipedia.org", ("wikipedia", "vikipedi")),

    # ---- Windows programlari ----
    Uygulama("Not Defteri", WINDOWS, "notepad.exe", ("not defteri", "notepad", "not")),
    Uygulama("Hesap Makinesi", WINDOWS, "calc.exe",
             ("hesap makinesi", "hesap makinası", "hesaplayıcı", "calc")),
    Uygulama("Paint", WINDOWS, "mspaint.exe", ("paint", "resim", "çizim")),
    Uygulama("Dosya Gezgini", WINDOWS, "explorer.exe",
             ("dosya gezgini", "gezgin", "explorer", "dosyalar")),
    Uygulama("Görev Yöneticisi", WINDOWS, "taskmgr.exe",
             ("görev yöneticisi", "taskmgr", "görev")),
    Uygulama("Denetim Masası", WINDOWS, "control.exe",
             ("denetim masası", "kontrol paneli", "control")),
    Uygulama("Komut İstemi", WINDOWS, "cmd.exe", ("komut istemi", "cmd", "konsol")),
    Uygulama("Kayıt Defteri", WINDOWS, "regedit.exe", ("kayıt defteri", "regedit")),
    Uygulama("Aygıt Yöneticisi", WINDOWS, "devmgmt.msc",
             ("aygıt yöneticisi", "device manager", "aygıt")),
    Uygulama("Disk Yönetimi", WINDOWS, "diskmgmt.msc", ("disk yönetimi", "diskmgmt")),
    Uygulama("Sistem Bilgisi", WINDOWS, "msinfo32.exe",
             ("sistem bilgisi", "msinfo", "sistem özellikleri")),
    Uygulama("Ekran Alıntısı", WINDOWS, "snippingtool.exe",
             ("ekran alıntısı", "ekran görüntüsü", "snipping")),

    # ---- Windows protokolleri ----
    Uygulama("Ayarlar", URI, "ms-settings:", ("ayarlar", "windows ayarları", "settings")),
    Uygulama("Bluetooth Ayarları", URI, "ms-settings:bluetooth", ("bluetooth",)),
    Uygulama("Ses Ayarları", URI, "ms-settings:sound", ("ses ayarları",)),
    Uygulama("Ağ Ayarları", URI, "ms-settings:network", ("ağ ayarları", "ağ", "wifi")),
    Uygulama("Windows Update", URI, "ms-settings:windowsupdate",
             ("windows update", "güncelleme", "güncelleştirme")),
    Uygulama("Uygulamalar ve Özellikler", URI, "ms-settings:appsfeatures",
             ("yüklü uygulamalar", "program ekle kaldır", "uygulamalar")),
)


def kullanici_katalogu(data_dir: Path | str = "~/.jarvis") -> Path:
    return Path(data_dir).expanduser() / "uygulamalar.json"


def _kullanici_girdileri(yol: Path) -> list[Uygulama]:
    """Read the owner's own additions. A broken file must not cost the rest."""
    if not yol.is_file():
        return []
    try:
        ham = json.loads(yol.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return []
    if not isinstance(ham, list):
        return []

    cikti = []
    for girdi in ham:
        if not isinstance(girdi, dict):
            continue
        ad = str(girdi.get("ad", "")).strip()
        hedef = str(girdi.get("hedef", "")).strip()
        tur = str(girdi.get("tur", "")).strip().lower()
        if not ad or not hedef or tur not in (WEB, WINDOWS, URI):
            continue
        takma = girdi.get("takma") or []
        if isinstance(takma, str):
            takma = [takma]
        cikti.append(Uygulama(ad, tur, hedef,
                              tuple(str(t) for t in takma if str(t).strip()),
                              str(girdi.get("aciklama", ""))))
    return cikti


def katalog(data_dir: Path | str = "~/.jarvis") -> list[Uygulama]:
    """The default catalogue plus the owner's own entries.

    User entries come last so a name they define wins over a built-in with the
    same name — their machine, their meaning of the word.
    """
    return list(VARSAYILAN) + _kullanici_girdileri(kullanici_katalogu(data_dir))


def bul(istek: str, data_dir: Path | str = "~/.jarvis") -> Uygulama | None:
    """Resolve a spoken name to an entry, or None.

    Three passes, strictest first: exact, prefix, then substring. Ordering
    matters — "not" must reach "Not Defteri" and not stop at some entry that
    merely contains the letters.
    """
    aranan = katla((istek or "").strip())
    if not aranan:
        return None
    liste = katalog(data_dir)

    # Kullanici girdileri sonda; ayni adda cakisma olursa onlarinki kazansin.
    for asama in (0, 1, 2):
        for uyg in reversed(liste):
            for ad in uyg.adlar():
                k = katla(ad)
                if asama == 0 and k == aranan:
                    return uyg
                # Kisa adlar YALNIZCA birebir eslesir. "x" (Twitter) gibi tek
                # harflik bir takma ad, parca eslesmesine birakildiginda
                # icinde x gecen her istegi yakaliyordu — "zzqqxx" Twitter'i
                # aciyordu. Uc harf, gercek bir isim ile rastlanti arasindaki
                # pratik sinir.
                if len(k) < _EN_KISA_PARCA or len(aranan) < _EN_KISA_PARCA:
                    continue
                if asama == 1 and (k.startswith(aranan) or aranan.startswith(k)):
                    return uyg
                if asama == 2 and (aranan in k or k in aranan):
                    return uyg
    return None


def benzerler(istek: str, adet: int = 5, data_dir: Path | str = "~/.jarvis") -> list[str]:
    """Names sharing a word with the request — for "did you mean" replies."""
    parcalar = {p for p in katla(istek or "").split() if len(p) >= 3}
    if not parcalar:
        return [u.ad for u in katalog(data_dir)[:adet]]
    liste = katalog(data_dir)
    puanli = []
    for uyg in liste:
        metin = katla(" ".join(uyg.adlar()))
        puan = sum(1 for p in parcalar if p in metin)
        if puan:
            puanli.append((puan, uyg.ad))
    puanli.sort(reverse=True)
    if puanli:
        return [ad for _, ad in puanli[:adet]]
    # Hicbir kelime tutmadi. Bos liste donmek "yardim edemem" demektir;
    # birkac ornek en azindan ne tur seyler acabildigini gosteriyor.
    return [u.ad for u in liste[:adet]]
