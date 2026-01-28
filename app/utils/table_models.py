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
        self, dataframe: pd.DataFrame, editable_columns: list[str] | None = None
    ) -> None:
        super().__init__()
        self._dataframe = dataframe.copy()
        self._editable_columns = (
            set(editable_columns) if editable_columns else None
        )

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return len(self._dataframe.index)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return len(self._dataframe.columns)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):  # noqa: ANN001
        if not index.isValid():
            return None

        column_name = self._dataframe.columns[index.column()]
        value = self._dataframe.iat[index.row(), index.column()]
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
                str(self._dataframe.columns[section]).replace("_", " ").title()
            )
        return str(section + 1)

    def flags(self, index: QModelIndex):  # noqa: ANN001
        if not index.isValid():
            return Qt.ItemIsEnabled
        column_name = self._dataframe.columns[index.column()]
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
            self._dataframe.iat[index.row(), index.column()] = numeric
        elif column_name == "avg_buy_price":
            try:
                text_value = normalize_numeric_text(str(value))
                numeric = float(text_value)
                if numeric < 0:
                    return False
            except (TypeError, ValueError):
                return False
            self._dataframe.iat[index.row(), index.column()] = numeric
        else:
            self._dataframe.iat[index.row(), index.column()] = value

        self.dataChanged.emit(index, index, [Qt.DisplayRole, Qt.EditRole])
        return True

    def set_dataframe(self, dataframe: pd.DataFrame) -> None:
        self.beginResetModel()
        self._dataframe = dataframe.copy()
        self.endResetModel()

    def dataframe(self) -> pd.DataFrame:
        return self._dataframe.copy()
