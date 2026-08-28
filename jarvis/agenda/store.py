from __future__ import annotations

import sqlite3
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

TURLER = ("gorev", "randevu", "teslim")
DURUMLAR = ("acik", "tamamlandi", "iptal")


class AgendaError(ValueError):
    pass


def parse_datetime(value: str | float | int) -> float:
    if isinstance(value, (float, int)):
        return float(value)
    text = value.strip()
    if not text:
        raise AgendaError("Tarih ve saat boş olamaz.")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AgendaError("Tarih ISO biçiminde olmalı; ör. 2026-09-01 14:30.") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.now().astimezone().tzinfo)
    return parsed.timestamp()


@dataclass(frozen=True)
class AgendaItem:
    id: int
    title: str
    kind: str
    due_ts: float
    reminder_ts: float
    status: str
    notes: str
    case_id: int | None
    created_ts: float
    notified_ts: float | None = None

    def as_dict(self) -> dict:
        return asdict(self)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS agenda_items (
 id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, kind TEXT NOT NULL,
 due_ts REAL NOT NULL, reminder_ts REAL NOT NULL, status TEXT NOT NULL DEFAULT 'acik',
 notes TEXT NOT NULL DEFAULT '', case_id INTEGER, created_ts REAL NOT NULL, notified_ts REAL
);
CREATE INDEX IF NOT EXISTS idx_agenda_due ON agenda_items(status, due_ts);
CREATE TABLE IF NOT EXISTS agenda_notifications (
 notification_key TEXT PRIMARY KEY, notified_ts REAL NOT NULL
);
"""


class AgendaStore:
    def __init__(self, db_path: Path | str = ":memory:", cases=None) -> None:
        self.db_path = str(db_path)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.cases = cases
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=5)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def create(self, title: str, kind: str, due, reminder=None, notes: str = "",
               case_id: int | None = None) -> AgendaItem:
        title, kind = title.strip(), kind.strip().lower()
        if not title:
            raise AgendaError("Ajanda başlığı boş olamaz.")
        if kind not in TURLER:
            raise AgendaError("Tür 'gorev', 'randevu' veya 'teslim' olmalı.")
        due_ts = parse_datetime(due)
        reminder_ts = parse_datetime(reminder) if reminder not in (None, "") else due_ts
        if reminder_ts > due_ts:
            raise AgendaError("Hatırlatma zamanı son tarihten sonra olamaz.")
        if case_id is not None:
            case_id = int(case_id)
            if self.cases is not None and self.cases.get_case(case_id) is None:
                raise AgendaError(f"#{case_id} numaralı vaka yok.")
        now = time.time()
        cur = self._conn.execute(
            "INSERT INTO agenda_items(title,kind,due_ts,reminder_ts,status,notes,case_id,created_ts) "
            "VALUES(?,?,?,?, 'acik',?,?,?)",
            (title, kind, due_ts, reminder_ts, notes.strip(), case_id, now))
        self._conn.commit()
        return self.get(cur.lastrowid)  # type: ignore[return-value]

    def get(self, item_id: int) -> AgendaItem | None:
        row = self._conn.execute("SELECT * FROM agenda_items WHERE id=?", (int(item_id),)).fetchone()
        return self._row(row) if row else None

    def list(self, status: str = "acik", limit: int = 100) -> list[AgendaItem]:
        if status not in (*DURUMLAR, "hepsi"):
            raise AgendaError("Ajanda durumu geçersiz.")
        if status == "hepsi":
            rows = self._conn.execute("SELECT * FROM agenda_items ORDER BY due_ts LIMIT ?", (limit,)).fetchall()
        else:
            rows = self._conn.execute("SELECT * FROM agenda_items WHERE status=? ORDER BY due_ts LIMIT ?",
                                      (status, limit)).fetchall()
        return [self._row(r) for r in rows]

    def set_status(self, item_id: int, status: str) -> AgendaItem:
        if status not in ("tamamlandi", "iptal"):
            raise AgendaError("Durum 'tamamlandi' veya 'iptal' olmalı.")
        if self.get(item_id) is None:
            raise AgendaError(f"#{item_id} numaralı ajanda kaydı yok.")
        self._conn.execute("UPDATE agenda_items SET status=? WHERE id=?", (status, int(item_id)))
        self._conn.commit()
        return self.get(item_id)  # type: ignore[return-value]

    def due_reminders(self, now: float | None = None) -> list[AgendaItem]:
        now = time.time() if now is None else now
        rows = self._conn.execute(
            "SELECT * FROM agenda_items WHERE status='acik' AND notified_ts IS NULL "
            "AND reminder_ts<=? ORDER BY reminder_ts", (now,)).fetchall()
        return [self._row(r) for r in rows]

    def mark_notified(self, item_id: int, now: float | None = None) -> None:
        self._conn.execute("UPDATE agenda_items SET notified_ts=? WHERE id=?",
                           (time.time() if now is None else now, int(item_id)))
        self._conn.commit()

    def claim_notification(self, key: str, now: float | None = None) -> bool:
        try:
            self._conn.execute("INSERT INTO agenda_notifications VALUES(?,?)",
                               (key, time.time() if now is None else now))
            self._conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    @staticmethod
    def _row(row: sqlite3.Row) -> AgendaItem:
        return AgendaItem(**dict(row))
