from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QCompleter,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.services.action_log_service import ActionLogService
from app.services.inventory_service import InventoryService
from app.services.invoice_service import InvoiceService, InvoiceSummary
from app.ui.widgets.toast import ToastManager
from app.utils import dialogs
from app.utils.dates import (
    jalali_month_days,
    jalali_to_gregorian,
    jalali_today,
    to_jalali_datetime,
)
from app.utils.excel import export_invoices_excel
from app.utils.numeric import format_amount
from app.utils.text import normalize_text


class JalaliDatePicker(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.year_combo = QComboBox()
        self.month_combo = QComboBox()
        self.day_combo = QComboBox()

        for year in range(1390, 1451):
            self.year_combo.addItem(str(year), year)
        for month in range(1, 13):
            self.month_combo.addItem(f"{month:02d}", month)

        layout.addWidget(self.year_combo)
        layout.addWidget(self.month_combo)
        layout.addWidget(self.day_combo)

        self.year_combo.currentIndexChanged.connect(self._refresh_days)
        self.month_combo.currentIndexChanged.connect(self._refresh_days)

        jy, jm, jd = jalali_today()
        self.set_jalali_date(jy, jm, jd)

    def set_jalali_date(self, jy: int, jm: int, jd: int) -> None:
        self.year_combo.setCurrentText(str(jy))
        month_index = max(1, min(jm, 12)) - 1
        self.month_combo.setCurrentIndex(month_index)
        self._refresh_days()
        day_index = max(1, min(jd, self.day_combo.count())) - 1
        self.day_combo.setCurrentIndex(day_index)

    def _refresh_days(self) -> None:
        jy = int(self.year_combo.currentData())
        jm = int(self.month_combo.currentData())
        current_day = self.day_combo.currentData()
        max_day = jalali_month_days(jy, jm)

        self.day_combo.blockSignals(True)
        self.day_combo.clear()
        for day in range(1, max_day + 1):
            self.day_combo.addItem(f"{day:02d}", day)
        if isinstance(current_day, int) and 1 <= current_day <= max_day:
            self.day_combo.setCurrentIndex(current_day - 1)
        self.day_combo.blockSignals(False)

    def jalali_date(self) -> tuple[int, int, int]:
        jy = int(self.year_combo.currentData())
        jm = int(self.month_combo.currentData())
        jd = int(self.day_combo.currentData())
        return jy, jm, jd

    def to_gregorian_datetime(self, end_of_day: bool = False) -> datetime:
        jy, jm, jd = self.jalali_date()
        gy, gm, gd = jalali_to_gregorian(jy, jm, jd)
        if end_of_day:
            return datetime(
                gy, gm, gd, 23, 59, 59, tzinfo=ZoneInfo("Asia/Tehran")
            )
        return datetime(gy, gm, gd, 0, 0, 0, tzinfo=ZoneInfo("Asia/Tehran"))


class InvoiceBatchExportDialog(QDialog):
    def __init__(
        self,
        invoice_service: InvoiceService,
        inventory_service: InventoryService | None = None,
        action_log_service: ActionLogService | None = None,
        current_admin_provider=None,
        toast: ToastManager | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.invoice_service = invoice_service
        self.inventory_service = inventory_service
        self.action_log_service = action_log_service
        self._current_admin_provider = current_admin_provider
        self.toast = toast
        self._invoices: list[InvoiceSummary] = []
        self._product_map: dict[str, str] = {}

        self.setWindowTitle("Factor Export")
        self.setModal(True)
        if parent is not None:
            self.resize(parent.size())
        else:
            self.resize(1100, 720)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("Export Invoices (Factor)")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        layout.addWidget(title)

        date_card = QFrame()
        date_card.setObjectName("Card")
        date_layout = QVBoxLayout(date_card)
        date_layout.setContentsMargins(16, 16, 16, 16)
        date_layout.setSpacing(10)

        row = QHBoxLayout()
        row.addWidget(QLabel("From:"))
        self.from_date = JalaliDatePicker()
        row.addWidget(self.from_date)
        row.addSpacing(20)
        row.addWidget(QLabel("Until:"))
        self.to_date = JalaliDatePicker()
        row.addWidget(self.to_date)
        row.addStretch(1)
        date_layout.addLayout(row)

        product_row = QHBoxLayout()
        product_row.addWidget(QLabel("Product:"))
        self.product_input = QLineEdit()
        self.product_input.setPlaceholderText("Product (optional)")
        product_row.addWidget(self.product_input, 1)
        date_layout.addLayout(product_row)

        self.product_hint = QLabel("")
        self.product_hint.setProperty("textRole", "muted")
        self.product_hint.setProperty("size", "small")
        date_layout.addWidget(self.product_hint)

        self.summary_label = QLabel("Invoices: 0")
        self.summary_label.setStyleSheet("font-weight: 600;")
        date_layout.addWidget(self.summary_label)

        layout.addWidget(date_card)

        table_card = QFrame()
        table_card.setObjectName("Card")
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(16, 16, 16, 16)
        table_layout.setSpacing(8)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["ID", "Date (IR)", "Type", "Lines", "Qty", "Total"]
        )
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setDefaultSectionSize(30)
        table_layout.addWidget(self.table)
        layout.addWidget(table_card, 1)

        action_row = QHBoxLayout()
        action_row.addStretch(1)
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.reject)
        action_row.addWidget(self.close_button)
        self.export_button = QPushButton("Export")
        self.export_button.clicked.connect(self._export)
        action_row.addWidget(self.export_button)
        layout.addLayout(action_row)

        today_dt = datetime.now(ZoneInfo("Asia/Tehran"))
        start_dt = today_dt - timedelta(days=30)
        self._set_picker_from_gregorian(self.from_date, start_dt)
        self._set_picker_from_gregorian(self.to_date, today_dt)
        self.from_date.year_combo.currentIndexChanged.connect(self._reload)
        self.from_date.month_combo.currentIndexChanged.connect(self._reload)
        self.from_date.day_combo.currentIndexChanged.connect(self._reload)
        self.to_date.year_combo.currentIndexChanged.connect(self._reload)
        self.to_date.month_combo.currentIndexChanged.connect(self._reload)
        self.to_date.day_combo.currentIndexChanged.connect(self._reload)
        self.product_input.textChanged.connect(self._reload)
        self._setup_product_completer()
        self._reload()

    def _reload(self) -> None:
        start_dt = self.from_date.to_gregorian_datetime(end_of_day=False)
        end_dt = self.to_date.to_gregorian_datetime(end_of_day=True)
        if end_dt < start_dt:
            self.summary_label.setText("End date must be after start date.")
            self.export_button.setEnabled(False)
            self.table.setRowCount(0)
            return
        start_iso = start_dt.isoformat(timespec="seconds")
        end_iso = end_dt.isoformat(timespec="seconds")
        product_filter, fuzzy = self._resolve_product_filter()
        self._invoices = self.invoice_service.list_invoices_between(
            start_iso, end_iso, product_filter=product_filter, fuzzy=fuzzy
        )
        self._populate_table()
        self.export_button.setEnabled(bool(self._invoices))

    @staticmethod
    def _set_picker_from_gregorian(
        picker: JalaliDatePicker, dt: datetime
    ) -> None:
        jalali_text = to_jalali_datetime(
            dt.isoformat(timespec="seconds")
        ).split(" ")[0]
        try:
            jy, jm, jd = (int(part) for part in jalali_text.split("/"))
        except ValueError:
            return
        picker.set_jalali_date(jy, jm, jd)

    def _populate_table(self) -> None:
        self.table.setRowCount(len(self._invoices))
        for row_idx, invoice in enumerate(self._invoices):
            self.table.setItem(
                row_idx, 0, QTableWidgetItem(str(invoice.invoice_id))
            )
            self.table.setItem(
                row_idx,
                1,
                QTableWidgetItem(to_jalali_datetime(invoice.created_at)),
            )
            self.table.setItem(
                row_idx,
                2,
                QTableWidgetItem(
                    "Sales" if invoice.invoice_type == "sales" else "Purchase"
                ),
            )
            lines_item = QTableWidgetItem(str(invoice.total_lines))
            lines_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row_idx, 3, lines_item)
            qty_item = QTableWidgetItem(str(invoice.total_qty))
            qty_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row_idx, 4, qty_item)
            total_item = QTableWidgetItem(format_amount(invoice.total_amount))
            total_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row_idx, 5, total_item)
        self.summary_label.setText(f"Invoices: {len(self._invoices)}")

    def _setup_product_completer(self) -> None:
        if not self.inventory_service or not self.inventory_service.is_loaded():
            self.product_hint.setText(
                "Inventory not loaded; product suggestions unavailable."
            )
            return
        product_names = self.inventory_service.get_product_names()
        self._product_map = {
            normalize_text(name): name for name in product_names
        }
        completer = QCompleter(product_names, self)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        self.product_input.setCompleter(completer)
        self.product_hint.setText("Type to search products.")

    def _resolve_product_filter(self) -> tuple[str | None, bool]:
        text = self.product_input.text().strip()
        if not text:
            self.product_hint.setText(
                "Type to search products." if self._product_map else ""
            )
            return None, False
        normalized = normalize_text(text)
        if normalized in self._product_map:
            self.product_hint.setText("")
            return self._product_map[normalized], False
        if self._product_map:
            self.product_hint.setText(
                "Product not found in inventory; using partial search."
            )
        return text, True

    def _export(self) -> None:
        if not self._invoices:
            dialogs.show_error(self, "Export", "No invoices to export.")
            return
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Invoices",
            "invoices_export.xlsx",
            "Excel Files (*.xlsx)",
        )
        if not file_path:
            return
        if not file_path.lower().endswith(".xlsx"):
            file_path = f"{file_path}.xlsx"
        invoices_with_lines = []
        for invoice in self._invoices:
            lines = self.invoice_service.get_invoice_lines(invoice.invoice_id)
            invoices_with_lines.append((invoice, lines))
        export_invoices_excel(file_path, invoices_with_lines)
        if self.action_log_service:
            admin = (
                self._current_admin_provider()
                if self._current_admin_provider
                else None
            )
            product_filter, fuzzy = self._resolve_product_filter()
            jy_from, jm_from, jd_from = self.from_date.jalali_date()
            jy_to, jm_to, jd_to = self.to_date.jalali_date()
            filter_text = product_filter if product_filter else "همه کالاها"
            filter_type = "دقیق" if product_filter and not fuzzy else "جزئی"
            self.action_log_service.log_action(
                "invoice_batch_export",
                "خروجی گروهی فاکتور",
                (
                    f"بازه تاریخ: {jy_from:04d}/{jm_from:02d}/{jd_from:02d} "
                    f"تا {jy_to:04d}/{jm_to:02d}/{jd_to:02d}\n"
                    f"فیلتر کالا: {filter_text}\n"
                    f"نوع فیلتر: {filter_type}\n"
                    f"تعداد فاکتور: {len(invoices_with_lines)}\n"
                    f"مسیر: {file_path}"
                ),
                admin=admin,
            )
        if self.toast:
            self.toast.show("Invoices exported", "success")
        else:
            dialogs.show_info(self, "Export", "Invoices exported.")
