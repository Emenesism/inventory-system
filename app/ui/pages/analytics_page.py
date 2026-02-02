from __future__ import annotations

from math import isfinite

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.services.invoice_service import InvoiceService
from app.utils.dates import to_jalali_month
from app.utils.numeric import format_amount


class AnalyticsPage(QWidget):
    _PROGRESS_MAX = 2_147_483_647

    def __init__(
        self,
        invoice_service: InvoiceService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.invoice_service = invoice_service

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        header = QHBoxLayout()
        title = QLabel("Analytics")
        title.setStyleSheet("font-size: 16px; font-weight: 600;")
        header.addWidget(title)
        header.addStretch(1)

        refresh_analytics = QPushButton("Refresh")
        refresh_analytics.clicked.connect(self.load_analytics)
        header.addWidget(refresh_analytics)
        layout.addLayout(header)

        stats_card = QFrame()
        stats_card.setObjectName("Card")
        stats_layout = QHBoxLayout(stats_card)
        stats_layout.setContentsMargins(16, 16, 16, 16)
        stats_layout.setSpacing(24)

        self.sales_total_label = QLabel("Sales total: 0")
        self.purchase_total_label = QLabel("Purchase total: 0")
        self.profit_total_label = QLabel("Profit: 0")
        self.invoice_count_label = QLabel("Invoices: 0")

        stats_layout.addWidget(self.sales_total_label)
        stats_layout.addWidget(self.purchase_total_label)
        stats_layout.addWidget(self.profit_total_label)
        stats_layout.addWidget(self.invoice_count_label)
        stats_layout.addStretch(1)
        layout.addWidget(stats_card)

        summary_card = QFrame()
        summary_card.setObjectName("Card")
        summary_layout = QVBoxLayout(summary_card)
        summary_layout.setContentsMargins(16, 16, 16, 16)

        self.monthly_table = QTableWidget(0, 6)
        self.monthly_table.setHorizontalHeaderLabels(
            ["Month (IR)", "Sales", "Purchases", "Profit", "Invoices", "Trend"]
        )
        header_view = self.monthly_table.horizontalHeader()
        header_view.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(5, QHeaderView.Stretch)
        self.monthly_table.verticalHeader().setDefaultSectionSize(32)
        self.monthly_table.setAlternatingRowColors(True)
        self.monthly_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        summary_layout.addWidget(self.monthly_table)
        layout.addWidget(summary_card)

        self.load_analytics()

    def load_analytics(self) -> None:
        summary = self.invoice_service.get_monthly_summary()
        total_sales = sum(item["sales_total"] for item in summary)
        total_purchases = sum(item["purchase_total"] for item in summary)
        total_profit = sum(item["profit"] for item in summary)
        total_invoices = sum(item["invoice_count"] for item in summary)

        self.sales_total_label.setText(
            f"Sales total: {self._format_amount(total_sales)}"
        )
        self.purchase_total_label.setText(
            f"Purchase total: {self._format_amount(total_purchases)}"
        )
        self.profit_total_label.setText(
            f"Profit: {self._format_amount(total_profit)}"
        )
        self.invoice_count_label.setText(f"Invoices: {total_invoices}")

        safe_sales = [
            self._safe_progress_value(item["sales_total"]) for item in summary
        ]
        max_sales = max(safe_sales, default=0)
        self.monthly_table.setRowCount(len(summary))
        for row_idx, item in enumerate(summary):
            self.monthly_table.setItem(
                row_idx,
                0,
                QTableWidgetItem(to_jalali_month(item["month"])),
            )

            sales_item = QTableWidgetItem(
                self._format_amount(item["sales_total"])
            )
            sales_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.monthly_table.setItem(row_idx, 1, sales_item)

            purchase_item = QTableWidgetItem(
                self._format_amount(item["purchase_total"])
            )
            purchase_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.monthly_table.setItem(row_idx, 2, purchase_item)

            profit_item = QTableWidgetItem(self._format_amount(item["profit"]))
            profit_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.monthly_table.setItem(row_idx, 3, profit_item)

            count_item = QTableWidgetItem(str(item["invoice_count"]))
            count_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.monthly_table.setItem(row_idx, 4, count_item)

            bar = QProgressBar()
            bar.setRange(0, max_sales if max_sales > 0 else 1)
            bar.setValue(self._safe_progress_value(item["sales_total"]))
            bar.setTextVisible(False)
            self.monthly_table.setCellWidget(row_idx, 5, bar)

    @staticmethod
    def _format_amount(value: float) -> str:
        return format_amount(value)

    @classmethod
    def _safe_progress_value(cls, value: float) -> int:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return 0
        if not isfinite(numeric):
            return cls._PROGRESS_MAX if numeric > 0 else 0
        if numeric <= 0:
            return 0
        if numeric >= cls._PROGRESS_MAX:
            return cls._PROGRESS_MAX
        return int(numeric)
