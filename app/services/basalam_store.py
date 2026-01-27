from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


class BasalamIdStore:
    def __init__(self, db_path: Path | None = None) -> None:
        if db_path is None:
            db_path = Path(__file__).resolve().parents[2] / "invoices.db"
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS basalam_order_ids (
                    id TEXT PRIMARY KEY,
                    saved_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_basalam_order_ids_saved_at "
                "ON basalam_order_ids(saved_at)"
            )

    def fetch_existing_ids(self, ids: list[str]) -> set[str]:
        if not ids:
            return set()
        existing: set[str] = set()
        with self._connect() as conn:
            for chunk in _chunked(ids, 500):
                placeholders = ",".join("?" for _ in chunk)
                rows = conn.execute(
                    f"""
                    SELECT id
                    FROM basalam_order_ids
                    WHERE id IN ({placeholders})
                    """,
                    chunk,
                ).fetchall()
                existing.update(row[0] for row in rows)
        return existing

    def store_ids(self, ids: list[str]) -> None:
        if not ids:
            return
        timestamp = datetime.now(ZoneInfo("Asia/Tehran")).isoformat(
            timespec="seconds"
        )
        rows = [(item_id, timestamp) for item_id in ids]
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT OR IGNORE INTO basalam_order_ids (id, saved_at)
                VALUES (?, ?)
                """,
                rows,
            )


def _chunked(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]
