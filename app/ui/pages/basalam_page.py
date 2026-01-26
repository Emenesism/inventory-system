from __future__ import annotations

import json
import math

import requests
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.config import AppConfig
from app.services.basalam_service import list_vendor_orders
from app.utils import dialogs


class BasalamPage(QWidget):
    def __init__(
        self, config: AppConfig, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.config = config
        self._dataframe = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        header = QHBoxLayout()
        title = QLabel("Basalam Orders")
        title.setStyleSheet("font-size: 16px; font-weight: 600;")
        header.addWidget(title)
        header.addStretch(1)

        self.fetch_button = QPushButton("Fetch")
        self.fetch_button.clicked.connect(self._fetch)
        header.addWidget(self.fetch_button)

        self.export_button = QPushButton("Export")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self._export)
        header.addWidget(self.export_button)
        layout.addLayout(header)

        helper = QLabel(
            "Access token is read from config.json (key: access_token). "
            "Vendor ID is required."
        )
        helper.setStyleSheet("color: #9CA3AF;")
        layout.addWidget(helper)

        form_card = QFrame()
        form_card.setObjectName("Card")
        form_layout = QGridLayout(form_card)
        form_layout.setContentsMargins(16, 16, 16, 16)
        form_layout.setHorizontalSpacing(12)
        form_layout.setVerticalSpacing(12)

        vendor_label = QLabel("Vendor ID")
        self.vendor_input = QLineEdit()
        self.vendor_input.setPlaceholderText("e.g. 563284")
        form_layout.addWidget(vendor_label, 0, 0)
        form_layout.addWidget(self.vendor_input, 0, 1)

        tab_label = QLabel("Tab")
        self.tab_input = QComboBox()
        self.tab_input.addItems(
            ["NOT_SHIPPED", "SHIPPED", "PENDING", "COMPLETED"]
        )
        self.tab_input.setCurrentText("SHIPPED")
        form_layout.addWidget(tab_label, 1, 0)
        form_layout.addWidget(self.tab_input, 1, 1)

        start_paid_label = QLabel("Start paid at")
        self.start_paid_input = QLineEdit()
        self.start_paid_input.setPlaceholderText(
            "YYYY-MM-DD or YYYY-MM-DD HH:MM:SS"
        )
        form_layout.addWidget(start_paid_label, 2, 0)
        form_layout.addWidget(self.start_paid_input, 2, 1)

        end_paid_label = QLabel("End paid at")
        self.end_paid_input = QLineEdit()
        self.end_paid_input.setPlaceholderText(
            "YYYY-MM-DD or YYYY-MM-DD HH:MM:SS"
        )
        form_layout.addWidget(end_paid_label, 3, 0)
        form_layout.addWidget(self.end_paid_input, 3, 1)

        limit_label = QLabel("Limit")
        self.limit_input = QSpinBox()
        self.limit_input.setRange(1, 200)
        self.limit_input.setValue(10)
        form_layout.addWidget(limit_label, 4, 0)
        form_layout.addWidget(self.limit_input, 4, 1)

        offset_label = QLabel("Offset")
        self.offset_input = QSpinBox()
        self.offset_input.setRange(0, 1_000_000)
        self.offset_input.setValue(0)
        form_layout.addWidget(offset_label, 5, 0)
        form_layout.addWidget(self.offset_input, 5, 1)

        layout.addWidget(form_card)

        self.summary_label = QLabel("No data loaded.")
        self.summary_label.setStyleSheet("color: #6B7280;")
        layout.addWidget(self.summary_label)

        table_card = QFrame()
        table_card.setObjectName("Card")
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(16, 16, 16, 16)

        self.table = QTableWidget(0, 0)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSortingEnabled(True)
        table_layout.addWidget(self.table)

        layout.addWidget(table_card)

    def _fetch(self) -> None:
        access_token = (self.config.access_token or "").strip()
        if not access_token:
            dialogs.show_error(
                self,
                "Basalam Token Missing",
                "Set access_token in config.json before fetching.",
            )
            return

        vendor_id = self.vendor_input.text().strip()
        if not vendor_id:
            dialogs.show_error(
                self,
                "Vendor ID Required",
                "Please enter the vendor ID from the Basalam URL.",
            )
            return

        tab = self.tab_input.currentText().strip() or None
        start_paid_at = self.start_paid_input.text().strip() or None
        end_paid_at = self.end_paid_input.text().strip() or None
        limit = self.limit_input.value()
        offset = self.offset_input.value()

        self.fetch_button.setEnabled(False)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            payload = list_vendor_orders(
                vendor_id=vendor_id,
                tab=tab,
                start_paid_at=start_paid_at,
                end_paid_at=end_paid_at,
                limit=limit,
                offset=offset,
                access_token=access_token,
            )
        except requests.HTTPError as exc:
            message = str(exc)
            if exc.response is not None and exc.response.text:
                message = f"{message}\n\n{exc.response.text}"
            dialogs.show_error(self, "Basalam Error", message)
            return
        except requests.RequestException as exc:
            dialogs.show_error(self, "Basalam Error", str(exc))
            return
        finally:
            self.fetch_button.setEnabled(True)
            QApplication.restoreOverrideCursor()

        df = self._payload_to_dataframe(payload)
        self._dataframe = df
        self._update_table(df)
        self.export_button.setEnabled(df is not None and not df.empty)

    def _export(self) -> None:
        if self._dataframe is None or self._dataframe.empty:
            return

        from PySide6.QtWidgets import QFileDialog

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Basalam Orders",
            "basalam_orders.xlsx",
            "Excel Files (*.xlsx);;CSV Files (*.csv)",
        )
        if not file_path:
            return

        if file_path.lower().endswith(".csv"):
            self._dataframe.to_csv(file_path, index=False)
        else:
            self._dataframe.to_excel(file_path, index=False)

    def _payload_to_dataframe(self, payload):
        import pandas as pd

        records = self._extract_records(payload)
        if not records:
            return pd.DataFrame()

        df = pd.json_normalize(records, sep="__")
        df = df.applymap(self._format_nested)
        df = df.rename(columns=self._pretty_column)
        return df

    @staticmethod
    def _extract_records(payload) -> list[dict]:
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            data = payload.get("data")
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                return [data]
            for key in ("items", "results", "parcels", "orders"):
                value = payload.get(key)
                if isinstance(value, list):
                    return value
            for key in ("items", "results", "parcels", "orders"):
                value = data.get(key) if isinstance(data, dict) else None
                if isinstance(value, list):
                    return value
            return [payload]
        return []

    @staticmethod
    def _pretty_column(name: str) -> str:
        cleaned = (
            str(name).replace("__", " ").replace(".", " ").replace("_", " ")
        )
        tokens = []
        for token in cleaned.split():
            lowered = token.lower()
            if lowered in {"id", "sku", "url"}:
                tokens.append(lowered.upper())
            else:
                tokens.append(token.capitalize())
        return " ".join(tokens)

    @staticmethod
    def _format_nested(value):
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return value

    def _update_table(self, df) -> None:
        if df is None or df.empty:
            self.table.setRowCount(0)
            self.table.setColumnCount(0)
            self.summary_label.setText("No data returned.")
            return

        max_rows = min(len(df), 200)
        self.table.setColumnCount(len(df.columns))
        self.table.setRowCount(max_rows)
        self.table.setHorizontalHeaderLabels([str(c) for c in df.columns])

        for row_idx in range(max_rows):
            row = df.iloc[row_idx]
            for col_idx, value in enumerate(row):
                item = QTableWidgetItem(self._format_cell(value))
                if isinstance(value, (int, float)) and not self._is_nan(value):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(row_idx, col_idx, item)

        self.table.resizeColumnsToContents()
        if len(df) > max_rows:
            self.summary_label.setText(f"Showing {max_rows} of {len(df)} rows.")
        else:
            self.summary_label.setText(f"{len(df)} rows loaded.")

    @staticmethod
    def _format_cell(value) -> str:
        if value is None:
            return ""
        if isinstance(value, float) and math.isnan(value):
            return ""
        return str(value)

    @staticmethod
    def _is_nan(value: float) -> bool:
        return isinstance(value, float) and math.isnan(value)
