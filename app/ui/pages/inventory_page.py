from __future__ import annotations

from PySide6.QtCore import Qt, Signal
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

from app.utils.search import NormalizedFilterProxyModel
from app.utils.table_models import DataFrameTableModel


class InventoryPage(QWidget):
    reload_requested = Signal()
    save_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._model: DataFrameTableModel | None = None
        self._proxy: NormalizedFilterProxyModel | None = None
        self._editable_columns: list[str] | None = None
        self._blocked_columns: set[str] | None = None

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

    def set_inventory(
        self,
        dataframe,
        editable_columns: list[str] | None = None,
        blocked_columns: list[str] | None = None,
    ) -> None:  # noqa: ANN001
        if dataframe is None:
            return
        if editable_columns is not None:
            self._editable_columns = editable_columns
            self._blocked_columns = None
        if blocked_columns is not None:
            self._blocked_columns = set(blocked_columns)
            self._editable_columns = None
        filter_text = self.search_input.text()
        active_editable = self._editable_columns
        if active_editable is None and self._blocked_columns:
            active_editable = [
                col
                for col in dataframe.columns
                if col not in self._blocked_columns
            ]
        self._model = DataFrameTableModel(
            dataframe, editable_columns=active_editable
        )
        self._proxy = NormalizedFilterProxyModel(self)
        self._proxy.setSourceModel(self._model)
        self.table.setModel(self._proxy)
        if filter_text:
            self._proxy.set_filter_text(filter_text)
        self.table.resizeColumnsToContents()

    def get_dataframe(self):  # noqa: ANN001
        if not self._model:
            return None
        return self._model.dataframe()

    def set_editable_columns(self, editable_columns: list[str] | None) -> None:
        self._editable_columns = editable_columns
        self._blocked_columns = None
        if not self._model:
            return
        current_df = self._model.dataframe()
        self.set_inventory(current_df, editable_columns=editable_columns)

    def set_blocked_columns(self, blocked_columns: list[str] | None) -> None:
        self._blocked_columns = (
            set(blocked_columns) if blocked_columns else None
        )
        self._editable_columns = None
        if not self._model:
            return
        current_df = self._model.dataframe()
        self.set_inventory(current_df, blocked_columns=blocked_columns)

    def set_enabled_state(self, enabled: bool) -> None:
        self.search_input.setEnabled(enabled)
        self.reload_button.setEnabled(enabled)
        self.save_button.setEnabled(enabled)
        self.table.setEnabled(enabled)

    def _apply_filter(self, text: str) -> None:
        if self._proxy:
            self._proxy.set_filter_text(text)
