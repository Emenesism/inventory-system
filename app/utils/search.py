from __future__ import annotations

from PySide6.QtCore import QSortFilterProxyModel, Qt

from app.utils.text import normalize_text


def normalize_search_text(value: str) -> str:
    return normalize_text(value)


class NormalizedFilterProxyModel(QSortFilterProxyModel):
    def __init__(self, parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self._filter_text = ""

    def headerData(  # noqa: N802, ANN001
        self, section: int, orientation, role: int = Qt.DisplayRole
    ):
        # Keep row numbering contiguous in current proxy order
        # (after sort/filter), instead of source row indices.
        if role == Qt.DisplayRole and orientation == Qt.Vertical:
            return str(section + 1)
        return super().headerData(section, orientation, role)

    def set_filter_text(self, text: str) -> None:
        self._filter_text = normalize_search_text(text)
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent) -> bool:  # noqa: ANN001, N802
        if not self._filter_text:
            return True
        source_model = self.sourceModel()
        if source_model is None:
            return True
        try:
            search_text = source_model.search_text(source_row)
        except Exception:  # noqa: BLE001
            search_text = None
        if search_text is not None:
            return self._filter_text in search_text
        column_count = source_model.columnCount()
        for column in range(column_count):
            index = source_model.index(source_row, column, source_parent)
            data = source_model.data(index, Qt.DisplayRole)
            if data is None:
                continue
            if self._filter_text in normalize_search_text(str(data)):
                return True
        return False
