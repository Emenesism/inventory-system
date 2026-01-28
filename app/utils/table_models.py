from __future__ import annotations

import numpy as np
import pandas as pd
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from app.utils.numeric import (
    format_amount,
    is_price_column,
    normalize_numeric_text,
)


class DataFrameTableModel(QAbstractTableModel):
    def __init__(
        self,
        dataframe: pd.DataFrame,
        editable_columns: list[str] | None = None,
        lazy_load: bool = False,
        chunk_size: int = 400,
    ) -> None:
        super().__init__()
        self._full_dataframe = dataframe.copy()
        self._editable_columns = (
            set(editable_columns) if editable_columns else None
        )
        self._lazy_enabled = bool(lazy_load)
        self._chunk_size = max(int(chunk_size), 1)
        self._visible_rows = (
            min(self._chunk_size, len(self._full_dataframe))
            if self._lazy_enabled
            else len(self._full_dataframe)
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
        if role == Qt.DisplayRole:
            if pd.isna(value):
                return "-" if column_name in {"منبع", "source"} else ""
            if isinstance(value, np.integer):
                value = int(value)
            elif isinstance(value, np.floating):
                value = float(value)
            if column_name in {"quantity", "avg_buy_price"} and value == 0:
                return ""
            if is_price_column(column_name):
                return format_amount(value)
            return value
        if role == Qt.EditRole:
            if pd.isna(value):
                return ""
            if isinstance(value, np.integer):
                return int(value)
            if isinstance(value, np.floating):
                return float(value)
            return value
        if role == Qt.TextAlignmentRole:
            return Qt.AlignVCenter | Qt.AlignLeft
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
        column_name = self._dataframe.columns[index.column()]
        if (
            self._editable_columns is not None
            and column_name not in self._editable_columns
        ):
            return False

        if column_name == "quantity":
            try:
                text_value = normalize_numeric_text(str(value))
                numeric = int(text_value)
                if numeric < 0:
                    return False
            except (TypeError, ValueError):
                return False
            self._full_dataframe.iat[index.row(), index.column()] = numeric
        elif column_name == "avg_buy_price":
            try:
                text_value = normalize_numeric_text(str(value))
                numeric = float(text_value)
                if numeric < 0:
                    return False
            except (TypeError, ValueError):
                return False
            self._full_dataframe.iat[index.row(), index.column()] = numeric
        else:
            self._full_dataframe.iat[index.row(), index.column()] = value

        self.dataChanged.emit(index, index, [Qt.DisplayRole, Qt.EditRole])
        return True

    def set_dataframe(self, dataframe: pd.DataFrame) -> None:
        self.beginResetModel()
        self._full_dataframe = dataframe.copy()
        self._visible_rows = (
            min(self._chunk_size, len(self._full_dataframe))
            if self._lazy_enabled
            else len(self._full_dataframe)
        )
        self.endResetModel()

    def dataframe(self) -> pd.DataFrame:
        return self._full_dataframe.copy()

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
