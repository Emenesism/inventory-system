from __future__ import annotations

import numpy as np
import pandas as pd
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtGui import QColor

from app.utils.numeric import (
    format_amount,
    format_number,
    is_price_column,
    normalize_numeric_text,
)
from app.utils.text import is_empty_marker, normalize_text


class DataFrameTableModel(QAbstractTableModel):
    _INVENTORY_NUMERIC_COLUMNS = {
        "quantity",
        "avg_buy_price",
        "last_buy_price",
        "sell_price",
        "alarm",
    }

    cell_edited = Signal(int, str, object, object)

    def __init__(
        self,
        dataframe: pd.DataFrame,
        editable_columns: list[str] | None = None,
        header_labels: dict[str, str] | None = None,
        lazy_load: bool = False,
        chunk_size: int = 400,
        sell_price_alarm_percent: float = 20.0,
    ) -> None:
        super().__init__()
        self._full_dataframe = dataframe.copy()
        self._editable_columns = (
            set(editable_columns) if editable_columns else None
        )
        self._header_labels = (
            {str(key): str(value) for key, value in header_labels.items()}
            if header_labels
            else {}
        )
        self._lazy_enabled = bool(lazy_load)
        self._chunk_size = max(int(chunk_size), 1)
        self._sell_price_alarm_percent = self._sanitize_alarm_percent(
            sell_price_alarm_percent
        )
        self._visible_rows = (
            min(self._chunk_size, len(self._full_dataframe))
            if self._lazy_enabled
            else len(self._full_dataframe)
        )
        self._search_cache = self._build_search_cache()

    def set_sell_price_alarm_percent(self, percent: float) -> None:
        sanitized = self._sanitize_alarm_percent(percent)
        if abs(self._sell_price_alarm_percent - sanitized) < 1e-6:
            return
        self._sell_price_alarm_percent = sanitized
        if self._visible_rows <= 0:
            return
        sell_col = self._column_index("sell_price")
        if sell_col is None:
            return
        top_left = self.index(0, sell_col)
        bottom_right = self.index(self._visible_rows - 1, sell_col)
        self.dataChanged.emit(
            top_left,
            bottom_right,
            [Qt.BackgroundRole, Qt.ToolTipRole, Qt.UserRole],
        )

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return self._visible_rows

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return len(self._full_dataframe.columns)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):  # noqa: ANN001
        if not index.isValid():
            return None
        if index.row() >= self._visible_rows:
            return None

        column_name = self._full_dataframe.columns[index.column()]
        value = self._full_dataframe.iat[index.row(), index.column()]
        is_product_column = self._is_product_column(column_name)
        if role == Qt.DisplayRole:
            if pd.isna(value) or is_empty_marker(value):
                return "-" if column_name in {"منبع", "source"} else ""
            if isinstance(value, np.integer):
                value = int(value)
            elif isinstance(value, np.floating):
                value = float(value)
            if (
                column_name
                in {"quantity", "avg_buy_price", "last_buy_price", "sell_price"}
                and value == 0
            ):
                return ""
            if column_name == "quantity":
                # Keep inventory quantity digits as Latin (English) numerals.
                formatted = format_number(value)
                return self._ltr_numeric_text(formatted) if formatted else ""
            if is_price_column(column_name):
                formatted = format_amount(value)
                return self._ltr_numeric_text(formatted) if formatted else ""
            if is_product_column:
                return self._rtl_text(value)
            if isinstance(value, (int, float)):
                formatted = format_number(value)
                return self._ltr_numeric_text(formatted) if formatted else ""
            return value
        if role == Qt.UserRole:
            return self._sort_value(index.row(), str(column_name), value)
        if role == Qt.EditRole:
            if pd.isna(value) or is_empty_marker(value):
                return ""
            normalized_column = str(column_name).strip().lower()
            if normalized_column in self._INVENTORY_NUMERIC_COLUMNS or (
                isinstance(value, (np.integer, np.floating, int, float))
                and not isinstance(value, bool)
            ):
                return format_number(value)
            return value
        if role == Qt.TextAlignmentRole:
            if is_product_column:
                # Force visual right alignment even when Qt mirrors in RTL.
                return Qt.AlignVCenter | Qt.AlignRight | Qt.AlignAbsolute
            return Qt.AlignCenter
        if role == Qt.BackgroundRole:
            normalized_column = (
                str(column_name)
                .strip()
                .lower()
                .replace("-", "_")
                .replace(" ", "_")
            )
            if normalized_column == "sell_price":
                severity = self._sell_price_alert_severity(index.row())
                if severity <= 0:
                    return None
                alpha = max(55, min(230, int(55 + severity * 175)))
                return QColor(220, 38, 38, alpha)
        if role == Qt.ToolTipRole:
            normalized_column = (
                str(column_name)
                .strip()
                .lower()
                .replace("-", "_")
                .replace(" ", "_")
            )
            if normalized_column == "sell_price":
                tooltip = self._sell_price_tooltip(index.row())
                return tooltip or None
        return None

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.DisplayRole,
    ):  # noqa: N802, ANN001
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            column_key = str(self._full_dataframe.columns[section])
            localized = self._header_labels.get(column_key)
            if localized:
                return localized
            return (
                str(self._full_dataframe.columns[section])
                .replace("_", " ")
                .title()
            )
        return str(section + 1)

    def flags(self, index: QModelIndex):  # noqa: ANN001
        if not index.isValid():
            return Qt.ItemIsEnabled
        column_name = self._full_dataframe.columns[index.column()]
        flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if (
            self._editable_columns is None
            or column_name in self._editable_columns
        ):
            flags |= Qt.ItemIsEditable
        return flags

    def setData(self, index: QModelIndex, value, role: int = Qt.EditRole):  # noqa: ANN001, N802
        if role != Qt.EditRole or not index.isValid():
            return False
        if index.row() >= self._visible_rows:
            return False
        column_name = self._full_dataframe.columns[index.column()]
        if (
            self._editable_columns is not None
            and column_name not in self._editable_columns
        ):
            return False
        old_value = self._full_dataframe.iat[index.row(), index.column()]

        if column_name == "quantity":
            try:
                numeric = self._parse_integer_value(value)
                if numeric is None:
                    return False
                if numeric < 0:
                    return False
            except (TypeError, ValueError):
                return False
            self._full_dataframe.iat[index.row(), index.column()] = numeric
        elif column_name in {"avg_buy_price", "last_buy_price", "sell_price"}:
            try:
                numeric = self._parse_integer_value(value)
                if numeric is None:
                    return False
                if numeric < 0:
                    return False
            except (TypeError, ValueError):
                return False
            self._full_dataframe.iat[index.row(), index.column()] = float(
                numeric
            )
        elif column_name == "alarm":
            try:
                numeric = self._parse_integer_value(value)
                if numeric is None:
                    return False
                if numeric < 0:
                    return False
            except (TypeError, ValueError):
                return False
            self._full_dataframe.iat[index.row(), index.column()] = numeric
        else:
            self._full_dataframe.iat[index.row(), index.column()] = value

        self.dataChanged.emit(index, index, [Qt.DisplayRole, Qt.EditRole])
        if column_name in {"sell_price", "last_buy_price"}:
            sell_col = self._column_index("sell_price")
            if sell_col is not None:
                sell_index = self.index(index.row(), sell_col)
                self.dataChanged.emit(
                    sell_index,
                    sell_index,
                    [Qt.BackgroundRole, Qt.ToolTipRole, Qt.UserRole],
                )
        self._update_search_cache_row(index.row())
        new_value = self._full_dataframe.iat[index.row(), index.column()]
        self.cell_edited.emit(index.row(), column_name, old_value, new_value)
        return True

    def set_dataframe(self, dataframe: pd.DataFrame) -> None:
        self.beginResetModel()
        self._full_dataframe = dataframe.copy()
        self._visible_rows = (
            min(self._chunk_size, len(self._full_dataframe))
            if self._lazy_enabled
            else len(self._full_dataframe)
        )
        self._search_cache = self._build_search_cache()
        self.endResetModel()

    def dataframe(self) -> pd.DataFrame:
        return self._full_dataframe.copy()

    def search_text(self, row: int) -> str:
        if row < 0 or row >= len(self._search_cache):
            return ""
        return self._search_cache[row]

    def set_lazy_loading(
        self, enabled: bool, chunk_size: int | None = None
    ) -> None:
        if chunk_size is not None:
            self._chunk_size = max(int(chunk_size), 1)
        if self._lazy_enabled == bool(enabled):
            return
        self.beginResetModel()
        self._lazy_enabled = bool(enabled)
        self._visible_rows = (
            min(self._chunk_size, len(self._full_dataframe))
            if self._lazy_enabled
            else len(self._full_dataframe)
        )
        self.endResetModel()

    def canFetchMore(self, parent: QModelIndex = QModelIndex()) -> bool:  # noqa: N802
        if parent.isValid():
            return False
        return self._lazy_enabled and self._visible_rows < len(
            self._full_dataframe
        )

    def fetchMore(self, parent: QModelIndex = QModelIndex()) -> None:  # noqa: N802
        if parent.isValid() or not self._lazy_enabled:
            return
        remaining = len(self._full_dataframe) - self._visible_rows
        if remaining <= 0:
            return
        items_to_fetch = min(self._chunk_size, remaining)
        start = self._visible_rows
        end = self._visible_rows + items_to_fetch - 1
        self.beginInsertRows(QModelIndex(), start, end)
        self._visible_rows += items_to_fetch
        self.endInsertRows()

    def _build_search_cache(self) -> list[str]:
        if self._full_dataframe.empty:
            return []
        cache: list[str] = []
        for row in self._full_dataframe.itertuples(index=False, name=None):
            parts: list[str] = []
            for value in row:
                if pd.isna(value) or is_empty_marker(value):
                    continue
                parts.append(str(value))
            cache.append(normalize_text(" ".join(parts)))
        return cache

    def _update_search_cache_row(self, row: int) -> None:
        if row < 0 or row >= len(self._full_dataframe):
            return
        row_values = self._full_dataframe.iloc[row]
        parts: list[str] = []
        for value in row_values.values:
            if pd.isna(value) or is_empty_marker(value):
                continue
            parts.append(str(value))
        if row >= len(self._search_cache):
            self._search_cache.extend(
                [""] * (row - len(self._search_cache) + 1)
            )
        self._search_cache[row] = normalize_text(" ".join(parts))

    @staticmethod
    def _parse_integer_value(value: object) -> int | None:
        text_value = normalize_numeric_text(str(value))
        if text_value == "":
            return 0
        parsed = float(text_value)
        if not np.isfinite(parsed):
            return None
        return int(round(parsed))

    def _sort_value(self, row: int, column_name: str, value: object) -> object:
        normalized_column = (
            str(column_name).strip().lower().replace("-", "_").replace(" ", "_")
        )
        if normalized_column == "sell_price":
            margin, _shortfall, severity = self._sell_price_alert_metrics(row)
            if margin is None:
                return 0.0
            # Lower sort value means riskier pricing; header sorting can flip.
            return float(-(severity * 10000.0) + margin)
        if normalized_column in self._INVENTORY_NUMERIC_COLUMNS:
            numeric = self._as_float(value)
            if numeric is None:
                return 0.0
            return numeric
        if self._is_product_column(column_name):
            if is_empty_marker(value):
                return ""
            return normalize_text(str(value or ""))
        if is_empty_marker(value):
            return ""
        return normalize_text(str(value or ""))

    def _sell_price_alert_severity(self, row: int) -> float:
        _margin, _shortfall, severity = self._sell_price_alert_metrics(row)
        return severity

    def _sell_price_alert_metrics(
        self, row: int
    ) -> tuple[float | None, float, float]:
        last_buy = self._row_numeric(row, "last_buy_price")
        sell_price = self._row_numeric(row, "sell_price")
        if last_buy is None or last_buy <= 0:
            return None, 0.0, 0.0
        if sell_price is None:
            sell_price = 0.0

        margin = ((sell_price - last_buy) / last_buy) * 100.0
        threshold = self._sell_price_alarm_percent
        if margin < 0:
            return margin, max(0.0, threshold - margin), 1.0
        if margin >= threshold:
            return margin, 0.0, 0.0

        base = threshold if threshold > 0 else 1.0
        shortfall = threshold - margin
        severity = shortfall / base
        severity = max(0.0, min(1.0, severity))
        return margin, shortfall, severity

    def _sell_price_tooltip(self, row: int) -> str:
        margin, shortfall, severity = self._sell_price_alert_metrics(row)
        if margin is None:
            return "آخرین قیمت خرید صفر است؛ محاسبه درصد اختلاف ممکن نیست."
        if severity <= 0:
            return (
                f"اختلاف فروش نسبت به آخرین خرید: {margin:.1f}% | "
                f"حداقل مجاز: {self._sell_price_alarm_percent:.1f}%"
            )
        return (
            f"اختلاف فروش نسبت به آخرین خرید: {margin:.1f}% | "
            f"کمبود نسبت به حداقل: {shortfall:.1f}% | "
            f"حداقل مجاز: {self._sell_price_alarm_percent:.1f}%"
        )

    def _row_numeric(self, row: int, column_name: str) -> float | None:
        col = self._column_index(column_name)
        if col is None or row < 0 or row >= len(self._full_dataframe):
            return None
        return self._as_float(self._full_dataframe.iat[row, col])

    def _column_index(self, column_name: str) -> int | None:
        for idx, existing in enumerate(self._full_dataframe.columns):
            normalized = (
                str(existing)
                .strip()
                .lower()
                .replace("-", "_")
                .replace(" ", "_")
            )
            if normalized == column_name:
                return idx
        return None

    @staticmethod
    def _as_float(value: object) -> float | None:
        if value is None:
            return None
        if pd.isna(value):
            return None
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            normalized = normalize_numeric_text(str(value))
            if not normalized:
                return None
            try:
                parsed = float(normalized)
            except (TypeError, ValueError):
                return None
        if not np.isfinite(parsed):
            return None
        return float(parsed)

    @staticmethod
    def _sanitize_alarm_percent(percent: float) -> float:
        try:
            value = float(percent)
        except (TypeError, ValueError):
            return 20.0
        if not np.isfinite(value):
            return 20.0
        if value < 0:
            return 0.0
        if value > 100:
            return 100.0
        return value

    @staticmethod
    def _ltr_numeric_text(value: object) -> str:
        # Prefix with LRM so minus sign stays leading in RTL UI (e.g. -37).
        return "\u200e" + str(value)

    @staticmethod
    def _rtl_text(value: object) -> str:
        # Prefix with RLM so mixed Persian/Latin product names keep RTL flow.
        return "\u200f" + str(value)

    @staticmethod
    def _is_product_column(column_name: object) -> bool:
        normalized = (
            str(column_name).strip().lower().replace("-", "_").replace(" ", "_")
        )
        if normalized in {
            "product_name",
            "product",
            "name",
            "نام_محصول",
            "نام_کالا",
            "کالا",
            "محصول",
        }:
            return True
        return "product" in normalized and "name" in normalized
