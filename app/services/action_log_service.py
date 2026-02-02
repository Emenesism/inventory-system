from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.core.paths import app_dir
from app.services.admin_service import AdminUser


@dataclass
class ActionEntry:
    action_id: int
    created_at: str
    admin_id: int | None
    admin_username: str | None
    action_type: str
    title: str
    details: str


class ActionLogService:
    def __init__(self, db_path: Path | None = None) -> None:
        if db_path is None:
            db_path = app_dir() / "invoices.db"
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                admin_id INTEGER,
                admin_username TEXT,
                action_type TEXT NOT NULL,
                title TEXT NOT NULL,
                details TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_actions_created_at "
            "ON actions(created_at)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_actions_type "
            "ON actions(action_type)"
        )

    def _init_db(self) -> None:
        with self._connect() as conn:
            self._ensure_schema(conn)

    def log_action(
        self,
        action_type: str,
        title: str,
        details: str,
        admin: AdminUser | None = None,
    ) -> None:
        created_at = datetime.now(ZoneInfo("Asia/Tehran")).isoformat(
            timespec="seconds"
        )
        with self._connect() as conn:
            self._ensure_schema(conn)
            conn.execute(
                """
                INSERT INTO actions (
                    created_at,
                    admin_id,
                    admin_username,
                    action_type,
                    title,
                    details
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    created_at,
                    admin.admin_id if admin else None,
                    admin.username if admin else None,
                    action_type,
                    title,
                    details,
                ),
            )

    def list_actions(
        self,
        limit: int = 200,
        offset: int = 0,
        search: str | None = None,
    ) -> list[ActionEntry]:
        with self._connect() as conn:
            self._ensure_schema(conn)
            if search:
                like = f"%{search}%"
                rows = conn.execute(
                    """
                    SELECT
                        id,
                        created_at,
                        admin_id,
                        admin_username,
                        action_type,
                        title,
                        details
                    FROM actions
                    WHERE title LIKE ? OR details LIKE ? OR admin_username LIKE ?
                    ORDER BY id DESC
                    LIMIT ?
                    OFFSET ?
                    """,
                    (like, like, like, limit, offset),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT
                        id,
                        created_at,
                        admin_id,
                        admin_username,
                        action_type,
                        title,
                        details
                    FROM actions
                    ORDER BY id DESC
                    LIMIT ?
                    OFFSET ?
                    """,
                    (limit, offset),
                ).fetchall()
        return [
            ActionEntry(
                action_id=row["id"],
                created_at=row["created_at"],
                admin_id=row["admin_id"],
                admin_username=row["admin_username"],
                action_type=row["action_type"],
                title=row["title"],
                details=row["details"],
            )
            for row in rows
        ]

    def count_actions(self, search: str | None = None) -> int:
        with self._connect() as conn:
            self._ensure_schema(conn)
            if search:
                like = f"%{search}%"
                row = conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM actions
                    WHERE title LIKE ? OR details LIKE ? OR admin_username LIKE ?
                    """,
                    (like, like, like),
                ).fetchone()
            else:
                row = conn.execute("SELECT COUNT(*) FROM actions").fetchone()
        return int(row[0] if row else 0)
