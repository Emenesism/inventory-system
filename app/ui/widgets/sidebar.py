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

        brand = QLabel(
            self.tr(
                '<span style="color:#DC2626;">آرم</span>'
                '<span style="color:#111111;">کالا</span>'
            )
        )
        brand.setObjectName("SidebarBrand")
        brand.setTextFormat(Qt.RichText)
        layout.addWidget(brand)

        self.button_group = QButtonGroup(self)
        self.button_group.setExclusive(True)
        self.buttons: dict[str, QToolButton] = {}
        icon_map = {
            "Inventory": QStyle.SP_DriveHDIcon,
            "Sales Import": QStyle.SP_DialogOpenButton,
            "Purchase Invoice": QStyle.SP_FileDialogNewFolder,
            "Invoices": QStyle.SP_FileDialogInfoView,
            "Analytics": QStyle.SP_ComputerIcon,
            "Low Stock": QStyle.SP_MessageBoxWarning,
            "Basalam": QStyle.SP_DriveNetIcon,
            "Actions": QStyle.SP_FileDialogDetailedView,
            "Reports/Logs": QStyle.SP_FileDialogDetailedView,
            "Settings": QStyle.SP_FileDialogContentsView,
        }
        title_map = {
            "Inventory": self.tr("موجودی"),
            "Sales Import": self.tr("ثبت فاکتور فروش"),
            "Purchase Invoice": self.tr("ثبت فاکتور خرید"),
            "Invoices": self.tr("فاکتورها"),
            "Analytics": self.tr("تحلیل"),
            "Low Stock": self.tr("کمبود موجودی"),
            "Basalam": self.tr("باسلام"),
            "Actions": self.tr("اقدامات"),
            "Reports/Logs": self.tr("گزارش/لاگ"),
            "Settings": self.tr("تنظیمات"),
        }

        for name in [
            "Inventory",
            "Sales Import",
            "Purchase Invoice",
            "Invoices",
            "Analytics",
            "Low Stock",
            "Basalam",
            "Actions",
            "Reports/Logs",
            "Settings",
        ]:
            button = QToolButton()
            button.setObjectName("SidebarButton")
            button.setText(title_map.get(name, name))
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
            layout.addWidget(button)
            self.buttons[name] = button

        layout.addStretch(1)

    def set_active(self, name: str) -> None:
        if name in self.buttons:
            self.buttons[name].setChecked(True)
