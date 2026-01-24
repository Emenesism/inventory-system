from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from app.services.fuzzy_search import get_fuzzy_matches
from app.services.purchase_service import PurchaseLine


class PurchaseInvoicePage(QWidget):
    submit_requested = Signal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.product_provider: Callable[[], list[str]] | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        header = QHBoxLayout()
        title = QLabel("Purchase Invoice")
        title.setStyleSheet("font-size: 16px; font-weight: 600;")
        header.addWidget(title)
        header.addStretch(1)
        layout.addLayout(header)

        table_card = QFrame()
        table_card.setObjectName("Card")
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(16, 16, 16, 16)
        table_layout.setSpacing(12)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(
            ["Product", "Buy Price", "Quantity"]
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table_layout.addWidget(self.table)

        button_row = QHBoxLayout()
        self.add_button = QPushButton("Add Line")
        self.add_button.clicked.connect(self.add_row)
        button_row.addWidget(self.add_button)

        self.remove_button = QPushButton("Remove Selected")
        self.remove_button.clicked.connect(self.remove_selected)
        button_row.addWidget(self.remove_button)

        button_row.addStretch(1)

        self.submit_button = QPushButton("Submit Invoice")
        self.submit_button.clicked.connect(self._emit_submit)
        button_row.addWidget(self.submit_button)
        table_layout.addLayout(button_row)

        layout.addWidget(table_card)

        self.add_row()

    def set_product_provider(self, provider: Callable[[], list[str]]) -> None:
        self.product_provider = provider

    def add_row(self) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)

        product_input = QLineEdit()
        product_input.setPlaceholderText("Start typing...")
        product_input.textEdited.connect(
            lambda text, widget=product_input: self._update_completer(
                text, widget
            )
        )

        price_input = QDoubleSpinBox()
        price_input.setRange(0.01, 1_000_000)
        price_input.setDecimals(2)
        price_input.setValue(1.0)

        quantity_input = QSpinBox()
        quantity_input.setRange(1, 1_000_000)
        quantity_input.setValue(1)

        self.table.setCellWidget(row, 0, product_input)
        self.table.setCellWidget(row, 1, price_input)
        self.table.setCellWidget(row, 2, quantity_input)

    def remove_selected(self) -> None:
        rows = sorted(
            set(index.row() for index in self.table.selectedIndexes()),
            reverse=True,
        )
        for row in rows:
            self.table.removeRow(row)

    def collect_lines(self) -> list[PurchaseLine]:
        lines: list[PurchaseLine] = []
        for row in range(self.table.rowCount()):
            product_widget = self.table.cellWidget(row, 0)
            price_widget = self.table.cellWidget(row, 1)
            qty_widget = self.table.cellWidget(row, 2)
            if not isinstance(product_widget, QLineEdit):
                continue
            product_name = product_widget.text().strip()
            price = (
                price_widget.value()
                if isinstance(price_widget, QDoubleSpinBox)
                else 0.0
            )
            quantity = (
                qty_widget.value() if isinstance(qty_widget, QSpinBox) else 0
            )
            lines.append(
                PurchaseLine(
                    product_name=product_name, price=price, quantity=quantity
                )
            )
            lines.append(
                PurchaseLine(
                    product_name=product_name, price=price, quantity=quantity
                )
            )
        return lines

    def set_enabled_state(self, enabled: bool) -> None:
        self.add_button.setEnabled(enabled)
        self.remove_button.setEnabled(enabled)
        self.submit_button.setEnabled(enabled)
        self.table.setEnabled(enabled)

    def _emit_submit(self) -> None:
        self.submit_requested.emit(self.collect_lines())

    def _update_completer(self, text: str, widget: QLineEdit) -> None:
        if not self.product_provider:
            return
        matches = get_fuzzy_matches(text, self.product_provider())
        if not matches:
            widget.setCompleter(None)
            return
        from PySide6.QtCore import QStringListModel, Qt
        from PySide6.QtWidgets import QCompleter

        model = QStringListModel(matches)
        completer = QCompleter(model, widget)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        widget.setCompleter(completer)
        completer.complete()
