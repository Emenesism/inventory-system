from __future__ import annotations

from PySide6.QtCore import QSortFilterProxyModel, Qt

from app.utils.numeric import normalize_numeric_text


def normalize_search_text(value: str) -> str:
    text = normalize_numeric_text(value)
    return text.casefold()


class NormalizedFilterProxyModel(QSortFilterProxyModel):
    def __init__(self, parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self._filter_text = ""

    def set_filter_text(self, text: str) -> None:
        self._filter_text = normalize_search_text(text)
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent) -> bool:  # noqa: ANN001, N802
        if not self._filter_text:
            return True
        source_model = self.sourceModel()
        if source_model is None:
            return True
        column_count = source_model.columnCount()
        for column in range(column_count):
            index = source_model.index(source_row, column, source_parent)
            data = source_model.data(index, Qt.DisplayRole)
            if data is None:
                continue
            if self._filter_text in normalize_search_text(str(data)):
                return True
        return False
