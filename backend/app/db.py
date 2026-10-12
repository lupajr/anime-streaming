"""Persistência local em SQLite: cache da biblioteca, análises de mídia e progresso."""
import sqlite3
import threading
from pathlib import Path
from typing import Any, Iterable

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id        TEXT PRIMARY KEY,
    parent_id TEXT NOT NULL,
    name      TEXT NOT NULL,
    mime      TEXT,
    size      INTEGER DEFAULT 0,
    modified  TEXT,
    kind      TEXT NOT NULL            -- folder | video | image
);
CREATE INDEX IF NOT EXISTS idx_items_parent ON items(parent_id);

CREATE TABLE IF NOT EXISTS probe (
    id       TEXT PRIMARY KEY,
    modified TEXT,
    data     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS progress (
    id         TEXT PRIMARY KEY,
    position   REAL NOT NULL,
    duration   REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS kv (
    k TEXT PRIMARY KEY,
    v TEXT
);
"""


class DB:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.executescript(SCHEMA)

    def query(self, sql: str, args: Iterable[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, tuple(args)).fetchall()

    def one(self, sql: str, args: Iterable[Any] = ()) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute(sql, tuple(args)).fetchone()

    def execute(self, sql: str, args: Iterable[Any] = ()) -> None:
        with self._lock:
            self._conn.execute(sql, tuple(args))

    def replace_items(self, rows: list[tuple]) -> None:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("BEGIN")
            try:
                cur.execute("DELETE FROM items")
                cur.executemany(
                    "INSERT OR REPLACE INTO items (id, parent_id, name, mime, size, modified, kind)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?)",
                    rows,
                )
                cur.execute("COMMIT")
            except Exception:
                cur.execute("ROLLBACK")
                raise

    def kv_get(self, key: str) -> str | None:
        row = self.one("SELECT v FROM kv WHERE k = ?", (key,))
        return row["v"] if row else None

    def kv_set(self, key: str, value: str) -> None:
        self.execute("INSERT OR REPLACE INTO kv (k, v) VALUES (?, ?)", (key, value))
