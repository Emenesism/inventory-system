from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDateEdit,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.services.invoice_service import InvoiceService, InvoiceSummary
from app.ui.widgets.toast import ToastManager
from app.utils import dialogs
from app.utils.dates import to_jalali_datetime
from app.utils.excel import export_invoices_excel
from app.utils.numeric import format_amount


class InvoiceBatchExportDialog(QDialog):
    def __init__(
        self,
        invoice_service: InvoiceService,
        toast: ToastManager | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.invoice_service = invoice_service
        self.toast = toast
        self._invoices: list[InvoiceSummary] = []

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
        self.from_date = QDateEdit()
        self.from_date.setCalendarPopup(True)
        row.addWidget(self.from_date)
        row.addSpacing(20)
        row.addWidget(QLabel("Until:"))
        self.to_date = QDateEdit()
        self.to_date.setCalendarPopup(True)
        row.addWidget(self.to_date)
        row.addStretch(1)
        date_layout.addLayout(row)

        self.jalali_hint = QLabel("")
        self.jalali_hint.setStyleSheet("color: #6B7280; font-size: 11px;")
        date_layout.addWidget(self.jalali_hint)

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

        today = QDate.currentDate()
        self.from_date.setDate(today.addDays(-30))
        self.to_date.setDate(today)
        self.from_date.dateChanged.connect(self._reload)
        self.to_date.dateChanged.connect(self._reload)
        self._reload()

    def _reload(self) -> None:
        start_date = self.from_date.date()
        end_date = self.to_date.date()
        if end_date < start_date:
            self.summary_label.setText("End date must be after start date.")
            self.export_button.setEnabled(False)
            self.table.setRowCount(0)
            return

        start_dt = datetime(
            start_date.year(),
            start_date.month(),
            start_date.day(),
            0,
            0,
            0,
            tzinfo=ZoneInfo("Asia/Tehran"),
        )
        end_dt = datetime(
            end_date.year(),
            end_date.month(),
            end_date.day(),
            23,
            59,
            59,
            tzinfo=ZoneInfo("Asia/Tehran"),
        )
        start_iso = start_dt.isoformat(timespec="seconds")
        end_iso = end_dt.isoformat(timespec="seconds")
        self._invoices = self.invoice_service.list_invoices_between(
            start_iso, end_iso
        )
        self._update_jalali_hint(start_dt, end_dt)
        self._populate_table()
        self.export_button.setEnabled(bool(self._invoices))

    def _update_jalali_hint(self, start_dt: datetime, end_dt: datetime) -> None:
        start_jalali = to_jalali_datetime(
            start_dt.isoformat(timespec="seconds")
        ).split(" ")[0]
        end_jalali = to_jalali_datetime(
            end_dt.isoformat(timespec="seconds")
        ).split(" ")[0]
        self.jalali_hint.setText(
            f"Jalali range: {start_jalali} تا {end_jalali}"
        )

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
        if self.toast:
            self.toast.show("Invoices exported", "success")
        else:
            dialogs.show_info(self, "Export", "Invoices exported.")
