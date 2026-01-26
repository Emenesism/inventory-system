from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QStyle,
    QToolButton,
    QWidget,
)


class HeaderBar(QFrame):
    inventory_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("HeaderBar")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 12, 20, 12)
        layout.setSpacing(12)

        title = QLabel("Accounting & Inventory")
        title.setObjectName("AppTitle")
        layout.addWidget(title)

        self.status_label = QLabel("No inventory loaded")
        self.status_label.setObjectName("StatusLabel")
        layout.addWidget(self.status_label)
        layout.addStretch(1)

        self.select_inventory_button = QToolButton()
        self.select_inventory_button.setObjectName("SelectInventoryButton")
        self.select_inventory_button.setText("Select Inventory File")
        self.select_inventory_button.setIcon(
            self.style().standardIcon(QStyle.SP_DialogOpenButton)
        )
        self.select_inventory_button.clicked.connect(
            self.inventory_requested.emit
        )
        layout.addWidget(self.select_inventory_button)

    def set_status(self, message: str) -> None:
        self.status_label.setText(message)

    def set_theme_label(self, theme: str) -> None:
        pass
