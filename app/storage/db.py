from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.config import get_settings


MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def connect(path: Path | None = None) -> sqlite3.Connection:
    db_path = path or get_settings().database_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(path: Path | None = None) -> None:
    with connect(path) as conn:
        for migration in sorted(MIGRATIONS_DIR.glob("*.sql")):
            conn.executescript(migration.read_text(encoding="utf-8"))
        _ensure_column(conn, "trace_runs", "identity_source", "TEXT NOT NULL DEFAULT 'unknown'")
        _ensure_column(conn, "llm_calls", "identity_source", "TEXT NOT NULL DEFAULT 'unknown'")


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


@contextmanager
def db_connection(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    init_db(path)
    with connect(path) as conn:
        yield conn
