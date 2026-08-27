"""Fetching one page and reducing it to readable text.

Two things make this more than ``urlopen``.

**Every redirect hop is checked.** urllib follows redirects on its own, so a
URL that resolves to a public address on the first request can bounce to
``127.0.0.1`` and be fetched anyway. Checking only what the caller passed in
would wave that through. The handler below validates each hop as it happens.

**What comes back is untrusted text.** A page is written by a stranger and may
contain sentences shaped like orders. Nothing here interprets it; the tool
layer labels it as data, the same way retrieved documents and stored facts
are labelled.
"""
from __future__ import annotations

import html as html_mod
import re
import urllib.error
import urllib.request

from .guvenlik import AdresReddedildi, url_denetle

#: Indirilecek en fazla bayt. Bir haber sayfasi 200-500 KB; bunun ustu
#: genelde bir dosya indirmesidir ve modele hicbir sey katmaz.
EN_FAZLA_BAYT = 3 * 1024 * 1024

#: Modele verilecek metnin ust siniri. Tam sayfa baglami doldurup asil
#: soruyu bastiriyor.
EN_FAZLA_KARAKTER = 12_000

ZAMAN_ASIMI = 25.0

_TARAYICI = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


class GetirError(RuntimeError):
    """Raised with a Turkish message the tool layer can hand straight back."""


class _DenetliYonlendirme(urllib.request.HTTPRedirectHandler):
    """Validate the target of every redirect before following it."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        try:
            url_denetle(newurl)
        except AdresReddedildi as exc:
            raise urllib.error.HTTPError(
                newurl, code, f"Yönlendirme reddedildi: {exc}", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _acici() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(_DenetliYonlendirme())


#: Icerigi metin sayilmayan etiketler; birakilirsa sayfanin yarisi JavaScript olur.
_ATILACAK = re.compile(
    r"<(script|style|noscript|template|svg|iframe)\b.*?</\1\s*>", re.S | re.I)

#: Blok etiketleri satir sonuna cevrilmezse butun sayfa tek satir oluyor.
_BLOK = re.compile(
    r"</?(p|div|br|li|tr|h[1-6]|section|article|header|footer|blockquote)\b[^>]*>",
    re.I)


def metne_cevir(govde: str) -> str:
    """Reduce an HTML document to the text a person would read."""
    metin = _ATILACAK.sub(" ", govde)
    metin = _BLOK.sub("\n", metin)
    metin = re.sub(r"<[^>]+>", " ", metin)
    metin = html_mod.unescape(metin)
    # Satirlari ayri ayri sadelestir: sayfa yapisi kalsin ama bosluk yigilmasin.
    satirlar = [" ".join(s.split()) for s in metin.splitlines()]
    return "\n".join(s for s in satirlar if s)


def baslik_bul(govde: str) -> str:
    eslesme = re.search(r"<title[^>]*>(.*?)</title>", govde, re.S | re.I)
    return " ".join(html_mod.unescape(eslesme.group(1)).split()) if eslesme else ""


def sayfa_getir(url: str, en_fazla_karakter: int = EN_FAZLA_KARAKTER) -> dict[str, object]:
    """Fetch one page and return its title and readable text.

    Raises :class:`GetirError` with a readable reason for every failure —
    including a refused address, which is a policy decision rather than a
    network error and should not look like one.
    """
    try:
        guvenli = url_denetle(url)
    except AdresReddedildi as exc:
        raise GetirError(str(exc)) from exc

    istek = urllib.request.Request(guvenli, headers={
        "User-Agent": _TARAYICI,
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
    })
    try:
        with _acici().open(istek, timeout=ZAMAN_ASIMI) as cevap:
            tur = (cevap.headers.get("Content-Type") or "").lower()
            ham = cevap.read(EN_FAZLA_BAYT + 1)
            son_url = cevap.geturl()
    except urllib.error.HTTPError as exc:
        if "Yönlendirme reddedildi" in str(exc.reason or ""):
            raise GetirError(str(exc.reason)) from exc
        raise GetirError(f"Sayfa alınamadı (HTTP {exc.code}).") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise GetirError(f"Sayfaya ulaşılamadı: {exc}") from exc

    if len(ham) > EN_FAZLA_BAYT:
        raise GetirError(f"Sayfa çok büyük ({EN_FAZLA_BAYT // (1024*1024)} MB sınırı).")
    if tur and not any(t in tur for t in ("text/", "html", "xml", "json")):
        raise GetirError(f"Bu bir metin sayfası değil ({tur.split(';')[0]}).")

    govde = ham.decode("utf-8", errors="replace")
    metin = metne_cevir(govde)
    kirpildi = len(metin) > en_fazla_karakter
    return {
        "url": son_url,
        "baslik": baslik_bul(govde),
        "metin": metin[:en_fazla_karakter],
        "kirpildi": kirpildi,
        "uzunluk": len(metin),
    }
