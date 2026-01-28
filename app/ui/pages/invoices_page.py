from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.services.invoice_service import InvoiceService, InvoiceSummary
from app.utils.dates import to_jalali_datetime
from app.utils.numeric import format_amount


class InvoicesPage(QWidget):
    def __init__(
        self, invoice_service: InvoiceService, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.invoice_service = invoice_service
        self.invoices: list[InvoiceSummary] = []
        self._page_size = 200
        self._loaded_count = 0
        self._total_count = 0
        self._total_amount = 0.0
        self._loading_more = False
        self._show_prices = True

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        header = QHBoxLayout()
        title = QLabel("Invoices")
        title.setStyleSheet("font-size: 16px; font-weight: 600;")
        header.addWidget(title)
        header.addStretch(1)

        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self.refresh)
        header.addWidget(refresh_button)

        self.load_more_button = QPushButton("Load More")
        self.load_more_button.clicked.connect(self._load_more)
        self.load_more_button.setEnabled(False)
        header.addWidget(self.load_more_button)
        layout.addLayout(header)

        summary_card = QFrame()
        summary_card.setObjectName("Card")
        summary_layout = QHBoxLayout(summary_card)
        summary_layout.setContentsMargins(16, 16, 16, 16)
        summary_layout.setSpacing(24)

        self.total_invoices_label = QLabel("Total invoices: 0")
        self.total_amount_label = QLabel("Total amount: 0")
        summary_layout.addWidget(self.total_invoices_label)
        summary_layout.addWidget(self.total_amount_label)
        summary_layout.addStretch(1)
        layout.addWidget(summary_card)

        list_card = QFrame()
        list_card.setObjectName("Card")
        list_layout = QVBoxLayout(list_card)
        list_layout.setContentsMargins(16, 16, 16, 16)

        self.invoices_table = QTableWidget(0, 5)
        self.invoices_table.setHorizontalHeaderLabels(
            ["Date (IR)", "Type", "Lines", "Quantity", "Total"]
        )
        header_view = self.invoices_table.horizontalHeader()
        header_view.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(4, QHeaderView.Stretch)
        self.invoices_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.invoices_table.setAlternatingRowColors(True)
        self.invoices_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.invoices_table.horizontalHeader().setStretchLastSection(True)
        self.invoices_table.verticalHeader().setDefaultSectionSize(34)
        self.invoices_table.setMinimumHeight(240)
        self.invoices_table.itemSelectionChanged.connect(
            self._show_selected_details
        )
        self.invoices_table.verticalScrollBar().valueChanged.connect(
            self._maybe_load_more
        )
        list_layout.addWidget(self.invoices_table)
        layout.addWidget(list_card)

        details_card = QFrame()
        details_card.setObjectName("Card")
        details_layout = QVBoxLayout(details_card)
        details_layout.setContentsMargins(16, 16, 16, 16)
        details_layout.setSpacing(12)

        self.details_label = QLabel("Select an invoice to view details.")
        details_layout.addWidget(self.details_label)

        self.lines_table = QTableWidget(0, 4)
        self.lines_table.setHorizontalHeaderLabels(
            ["Product", "Price", "Qty", "Line Total"]
        )
        lines_header = self.lines_table.horizontalHeader()
        lines_header.setSectionResizeMode(0, QHeaderView.Stretch)
        lines_header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        lines_header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        lines_header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.lines_table.setAlternatingRowColors(True)
        self.lines_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.lines_table.horizontalHeader().setStretchLastSection(True)
        self.lines_table.verticalHeader().setDefaultSectionSize(32)
        self.lines_table.setMinimumHeight(200)
        details_layout.addWidget(self.lines_table)

        layout.addWidget(details_card)
        self._apply_price_visibility()
        self.refresh()

    def refresh(self) -> None:
        self.invoices = []
        self._loaded_count = 0
        self._total_count, self._total_amount = (
            self.invoice_service.get_invoice_stats()
        )
        self.total_invoices_label.setText(
            f"Total invoices: {self._total_count}"
        )
        self._set_total_amount_label()
        self.invoices_table.blockSignals(True)
        self.invoices_table.setRowCount(0)
        self.invoices_table.blockSignals(False)
        self.details_label.setText("Select an invoice to view details.")
        self.lines_table.setRowCount(0)
        self._load_more()

    def _show_selected_details(self) -> None:
        row = self.invoices_table.currentRow()
        if row < 0:
            return
        item = self.invoices_table.item(row, 0)
        if not item:
            return
        invoice_id = item.data(Qt.UserRole)
        lines = self.invoice_service.get_invoice_lines(int(invoice_id))

        inv = next(
            (inv for inv in self.invoices if inv.invoice_id == invoice_id),
            None,
        )
        if inv:
            header_parts = [
                self._format_type(inv.invoice_type),
                to_jalali_datetime(inv.created_at),
            ]
            if self._show_prices:
                header_parts.append(
                    f"Total {self._format_amount(inv.total_amount)}"
                )
            else:
                header_parts.append("Total hidden")
            header = " | ".join(header_parts)
        else:
            header = "Invoice details"
        self.details_label.setText(header)

        self.lines_table.setRowCount(len(lines))
        for row_idx, line in enumerate(lines):
            self.lines_table.setItem(
                row_idx, 0, QTableWidgetItem(line.product_name)
            )
            price_item = QTableWidgetItem(self._format_amount(line.price))
            price_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.lines_table.setItem(row_idx, 1, price_item)

            qty_item = QTableWidgetItem(str(line.quantity))
            qty_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.lines_table.setItem(row_idx, 2, qty_item)

            total_item = QTableWidgetItem(self._format_amount(line.line_total))
            total_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.lines_table.setItem(row_idx, 3, total_item)

    def _maybe_load_more(self) -> None:
        if self._loading_more or self._loaded_count >= self._total_count:
            return
        bar = self.invoices_table.verticalScrollBar()
        if bar.maximum() == 0:
            return
        if bar.value() >= bar.maximum() - 20:
            self._load_more()

    def _load_more(self) -> None:
        if self._loading_more or self._loaded_count >= self._total_count:
            self.load_more_button.setEnabled(False)
            return
        self._loading_more = True
        batch = self.invoice_service.list_invoices(
            limit=self._page_size, offset=self._loaded_count
        )
        if not batch:
            self._loading_more = False
            self.load_more_button.setEnabled(False)
            if not self.invoices:
                self.details_label.setText("No invoices yet.")
            return

        start_row = self.invoices_table.rowCount()
        self.invoices_table.setUpdatesEnabled(False)
        self.invoices_table.blockSignals(True)
        self.invoices_table.setRowCount(start_row + len(batch))
        for row_offset, invoice in enumerate(batch):
            row_idx = start_row + row_offset
            date_item = QTableWidgetItem(to_jalali_datetime(invoice.created_at))
            date_item.setData(Qt.UserRole, invoice.invoice_id)
            self.invoices_table.setItem(row_idx, 0, date_item)
            self.invoices_table.setItem(
                row_idx,
                1,
                QTableWidgetItem(self._format_type(invoice.invoice_type)),
            )
            lines_item = QTableWidgetItem(str(invoice.total_lines))
            lines_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.invoices_table.setItem(row_idx, 2, lines_item)

            qty_item = QTableWidgetItem(str(invoice.total_qty))
            qty_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.invoices_table.setItem(row_idx, 3, qty_item)

            total_value = (
                self._format_amount(invoice.total_amount)
                if self._show_prices
                else ""
            )
            total_item = QTableWidgetItem(total_value)
            total_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.invoices_table.setItem(row_idx, 4, total_item)

        self.invoices.extend(batch)
        self._loaded_count += len(batch)
        self.invoices_table.blockSignals(False)
        self.invoices_table.setUpdatesEnabled(True)
        self._loading_more = False
        self.load_more_button.setEnabled(self._loaded_count < self._total_count)
        if start_row == 0 and self.invoices:
            self.invoices_table.selectRow(0)

    @staticmethod
    def _format_type(value: str) -> str:
        if value == "purchase":
            return "Purchase"
        if value == "sales":
            return "Sales"
        return value.title()

    @staticmethod
    def _format_amount(value: float) -> str:
        return format_amount(value)

    def set_price_visibility(self, show: bool) -> None:
        self._show_prices = bool(show)
        self._apply_price_visibility()
        self._set_total_amount_label()
        if self.invoices_table.currentRow() >= 0:
            self._show_selected_details()

    def _apply_price_visibility(self) -> None:
        self.invoices_table.setColumnHidden(4, not self._show_prices)
        self.lines_table.setColumnHidden(1, not self._show_prices)
        self.lines_table.setColumnHidden(3, not self._show_prices)

    def _set_total_amount_label(self) -> None:
        if self._show_prices:
            self.total_amount_label.setText(
                f"Total amount: {self._format_amount(self._total_amount)}"
            )
        else:
            self.total_amount_label.setText("Total amount: Hidden")
