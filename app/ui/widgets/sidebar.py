from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class Sidebar(QFrame):
    page_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Sidebar")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        brand = QLabel("Reza Inventory")
        brand.setStyleSheet(
            "color: #FFFFFF; font-weight: 600; font-size: 16px;"
        )
        layout.addWidget(brand)

        self.buttons: dict[str, QToolButton] = {}
        icon_map = {
            "Inventory": QStyle.SP_DriveHDIcon,
            "Sales Import": QStyle.SP_DialogOpenButton,
            "Purchase Invoice": QStyle.SP_FileDialogNewFolder,
            "Reports/Logs": QStyle.SP_FileDialogDetailedView,
        }

        for name in [
            "Inventory",
            "Sales Import",
            "Purchase Invoice",
            "Reports/Logs",
        ]:
            button = QToolButton()
            button.setObjectName("SidebarButton")
            button.setText(name)
            button.setIcon(
                self.style().standardIcon(
                    icon_map.get(name, QStyle.SP_FileIcon)
                )
            )
            button.setCheckable(True)
            button.setAutoExclusive(True)
            button.clicked.connect(
                lambda checked, key=name: self.page_selected.emit(key)
            )
            layout.addWidget(button)
            self.buttons[name] = button

        layout.addStretch(1)

    def set_active(self, name: str) -> None:
        if name in self.buttons:
            self.buttons[name].setChecked(True)
