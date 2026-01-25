from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
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
        self.setMinimumWidth(220)

        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        brand = QLabel("Armkala")
        brand.setStyleSheet(
            "color: #FFFFFF; font-weight: 700; font-size: 18px;"
        )
        layout.addWidget(brand)

        self.button_group = QButtonGroup(self)
        self.button_group.setExclusive(True)
        self.buttons: dict[str, QToolButton] = {}
        icon_map = {
            "Inventory": QStyle.SP_DriveHDIcon,
            "Sales Import": QStyle.SP_DialogOpenButton,
            "Purchase Invoice": QStyle.SP_FileDialogNewFolder,
            "Reports/Logs": QStyle.SP_FileDialogDetailedView,
        }
        hint_map = {
            "Inventory": "View and edit stock",
            "Sales Import": "Apply sales from Excel",
            "Purchase Invoice": "Add new purchases",
            "Reports/Logs": "App log",
        }

        for name in [
            "Inventory",
            "Sales Import",
            "Purchase Invoice",
            "Reports/Logs",
        ]:
            item = QWidget()
            item_layout = QVBoxLayout(item)
            item_layout.setContentsMargins(0, 0, 0, 0)
            item_layout.setSpacing(6)

            button = QToolButton()
            button.setObjectName("SidebarButton")
            button.setText(name)
            button.setIcon(
                self.style().standardIcon(
                    icon_map.get(name, QStyle.SP_FileIcon)
                )
            )
            button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            button.setIconSize(QSize(18, 18))
            button.setCheckable(True)
            button.clicked.connect(
                lambda checked, key=name: self.page_selected.emit(key)
            )
            self.button_group.addButton(button)
            item_layout.addWidget(button)

            hint = QLabel(hint_map.get(name, ""))
            hint.setObjectName("SidebarHint")
            item_layout.addWidget(hint)

            layout.addWidget(item)
            self.buttons[name] = button

        layout.addStretch(1)

    def set_active(self, name: str) -> None:
        if name in self.buttons:
            self.buttons[name].setChecked(True)
