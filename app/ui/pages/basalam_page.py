from __future__ import annotations

import json
import math

import requests
from PySide6.QtCore import Qt, QTime
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.config import AppConfig
from app.services.basalam_service import list_vendor_orders
from app.utils import dialogs
from app.utils.dates import jalali_month_days, jalali_to_gregorian, jalali_today

PERSIAN_MONTHS = [
    "Farvardin",
    "Ordibehesht",
    "Khordad",
    "Tir",
    "Mordad",
    "Shahrivar",
    "Mehr",
    "Aban",
    "Azar",
    "Dey",
    "Bahman",
    "Esfand",
]

TARGET_STATUS_FA = "رضایت مشتری"
PAGE_LIMIT = 30


class JalaliDateTimePicker(QWidget):
    def __init__(
        self,
        parent: QWidget | None = None,
        default_time: QTime | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.year_combo = QComboBox()
        self.month_combo = QComboBox()
        self.day_combo = QComboBox()
        self.time_edit = QTimeEdit()
        self.time_edit.setDisplayFormat("HH:mm:ss")

        for year in range(1390, 1451):
            self.year_combo.addItem(str(year), year)
        for idx, name in enumerate(PERSIAN_MONTHS, start=1):
            self.month_combo.addItem(f"{idx:02d} {name}", idx)

        layout.addWidget(self.year_combo)
        layout.addWidget(self.month_combo)
        layout.addWidget(self.day_combo)
        layout.addWidget(self.time_edit)

        self.year_combo.currentIndexChanged.connect(self._refresh_days)
        self.month_combo.currentIndexChanged.connect(self._refresh_days)

        jy, jm, jd = jalali_today()
        self._set_date(jy, jm, jd)
        if default_time is not None:
            self.time_edit.setTime(default_time)

    def _set_date(self, jy: int, jm: int, jd: int) -> None:
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

    def to_gregorian_str(self) -> str:
        jy, jm, jd = self.jalali_date()
        gy, gm, gd = jalali_to_gregorian(jy, jm, jd)
        time_text = self.time_edit.time().toString("HH:mm:ss")
        return f"{gy:04d}-{gm:02d}-{gd:02d} {time_text}"


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

        form_card = QFrame()
        form_card.setObjectName("Card")
        form_layout = QGridLayout(form_card)
        form_layout.setContentsMargins(16, 16, 16, 16)
        form_layout.setHorizontalSpacing(12)
        form_layout.setVerticalSpacing(12)

        start_paid_label = QLabel("Start paid at (Jalali)")
        self.start_paid_input = JalaliDateTimePicker(
            default_time=QTime(0, 0, 0)
        )
        form_layout.addWidget(start_paid_label, 0, 0)
        form_layout.addWidget(self.start_paid_input, 0, 1)

        end_paid_label = QLabel("End paid at (Jalali)")
        self.end_paid_input = JalaliDateTimePicker(
            default_time=QTime(23, 59, 59)
        )
        form_layout.addWidget(end_paid_label, 1, 0)
        form_layout.addWidget(self.end_paid_input, 1, 1)

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

        vendor_id = "563284"

        start_paid_at = self.start_paid_input.to_gregorian_str()
        end_paid_at = self.end_paid_input.to_gregorian_str()
        tab = "COMPLECTED"

        self.fetch_button.setEnabled(False)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            records, total_count = self._fetch_all_records(
                vendor_id=vendor_id,
                tab=tab,
                start_paid_at=start_paid_at,
                end_paid_at=end_paid_at,
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

        df = self._records_to_dataframe(records)
        self._dataframe = df
        self._update_table(df)
        self.export_button.setEnabled(df is not None and not df.empty)
        if total_count == 0:
            self.summary_label.setText("No data returned.")
        elif df.empty:
            self.summary_label.setText(
                f"{total_count} rows fetched, 0 matched {TARGET_STATUS_FA}."
            )
        else:
            self.summary_label.setText(
                f"{len(df)} rows matched {TARGET_STATUS_FA} out of {total_count} fetched."
            )

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

    def _fetch_all_records(
        self,
        vendor_id: str,
        tab: str,
        start_paid_at: str,
        end_paid_at: str,
        access_token: str,
    ) -> tuple[list[dict], int]:
        offset = 0
        all_records: list[dict] = []
        seen_ids: set[str] = set()
        while True:
            payload = list_vendor_orders(
                vendor_id=vendor_id,
                tab=tab,
                start_paid_at=start_paid_at,
                end_paid_at=end_paid_at,
                limit=PAGE_LIMIT,
                offset=offset,
                access_token=access_token,
            )
            batch = self._extract_records(payload)
            if not batch:
                break

            unique_batch = []
            for item in batch:
                item_id = (
                    str(item.get("id", "")) if isinstance(item, dict) else ""
                )
                if item_id and item_id in seen_ids:
                    continue
                if item_id:
                    seen_ids.add(item_id)
                unique_batch.append(item)

            before_count = len(all_records)
            all_records.extend(unique_batch)
            if len(all_records) == before_count:
                break
            if len(batch) < PAGE_LIMIT:
                break
            offset += PAGE_LIMIT

        filtered = self._filter_records(all_records)
        return filtered, len(all_records)

    def _filter_records(self, records: list[dict]) -> list[dict]:
        return [
            record
            for record in records
            if self._status_matches(record, TARGET_STATUS_FA)
        ]

    def _status_matches(self, record: dict, target: str) -> bool:
        if not isinstance(record, dict):
            return False
        for key, value in record.items():
            key_lower = str(key).lower()
            if (
                "status" in key_lower
                or "state" in key_lower
                or "وضعیت" in key_lower
            ):
                if self._value_matches_status(value, target):
                    return True
        return False

    def _value_matches_status(self, value, target: str) -> bool:
        if isinstance(value, str):
            return value.strip() == target
        if isinstance(value, dict):
            for key in ("title", "name", "label", "value", "fa", "fa_IR"):
                inner = value.get(key)
                if isinstance(inner, str) and inner.strip() == target:
                    return True
            for key, inner in value.items():
                if "status" in str(key).lower() and isinstance(inner, str):
                    if inner.strip() == target:
                        return True
        return False

    def _records_to_dataframe(self, records):
        import pandas as pd

        rows = self._extract_summary_rows(records)
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(
            rows, columns=["Customer Name", "Product Name", "Quantity"]
        )

    def _extract_summary_rows(self, records: list[dict]) -> list[dict]:
        rows: list[dict] = []
        for record in records:
            if not isinstance(record, dict):
                continue
            customer_name = self._get_customer_name(record)
            items = self._get_items(record)
            if items:
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    product_name = self._get_product_name(item)
                    quantity = self._get_quantity(item)
                    if product_name is None and quantity is None:
                        continue
                    rows.append(
                        {
                            "Customer Name": customer_name or "",
                            "Product Name": product_name or "",
                            "Quantity": "" if quantity is None else quantity,
                        }
                    )
                continue

            product_name = self._get_product_name(record)
            quantity = self._get_quantity(record)
            if not (customer_name or product_name or quantity is not None):
                continue
            rows.append(
                {
                    "Customer Name": customer_name or "",
                    "Product Name": product_name or "",
                    "Quantity": "" if quantity is None else quantity,
                }
            )

        return rows

    def _get_items(self, record: dict) -> list[dict]:
        for key in (
            "items",
            "order_items",
            "orderItems",
            "line_items",
            "lines",
            "products",
        ):
            value = record.get(key)
            if isinstance(value, list):
                return value
        return []

    def _get_customer_name(self, record: dict) -> str | None:
        for key in ("customer", "buyer", "user", "client"):
            value = record.get(key)
            name = self._extract_name_from_value(value)
            if name:
                return name
        for key in (
            "customer_data_user_name",
            "customer_data_userName",
            "customerDataUserName",
            "customer_data_user",
            "customerDataUser",
        ):
            value = record.get(key)
            name = self._extract_name_from_value(value)
            if name:
                return name
        for path in (
            ("customer_data", "user", "name"),
            ("customer_data", "user_name"),
            ("customer_data", "userName"),
            ("customer_data", "user", "full_name"),
            ("customer_data", "user", "fullName"),
            ("customerData", "user", "name"),
            ("customerData", "user_name"),
            ("customerData", "userName"),
        ):
            value = self._get_nested_value(record, path)
            name = self._extract_name_from_value(value)
            if name:
                return name
        for key in (
            "customer_name",
            "buyer_name",
            "user_name",
            "full_name",
            "fullname",
        ):
            value = record.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def _extract_name_from_value(self, value) -> str | None:
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            for key in (
                "full_name",
                "fullname",
                "name",
                "title",
                "user_name",
                "userName",
            ):
                name = value.get(key)
                if isinstance(name, str) and name.strip():
                    return name.strip()
            first = value.get("first_name") or value.get("firstname")
            last = value.get("last_name") or value.get("lastname")
            if isinstance(first, str) and isinstance(last, str):
                full = f"{first.strip()} {last.strip()}".strip()
                return full if full else None
        return None

    @staticmethod
    def _get_nested_value(record: dict, path: tuple[str, ...]):
        current = record
        for key in path:
            if not isinstance(current, dict):
                return None
            if key not in current:
                return None
            current = current[key]
        return current

    def _get_product_name(self, record: dict) -> str | None:
        value = record.get("product")
        name = self._extract_name_from_value(value)
        if name:
            return name
        for key in (
            "product_name",
            "productTitle",
            "product_title",
            "title",
            "name",
        ):
            value = record.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def _get_quantity(self, record: dict):
        for key in ("quantity", "qty", "count", "amount", "number"):
            value = record.get(key)
            if value is None:
                continue
            if isinstance(value, (int, float)):
                return int(value) if isinstance(value, bool) is False else value
            if isinstance(value, str):
                cleaned = value.strip()
                if cleaned.isdigit():
                    return int(cleaned)
                return cleaned
        return None

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
