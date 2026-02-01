from __future__ import annotations

import io
import logging
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Iterable

import requests

from app.core.config import AppConfig
from app.core.paths import app_dir
from app.services.bale_bot_service import BaleBotClient

DEFAULT_DB_NAME = "invoices.db"
DEFAULT_STOCK_NAME = "stock.dat"

logger = logging.getLogger(__name__)


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

    def restore_latest_backup(
        self, on_status=None, raise_errors: bool = False
    ) -> bool:
        token = (self.config.bot_token or "").strip()
        channel_id = (self.config.channel_id or "").strip()
        if not token or not channel_id:
            if raise_errors:
                raise RuntimeError("تنظیمات ربات یا کانال ناقص است.")
            return False

        client = BaleBotClient(token=token)
        if on_status:
            on_status("در حال دریافت بروزرسانی‌ها از بله...")
        updates = self._fetch_latest_update(client)

        if on_status:
            on_status("در حال بررسی پیام‌های کانال پشتیبان...")
        latest_message = self._latest_channel_message(updates, channel_id)
        if latest_message is None:
            return False

        backup_name = self._extract_file_name(latest_message)
        file_id = self._extract_file_id(latest_message)
        if not file_id:
            return False

        if on_status:
            on_status("در حال دریافت فایل پشتیبان...")
        file_path = self._get_file_path(client, file_id)
        if not file_path:
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
        db_bytes, stock_bytes = self._extract_files(payload)
        if not db_bytes and not stock_bytes:
            return False

        if db_bytes:
            if on_status:
                on_status("در حال جایگزینی پایگاه داده...")
            self._atomic_replace(self.db_path, db_bytes)

        if stock_bytes:
            if on_status:
                on_status("در حال جایگزینی فایل موجودی...")
            self._atomic_replace(self.stock_path, stock_bytes)

        if backup_name:
            self._store_backup_name(backup_name)

        if on_status:
            on_status("پاکسازی فایل‌های موقت...")
        return True

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
        try:
            with zipfile.ZipFile(io.BytesIO(payload)) as zip_file:
                for name in zip_file.namelist():
                    filename = Path(name).name.lower()
                    if filename == DEFAULT_DB_NAME:
                        db_bytes = zip_file.read(name)
                    if filename == DEFAULT_STOCK_NAME:
                        stock_bytes = zip_file.read(name)
        except zipfile.BadZipFile:
            return None, None
        return db_bytes, stock_bytes

    @staticmethod
    def _atomic_replace(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            prefix=f"{path.stem}_",
            suffix=".tmp",
            dir=str(path.parent),
            delete=False,
        ) as handle:
            handle.write(data)
            temp_name = handle.name
        Path(temp_name).replace(path)


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
