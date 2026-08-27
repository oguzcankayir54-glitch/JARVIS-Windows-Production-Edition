"""The knowledge base: what J.A.R.V.I.S. can look up, and how it finds it.

This is the R in RAG. It is deliberately **not** the memory store: memory
holds what is true about the owner and is pushed into every turn for free;
this holds documents and code, is far too large to push, and is therefore
*pulled* — searched only when a question needs it.

Three decisions shape the implementation.

**SQLite, not a vector database.** The roadmap once said Chroma. At this
scale that is the wrong trade: a personal knowledge base is thousands of
chunks, not millions, and brute-force cosine over a few thousand vectors takes
milliseconds. In exchange the whole thing stays in one file next to the rest
of memory, backs up by copying, and adds no service to keep running.

**Hybrid retrieval, not vectors alone.** Pure semantic search is very good at
"how did we wire up the voice system" and quietly terrible at
``libcublas.so.12`` or ``ELEVENLABS_API_KEY`` — an exact identifier is not a
concept, and its embedding sits near every other identifier. Keyword search is
the mirror image. So both run, and their rankings are fused with Reciprocal
Rank Fusion: each result scores ``1/(k + rank)`` from each retriever. RRF
needs no score calibration between two systems whose numbers mean different
things, which is exactly the situation here.

**Secrets are never indexed.** The point of this feature is that the owner
points it at a project directory — and that directory contains ``.env`` with
a live API key. An indexed secret is a secret that can be retrieved into an
answer, and answers may later be routed to a cloud model. The same blocklist
that guards the file tools guards the indexer, and it is checked per file.
"""
from __future__ import annotations

import hashlib
import sqlite3
import struct
import threading
import time
from functools import wraps
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from ..core.metin import katla, kelimeler
from ..tools.file_tools import is_secret_path
from .chunk import Chunk, parcala
from .embed import EmbedError, Embedder, NullEmbedder

#: RRF sabiti. Literatürdeki 60 değeri; tek başına ilk sırada olmayı değil,
#: iki listede birden üst sıralarda olmayı ödüllendirir.
RRF_K = 60

#: Her arayıcıdan füzyona kaç aday girsin. Nihai sonuç sayısından yüksek:
#: yalnızca birinde geçen ama çok isabetli bir sonuç elenmesin.
ADAY_SAYISI = 40

#: Vektör aramasının alt eşiği. Eşik olmadan anlam araması **her zaman** bir
#: şey döndürür: en yakın komşu, hiçbir ilgisi olmasa bile. Model o metni
#: alır, kaynağıyla birlikte alıntılar ve emin görünür — RAG'ın kendinden
#: emin saçmalama biçimi tam olarak budur.
#:
#: Değer "ilgili" eşiği değil, "açıkça ilgisiz" eşiği. Modelden modele
#: taban benzerlik değiştiği için ilgiliyi ayırmayı tek bir sayıya
#: bırakmıyoruz; onu araç açıklamasındaki "karşılamıyorsa söyle" talimatı
#: üstleniyor. Buradaki eşik yalnızca dik ve zıt vektörleri eliyor.
EN_AZ_BENZERLIK = 0.2

#: İndekslenecek en büyük dosya. Bunun üstü genelde günlük dosyası veya
#: üretilmiş çıktı — arandığında işe yaramaz, indeksi şişirir.
EN_FAZLA_DOSYA_BAYT = 1_000_000

#: Metin sayılan uzantılar. Beyaz liste, kara liste değil: bilinmeyen bir
#: uzantının ikili olma ihtimali metin olmasından yüksek.
METIN_UZANTILARI = frozenset({
    ".py", ".pyi", ".md", ".markdown", ".mdown", ".txt", ".rst",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf",
    ".html", ".htm", ".css", ".js", ".ts", ".jsx", ".tsx",
    ".sh", ".bash", ".zsh", ".ps1", ".bat", ".sql", ".csv",
    ".c", ".h", ".cpp", ".hpp", ".java", ".go", ".rs", ".rb", ".php",
})

#: Uzantısız ama metin olduğu bilinen dosyalar.
METIN_ADLARI = frozenset({
    "readme", "license", "licence", "makefile", "dockerfile",
    "changelog", "authors", "contributing", "notes",
})

#: Hiç girilmeyen dizinler. Bunlar üretilmiş veya dışarıdan gelen içerik;
#: indekslemek hem yavaş hem sonuçları çöple doldurur.
ATLANAN_DIZINLER = frozenset({
    ".git", ".hg", ".svn", "__pycache__", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", "node_modules", ".venv", "venv", "env", ".env.d",
    "dist", "build", ".idea", ".vscode", ".cache", "site-packages",
    ".tox", ".eggs", "htmlcov", ".next", "target",
})


class RagError(RuntimeError):
    """Raised with a Turkish message the CLI and tool layer can pass through."""


@dataclass
class Hit:
    """One retrieved chunk, with enough context to be quoted and checked."""

    yol: str
    baslik: str
    metin: str
    ilk_satir: int
    son_satir: int
    puan: float
    #: "anlam", "kelime" veya "anlam+kelime" — hangi arayıcı bulmuş.
    neden: str

    @property
    def kaynak(self) -> str:
        """Citable location: path with the line range, the way an editor shows it."""
        if self.ilk_satir:
            return f"{self.yol}:{self.ilk_satir}-{self.son_satir}"
        return self.yol

    def as_dict(self) -> dict[str, object]:
        return {"kaynak": self.kaynak, "baslik": self.baslik,
                "metin": self.metin, "puan": round(self.puan, 4),
                "neden": self.neden}


#: index_text'in ne yaptığı. Çağıranın "değişti mi" diye tekrar sorgu
#: atmasına gerek kalmasın diye dönülüyor.
YENI = "yeni"
GUNCELLENDI = "guncellendi"
DEGISMEDI = "degismedi"
BOS = "bos"


@dataclass
class IndexResult:
    """The outcome of indexing one document."""

    durum: str
    parca: int = 0
    gomulen: int = 0
    #: Gömme denendi ve olmadıysa nedeni. Sessizce kelime aramasına düşmek,
    #: kullanıcıya çalıştığını sandırır — bu yüzden yukarı taşınıyor.
    gomme_hatasi: str = ""


@dataclass
class IndexReport:
    """What one indexing run actually did."""

    eklenen: int = 0
    guncellenen: int = 0
    degismeyen: int = 0
    silinen: int = 0
    atlanan: int = 0
    #: Yeni yazılan parça sayısı (değişmeyen belgeler sayılmaz).
    parca: int = 0
    gomulen: int = 0
    #: Hiç aday olmayan dosyalar — resim, ikili, üretilmiş içerik. Atlanan
    #: değiller: indekslenmeleri hiç beklenmiyordu, sayıyı şişirmesinler.
    aday_disi: int = 0
    sure: float = 0.0
    #: Atlama sebepleri, ör. {"gizli": 2, "büyük": 1}. Sessizce atlamamak için.
    sebepler: dict[str, int] = field(default_factory=dict)
    #: Gömme yapılamadıysa nedeni — indeks yine kurulur, arama kelimeye düşer.
    gomme_notu: str = ""

    def ozet(self) -> str:
        return (f"{self.eklenen} yeni · {self.guncellenen} güncellendi · "
                f"{self.degismeyen} değişmedi · {self.silinen} silindi · "
                f"{self.atlanan} atlandı · "
                f"{self.parca} yeni parça · {self.sure:.1f} sn")


_SEMA = """
CREATE TABLE IF NOT EXISTS belgeler (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    yol          TEXT NOT NULL UNIQUE,
    tur          TEXT NOT NULL DEFAULT 'belge',
    imza         TEXT NOT NULL,
    boyut        INTEGER NOT NULL DEFAULT 0,
    parca_sayisi INTEGER NOT NULL DEFAULT 0,
    eklendi_ts   REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS parcalar (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    belge_id  INTEGER NOT NULL REFERENCES belgeler(id) ON DELETE CASCADE,
    sira      INTEGER NOT NULL,
    baslik    TEXT NOT NULL DEFAULT '',
    metin     TEXT NOT NULL,
    ilk_satir INTEGER NOT NULL DEFAULT 0,
    son_satir INTEGER NOT NULL DEFAULT 0,
    vektor    BLOB,
    boyut     INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_parca_belge ON parcalar(belge_id);

CREATE VIRTUAL TABLE IF NOT EXISTS parca_fts
    USING fts5(katlanmis, parca_id UNINDEXED, tokenize='unicode61');
"""


def _kilitli(func):
    """Serialise public SQLite operations, including background re-indexing."""
    @wraps(func)
    def sarici(self, *args, **kwargs):
        with self._kilit:
            return func(self, *args, **kwargs)
    return sarici


def _imza(veri: str) -> str:
    return hashlib.sha256(veri.encode("utf-8")).hexdigest()[:32]


def _paketle(vektor: list[float]) -> bytes:
    return struct.pack(f"<{len(vektor)}f", *vektor)


def _cozumle(ham: bytes) -> list[float]:
    return list(struct.unpack(f"<{len(ham) // 4}f", ham))


def metin_dosyasi_mi(yol: Path) -> bool:
    """Whether this path looks like something worth reading as text."""
    if yol.suffix.lower() in METIN_UZANTILARI:
        return True
    return not yol.suffix and yol.name.lower() in METIN_ADLARI


def _ikili_mi(ham: bytes) -> bool:
    """A NUL byte in the first block is the classic, and reliable, tell."""
    return b"\x00" in ham[:4096]


class KnowledgeBase:
    """Documents and code, chunked, indexed and searchable."""

    def __init__(self, db_path: Path | str = ":memory:", embedder: Embedder | None = None) -> None:
        self.db_path = str(db_path)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(_SEMA)
        self._conn.commit()
        self.embedder: Embedder = embedder if embedder is not None else NullEmbedder()
        # Panel arka planda senkronlarken ajan aynı tabanda arama yapabilir.
        # RLock gerekli: index_path -> index_file -> index_text iç içe girer.
        self._kilit = threading.RLock()
        # Vektörler her sorguda diskten okunursa arama I/O'ya bağlı kalıyor;
        # bir kez okunup bellekte tutuluyor ve her yazmada geçersizleşiyor.
        self._vektor_onbellek: tuple[list[int], list[list[float]]] | None = None

    @_kilitli
    def close(self) -> None:
        self._conn.close()

    # ---------------- yazma ----------------

    def _onbellegi_bosalt(self) -> None:
        self._vektor_onbellek = None

    @_kilitli
    def forget_document(self, yol: str) -> bool:
        """Remove a document and everything indexed from it."""
        satir = self._conn.execute(
            "SELECT id FROM belgeler WHERE yol = ?", (str(yol),)).fetchone()
        if satir is None:
            return False
        self._parcalari_sil(int(satir["id"]))
        self._conn.execute("DELETE FROM belgeler WHERE id = ?", (satir["id"],))
        self._conn.commit()
        self._onbellegi_bosalt()
        return True

    def _parcalari_sil(self, belge_id: int) -> None:
        # FTS5 sanal tablosu yabancı anahtar zincirine katılmıyor; kendi
        # satırlarını elle temizlemezsek arama silinmiş metni bulmaya devam eder.
        idler = [r["id"] for r in self._conn.execute(
            "SELECT id FROM parcalar WHERE belge_id = ?", (belge_id,))]
        for pid in idler:
            self._conn.execute("DELETE FROM parca_fts WHERE parca_id = ?", (pid,))
        self._conn.execute("DELETE FROM parcalar WHERE belge_id = ?", (belge_id,))

    @_kilitli
    def clear(self) -> None:
        self._conn.execute("DELETE FROM parca_fts")
        self._conn.execute("DELETE FROM parcalar")
        self._conn.execute("DELETE FROM belgeler")
        self._conn.commit()
        self._onbellegi_bosalt()

    @_kilitli
    def index_text(self, yol: str, metin: str, tur: str = "belge",
                   gom: bool = True) -> IndexResult:
        """Index one document given its text.

        Re-indexing unchanged text is a no-op — the content hash is compared
        first, so pointing the indexer at a project every morning costs a read
        per file rather than a re-embed of everything.
        """
        yol = str(yol)
        imza = _imza(metin)
        mevcut = self._conn.execute(
            "SELECT id, imza, parca_sayisi FROM belgeler WHERE yol = ?", (yol,)).fetchone()
        if mevcut is not None and mevcut["imza"] == imza:
            return IndexResult(DEGISMEDI, int(mevcut["parca_sayisi"]), 0)

        parcalar = parcala(metin, yol)
        if not parcalar:
            if mevcut is not None:
                self.forget_document(yol)
            return IndexResult(BOS, 0, 0)

        vektorler: list[list[float] | None] = [None] * len(parcalar)
        gomulen = 0
        gomme_hatasi = ""
        if gom and self.embedder.available:
            try:
                cikti = self.embedder.embed([p.text for p in parcalar])
                if len(cikti) == len(parcalar):
                    vektorler = list(cikti)
                    gomulen = len(cikti)
            except EmbedError as exc:
                # Gömme yoksa indeks yine kurulur ve kelime araması çalışır:
                # burada durmak, modeli olmayan kullanıcıya hiçbir şey vermez.
                # Ama sessizce düşmek de olmaz — sebep çağırana taşınıyor.
                gomme_hatasi = str(exc)

        if mevcut is not None:
            self._parcalari_sil(int(mevcut["id"]))
            belge_id = int(mevcut["id"])
            self._conn.execute(
                "UPDATE belgeler SET imza = ?, boyut = ?, tur = ?, parca_sayisi = ?, "
                "eklendi_ts = ? WHERE id = ?",
                (imza, len(metin), tur, len(parcalar), time.time(), belge_id))
        else:
            cur = self._conn.execute(
                "INSERT INTO belgeler (yol, tur, imza, boyut, parca_sayisi, eklendi_ts) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (yol, tur, imza, len(metin), len(parcalar), time.time()))
            belge_id = int(cur.lastrowid)

        for sira, (parca, vektor) in enumerate(zip(parcalar, vektorler)):
            self._parca_yaz(belge_id, sira, parca, vektor)

        self._conn.commit()
        self._onbellegi_bosalt()
        return IndexResult(GUNCELLENDI if mevcut is not None else YENI,
                           len(parcalar), gomulen, gomme_hatasi)

    def _parca_yaz(self, belge_id: int, sira: int, parca: Chunk,
                   vektor: list[float] | None) -> None:
        cur = self._conn.execute(
            "INSERT INTO parcalar (belge_id, sira, baslik, metin, ilk_satir, son_satir, "
            "vektor, boyut) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (belge_id, sira, parca.baslik, parca.body, parca.ilk_satir, parca.son_satir,
             _paketle(vektor) if vektor else None, len(vektor) if vektor else 0))
        parca_id = int(cur.lastrowid)
        # FTS'e katlanmış metin giriyor: unicode61 büyük/küçük harfi çözer ama
        # "ışık"/"isik" ayrımını çözmez, o Türkçeye özgü ve bizim işimiz.
        self._conn.execute(
            "INSERT INTO parca_fts (katlanmis, parca_id) VALUES (?, ?)",
            (katla(parca.text), parca_id))

    @_kilitli
    def index_file(self, yol: Path | str, gom: bool = True) -> IndexResult:
        """Index a single file, refusing the ones that must never be indexed."""
        p = Path(yol).expanduser().resolve()
        if is_secret_path(p):
            raise RagError(
                f"'{p.name}' gizli bilgi içerebilir; bilgi tabanına alınmıyor.")
        if not p.is_file():
            raise RagError(f"Dosya yok: {p}")
        ham = p.read_bytes()
        if len(ham) > EN_FAZLA_DOSYA_BAYT:
            raise RagError(f"Dosya çok büyük ({len(ham) // 1024} KB).")
        if _ikili_mi(ham):
            raise RagError(f"'{p.name}' ikili görünüyor; metin değil.")
        metin = ham.decode("utf-8", errors="replace")
        tur = "kod" if p.suffix.lower() in {".py", ".js", ".ts", ".sh", ".ps1"} else "belge"
        return self.index_text(str(p), metin, tur=tur, gom=gom)

    @_kilitli
    def index_path(self, kok: Path | str, gom: bool = True,
                   ilerleme=None, silinenleri_unut: bool = False) -> IndexReport:
        """Walk a directory (or take a single file) and index what belongs.

        Everything skipped is counted by reason. Silent skipping is how a
        knowledge base ends up quietly missing the one file that mattered.
        """
        basladi = time.time()
        rapor = IndexReport()
        kok_yolu = Path(kok).expanduser().resolve()
        if not kok_yolu.exists():
            # Tek dosyalık otomatik kaynak silindiyse hayalet sonucu bırakma.
            # Klasörün tamamı yoksa (ör. geçici bağlı disk) toplu silme yapma:
            # kaynak erişim hatası, kullanıcı verisini yeniden kurma sebebi değil.
            if silinenleri_unut and self.forget_document(str(kok_yolu)):
                rapor.silinen = 1
                rapor.sure = time.time() - basladi
                return rapor
            raise RagError(f"Yol yok: {kok_yolu}")

        if gom and not self.embedder.available:
            rapor.gomme_notu = getattr(self.embedder, "reason", "")

        adaylar = list(self._dosyalari_bul(kok_yolu, rapor))
        for dosya in adaylar:
            try:
                sonuc = self.index_file(dosya, gom=gom)
            except RagError as exc:
                rapor.atlanan += 1
                sebep = ("gizli" if "gizli" in str(exc)
                         else "büyük" if "büyük" in str(exc)
                         else "ikili" if "ikili" in str(exc)
                         else "okunamadı")
                rapor.sebepler[sebep] = rapor.sebepler.get(sebep, 0) + 1
                continue
            except OSError:
                rapor.atlanan += 1
                rapor.sebepler["okunamadı"] = rapor.sebepler.get("okunamadı", 0) + 1
                continue

            if sonuc.durum == BOS:
                rapor.atlanan += 1
                rapor.sebepler["boş"] = rapor.sebepler.get("boş", 0) + 1
                continue
            if sonuc.durum == YENI:
                rapor.eklenen += 1
            elif sonuc.durum == GUNCELLENDI:
                rapor.guncellenen += 1
            else:
                rapor.degismeyen += 1
                continue          # değişmeyen belge yeni parça yazmadı
            rapor.parca += sonuc.parca
            rapor.gomulen += sonuc.gomulen
            if sonuc.gomme_hatasi and not rapor.gomme_notu:
                rapor.gomme_notu = sonuc.gomme_hatasi
            if ilerleme is not None:
                ilerleme(str(dosya), sonuc.parca)

        if silinenleri_unut:
            guncel = {str(p.resolve()) for p in adaylar}
            for belge in self.documents(limit=1_000_000):
                belge_yolu = Path(str(belge["yol"]))
                try:
                    kapsamda = (belge_yolu == kok_yolu if kok_yolu.is_file()
                                else belge_yolu.is_relative_to(kok_yolu))
                except (OSError, ValueError):
                    kapsamda = False
                if kapsamda and str(belge_yolu) not in guncel:
                    if self.forget_document(str(belge_yolu)):
                        rapor.silinen += 1

        rapor.sure = time.time() - basladi
        return rapor

    def _dosyalari_bul(self, kok: Path, rapor: IndexReport) -> Iterable[Path]:
        if kok.is_file():
            yield kok
            return
        for yol in sorted(kok.rglob("*")):
            if yol.is_dir():
                continue
            if yol.is_symlink():
                rapor.atlanan += 1
                rapor.sebepler["bağlantı"] = rapor.sebepler.get("bağlantı", 0) + 1
                continue
            # Gizli dizinler ve üretilmiş içerik hiç açılmaz.
            if any(p in ATLANAN_DIZINLER or (p.startswith(".") and p not in {".", ".."})
                   for p in yol.relative_to(kok).parts[:-1]):
                continue
            if not metin_dosyasi_mi(yol):
                # Resim, ikili, üretilmiş çıktı: aday bile değil. "Atlandı"
                # saymak, bir depoda yüzlerce dosyalık anlamsız bir sayı üretir
                # ve gerçekten atlanan gizli dosyayı görünmez kılar.
                rapor.aday_disi += 1
                continue
            yield yol

    # ---------------- arama ----------------

    def _vektorleri_yukle(self) -> tuple[list[int], list[list[float]]]:
        if self._vektor_onbellek is not None:
            return self._vektor_onbellek
        idler: list[int] = []
        vektorler: list[list[float]] = []
        for satir in self._conn.execute(
                "SELECT id, vektor FROM parcalar WHERE vektor IS NOT NULL"):
            idler.append(int(satir["id"]))
            vektorler.append(_cozumle(satir["vektor"]))
        self._vektor_onbellek = (idler, vektorler)
        return self._vektor_onbellek

    def _anlam_ara(self, sorgu: str, limit: int) -> list[int]:
        """Rank chunk ids by cosine similarity to the query."""
        if not self.embedder.available:
            return []
        idler, vektorler = self._vektorleri_yukle()
        if not idler:
            return []
        try:
            sorgu_vektoru = self.embedder.embed([sorgu])[0]
        except EmbedError:
            return []
        if len(sorgu_vektoru) != len(vektorler[0]):
            # Gömme modeli değişmiş: eski vektörler yeni sorguyla kıyaslanamaz.
            return []

        try:
            import numpy as np
            dizi = np.asarray(vektorler, dtype=np.float32)
            puanlar = dizi @ np.asarray(sorgu_vektoru, dtype=np.float32)
            sira = np.argsort(-puanlar)[:limit]
            return [idler[i] for i in sira if puanlar[i] >= EN_AZ_BENZERLIK]
        except ImportError:
            # numpy yoksa saf Python: birkaç bin parçada kabul edilebilir,
            # onlarca binde değil. Bu yüzden numpy 'bilgi' ekinde önerilir.
            puanli = [(sum(a * b for a, b in zip(v, sorgu_vektoru)), pid)
                      for pid, v in zip(idler, vektorler)]
            puanli.sort(reverse=True)
            return [pid for puan, pid in puanli[:limit] if puan >= EN_AZ_BENZERLIK]

    def _kelime_ara(self, sorgu: str, limit: int) -> list[int]:
        """Rank chunk ids by BM25 over the folded full-text index."""
        parcalar = kelimeler(sorgu, sorular_da=True)
        if not parcalar:
            return []
        # Her kelime tırnak içinde: FTS5 sözdizimi karakterleri (NEAR, *, ^)
        # kullanıcının cümlesinde geçtiğinde sorguyu bozuyor.
        #
        # Sondaki yıldız Türkçe için isteğe bağlı değil. FTS5'in gövdeleyicisi
        # yok, Türkçe ise ekleri kelimenin sonuna yığıyor: "talimat" araması
        # "talimatlarını" geçen bir belgeyi bulamaz, "vaka" da "vakaların"ı.
        # Önek eşleşmesi bu dilde tam da doğru davranış.
        ifade = " OR ".join(f'"{k}"*' for k in parcalar)
        try:
            satirlar = self._conn.execute(
                "SELECT parca_id FROM parca_fts WHERE parca_fts MATCH ? "
                "ORDER BY bm25(parca_fts) LIMIT ?", (ifade, limit)).fetchall()
        except sqlite3.OperationalError:
            return []
        return [int(r["parca_id"]) for r in satirlar]

    @_kilitli
    def search(self, sorgu: str, limit: int = 6) -> list[Hit]:
        """Hybrid search: semantic and keyword rankings fused with RRF."""
        sorgu = (sorgu or "").strip()
        if not sorgu:
            raise RagError("Boş sorgu ile arama yapılamaz.")

        anlam = self._anlam_ara(sorgu, ADAY_SAYISI)
        kelime = self._kelime_ara(sorgu, ADAY_SAYISI)
        if not anlam and not kelime:
            return []

        puanlar: dict[int, float] = {}
        nedenler: dict[int, set[str]] = {}
        for etiket, sirali in (("anlam", anlam), ("kelime", kelime)):
            for sira, parca_id in enumerate(sirali):
                puanlar[parca_id] = puanlar.get(parca_id, 0.0) + 1.0 / (RRF_K + sira + 1)
                nedenler.setdefault(parca_id, set()).add(etiket)

        en_iyi = sorted(puanlar.items(), key=lambda kv: kv[1], reverse=True)[:limit]
        return [h for h in (self._hit(pid, puan, nedenler[pid]) for pid, puan in en_iyi)
                if h is not None]

    def _hit(self, parca_id: int, puan: float, neden: set[str]) -> Hit | None:
        satir = self._conn.execute(
            "SELECT p.baslik, p.metin, p.ilk_satir, p.son_satir, b.yol "
            "FROM parcalar p JOIN belgeler b ON b.id = p.belge_id WHERE p.id = ?",
            (parca_id,)).fetchone()
        if satir is None:
            return None
        return Hit(
            yol=satir["yol"], baslik=satir["baslik"], metin=satir["metin"],
            ilk_satir=int(satir["ilk_satir"]), son_satir=int(satir["son_satir"]),
            puan=puan, neden="+".join(sorted(neden)),
        )

    # ---------------- durum ----------------

    @_kilitli
    def stats(self) -> dict[str, object]:
        """What is in the base — the numbers the panel and CLI report."""
        belge = self._conn.execute("SELECT COUNT(*) n FROM belgeler").fetchone()["n"]
        parca = self._conn.execute("SELECT COUNT(*) n FROM parcalar").fetchone()["n"]
        vektorlu = self._conn.execute(
            "SELECT COUNT(*) n FROM parcalar WHERE vektor IS NOT NULL").fetchone()["n"]
        boyut = self._conn.execute(
            "SELECT boyut FROM parcalar WHERE vektor IS NOT NULL LIMIT 1").fetchone()
        return {
            "belge": int(belge),
            "parca": int(parca),
            "vektorlu": int(vektorlu),
            "boyut": int(boyut["boyut"]) if boyut else 0,
            "model": self.embedder.model,
            "anlam_aramasi": bool(self.embedder.available and vektorlu),
        }

    @_kilitli
    def documents(self, limit: int = 100) -> list[dict[str, object]]:
        satirlar = self._conn.execute(
            "SELECT yol, tur, parca_sayisi, boyut, eklendi_ts FROM belgeler "
            "ORDER BY eklendi_ts DESC LIMIT ?", (limit,)).fetchall()
        return [{"yol": r["yol"], "tur": r["tur"], "parca": r["parca_sayisi"],
                 "boyut": r["boyut"], "eklendi_ts": r["eklendi_ts"]} for r in satirlar]
