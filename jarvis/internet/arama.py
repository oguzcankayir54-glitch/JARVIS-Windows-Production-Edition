"""Web search, behind a provider interface.

The interface exists for a reason this project has already run into twice:
every free search endpoint eventually decides you are a robot. DuckDuckGo
answers a datacentre address with a CAPTCHA page — HTTP 200, fourteen
kilobytes, zero results. A scraper that only looks for result markup reports
"aradım, bir şey bulamadım", which is a lie: it never got to search.

So two rules shape this module.

**Providers are swappable.** DuckDuckGo needs no key and is the default. When
it starts refusing — or the owner wants better results — a key-based provider
takes over from ``.env`` without touching any calling code. Same shape as the
LLM, TTS, STT and vision layers.

**A refusal is never silent.** The challenge page is detected explicitly and
raises a message that says what happened and what to do about it, because
"engellendi" and "sonuç yok" need completely different reactions from the
person reading them.
"""
from __future__ import annotations

import html as html_mod
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Protocol

from .guvenlik import alan_adi

#: Bir aramada donecek en fazla sonuc. Modelin baglami sinirli ve on tane
#: baslik asil soruyu bastiriyor.
EN_FAZLA_SONUC = 10

#: Arama sayfasi icin ust sinir. Bunu asan bir cevap arama sonucu degildir.
EN_FAZLA_BAYT = 2 * 1024 * 1024

ZAMAN_ASIMI = 20.0

#: Gercek bir tarayici gibi gorunmek gerekiyor: arama motorlari varsayilan
#: Python User-Agent'ini dogrudan reddediyor.
_TARAYICI = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


class AramaError(RuntimeError):
    """Raised with a Turkish message the tool layer can hand straight back."""


@dataclass
class Sonuc:
    """One search hit."""

    baslik: str
    url: str
    ozet: str

    @property
    def kaynak(self) -> str:
        return alan_adi(self.url)

    def as_dict(self) -> dict[str, str]:
        return {"baslik": self.baslik, "url": self.url,
                "ozet": self.ozet, "kaynak": self.kaynak}


class AramaSaglayici(Protocol):
    name: str
    available: bool

    def ara(self, sorgu: str, adet: int = 5) -> list[Sonuc]:
        ...


class NullArama:
    """Used when search is switched off: the tool says why instead of failing."""

    name = "yok"
    available = False

    def __init__(self, reason: str = "") -> None:
        self.reason = reason or "Web araması kapalı (JARVIS_WEB_ENABLED=false)."

    def ara(self, sorgu: str, adet: int = 5) -> list[Sonuc]:
        raise AramaError(self.reason)


def _getir(url: str, veri: bytes | None = None) -> str:
    istek = urllib.request.Request(url, data=veri, headers={
        "User-Agent": _TARAYICI,
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
    })
    try:
        with urllib.request.urlopen(istek, timeout=ZAMAN_ASIMI) as cevap:
            ham = cevap.read(EN_FAZLA_BAYT + 1)
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise AramaError(
                "Arama motoru çok fazla istek geldiğini söylüyor (429). "
                "Birkaç dakika bekleyin."
            ) from exc
        raise AramaError(f"Arama başarısız (HTTP {exc.code}).") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise AramaError(f"Arama motoruna ulaşılamadı: {exc}") from exc

    if len(ham) > EN_FAZLA_BAYT:
        raise AramaError("Arama cevabı beklenmedik biçimde büyük.")
    return ham.decode("utf-8", errors="replace")


#: Bot koruma sayfasinin imzalari. Bunlar HTTP 200 ile geliyor, o yuzden
#: durum koduna bakmak yetmiyor.
_ENGEL_ISARETLERI = (
    "bots use duckduckgo",
    "complete the following challenge",
    "confirm this search was made by a human",
    "unusual traffic",
    "are you a robot",
    "captcha",
    "cf-challenge",
    "enable javascript and cookies to continue",
)


def engellendi_mi(govde: str) -> bool:
    """Whether this page is a bot challenge rather than a result list."""
    kucuk = govde.lower()
    return any(isaret in kucuk for isaret in _ENGEL_ISARETLERI)


def _temizle(ham: str) -> str:
    """HTML parçasını okunur düz metne indir."""
    metin = re.sub(r"<[^>]+>", "", ham)
    return " ".join(html_mod.unescape(metin).split())


class DuckDuckGoArama:
    """Key-free search by reading DuckDuckGo's HTML endpoint.

    The lite endpoint is used because its markup is small and stable. It is
    still scraping: it can break when DuckDuckGo changes the page, and it can
    be refused outright. Both cases are reported as themselves rather than as
    an empty result list.
    """

    name = "duckduckgo"
    ADRES = "https://html.duckduckgo.com/html/"

    def __init__(self) -> None:
        self.available = True

    def ara(self, sorgu: str, adet: int = 5) -> list[Sonuc]:
        sorgu = (sorgu or "").strip()
        if not sorgu:
            raise AramaError("Boş sorgu ile arama yapılamaz.")
        adet = max(1, min(int(adet), EN_FAZLA_SONUC))

        veri = urllib.parse.urlencode({"q": sorgu, "kl": "tr-tr"}).encode("utf-8")
        govde = _getir(self.ADRES, veri)

        if engellendi_mi(govde):
            raise AramaError(
                "DuckDuckGo bu isteği robot sanıp doğrulama istedi; arama "
                "yapılamadı.\n"
                "  · Birkaç dakika sonra tekrar deneyin, ya da\n"
                "  · .env içine bir arama anahtarı ekleyin "
                "(JARVIS_BRAVE_API_KEY) — engellenmez."
            )

        sonuclar = self._ayikla(govde, adet)
        if not sonuclar and "result" not in govde:
            # Ne sonuc ne de sonuc isareti var: sayfa yapisi degismis olabilir.
            raise AramaError(
                "Arama sayfası beklenen biçimde değil — DuckDuckGo düzenini "
                "değiştirmiş olabilir. Anahtarlı bir sağlayıcı daha güvenilir: "
                "JARVIS_BRAVE_API_KEY"
            )
        return sonuclar

    @staticmethod
    def _ayikla(govde: str, adet: int) -> list[Sonuc]:
        sonuclar: list[Sonuc] = []
        # Baglanti + baslik, ardindan (varsa) ozet.
        kalip = re.compile(
            r'<a[^>]+class="[^"]*result__a[^"]*"[^>]*href="(?P<url>[^"]+)"[^>]*>'
            r'(?P<baslik>.*?)</a>(?P<kalan>.*?)(?=<a[^>]+class="[^"]*result__a|\Z)',
            re.S,
        )
        for eslesme in kalip.finditer(govde):
            url = html_mod.unescape(eslesme.group("url"))
            url = _ddg_yonlendirmesini_coz(url)
            if not url.startswith(("http://", "https://")):
                continue
            baslik = _temizle(eslesme.group("baslik"))
            ozet = ""
            ozet_eslesme = re.search(
                r'class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>',
                eslesme.group("kalan"), re.S)
            if ozet_eslesme:
                ozet = _temizle(ozet_eslesme.group(1))
            if baslik:
                sonuclar.append(Sonuc(baslik=baslik, url=url, ozet=ozet))
            if len(sonuclar) >= adet:
                break
        return sonuclar


def _ddg_yonlendirmesini_coz(url: str) -> str:
    """DuckDuckGo wraps results in its own redirect; unwrap to the real target.

    Left wrapped, every result would look as if it came from duckduckgo.com —
    and the citation the model prints would point at the wrapper instead of
    the source.
    """
    if "duckduckgo.com/l/" not in url and not url.startswith("//duckduckgo.com/l/"):
        return url
    parca = urllib.parse.urlsplit(url if url.startswith("http") else "https:" + url)
    hedef = urllib.parse.parse_qs(parca.query).get("uddg", [""])[0]
    return hedef or url


class BraveArama:
    """Brave Search API — needs a key, does not get blocked.

    Offered because the key-free path is fragile by nature. The free tier is
    enough for a technician's occasional lookup.
    """

    name = "brave"
    ADRES = "https://api.search.brave.com/res/v1/web/search"

    def __init__(self, api_key: str) -> None:
        self._key = api_key
        self.available = bool(api_key)

    def ara(self, sorgu: str, adet: int = 5) -> list[Sonuc]:
        sorgu = (sorgu or "").strip()
        if not sorgu:
            raise AramaError("Boş sorgu ile arama yapılamaz.")
        adet = max(1, min(int(adet), EN_FAZLA_SONUC))

        url = f"{self.ADRES}?{urllib.parse.urlencode({'q': sorgu, 'count': adet})}"
        istek = urllib.request.Request(url, headers={
            "Accept": "application/json",
            "X-Subscription-Token": self._key,
            "User-Agent": _TARAYICI,
        })
        try:
            with urllib.request.urlopen(istek, timeout=ZAMAN_ASIMI) as cevap:
                govde = json.loads(cevap.read(EN_FAZLA_BAYT).decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise AramaError(
                    "Brave arama anahtarı reddedildi (JARVIS_BRAVE_API_KEY)."
                ) from exc
            raise AramaError(f"Brave araması başarısız (HTTP {exc.code}).") from exc
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            raise AramaError(f"Brave'e ulaşılamadı: {exc}") from exc

        return [
            Sonuc(baslik=_temizle(g.get("title", "")),
                  url=g.get("url", ""),
                  ozet=_temizle(g.get("description", "")))
            for g in (govde.get("web", {}) or {}).get("results", [])[:adet]
            if g.get("url")
        ]


def build_arama(enabled: bool = True, brave_key: str = "") -> AramaSaglayici:
    """Pick a provider: a key beats scraping, and off beats both."""
    if not enabled:
        return NullArama()
    if brave_key.strip():
        return BraveArama(brave_key.strip())
    return DuckDuckGoArama()
