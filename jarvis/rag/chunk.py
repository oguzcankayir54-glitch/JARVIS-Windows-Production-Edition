"""Splitting a file into pieces worth retrieving.

Chunking decides the ceiling on retrieval quality. Everything downstream —
embeddings, ranking, what the model finally reads — works on whatever comes
out of here, and no amount of clever search recovers a chunk that cut a
function in half.

Three strategies, chosen by what the file actually is:

* **Python** is parsed with :mod:`ast` when it parses, so a chunk is a whole
  function or method with its decorators and docstring attached. Line windows
  would split "how ElevenLabs is wired" across two pieces and retrieve
  neither well.
* **Markdown** follows its headings, because a heading is the author's own
  statement of where one subject ends.
* **Everything else** falls back to paragraph packing with a small overlap.

Every chunk carries a **breadcrumb** — the file path plus the enclosing symbol
or heading — and the breadcrumb is embedded *with* the text. This is the
single cheapest win in the whole pipeline: a question about "ElevenLabs voice
setup" matches `jarvis/voice/tts.py · ElevenLabsTTS.stream` even when the body
never repeats those words together.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

#: Hedef parça boyutu (karakter). Küçük parçalar daha isabetli eşleşir ama
#: bağlamı kaybeder; büyük parçalar tersi. 1100 civarı, bir Python fonksiyonu
#: veya bir başlık altındaki bir bölüm için pratikte iyi oturuyor.
HEDEF_KARAKTER = 1100

#: Bunu aşan tek bir parça pencerelere bölünür. Çok uzun bir metnin
#: gömülmesi ortalamaya dönüşür ve hiçbir şeye tam benzemez.
EN_FAZLA_KARAKTER = 2400

#: Pencereye bölerken kaç satır üst üste binsin. Sınıra denk gelen bir cümle
#: veya koşul iki parçanın da içinde kalsın diye.
ORTUSME_SATIR = 3

#: Bundan kısa parçalar tek başına anlam taşımıyor (tek satırlık import,
#: kapanış parantezi); bir öncekine eklenirler.
EN_KISA_KARAKTER = 60


@dataclass
class Chunk:
    """One retrievable piece of a file."""

    #: Kullanıcıya ve modele gösterilen asıl metin.
    body: str
    #: Nerede olduğu: "yol · Sınıf.metot" veya "yol · Başlık > Alt başlık".
    baslik: str
    ilk_satir: int
    son_satir: int

    @property
    def text(self) -> str:
        """What actually gets embedded and indexed: breadcrumb + body.

        The breadcrumb is part of the searchable text on purpose — it carries
        the file path and symbol name, which are often the only place a
        question's keywords appear literally.
        """
        return f"{self.baslik}\n\n{self.body}" if self.baslik else self.body

    def as_dict(self) -> dict[str, object]:
        return {"baslik": self.baslik, "metin": self.body,
                "ilk_satir": self.ilk_satir, "son_satir": self.son_satir}


# ---------------------------------------------------------------- yardımcılar

def _satirlar(metin: str) -> list[str]:
    return metin.splitlines()


def _kes(satirlar: list[str], ilk: int, son: int) -> str:
    """1-tabanlı, iki uçtan kapsayıcı satır aralığı."""
    return "\n".join(satirlar[ilk - 1:son]).strip("\n")


def _pencerele(satirlar: list[str], ilk: int, son: int, baslik: str) -> list[Chunk]:
    """Split an over-long span into overlapping line windows."""
    parcalar: list[Chunk] = []
    imlec = ilk
    while imlec <= son:
        uzunluk = 0
        bitis = imlec
        while bitis <= son and uzunluk < HEDEF_KARAKTER:
            uzunluk += len(satirlar[bitis - 1]) + 1
            bitis += 1
        bitis = min(bitis - 1, son)
        govde = _kes(satirlar, imlec, bitis)
        if govde.strip():
            ek = "" if imlec == ilk else f" (satır {imlec}–{bitis})"
            parcalar.append(Chunk(govde, baslik + ek, imlec, bitis))
        if bitis >= son:
            break
        imlec = max(bitis - ORTUSME_SATIR + 1, imlec + 1)
    return parcalar


def _birlestir(parcalar: list[Chunk]) -> list[Chunk]:
    """Fold pieces too short to stand alone into the one before them.

    Only ever merges two chunks that carry the *same* breadcrumb. A two-line
    method and the heading above it are short, but they are short pieces of
    different things: merging them across breadcrumbs throws away the symbol
    name, which is the most searchable part of the chunk. This is for stray
    fragments — a closing bracket, a lone import — inside one span.
    """
    cikti: list[Chunk] = []
    for p in parcalar:
        if (cikti and cikti[-1].baslik == p.baslik
                and len(p.body) < EN_KISA_KARAKTER
                and len(cikti[-1].body) + len(p.body) < EN_FAZLA_KARAKTER):
            onceki = cikti[-1]
            cikti[-1] = Chunk(
                body=onceki.body + "\n" + p.body,
                baslik=onceki.baslik,
                ilk_satir=onceki.ilk_satir,
                son_satir=p.son_satir,
            )
        else:
            cikti.append(p)
    return cikti


# ------------------------------------------------------------------- Python

def _ad_zinciri(dugum: ast.AST, ust: str = "") -> str:
    ad = getattr(dugum, "name", "")
    return f"{ust}.{ad}" if ust and ad else (ad or ust)


def _baslangic(dugum: ast.AST) -> int:
    """First line of a definition, decorators included.

    ``node.lineno`` points at the ``def``; a decorator sitting above it is
    part of what the definition means (``@property``, ``@staticmethod``) and
    dropping it out of the chunk loses that.
    """
    satirlar = [getattr(dugum, "lineno", 1)]
    for suslu in getattr(dugum, "decorator_list", []) or []:
        satirlar.append(getattr(suslu, "lineno", satirlar[0]))
    return min(satirlar)


_TANIM = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def python_parcala(metin: str, yol: str) -> list[Chunk] | None:
    """Chunk Python along its own structure, or None if it does not parse.

    Returning None rather than raising lets the caller fall back: a file that
    is being edited, or written for a newer syntax than this interpreter, is
    still worth indexing as plain text.
    """
    try:
        agac = ast.parse(metin)
    except (SyntaxError, ValueError, RecursionError):
        return None

    satirlar = _satirlar(metin)
    if not satirlar:
        return []
    parcalar: list[Chunk] = []

    def ekle(ilk: int, son: int, ad: str) -> None:
        govde = _kes(satirlar, ilk, son)
        if not govde.strip():
            return
        baslik = f"{yol} · {ad}" if ad else yol
        if len(govde) > EN_FAZLA_KARAKTER:
            parcalar.extend(_pencerele(satirlar, ilk, son, baslik))
        else:
            parcalar.append(Chunk(govde, baslik, ilk, son))

    def gez(govde_dugumleri: list[ast.stmt], ust: str, sinir: int) -> None:
        """Walk one body, emitting a chunk per definition and per gap between."""
        tanimlar = [d for d in govde_dugumleri if isinstance(d, _TANIM)]
        imlec = sinir
        for dugum in tanimlar:
            basi = _baslangic(dugum)
            sonu = getattr(dugum, "end_lineno", basi) or basi
            # Tanımlar arasında kalan kod (import'lar, sabitler, modül
            # gövdesi) da aranabilir olmalı — atlanırsa dosyanın yarısı
            # indekse hiç girmez.
            if basi > imlec:
                ekle(imlec, basi - 1, ust)
            ad = _ad_zinciri(dugum, ust)
            if isinstance(dugum, ast.ClassDef):
                ic_tanimlar = [d for d in dugum.body if isinstance(d, _TANIM)]
                if ic_tanimlar:
                    # Sınıf başlığı + docstring + alan tanımları ayrı parça:
                    # "bu sınıf ne işe yarar" sorusunun cevabı orada.
                    gez(dugum.body, ad, basi)
                else:
                    ekle(basi, sonu, ad)
            else:
                ekle(basi, sonu, ad)
            imlec = sonu + 1
        if imlec <= len(satirlar) and ust == "":
            ekle(imlec, len(satirlar), ust)

    gez(agac.body, "", 1)
    return _birlestir([p for p in parcalar if p.body.strip()])


# ------------------------------------------------------------------ Markdown

_BASLIK = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")


def markdown_parcala(metin: str, yol: str) -> list[Chunk]:
    """Chunk Markdown at its headings, carrying the heading stack as context."""
    satirlar = _satirlar(metin)
    parcalar: list[Chunk] = []
    yigin: list[str] = []          # açık başlıklar, seviyeye göre
    bolum_ilk = 1
    kod_bloku = False

    def kapat(son: int, yol_izi: list[str]) -> None:
        if son < bolum_ilk:
            return
        govde = _kes(satirlar, bolum_ilk, son)
        if not govde.strip():
            return
        # Kendi metni olmayan bir başlık (hemen altında alt başlık gelen)
        # aranmaya değmez: içeriği yok, ve başlığın kendisi zaten alt
        # bölümlerin izinde duruyor. Sonuç listesinde yer kaplamasın.
        if not any(satir.strip() and not _BASLIK.match(satir)
                   for satir in govde.splitlines()):
            return
        iz = " > ".join(yol_izi)
        baslik = f"{yol} · {iz}" if iz else yol
        if len(govde) > EN_FAZLA_KARAKTER:
            parcalar.extend(_pencerele(satirlar, bolum_ilk, son, baslik))
        else:
            parcalar.append(Chunk(govde, baslik, bolum_ilk, son))

    for i, satir in enumerate(satirlar, start=1):
        # Kod bloğunun içindeki "# yorum" satırı başlık değildir.
        if satir.lstrip().startswith("```"):
            kod_bloku = not kod_bloku
            continue
        if kod_bloku:
            continue
        m = _BASLIK.match(satir)
        if not m:
            continue
        kapat(i - 1, list(yigin))
        seviye = len(m.group(1))
        del yigin[seviye - 1:]
        yigin.append(m.group(2).strip())
        bolum_ilk = i

    kapat(len(satirlar), list(yigin))
    return _birlestir([p for p in parcalar if p.body.strip()])


# --------------------------------------------------------------------- düz

def duz_parcala(metin: str, yol: str) -> list[Chunk]:
    """Paragraph packing for anything with no structure worth following."""
    satirlar = _satirlar(metin)
    if not satirlar:
        return []
    return _birlestir(_pencerele(satirlar, 1, len(satirlar), yol))


# --------------------------------------------------------------------- giriş

#: Uzantıya göre hangi bölücü. Bilinmeyen uzantı düz metin sayılır.
_PYTHON = {".py", ".pyi"}
_MARKDOWN = {".md", ".markdown", ".mdown"}


def parcala(metin: str, yol: str | Path) -> list[Chunk]:
    """Split one file's text into chunks, choosing the strategy by extension."""
    ad = str(yol)
    uzanti = Path(ad).suffix.lower()
    if not metin.strip():
        return []
    if uzanti in _PYTHON:
        yapisal = python_parcala(metin, ad)
        if yapisal is not None:
            return yapisal
    if uzanti in _MARKDOWN:
        return markdown_parcala(metin, ad)
    return duz_parcala(metin, ad)
