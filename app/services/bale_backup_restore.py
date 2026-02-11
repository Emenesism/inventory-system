from __future__ import annotations

import hashlib
import io
import logging
import os
import sqlite3
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any, Iterable

import requests

from app.core.config import AppConfig
from app.core.db_lock import db_lock
from app.core.paths import app_dir
from app.services.bale_bot_service import BaleBotClient

DEFAULT_DB_NAME = "invoices.db"
DEFAULT_STOCK_NAME = "stock.dat"

logger = logging.getLogger(__name__)

_HASH_CHUNK_SIZE = 1024 * 1024
_IGNORED_DB_TABLES = {"actions"}


class BaleBackupRestorer:
    def __init__(
        self,
        config: AppConfig | None = None,
        db_path: Path | None = None,
        stock_path: Path | None = None,
    ) -> None:
        self.config = config or AppConfig.load()
        self.db_path = db_path or (app_dir() / DEFAULT_DB_NAME)
        self.stock_path = stock_path or self._resolve_stock_path()
        self._logger = logging.getLogger(self.__class__.__name__)
        self.restart_required = False
        self.missing_files: list[str] = []
        self.pending_files: list[str] = []

    def restore_latest_backup(
        self, on_status=None, raise_errors: bool = False
    ) -> bool:
        self.restart_required = False
        self.missing_files = []
        self.pending_files = []
        self._logger.info(
            "Starting backup restore (db=%s, stock=%s).",
            self.db_path,
            self.stock_path,
        )
        token = (self.config.bot_token or "").strip()
        channel_id = (self.config.channel_id or "").strip()
        if not token or not channel_id:
            if raise_errors:
                raise RuntimeError("تنظیمات ربات یا کانال ناقص است.")
            self._logger.warning(
                "Backup restore skipped (missing bot_token/channel_id)."
            )
            return False

        client = BaleBotClient(token=token)
        if on_status:
            on_status("در حال دریافت بروزرسانی‌ها از بله...")
        updates = self._fetch_latest_update(client)
        self._logger.info("Fetched %d update(s) from Bale.", len(updates))

        if on_status:
            on_status("در حال بررسی پیام‌های کانال پشتیبان...")
        latest_message = self._latest_channel_message(updates, channel_id)
        if latest_message is None:
            self._logger.warning("No backup message found for channel.")
            return False

        backup_name = self._extract_file_name(latest_message)
        file_id = self._extract_file_id(latest_message)
        if not file_id:
            self._logger.warning("Latest channel message has no file_id.")
            return False
        self._logger.info(
            "Latest backup message found (name=%s).",
            backup_name or "-",
        )

        if on_status:
            on_status("در حال دریافت فایل پشتیبان...")
        file_path = self._get_file_path(client, file_id)
        if not file_path:
            self._logger.warning("Backup file path not resolved from Bale.")
            return False

        download_url = client.build_file_url(file_path)
        try:
            response = requests.get(download_url, timeout=60)
            response.raise_for_status()
        except requests.RequestException as exc:
            if raise_errors:
                raise RuntimeError("دانلود فایل پشتیبان ناموفق بود.") from exc
            self._logger.exception("Backup download failed.")
            return False

        if on_status:
            on_status("در حال استخراج فایل پشتیبان...")
        payload = response.content
        self._logger.info("Backup download size: %d bytes.", len(payload))
        db_bytes, stock_bytes = self._extract_files(payload)
        if not db_bytes and not stock_bytes:
            self._logger.warning("Backup archive contained no known files.")
            return False
        self._logger.info(
            "Backup contents (db=%s, stock=%s).",
            "yes" if db_bytes else "no",
            "yes" if stock_bytes else "no",
        )

        if db_bytes and self._db_matches_backup(db_bytes):
            self._logger.info(
                "Local database matches backup hash. Skipping DB restore."
            )
            db_bytes = None
        if stock_bytes and self._stock_matches_backup(stock_bytes):
            self._logger.info(
                "Local stock matches backup hash. Skipping stock restore."
            )
            stock_bytes = None

        if not db_bytes and not stock_bytes:
            if on_status:
                on_status("نسخه پشتیبان با فایل‌های فعلی یکسان است.")
            if backup_name:
                self._store_backup_name(backup_name)
            self._logger.info("Backup matches local files. Restore skipped.")
            return True

        if db_bytes:
            if on_status:
                on_status("در حال جایگزینی پایگاه داده...")
        if stock_bytes:
            if on_status:
                on_status("در حال جایگزینی فایل موجودی...")

        if db_bytes or stock_bytes:
            if db_bytes and not self.db_path.exists():
                self.missing_files.append(self.db_path.name)
            if stock_bytes and not self.stock_path.exists():
                self.missing_files.append(self.stock_path.name)
            if self.missing_files:
                self._logger.info(
                    "Missing files before restore: %s",
                    ", ".join(self.missing_files),
                )
            with db_lock():
                if db_bytes:
                    replaced = self._atomic_replace(self.db_path, db_bytes)
                    if not replaced:
                        self.pending_files.append(self.db_path.name)
                if stock_bytes:
                    replaced = self._atomic_replace(
                        self.stock_path, stock_bytes
                    )
                    if not replaced:
                        self.pending_files.append(self.stock_path.name)
            if self.pending_files:
                self._logger.warning(
                    "Restore pending for locked files: %s",
                    ", ".join(self.pending_files),
                )
            if self.missing_files or self.pending_files:
                self.restart_required = True
                self._logger.info(
                    "Backup restored with restart required (missing=%s, pending=%s).",
                    ", ".join(self.missing_files) or "-",
                    ", ".join(self.pending_files) or "-",
                )
            else:
                self._logger.info("Backup restored successfully in-place.")

        if backup_name:
            self._store_backup_name(backup_name)

        if on_status:
            on_status("پاکسازی فایل‌های موقت...")
        self._logger.info("Backup restore finished.")
        return True

    def restart_message(self) -> str | None:
        if not self.restart_required:
            return None
        parts: list[str] = []
        if self.missing_files:
            missing_text = self._format_file_list(self.missing_files)
            parts.append(f"{missing_text} وجود نداشت و بازیابی شد")
        if self.pending_files:
            pending_text = self._format_file_list(self.pending_files)
            parts.append(
                f"{pending_text} در حال استفاده بود و در صف اعمال قرار گرفت"
            )
        if not parts:
            return None
        return " و ".join(parts) + ". لطفا برنامه را ببندید و دوباره اجرا کنید."

    @staticmethod
    def _format_file_list(files: list[str]) -> str:
        if len(files) == 1:
            return f"فایل {files[0]}"
        return "فایل‌های " + " و ".join(files)

    @staticmethod
    def _pending_restore_path(path: Path) -> Path:
        return path.with_name(f"{path.name}.restore")

    def apply_pending_restore(self) -> list[str]:
        restored: list[str] = []
        for path in (self.db_path, self.stock_path):
            pending_path = self._pending_restore_path(path)
            if not pending_path.exists():
                continue
            self._logger.info(
                "Applying pending restore file: %s -> %s",
                pending_path,
                path,
            )
            try:
                pending_path.replace(path)
                restored.append(path.name)
            except OSError:
                self._logger.exception(
                    "Failed to apply pending restore for %s", path
                )
        if restored:
            self._logger.info(
                "Applied pending restore files at startup: %s",
                ", ".join(restored),
            )
        return restored

    def _fetch_latest_update(
        self, client: BaleBotClient
    ) -> list[dict[str, Any]]:
        response = client.get_updates(offset=-1, limit=1, timeout_seconds=10)
        if not response.get("ok", False):
            return []
        return client.extract_updates(response)

    @staticmethod
    def _latest_channel_message(
        updates: Iterable[dict[str, Any]], channel_id: str
    ) -> dict[str, Any] | None:
        latest: tuple[int, dict[str, Any]] | None = None
        channel_key = str(channel_id).strip()
        for update in updates:
            message = update.get("message")
            if not isinstance(message, dict):
                continue
            if not _message_matches_channel(message, channel_key):
                continue
            if not BaleBackupRestorer._extract_file_id(message):
                continue
            update_id = update.get("update_id")
            if not isinstance(update_id, int):
                update_id = 0
            if latest is None or update_id > latest[0]:
                latest = (update_id, message)
        return latest[1] if latest else None

    @staticmethod
    def _extract_file_id(message: dict[str, Any]) -> str | None:
        document = message.get("document")
        if isinstance(document, dict):
            file_id = document.get("file_id")
            if isinstance(file_id, str) and file_id.strip():
                return file_id
        file_id = message.get("file_id")
        if isinstance(file_id, str) and file_id.strip():
            return file_id
        return None

    @staticmethod
    def _extract_file_name(message: dict[str, Any]) -> str | None:
        document = message.get("document")
        if isinstance(document, dict):
            file_name = document.get("file_name")
            if isinstance(file_name, str) and file_name.strip():
                return file_name
        return None

    def _store_backup_name(self, backup_name: str) -> None:
        if self.config.bale_last_backup_name != backup_name:
            self.config.bale_last_backup_name = backup_name
            self.config.save()

    @staticmethod
    def _get_file_path(client: BaleBotClient, file_id: str) -> str | None:
        response = client.get_file(file_id)
        if not response.get("ok"):
            return None
        result = response.get("result")
        if not isinstance(result, dict):
            return None
        file_path = result.get("file_path")
        if isinstance(file_path, str) and file_path.strip():
            return file_path
        return None

    def _resolve_stock_path(self) -> Path:
        if self.config.inventory_file:
            return Path(self.config.inventory_file)
        return app_dir() / DEFAULT_STOCK_NAME

    @staticmethod
    def _extract_files(payload: bytes) -> tuple[bytes | None, bytes | None]:
        db_bytes = None
        stock_bytes = None
        legacy_stock_name: str | None = None
        legacy_stock_bytes: bytes | None = None
        try:
            with zipfile.ZipFile(io.BytesIO(payload)) as zip_file:
                for name in zip_file.namelist():
                    filename = Path(name).name
                    normalized = filename.lower()
                    if normalized == DEFAULT_DB_NAME:
                        db_bytes = zip_file.read(name)
                    elif normalized == DEFAULT_STOCK_NAME:
                        stock_bytes = zip_file.read(name)
                    elif legacy_stock_bytes is None:
                        suffix = Path(filename).suffix.lower()
                        if suffix in {".dat", ".xlsx", ".xlsm"}:
                            legacy_stock_name = filename
                            legacy_stock_bytes = zip_file.read(name)
                if stock_bytes is None and legacy_stock_bytes is not None:
                    logger.info(
                        "Using legacy stock entry from backup archive: %s",
                        legacy_stock_name,
                    )
                    stock_bytes = legacy_stock_bytes
        except zipfile.BadZipFile:
            return None, None
        return db_bytes, stock_bytes

    @staticmethod
    def _sha256_bytes(payload: bytes) -> str:
        digest = hashlib.sha256()
        digest.update(payload)
        return digest.hexdigest()

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(_HASH_CHUNK_SIZE)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _quote_identifier(name: str) -> str:
        return f'"{name.replace('"', '""')}"'

    @staticmethod
    def _serialize_sql_value(value: Any) -> bytes:
        if value is None:
            return b"NULL"
        if isinstance(value, bytes):
            return b"BYTES:" + value
        return f"{type(value).__name__}:{value!r}".encode("utf-8")

    @classmethod
    def _hash_sqlite_connection(cls, conn: sqlite3.Connection) -> str:
        digest = hashlib.sha256()
        rows = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name ASC
            """
        ).fetchall()
        table_names = [str(row[0]) for row in rows]
        for table in table_names:
            if table in _IGNORED_DB_TABLES:
                continue
            digest.update(b"TBL:")
            digest.update(table.encode("utf-8"))
            columns = conn.execute(
                f"PRAGMA table_info({cls._quote_identifier(table)})"
            ).fetchall()
            col_names = [str(col[1]) for col in columns]
            digest.update(b"COLS:")
            digest.update(
                ",".join(
                    f"{col[1]}|{col[2]}|{col[3]}|{col[4]}|{col[5]}"
                    for col in columns
                ).encode("utf-8")
            )
            if not col_names:
                continue
            col_sql = ", ".join(
                cls._quote_identifier(name) for name in col_names
            )
            order_sql = ", ".join(
                cls._quote_identifier(name) for name in col_names
            )
            query = (
                f"SELECT {col_sql} FROM {cls._quote_identifier(table)} "
                f"ORDER BY {order_sql}"
            )
            for row in conn.execute(query):
                digest.update(b"ROW:")
                for value in row:
                    digest.update(b"|")
                    digest.update(cls._serialize_sql_value(value))
        return digest.hexdigest()

    @classmethod
    def _hash_sqlite_path(cls, path: Path) -> str | None:
        try:
            with sqlite3.connect(path) as conn:
                return cls._hash_sqlite_connection(conn)
        except sqlite3.Error:
            logger.exception("Failed hashing SQLite database: %s", path)
            return None

    def _hash_sqlite_bytes(self, payload: bytes) -> str | None:
        tmp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                prefix="armkala_db_hash_",
                suffix=".db",
                delete=False,
            ) as handle:
                handle.write(payload)
                tmp_path = Path(handle.name)
            return self._hash_sqlite_path(tmp_path)
        finally:
            if tmp_path is not None:
                try:
                    tmp_path.unlink()
                except OSError:
                    pass

    def _snapshot_db_for_hash(self) -> Path | None:
        if not self.db_path.exists():
            return None
        tmp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                prefix="armkala_db_hash_",
                suffix=".db",
                delete=False,
            ) as handle:
                tmp_path = Path(handle.name)
            with db_lock():
                with sqlite3.connect(self.db_path) as source:
                    with sqlite3.connect(tmp_path) as dest:
                        source.backup(dest)
            return tmp_path
        except Exception:
            logger.exception("Failed creating SQLite snapshot for hash.")
            if tmp_path is not None:
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
            return None

    def _hash_local_db(self) -> str | None:
        snapshot = self._snapshot_db_for_hash()
        if snapshot is None:
            return None
        try:
            return self._hash_sqlite_path(snapshot)
        finally:
            try:
                snapshot.unlink()
            except OSError:
                pass

    def _db_matches_backup(self, db_bytes: bytes) -> bool:
        if not self.db_path.exists():
            return False
        remote_hash = self._hash_sqlite_bytes(db_bytes)
        local_hash = self._hash_local_db()
        if not remote_hash or not local_hash:
            return False
        return remote_hash == local_hash

    def _stock_matches_backup(self, stock_bytes: bytes) -> bool:
        if not self.stock_path.exists():
            return False
        try:
            local_hash = self._sha256_file(self.stock_path)
        except OSError:
            logger.exception(
                "Failed hashing local stock file: %s", self.stock_path
            )
            return False
        remote_hash = self._sha256_bytes(stock_bytes)
        return local_hash == remote_hash

    @staticmethod
    def _atomic_replace(path: Path, data: bytes) -> bool:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            prefix=f"{path.stem}_",
            suffix=".tmp",
            dir=str(path.parent),
            delete=False,
        ) as handle:
            handle.write(data)
            temp_name = handle.name
        temp_path = Path(temp_name)
        last_exc: Exception | None = None
        for _ in range(4):
            try:
                temp_path.replace(path)
                return True
            except (PermissionError, OSError) as exc:
                last_exc = exc
                time.sleep(0.2)
        pending_path = BaleBackupRestorer._pending_restore_path(path)
        try:
            if pending_path.exists():
                try:
                    pending_path.unlink()
                except OSError:
                    pass
            temp_path.replace(pending_path)
        except Exception:
            try:
                os.remove(temp_name)
            except FileNotFoundError:
                pass
            if last_exc:
                raise last_exc
            raise
        return False


def _message_matches_channel(message: dict[str, Any], channel_id: str) -> bool:
    if channel_id.startswith("@"):
        username = channel_id.lstrip("@")
        chat = message.get("chat")
        if isinstance(chat, dict):
            chat_user = chat.get("username")
            if isinstance(chat_user, str) and chat_user == username:
                return True
        return False

    chat_id = message.get("chat_id")
    if chat_id is None:
        chat = message.get("chat")
        if isinstance(chat, dict):
            chat_id = chat.get("id")
    if chat_id is None:
        return False
    return str(chat_id) == channel_id


def restore_latest_backup_async(
    config: AppConfig | None = None,
    db_path: Path | None = None,
    stock_path: Path | None = None,
    ui_parent=None,
    on_restored=None,
) -> None:
    try:
        from PySide6.QtCore import QObject, QThread, Signal, Slot
        from PySide6.QtWidgets import QApplication, QMainWindow

        from app.ui.widgets.backup_progress_overlay import (
            BackupProgressOverlay,
        )
    except Exception:
        BaleBackupRestorer(
            config=config, db_path=db_path, stock_path=stock_path
        ).restore_latest_backup()
        return

    parent = _resolve_ui_parent(ui_parent, QMainWindow)
    if parent is None:
        BaleBackupRestorer(
            config=config, db_path=db_path, stock_path=stock_path
        ).restore_latest_backup()
        return

    overlay = getattr(parent, "_backup_overlay", None)
    if overlay is None:
        overlay = BackupProgressOverlay(parent=parent)
        parent._backup_overlay = overlay
    overlay.show_overlay()

    class RestoreWorker(QObject):
        status = Signal(str)
        finished = Signal(bool, bool, str)

        def __init__(self) -> None:
            super().__init__()

        @Slot()
        def run(self) -> None:
            restorer = BaleBackupRestorer(
                config=config, db_path=db_path, stock_path=stock_path
            )
            try:
                self.status.emit("در حال شروع بازیابی نسخه پشتیبان...")
                restored = restorer.restore_latest_backup(
                    on_status=self.status.emit, raise_errors=True
                )
                if restored:
                    restart_message = restorer.restart_message()
                    if restart_message:
                        self.finished.emit(True, False, restart_message)
                    else:
                        self.finished.emit(
                            True, True, "بازیابی نسخه پشتیبان انجام شد."
                        )
                else:
                    self.finished.emit(
                        True, False, "نسخه پشتیبان جدیدی یافت نشد."
                    )
            except Exception as exc:  # noqa: BLE001
                self.finished.emit(False, False, str(exc))

    class UiCallbacks(QObject):
        def __init__(
            self,
            overlay: BackupProgressOverlay,
            on_restored_callback,
        ) -> None:
            super().__init__(overlay)
            self._overlay = overlay
            self._on_restored = on_restored_callback

        @Slot(bool, bool, str)
        def handle_finished(
            self, success: bool, restored: bool, message: str
        ) -> None:
            self._overlay.mark_finished(success, message)
            if self._on_restored is not None and success and restored:
                self._on_restored()

    thread = QThread(parent)
    worker = RestoreWorker()
    ui_callbacks = UiCallbacks(overlay, on_restored)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.status.connect(overlay.set_status)
    worker.finished.connect(ui_callbacks.handle_finished)
    worker.finished.connect(thread.quit)
    thread.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)
    thread.start()
    parent._backup_restore_thread = thread
    parent._backup_restore_worker = worker
    parent._backup_restore_callbacks = ui_callbacks


def _resolve_ui_parent(ui_parent, main_window_type):
    if ui_parent is not None:
        try:
            window = ui_parent.window()
            if window is not None:
                return window
        except Exception:
            return ui_parent
        return ui_parent
    try:
        from PySide6.QtWidgets import QApplication
    except Exception:
        return None
    app = QApplication.instance()
    if app is None:
        return None
    active = app.activeWindow()
    if (
        active is not None
        and active.isVisible()
        and main_window_type is not None
        and isinstance(active, main_window_type)
    ):
        return active
    if main_window_type is not None:
        for widget in app.topLevelWidgets():
            if widget.isVisible() and isinstance(widget, main_window_type):
                return widget
    if active is not None and active.isVisible():
        return active
    for widget in app.topLevelWidgets():
        if widget.isVisible():
            return widget
    return None
