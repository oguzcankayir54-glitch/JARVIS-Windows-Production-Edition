"""Service log — the record of what came in, what was tried, what it turned out to be.

The third memory layer from the spec (§15). Facts hold what is true in
general; this holds what happened to a specific machine on a specific day.

The distinction matters because of what it makes possible later: once a
hundred cases are on record, "have we seen this symptom before, and what did
it turn out to be?" becomes a question with a real answer instead of a guess.
No off-the-shelf model knows this workshop's customers — that value only
accumulates from here, which is why it is worth starting early.

Cases live in the same database file as the rest of memory but in their own
module: conversation and facts are about the owner, cases are about other
people's machines, and mixing the two would blur who a record belongs to.
"""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path

from ..core.metin import EN_KISA, ETKISIZ, katla, kelimeler

#: Bir vakanın geçebileceği durumlar. Kapalı vakalar silinmez, arşivlenir —
#: geçmiş vaka aramanın bütün değeri onların durmasında.
ACIK = "acik"
BEKLIYOR = "bekliyor"      # parça/müşteri bekleniyor
KAPALI = "kapali"
DURUMLAR = (ACIK, BEKLIYOR, KAPALI)


#: Arama katlaması ortak: vaka araması ile bilgi tabanı araması aynı soruyu
#: farklı biçimde katlarsa, aynı kelime iki yerde iki farklı sonuç verir.
_katla = katla
_kelimeler = kelimeler
_EN_KISA = EN_KISA
_ETKISIZ = ETKISIZ


class CaseError(ValueError):
    """Raised with a Turkish message the tool layer can hand straight back."""


@dataclass
class CaseNote:
    id: int
    case_id: int
    text: str
    kind: str          # gozlem | deneme | sonuc
    ts: float


@dataclass
class Case:
    id: int
    customer: str
    device: str
    symptom: str
    status: str
    opened_ts: float
    closed_ts: float | None = None
    resolution: str = ""
    promised_ts: float | None = None
    notes: list[CaseNote] = field(default_factory=list)

    def as_line(self) -> str:
        """One-line summary — what the model sees when cases are listed."""
        yas = int((time.time() - self.opened_ts) // 86400)
        yas_str = "bugün" if yas == 0 else f"{yas} gün önce"
        parca = f"#{self.id} · {self.customer} · {self.device} · {self.symptom} ({yas_str})"
        return parca if self.status == ACIK else f"{parca} [{self.status}]"


@dataclass
class DiagnosticSession:
    id: int
    case_id: int
    playbook: str
    current_node: str
    status: str
    summary: str
    started_ts: float
    updated_ts: float


_SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    customer    TEXT NOT NULL,
    device      TEXT NOT NULL,
    symptom     TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'acik',
    opened_ts   REAL NOT NULL,
    closed_ts   REAL,
    resolution  TEXT NOT NULL DEFAULT '',
    promised_ts REAL
);
CREATE INDEX IF NOT EXISTS idx_cases_status ON cases(status, id);

CREATE TABLE IF NOT EXISTS case_notes (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    text    TEXT NOT NULL,
    kind    TEXT NOT NULL DEFAULT 'gozlem',
    ts      REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_notes_case ON case_notes(case_id, id);

CREATE TABLE IF NOT EXISTS diagnostic_sessions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id      INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    playbook     TEXT NOT NULL,
    current_node TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'aktif',
    summary      TEXT NOT NULL DEFAULT '',
    started_ts   REAL NOT NULL,
    updated_ts   REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_diagnostic_case
    ON diagnostic_sessions(case_id, status, id);
"""


class CaseStore:
    """Persistence for service cases, over the same SQLite file as memory."""

    def __init__(self, db_path: Path | str = ":memory:") -> None:
        self.db_path = str(db_path)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        # Its own connection to the shared file. Writes are short and the agent
        # is serialised, but a busy timeout keeps a concurrent panel request
        # from failing outright if the two ever overlap.
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=5.0)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # ---------------- writing ----------------

    def open_case(self, customer: str, device: str, symptom: str,
                  promised_ts: float | None = None) -> Case:
        customer, device, symptom = customer.strip(), device.strip(), symptom.strip()
        # Guarded rather than allowed through: a case with no symptom is
        # unsearchable later, which defeats the point of keeping it.
        if not customer:
            raise CaseError("Müşteri adı boş olamaz.")
        if not device:
            raise CaseError("Cihaz boş olamaz — ör. 'Lenovo V15 laptop'.")
        if not symptom:
            raise CaseError("Belirti boş olamaz; sonradan arayamayız.")

        now = time.time()
        cur = self._conn.execute(
            "INSERT INTO cases (customer, device, symptom, status, opened_ts, promised_ts) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (customer, device, symptom, ACIK, now, promised_ts),
        )
        self._conn.commit()
        return Case(id=cur.lastrowid, customer=customer, device=device, symptom=symptom,
                    status=ACIK, opened_ts=now, promised_ts=promised_ts)

    def add_note(self, case_id: int, text: str, kind: str = "gozlem") -> CaseNote:
        text = text.strip()
        if not text:
            raise CaseError("Not boş olamaz.")
        if kind not in ("gozlem", "deneme", "sonuc"):
            kind = "gozlem"
        if self.get_case(case_id) is None:
            raise CaseError(f"#{case_id} numaralı vaka yok.")

        now = time.time()
        cur = self._conn.execute(
            "INSERT INTO case_notes (case_id, text, kind, ts) VALUES (?, ?, ?, ?)",
            (case_id, text, kind, now),
        )
        self._conn.commit()
        return CaseNote(id=cur.lastrowid, case_id=case_id, text=text, kind=kind, ts=now)

    def close_case(self, case_id: int, resolution: str) -> Case:
        resolution = resolution.strip()
        # The resolution is the whole point of the record: a case closed with
        # "fixed" teaches nothing when the same symptom returns in a year.
        if not resolution:
            raise CaseError("Sonuç yazılmadan vaka kapatılamaz — ne çıktığını yazın.")
        vaka = self.get_case(case_id)
        if vaka is None:
            raise CaseError(f"#{case_id} numaralı vaka yok.")
        if vaka.status == KAPALI:
            raise CaseError(f"#{case_id} zaten kapalı ({vaka.resolution}).")

        now = time.time()
        self._conn.execute(
            "UPDATE cases SET status = ?, closed_ts = ?, resolution = ? WHERE id = ?",
            (KAPALI, now, resolution, case_id),
        )
        self._conn.commit()
        return self.get_case(case_id)   # type: ignore[return-value]

    def set_status(self, case_id: int, status: str) -> Case:
        if status not in (ACIK, BEKLIYOR):
            raise CaseError(f"Durum '{ACIK}' veya '{BEKLIYOR}' olmalı; kapatmak için close_case.")
        if self.get_case(case_id) is None:
            raise CaseError(f"#{case_id} numaralı vaka yok.")
        self._conn.execute("UPDATE cases SET status = ? WHERE id = ?", (status, case_id))
        self._conn.commit()
        return self.get_case(case_id)   # type: ignore[return-value]

    def start_diagnostic(self, case_id: int, playbook: str,
                         first_node: str) -> DiagnosticSession:
        if self.get_case(case_id) is None:
            raise CaseError(f"#{case_id} numaralı vaka yok.")
        now = time.time()
        cur = self._conn.execute(
            "INSERT INTO diagnostic_sessions "
            "(case_id, playbook, current_node, status, started_ts, updated_ts) "
            "VALUES (?, ?, ?, 'aktif', ?, ?)",
            (case_id, playbook, first_node, now, now),
        )
        self._conn.commit()
        return self.get_diagnostic(cur.lastrowid)  # type: ignore[return-value]

    def update_diagnostic(self, session_id: int, *, current_node: str,
                          status: str = "aktif", summary: str = "") -> DiagnosticSession:
        if status not in ("aktif", "tamamlandi"):
            raise CaseError("Teşhis oturumu durumu geçersiz.")
        if self.get_diagnostic(session_id) is None:
            raise CaseError(f"#{session_id} numaralı teşhis oturumu yok.")
        self._conn.execute(
            "UPDATE diagnostic_sessions SET current_node = ?, status = ?, "
            "summary = ?, updated_ts = ? WHERE id = ?",
            (current_node, status, summary.strip(), time.time(), session_id),
        )
        self._conn.commit()
        return self.get_diagnostic(session_id)  # type: ignore[return-value]

    # ---------------- reading ----------------

    def get_case(self, case_id: int, with_notes: bool = False) -> Case | None:
        row = self._conn.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone()
        if row is None:
            return None
        vaka = self._row_to_case(row)
        if with_notes:
            vaka.notes = self.notes_for(case_id)
        return vaka

    def notes_for(self, case_id: int) -> list[CaseNote]:
        rows = self._conn.execute(
            "SELECT * FROM case_notes WHERE case_id = ? ORDER BY id", (case_id,)
        ).fetchall()
        return [CaseNote(id=r["id"], case_id=r["case_id"], text=r["text"],
                         kind=r["kind"], ts=r["ts"]) for r in rows]

    def get_diagnostic(self, session_id: int) -> DiagnosticSession | None:
        row = self._conn.execute(
            "SELECT * FROM diagnostic_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if row is None:
            return None
        return DiagnosticSession(
            id=row["id"], case_id=row["case_id"], playbook=row["playbook"],
            current_node=row["current_node"], status=row["status"],
            summary=row["summary"], started_ts=row["started_ts"],
            updated_ts=row["updated_ts"],
        )

    def diagnostics_for(self, case_id: int) -> list[DiagnosticSession]:
        rows = self._conn.execute(
            "SELECT id FROM diagnostic_sessions WHERE case_id = ? ORDER BY id DESC",
            (case_id,),
        ).fetchall()
        return [session for row in rows
                if (session := self.get_diagnostic(row["id"])) is not None]

    def open_cases(self, limit: int = 30) -> list[Case]:
        """Cases still on the bench — oldest first, because those are the ones
        that get forgotten."""
        rows = self._conn.execute(
            "SELECT * FROM cases WHERE status IN (?, ?) ORDER BY opened_ts LIMIT ?",
            (ACIK, BEKLIYOR, limit),
        ).fetchall()
        return [self._row_to_case(r) for r in rows]

    def promised_cases(self, until_ts: float, limit: int = 50) -> list[Case]:
        """Açık/bekleyen ve teslim sözü yaklaşan vakalar, en acili önce."""
        rows = self._conn.execute(
            "SELECT * FROM cases WHERE status IN (?, ?) AND promised_ts IS NOT NULL "
            "AND promised_ts <= ? ORDER BY promised_ts LIMIT ?",
            (ACIK, BEKLIYOR, float(until_ts), int(limit)),
        ).fetchall()
        return [self._row_to_case(r) for r in rows]

    def search(self, query: str, limit: int = 6) -> list[tuple[Case, int]]:
        """Past cases whose text overlaps ``query``, best match first.

        Matching happens in Python rather than SQL on purpose. SQLite's LIKE
        folds case for ASCII only, so "IŞIK" would not find "ışık" — and
        Turkish is exactly where this gets used. ``casefold`` handles it, at
        the cost of reading the candidate rows; with a workshop's volume that
        stays cheap for years.

        This is keyword overlap, not meaning: "görüntü yok" will not find
        "ekran karanlık". Real semantic search arrives with the document
        index; until then the scoring is honest about what it did — the count
        of query words a case actually contains.
        """
        kelimeler = _kelimeler(query)
        if not kelimeler:
            return []

        rows = self._conn.execute("SELECT * FROM cases ORDER BY id DESC LIMIT 500").fetchall()
        notlar = self._notes_by_case()

        puanli: list[tuple[Case, int]] = []
        for row in rows:
            vaka = self._row_to_case(row)
            metin = _katla(" ".join([
                vaka.customer, vaka.device, vaka.symptom, vaka.resolution,
                *notlar.get(vaka.id, ()),
            ]))
            puan = sum(1 for k in kelimeler if k in metin)
            if puan:
                puanli.append((vaka, puan))

        # Score first, then the solved ones, then the recent: a closed case
        # says what it turned out to be, which is the answer being looked for.
        puanli.sort(key=lambda p: (p[1], p[0].status == KAPALI, p[0].opened_ts), reverse=True)
        return puanli[:limit]

    def _notes_by_case(self) -> dict[int, list[str]]:
        rows = self._conn.execute("SELECT case_id, text FROM case_notes").fetchall()
        toplu: dict[int, list[str]] = {}
        for r in rows:
            toplu.setdefault(r["case_id"], []).append(r["text"])
        return toplu

    def count_open(self) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM cases WHERE status IN (?, ?)", (ACIK, BEKLIYOR)
        ).fetchone()
        return int(row["n"])

    @staticmethod
    def _row_to_case(row: sqlite3.Row) -> Case:
        return Case(
            id=row["id"], customer=row["customer"], device=row["device"],
            symptom=row["symptom"], status=row["status"], opened_ts=row["opened_ts"],
            closed_ts=row["closed_ts"], resolution=row["resolution"],
            promised_ts=row["promised_ts"],
        )
