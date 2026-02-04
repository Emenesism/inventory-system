from __future__ import annotations

import logging
import sqlite3
import tempfile
import threading
import zipfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import requests

from app.core.config import AppConfig
from app.core.db_lock import db_connection
from app.core.paths import app_dir
from app.services.bale_bot_service import (
    REQUEST_FORMAT_MULTIPART,
    BaleBotClient,
)
from app.utils.dates import jalali_today, to_jalali_datetime

DEFAULT_DB_NAME = "invoices.db"
DEFAULT_STOCK_NAME = "stock.dat"

_backup_state = threading.local()

_REASON_LABELS = {
    "purchase_invoice": "ثبت فاکتور خرید",
    "sales_import": "ثبت فاکتور فروش (ایمپورت)",
    "sales_manual": "ثبت فاکتور فروش دستی",
    "invoice_change": "ویرایش/حذف فاکتور",
    "invoice_purchase_created": "ثبت فاکتور خرید",
    "invoice_sales_created": "ثبت فاکتور فروش",
    "invoice_updated": "ویرایش فاکتور",
    "invoice_deleted": "حذف فاکتور",
    "inventory_saved": "ذخیره موجودی",
    "admin_created": "ایجاد مدیر",
    "admin_password_updated": "تغییر رمز مدیر",
    "admin_auto_lock_updated": "تغییر قفل خودکار",
    "admin_deleted": "حذف مدیر",
    "admin_default_created": "ایجاد مدیر پیش‌فرض",
    "basalam_ids": "به‌روزرسانی شناسه‌های باسلام",
}


def _format_reason(reason: str | None) -> str | None:
    if not reason:
        return None
    parts = [part.strip() for part in reason.split(",") if part.strip()]
    if not parts:
        return None
    labels: list[str] = []
    seen: set[str] = set()
    for item in parts:
        label = _REASON_LABELS.get(item, item)
        if label in seen:
            continue
        labels.append(label)
        seen.add(label)
    return "، ".join(labels) if labels else None


def _normalize_admin_username(admin_username: str | None) -> str | None:
    if not admin_username:
        return None
    value = str(admin_username).strip()
    return value or None


def _get_backup_state() -> threading.local:
    if not hasattr(_backup_state, "depth"):
        _backup_state.depth = 0
        _backup_state.pending = False
        _backup_state.reasons = set()
        _backup_state.config = None
        _backup_state.db_path = None
        _backup_state.stock_path = None
        _backup_state.admin_username = None
    return _backup_state


def _update_backup_state(
    state: threading.local,
    reason: str | None,
    config: AppConfig | None,
    db_path: Path | None,
    stock_path: Path | None,
    admin_username: str | None,
) -> None:
    if reason:
        state.reasons.add(str(reason))
    if config is not None:
        state.config = config
    if db_path is not None:
        state.db_path = db_path
    if stock_path is not None:
        state.stock_path = stock_path
    admin_username = _normalize_admin_username(admin_username)
    if admin_username is not None:
        state.admin_username = admin_username


@contextmanager
def backup_batch(reason: str | None = None, admin_username: str | None = None):
    state = _get_backup_state()
    state.depth += 1
    _update_backup_state(state, reason, None, None, None, admin_username)
    try:
        yield
    finally:
        state.depth -= 1
        if state.depth <= 0:
            state.depth = 0
            if state.pending:
                reason_text = (
                    ", ".join(sorted(state.reasons)) if state.reasons else None
                )
                _dispatch_backup(
                    reason=reason_text,
                    config=state.config,
                    db_path=state.db_path,
                    stock_path=state.stock_path,
                    admin_username=state.admin_username,
                )
            state.pending = False
            state.reasons = set()
            state.config = None
            state.db_path = None
            state.stock_path = None
            state.admin_username = None


class BackupSender:
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

    def send_backup(
        self,
        reason: str | None = None,
        on_status=None,
        raise_errors: bool = False,
        admin_username: str | None = None,
    ) -> bool:
        token = (self.config.bot_token or "").strip()
        chat_id = (self.config.channel_id or "").strip()
        if not token or not chat_id:
            self._logger.info("Backup skipped (missing bot_token/channel_id).")
            if raise_errors:
                raise RuntimeError("تنظیمات ربات یا کانال ناقص است.")
            return False

        try:
            with tempfile.TemporaryDirectory(
                prefix="armkala_backup_"
            ) as temp_dir:
                temp_path = Path(temp_dir)
                zip_path = self._create_backup_zip(
                    temp_path, on_status=on_status
                )
                if zip_path is None:
                    if on_status:
                        on_status("هیچ فایلی برای پشتیبان یافت نشد.")
                    return False
                if on_status:
                    on_status("در حال ارسال نسخه پشتیبان به کانال...")
                caption = self._build_caption(
                    reason, admin_username=admin_username
                )
                client = BaleBotClient(token=token)
                client.send_document(
                    chat_id=chat_id,
                    document=zip_path,
                    caption=caption,
                    request_format=REQUEST_FORMAT_MULTIPART,
                )
                return True
        except requests.RequestException as exc:
            self._logger.exception("Backup upload failed.")
            if raise_errors:
                raise RuntimeError("ارسال نسخه پشتیبان ناموفق بود.") from exc
            return False
        except Exception:  # noqa: BLE001
            self._logger.exception("Backup failed.")
            if raise_errors:
                raise
            return False

    def _create_backup_zip(self, temp_dir: Path, on_status=None) -> Path | None:
        date_stamp = _jalali_date_stamp()
        zip_path = temp_dir / f"{date_stamp}.zip"
        db_snapshot = None

        if self.db_path.exists():
            db_snapshot = temp_dir / DEFAULT_DB_NAME
            if on_status:
                on_status("در حال تهیه نسخه پشتیبان از پایگاه داده...")
            self._snapshot_db(db_snapshot)

        stock_path = self.stock_path if self.stock_path else None
        if stock_path and not stock_path.exists():
            self._logger.warning("Stock file not found: %s", stock_path)
            stock_path = None
        if stock_path and on_status:
            on_status("در حال آماده‌سازی فایل موجودی...")

        if db_snapshot is None and stock_path is None:
            self._logger.warning("No files available for backup.")
            return None

        if on_status:
            on_status("در حال فشرده‌سازی فایل‌ها...")
        with zipfile.ZipFile(
            zip_path, "w", compression=zipfile.ZIP_DEFLATED
        ) as zip_file:
            if db_snapshot is not None and db_snapshot.exists():
                zip_file.write(db_snapshot, arcname=DEFAULT_DB_NAME)
            if stock_path is not None:
                arcname = (
                    DEFAULT_STOCK_NAME
                    if stock_path.name == DEFAULT_STOCK_NAME
                    else stock_path.name
                )
                zip_file.write(stock_path, arcname=arcname)

        return zip_path

    def _snapshot_db(self, target_path: Path) -> None:
        try:
            with db_connection(self.db_path, foreign_keys=False) as source:
                with sqlite3.connect(target_path) as dest:
                    source.backup(dest)
        except sqlite3.Error as exc:
            raise RuntimeError("SQLite backup failed.") from exc

    def _resolve_stock_path(self) -> Path | None:
        if self.config.inventory_file:
            return Path(self.config.inventory_file)
        return app_dir() / DEFAULT_STOCK_NAME

    @staticmethod
    def _build_caption(
        reason: str | None, admin_username: str | None = None
    ) -> str:
        timestamp = _jalali_timestamp()
        reason_text = _format_reason(reason)
        admin_username = _normalize_admin_username(admin_username)
        lines = ["نسخه پشتیبان خودکار"]
        if admin_username:
            lines.append(f"کاربر: {admin_username}")
        if reason_text:
            lines.append(f"دلیل: {reason_text}")
        lines.append(f"زمان: {timestamp}")
        return "\n".join(lines)


def _jalali_date_stamp() -> str:
    jy, jm, jd = jalali_today()
    now_time = datetime.now().strftime("%H-%M-%S")
    return f"{jy:04d}-{jm:02d}-{jd:02d}_{now_time}"


def _jalali_timestamp() -> str:
    now_iso = datetime.now().isoformat(timespec="seconds")
    return to_jalali_datetime(now_iso)


def send_backup(
    reason: str | None = None,
    config: AppConfig | None = None,
    db_path: Path | None = None,
    stock_path: Path | None = None,
    async_mode: bool | None = None,
    ui_parent=None,
    admin_username: str | None = None,
) -> None:
    state = _get_backup_state()
    admin_username = _normalize_admin_username(admin_username)
    if state.depth > 0:
        state.pending = True
        _update_backup_state(
            state, reason, config, db_path, stock_path, admin_username
        )
        return
    _dispatch_backup(
        reason=reason,
        config=config,
        db_path=db_path,
        stock_path=stock_path,
        async_mode=async_mode,
        ui_parent=ui_parent,
        admin_username=admin_username,
    )


def _send_backup_now(
    reason: str | None = None,
    config: AppConfig | None = None,
    db_path: Path | None = None,
    stock_path: Path | None = None,
    admin_username: str | None = None,
) -> None:
    BackupSender(
        config=config, db_path=db_path, stock_path=stock_path
    ).send_backup(reason=reason, admin_username=admin_username)


def _can_use_qt() -> bool:
    try:
        from PySide6.QtCore import QThread  # type: ignore
        from PySide6.QtWidgets import QApplication  # type: ignore
    except Exception:
        return False
    app = QApplication.instance()
    if app is None:
        return False
    return QThread.currentThread() == app.thread()


def _dispatch_backup(
    reason: str | None = None,
    config: AppConfig | None = None,
    db_path: Path | None = None,
    stock_path: Path | None = None,
    async_mode: bool | None = None,
    ui_parent=None,
    admin_username: str | None = None,
) -> None:
    admin_username = _normalize_admin_username(admin_username)
    if async_mode is None:
        if _schedule_async_on_ui_thread(
            reason=reason,
            config=config,
            db_path=db_path,
            stock_path=stock_path,
            ui_parent=ui_parent,
            admin_username=admin_username,
        ):
            return
        async_mode = _can_use_qt()
    if async_mode:
        _send_backup_async_ui(
            reason=reason,
            config=config,
            db_path=db_path,
            stock_path=stock_path,
            ui_parent=ui_parent,
            admin_username=admin_username,
        )
    else:
        _send_backup_now(
            reason=reason,
            config=config,
            db_path=db_path,
            stock_path=stock_path,
            admin_username=admin_username,
        )


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


def _schedule_async_on_ui_thread(
    reason: str | None,
    config: AppConfig | None,
    db_path: Path | None,
    stock_path: Path | None,
    ui_parent=None,
    admin_username: str | None = None,
) -> bool:
    try:
        from PySide6.QtCore import QMetaObject, QObject, Qt, QThread, Slot
        from PySide6.QtWidgets import QApplication
    except Exception:
        return False
    app = QApplication.instance()
    if app is None:
        return False
    if QThread.currentThread() == app.thread():
        return False

    class _UiInvoker(QObject):
        def __init__(self, fn, parent=None) -> None:
            super().__init__(parent)
            self._fn = fn

        @Slot()
        def run(self) -> None:
            try:
                self._fn()
            finally:
                self.deleteLater()

    def _invoke() -> None:
        _dispatch_backup(
            reason=reason,
            config=config,
            db_path=db_path,
            stock_path=stock_path,
            async_mode=True,
            ui_parent=ui_parent,
            admin_username=admin_username,
        )

    invoker = _UiInvoker(_invoke, parent=app)
    invoker.moveToThread(app.thread())
    QMetaObject.invokeMethod(invoker, "run", Qt.QueuedConnection)
    return True


def _send_backup_async_ui(
    reason: str | None,
    config: AppConfig | None,
    db_path: Path | None,
    stock_path: Path | None,
    ui_parent=None,
    admin_username: str | None = None,
) -> None:
    try:
        from PySide6.QtCore import QObject, QThread, Signal, Slot
        from PySide6.QtWidgets import QApplication, QMainWindow

        from app.ui.widgets.backup_progress_overlay import (
            BackupProgressOverlay,
        )
    except Exception:
        _send_backup_now(
            reason=reason,
            config=config,
            db_path=db_path,
            stock_path=stock_path,
            admin_username=admin_username,
        )
        return

    parent = _resolve_ui_parent(ui_parent, QMainWindow)
    if parent is None:
        _send_backup_now(
            reason=reason,
            config=config,
            db_path=db_path,
            stock_path=stock_path,
            admin_username=admin_username,
        )
        return

    overlay = getattr(parent, "_backup_overlay", None)
    if overlay is None:
        overlay = BackupProgressOverlay(parent=parent)
        parent._backup_overlay = overlay
    overlay.show_overlay()

    class BackupWorker(QObject):
        status = Signal(str)
        finished = Signal(bool, str)

        def __init__(self) -> None:
            super().__init__()

        @Slot()
        def run(self) -> None:
            sender = BackupSender(
                config=config, db_path=db_path, stock_path=stock_path
            )
            try:
                self.status.emit("در حال شروع فرآیند پشتیبان‌گیری...")
                sent = sender.send_backup(
                    reason=reason,
                    on_status=self.status.emit,
                    raise_errors=True,
                    admin_username=admin_username,
                )
                if sent:
                    self.finished.emit(True, "نسخه پشتیبان ارسال شد.")
                else:
                    self.finished.emit(True, "فایلی برای پشتیبان نبود.")
            except Exception as exc:  # noqa: BLE001
                self.finished.emit(False, str(exc))

    thread = QThread(parent)
    worker = BackupWorker()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.status.connect(overlay.set_status)
    worker.finished.connect(overlay.mark_finished)
    worker.finished.connect(thread.quit)
    thread.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)
    thread.start()
    parent._backup_thread = thread
    parent._backup_worker = worker
