from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.core.db_lock import db_connection
from app.core.paths import app_dir
from app.services.backup_sender import send_backup


@dataclass(frozen=True)
class AdminUser:
    admin_id: int
    username: str
    role: str
    auto_lock_minutes: int


class AdminService:
    def __init__(self, db_path: Path | None = None) -> None:
        if db_path is None:
            db_path = app_dir() / "invoices.db"
        self.db_path = db_path
        self._init_db()
        self._ensure_default_admin()

    def _connect(self):
        return db_connection(self.db_path, row_factory=sqlite3.Row)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS admins (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL,
                    auto_lock_minutes INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_admins_username ON admins(username)"
            )

    def _ensure_default_admin(self) -> None:
        created = False
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id FROM admins WHERE username = ?",
                ("reza",),
            ).fetchone()
            if row:
                return
            now = datetime.now(ZoneInfo("Asia/Tehran")).isoformat(
                timespec="seconds"
            )
            password_hash = self._hash_password("reza1375")
            conn.execute(
                """
                INSERT INTO admins (username, password_hash, role, auto_lock_minutes, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                ("reza", password_hash, "manager", 1, now),
            )
            created = True
        if created:
            send_backup(reason="admin_default_created")

    @staticmethod
    def _hash_password(password: str) -> str:
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, 150_000
        )
        return f"{salt.hex()}${digest.hex()}"

    @staticmethod
    def _verify_password(stored_hash: str, password: str) -> bool:
        if not stored_hash or "$" not in stored_hash:
            return False
        salt_hex, digest_hex = stored_hash.split("$", 1)
        try:
            salt = bytes.fromhex(salt_hex)
            expected = bytes.fromhex(digest_hex)
        except ValueError:
            return False
        candidate = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, 150_000
        )
        return hmac.compare_digest(candidate, expected)

    @staticmethod
    def _normalize_role(role: str) -> str:
        role_value = role.strip().lower()
        if role_value not in {"manager", "employee"}:
            raise ValueError("Role must be manager or employee.")
        return role_value

    @staticmethod
    def _validate_auto_lock(minutes: int) -> int:
        if minutes < 1 or minutes > 60:
            raise ValueError("Auto lock minutes must be between 1 and 60.")
        return minutes

    def authenticate(self, username: str, password: str) -> AdminUser | None:
        username = username.strip()
        if not username or not password:
            return None
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, username, password_hash, role, auto_lock_minutes
                FROM admins
                WHERE username = ?
                """,
                (username,),
            ).fetchone()
            if row is None:
                return None
            if not self._verify_password(row["password_hash"], password):
                return None
            return AdminUser(
                admin_id=int(row["id"]),
                username=str(row["username"]),
                role=str(row["role"]),
                auto_lock_minutes=int(row["auto_lock_minutes"]),
            )

    def list_admins(self) -> list[AdminUser]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, username, role, auto_lock_minutes
                FROM admins
                ORDER BY username ASC
                """
            ).fetchall()
        return [
            AdminUser(
                admin_id=int(row["id"]),
                username=str(row["username"]),
                role=str(row["role"]),
                auto_lock_minutes=int(row["auto_lock_minutes"]),
            )
            for row in rows
        ]

    def create_admin(
        self,
        username: str,
        password: str,
        role: str,
        auto_lock_minutes: int = 1,
        admin_username: str | None = None,
    ) -> AdminUser:
        username = username.strip()
        if not username:
            raise ValueError("Username is required.")
        if not password:
            raise ValueError("Password is required.")
        role_value = self._normalize_role(role)
        auto_lock = self._validate_auto_lock(int(auto_lock_minutes))
        password_hash = self._hash_password(password)
        created_at = datetime.now(ZoneInfo("Asia/Tehran")).isoformat(
            timespec="seconds"
        )
        with self._connect() as conn:
            try:
                cursor = conn.execute(
                    """
                    INSERT INTO admins (username, password_hash, role, auto_lock_minutes, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        username,
                        password_hash,
                        role_value,
                        auto_lock,
                        created_at,
                    ),
                )
            except sqlite3.IntegrityError as exc:  # noqa: BLE001
                raise ValueError("Username already exists.") from exc
            admin_id = int(cursor.lastrowid)
        send_backup(reason="admin_created", admin_username=admin_username)
        return AdminUser(
            admin_id=admin_id,
            username=username,
            role=role_value,
            auto_lock_minutes=auto_lock,
        )

    def update_password(
        self,
        admin_id: int,
        new_password: str,
        admin_username: str | None = None,
    ) -> None:
        if not new_password:
            raise ValueError("New password is required.")
        password_hash = self._hash_password(new_password)
        with self._connect() as conn:
            conn.execute(
                "UPDATE admins SET password_hash = ? WHERE id = ?",
                (password_hash, admin_id),
            )
        send_backup(
            reason="admin_password_updated", admin_username=admin_username
        )

    def update_auto_lock(
        self,
        admin_id: int,
        minutes: int,
        admin_username: str | None = None,
    ) -> None:
        auto_lock = self._validate_auto_lock(int(minutes))
        with self._connect() as conn:
            conn.execute(
                "UPDATE admins SET auto_lock_minutes = ? WHERE id = ?",
                (auto_lock, admin_id),
            )
        send_backup(
            reason="admin_auto_lock_updated", admin_username=admin_username
        )

    def delete_admin(
        self, admin_id: int, admin_username: str | None = None
    ) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM admins WHERE id = ?", (admin_id,))
        send_backup(reason="admin_deleted", admin_username=admin_username)

    def get_admin_by_id(self, admin_id: int) -> AdminUser | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, username, role, auto_lock_minutes
                FROM admins
                WHERE id = ?
                """,
                (admin_id,),
            ).fetchone()
            if row is None:
                return None
            return AdminUser(
                admin_id=int(row["id"]),
                username=str(row["username"]),
                role=str(row["role"]),
                auto_lock_minutes=int(row["auto_lock_minutes"]),
            )
