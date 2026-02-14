from __future__ import annotations

from html import escape

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGraphicsBlurEffect,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
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

        self.details_text = QTextEdit()
        self.details_text.setReadOnly(True)
        self.details_text.setLineWrapMode(QTextEdit.WidgetWidth)
        self.details_text.setLayoutDirection(Qt.RightToLeft)
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
        self._show_action_details(action)

    def _show_action_details(self, action: ActionEntry) -> None:
        if action.action_type == "inventory_edit":
            rendered = self._render_inventory_edit_details(action.details)
            if rendered:
                self._set_html_details(rendered)
                return
        self._set_plain_details(action.details)

    def _set_html_details(self, body_html: str) -> None:
        html = (
            "<html><head><meta charset='utf-8'>"
            "<style>"
            "body{font-family:Vazirmatn,Tahoma,sans-serif; text-align:right; margin:0; padding:0;}"
            "table{width:100%; border-collapse:collapse; table-layout:fixed;}"
            "th,td{text-align:right; vertical-align:middle;}"
            "</style></head><body>" + body_html + "</body></html>"
        )
        self.details_text.setHtml(html)
        self.details_text.setAlignment(Qt.AlignRight)

    def _set_plain_details(self, text: str) -> None:
        safe = escape(text or "")
        self._set_html_details(
            "<div style='text-align:right; white-space:pre-wrap;'>"
            + safe
            + "</div>"
        )

    def _render_inventory_edit_details(self, details: str) -> str | None:
        text = str(details or "").strip()
        if not text:
            return None
        blocks = [part.strip() for part in text.split("\n\n") if part.strip()]
        if len(blocks) < 2:
            return None

        summary = blocks[0]
        section_html: list[str] = []
        for block in blocks[1:]:
            lines = [
                line.strip() for line in block.splitlines() if line.strip()
            ]
            if not lines:
                continue

            title = lines[0]
            try:
                before_idx = lines.index("قبل:")
                after_idx = lines.index("بعد:")
            except ValueError:
                continue
            if after_idx <= before_idx:
                continue

            before_lines = lines[before_idx + 1 : after_idx]
            after_lines = lines[after_idx + 1 :]

            before_table = self._inventory_snapshot_to_html(before_lines)
            after_table = self._inventory_snapshot_to_html(after_lines)
            section_html.append(
                "<div style='margin-top:12px; padding:12px; border:1px solid #cbd5e1; border-radius:10px; background:#f8fafc; direction:rtl; text-align:right;'>"
                f"<div style='font-weight:700; margin-bottom:10px;'>{escape(title)}</div>"
                "<div style='margin-bottom:12px; padding:8px; border:1px solid #d1d5db; border-radius:8px; background:#ffffff;'>"
                "<div style='font-weight:700; margin-bottom:8px;'>قبل</div>"
                f"{before_table}"
                "</div>"
                "<div style='padding:8px; border:1px solid #d1d5db; border-radius:8px; background:#ffffff;'>"
                "<div style='font-weight:700; margin-bottom:8px;'>بعد</div>"
                f"{after_table}"
                "</div>"
                "</div>"
            )

        if not section_html:
            return None

        return (
            "<div style='text-align:right;'>"
            f"<div style='font-weight:700; margin-bottom:10px; line-height:1.6;'>{escape(summary)}</div>"
            + "".join(section_html)
            + "</div>"
        )

    def _inventory_snapshot_to_html(self, lines: list[str]) -> str:
        if not lines:
            return (
                "<div style='padding:8px; border:1px dashed #cbd5e1; "
                "border-radius:6px; color:#475569;'>(هیچ)</div>"
            )
        marker = lines[0].strip()
        if marker in {"(هیچ)", "(وجود ندارد)", "(حذف شد)"}:
            return (
                "<div style='padding:8px; border:1px dashed #cbd5e1; "
                "border-radius:6px; color:#475569;'>"
                + escape(marker)
                + "</div>"
            )

        header_parts = [part.strip() for part in lines[0].split("|")]
        value_parts: list[str] = []
        if len(lines) > 1:
            value_parts = [part.strip() for part in lines[1].split("|")]
        if not value_parts:
            value_parts = [""] * len(header_parts)
        if len(value_parts) < len(header_parts):
            value_parts.extend([""] * (len(header_parts) - len(value_parts)))
        if len(value_parts) > len(header_parts):
            value_parts = value_parts[: len(header_parts)]
        # QTextEdit rich-text tables often ignore RTL column flow; reverse explicitly.
        header_parts = list(reversed(header_parts))
        value_parts = list(reversed(value_parts))

        head_html = "".join(
            "<th style='border:1px solid #d1d5db; background:#f3f4f6; padding:6px; text-align:right;'>"
            f"{escape(part)}"
            "</th>"
            for part in header_parts
        )
        row_html = "".join(
            "<td style='border:1px solid #d1d5db; padding:6px; text-align:right;'>"
            f"{escape(part)}"
            "</td>"
            for part in value_parts
        )
        return (
            "<div style='display:block; width:100%;'>"
            "<table width='100%' cellspacing='0' cellpadding='0' "
            "style='width:100%; border-collapse:collapse; table-layout:fixed;'>"
            f"<tr>{head_html}</tr><tr>{row_html}</tr>"
            "</table>"
            "</div>"
        )

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
            "purchase_invoice": t("ثبت فاکتور خرید"),
            "inventory_edit": t("ویرایش موجودی"),
            "invoice_edit": t("ویرایش فاکتور"),
            "invoice_delete": t("حذف فاکتور"),
            "invoice_product_rename": t("به‌روزرسانی نام کالا در فاکتورها"),
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
