from __future__ import annotations

from PySide6.QtCore import QSortFilterProxyModel, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from app.utils.table_models import DataFrameTableModel


class InventoryPage(QWidget):
    reload_requested = Signal()
    save_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._model: DataFrameTableModel | None = None
        self._proxy: QSortFilterProxyModel | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        header = QHBoxLayout()
        title = QLabel("Inventory Overview")
        title.setStyleSheet("font-size: 16px; font-weight: 600;")
        header.addWidget(title)
        header.addStretch(1)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search products...")
        self.search_input.textChanged.connect(self._apply_filter)
        header.addWidget(self.search_input)

        self.reload_button = QPushButton("Reload")
        self.reload_button.clicked.connect(self.reload_requested.emit)
        header.addWidget(self.reload_button)

        self.save_button = QPushButton("Save Changes")
        self.save_button.clicked.connect(self.save_requested.emit)
        header.addWidget(self.save_button)

        layout.addLayout(header)

        card = QFrame()
        card.setObjectName("Card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)

        self.table = QTableView()
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QAbstractItemView.AllEditTriggers)
        card_layout.addWidget(self.table)

        layout.addWidget(card)

    def set_inventory(self, dataframe) -> None:  # noqa: ANN001
        if dataframe is None:
            return
        self._model = DataFrameTableModel(dataframe)
        self._proxy = QSortFilterProxyModel(self)
        self._proxy.setSourceModel(self._model)
        self._proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self._proxy.setFilterKeyColumn(-1)
        self.table.setModel(self._proxy)
        self.table.resizeColumnsToContents()

    def get_dataframe(self):  # noqa: ANN001
        if not self._model:
            return None
        return self._model.dataframe()

    def set_enabled_state(self, enabled: bool) -> None:
        self.search_input.setEnabled(enabled)
        self.reload_button.setEnabled(enabled)
        self.save_button.setEnabled(enabled)
        self.table.setEnabled(enabled)

    def _apply_filter(self, text: str) -> None:
        if self._proxy:
            self._proxy.setFilterFixedString(text)
