from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
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

from app.core.config import AppConfig
from app.services.inventory_service import InventoryService
from app.utils.numeric import normalize_numeric_text


class LowStockPage(QWidget):
    def __init__(
        self,
        inventory_service: InventoryService,
        config: AppConfig,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.inventory_service = inventory_service
        self.config = config
        self._rows: list[dict[str, object]] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        header = QHBoxLayout()
        title = QLabel("Low Stock Alerts")
        title.setStyleSheet("font-size: 16px; font-weight: 600;")
        header.addWidget(title)
        header.addStretch(1)

        export_button = QPushButton("Export")
        export_button.clicked.connect(self._export)
        header.addWidget(export_button)

        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self.refresh)
        header.addWidget(refresh_button)
        layout.addLayout(header)

        summary_card = QFrame()
        summary_card.setObjectName("Card")
        summary_layout = QHBoxLayout(summary_card)
        summary_layout.setContentsMargins(16, 16, 16, 16)
        summary_layout.setSpacing(24)

        self.items_label = QLabel("Items below alarm: 0")
        self.total_needed_label = QLabel("Total needed: 0")
        summary_layout.addWidget(self.items_label)
        summary_layout.addWidget(self.total_needed_label)
        summary_layout.addStretch(1)
        layout.addWidget(summary_card)

        table_card = QFrame()
        table_card.setObjectName("Card")
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(16, 16, 16, 16)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Product", "Quantity", "Alarm", "Needed", "Avg Buy", "Source"]
        )
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setDefaultSectionSize(32)
        table_layout.addWidget(self.table)
        layout.addWidget(table_card)

    def set_enabled_state(self, enabled: bool) -> None:
        self.table.setEnabled(enabled)

    def refresh(self) -> None:
        if not self.inventory_service.is_loaded():
            self.table.setRowCount(0)
            self.items_label.setText("Items below alarm: 0")
            self.total_needed_label.setText("Total needed: 0")
            return

        df = self.inventory_service.get_dataframe()

        rows: list[dict[str, object]] = []
        for _, row in df.iterrows():
            qty = int(row.get("quantity", 0))
            alarm_value = row.get("alarm", self.config.low_stock_threshold)
            alarm = self._parse_alarm(alarm_value)
            if qty >= alarm:
                continue
            needed = alarm - qty
            source_value = row.get("source", "")
            source_text = "" if source_value is None else str(source_value)
            if source_text.lower() == "nan":
                source_text = ""
            rows.append(
                {
                    "product": str(row.get("product_name", "")).strip(),
                    "quantity": qty,
                    "alarm": alarm,
                    "needed": needed,
                    "avg_buy": float(row.get("avg_buy_price", 0.0)),
                    "source": source_text.strip(),
                }
            )

        self._rows = rows
        self.items_label.setText(f"Items below alarm: {len(rows)}")
        self.total_needed_label.setText(
            f"Total needed: {sum(item['needed'] for item in rows)}"
        )

        self.table.setRowCount(len(rows))
        for row_idx, item in enumerate(rows):
            self.table.setItem(row_idx, 0, QTableWidgetItem(item["product"]))

            qty_item = QTableWidgetItem(str(item["quantity"]))
            qty_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row_idx, 1, qty_item)

            min_item = QTableWidgetItem(str(item["alarm"]))
            min_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row_idx, 2, min_item)

            needed_item = QTableWidgetItem(str(item["needed"]))
            needed_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row_idx, 3, needed_item)

            avg_item = QTableWidgetItem(self._format_amount(item["avg_buy"]))
            avg_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row_idx, 4, avg_item)

            self.table.setItem(row_idx, 5, QTableWidgetItem(item["source"]))

    def _export(self) -> None:
        if not self._rows:
            return
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Low Stock List",
            "low_stock.xlsx",
            "Excel Files (*.xlsx);;CSV Files (*.csv)",
        )
        if not file_path:
            return

        import pandas as pd

        df = pd.DataFrame(self._rows)
        df = df.rename(
            columns={
                "product": "Product",
                "quantity": "Quantity",
                "alarm": "Alarm",
                "needed": "Needed",
                "avg_buy": "Avg Buy",
                "source": "Source",
            }
        )
        if file_path.lower().endswith(".csv"):
            df.to_csv(file_path, index=False)
        else:
            df.to_excel(file_path, index=False)

    @staticmethod
    def _format_amount(value: float) -> str:
        return f"{value:,.0f}"

    @staticmethod
    def _parse_alarm(value: object) -> int:
        if value is None:
            return 0
        if isinstance(value, (int, float)):
            if value != value:
                return 0
            return int(value)
        if isinstance(value, str):
            normalized = normalize_numeric_text(value)
            if not normalized:
                return 0
            try:
                return int(float(normalized))
            except ValueError:
                return 0
        return 0
