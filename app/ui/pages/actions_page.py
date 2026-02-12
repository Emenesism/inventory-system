from __future__ import annotations

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGraphicsBlurEffect,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.services.action_log_service import ActionEntry, ActionLogService
from app.utils.dates import to_jalali_datetime


class ActionsPage(QWidget):
    def __init__(
        self, action_service: ActionLogService, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setLayoutDirection(Qt.RightToLeft)
        self.action_service = action_service
        self._page_size = 200
        self._loaded_count = 0
        self._total_count = 0
        self._loading_more = False
        self._actions: list[ActionEntry] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(16)

        self._content = QWidget()
        content_layout = QVBoxLayout(self._content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(16)

        header = QHBoxLayout()
        title = QLabel(self.tr("اقدامات"))
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        header.addWidget(title)
        header.addStretch(1)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(self.tr("جستجو در اقدامات..."))
        self.search_input.textChanged.connect(self.refresh)
        header.addWidget(self.search_input)

        refresh_button = QPushButton(self.tr("بروزرسانی"))
        refresh_button.clicked.connect(self.refresh)
        header.addWidget(refresh_button)

        self.load_more_button = QPushButton(self.tr("موارد بیشتر"))
        self.load_more_button.clicked.connect(self._load_more)
        self.load_more_button.setEnabled(False)
        header.addWidget(self.load_more_button)
        content_layout.addLayout(header)

        summary_card = QFrame()
        summary_card.setObjectName("Card")
        summary_layout = QHBoxLayout(summary_card)
        summary_layout.setContentsMargins(16, 16, 16, 16)
        summary_layout.setSpacing(24)

        self.total_label = QLabel(self.tr("تعداد اقدامات: 0"))
        summary_layout.addWidget(self.total_label)
        summary_layout.addStretch(1)
        content_layout.addWidget(summary_card)

        list_card = QFrame()
        list_card.setObjectName("Card")
        list_layout = QVBoxLayout(list_card)
        list_layout.setContentsMargins(16, 16, 16, 16)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            [
                self.tr("تاریخ"),
                self.tr("ادمین"),
                self.tr("نوع"),
                self.tr("عنوان"),
            ]
        )
        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setDefaultSectionSize(32)
        if hasattr(self.table, "setUniformRowHeights"):
            self.table.setUniformRowHeights(True)
        self.table.itemSelectionChanged.connect(self._show_details)
        self.table.verticalScrollBar().valueChanged.connect(
            self._maybe_load_more
        )
        list_layout.addWidget(self.table)
        content_layout.addWidget(list_card)

        details_card = QFrame()
        details_card.setObjectName("Card")
        details_layout = QVBoxLayout(details_card)
        details_layout.setContentsMargins(16, 16, 16, 16)
        details_layout.setSpacing(12)

        self.details_label = QLabel(self.tr("جزئیات اقدام را انتخاب کنید."))
        details_layout.addWidget(self.details_label)

        self.details_text = QPlainTextEdit()
        self.details_text.setReadOnly(True)
        details_layout.addWidget(self.details_text)
        content_layout.addWidget(details_card)

        outer.addWidget(self._content)

        self._overlay = QFrame(self)
        self._overlay.setStyleSheet(
            "background: rgba(15, 23, 42, 0.55); border-radius: 16px;"
        )
        overlay_layout = QVBoxLayout(self._overlay)
        overlay_layout.setContentsMargins(0, 0, 0, 0)
        overlay_layout.addStretch(1)
        self._overlay.hide()

        self.refresh()
        self.set_accessible(False)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._overlay.setGeometry(self.rect())

    def set_accessible(self, accessible: bool) -> None:
        if accessible:
            self._content.setGraphicsEffect(None)
            self._content.setEnabled(True)
            self._overlay.hide()
        else:
            blur = QGraphicsBlurEffect(self)
            blur.setBlurRadius(12)
            self._content.setGraphicsEffect(blur)
            self._content.setEnabled(False)
            self._overlay.show()
            self._overlay.raise_()

    def refresh(self) -> None:
        self._actions = []
        self._loaded_count = 0
        search = self.search_input.text().strip()
        self._total_count = self.action_service.count_actions(
            search if search else None
        )
        self.total_label.setText(
            self.tr("تعداد اقدامات: {count}").format(count=self._total_count)
        )
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        self.table.blockSignals(False)
        self.details_label.setText(self.tr("جزئیات اقدام را انتخاب کنید."))
        self.details_text.clear()
        self._load_more()

    def _show_details(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        item = self.table.item(row, 0)
        if not item:
            return
        action_id = item.data(Qt.UserRole)
        action = next(
            (entry for entry in self._actions if entry.action_id == action_id),
            None,
        )
        if not action:
            return
        header = f"{action.title} | {to_jalali_datetime(action.created_at)}"
        self.details_label.setText(header)
        self.details_text.setPlainText(action.details)

    def _maybe_load_more(self) -> None:
        if self._loading_more or self._loaded_count >= self._total_count:
            return
        bar = self.table.verticalScrollBar()
        if bar.maximum() == 0:
            return
        if bar.value() >= bar.maximum() - 20:
            self._load_more()

    def _load_more(self) -> None:
        if self._loading_more or self._loaded_count >= self._total_count:
            self.load_more_button.setEnabled(False)
            return
        self._loading_more = True
        search = self.search_input.text().strip()
        batch = self.action_service.list_actions(
            limit=self._page_size,
            offset=self._loaded_count,
            search=search if search else None,
        )
        if not batch:
            self._loading_more = False
            self.load_more_button.setEnabled(False)
            return

        start_row = self.table.rowCount()
        self.table.setUpdatesEnabled(False)
        self.table.blockSignals(True)
        self.table.setRowCount(start_row + len(batch))
        for row_offset, entry in enumerate(batch):
            row_idx = start_row + row_offset
            date_item = QTableWidgetItem(to_jalali_datetime(entry.created_at))
            date_item.setData(Qt.UserRole, entry.action_id)
            self.table.setItem(row_idx, 0, date_item)
            admin_text = entry.admin_username or self.tr("نامشخص")
            self.table.setItem(row_idx, 1, QTableWidgetItem(admin_text))
            self.table.setItem(
                row_idx, 2, QTableWidgetItem(self._format_action(entry))
            )
            self.table.setItem(row_idx, 3, QTableWidgetItem(entry.title))
        self._actions.extend(batch)
        self._loaded_count += len(batch)
        self.table.blockSignals(False)
        self.table.setUpdatesEnabled(True)
        self._loading_more = False
        self.load_more_button.setEnabled(self._loaded_count < self._total_count)
        if start_row == 0 and self._actions:
            self.table.selectRow(0)

    def _format_action(self, entry: ActionEntry) -> str:
        t = lambda text: QCoreApplication.translate(  # noqa: E731
            "ActionsPage", text
        )
        mapping = {
            "sales_import": t("ثبت فروش"),
            "sales_manual_invoice": t("ثبت فاکتور فروش دستی"),
            "sales_import_export": t("خروجی مغایرت‌های فروش"),
            "purchase_invoice": t("ثبت خرید"),
            "inventory_edit": t("ویرایش موجودی"),
            "invoice_edit": t("ویرایش فاکتور"),
            "invoice_delete": t("حذف فاکتور"),
            "invoice_export": t("خروجی فاکتور"),
            "invoice_batch_export": t("خروجی گروهی فاکتورها"),
            "low_stock_export": t("خروجی کمبود موجودی"),
            "inventory_export": t("خروجی موجودی"),
            "basalam_fetch": t("دریافت باسلام"),
            "basalam_export": t("خروجی باسلام"),
            "password_change": t("تغییر رمز عبور"),
            "auto_lock_update": t("تغییر قفل خودکار"),
            "admin_create": t("ایجاد ادمین"),
            "admin_delete": t("حذف ادمین"),
            "reports_export": t("خروجی گزارش"),
            "login": t("ورود"),
            "logout": t("خروج"),
        }
        return mapping.get(entry.action_type, entry.action_type)
