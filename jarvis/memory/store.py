"""SQLite-backed memory store.

Two of the five memory layers from the spec (§15) land here in V1:

* **Conversation memory** — every turn is logged automatically so a session
  can be reviewed and later summarised.
* **User memory (facts)** — written only through an explicit ``remember_fact``
  call. Nothing becomes a durable fact on its own: remembering is a deliberate
  act, not a side effect of chatting.

Technical knowledge, service cases and tasks arrive in later phases; the
schema leaves room for them without forcing a migration now.
"""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from ..core.owner import Owner
from ..core.metin import katla
from .onem import Kaynak, Onem, guven_belirle, onem_belirle
from .types import MemoryCategory, category_family


@dataclass
class Fact:
    key: str
    value: str
    category: str
    updated_ts: float
    #: Bağlama girme sırası. Varsayılan ORTA: alanı verilmeden kurulan
    #: eski çağrı yerleri kırılmasın diye.
    importance: int = 1
    confidence: float = 1.0
    source: str = "kullanici"
    last_used: float = 0.0
    usage_count: int = 0

    def as_line(self) -> str:
        return f"{self.key}: {self.value}"

    @property
    def onem(self) -> "Onem":
        return Onem(max(0, min(int(self.importance), 2)))

    @property
    def canonical_category(self) -> MemoryCategory:
        return category_family(self.category)


@dataclass
class TurnMessage:
    role: str
    content: str
    ts: float


_SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role       TEXT NOT NULL,
    content    TEXT NOT NULL,
    ts         REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id);

CREATE TABLE IF NOT EXISTS facts (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    category   TEXT NOT NULL DEFAULT 'genel',
    created_ts REAL NOT NULL,
    updated_ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_facts_category ON facts(category);

-- Ustune yazilan degerler silinmiyor, buraya tasiniyor.
--
-- Sebebi: "Artik Cursor kullaniyorum" dendiginde eski deger (VS Code)
-- gecerliligini kaybediyor ama YANLIS olmuyor — bir donem dogruydu.
-- Ustune yazip yok saymak, celiskiyi gorunmez kilar; kullanici "ben sana
-- bunu soylemistim" dediginde bakilacak bir yer kalmaz.
CREATE TABLE IF NOT EXISTS fact_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    key         TEXT NOT NULL,
    old_value   TEXT NOT NULL,
    new_value   TEXT NOT NULL,
    source      TEXT NOT NULL DEFAULT '',
    changed_ts  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fact_history_key ON fact_history(key, id);

-- Identity is a single row, kept apart from facts so it cannot be dropped by
-- a forget_fact call and is always available at startup.
CREATE TABLE IF NOT EXISTS owner (
    id               INTEGER PRIMARY KEY CHECK (id = 1),
    name             TEXT NOT NULL DEFAULT '',
    address_forms    TEXT NOT NULL DEFAULT '[]',
    role             TEXT NOT NULL DEFAULT '',
    profession       TEXT NOT NULL DEFAULT '',
    response_style   TEXT NOT NULL DEFAULT '',
    notes            TEXT NOT NULL DEFAULT '',
    share_with_cloud INTEGER NOT NULL DEFAULT 1,
    updated_ts       REAL NOT NULL
);
"""


class MemoryStore:
    """Thin, dependency-free persistence layer over SQLite."""

    def __init__(self, db_path: Path | str = ":memory:") -> None:
        self.db_path = str(db_path)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False: the agent and a future server loop may touch
        # the store from different threads; writes here are short and serialised.
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._göç_et()
        self._conn.commit()

    #: Sonradan eklenen sütunlar: (ad, SQLite tipi ve varsayılanı).
    #:
    #: ``CREATE TABLE IF NOT EXISTS`` var olan bir tabloya sütun EKLEMEZ —
    #: sessizce hiçbir şey yapar. Kullanıcının makinesinde aylardır dolu bir
    #: veritabanı var; şemayı değiştirmek onu yeniden kurmak değil, üstüne
    #: eklemek zorunda. Tabloyu silip yeniden yaratmak buradaki en kolay ve
    #: en yıkıcı seçenek olurdu.
    YENI_SUTUNLAR: tuple[tuple[str, str], ...] = (
        ("importance", "INTEGER NOT NULL DEFAULT 1"),
        ("confidence", "REAL NOT NULL DEFAULT 1.0"),
        ("source", "TEXT NOT NULL DEFAULT 'kullanici'"),
        ("last_used", "REAL NOT NULL DEFAULT 0"),
        ("usage_count", "INTEGER NOT NULL DEFAULT 0"),
    )

    def _göç_et(self) -> None:
        """Eksik sütunları ekle. Var olan satırlara dokunma.

        Varsayılanlar bilinçli seçildi: eski kayıtlar ``importance=1``
        (ORTA) ve ``confidence=1.0`` ile geliyor. Hepsini DÜŞÜK saymak,
        bugüne kadar kaydedilmiş her şeyi bağlamın dibine atardı; YÜKSEK
        saymak da yeni puanlamayı anlamsız kılardı. Ortada durmak, eski
        kayıtları ne cezalandırıyor ne kayırıyor.
        """
        var_olan = {r["name"] for r in
                    self._conn.execute("PRAGMA table_info(facts)").fetchall()}
        for ad, tanim in self.YENI_SUTUNLAR:
            if ad not in var_olan:
                self._conn.execute(f"ALTER TABLE facts ADD COLUMN {ad} {tanim}")

    def close(self) -> None:
        self._conn.close()

    # ---------------- conversation memory ----------------

    def add_message(self, session_id: str, role: str, content: str) -> None:
        self._conn.execute(
            "INSERT INTO messages (session_id, role, content, ts) VALUES (?, ?, ?, ?)",
            (session_id, role, content, time.time()),
        )
        self._conn.commit()

    def recent_messages(self, session_id: str, limit: int = 20) -> list[TurnMessage]:
        rows = self._conn.execute(
            "SELECT role, content, ts FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()
        return [TurnMessage(r["role"], r["content"], r["ts"]) for r in reversed(rows)]

    def session_count(self, session_id: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM messages WHERE session_id = ?", (session_id,)
        ).fetchone()
        return int(row["n"])

    # ---------------- user memory (facts) ----------------

    #: Sütun listesi tek yerde: SELECT'ler arasında sıra kayması,
    #: değerlerin yanlış alana düşmesi demek ve sessizce olur.
    _FACT_SUTUNLARI = ("key, value, category, updated_ts, importance, "
                       "confidence, source, last_used, usage_count")

    @staticmethod
    def _fact(row) -> Fact:
        return Fact(row["key"], row["value"], row["category"], row["updated_ts"],
                    importance=row["importance"], confidence=row["confidence"],
                    source=row["source"], last_used=row["last_used"],
                    usage_count=row["usage_count"])

    def remember(self, key: str, value: str, category: str = "genel",
                 source: str = Kaynak.KULLANICI.value,
                 israr: bool = False,
                 importance: int | None = None) -> Fact:
        """Bir bilgiyi kaydet ya da güncelle.

        Anahtar aynıysa güncelleme yapılıyor, ama **körü körüne değil.**
        Kural şu: bir ÇIKARIM, kullanıcının AÇIKÇA söylediğinin üstüne
        yazamaz. Sebebi somut — model konuşmadan "favori editörü Vim"
        diye bir sonuç çıkarabilir; kullanıcı bunu bizzat söylemişse
        çıkarımın onu ezmesi, hafızayı zamanla tahmine çevirir.

        Ters yön serbest: kullanıcı fikrini değiştirdiğinde ("artık Cursor
        kullanıyorum") güncelleme oluyor ve eski değer ``fact_history``
        içine taşınıyor — silinmiyor, çünkü bir dönem doğruydu.

        ``importance`` verilmezse :func:`onem_belirle` hesaplıyor.
        """
        key = key.strip()
        if not key:
            raise ValueError("boş anahtar ile hatırlanamaz")
        now = time.time()
        kaynak = (source or Kaynak.KULLANICI.value).strip().lower()
        guven = guven_belirle(kaynak)
        onem = (int(importance) if importance is not None
                else int(onem_belirle(key, value, category, israr)))

        eski = self._conn.execute(
            f"SELECT {self._FACT_SUTUNLARI} FROM facts WHERE key = ?", (key,)
        ).fetchone()

        if eski is not None and eski["value"] != value:
            zayif = guven < float(eski["confidence"])
            if zayif:
                # Celiski var ve YENI olan daha zayif kaynaktan geliyor.
                # Yazmiyoruz; ama sessiz de kalmiyoruz — cakisma kayda
                # geciyor, yoksa "neden guncellenmedi" sorusunun cevabi
                # hicbir yerde olmaz.
                self._conn.execute(
                    "INSERT INTO fact_history (key, old_value, new_value, "
                    "source, changed_ts) VALUES (?, ?, ?, ?, ?)",
                    (key, eski["value"], value, f"{kaynak}:reddedildi", now),
                )
                self._conn.commit()
                return self._fact(eski)
            self._conn.execute(
                "INSERT INTO fact_history (key, old_value, new_value, "
                "source, changed_ts) VALUES (?, ?, ?, ?, ?)",
                (key, eski["value"], value, kaynak, now),
            )

        if eski is not None:
            # Onem yalnizca YUKSELEBILIR. Bir kez "kimlik" diye isaretlenmis
            # bir kayit, sonraki gevsek bir yazmayla bağlamin dibine
            # dusmemeli; ayni ders izin katmaninda da alinmisti.
            onem = max(onem, int(eski["importance"]))

        self._conn.execute(
            """
            INSERT INTO facts (key, value, category, created_ts, updated_ts,
                               importance, confidence, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                category = excluded.category,
                updated_ts = excluded.updated_ts,
                importance = excluded.importance,
                confidence = excluded.confidence,
                source = excluded.source
            """,
            (key, value, category, now, now, onem, guven, kaynak),
        )
        self._conn.commit()
        return Fact(key, value, category, now, importance=onem,
                    confidence=guven, source=kaynak)

    def gecmis(self, key: str = "", limit: int = 20) -> list[dict]:
        """Üstüne yazılmış değerler. "Sana bunu söylemiştim"in cevabı."""
        sql = ("SELECT key, old_value, new_value, source, changed_ts "
               "FROM fact_history WHERE 1=1")
        params: list[object] = []
        if key:
            sql += " AND key = ?"
            params.append(key.strip())
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def recall(self, query: str = "", category: str = "", limit: int = 20,
               kullanim_say: bool = True) -> list[Fact]:
        """Anahtar/değer içinde ara, önem sırasına göre döndür.

        Sıralama ÖNEM önce, tazelik sonra. Yalnızca tazeliğe bakmak,
        kullanıcının adını bugünkü bir arıza notunun arkasında bırakıyordu
        — gerekçe :mod:`jarvis.memory.onem` içinde.

        ``kullanim_say`` dönen kayıtların sayacını artırıyor. Bu, hangi
        bilginin gerçekten işe yaradığını gösteren tek ölçüm; budama
        kararı buna bakıyor, tahmine değil.
        """
        sql = f"SELECT {self._FACT_SUTUNLARI} FROM facts WHERE 1=1"
        params: list[object] = []
        if query:
            sql += " AND (key LIKE ? OR value LIKE ?)"
            like = f"%{query}%"
            params += [like, like]
        if category:
            sql += " AND category = ?"
            params.append(category)
        sql += " ORDER BY importance DESC, updated_ts DESC LIMIT ?"
        params.append(limit)
        rows = self._conn.execute(sql, params).fetchall()
        sonuc = [self._fact(r) for r in rows]

        if kullanim_say and sonuc:
            now = time.time()
            self._conn.executemany(
                "UPDATE facts SET usage_count = usage_count + 1, last_used = ? "
                "WHERE key = ?",
                [(now, f.key) for f in sonuc],
            )
            self._conn.commit()
        return sonuc

    @staticmethod
    def _arama_tokenlari(query: str) -> set[str]:
        metin = katla(query or "")
        return {p for p in "".join(c if c.isalnum() else " " for c in metin).split()
                if len(p) >= 3}

    def retrieve_relevant(self, query: str, *, intent: str = "", limit: int = 8,
                          mark_used: bool = True) -> list[Fact]:
        """Return only long-term facts relevant to the current turn.

        This replaces the old ``all_facts() on every turn`` behaviour.  It is
        deterministic: lexical overlap + category affinity + importance.  A
        broad MEMORY_RECALL intent intentionally returns a profile slice even
        when the wording ("benim hakkımda ne biliyorsun") contains none of
        the stored keys.
        """
        limit = max(1, int(limit or 1))
        all_rows = self._conn.execute(
            f"SELECT {self._FACT_SUTUNLARI} FROM facts ORDER BY importance DESC, updated_ts DESC"
        ).fetchall()
        facts = [self._fact(r) for r in all_rows]
        if not facts:
            return []

        intent_name = (intent or "").upper()
        if intent_name == "MEMORY_RECALL":
            selected = facts[:limit]
        else:
            tokens = self._arama_tokenlari(query)
            affinity: dict[str, set[MemoryCategory]] = {
                "CODING": {MemoryCategory.PROJECT, MemoryCategory.TECHNICAL,
                           MemoryCategory.DECISION, MemoryCategory.INSTRUCTION},
                "GITHUB": {MemoryCategory.PROJECT, MemoryCategory.TECHNICAL,
                           MemoryCategory.DECISION},
                "SYSTEM_MONITOR": {MemoryCategory.TECHNICAL},
                "COMPUTER_CONTROL": {MemoryCategory.PREFERENCE, MemoryCategory.INSTRUCTION},
                "WEB_RESEARCH": {MemoryCategory.PROJECT, MemoryCategory.PREFERENCE},
                "TRAINING": {MemoryCategory.IDENTITY, MemoryCategory.PREFERENCE,
                             MemoryCategory.PROJECT, MemoryCategory.INSTRUCTION},
                "MEMORY_SAVE": {MemoryCategory.IDENTITY, MemoryCategory.PREFERENCE,
                                MemoryCategory.PROJECT, MemoryCategory.INSTRUCTION},
                "MEMORY_UPDATE": {MemoryCategory.IDENTITY, MemoryCategory.PREFERENCE,
                                  MemoryCategory.PROJECT, MemoryCategory.INSTRUCTION},
            }
            favored = affinity.get(intent_name, set())
            scored: list[tuple[float, Fact]] = []
            for fact in facts:
                hay = katla(f"{fact.key} {fact.value} {fact.category}")
                overlap = sum(1 for t in tokens if t in hay)
                score = overlap * 10.0
                if fact.canonical_category in favored:
                    score += 3.0
                # Explicit standing instructions are relevant to almost every
                # turn; identity itself lives in Owner, so ordinary identity
                # facts are not globally injected.
                if fact.canonical_category is MemoryCategory.INSTRUCTION:
                    score += 6.0
                score += float(fact.importance) * 0.5
                if overlap or fact.canonical_category is MemoryCategory.INSTRUCTION:
                    scored.append((score, fact))
            scored.sort(key=lambda x: (-x[0], -x[1].updated_ts))
            selected = [f for _, f in scored[:limit]]

        if mark_used and selected:
            now = time.time()
            self._conn.executemany(
                "UPDATE facts SET usage_count = usage_count + 1, last_used = ? WHERE key = ?",
                [(now, f.key) for f in selected],
            )
            self._conn.commit()
        return selected

    def merge_facts(self, keys: list[str], target_key: str, *,
                    category: str = "genel", source: str = Kaynak.KULLANICI.value) -> Fact:
        """Merge several explicit facts into one without silently deleting history.

        This is an explicit operation; automatic merging would risk losing a
        distinction the user intended to keep.  Source facts are removed only
        after the merged fact has been written successfully.
        """
        clean = [k.strip() for k in keys if k and k.strip()]
        if len(clean) < 2:
            raise ValueError("birleştirmek için en az iki anahtar gerekir")
        rows = []
        for key in clean:
            found = self.recall(key, limit=1, kullanim_say=False)
            exact = next((f for f in found if f.key == key), None)
            if exact is None:
                raise KeyError(f"hafıza anahtarı bulunamadı: {key}")
            rows.append(exact)
        value = "; ".join(f"{f.key}: {f.value}" for f in rows)
        merged = self.remember(target_key, value, category, source=source)
        for f in rows:
            if f.key != target_key:
                self.forget(f.key)
        return merged

    def forget(self, key: str) -> bool:
        cur = self._conn.execute("DELETE FROM facts WHERE key = ?", (key.strip(),))
        self._conn.commit()
        return cur.rowcount > 0

    def all_facts(self, limit: int = 40) -> list[Fact]:
        """Bağlama itilecek kayıtlar — en önemliden başlayarak.

        Sayaç ARTIRILMIYOR: bu çağrı her turda koşulsuz yapılıyor ve
        "bağlama kondu" ile "işe yaradı" aynı şey değil. Sayacı burada
        artırmak, hiç kullanılmayan bir kaydı da çok kullanılmış
        gösterirdi ve budama ölçümü anlamını yitirirdi.
        """
        return self.recall(limit=limit, kullanim_say=False)

    #: Budama adayı sayılmak için geçmesi gereken süre (gün).
    BUDAMA_GUNU = 90

    def budama_adaylari(self, gun: int | None = None) -> list[Fact]:
        """Silinmesi ÖNERİLEN kayıtlar — silinmiş olanlar değil.

        Kendiliğinden silme yok. Hafızadan bir şey düşürmek geri
        alınamaz ve kullanıcının "hani bunu biliyordun" demesiyle
        sonuçlanır; bu yüzden burası yalnızca liste veriyor, kararı
        sahibi veriyor.

        Aday olma şartı üçü birden: düşük önem, hiç kullanılmamış, ve
        yeterince eski. Üçünden biri tutmuyorsa kayıt duruyor.
        """
        sinir = time.time() - (gun if gun is not None else self.BUDAMA_GUNU) * 86400
        rows = self._conn.execute(
            f"SELECT {self._FACT_SUTUNLARI} FROM facts "
            "WHERE importance <= ? AND usage_count = 0 AND updated_ts < ? "
            "ORDER BY updated_ts ASC",
            (int(Onem.DUSUK), sinir),
        ).fetchall()
        return [self._fact(r) for r in rows]

    # ---------------- owner identity ----------------

    def get_owner(self) -> Owner:
        """The configured owner, or an empty Owner when none is set yet."""
        row = self._conn.execute("SELECT * FROM owner WHERE id = 1").fetchone()
        return Owner.from_row(row) if row is not None else Owner()

    def set_owner(self, owner: Owner) -> Owner:
        self._conn.execute(
            """
            INSERT INTO owner (id, name, address_forms, role, profession,
                               response_style, notes, share_with_cloud, updated_ts)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                address_forms = excluded.address_forms,
                role = excluded.role,
                profession = excluded.profession,
                response_style = excluded.response_style,
                notes = excluded.notes,
                share_with_cloud = excluded.share_with_cloud,
                updated_ts = excluded.updated_ts
            """,
            (*owner.to_row(), time.time()),
        )
        self._conn.commit()
        return owner

    def clear_owner(self) -> bool:
        cur = self._conn.execute("DELETE FROM owner WHERE id = 1")
        self._conn.commit()
        return cur.rowcount > 0
