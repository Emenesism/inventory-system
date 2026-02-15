from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QToolButton,
    QWidget,
)


class HeaderBar(QFrame):
    lock_requested = Signal()
    help_requested = Signal()
    menu_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("HeaderBar")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 10, 20, 10)
        layout.setSpacing(10)

        self.menu_button = QToolButton()
        self.menu_button.setObjectName("MenuButton")
        self.menu_button.setText(self.tr("منو"))
        self.menu_button.setToolTip(self.tr("نمایش/پنهان کردن نوار کناری"))
        self.menu_button.clicked.connect(self.menu_requested.emit)
        self.menu_button.setVisible(False)
        layout.addWidget(self.menu_button)

        title = QLabel(self.tr("حسابداری و انبار"))
        title.setObjectName("AppTitle")
        title.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        layout.addWidget(title)

        self.status_label = QLabel(self.tr("موجودی بارگذاری نشده است"))
        self.status_label.setObjectName("StatusLabel")
        self.status_label.setMinimumWidth(0)
        self.status_label.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Fixed
        )
        self.status_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(self.status_label)
        layout.addStretch(1)

        self.lock_button = QToolButton()
        self.lock_button.setObjectName("LockButton")
        self.lock_button.setText(self.tr("قفل"))
        self.lock_button.setToolTip(self.tr("قفل برنامه"))
        self.lock_button.clicked.connect(self.lock_requested.emit)
        layout.addWidget(self.lock_button)

        self.help_button = QToolButton()
        self.help_button.setObjectName("HelpButton")
        self.help_button.setText("؟")
        self.help_button.setToolTip(self.tr("راهنما"))
        self.help_button.clicked.connect(self.help_requested.emit)
        layout.addWidget(self.help_button)

    def set_status(self, message: str) -> None:
        self.status_label.setText(message)

    def set_theme_label(self, theme: str) -> None:
        pass

    def set_menu_button_visible(self, visible: bool) -> None:
        self.menu_button.setVisible(visible)
